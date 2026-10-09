"""Lifecycle contract tests with fake presentation and read-only actor fixtures.

These establish helper lifetime/cancellation behavior, never live Niri rendering.
"""

import copy
import importlib.util
import json
import os
import signal
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SOURCE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("indicator", SOURCE / "indicator.py")
indicator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(indicator)


class StatusDeadline(unittest.TestCase):
    def test_fragmented_response_has_total_deadline(self):
        reader, writer = socket.socketpair()
        reader.settimeout(0.12)

        def fragment():
            try:
                for byte in b'{"ok":true}\n':
                    writer.send(bytes([byte]))
                    time.sleep(0.035)
            except OSError:
                pass
            finally:
                writer.close()

        sender = threading.Thread(target=fragment)
        sender.start()
        started = time.monotonic()
        try:
            with self.assertRaises((TimeoutError, indicator.CapabilityError)):
                indicator.read_line(reader, 4096)
            self.assertLess(time.monotonic() - started, 0.25)
        finally:
            reader.close()
            sender.join(timeout=1)


class IndicatorLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime = Path(self.temp.name)
        self.actor_dir = self.runtime / "weasel-computer-use"
        self.actor_dir.mkdir(mode=0o700)
        self.actor_path = self.actor_dir / "desktop.sock"
        self.actor_state = {
            "schema": 1, "session_id": "fixture-session", "epoch": 2,
            "takeover_latched": False, "active": None,
            "queued_batches": 0, "actor_release_confirmed": True,
        }
        self.actor_lock = threading.Lock()
        self.niri_state_path = self.runtime / "outputs.json"
        self.niri_state = {"DP-6": {"logical": {"x": 1920, "y": 0, "width": 3440, "height": 1440, "scale": 1}}}
        self.niri_state_path.write_text(json.dumps(self.niri_state))
        self.render_started = self.runtime / "renderer-started"
        self.renderer = self.runtime / "renderer.py"
        self.renderer.write_text(
            f"#!{sys.executable}\n"
            "import json, os, pathlib, sys\n"
            f"pathlib.Path({str(self.render_started)!r}).write_text(str(os.getpid()))\n"
            "for line in sys.stdin:\n"
            " if line == 'v1 begin\\n':\n"
            "  print(json.dumps({'revision':1,'event':'ready','task_id':sys.argv[2],'output':sys.argv[1],'surfaces':5}),flush=True)\n"
            " elif line == 'v1 end\\n': break\n"
        )
        self.renderer.chmod(0o700)
        self.niri = self.runtime / "niri.py"
        self.niri.write_text(f"#!{sys.executable}\nfrom pathlib import Path\nprint(Path({str(self.niri_state_path)!r}).read_text())\n")
        self.niri.chmod(0o700)
        self.env = {
            **os.environ, "XDG_RUNTIME_DIR": str(self.runtime),
            "WEASEL_COMPUTER_USE_SOCKET": str(self.actor_path),
            "WEASEL_INDICATOR_NIRI": str(self.niri),
            "WEASEL_INDICATOR_RENDERER": str(self.renderer),
        }
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(self.actor_path))
        self.server.listen(4)
        self.server.settimeout(0.05)
        self.server_stop = threading.Event()
        self.actor_thread = threading.Thread(target=self.serve_actor, daemon=True)
        self.actor_thread.start()
        self.processes = []

    def serve_actor(self):
        while not self.server_stop.is_set():
            try:
                client, _ = self.server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with client:
                client.settimeout(0.1)
                try:
                    request = client.recv(4096)
                    self.assertIn(b'"desktop_status"', request)
                    with self.actor_lock:
                        state = copy.deepcopy(self.actor_state)
                    response = {"content": [{"type": "text", "text": json.dumps(state)}], "isError": False}
                    client.sendall(json.dumps(response).encode() + b"\n")
                except OSError:
                    pass

    def tearDown(self):
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=2)
            process.stdout.close()
            process.stderr.close()
        self.server_stop.set()
        self.server.close()
        self.actor_thread.join(timeout=1)
        self.temp.cleanup()

    def launch(self, task="fixture-task", extra=()):
        process = subprocess.Popen(
            [sys.executable, str(SOURCE / "indicator.py"), "run", "--task-id", task,
             "--output", "DP-6", *extra],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        self.processes.append(process)
        return process

    def ready(self, process):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if select.select([process.stdout], [], [], 0.1)[0]:
                line = process.stdout.readline()
                if line and json.loads(line).get("event") == "ready":
                    return
            if process.poll() is not None:
                break
        self.fail("fixture indicator was not ready")

    def ended(self, process):
        stdout, stderr = process.communicate(timeout=2)
        events = [json.loads(line) for line in stdout.splitlines()]
        ended = next(item for item in reversed(events) if item.get("event") == "ended")
        self.assertEqual(stderr, "")
        self.assertFalse(list((self.actor_dir / "indicators").glob("task-*")))
        return ended

    def test_thinking_gap_stays_owned_and_explicit_end_cleans(self):
        process = self.launch()
        self.ready(process)
        time.sleep(0.35)  # actor remains idle: lifetime is workflow, not action.
        self.assertIsNone(process.poll())
        result = subprocess.run([sys.executable, str(SOURCE / "indicator.py"), "end", "--task-id", "fixture-task"], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.ended(process)["reason"], "explicit_end")

    def test_cancel_epoch_ends_without_replay(self):
        process = self.launch()
        self.ready(process)
        started = time.monotonic()
        with self.actor_lock:
            self.actor_state["epoch"] += 1
        self.assertEqual(self.ended(process)["reason"], "actor_cancel_epoch_changed")
        self.assertLess(time.monotonic() - started, 0.7)

    def test_takeover_ends(self):
        process = self.launch()
        self.ready(process)
        with self.actor_lock:
            self.actor_state["takeover_latched"] = True
        self.assertEqual(self.ended(process)["reason"], "actor_takeover_latched")

    def test_backend_restart_does_not_silently_reconnect(self):
        process = self.launch()
        self.ready(process)
        with self.actor_lock:
            self.actor_state["session_id"] = "replacement-session"
        self.assertEqual(self.ended(process)["reason"], "actor_session_changed")

    def test_unconfirmed_release_during_active_action_keeps_indicator(self):
        process = self.launch()
        self.ready(process)
        with self.actor_lock:
            self.actor_state["active"] = {"task_id": "action"}
            self.actor_state["actor_release_confirmed"] = False
        time.sleep(0.3)
        self.assertIsNone(process.poll())
        with self.actor_lock:
            self.actor_state["active"] = None
        self.assertEqual(self.ended(process)["reason"], "idle_release_unconfirmed")

    def test_initial_latch_refuses_without_renderer(self):
        with self.actor_lock:
            self.actor_state["takeover_latched"] = True
        process = self.launch()
        stdout, _ = process.communicate(timeout=2)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("actor must be resumed", stdout)
        self.assertFalse(self.render_started.exists())

    def test_owner_identity_mismatch_refuses_without_renderer(self):
        process = self.launch(extra=("--owner-pid", str(os.getpid()), "--owner-start-ticks", "0"))
        stdout, _ = process.communicate(timeout=2)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("owner process identity changed", stdout)
        self.assertFalse(self.render_started.exists())

    def test_signal_cleanup(self):
        process = self.launch()
        self.ready(process)
        process.terminate()
        self.assertEqual(self.ended(process)["reason"], "owner_signal")

    def test_hard_maximum_runtime(self):
        process = self.launch(extra=("--max-runtime-seconds", "1"))
        self.ready(process)
        self.assertEqual(self.ended(process)["reason"], "maximum_runtime_expired")

    def test_same_output_cannot_have_two_owners(self):
        first = self.launch()
        self.ready(first)
        second = self.launch(task="second-task")
        stdout, _ = second.communicate(timeout=2)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("capability_unavailable", stdout)
        self.assertIsNone(first.poll())
        first.terminate()
        self.ended(first)

    def test_renderer_crash_cleans_lease_even_with_broken_pipe(self):
        process = self.launch()
        self.ready(process)
        os.kill(int(self.render_started.read_text()), signal.SIGKILL)
        ended = self.ended(process)
        self.assertTrue(ended["renderer_exit_confirmed"])

    def test_actor_connection_loss_hides_without_reconnecting(self):
        process = self.launch()
        self.ready(process)
        self.actor_path.unlink()
        started = time.monotonic()
        self.assertEqual(self.ended(process)["reason"], "capability_unavailable")
        self.assertLess(time.monotonic() - started, 0.7)

    def test_wrong_task_control_cannot_end_owned_indicator(self):
        process = self.launch()
        self.ready(process)
        path = next((self.actor_dir / "indicators").glob("task-*.sock"))
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.connect(str(path))
            stream.sendall(b'{"revision":1,"event":"end","task_id":"wrong-task"}\n')
            response = json.loads(stream.recv(4096))
        self.assertFalse(response["ok"])
        self.assertIsNone(process.poll())
        process.terminate()
        self.ended(process)


if __name__ == "__main__":
    unittest.main()
