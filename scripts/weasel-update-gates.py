#!/usr/bin/env python3
"""Fail-closed app-only closure comparisons and private, owned startup probes.

This module never activates a system, reads a user's profile, or submits a
model request. GUI probes run in private Bubblewrap namespaces. A host-side
Unix-socket proxy permits only the public Clerk frontend needed by fresh T3
profiles; no internet route exists inside the probe namespace.
"""

import argparse
import datetime as dt
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import selectors
import shutil
import signal
import socket
import socketserver
import sqlite3
import stat
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request


class GateError(RuntimeError):
    """A required invariant failed; callers must not activate the candidate."""


KINDS = {"t3": "t3code", "codex": "codex", "chatgpt": "chatgpt"}
SOURCE_FILES = {
    "t3": "packages/t3code/source.json",
    "codex": "packages/codex-bin.nix",
    "chatgpt": "packages/chatgpt/default.nix",
}
STORE_PATH = re.compile(r"/nix/store/[0-9a-z]{32}-[^/\s]+\Z")
SRI = re.compile(r"sha256-[A-Za-z0-9+/]{43}=\Z")
VERSION_ASSIGNMENT = re.compile(rb'(?m)^  version = "([^"\n]+)";$')
HASH_ASSIGNMENT = re.compile(rb'(?m)^    hash = "([^"\n]+)";$')
GENERATED = re.compile(
    r"(?:source|etc|system-path|system-units|user-units|user-environment|"
    r"nixos-system-nixy-laptop-.+|home-manager-(?:generation|path|files|applications)|"
    r"activation-script|activate|hm-activation-script|hm-session-vars\.sh|hm_.+|"
    r"unit-.+|.+\.service|.+\.target|dbus-1|dbus-configuration|"
    r"man-paths|manual-combined|xdg-desktop-portal-.+-portals\.conf|"
    r"X-Restart-Triggers-(?:polkit|dbus)|"
    r"codex-acp-[0-9.]+|weasel-laptop-executor|codex-recovery|kai-codex-usage)\Z"
)
CLERK_HOSTS = frozenset({"clerk.t3.codes"})
PROBE_TIMEOUT = 100
MAX_CDP_BYTES = 1024 * 1024


def _command(args, *, timeout=60, env=None, cwd=None):
    try:
        result = subprocess.run(
            [str(x) for x in args], capture_output=True, timeout=timeout,
            env=env, cwd=cwd, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GateError(f"Required command unavailable or timed out: {Path(str(args[0])).name}") from error
    if result.returncode:
        # Child output can contain account material. Keep it in private fixture
        # logs rather than reflecting it into the scheduler's conversation.
        raise GateError(f"Required command failed: {Path(str(args[0])).name} (exit {result.returncode})")
    return result.stdout


def _store_root(value):
    path = str(value)
    if not STORE_PATH.fullmatch(path):
        raise GateError("Expected an exact Nix store output root")
    if not Path(path).exists() or Path(path).is_symlink():
        raise GateError("Store output is missing or is a symlink")
    return path


def _store_name(path):
    if not STORE_PATH.fullmatch(str(path)):
        raise GateError("Malformed store path in closure")
    return Path(path).name[33:]


def _app_version(kind, path):
    name = _store_name(path)
    prefix = KINDS[kind] + "-"
    value = name[len(prefix):] if name.startswith(prefix) else ""
    pattern = r"[0-9]+\.[0-9]+\.[0-9]+"
    if kind == "t3":
        pattern += r"(?:-nightly\.[0-9]{8}\.[0-9]+)?"
    if not re.fullmatch(pattern, value):
        raise GateError("Selected root does not identify an exact supported app version")
    return value


def _closure(root):
    paths = set(_command(["nix-store", "--query", "--requisites", root]).decode().splitlines())
    if root not in paths or any(not STORE_PATH.fullmatch(p) for p in paths):
        raise GateError("Incomplete or malformed Nix closure")
    return paths


def _pair(value):
    if isinstance(value, dict) and set(value) == {"old", "new"}:
        return value["old"], value["new"]
    if isinstance(value, (tuple, list)) and len(value) == 2:
        return value[0], value[1]
    raise GateError("Pairs must contain exactly old and new values")


def _bytes(value):
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    raise GateError("Source transitions require exact old and new bytes")


def _validate_source_changes(changes, selected):
    if not isinstance(changes, dict):
        raise GateError("Source transitions must include exact before/after bytes")
    allowed = {SOURCE_FILES[kind] for kind in selected} | {"agent-learnings.md"}
    if set(changes) - allowed:
        raise GateError("Source change is outside the selected app pin files")
    result = {}
    for name, values in changes.items():
        if name == "agent-learnings.md":
            continue
        old, new = map(_bytes, _pair(values))
        if old == new:
            raise GateError("Declared source transition has unchanged content")
        if name == SOURCE_FILES["t3"]:
            for data in (old, new):
                try:
                    pin = json.loads(data)
                except (ValueError, UnicodeError) as error:
                    raise GateError("Invalid T3 source JSON") from error
                if not isinstance(pin, dict) or set(pin) != {"version", "url", "hash"}:
                    raise GateError("Unexpected T3 source metadata")
                version = pin["version"]
                if not isinstance(version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:-nightly\.[0-9]{8}\.[0-9]+)?", version):
                    raise GateError("Unsupported T3 release version")
                expected = f"https://github.com/pingdotgg/t3code/releases/download/v{version}/T3-Code-{version}-x86_64.AppImage"
                if pin["url"] != expected or not isinstance(pin["hash"], str) or not SRI.fullmatch(pin["hash"]):
                    raise GateError("T3 pin is outside its immutable upstream release path")
        else:
            normalized = []
            for data in (old, new):
                versions = list(VERSION_ASSIGNMENT.finditer(data))
                hashes = list(HASH_ASSIGNMENT.finditer(data))
                if len(versions) != 1 or len(hashes) != 1:
                    raise GateError("Nix app pin must contain exactly one version and source hash")
                if not re.fullmatch(rb"[0-9]+\.[0-9]+\.[0-9]+", versions[0][1]):
                    raise GateError("Unsupported Nix app version")
                if not SRI.fullmatch(hashes[0][1].decode("ascii", errors="replace")):
                    raise GateError("Invalid Nix app source SHA-256")
                data = VERSION_ASSIGNMENT.sub(b'  version = "<app-version>";', data)
                data = HASH_ASSIGNMENT.sub(b'    hash = "<app-source-sha256>";', data)
                normalized.append(data)
            if normalized[0] != normalized[1]:
                raise GateError("Automatic Nix app transition changes packaging code or patches")
        result[name] = (old, new)
    changed_kinds = {kind for kind, path in SOURCE_FILES.items() if path in result}
    if changed_kinds != set(selected):
        raise GateError("Selected changed app roots and source transitions do not match")
    if "agent-learnings.md" in changes:
        old_log, new_log = map(_bytes, _pair(changes["agent-learnings.md"]))
        if not new_log.startswith(old_log) or not selected:
            raise GateError("Learning log must preserve its exact baseline and append verified entries")
        appended = new_log[len(old_log):]
        header = re.match(rb"\n\n### [0-9]{4}-[0-9]{2}-[0-9]{2} \(daily update candidate ([0-9]{8}[A-Za-z0-9._-]{1,120})\)\n", appended)
        if header is None:
            raise GateError("Learning log lacks the deterministic candidate entry")
        spec = importlib.util.spec_from_file_location("weasel_update_gate_discover", Path(__file__).with_name("weasel-update-discover.py"))
        discover = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(discover)
        candidate_id = header[1].decode("ascii")
        versions = {}
        for kind in sorted(selected):
            versions[kind] = [json.loads(data)["version"] if kind == "t3" else VERSION_ASSIGNMENT.search(data)[1].decode()
                              for data in result[SOURCE_FILES[kind]]]
        try:
            expected = b"".join(discover.learning_suffix(candidate_id, kind, *versions[kind]) for kind in sorted(selected))
        except (ValueError, discover.DiscoveryError) as error:
            raise GateError("Invalid deterministic learning candidate identifier") from error
        if appended != expected:
            raise GateError("Learning log differs from the exact independently generated candidate suffix")
        result["agent-learnings.md"] = (old_log, new_log)
    return result


def _tree(path, replacements, source_changes=None, side=0):
    """Compare every generated entry's type, mode, link target and file bytes."""
    def normalize(data):
        for original, token in replacements:
            data = data.replace(original, token)
        return data

    entries = {}
    stack = [(Path(path), "")]
    seen_changes = set()
    while stack:
        target, relative = stack.pop()
        info = target.lstat()
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISLNK(info.st_mode):
            entries[relative] = ("link", mode, normalize(os.fsencode(os.readlink(target))))
        elif stat.S_ISDIR(info.st_mode):
            entries[relative] = ("directory", mode)
            for child in target.iterdir():
                stack.append((child, f"{relative}/{child.name}".lstrip("/")))
        elif stat.S_ISREG(info.st_mode):
            data = target.read_bytes()
            if source_changes is not None and relative in source_changes:
                if data != source_changes[relative][side]:
                    raise GateError("Generated source does not match the verified pin transition")
                data = f"<verified-app-pin:{relative}>".encode()
                seen_changes.add(relative)
            entries[relative] = ("file", mode, hashlib.sha256(normalize(data)).hexdigest())
        else:
            raise GateError("Unsupported generated-output file type")
    if source_changes is not None and seen_changes != set(source_changes):
        raise GateError("Generated source omits a declared app pin")
    return entries


def _verify_restart_trigger(path, dependency_root, name):
    """The generated trigger must be exactly its paired generated dependency.

    The complete system-path tree is separately compared below. No extra
    policy text, arbitrary restart dependency or symlink is accepted here.
    """
    target = Path(path)
    if not dependency_root or target.is_symlink() or not target.is_file() or target.read_bytes() != dependency_root.encode():
        raise GateError(f"{name} restart trigger is not the exact paired generated dependency")


def _replacements(pairs, named):
    references = [(a, b, f"<app:{kind}>") for kind, (a, b) in sorted(pairs.items())]
    references += [(named[0][n], named[1][n], f"<generated:{n}>") for n in sorted(named[0])]
    result = [[], []]
    for before, after, token in references:
        result[0].append((before.encode(), token.encode()))
        result[1].append((after.encode(), token.encode()))
    for kind, (before, after) in pairs.items():
        result[0].append((_store_name(before).encode(), f"<app-name:{kind}>".encode()))
        result[1].append((_store_name(after).encode(), f"<app-name:{kind}>".encode()))
    for side in result:
        side.sort(key=lambda pair: -len(pair[0]))
    return result


def verify_closure(old_system, new_system, app_pairs, source_changes):
    """Verify app-only changes; return a receipt or raise GateError.

    app_pairs maps t3/codex/chatgpt to {old:root,new:root} (two-tuples also work).
    source_changes maps the exact pin path to {old:bytes,new:bytes}, or tuples.
    Dependencies inside a selected app's own closure may change. Every changed
    output outside those closures must have a paired, explicitly named generated
    output whose complete structure and content are identical after app/root
    reference normalization. Unknown or unrelated executable outputs are refused.
    """
    old_system, new_system = _store_root(old_system), _store_root(new_system)
    if not isinstance(app_pairs, dict) or set(app_pairs) - set(KINDS):
        raise GateError("Unknown selected app kind")
    pairs = {}
    for kind, value in app_pairs.items():
        before, after = map(_store_root, _pair(value))
        _app_version(kind, before)
        _app_version(kind, after)
        if before != after:
            pairs[kind] = (before, after)
    changes = _validate_source_changes(source_changes, pairs)
    for kind, roots in pairs.items():
        for root, data in zip(roots, changes[SOURCE_FILES[kind]]):
            declared = json.loads(data)["version"] if kind == "t3" else VERSION_ASSIGNMENT.search(data)[1].decode()
            if declared != _app_version(kind, root):
                raise GateError("Selected app version differs from its source transition")
    old_all, new_all = _closure(old_system), _closure(new_system)
    old_apps, new_apps = set(), set()
    for before, after in pairs.values():
        if before not in old_all or after not in new_all:
            raise GateError("Selected app root is absent from its system closure")
        old_apps |= _closure(before)
        new_apps |= _closure(after)
    outside = ((old_all - new_all) - old_apps, (new_all - old_all) - new_apps)
    grouped = []
    for paths in outside:
        names = {}
        for path in paths:
            name = _store_name(path)
            if not GENERATED.fullmatch(name):
                raise GateError(f"Unrelated or ambiguous changed store output: {name}")
            names.setdefault(name, []).append(path)
        grouped.append(names)
    if set(grouped[0]) != set(grouped[1]) or any(len(grouped[0][n]) != len(grouped[1][n]) for n in grouped[0]):
        raise GateError("Unpaired generated outputs outside the selected app closures")
    named = [{n: paths[0] for n, paths in side.items() if len(paths) == 1} for side in grouped]
    duplicates = [name for name in grouped[0] if len(grouped[0][name]) > 1]
    # Match the two NixOS D-Bus roles by complete content after normalizing only
    # already unique references. Duplicate roots never share a common token.
    unique_replacements = _replacements(pairs, named)
    for name in duplicates:
        if name != "unit-dbus.service":
            raise GateError(f"Unrelated or ambiguous changed store output: {name}")
        fingerprints = []
        for side in (0, 1):
            matching = {}
            for path in grouped[side][name]:
                tree = _tree(path, unique_replacements[side])
                digest = hashlib.sha256(json.dumps(tree, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                if digest in matching:
                    raise GateError("Generated D-Bus role pairing is ambiguous")
                matching[digest] = path
            fingerprints.append(matching)
        if set(fingerprints[0]) != set(fingerprints[1]):
            raise GateError("Non-app content changed in generated D-Bus roles")
        for digest in fingerprints[0]:
            role = f"{name}:{digest}"
            named[0][role], named[1][role] = fingerprints[0][digest], fingerprints[1][digest]
    for trigger, dependency in (("polkit", "system-path"), ("dbus", "dbus-1")):
        name = f"X-Restart-Triggers-{trigger}"
        if name in named[0]:
            for side in named:
                _verify_restart_trigger(side[name], side.get(dependency), trigger)
    replacements = _replacements(pairs, named)
    compared = []
    for name in sorted(named[0]):
        source = changes if name == "source" else None
        before = _tree(named[0][name], replacements[0], source, 0)
        after = _tree(named[1][name], replacements[1], source, 1)
        if before != after:
            raise GateError(f"Non-app content changed in generated output: {name}")
        compared.append(name)
    return {
        "ok": True, "old_system": old_system, "new_system": new_system,
        "apps": {k: {"old": a, "new": b} for k, (a, b) in sorted(pairs.items())},
        "source_changes": sorted(changes), "compared_generated_outputs": compared,
        "removed": sorted(old_all - new_all), "added": sorted(new_all - old_all),
    }


def _write_json(path, payload):
    data = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _private_directory(path):
    path = Path(path).absolute()
    if path.is_symlink():
        raise GateError("Probe directory must not be a symlink")
    if path.exists():
        info = path.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise GateError("Probe directory must be private and owned by the probe user")
        if any(path.iterdir()):
            raise GateError("Probe directory must be empty; never reuse an existing profile")
    else:
        path.mkdir(parents=True, mode=0o700)
    return path


def _tool(name):
    value = shutil.which(name)
    if not value:
        raise GateError(f"Required probe dependency missing: {name}")
    return str(Path(value).resolve(strict=True))


def _electron_version(kind, app):
    candidates = [app]
    if kind == "t3":
        candidates = [Path(p) for p in _closure(str(app)) if _store_name(p).endswith("-extracted") and "t3code-" in _store_name(p)]
    archives = [p for root in candidates for p in root.rglob("app.asar")]
    if len(archives) != 1:
        raise GateError("Built Electron app must contain exactly one app.asar archive")
    try:
        with archives[0].open("rb") as handle:
            prefix = handle.read(16)
            pickle_size, header_size, payload_size, json_size = struct.unpack("<4I", prefix)
            if pickle_size != 4 or not 0 < json_size <= 16 * 1024 * 1024 or header_size < json_size + 8:
                raise GateError("Invalid Electron archive header")
            header = json.loads(handle.read(json_size))
            metadata = header["files"]["package.json"]
            size, offset = int(metadata["size"]), int(metadata["offset"])
            if not 0 < size <= 1024 * 1024 or offset < 0 or metadata.get("unpacked"):
                raise GateError("Invalid Electron package metadata")
            handle.seek(8 + header_size + offset)
            version = json.loads(handle.read(size))["version"]
    except (OSError, KeyError, ValueError, struct.error) as error:
        raise GateError("Could not verify built Electron package version") from error
    if version != _app_version(kind, str(app)):
        raise GateError("Embedded Electron app version differs from its built package")
    return version


def _private_environment(run_dir, tool_paths):
    profile = run_dir / "fixture"
    profile.mkdir(mode=0o700)
    for name in ("home", "config", "data", "state", "cache", "runtime", "tmp", "codex", "t3", "electron"):
        (profile / name).mkdir(mode=0o700)
    env = {
        "PATH": os.pathsep.join(sorted({str(Path(p).parent) for p in tool_paths})),
        "LANG": "C.UTF-8", "HOME": str(profile / "home"),
        "XDG_CONFIG_HOME": str(profile / "config"), "XDG_DATA_HOME": str(profile / "data"),
        "XDG_STATE_HOME": str(profile / "state"), "XDG_CACHE_HOME": str(profile / "cache"),
        "XDG_RUNTIME_DIR": str(profile / "runtime"), "TMPDIR": str(profile / "tmp"),
        "CODEX_HOME": str(profile / "codex"), "T3CODE_HOME": str(profile / "t3"),
        "T3CODE_DISABLE_AUTO_UPDATE": "true", "WEASEL_T3_CLIENT": "1",
        "LIBGL_ALWAYS_SOFTWARE": "1", "NO_AT_BRIDGE": "1",
        "ELECTRON_DISABLE_SECURITY_WARNINGS": "true",
    }
    (profile / "codex/config.toml").write_text("[mcp_servers]\n[analytics]\nenabled = false\n", encoding="utf-8")
    (profile / "t3/userdata").mkdir(mode=0o700)
    settings = {"providerInstances": {kind: {"driver": kind, "enabled": False} for kind in (
        "codex", "claudeAgent", "openai", "openrouter", "gemini", "opencode", "pi", "grok", "muse"
    )}}
    (profile / "t3/userdata/settings.json").write_text(json.dumps(settings), encoding="utf-8")
    return env


def _relay(left, right, *, deadline=60, max_bytes=32 * 1024 * 1024):
    limit = time.monotonic() + deadline
    copied = 0
    while time.monotonic() < limit and copied < max_bytes:
        readable, _, _ = select.select([left, right], [], [], min(1, max(0, limit - time.monotonic())))
        for incoming in readable:
            data = incoming.recv(65536)
            if not data:
                return
            copied += len(data)
            (right if incoming is left else left).sendall(data)


class _UnixProxy(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True

    def __init__(self, path, allowed_hosts):
        self.allowed_hosts = allowed_hosts
        self.decisions = []
        self.decision_lock = threading.Lock()
        super().__init__(str(path), _ProxyRequest)

    def record(self, host, allowed):
        with self.decision_lock:
            self.decisions.append({"host": host, "allowed": allowed})


class _ProxyRequest(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(10)
        header = b""
        try:
            while b"\r\n\r\n" not in header and len(header) <= 8192:
                chunk = self.request.recv(4096)
                if not chunk:
                    return
                header += chunk
            first = header.partition(b"\r\n")[0].decode("ascii", errors="replace").split()
            host, port = "invalid", 0
            if len(first) == 3 and first[0] == "CONNECT":
                parsed = urllib.parse.urlsplit("https://" + first[1])
                host, port = parsed.hostname or "invalid", parsed.port or 443
            allowed = host in self.server.allowed_hosts and port == 443 and len(header) <= 8192
            self.server.record(host, allowed)
            if not allowed:
                self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                return
            with socket.create_connection((host, port), timeout=10) as remote:
                self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                _relay(self.request, remote)
        except (OSError, ValueError):
            return


class _ProxyBridge(socketserver.ThreadingTCPServer):
    daemon_threads = True

    def __init__(self, socket_path):
        self.socket_path = str(socket_path)
        super().__init__(("127.0.0.1", 0), _BridgeRequest)


class _BridgeRequest(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as outside:
                outside.connect(self.server.socket_path)
                _relay(self.request, outside, deadline=110)
        except OSError:
            return


def _stop_owned(process):
    if process is None:
        return
    # Nested FHS launchers may place Electron/backend descendants in separate
    # groups. Capture only this owned process's descendants before terminating
    # their parent; record start time to exclude any later PID reuse.
    descendants = {}
    for proc in Path("/proc").iterdir():
        if proc.name.isdecimal() and int(proc.name) != process.pid:
            try:
                if _owned_app_process(int(proc.name), process):
                    descendants[int(proc.name)] = proc.joinpath("stat").read_text().rpartition(")")[2].split()[19]
            except (OSError, IndexError):
                continue
    # Reap the original owned group even if its leader exited, because helpers
    # can outlive Electron. Never signal another process group.
    for sig, timeout in ((signal.SIGTERM, 3), (signal.SIGKILL, 3)):
        for pid, started in descendants.items():
            try:
                if Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[19] == started:
                    os.kill(pid, sig)
            except (OSError, IndexError):
                pass
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        if sig == signal.SIGKILL:
            break


def _listener_owners(port):
    """Read kernel socket inode ownership; never trust an unrelated CDP port."""
    inodes = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        for row in Path(table).read_text().splitlines()[1:]:
            fields = row.split()
            if len(fields) > 9 and fields[3] == "0A" and int(fields[1].rsplit(":", 1)[1], 16) == port:
                inodes.add(fields[9])
    owners = set()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal():
            continue
        try:
            for descriptor in (proc / "fd").iterdir():
                target = os.readlink(descriptor)
                if target.startswith("socket:[") and target[8:-1] in inodes:
                    owners.add(int(proc.name))
        except (OSError, PermissionError):
            continue
    return owners


def _in_process_group(pid, group):
    try:
        return os.getpgid(pid) == group
    except ProcessLookupError:
        return False


def _owned_app_process(pid, process):
    """Accept descendants even when a nested FHS launcher changes their group."""
    if _in_process_group(pid, process.pid):
        return True
    visited = set()
    while pid > 1 and pid not in visited:
        if pid == process.pid:
            return True
        visited.add(pid)
        try:
            # comm can itself contain spaces or parentheses; stat fields after
            # its last ')' start with state, then parent PID.
            fields = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()
            pid = int(fields[1])
        except (OSError, ValueError, IndexError):
            return False
    return False


CDP_PROBE = r"""
const ws = new WebSocket(process.argv[1]);
const diagnostics=[];
const timeout = setTimeout(() => process.exit(2), 6000);
ws.addEventListener('error', () => process.exit(2));
ws.addEventListener('open', () => {
  ws.send(JSON.stringify({id:2,method:'Log.enable'}));
  ws.send(JSON.stringify({id:3,method:'Runtime.enable'}));
  ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{
  expression:`({title:document.title,url:location.href,ready:document.readyState,
    online:navigator.onLine,
    rootChildren:document.getElementById('root')?.childElementCount||0,
    text:document.body?.innerText.slice(0,4000)||'',
    addProject:!!document.querySelector('[aria-label="Add project"]'),
    desktopBootstraps:window.desktopBridge?.getLocalEnvironmentBootstraps?.().map(x=>({id:x.id,httpBaseUrl:x.httpBaseUrl,wsBaseUrl:x.wsBaseUrl}))||[],
    localEnvironmentEnabled:window.desktopBridge?.getLocalEnvironmentEnabled?.(),
    bodySnippet:document.body?.outerHTML.slice(0,8000)||''})`,returnByValue:true
}}));
});
ws.addEventListener('message', ({data}) => {
  const result=JSON.parse(data);
  if(result.method==='Log.entryAdded'&&diagnostics.length<30){
    const entry=result.params.entry;
    if(entry.level==='error'||entry.level==='warning')diagnostics.push(String(entry.text).replace(/([?&](?:wsTicket|token|access_token)=)[^&\s]+/g,'$1<redacted>').slice(0,500));
  }
  if(result.method==='Runtime.consoleAPICalled'&&['error','warning','warn'].includes(result.params.type)&&diagnostics.length<30){
    diagnostics.push(result.params.args.map(x=>x.value??x.description??x.type).join(' ').replace(/([?&](?:wsTicket|token|access_token)=)[^&\s]+/g,'$1<redacted>').slice(0,800));
  }
  if(result.method==='Runtime.exceptionThrown'&&diagnostics.length<30){
    diagnostics.push(String(result.params.exceptionDetails.exception?.description||result.params.exceptionDetails.text).slice(0,800));
  }
  if(result.id!==1)return;
  if(result.error||result.result?.exceptionDetails)process.exit(2);
  setTimeout(()=>{
    console.log(JSON.stringify({...result.result?.result?.value,diagnostics}));
    clearTimeout(timeout); ws.close();
  },100);
});
"""


CHATGPT_NATIVE_PROBE = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=process.argv[1],fixture=process.argv[2];
const watcherRoot=path.join(root,'lib/chatgpt/resources/app.asar.unpacked/node_modules/@parcel/watcher');
const libcRoot=path.join(watcherRoot,'node_modules/detect-libc/lib');
const filesystem=require(path.join(libcRoot,'filesystem.js'));
const read=filesystem.readFileSync,report=process.report.getReport;
filesystem.readFileSync=file=>{if(file===filesystem.SELF_PATH)throw Error('ELF probe unavailable');return read(file)};
process.report.getReport=()=>{throw Error('Unsafe Electron worker report fallback was invoked')};
try{
  assert(filesystem.LDD_PATH.startsWith('/nix/store/'));
  assert.match(fs.readFileSync(filesystem.LDD_PATH,'utf8'),/GNU C Library/);
  assert.equal(require(path.join(libcRoot,'detect-libc.js')).familySync(),'glibc');
}finally{filesystem.readFileSync=read;process.report.getReport=report}
const watcher=require(watcherRoot);fs.mkdirSync(fixture,{recursive:true});
let subscription,timer;
(async()=>{
  try{
    let event;
    const observed=new Promise((resolve,reject)=>{
      timer=setTimeout(()=>reject(Error('No native file event')),8000);
      event=(error,events)=>{if(error)reject(error);if(events.some(e=>e.path===path.join(fixture,'probe')))resolve()};
    });
    subscription=await watcher.subscribe(fixture,event);
    fs.writeFileSync(path.join(fixture,'probe'),'private startup regression fixture\n');
    await observed;
    console.log(JSON.stringify({glibc_fallback:true,native_file_event:true}));
  }finally{clearTimeout(timer);if(subscription)await subscription.unsubscribe()}
})().catch(()=>process.exitCode=1);
"""


def _renderer_usable(kind, result):
    text = result.get("text", "")
    if result.get("ready") != "complete" or len(text.strip()) < 15:
        return False
    if re.search(r"application error|something went wrong|failed to load|clerk.*failed", text, re.I):
        return False
    if kind == "t3":
        return result.get("url", "").startswith("t3code:") and result.get("rootChildren", 0) > 0 and (
            result.get("addProject") is True or any(marker in text for marker in (
                "Add a project", "New thread", "Sign in", "Welcome to T3"
            ))
        )
    return bool(re.search(r"chatgpt|codex", result.get("title", "") + " " + text, re.I)) and bool(
        re.search(r"sign in|log in|continue|welcome|let.s get started", text, re.I)
    )


def _gui_worker(kind, app, run_dir, tools):
    env = dict(os.environ)
    profile = Path(env["HOME"]).parent
    Path("/tmp/.X11-unix").mkdir(mode=0o1777, exist_ok=True)
    proxy = _ProxyBridge(Path("/weasel-outbound/socket"))
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    proxy_thread.start()
    port = proxy.server_address[1]
    endpoint = f"http://127.0.0.1:{port}"
    env.update({"HTTP_PROXY": endpoint, "HTTPS_PROXY": endpoint, "http_proxy": endpoint, "https_proxy": endpoint})
    env.update({"NO_PROXY": "127.0.0.1,localhost,::1", "no_proxy": "127.0.0.1,localhost,::1"})
    xserver, process = None, None
    try:
        with (run_dir / "xvfb.log").open("wb") as xlog, (run_dir / "app.log").open("wb") as log:
            xserver = subprocess.Popen(
                [tools["Xvfb"], "-displayfd", "1", "-screen", "0", "1280x800x24", "-nolisten", "tcp", "-ac"],
                env=env, stdout=subprocess.PIPE, stderr=xlog, start_new_session=True,
            )
            with selectors.DefaultSelector() as selector:
                selector.register(xserver.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=10):
                    raise GateError("Private X server did not become ready")
                display = xserver.stdout.readline().decode().strip()
            if not display.isdecimal():
                raise GateError("Private X server returned an invalid display")
            env["DISPLAY"] = ":" + display
            with socket.socket() as reserved:
                reserved.bind(("127.0.0.1", 0))
                debug_port = reserved.getsockname()[1]
            with socket.socket() as reserved:
                reserved.bind(("127.0.0.1", 0))
                env["T3CODE_PORT"] = str(reserved.getsockname()[1])
            args = [
                str(app / "bin" / KINDS[kind]), "--ozone-platform=x11", "--no-sandbox", "--disable-gpu",
                "--password-store=basic",
                "--disable-quic", "--disable-background-networking", "--disable-component-update",
                f"--user-data-dir={profile / 'electron'}", "--remote-debugging-address=127.0.0.1",
                f"--remote-debugging-port={debug_port}", f"--proxy-server={endpoint}",
                "--proxy-bypass-list=localhost;127.0.0.1;[::1]",
            ]
            process = subprocess.Popen(args, cwd=profile / "home", env=env, stdout=log, stderr=log, start_new_session=True)
            deadline = time.monotonic() + 75
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            last = None
            last_error = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise GateError("Owned GUI process exited before showing usable UI")
                try:
                    owners = _listener_owners(debug_port)
                    if not owners or any(not _owned_app_process(pid, process) for pid in owners):
                        raise GateError("CDP listener does not belong to the owned app descendants")
                    with opener.open(f"http://127.0.0.1:{debug_port}/json/list", timeout=2) as response:
                        data = response.read(MAX_CDP_BYTES + 1)
                    if len(data) > MAX_CDP_BYTES:
                        raise GateError("CDP target list exceeds its bound")
                    pages = json.loads(data)
                    for page in pages:
                        target = page.get("webSocketDebuggerUrl", "")
                        if page.get("type") != "page" or not target:
                            continue
                        parsed = urllib.parse.urlsplit(target)
                        if parsed.scheme != "ws" or parsed.hostname != "127.0.0.1" or parsed.port != debug_port:
                            raise GateError("CDP target points outside the owned listener")
                        last = json.loads(_command([tools["node"], "--eval", CDP_PROBE, target], timeout=8, env=env))
                        if _renderer_usable(kind, last):
                            time.sleep(1)
                            if process.poll() is not None:
                                raise GateError("Owned GUI exited immediately after rendering")
                            last.pop("bodySnippet", None)
                            last.pop("diagnostics", None)
                            return {"renderer": last, "owned_listener": True, "private_profile": True}
                except (OSError, ValueError, GateError, http.client.HTTPException) as error:
                    last_error = str(error)
                time.sleep(0.5)
            if last is not None:
                _write_json(run_dir / "renderer-last.json", last)
            if last_error is not None:
                _write_json(run_dir / "cdp-error.json", {"error": last_error})
            raise GateError("GUI did not show a usable fresh-profile interface within 75 seconds")
    finally:
        _stop_owned(process)
        _stop_owned(xserver)
        proxy.shutdown()
        proxy.server_close()


def _codex_worker(app, run_dir):
    executable = str(app / "bin/codex")
    version = _command([executable, "--version"], timeout=10).decode().strip()
    expected = _store_name(str(app))[len("codex-"):]
    if version != f"codex-cli {expected}":
        raise GateError("Codex runtime version differs from its built package")
    with (run_dir / "app-server.log").open("wb") as log:
        process = subprocess.Popen(
            [executable, "app-server", "-c", "mcp_servers={}", "-c", "analytics.enabled=false"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, start_new_session=True,
        )
        try:
            request = {"id": 1, "method": "initialize", "params": {
                "clientInfo": {"name": "weasel-update-gate", "version": "1"},
                "capabilities": {"experimentalApi": True},
            }}
            process.stdin.write((json.dumps(request) + "\n").encode())
            process.stdin.flush()
            deadline, buffer = time.monotonic() + 15, b""
            received = None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while time.monotonic() < deadline and process.poll() is None:
                    if not selector.select(timeout=0.5):
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    buffer += chunk
                    if len(buffer) > 1024 * 1024:
                        raise GateError("Codex protocol output exceeds its bound")
                    while b"\n" in buffer:
                        raw, buffer = buffer.split(b"\n", 1)
                        response = json.loads(raw)
                        if response.get("id") == 1:
                            received = response
                            break
                    if received is not None:
                        break
            if not received or "error" in received or not isinstance(received.get("result"), dict):
                raise GateError("Codex app-server failed its initialize protocol handshake")
            process.stdin.write(b'{"method":"initialized","params":{}}\n')
            process.stdin.flush()
            return {"version_output": version, "app_server_initialize": received["result"], "model_requests": 0}
        finally:
            if process.stdin is not None:
                process.stdin.close()
            _stop_owned(process)


def find_acp(system, codex_app):
    """Locate the candidate's unchanged ACP adapter rebuilt against its Codex."""
    system, codex_app = _store_root(system), _store_root(codex_app)
    found = []
    for root in _closure(system):
        if re.fullmatch(r"codex-acp-[0-9]+\.[0-9]+\.[0-9]+", _store_name(root)):
            wrapper = Path(root) / "bin/codex-acp"
            if wrapper.is_file():
                data = wrapper.read_bytes()
                if b"CODEX_PATH" in data and (codex_app + "/bin/codex").encode() in data:
                    found.append(root)
    if len(found) != 1:
        raise GateError("Candidate must contain one ACP adapter bound to its exact Codex")
    return found[0]


def _acp_worker(acp_app, codex_app, run_dir):
    executable = acp_app / "bin/codex-acp"
    data = executable.read_bytes()
    if b"CODEX_PATH" not in data or (str(codex_app) + "/bin/codex").encode() not in data:
        raise GateError("ACP wrapper does not use the tested candidate Codex")
    with (run_dir / "acp.log").open("wb") as log:
        process = subprocess.Popen(
            [str(executable)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=log, start_new_session=True,
        )
        try:
            request = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": 1, "clientCapabilities": {},
                "clientInfo": {"name": "weasel-update-gate", "version": "1"},
            }}
            process.stdin.write((json.dumps(request) + "\n").encode())
            process.stdin.flush()
            deadline, buffer, received = time.monotonic() + 15, b"", None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while time.monotonic() < deadline and process.poll() is None:
                    if not selector.select(timeout=0.5):
                        continue
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    buffer += chunk
                    if len(buffer) > 1024 * 1024:
                        raise GateError("ACP protocol output exceeds its bound")
                    while b"\n" in buffer:
                        raw, buffer = buffer.split(b"\n", 1)
                        response = json.loads(raw)
                        if response.get("id") == 1:
                            received = response
                            break
                    if received is not None:
                        break
            result = received.get("result") if received else None
            if not isinstance(result, dict) or result.get("protocolVersion") != 1 or "error" in received:
                raise GateError("Rebuilt ACP adapter failed its initialize protocol handshake")
            return {"app": str(acp_app), "candidate_codex_bound": True, "initialize": result, "model_requests": 0}
        finally:
            if process.stdin is not None:
                process.stdin.close()
            _stop_owned(process)


T3_FIXTURE_ROWS = {
    "projection_projects": ("project_id", "weasel-gate-project", ("project_id", "title", "workspace_root", "scripts_json")),
    "projection_threads": ("thread_id", "weasel-gate-thread", ("thread_id", "project_id", "title", "runtime_mode", "interaction_mode")),
    "projection_thread_messages": ("message_id", "weasel-gate-message", ("message_id", "thread_id", "role", "text", "is_streaming")),
    "scheduled_tasks": ("task_id", "weasel-gate-disabled-task", (
        "task_id", "project_id", "thread_id", "enabled", "run_count", "last_run_status", "next_run_at",
        "title", "prompt", "schedule_json", "workspace_strategy_json", "model_selection_json",
        "runtime_mode", "interaction_mode", "created_by", "creation_source", "created_at", "updated_at",
    )),
}


def _t3_fixture_fingerprint(database, *, include_schedule=True):
    if not database.is_file():
        raise GateError("T3 did not create its isolated SQLite database")
    with sqlite3.connect(database) as db:
        if db.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise GateError("T3 fixture database integrity check failed")
        result = {}
        for table, (key, value, columns) in T3_FIXTURE_ROWS.items():
            if table == "scheduled_tasks" and not include_schedule:
                continue
            # Table/column names are fixed trusted constants, never caller SQL.
            rows = db.execute(f"SELECT {','.join(columns)} FROM {table} WHERE {key}=?", (value,)).fetchall()
            if len(rows) != 1:
                raise GateError(f"T3 migration omitted its synthetic {table} record")
            result[table] = rows[0]
        has_schedules = db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='scheduled_tasks'").fetchone() == (1,)
        if has_schedules and db.execute("SELECT count(*) FROM scheduled_tasks WHERE enabled != 0 OR run_count != 0").fetchone() != (0,):
            raise GateError("Isolated T3 migration enabled or executed a scheduled task")
        result["migrations"] = db.execute("SELECT migration_id,name FROM effect_sql_migrations ORDER BY migration_id").fetchall()
        return result


def _seed_t3_schedule(db):
    moment = "2026-01-01T00:00:00.000Z"
    db.execute("INSERT INTO scheduled_tasks (task_id,title,prompt,enabled,schedule_json,project_id,thread_id,workspace_strategy_json,model_selection_json,runtime_mode,interaction_mode,created_by,creation_source,created_at,updated_at,last_run_status,run_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               ("weasel-gate-disabled-task", "Disabled synthetic schedule", "Never execute this fixture.", 0,
                '{"type":"interval","everyMs":86400000}', "weasel-gate-project", "weasel-gate-thread",
                '{"type":"root"}', '{"provider":"codex","model":"fixture-model"}', "approval-required", "default",
                "user", "server", moment, moment, "never", 0))


def _seed_t3_fixture(database, run_dir, *, include_schedule=True):
    moment = "2026-01-01T00:00:00.000Z"
    workspace = run_dir / "fixture/home/synthetic-project"
    workspace.mkdir(mode=0o700)
    with sqlite3.connect(database) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.execute("INSERT INTO projection_projects (project_id,title,workspace_root,scripts_json,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                   ("weasel-gate-project", "Synthetic migration fixture", str(workspace), "[]", moment, moment))
        db.execute("INSERT INTO projection_threads (thread_id,project_id,title,created_at,updated_at,runtime_mode,interaction_mode) VALUES (?,?,?,?,?,?,?)",
                   ("weasel-gate-thread", "weasel-gate-project", "Preserved synthetic thread", moment, moment, "approval-required", "default"))
        db.execute("INSERT INTO projection_thread_messages (message_id,thread_id,role,text,is_streaming,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                   ("weasel-gate-message", "weasel-gate-thread", "user", "Synthetic text; never submit to any provider.", 0, moment, moment))
        if include_schedule:
            _seed_t3_schedule(db)
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return _t3_fixture_fingerprint(database, include_schedule=include_schedule)


def _t3_migration_worker(old_app, new_app, run_dir, tools):
    # The old binary creates its own actual schema; the new binary then starts
    # with synthetic records in that schema. This never imports user auth,
    # sessions, prompts, schedules or provider state.
    old_dir = run_dir / "old-phase"
    old_dir.mkdir(mode=0o700)
    # GUI logs remain separated; profile location stays identical for both
    # binaries so saved workspace roots do not require normalization.
    _gui_worker("t3", old_app, run_dir, tools)
    for filename in ("app.log", "xvfb.log"):
        (run_dir / filename).rename(old_dir / filename)
    legacy_stable = _app_version("t3", str(old_app)) == "0.0.45"
    directory = run_dir / "fixture/t3/userdata"
    old_database = directory / ("state.sqlite" if legacy_stable else "statev2.sqlite")
    database = directory / "statev2.sqlite"
    try:
        # Stable 0.0.45 predates schedules and the V2 database. Its real native
        # records migrate from state.sqlite; never invent an old schedule table.
        before = _seed_t3_fixture(old_database, run_dir, include_schedule=not legacy_stable)
        renderer = _gui_worker("t3", new_app, run_dir, tools)
        after = _t3_fixture_fingerprint(database, include_schedule=not legacy_stable)
        if legacy_stable and before != _t3_fixture_fingerprint(old_database, include_schedule=False):
            raise GateError("T3 migration altered its native legacy source database")
    except sqlite3.Error as error:
        raise GateError("Unsupported or failed synthetic T3 database migration") from error
    old_migrations, new_migrations = before.pop("migrations"), after.pop("migrations")
    if before != after or not set(old_migrations).issubset(set(new_migrations)):
        raise GateError("T3 migration changed synthetic project/thread/message/schedule data")
    schedule_roundtrip = None
    if legacy_stable:
        # Schedules first exist in the candidate schema. Exercise a disabled
        # schedule there and reopen the candidate, preserving all four records
        # while keeping this proof separate from the native three-record import.
        try:
            with sqlite3.connect(database) as db:
                _seed_t3_schedule(db)
                db.commit()
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            all_before = _t3_fixture_fingerprint(database)
            candidate_dir = run_dir / "candidate-migration-phase"
            candidate_dir.mkdir(mode=0o700)
            for filename in ("app.log", "xvfb.log"):
                (run_dir / filename).rename(candidate_dir / filename)
            renderer = _gui_worker("t3", new_app, run_dir, tools)
            if all_before != _t3_fixture_fingerprint(database):
                raise GateError("T3 candidate reopen changed synthetic data or its disabled schedule")
            schedule_roundtrip = {"ok": True, "introduced_in_candidate_schema": True,
                                  "records_preserved": sorted(T3_FIXTURE_ROWS), "scheduled_tasks_enabled": 0, "scheduled_runs": 0}
        except sqlite3.Error as error:
            raise GateError("Candidate schema lacks the required disabled schedule roundtrip") from error
    renderer["database_migration"] = {
        "old_app": str(old_app), "new_app": str(new_app), "synthetic_records_preserved": sorted(before),
        "old_migration_count": len(old_migrations), "new_migration_count": len(new_migrations),
        "integrity_check": "ok", "scheduled_tasks_enabled": 0, "scheduled_runs": 0,
        "user_profile_copied": False,
    }
    if legacy_stable:
        renderer["database_migration"].update({"old_schema": "state.sqlite", "candidate_schema": "statev2.sqlite",
                                              "legacy_source_unchanged": True,
                                              "candidate_schedule_roundtrip": schedule_roundtrip})
    return renderer


def _namespace_worker(kind, app, run_dir, tools, old_app=None, acp_app=None):
    if os.environ.get("WEASEL_GATE_NAMESPACE") != "1":
        raise GateError("Probe worker must run inside its private namespace")
    capabilities = [row.split()[1] for row in Path("/proc/self/status").read_text().splitlines() if row.startswith("Cap")]
    if not capabilities or any(int(value, 16) != 0 for value in capabilities):
        raise GateError("App probe still possesses namespace setup capabilities")
    if kind == "t3" and os.getuid() != int(os.environ.get("WEASEL_APP_UID", "-1")):
        raise GateError("T3 must run as the original unprivileged probe user")
    if kind == "codex":
        result = _codex_worker(app, run_dir)
        if acp_app is not None:
            result["acp_adapter"] = _acp_worker(acp_app, app, run_dir)
        return result
    if kind == "t3" and old_app is not None:
        return _t3_migration_worker(old_app, app, run_dir, tools)
    native = None
    if kind == "chatgpt":
        native = json.loads(_command(
            [tools["node"], "--eval", CHATGPT_NATIVE_PROBE, app, run_dir / "fixture/native-watcher"],
            timeout=12,
        ))
        if native != {"glibc_fallback": True, "native_file_event": True}:
            raise GateError("ChatGPT native watcher regression probe failed")
    result = _gui_worker(kind, app, run_dir, tools)
    if native is not None:
        result["native_watcher"] = native
    return result


def _network_fixture(tools, app_uid, app_gid, worker_args):
    """Give Chromium a real local link, then remove all setup privileges.

    T3 honors navigator.onLine and never opens its initial local WebSocket when
    Chromium sees a loopback-only namespace. Both ends of this veth exist only
    in our private namespace; there is no default route or host-network link.
    Apps run in a nested user namespace with the original user ID and zero
    capabilities, so they cannot modify that isolation.
    """
    if os.environ.get("WEASEL_GATE_NAMESPACE") != "1" or os.getuid() != 0:
        raise GateError("Private network fixture setup requires its own namespace root")
    for arguments in (
        ["link", "add", "weasel0", "type", "veth", "peer", "name", "weasel1"],
        ["link", "set", "weasel0", "up"], ["link", "set", "weasel1", "up"],
        ["address", "add", "198.18.0.1/32", "dev", "weasel0"],
    ):
        _command([tools["ip"], *arguments], timeout=5)
    routes = json.loads(_command([tools["ip"], "-j", "route"], timeout=5))
    if routes:
        raise GateError("Private online fixture unexpectedly has an outbound route")
    python = str(Path(sys.executable).resolve(strict=True))
    os.environ["WEASEL_APP_UID"] = str(app_uid)
    run_dir = worker_args[worker_args.index("--run-dir") + 1]
    child_args = [
        tools["bwrap"], "--unshare-user", "--uid", str(app_uid), "--gid", str(app_gid),
        "--cap-drop", "ALL", "--die-with-parent", "--new-session",
        "--ro-bind", "/nix/store", "/nix/store", "--dir", "/etc",
        "--dir", "/bin", "--ro-bind", tools["sh"], "/bin/sh",
        "--dir", "/run", "--ro-bind", "/run/current-system", "/run/current-system",
        "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--bind", run_dir, run_dir, "--bind", "/weasel-fixture", "/weasel-fixture",
        "--ro-bind", "/weasel-outbound", "/weasel-outbound",
        "--ro-bind", "/weasel-update-gates.py", "/weasel-update-gates.py",
        "--chdir", "/weasel-fixture/home",
    ]
    # /etc here already belongs to the first isolated namespace. Retain the
    # same explicit non-secret runtime files in the capability-free app layer.
    for name in ("passwd", "group", "hosts", "nsswitch.conf", "localtime", "os-release", "ssl/certs", "fonts"):
        item = Path("/etc") / name
        if item.exists():
            child_args += ["--ro-bind", str(item), str(item)]
    os.execv(tools["bwrap"], [*child_args, python, "/weasel-update-gates.py", *worker_args])


def probe(kind, app, run_dir, *, old_app=None, acp_app=None):
    """Return/save a private receipt for real startup, or raise GateError.

    The app must be its exact store output root. No existing profiles are
    copied. Never invoke this function with a live user's HOME or T3 state.
    """
    if kind not in KINDS:
        raise GateError("Unknown app probe kind")
    app = Path(_store_root(app))
    version = _app_version(kind, str(app))
    if old_app is not None:
        if kind != "t3":
            raise GateError("Old app migration input is supported only for T3")
        old_app = Path(_store_root(old_app))
        _app_version("t3", str(old_app))
        _electron_version("t3", old_app)
    if acp_app is not None:
        if kind != "codex":
            raise GateError("ACP dependency input is supported only for Codex")
        acp_app = Path(_store_root(acp_app))
        if not re.fullmatch(r"codex-acp-[0-9]+\.[0-9]+\.[0-9]+", _store_name(str(acp_app))):
            raise GateError("Unsupported candidate ACP adapter root")
    if not (app / "bin" / KINDS[kind]).is_file():
        raise GateError("Built app executable is missing")
    run_dir = _private_directory(run_dir)
    receipt = {
        "schema": 1, "kind": kind, "app": str(app), "version": version,
        "ok": False, "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "receipt_path": str(run_dir / "receipt.json"),
        "isolation": {"private_home": True, "network_namespace": True, "profile_copy": False,
                      "model_requests": 0, "allowed_external_hosts": sorted(CLERK_HOSTS if kind == "t3" else [])},
    }
    if kind == "t3":
        receipt["isolation"].update({"namespace_only_online_link": True, "app_capabilities": 0, "default_route": False})
    proxy = None
    proxy_directory = None
    try:
        if kind != "codex":
            receipt["embedded_version"] = _electron_version(kind, app)
        if kind == "chatgpt":
            wrapper = (app / "bin/chatgpt").read_bytes()
            if b"LD_LIBRARY_PATH" not in wrapper or b"libpulseaudio" not in wrapper or not any(
                _store_name(p).startswith("libpulseaudio-") for p in _closure(str(app))
            ):
                raise GateError("ChatGPT package no longer exposes its required PulseAudio runtime")
            receipt["packaged_pulseaudio_runtime"] = True
        names = ["bwrap", "sh"] if kind == "codex" else ["bwrap", "sh", "node", "Xvfb"]
        if kind == "t3":
            names.append("ip")
        tools = {name: _tool(name) for name in names}
        python = str(Path(sys.executable).resolve(strict=True))
        env = _private_environment(run_dir, [python, *tools.values()])
        fixture_path = str(run_dir / "fixture")
        env = {key: value.replace(fixture_path, "/weasel-fixture") for key, value in env.items()}
        # Namespace-local /tmp is private and short enough for Chromium's
        # SingletonSocket, independently of the candidate receipt path length.
        env["TMPDIR"] = "/tmp"
        env["WEASEL_GATE_NAMESPACE"] = "1"
        if kind != "codex":
            # AF_UNIX paths are bounded to 108 bytes on Linux. Candidate state
            # paths can be much longer; keep this owned bridge under short /tmp
            # and expose only its socket directory in the private namespace.
            proxy_directory = tempfile.TemporaryDirectory(prefix="weasel-gate-proxy-")
            proxy_path = Path(proxy_directory.name) / "socket"
            proxy = _UnixProxy(proxy_path, CLERK_HOSTS if kind == "t3" else frozenset())
            os.chmod(proxy_path, 0o600)
            threading.Thread(target=proxy.serve_forever, daemon=True).start()
        args = [
            tools["bwrap"], "--die-with-parent", "--unshare-all", "--new-session",
            "--ro-bind", "/nix/store", "/nix/store", "--dir", "/etc",
            "--dir", "/bin", "--ro-bind", tools["sh"], "/bin/sh",
            "--dir", "/run", "--ro-bind", str(Path("/run/current-system").resolve()), "/run/current-system",
            "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
            "--bind", str(run_dir), str(run_dir), "--chdir", str(run_dir / "fixture/home"),
            "--bind", str(run_dir / "fixture"), "/weasel-fixture",
            "--ro-bind", str(Path(__file__).resolve()), "/weasel-update-gates.py",
        ]
        if kind == "t3":
            # Only the trusted link-setup worker runs as namespace root.
            # Nested Bubblewrap needs that namespace's complete capability set
            # to create its UID mapping, then drops every app capability.
            args += ["--uid", "0", "--gid", "0", "--cap-add", "ALL"]
        if proxy_directory is not None:
            args += ["--ro-bind", proxy_directory.name, "/weasel-outbound"]
        # Resolve NixOS /etc symlinks before binding. Binding the whole /etc
        # would include credential-bearing configuration and broken profile
        # symlinks; this list contains only runtime identity, TLS and font data.
        for name in ("passwd", "group", "hosts", "nsswitch.conf", "localtime", "os-release", "ssl/certs", "fonts"):
            item = Path("/etc") / name
            if item.exists():
                args += ["--ro-bind", str(item.resolve(strict=True)), "/etc/" + name]
        if Path("/etc/fonts/fonts.conf").exists():
            env["FONTCONFIG_FILE"] = str(Path("/etc/fonts/fonts.conf").resolve(strict=True))
        args += [
            python, "/weasel-update-gates.py", "--namespace-worker",
            "--kind", kind, "--app", str(app), "--run-dir", str(run_dir),
            "--tools", json.dumps(tools),
        ]
        if old_app is not None:
            args += ["--old-app", str(old_app)]
        if acp_app is not None:
            args += ["--acp-app", str(acp_app)]
        if kind == "t3":
            args += ["--setup-network", "--app-uid", str(os.getuid()), "--app-gid", str(os.getgid())]
        with (run_dir / "namespace.log").open("wb") as log:
            process = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=log, start_new_session=True)
            try:
                output, _ = process.communicate(timeout=270 if old_app is not None else PROBE_TIMEOUT)
            except subprocess.TimeoutExpired as error:
                _stop_owned(process)
                raise GateError("Owned probe namespace timed out and was terminated") from error
            finally:
                _stop_owned(process)
        try:
            evidence = json.loads(output)
        except ValueError as error:
            raise GateError("Private probe returned an invalid receipt") from error
        if process.returncode != 0:
            _write_json(run_dir / "worker-error.json", evidence)
            raise GateError(f"Private app probe failed (exit {process.returncode}); see its private worker error and logs")
        receipt["evidence"] = evidence
        receipt["ok"] = True
        return receipt
    except (OSError, ValueError, GateError) as error:
        receipt["error"] = str(error)
        raise GateError(str(error)) from error
    finally:
        if proxy is not None:
            proxy.shutdown()
            proxy.server_close()
            receipt["network_decisions"] = proxy.decisions
        if proxy_directory is not None:
            proxy_directory.cleanup()
        receipt["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        _write_json(run_dir / "receipt.json", receipt)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=sorted(KINDS), required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--old-app", type=Path, help="T3 baseline root for a real synthetic old-to-new schema migration")
    parser.add_argument("--acp-app", type=Path, help="Rebuilt ACP adapter whose wrapper binds the tested candidate Codex")
    parser.add_argument("--namespace-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--tools", default="{}", help=argparse.SUPPRESS)
    parser.add_argument("--setup-network", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--app-uid", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--app-gid", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.setup_network:
            worker_args = ["--namespace-worker", "--kind", args.kind, "--app", str(args.app),
                           "--run-dir", str(args.run_dir), "--tools", args.tools]
            if args.old_app is not None:
                worker_args += ["--old-app", str(args.old_app)]
            _network_fixture(json.loads(args.tools), args.app_uid, args.app_gid, worker_args)
        if args.namespace_worker:
            result = _namespace_worker(args.kind, args.app, args.run_dir, json.loads(args.tools), args.old_app, args.acp_app)
        else:
            result = probe(args.kind, args.app, args.run_dir, old_app=args.old_app, acp_app=args.acp_app)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (GateError, OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error), "receipt_path": str(args.run_dir / "receipt.json")}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
