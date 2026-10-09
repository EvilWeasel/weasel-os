#!/usr/bin/env python3
"""Owned presentation lease. This helper never captures, focuses or inputs.

The Rust actor is the authority for input and cancellation. The child renderer
only draws five noninteractive layer surfaces and expires without heartbeats.
"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import socket
import stat
import struct
import subprocess
import sys
import time

REVISION = 1
MAX_RUNTIME_SECONDS = 20 * 60
POLL_SECONDS = 0.1
STATUS_TIMEOUT_SECONDS = 0.3
MAX_STATUS_BYTES = 8 * 1024 * 1024
IDENTIFIER = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")


class CapabilityError(RuntimeError):
    pass


def emit(event, **fields):
    print(json.dumps({"revision": REVISION, "event": event, **fields}, ensure_ascii=False), flush=True)


def process_start_ticks(pid):
    # /proc stat comm can contain spaces or parentheses. Fields after the final
    # ')' start at #3 (state); process starttime is #22.
    process = Path(f"/proc/{pid}")
    if process.stat().st_uid != os.getuid():
        raise CapabilityError("owner process is not owned by the current user")
    raw = (process / "stat").read_text()
    fields = raw[raw.rfind(")") + 2 :].split()
    if fields[0] in ("Z", "X", "x"):
        raise ProcessLookupError("owner process exited")
    return int(fields[19])


def runtime_dir():
    base = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    info = base.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise CapabilityError("private XDG_RUNTIME_DIR unavailable")
    directory = base / "weasel-computer-use" / "indicators"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    for check in (directory.parent, directory):
        info = check.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise CapabilityError("private indicator runtime directory unavailable")
    return directory


def task_paths(task_id):
    token = hashlib.sha256(task_id.encode()).hexdigest()[:20]
    directory = runtime_dir()
    return directory / f"task-{token}.sock", directory / f"task-{token}.json"


def read_line(stream, limit):
    timeout = stream.gettimeout()
    deadline = time.monotonic() + (timeout if timeout is not None else STATUS_TIMEOUT_SECONDS)
    buffer = bytearray()
    while len(buffer) <= limit:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise CapabilityError("response deadline elapsed")
        stream.settimeout(remaining)
        chunk = stream.recv(min(65536, limit + 1 - len(buffer)))
        if not chunk:
            raise CapabilityError("connection closed before response")
        buffer.extend(chunk)
        if b"\n" in buffer:
            line, _, remainder = buffer.partition(b"\n")
            if remainder:
                raise CapabilityError("unexpected extra response data")
            return json.loads(line)
    raise CapabilityError("response exceeds bounded size")


def desktop_status(actor_socket):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(STATUS_TIMEOUT_SECONDS)
        stream.connect(str(actor_socket))
        stream.sendall(b'{"tool":"desktop_status","arguments":{}}\n')
        result = read_line(stream, MAX_STATUS_BYTES)
    if result.get("isError"):
        raise CapabilityError("actor rejected status request")
    texts = [item["text"] for item in result.get("content", []) if item.get("type") == "text"]
    if len(texts) != 1:
        raise CapabilityError("actor status contract unavailable")
    status = json.loads(texts[0])
    if status.get("schema") != 1 or not isinstance(status.get("session_id"), str):
        raise CapabilityError("actor status contract unavailable")
    if type(status.get("epoch")) is not int or type(status.get("takeover_latched")) is not bool:
        raise CapabilityError("actor cancellation contract unavailable")
    return status


def selected_geometry(output):
    niri = os.environ.get("WEASEL_INDICATOR_NIRI", "niri")
    result = subprocess.run([niri, "msg", "--json", "outputs"], capture_output=True, timeout=1, check=True)
    outputs = json.loads(result.stdout)
    if not isinstance(outputs, dict) or output not in outputs:
        raise CapabilityError("selected Niri output unavailable")
    logical = outputs[output].get("logical")
    if not isinstance(logical, dict):
        raise CapabilityError("selected Niri output is disabled")
    geometry = tuple(logical.get(key) for key in ("x", "y", "width", "height"))
    if any(type(value) is not int for value in geometry) or geometry[2] < 320 or geometry[3] < 200:
        raise CapabilityError("selected output logical geometry unavailable")
    return geometry, logical


def status_stop_reason(status, initial):
    if status["session_id"] != initial["session_id"]:
        return "actor_session_changed"
    if status["epoch"] != initial["epoch"]:
        return "actor_cancel_epoch_changed"
    if status["takeover_latched"]:
        return "actor_takeover_latched"
    if status.get("active") is None and status.get("actor_release_confirmed") is not True:
        return "idle_release_unconfirmed"
    return None


def control(args):
    path, _ = task_paths(args.task_id)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(1)
        stream.connect(str(path))
        stream.sendall(json.dumps({"revision": REVISION, "event": args.command, "task_id": args.task_id}).encode() + b"\n")
        response = read_line(stream, 4096)
    emit("control_reply", **response)
    return 0 if response.get("ok") is True else 1


def run(args):
    task_socket, lease_path = task_paths(args.task_id)
    actor_socket = Path(os.environ.get("WEASEL_COMPUTER_USE_SOCKET", str(task_socket.parent.parent / "desktop.sock")))
    owner_pid = args.owner_pid or os.getppid()
    owner_ticks = args.owner_start_ticks if args.owner_start_ticks is not None else process_start_ticks(owner_pid)
    if process_start_ticks(owner_pid) != owner_ticks:
        raise CapabilityError("owner process identity changed before begin")
    initial = desktop_status(actor_socket)
    if initial["takeover_latched"] or initial.get("active") is not None or initial.get("queued_batches") != 0:
        raise CapabilityError("actor must be resumed and idle before indicator begin")
    if initial.get("actor_release_confirmed") is not True:
        raise CapabilityError("actor release is unconfirmed")
    geometry, logical = selected_geometry(args.output)
    if task_socket.exists() or lease_path.exists():
        raise CapabilityError("task indicator already exists; no stale owner is replaced")
    renderer_path = os.environ.get("WEASEL_INDICATOR_RENDERER")
    if not renderer_path:
        raise CapabilityError("packaged indicator renderer unavailable")
    directory = runtime_dir()
    output_token = hashlib.sha256(args.output.encode()).hexdigest()[:20]
    lock_path = directory / f"output-{output_token}.lock"
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    server = None
    renderer = None
    selector = selectors.DefaultSelector()
    reason = "initialization_failed"
    started = time.monotonic()
    deadline = started + args.max_runtime_seconds
    owned_socket_identity = None
    owned_lease_identity = None
    old_signals = {}
    stop_signal = [None]
    metadata = {
        "revision": REVISION, "task_id": args.task_id, "output": args.output,
        "pid": os.getpid(), "start_ticks": process_start_ticks(os.getpid()),
        "owner_pid": owner_pid, "owner_start_ticks": owner_ticks,
        "actor_session_id": initial["session_id"], "actor_epoch": initial["epoch"],
        "started_monotonic": started, "deadline_monotonic": deadline,
        "geometry": geometry, "control_socket": str(task_socket),
    }
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise CapabilityError("selected output has another indicator owner") from error
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(task_socket))
        os.chmod(task_socket, 0o600)
        owned_socket_identity = task_socket.stat().st_ino
        server.listen(4)
        server.setblocking(False)
        selector.register(server, selectors.EVENT_READ, "control")
        lease_fd = os.open(lease_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        owned_lease_identity = os.fstat(lease_fd).st_ino
        with os.fdopen(lease_fd, "w") as lease:
            json.dump(metadata, lease, ensure_ascii=False)
        renderer = subprocess.Popen(
            [renderer_path, args.output, args.task_id, *(str(value) for value in geometry)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1,
        )
        selector.register(renderer.stdout, selectors.EVENT_READ, "renderer")
        if args.stdin_control:
            os.set_blocking(sys.stdin.fileno(), False)
            selector.register(sys.stdin, selectors.EVENT_READ, "stdin")
        for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            old_signals[signum] = signal.signal(signum, lambda received, _frame: stop_signal.__setitem__(0, received))
        renderer.stdin.write("v1 begin\n")
        renderer.stdin.flush()
        emit("starting", task_id=args.task_id, output=args.output, pid=os.getpid(), geometry=geometry)
        next_poll = next_heartbeat = started
        next_geometry = started + 1
        ready = False
        stdin_pending = bytearray()
        while True:
            now = time.monotonic()
            if stop_signal[0] is not None:
                reason = "owner_signal"
                break
            if now >= deadline:
                reason = "maximum_runtime_expired"
                break
            if not ready and now - started > 4:
                reason = "renderer_readiness_timeout"
                break
            if renderer.poll() is not None:
                reason = "renderer_exited"
                break
            try:
                if process_start_ticks(owner_pid) != owner_ticks:
                    reason = "owner_process_changed"
                    break
            except (FileNotFoundError, ProcessLookupError):
                reason = "owner_process_exited"
                break
            if now >= next_poll:
                status = desktop_status(actor_socket)
                reason = status_stop_reason(status, initial)
                if reason:
                    break
                next_poll = time.monotonic() + POLL_SECONDS
            if now >= next_geometry:
                new_geometry, new_logical = selected_geometry(args.output)
                if new_geometry != geometry or new_logical != logical:
                    reason = "output_geometry_changed"
                    break
                next_geometry = time.monotonic() + 1
            if now >= next_heartbeat:
                renderer.stdin.write("v1 heartbeat\n")
                renderer.stdin.flush()
                next_heartbeat = now + 1
            for key, _mask in selector.select(timeout=min(POLL_SECONDS, max(0, deadline - time.monotonic()))):
                if key.data == "control":
                    with server.accept()[0] as client:
                        client.settimeout(0.05)
                        try:
                            _pid, uid, _gid = struct.unpack("3i", client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                            request = read_line(client, 4096)
                            valid = uid == os.getuid() and request.get("revision") == REVISION and request.get("task_id") == args.task_id
                            event = request.get("event")
                            response = {"ok": valid and event in ("status", "end"), "task_id": args.task_id, "ready": ready}
                            client.sendall(json.dumps(response).encode() + b"\n")
                            if valid and event == "end":
                                reason = "explicit_end"
                                stop_signal[0] = 0
                        except (OSError, ValueError, CapabilityError):
                            pass  # Invalid local control does not renew the renderer lease.
                elif key.data == "renderer":
                    line = renderer.stdout.readline()
                    if not line or len(line) > 4096:
                        reason = "renderer_pipe_closed"
                        stop_signal[0] = 0
                        continue
                    event = json.loads(line)
                    if event.get("revision") == REVISION and event.get("event") == "ready":
                        if event.get("task_id") != args.task_id or event.get("output") != args.output:
                            raise CapabilityError("renderer identity differs from owned task")
                        ready = True
                        emit("ready", task_id=args.task_id, output=args.output, surfaces=event.get("surfaces"), geometry=geometry)
                    elif event.get("event") == "ended":
                        reason = "renderer_" + str(event.get("reason", "ended"))
                        stop_signal[0] = 0
                elif key.data == "stdin":
                    chunk = os.read(sys.stdin.fileno(), 4096)
                    if not chunk:
                        reason = "owner_stdin_closed"
                        stop_signal[0] = 0
                    else:
                        stdin_pending.extend(chunk)
                        if len(stdin_pending) > 4096:
                            reason = "invalid_stdin_control"
                            stop_signal[0] = 0
                        while b"\n" in stdin_pending:
                            line, _, tail = stdin_pending.partition(b"\n")
                            stdin_pending[:] = tail
                            reason = "explicit_end" if line == b"v1 end" else "invalid_stdin_control"
                            stop_signal[0] = 0
            if stop_signal[0] == 0:
                break
        return 0 if reason in ("explicit_end", "owner_signal", "actor_cancel_epoch_changed", "actor_takeover_latched") else 1
    except (OSError, subprocess.SubprocessError, ValueError, CapabilityError) as error:
        reason = "capability_unavailable"
        # Do not print actor responses, window titles, environment or raw argv.
        emit("error", kind=type(error).__name__)
        return 1
    finally:
        cleanup_started = time.monotonic()
        # Closing the owned pipe hides the renderer even if writing end fails.
        if renderer:
            try:
                renderer.stdin.write("v1 end\n")
                renderer.stdin.flush()
            except (OSError, BrokenPipeError):
                pass
            try:
                renderer.stdin.close()
            except OSError:
                pass
            try:
                renderer.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                renderer.terminate()
                try:
                    renderer.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    renderer.kill()
                    renderer.wait(timeout=0.5)
            renderer.stdout.close()
        selector.close()
        if server:
            server.close()
        for path, inode in ((task_socket, owned_socket_identity), (lease_path, owned_lease_identity)):
            try:
                if inode is not None and path.lstat().st_ino == inode:
                    path.unlink()
            except FileNotFoundError:
                pass
        os.close(lock_fd)
        for signum, previous in old_signals.items():
            signal.signal(signum, previous)
        emit(
            "ended", task_id=args.task_id, output=args.output, reason=reason,
            renderer_exit_confirmed=renderer is None or renderer.poll() is not None,
            cleanup_ms=round((time.monotonic() - cleanup_started) * 1000, 2),
            elapsed_ms=round((time.monotonic() - started) * 1000, 2),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run", help="foreground task-owned indicator; use an owned exec session")
    runner.add_argument("--task-id", required=True)
    runner.add_argument("--output", required=True)
    runner.add_argument("--owner-pid", type=int)
    runner.add_argument("--owner-start-ticks", type=int)
    runner.add_argument("--stdin-control", action="store_true", help="EOF or v1 end on stdin also ends the indicator; use a PTY/held pipe")
    runner.add_argument("--max-runtime-seconds", type=int, default=MAX_RUNTIME_SECONDS)
    for name in ("status", "end"):
        command = commands.add_parser(name)
        command.add_argument("--task-id", required=True)
    args = parser.parse_args()
    if not IDENTIFIER.fullmatch(args.task_id):
        parser.error("task ID must contain 1–128 ASCII letters, digits, dots, dashes or underscores")
    if args.command == "run":
        if not IDENTIFIER.fullmatch(args.output):
            parser.error("invalid output identifier")
        if not 1 <= args.max_runtime_seconds <= MAX_RUNTIME_SECONDS:
            parser.error("maximum runtime must be 1–1200 seconds")
        if args.owner_pid is not None and (args.owner_pid < 1 or args.owner_start_ticks is None):
            parser.error("explicit owner PID requires its exact --owner-start-ticks")
        if args.owner_start_ticks is not None and args.owner_pid is None:
            parser.error("--owner-start-ticks requires --owner-pid")
    try:
        return run(args) if args.command == "run" else control(args)
    except (OSError, ValueError, subprocess.SubprocessError, CapabilityError) as error:
        emit("error", kind=type(error).__name__, detail=str(error) if isinstance(error, CapabilityError) else "indicator capability unavailable")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
