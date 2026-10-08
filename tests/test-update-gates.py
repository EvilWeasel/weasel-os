#!/usr/bin/env python3
"""Exercise closure isolation, verified source transitions and probe boundaries."""

import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "weasel_update_gates", Path(__file__).resolve().parents[1] / "scripts/weasel-update-gates.py"
)
gates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gates)


def pin(version):
    return (json.dumps({
        "version": version,
        "url": f"https://github.com/pingdotgg/t3code/releases/download/v{version}/T3-Code-{version}-x86_64.AppImage",
        "hash": "sha256-" + "A" * 43 + "=",
    }, indent=2) + "\n").encode()


class ClosureGates(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.paths = {}
        self.counter = 0
        self.old_system = self.output("nixos-system-nixy-laptop-25.11")
        self.new_system = self.output("nixos-system-nixy-laptop-25.11")
        self.old_app = self.output("t3code-1.0.0")
        self.new_app = self.output("t3code-1.0.1")
        self.old_source = self.output("source")
        self.new_source = self.output("source")
        self.old_path = self.output("system-path")
        self.new_path = self.output("system-path")
        self.unchanged = self.output("glibc-2.42")
        self.old_pin, self.new_pin = pin("1.0.0"), pin("1.0.1")
        self.write(self.old_source, "packages/t3code/source.json", self.old_pin)
        self.write(self.new_source, "packages/t3code/source.json", self.new_pin)
        self.write(self.old_source, "programs/unchanged.nix", b"{ safe = true; }\n")
        self.write(self.new_source, "programs/unchanged.nix", b"{ safe = true; }\n")
        self.write(self.old_system, "activate", f"exec {self.old_path}/bin/true\nsource={self.old_source}\n".encode())
        self.write(self.new_system, "activate", f"exec {self.new_path}/bin/true\nsource={self.new_source}\n".encode())
        self.link(self.old_path, "bin/t3code", self.old_app + "/bin/t3code")
        self.link(self.new_path, "bin/t3code", self.new_app + "/bin/t3code")
        self.write(self.old_path, "manifest.json", json.dumps({"name": "t3code-1.0.0", "path": self.old_app}).encode())
        self.write(self.new_path, "manifest.json", json.dumps({"name": "t3code-1.0.1", "path": self.new_app}).encode())
        self.closures = {
            self.old_system: {self.old_system, self.old_app, self.old_source, self.old_path, self.unchanged},
            self.new_system: {self.new_system, self.new_app, self.new_source, self.new_path, self.unchanged},
            self.old_app: {self.old_app, self.unchanged},
            self.new_app: {self.new_app, self.unchanged},
        }
        real_tree = gates._tree
        real_trigger = gates._verify_restart_trigger
        patchers = [
            mock.patch.object(gates, "_store_root", lambda path: str(path)),
            mock.patch.object(gates, "_closure", lambda path: self.closures[path]),
            mock.patch.object(gates, "_tree", lambda path, *args: real_tree(self.paths[path], *args)),
            mock.patch.object(gates, "_verify_restart_trigger", lambda path, system, name: real_trigger(self.paths[path], system, name)),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def output(self, name):
        self.counter += 1
        path = f"/nix/store/{self.counter:032d}-{name}"
        directory = self.directory / str(self.counter)
        directory.mkdir()
        self.paths[path] = directory
        return path

    def write(self, root, name, data):
        path = self.paths[root] / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def link(self, root, name, target):
        path = self.paths[root] / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(target)

    def verify(self, additional_changes=None):
        changes = {"packages/t3code/source.json": (self.old_pin, self.new_pin)}
        changes.update(additional_changes or {})
        return gates.verify_closure(
            self.old_system, self.new_system,
            {"t3": {"old": self.old_app, "new": self.new_app}},
            changes,
        )

    def test_learning_log_normalizes_only_exact_candidate_append(self):
        discover_spec = importlib.util.spec_from_file_location("test_discover", Path(gates.__file__).with_name("weasel-update-discover.py"))
        discover = importlib.util.module_from_spec(discover_spec)
        discover_spec.loader.exec_module(discover)
        before = b"# Preserved historical learnings\n"
        after = before + discover.learning_suffix("20261008-probe", "t3", "1.0.0", "1.0.1")
        self.write(self.old_source, "agent-learnings.md", before)
        self.write(self.new_source, "agent-learnings.md", after)
        changes = {"agent-learnings.md": (before, after)}
        self.assertTrue(self.verify(changes)["ok"])
        for modified in (after + b"arbitrary text\n", after.replace(b"1.0.1", b"9.9.9"), after.replace(b"Pending", b"Complete"), b"changed baseline" + after):
            with self.assertRaises(gates.GateError):
                self.verify({"agent-learnings.md": (before, modified)})

    def test_app_update_accepts_exact_generated_content_and_version_references(self):
        result = self.verify()
        self.assertTrue(result["ok"])
        self.assertEqual(result["compared_generated_outputs"], ["nixos-system-nixy-laptop-25.11", "source", "system-path"])

    def test_app_dependency_change_is_allowed_only_inside_selected_closures(self):
        old_dep, new_dep = self.output("app-library-1"), self.output("app-library-2")
        self.closures[self.old_system].add(old_dep)
        self.closures[self.old_app].add(old_dep)
        self.closures[self.new_system].add(new_dep)
        self.closures[self.new_app].add(new_dep)
        self.assertTrue(self.verify()["ok"])
        self.closures[self.new_app].remove(new_dep)
        with self.assertRaisesRegex(gates.GateError, "Unrelated"):
            self.verify()

    def test_unrelated_changed_package_is_rejected_even_with_same_name(self):
        old_dep, new_dep = self.output("networkmanager-1"), self.output("networkmanager-1")
        self.closures[self.old_system].add(old_dep)
        self.closures[self.new_system].add(new_dep)
        with self.assertRaisesRegex(gates.GateError, "Unrelated"):
            self.verify()

    def test_modified_generated_activation_script_is_rejected(self):
        self.write(self.new_system, "activate", b"launch-unrelated-new-service\n")
        with self.assertRaisesRegex(gates.GateError, "Non-app content"):
            self.verify()

    def test_added_generated_file_is_rejected(self):
        self.write(self.new_path, "bin/other", b"unrelated script\n")
        with self.assertRaisesRegex(gates.GateError, "Non-app content"):
            self.verify()

    def test_generated_file_mode_changes_are_rejected(self):
        (self.paths[self.new_system] / "activate").chmod(0o755)
        with self.assertRaisesRegex(gates.GateError, "Non-app content"):
            self.verify()

    def test_other_source_changes_are_rejected(self):
        self.write(self.new_source, "programs/unchanged.nix", b"{ safe = false; }\n")
        with self.assertRaisesRegex(gates.GateError, "Non-app content"):
            self.verify()

    def test_source_must_match_exact_verified_bytes(self):
        self.write(self.new_source, "packages/t3code/source.json", self.new_pin + b"\n")
        with self.assertRaisesRegex(gates.GateError, "verified pin"):
            self.verify()

    def test_missing_declared_source_pin_is_rejected(self):
        (self.paths[self.new_source] / "packages/t3code/source.json").unlink()
        with self.assertRaisesRegex(gates.GateError, "omits"):
            self.verify()

    def test_unpaired_generated_output_is_rejected(self):
        self.closures[self.new_system].add(self.output("dbus-configuration"))
        with self.assertRaisesRegex(gates.GateError, "Unpaired"):
            self.verify()

    def test_duplicate_generated_names_are_rejected(self):
        self.closures[self.new_system].add(self.output("source"))
        with self.assertRaisesRegex(gates.GateError, "Unpaired|ambiguous"):
            self.verify()

    def test_root_absent_from_system_is_rejected(self):
        self.closures[self.new_system].remove(self.new_app)
        with self.assertRaisesRegex(gates.GateError, "absent"):
            self.verify()

    def test_source_version_must_match_selected_app(self):
        bad_pin = pin("1.0.2")
        with self.assertRaisesRegex(gates.GateError, "differs from its source"):
            gates.verify_closure(self.old_system, self.new_system,
                {"t3": (self.old_app, self.new_app)},
                {"packages/t3code/source.json": (self.old_pin, bad_pin)})

    def test_wrapper_rebuild_must_preserve_its_code_exactly(self):
        before, after = self.output("weasel-laptop-executor"), self.output("weasel-laptop-executor")
        self.write(before, "bin/executor", f"exec {self.old_app}/bin/t3code\n".encode())
        self.write(after, "bin/executor", f"exec {self.new_app}/bin/t3code\n".encode())
        self.closures[self.old_system].add(before)
        self.closures[self.new_system].add(after)
        self.assertTrue(self.verify()["ok"])
        self.write(after, "bin/executor", f"exec {self.new_app}/bin/t3code --unsafe\n".encode())
        with self.assertRaisesRegex(gates.GateError, "Non-app content"):
            self.verify()

    def test_polkit_trigger_allows_only_the_exact_paired_system_path(self):
        before, after = self.output("X-Restart-Triggers-polkit"), self.output("X-Restart-Triggers-polkit")
        for root, system_path in ((before, self.old_path), (after, self.new_path)):
            self.paths[root].rmdir()
            self.paths[root].write_bytes(system_path.encode())
        self.closures[self.old_system].add(before)
        self.closures[self.new_system].add(after)
        self.assertTrue(self.verify()["ok"])
        self.paths[after].write_bytes((self.new_path + "\nextra-policy-reference").encode())
        with self.assertRaisesRegex(gates.GateError, "exact paired generated"):
            self.verify()

    def test_duplicate_dbus_roles_pair_by_content_and_reject_swapped_parent_links(self):
        roles = []
        for role in ("user", "system"):
            before, after = self.output("unit-dbus.service"), self.output("unit-dbus.service")
            self.write(before, "dbus.service", f"role={role}\nExecStart={self.old_path}/bin/dbus\n".encode())
            self.write(after, "dbus.service", f"role={role}\nExecStart={self.new_path}/bin/dbus\n".encode())
            self.closures[self.old_system].add(before)
            self.closures[self.new_system].add(after)
            roles.append((before, after))
        for index, (before, after) in enumerate(roles):
            self.link(self.old_system, f"roles/{index}", before + "/dbus.service")
            self.link(self.new_system, f"roles/{index}", after + "/dbus.service")
        self.assertTrue(self.verify()["ok"])
        for index in (0, 1):
            (self.paths[self.new_system] / f"roles/{index}").unlink()
            self.link(self.new_system, f"roles/{index}", roles[1-index][1] + "/dbus.service")
        with self.assertRaisesRegex(gates.GateError, "Non-app content"):
            self.verify()


class SourceTransitions(unittest.TestCase):
    def test_nix_pins_allow_only_version_and_hash_value_changes(self):
        old = b'{\n  version = "0.1.0";\n    hash = "sha256-' + b'A' * 43 + b'=";\n  safe = true;\n}\n'
        new = old.replace(b'0.1.0', b'0.2.0').replace(b'A' * 43, b'B' * 43)
        self.assertEqual(gates._validate_source_changes({"packages/codex-bin.nix": (old, new)}, {"codex"})["packages/codex-bin.nix"], (old, new))
        with self.assertRaisesRegex(gates.GateError, "packaging code"):
            gates._validate_source_changes({"packages/codex-bin.nix": (old, new.replace(b'true', b'false'))}, {"codex"})

    def test_unknown_source_paths_and_incomplete_transitions_refused(self):
        for changes in ({"flake.lock": (b"old", b"new")}, ["packages/t3code/source.json"], {}):
            with self.assertRaises(gates.GateError):
                gates._validate_source_changes(changes, {"t3"})

    def test_t3_only_official_immutable_release_url_is_accepted(self):
        old, new = pin("1.0.0"), json.loads(pin("1.0.1"))
        new["url"] = "https://example.com/app"
        with self.assertRaisesRegex(gates.GateError, "immutable"):
            gates._validate_source_changes({"packages/t3code/source.json": (old, json.dumps(new))}, {"t3"})

    def test_codex_acp_is_not_a_codex_app_root(self):
        with self.assertRaises(gates.GateError):
            gates._app_version("codex", "/nix/store/" + "a" * 32 + "-codex-acp-2.1.1")


class ProbeBoundaries(unittest.TestCase):
    def test_environment_drops_live_credentials_and_client_context(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(os.environ, {
            "OPENAI_API_KEY": "fixture-private-key", "CODEX_HOME": "/live/codex",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/live/bus", "T3_ACP_MCP_NODE": "/live/transport",
        }):
            result = gates._private_environment(Path(directory), ["/nix/store/python/bin/python"])
            for key in ("OPENAI_API_KEY", "DBUS_SESSION_BUS_ADDRESS", "T3_ACP_MCP_NODE"):
                self.assertNotIn(key, result)
            self.assertNotEqual(result["CODEX_HOME"], "/live/codex")
            settings = json.loads((Path(result["T3CODE_HOME"]) / "userdata/settings.json").read_text())
            self.assertTrue(all(value["enabled"] is False for value in settings["providerInstances"].values()))
            self.assertFalse((Path(result["CODEX_HOME"]) / "auth.json").exists())

    def test_existing_or_world_readable_profiles_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "probe"
            root.mkdir(mode=0o700)
            (root / "user-profile").write_text("existing data")
            with self.assertRaisesRegex(gates.GateError, "empty"):
                gates._private_directory(root)
            (root / "user-profile").unlink()
            root.chmod(0o755)
            with self.assertRaisesRegex(gates.GateError, "private"):
                gates._private_directory(root)

    def test_symlink_probe_directory_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target"
            target.mkdir()
            link = Path(directory) / "link"
            link.symlink_to(target)
            with self.assertRaisesRegex(gates.GateError, "symlink"):
                gates._private_directory(link)

    def test_proxy_denies_model_hosts_without_connecting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "proxy.sock"
            server = gates._UnixProxy(path, gates.CLERK_HOSTS)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with mock.patch.object(gates.socket, "create_connection") as connect:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                        client.connect(str(path))
                        client.sendall(b"CONNECT api.openai.com:443 HTTP/1.1\r\nHost: api.openai.com\r\n\r\n")
                        self.assertIn(b"403 Forbidden", client.recv(1024))
                    connect.assert_not_called()
                self.assertEqual(server.decisions, [{"host": "api.openai.com", "allowed": False}])
            finally:
                server.shutdown()
                server.server_close()

    def test_error_and_empty_renderer_pages_are_not_startup_success(self):
        self.assertFalse(gates._renderer_usable("t3", {"ready": "complete", "text": "Application error: failed to load", "rootChildren": 1, "url": "t3code://app", "addProject": True}))
        self.assertFalse(gates._renderer_usable("chatgpt", {"ready": "complete", "title": "ChatGPT", "text": ""}))
        self.assertTrue(gates._renderer_usable("t3", {"ready": "complete", "text": "Add a project to start working", "rootChildren": 1, "url": "t3code://app", "addProject": True}))
        self.assertTrue(gates._renderer_usable("chatgpt", {"ready": "complete", "title": "Codex", "text": "Welcome to Codex. Sign in to continue."}))

    def test_owned_descendant_can_change_process_group_without_losing_ownership(self):
        records = {"/proc/42/stat": "42 (fixture electron) S 41 42", "/proc/41/stat": "41 (fixture launcher) S 40 41"}
        with mock.patch.object(gates, "_in_process_group", return_value=False), mock.patch.object(Path, "read_text", lambda path: records[str(path)]):
            self.assertTrue(gates._owned_app_process(42, mock.Mock(pid=40)))

    def test_unrelated_cdp_process_is_not_accepted(self):
        with mock.patch.object(gates, "_in_process_group", return_value=False), mock.patch.object(Path, "read_text", return_value="42 (unrelated) S 1 42"):
            self.assertFalse(gates._owned_app_process(42, mock.Mock(pid=40)))

    def test_cleanup_reaps_owned_child_in_a_different_process_group(self):
        code = """import subprocess,sys,time,signal
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)
def stop(*unused):
    child.wait(timeout=5)
    sys.exit(0)
signal.signal(signal.SIGTERM,stop)
print(child.pid,flush=True)
time.sleep(60)
"""
        parent = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, start_new_session=True)
        try:
            child = int(parent.stdout.readline())
            self.assertNotEqual(os.getpgid(child), parent.pid)
            gates._stop_owned(parent)
            with self.assertRaises(ProcessLookupError):
                os.kill(child, 0)
        finally:
            gates._stop_owned(parent)
            parent.stdout.close()

    def test_namespace_worker_refuses_unisolated_invocation(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(gates.GateError, "private namespace"):
                gates._namespace_worker("codex", Path("/app"), Path("/fixture"), {})

    def test_app_worker_refuses_remaining_namespace_capabilities(self):
        with mock.patch.dict(os.environ, {"WEASEL_GATE_NAMESPACE": "1"}, clear=True), mock.patch.object(Path, "read_text", return_value="CapEff:\t00001000\n"):
            with self.assertRaisesRegex(gates.GateError, "setup capabilities"):
                gates._namespace_worker("codex", Path("/app"), Path("/fixture"), {})

    def test_private_online_fixture_refuses_any_outbound_route(self):
        with mock.patch.dict(os.environ, {"WEASEL_GATE_NAMESPACE": "1"}, clear=True), mock.patch.object(os, "getuid", return_value=0), mock.patch.object(gates, "_command", return_value=b'[{"dst":"default","gateway":"198.18.0.2"}]'), mock.patch.object(os, "execv") as execute:
            with self.assertRaisesRegex(gates.GateError, "outbound route"):
                gates._network_fixture({"ip": "/trusted/ip"}, 1000, 100, [])
            execute.assert_not_called()


class MigrationFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "fixture/home").mkdir(parents=True)
        self.database = self.root / "state.sqlite"
        with sqlite3.connect(self.database) as db:
            db.executescript("""
            CREATE TABLE projection_projects (project_id TEXT PRIMARY KEY,title TEXT,workspace_root TEXT,scripts_json TEXT,created_at TEXT,updated_at TEXT);
            CREATE TABLE projection_threads (thread_id TEXT PRIMARY KEY,project_id TEXT,title TEXT,created_at TEXT,updated_at TEXT,runtime_mode TEXT,interaction_mode TEXT);
            CREATE TABLE projection_thread_messages (message_id TEXT PRIMARY KEY,thread_id TEXT,role TEXT,text TEXT,is_streaming INTEGER,created_at TEXT,updated_at TEXT);
            CREATE TABLE scheduled_tasks (task_id TEXT PRIMARY KEY,title TEXT,prompt TEXT,enabled INTEGER,schedule_json TEXT,project_id TEXT,thread_id TEXT,workspace_strategy_json TEXT,model_selection_json TEXT,runtime_mode TEXT,interaction_mode TEXT,created_by TEXT,creation_source TEXT,created_at TEXT,updated_at TEXT,last_run_status TEXT,run_count INTEGER,next_run_at TEXT);
            CREATE TABLE effect_sql_migrations (migration_id INTEGER,name TEXT);
            INSERT INTO effect_sql_migrations VALUES (1,'fixture-schema');
            """)

    def test_synthetic_fixture_contains_records_and_no_runnable_schedule(self):
        before = gates._seed_t3_fixture(self.database, self.root)
        self.assertEqual(before, gates._t3_fixture_fingerprint(self.database))
        self.assertEqual(before["scheduled_tasks"][3:7], (0, 0, "never", None))

    def test_legacy_fixture_does_not_invent_stable_schedule_support(self):
        with sqlite3.connect(self.database) as db:
            db.execute("DROP TABLE scheduled_tasks")
        before = gates._seed_t3_fixture(self.database, self.root, include_schedule=False)
        self.assertEqual(set(before), {"projection_projects", "projection_threads", "projection_thread_messages", "migrations"})
        with sqlite3.connect(self.database) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name='scheduled_tasks'").fetchone(), (0,))
        with self.assertRaises(sqlite3.OperationalError):
            gates._t3_fixture_fingerprint(self.database)

    def test_disabled_schedule_payload_drift_is_detectable(self):
        before = gates._seed_t3_fixture(self.database, self.root)
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE scheduled_tasks SET prompt='changed user task',schedule_json='{}'")
        self.assertNotEqual(before, gates._t3_fixture_fingerprint(self.database))

    def test_synthetic_row_loss_is_detected(self):
        gates._seed_t3_fixture(self.database, self.root)
        with sqlite3.connect(self.database) as db:
            db.execute("DELETE FROM projection_thread_messages")
        with self.assertRaisesRegex(gates.GateError, "omitted"):
            gates._t3_fixture_fingerprint(self.database)

    def test_migration_enabling_or_running_a_schedule_is_detected(self):
        gates._seed_t3_fixture(self.database, self.root)
        with sqlite3.connect(self.database) as db:
            db.execute("UPDATE scheduled_tasks SET enabled=1")
        with self.assertRaisesRegex(gates.GateError, "enabled or executed"):
            gates._t3_fixture_fingerprint(self.database)


if __name__ == "__main__":
    unittest.main()
