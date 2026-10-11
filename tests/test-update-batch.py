#!/usr/bin/env python3
"""Adversarial configured-channel fixtures; no Nix builds or activation."""
import base64
import copy
import hashlib
import importlib.util
import json
import os
import re
import struct
from unittest.mock import patch
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "batch_policy", Path(__file__).resolve().parents[1] / "scripts/weasel-update-batch.py"
)
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)

IDENTIFIER = "20261008T220000Z-1234abcd"


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


def github(owner, repository, reference, revision):
    return {
        "original": {"type": "github", "owner": owner, "repo": repository, "ref": reference},
        "locked": {
            "type": "github", "owner": owner, "repo": repository, "rev": revision,
            "lastModified": 1780000000,
            "narHash": "sha256-" + base64.b64encode(hashlib.sha256(revision.encode()).digest()).decode(),
        },
    }


def fixture_lock():
    nodes = {
        "root": {"inputs": {
            "nixpkgs": "stable", "home-manager": "hm", "nixpkgs-unstable": "moving",
            "quickshell": "shell", "handy": "app",
        }},
        "stable": github("nixos", "nixpkgs", "nixos-25.11", "a" * 40),
        "hm": github("nix-community", "home-manager", "release-25.11", "b" * 40),
        "moving": github("nixos", "nixpkgs", "nixos-unstable", "c" * 40),
        "app": github("cjpais", "Handy", "v0.9.6", "d" * 40),
        "dependency": github("nix-community", "bun2nix", "2.0.8", "e" * 40),
        "shell": {
            "original": {"type": "git", "url": "https://git.outfoxxed.me/outfoxxed/quickshell"},
            "locked": {
                "type": "git", "url": "https://git.outfoxxed.me/outfoxxed/quickshell",
                "rev": "f" * 40, "ref": "refs/heads/master", "lastModified": 1780000000,
                "narHash": "sha256-" + base64.b64encode(bytes(32)).decode(),
            },
        },
    }
    nodes["hm"]["inputs"] = {"nixpkgs": ["nixpkgs"]}
    nodes["shell"]["inputs"] = {"nixpkgs": ["nixpkgs"]}
    nodes["app"]["inputs"] = {"nixpkgs": ["nixpkgs-unstable"], "tool": "dependency"}
    return {"version": 7, "root": "root", "nodes": nodes}


def fixture_flake():
    return b'''{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-25.11";
    home-manager = {
      url = "github:nix-community/home-manager/release-25.11";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    nixpkgs-unstable.url = "github:nixos/nixpkgs/nixos-unstable";
    quickshell = {
      url = "git+https://git.outfoxxed.me/outfoxxed/quickshell";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    handy = {
      url = "github:cjpais/Handy/v0.9.6";
      inputs.nixpkgs.follows = "nixpkgs-unstable";
    };
  };
}
'''


def transitions(changes, mode="batch"):
    changes = dict(changes)
    old_learning = b"# Prior verified work\n"
    changes["agent-learnings.md"] = (
        old_learning, old_learning + batch.learning_suffix(IDENTIFIER, mode, changes)
    )
    return changes


class BatchPolicyTests(unittest.TestCase):
    def setUp(self):
        # Existing session/source fixtures use temporary non-Store roots;
        # independent NVIDIA fixtures below validate the actual new guard.
        guard = patch.object(batch, "verify_nvidia_live_abi", return_value={"ok": True, "fixture": "graphical-session-only"})
        guard.start()
        self.addCleanup(guard.stop)

    def check(self, changes, mode="batch"):
        return batch.validate_changes(transitions(changes, mode), mode, IDENTIFIER)

    def test_many_configured_channels_advance_together(self):
        before = fixture_lock()
        after = copy.deepcopy(before)
        for name, revision in [("stable", "1"), ("hm", "2"), ("moving", "3"), ("shell", "4")]:
            after["nodes"][name]["locked"]["rev"] = revision * 40
        result = self.check({"flake.lock": (encoded(before), encoded(after))})
        self.assertEqual(result["mode"], "batch")
        self.assertEqual(result["new_lock_nodes"], 6)

    def test_paired_named_release_migration_is_allowed(self):
        before = fixture_lock()
        after = copy.deepcopy(before)
        after["nodes"]["stable"]["original"]["ref"] = "nixos-26.05"
        after["nodes"]["hm"]["original"]["ref"] = "release-26.05"
        old_flake = fixture_flake()
        new_flake = old_flake.replace(b"nixos-25.11", b"nixos-26.05").replace(
            b"release-25.11", b"release-26.05"
        )
        result = self.check({"flake.nix": (old_flake, new_flake),
                             "flake.lock": (encoded(before), encoded(after))}, "release-migration")
        self.assertEqual(result["mode"], "release-migration")

    def test_moving_channel_cannot_silently_become_master(self):
        before = fixture_lock()
        after = copy.deepcopy(before)
        after["nodes"]["moving"]["original"]["ref"] = "master"
        with self.assertRaises(batch.BatchError):
            self.check({"flake.lock": (encoded(before), encoded(after))})

    def test_lock_only_release_change_is_not_ordinary_batch(self):
        before = fixture_lock()
        after = copy.deepcopy(before)
        after["nodes"]["stable"]["original"]["ref"] = "nixos-26.05"
        after["nodes"]["hm"]["original"]["ref"] = "release-26.05"
        with self.assertRaises(batch.BatchError):
            self.check({"flake.lock": (encoded(before), encoded(after))})

    def test_named_migration_lock_must_match_paired_flake_release(self):
        before = fixture_lock()
        after = copy.deepcopy(before)
        after["nodes"]["stable"]["locked"]["rev"] = "1" * 40
        old_flake = fixture_flake()
        new_flake = old_flake.replace(b"nixos-25.11", b"nixos-26.05").replace(
            b"release-25.11", b"release-26.05"
        )
        with self.assertRaises(batch.BatchError):
            self.check({"flake.nix": (old_flake, new_flake),
                        "flake.lock": (encoded(before), encoded(after))}, "release-migration")

    def test_git_root_fetch_cannot_disagree_with_original(self):
        before = fixture_lock()
        after = copy.deepcopy(before)
        after["nodes"]["shell"]["locked"]["url"] = "https://attacker.invalid/quickshell"
        with self.assertRaises(batch.BatchError):
            self.check({"flake.lock": (encoded(before), encoded(after))})

    def test_git_root_cannot_change_selected_default_branch(self):
        before = fixture_lock()
        after = copy.deepcopy(before)
        after["nodes"]["shell"]["original"]["ref"] = "experimental"
        after["nodes"]["shell"]["locked"]["ref"] = "refs/heads/experimental"
        with self.assertRaises(batch.BatchError):
            self.check({"flake.lock": (encoded(before), encoded(after))})

    def test_transitive_fetch_cannot_disagree_with_original(self):
        before = fixture_lock()
        after = copy.deepcopy(before)
        after["nodes"]["dependency"]["locked"]["owner"] = "attacker"
        with self.assertRaises(batch.BatchError):
            self.check({"flake.lock": (encoded(before), encoded(after))})

    def test_explicit_immutable_revision_cannot_be_rebound(self):
        before = fixture_lock()
        dependency = before["nodes"]["dependency"]
        dependency["original"].pop("ref")
        dependency["original"]["rev"] = dependency["locked"]["rev"]
        after = copy.deepcopy(before)
        after["nodes"]["dependency"]["locked"]["rev"] = "9" * 40
        with self.assertRaises(batch.BatchError):
            self.check({"flake.lock": (encoded(before), encoded(after))})

    def test_configured_root_follows_cannot_select_another_channel(self):
        before = fixture_lock()
        after = copy.deepcopy(before)
        after["nodes"]["shell"]["inputs"]["nixpkgs"] = ["nixpkgs-unstable"]
        with self.assertRaises(batch.BatchError):
            self.check({"flake.lock": (encoded(before), encoded(after))})

    def duplicate_fixture(self):
        graph = fixture_lock()
        graph["nodes"]["systems_4"] = github("nix-systems", "default", "master", "8" * 40)
        graph["nodes"]["dependency"]["inputs"] = {"systems": "systems_4"}
        compact = lambda value: json.dumps(value, separators=(",", ":")).encode()
        marker = b'"systems_4":' + compact(graph["nodes"]["systems_4"])
        original = compact(graph)
        self.assertEqual(original.count(marker), 1)
        duplicate = original.replace(marker, marker + b"," + marker, 1)
        return graph, original, duplicate, marker

    def test_identical_existing_duplicate_node_can_be_canonicalized(self):
        graph, _canonical, duplicate, _marker = self.duplicate_fixture()
        graph["nodes"]["stable"]["locked"]["rev"] = "1" * 40
        result = self.check({"flake.lock": (duplicate, encoded(graph))})
        self.assertEqual(result["old_lock_nodes"], 7)
        self.assertEqual(result["new_lock_nodes"], 7)

    def test_new_duplicate_node_is_rejected_even_if_identical(self):
        _graph, canonical, duplicate, _marker = self.duplicate_fixture()
        with self.assertRaises(batch.BatchError):
            self.check({"flake.lock": (canonical, duplicate)})

    def test_conflicting_existing_duplicate_node_cannot_be_silently_chosen(self):
        _graph, canonical, duplicate, marker = self.duplicate_fixture()
        conflicting = marker.replace(b'"rev":"' + b"8" * 40, b'"rev":"' + b"9" * 40)
        ambiguous = duplicate.replace(marker, conflicting, 1)
        with self.assertRaises(batch.BatchError):
            self.check({"flake.lock": (ambiguous, canonical)})

    def test_home_attrset_state_version_is_protected(self):
        old = b'{ home = { stateVersion = "24.11"; packages = []; }; }\n'
        new = old.replace(b'"24.11"', b'"26.05"')
        with self.assertRaises(batch.BatchError):
            self.check({"profiles/home/common.nix": (old, new)})

    def test_nested_sudo_policy_is_protected(self):
        old = b'{ security = { sudo = { wheelNeedsPassword = true; }; }; }\n'
        new = old.replace(b"true", b"false")
        with self.assertRaises(batch.BatchError):
            self.check({"hosts/nixy-laptop/config.nix": (old, new)})

    def test_root_ssh_login_cannot_be_enabled_in_allowed_config_file(self):
        old = b'{ services.openssh.settings.PermitRootLogin = "no"; }\n'
        new = old.replace(b'"no"', b'"yes"')
        with self.assertRaises(batch.BatchError):
            self.check({"hosts/nixy-laptop/config.nix": (old, new)})

    def test_security_fix_cannot_add_an_account_to_wheel(self):
        old = b'{ users.users.example.extraGroups = [ "audio" ]; }\n'
        new = old.replace(b'"audio"', b'"audio" "wheel"')
        with self.assertRaises(batch.BatchError):
            self.check({"hosts/nixy-laptop/users.nix": (old, new)})

    def test_existing_package_repair_is_not_blocked_by_missing_adapter(self):
        old = b'{ pkgs }: pkgs.hello.overrideAttrs (_: { version = "1.0"; })\n'
        new = old.replace(b'"1.0"', b'"1.1"')
        result = self.check({"packages/example.nix": (old, new)})
        self.assertIn("other apps not exercised", result["runtime_coverage"])

    def t3_pin(self):
        version = "0.0.46-nightly.20261008.2833"
        return {"version": version,
                "url": "https://github.com/pingdotgg/t3code/releases/download/v" + version +
                       "/T3-Code-" + version + "-x86_64.AppImage",
                "hash": "sha256-H48f1Im/hHCWZl72jqam9knS+pbxoWDmZkutwbFn9aA="}

    def test_t3_batch_cannot_downgrade_selected_nightly_to_old_stable(self):
        old = self.t3_pin()
        new = copy.deepcopy(old)
        new["version"] = "0.0.45"
        new["url"] = new["url"].replace(old["version"], new["version"])
        with self.assertRaises(batch.BatchError):
            self.check({"packages/t3code/source.json": (encoded(old), encoded(new))})

    def test_t3_batch_cannot_select_maintainer_preview(self):
        old = self.t3_pin()
        new = copy.deepcopy(old)
        new["version"] = "0.0.47-preview.20261009.1234"
        new["url"] = new["url"].replace(old["version"], new["version"])
        with self.assertRaises(batch.BatchError):
            self.check({"packages/t3code/source.json": (encoded(old), encoded(new))})

    def test_t3_batch_cannot_point_official_pin_at_another_host(self):
        old = self.t3_pin()
        new = copy.deepcopy(old)
        new["url"] = new["url"].replace("https://github.com", "https://attacker.invalid")
        with self.assertRaises(batch.BatchError):
            self.check({"packages/t3code/source.json": (encoded(old), encoded(new))})

    def test_niri_upgrade_needs_effective_session_preservation_flag(self):
        with tempfile.TemporaryDirectory(prefix="weasel-batch-session-test-") as directory:
            before, after = Path(directory) / "old", Path(directory) / "new"
            for root, version in [(before, "old"), (after, "new")]:
                unit = root / "etc/systemd/user/niri.service"
                unit.parent.mkdir(parents=True)
                unit.write_text("[Service]\nExecStart=/nix/store/" + version + "-niri/bin/niri --session\n")
            with self.assertRaises(batch.BatchError):
                batch.verify_runtime_units(before, after)

    def test_session_receipt_does_not_claim_new_kernel_is_running(self):
        with tempfile.TemporaryDirectory(prefix="weasel-batch-session-test-") as directory:
            before, after = Path(directory) / "old", Path(directory) / "new"
            for root, version in [(before, "old"), (after, "new")]:
                unit = root / "etc/systemd/user/niri.service"
                unit.parent.mkdir(parents=True)
                unit.write_text("[Service]\nX-RestartIfChanged=false\nExecStart=/nix/store/" + version + "-niri/bin/niri --session\n")
            result = batch.verify_runtime_units(before, after)
            self.assertTrue(result["checked"][0]["changed"])
            self.assertIn("may remain running", result["reboot"])

    def test_false_flag_in_unit_section_does_not_prevent_restart(self):
        with tempfile.TemporaryDirectory(prefix="weasel-batch-session-test-") as directory:
            before, after = Path(directory) / "old", Path(directory) / "new"
            for root, version in [(before, "old"), (after, "new")]:
                unit = root / "etc/systemd/user/niri.service"
                unit.parent.mkdir(parents=True)
                unit.write_text("[Unit]\nX-RestartIfChanged=false\n[Service]\nExecStart=/nix/store/" + version + "-niri/bin/niri --session\n")
            with self.assertRaises(batch.BatchError):
                batch.verify_runtime_units(before, after)

    def alias_session_fixture(self, directory):
        before, after = Path(directory) / "old", Path(directory) / "new"
        for root, version in [(before, "old"), (after, "new")]:
            units = root / "etc/systemd/system"
            units.mkdir(parents=True)
            (units / "greetd.service").write_text("[Service]\nExecStart=/nix/store/" + version + "-greetd/bin/greetd\n")
            (units / "display-manager.service").symlink_to("greetd.service")
            overrides = units / "greetd.service.d"
            overrides.mkdir()
            (overrides / "10-preserve.conf").write_text("[Service]\nX-RestartIfChanged=false\n")
        return before, after

    def test_real_alias_target_dropin_can_preserve_session(self):
        with tempfile.TemporaryDirectory(prefix="weasel-batch-session-test-") as directory:
            before, after = self.alias_session_fixture(directory)
            result = batch.verify_runtime_units(before, after)
            self.assertTrue(result["checked"][0]["changed"])
            self.assertFalse(result["checked"][0]["restart_on_change"])

    def test_later_alias_target_dropin_can_enable_restart(self):
        with tempfile.TemporaryDirectory(prefix="weasel-batch-session-test-") as directory:
            before, after = self.alias_session_fixture(directory)
            (after / "etc/systemd/system/greetd.service.d/20-restart.conf").write_text(
                "[Service]\nX-RestartIfChanged=true\n"
            )
            with self.assertRaises(batch.BatchError):
                batch.verify_runtime_units(before, after)

    def test_last_effective_service_dropin_false_preserves_session(self):
        with tempfile.TemporaryDirectory(prefix="weasel-batch-session-test-") as directory:
            before, after = self.alias_session_fixture(directory)
            overrides = after / "etc/systemd/system/greetd.service.d"
            (overrides / "20-restart.conf").write_text("[Service]\nX-RestartIfChanged=true\n")
            (overrides / "30-preserve.conf").write_text("[Service]\nX-RestartIfChanged=false\n")
            result = batch.verify_runtime_units(before, after)
            self.assertFalse(result["checked"][0]["restart_on_change"])


REAL_LOADED_NVIDIA_VERSION = batch._loaded_nvidia_version

class NvidiaLiveAbiTests(unittest.TestCase):
    """Real private artifact fixtures; mock only Store namespace/daemon and kernel metadata."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="weasel-batch-nvidia-fixtures-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.roots = set()
        namespace = re.compile(re.escape(str(self.base)) + r"/[0-9a-z]{32}-[A-Za-z0-9.+_?=-]+")
        for mock in (patch.object(batch, "STORE", namespace),
                     patch.object(batch, "_closure", side_effect=lambda root: set(self.roots)),
                     patch.object(batch, "_loaded_nvidia_version", return_value="580.142")):
            mock.start()
            self.addCleanup(mock.stop)
        self.old = self.fixture("a", "580.142")
        self.new = self.fixture("b", "580.142")

    def output(self, letter, name):
        path = self.base / (letter * 32 + "-" + name)
        path.mkdir()
        self.roots.add(str(path))
        return path

    def fixture(self, letter, version):
        system = self.output(letter, "nixos-system-test")
        configs = system / "etc/tmpfiles.d"
        configs.mkdir(parents=True)
        graphics = self.output(letter.upper().lower().replace("a", "c").replace("b", "d"), "graphics-drivers")
        (graphics / "lib").mkdir()
        if version is not None:
            vendor = self.output({"a": "e", "b": "f"}[letter], "nvidia-x11-" + version)
            (vendor / "lib").mkdir()
            library = vendor / "lib" / ("libnvidia-ml.so." + version)
            data = bytearray(64)
            data[:6] = b"\x7fELF\x02\x01"
            struct.pack_into("<H", data, 16, 3)
            library.write_bytes(data)
            (graphics / "lib/libnvidia-ml.so.1").symlink_to(library)
        (configs / "graphics-driver.conf").write_text(
            "'L+' '/run/opengl-driver' '-' '-' '-' '-' " + str(graphics) + "\n")
        self.immutable()
        return system

    def immutable(self):
        for root in self.roots:
            for path in sorted(Path(root).rglob("*"), reverse=True):
                if not path.is_symlink():
                    path.chmod(0o555 if path.is_dir() else 0o444)
            Path(root).chmod(0o555)

    def selected_library(self, system):
        return Path(batch._nvidia_selection(system)["library"])

    def change_library(self, version):
        old = self.selected_library(self.new)
        old.parent.chmod(0o755)
        new = old.with_name("libnvidia-ml.so." + version)
        old.rename(new)
        graphics = self.base / ("d" * 32 + "-graphics-drivers")
        (graphics / "lib").chmod(0o755)
        link = graphics / "lib/libnvidia-ml.so.1"
        link.unlink()
        link.symlink_to(new)
        self.immutable()

    def test_same_driver_version_bound_to_actual_immutable_library_is_valid(self):
        result = batch.verify_nvidia_live_abi(self.old, self.new)
        self.assertTrue(result["ok"])
        self.assertEqual(result["new"]["version"], "580.142")
        self.assertEqual(result["new"]["library_sha256"], hashlib.sha256(self.selected_library(self.new).read_bytes()).hexdigest())
        self.assertIn("no GPU query", result["coverage"])

    def test_upgraded_userspace_against_old_loaded_driver_is_blocked(self):
        self.change_library("595.71.05")
        with self.assertRaisesRegex(batch.BatchError, "does not match"):
            batch.verify_nvidia_live_abi(self.old, self.new)

    def test_missing_loaded_driver_is_not_inferred_from_active_generation(self):
        with patch.object(batch, "_loaded_nvidia_version", return_value=None):
            with self.assertRaisesRegex(batch.BatchError, "does not match"):
                batch.verify_nvidia_live_abi(self.old, self.new)

    def test_non_nvidia_system_remains_valid(self):
        # Remove both actual selected libraries; immutable generated Mesa-style
        # rules still exist, and fixed loaded-module metadata is absent.
        for letter in ("c", "d"):
            folder = self.base / (letter * 32 + "-graphics-drivers/lib")
            folder.chmod(0o755)
            (folder / "libnvidia-ml.so.1").unlink()
            folder.chmod(0o555)
        with patch.object(batch, "_loaded_nvidia_version", return_value=None):
            self.assertTrue(batch.verify_nvidia_live_abi(self.old, self.new)["ok"])

    def test_removal_of_existing_nvidia_userspace_is_blocked(self):
        folder = self.base / ("d" * 32 + "-graphics-drivers/lib")
        folder.chmod(0o755)
        (folder / "libnvidia-ml.so.1").unlink()
        folder.chmod(0o555)
        with self.assertRaisesRegex(batch.BatchError, "removes"):
            batch.verify_nvidia_live_abi(self.old, self.new)

    def test_duplicate_graphics_rule_is_blocked(self):
        folder = self.new / "etc/tmpfiles.d"
        folder.chmod(0o755)
        (folder / "other.conf").write_bytes((folder / "graphics-driver.conf").read_bytes())
        self.immutable()
        with self.assertRaisesRegex(batch.BatchError, "Ambiguous"):
            batch.verify_nvidia_live_abi(self.old, self.new)

    def test_writable_selected_library_is_blocked(self):
        self.selected_library(self.new).chmod(0o644)
        with self.assertRaisesRegex(batch.BatchError, "Writable"):
            batch.verify_nvidia_live_abi(self.old, self.new)

    def test_actual_library_missing_from_exact_closure_is_blocked(self):
        self.roots.remove(str(self.selected_library(self.new).parent.parent))
        with self.assertRaisesRegex(batch.BatchError, "exact immutable closure"):
            batch.verify_nvidia_live_abi(self.old, self.new)

    def test_broken_library_link_is_blocked(self):
        path = self.selected_library(self.new)
        path.parent.chmod(0o755)
        path.unlink()
        path.parent.chmod(0o555)
        with self.assertRaisesRegex(batch.BatchError, "Broken selected"):
            batch.verify_nvidia_live_abi(self.old, self.new)

    def test_library_symlink_to_unmanaged_path_is_blocked(self):
        target = self.base / "unmanaged.so"
        target.write_bytes(self.selected_library(self.new).read_bytes())
        target.chmod(0o444)
        folder = self.base / ("d" * 32 + "-graphics-drivers/lib")
        folder.chmod(0o755)
        link = folder / "libnvidia-ml.so.1"
        link.unlink()
        link.symlink_to(target)
        folder.chmod(0o555)
        with self.assertRaisesRegex(batch.BatchError, "exact immutable closure"):
            batch.verify_nvidia_live_abi(self.old, self.new)

    def test_unknown_library_basename_cannot_waive_version_comparison(self):
        self.change_library("unknown")
        with self.assertRaisesRegex(batch.BatchError, "unknown exact version"):
            batch.verify_nvidia_live_abi(self.old, self.new)

    def test_non_elf_library_is_blocked(self):
        library = self.selected_library(self.new)
        library.chmod(0o644)
        library.write_bytes(b"not a driver library")
        library.chmod(0o444)
        with self.assertRaisesRegex(batch.BatchError, "ELF64"):
            batch.verify_nvidia_live_abi(self.old, self.new)

    def test_loaded_module_race_is_blocked(self):
        with patch.object(batch, "_loaded_nvidia_version", side_effect=["580.142", "595.71.05"]):
            with self.assertRaisesRegex(batch.BatchError, "changed during"):
                batch.verify_nvidia_live_abi(self.old, self.new)

    def test_selection_race_is_blocked(self):
        real = batch._nvidia_selection
        calls = []
        def racing(root):
            result = real(root)
            calls.append(root)
            if len(calls) == 4:
                result = dict(result, library_sha256="0" * 64)
            return result
        with patch.object(batch, "_nvidia_selection", side_effect=racing):
            with self.assertRaisesRegex(batch.BatchError, "changed during"):
                batch.verify_nvidia_live_abi(self.old, self.new)

    def test_runtime_gate_invokes_nvidia_guard_without_caller_override(self):
        with patch.object(batch, "verify_nvidia_live_abi", side_effect=batch.BatchError("NVIDIA blocked")) as guard:
            with self.assertRaisesRegex(batch.BatchError, "NVIDIA blocked"):
                batch.verify_runtime_units(self.old, self.new)
            guard.assert_called_once_with(self.old, self.new)

    def test_fixed_kernel_metadata_rejects_unknown_version_and_symlink(self):
        # Exercise the real loader via an os.open seam; the requested path must
        # always be the fixed sysfs file and include O_NOFOLLOW.
        real_open = os.open
        def redirected(path, flags):
            self.assertEqual(str(path), "/sys/module/nvidia/version")
            self.assertTrue(flags & os.O_NOFOLLOW)
            return real_open(self.base / "kernel-version", flags)
        kernel = self.base / "kernel-version"
        kernel.write_bytes(b"580.142\n")
        # setUp mocks metadata only; recover the original supplied below by the
        # private test assembler, without adding a production bypass parameter.
        with patch.object(batch.os, "open", side_effect=redirected):
            self.assertEqual(REAL_LOADED_NVIDIA_VERSION(), "580.142")
            kernel.write_bytes(b"unrecognized\n")
            with self.assertRaisesRegex(batch.BatchError, "Unknown"):
                REAL_LOADED_NVIDIA_VERSION()
            kernel.unlink()
            kernel.symlink_to(self.base / "unknown")
            with self.assertRaisesRegex(batch.BatchError, "Cannot establish"):
                REAL_LOADED_NVIDIA_VERSION()


@unittest.skipUnless(shutil.which("nix"), "Semantic protection fixtures require local Nix")
class SemanticBatchTests(unittest.TestCase):
    """Evaluate synthetic flakes locally; no real host secrets, builds or activation."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="weasel-batch-semantic-test-")
        self.addCleanup(temporary.cleanup)
        self.before, self.after = Path(temporary.name) / "old", Path(temporary.name) / "new"
        self.expected = {
            "environment": {"systemPackages": [{"outPath": "/nix/store/" + "a" * 32 + "-prepare"},
                                                {"outPath": "/nix/store/" + "b" * 32 + "-bootstrap"}]},
            "systemd": {
                "services": {"weasel-update-activate": {
                    "serviceConfig": {"User": "root", "Type": "oneshot", "UMask": "0077",
                                      "ExecStart": "/nix/store/" + "c" * 32 + "-activate/bin/updater"},
                    "restartIfChanged": False,
                }},
                "paths": {"weasel-update-activate": {
                    "wantedBy": ["multi-user.target"],
                    "pathConfig": {"PathExists": "/var/lib/weasel-updates-inbox/request.json",
                                   "Unit": "weasel-update-activate.service"},
                }},
            },
        }
        self.config = {
            "system": {"stateVersion": "24.11", "nixos": {"release": "25.11"}},
            "home-manager": {"users": {"example": {"home": {"stateVersion": "24.11"}}}},
            "users": {"mutableUsers": False, "users": {
                "example": {"uid": 1000, "isNormalUser": True, "isSystemUser": False,
                            "home": "/home/example", "group": "users", "extraGroups": ["wheel"],
                            "hashedPassword": "synthetic-fixture", "openssh": {"authorizedKeys": {"keys": []}}}
            }},
            "services": {"openssh": {"enable": True, "openFirewall": False,
                                      "settings": {"PermitRootLogin": "no"}, "authorizedKeysFiles": []}},
            "security": {"sudo": {"enable": True, "wheelNeedsPassword": True, "extraRules": [], "extraConfig": ""},
                         "polkit": {"enable": True, "extraConfig": ""},
                         "doas": {"enable": False, "extraRules": [], "extraConfig": ""}},
            "nix": {"settings": {"trusted-users": ["root"], "allowed-users": ["*"],
                                  "require-sigs": True, "trusted-public-keys": [], "substituters": []}},
            "environment": copy.deepcopy(self.expected["environment"]),
            "systemd": copy.deepcopy(self.expected["systemd"]),
        }
        self.config["systemd"]["services"]["weasel-update-activate"]["enable"] = True
        self.config["systemd"]["paths"]["weasel-update-activate"]["enable"] = True
        self.ssh_fragment = ("Host synthetic-recovery\n"
                             "  HostName 192.0.2.1\n"
                             "  IdentityAgent /run/user/1000/infra.sock\n"
                             "  IdentityFile /home/example/.ssh/recovery\n")
        home = self.config["home-manager"]["users"]["example"]
        home["home"]["file"] = {".ssh/weasel-vps.conf": {"source": "fixture", "force": True}}
        home["systemd"] = {"user": {"services": {"weasel-proton-infra-ssh-agent": {
            "Unit": {"Description": "Synthetic infrastructure SSH agent", "After": ["dbus.service"]},
            "Install": {"WantedBy": ["default.target"]},
            "Service": {
                "ExecStart": ["/nix/store/" + "d" * 32 + "-pass-cli/bin/pass-cli ssh-agent start "
                              "--share-id own --socket /run/user/1000/infra.sock"],
                "Environment": ["DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus"],
                "NoNewPrivileges": True, "UMask": "0077",
            },
        }}}}

    def write_source(self, path, config, *, ssh_fragment=None):
        (path / "modules").mkdir(parents=True)
        fixture = path / "fixture-ssh.conf"
        fixture.write_text(self.ssh_fragment if ssh_fragment is None else ssh_fragment)
        config = copy.deepcopy(config)
        config["home-manager"]["users"]["example"]["home"]["file"][".ssh/weasel-vps.conf"]["source"] = str(fixture)
        (path / "modules/daily-updates.nix").write_text(
            "{ config, pkgs, ... }: builtins.fromJSON ''" + json.dumps(self.expected) + "''\n"
        )
        (path / "flake.nix").write_text(
            "{ outputs = { self }: let c = builtins.fromJSON ''" + json.dumps(config) + "''; "
            "in { nixosConfigurations = builtins.listToAttrs (map "
            "(name: { inherit name; value = { pkgs = {}; config = c; }; }) "
            "[ \"nixy-laptop\" \"nixy-desktop\" \"michapc\" \"michapc-debug\" ]); }; }\n"
        )

    def evaluate(self, expression):
        # A private local evaluation store keeps the fixture independent of the
        # real daemon socket and never allocates to the workstation's Nix store.
        result = subprocess.run([shutil.which("nix"), "eval", "--store", str(self.before.parent / "eval-store"),
                                 "--raw", "--offline", "--impure",
                                 "--no-write-lock-file", "--expr", expression],
                                capture_output=True, check=True, timeout=30)
        return result.stdout

    def verify(self, candidate, mode="batch", *, ssh_fragment=None):
        self.write_source(self.before, self.config)
        self.write_source(self.after, candidate, ssh_fragment=ssh_fragment)
        # This fixture isolates authentication/stateVersion invariants with a
        # synthetic example user and no real package set. Source Codex ownership
        # is evaluated separately by the source adapter's private Nix fixture.
        from unittest.mock import patch
        from types import SimpleNamespace
        # This existing synthetic fixture has no real stable package set.
        # Preserve its real Nix auth/state proof while mocking only the new
        # separate SSH proof; real SSH binding/negative fixtures are in the
        # migration suite and the required private integration receipts.
        def ssh_proof(expression, before, after, host, evaluator, executor):
            self.assertIsNotNone(executor)
            return {"old": evaluator(expression(before,host)).decode().strip(),
                    "new": evaluator(expression(after,host)).decode().strip(),
                    "coverage": "Synthetic auth fixture; SSH execution mocked"}
        adapter=SimpleNamespace(verify_general=ssh_proof)
        spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:None))
        with patch.object(batch, "codex_ownership_predicate", return_value="true"), \
             patch.object(batch.importlib.util,"spec_from_file_location",return_value=spec), \
             patch.object(batch.importlib.util,"module_from_spec",return_value=adapter):
            return batch.verify_sensitive_state(self.before, self.after, self.evaluate, mode=mode,
                                                 migration_executor=lambda *args:b"fixture-only")

    def candidate_agent(self, candidate):
        return candidate["home-manager"]["users"]["example"]["systemd"]["user"]["services"]["weasel-proton-infra-ssh-agent"]

    def test_unchanged_effective_protection_is_allowed(self):
        self.assertTrue(self.verify(copy.deepcopy(self.config))["ok"])

    def test_native_agent_dependency_store_prefix_can_advance_without_changing_scope(self):
        candidate = copy.deepcopy(self.config)
        service = self.candidate_agent(candidate)["Service"]
        service["ExecStart"][0] = service["ExecStart"][0].replace("d" * 32 + "-pass-cli", "e" * 32 + "-pass-cli-new")
        self.assertTrue(self.verify(candidate)["ok"])

    def test_native_agent_vault_scope_change_is_blocked(self):
        candidate = copy.deepcopy(self.config)
        service = self.candidate_agent(candidate)["Service"]
        service["ExecStart"][0] = service["ExecStart"][0].replace("--share-id own", "--share-id another-vault")
        with self.assertRaisesRegex(batch.BatchError, "authentication"):
            self.verify(candidate)

    def test_native_agent_socket_change_is_blocked(self):
        candidate = copy.deepcopy(self.config)
        service = self.candidate_agent(candidate)["Service"]
        service["ExecStart"][0] = service["ExecStart"][0].replace("--socket /run/user/1000/infra.sock", "--socket /run/user/1000/default-agent.sock")
        with self.assertRaisesRegex(batch.BatchError, "authentication"):
            self.verify(candidate)

    def test_native_agent_environment_change_is_blocked(self):
        candidate = copy.deepcopy(self.config)
        self.candidate_agent(candidate)["Service"]["Environment"] = ["DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/another-bus"]
        with self.assertRaisesRegex(batch.BatchError, "authentication"):
            self.verify(candidate)

    def test_native_agent_install_target_change_is_blocked(self):
        candidate = copy.deepcopy(self.config)
        self.candidate_agent(candidate)["Install"]["WantedBy"] = ["graphical-session.target"]
        with self.assertRaisesRegex(batch.BatchError, "authentication"):
            self.verify(candidate)

    def test_recovery_ssh_fragment_content_change_is_blocked(self):
        candidate = copy.deepcopy(self.config)
        changed = self.ssh_fragment.replace("Host synthetic-recovery", "Host different-recovery")
        with self.assertRaisesRegex(batch.BatchError, "authentication"):
            self.verify(candidate, ssh_fragment=changed)

    def test_recovery_ssh_fragment_force_policy_change_is_blocked(self):
        candidate = copy.deepcopy(self.config)
        candidate["home-manager"]["users"]["example"]["home"]["file"][".ssh/weasel-vps.conf"]["force"] = False
        with self.assertRaisesRegex(batch.BatchError, "authentication"):
            self.verify(candidate)

    def test_actual_release_cannot_be_hidden_by_unchanged_lock_labels(self):
        candidate = copy.deepcopy(self.config)
        candidate["system"]["nixos"]["release"] = "26.05"
        with self.assertRaises((batch.BatchError, subprocess.CalledProcessError)):
            self.verify(candidate)

    def test_effective_updater_cannot_be_removed(self):
        candidate = copy.deepcopy(self.config)
        candidate["systemd"]["services"].pop("weasel-update-activate")
        with self.assertRaises((batch.BatchError, subprocess.CalledProcessError)):
            self.verify(candidate)

    def test_effective_updater_cannot_be_disabled(self):
        candidate = copy.deepcopy(self.config)
        candidate["systemd"]["services"]["weasel-update-activate"]["enable"] = False
        with self.assertRaises((batch.BatchError, subprocess.CalledProcessError)):
            self.verify(candidate)

    def test_effective_inbox_path_cannot_be_disabled(self):
        candidate = copy.deepcopy(self.config)
        candidate["systemd"]["paths"]["weasel-update-activate"]["enable"] = False
        with self.assertRaises((batch.BatchError, subprocess.CalledProcessError)):
            self.verify(candidate)

    def test_root_pre_start_command_cannot_be_added_via_another_module(self):
        candidate = copy.deepcopy(self.config)
        candidate["systemd"]["services"]["weasel-update-activate"]["serviceConfig"]["ExecStartPre"] = "/nix/store/" + "d" * 32 + "-unexpected/bin/run"
        with self.assertRaises((batch.BatchError, subprocess.CalledProcessError)):
            self.verify(candidate)

    def test_service_mount_cannot_shadow_the_immutable_helper(self):
        candidate = copy.deepcopy(self.config)
        target = self.expected["systemd"]["services"]["weasel-update-activate"]["serviceConfig"]["ExecStart"]
        candidate["systemd"]["services"]["weasel-update-activate"]["serviceConfig"]["BindReadOnlyPaths"] = [
            "/home/example/mutable-command:" + target
        ]
        with self.assertRaises((batch.BatchError, subprocess.CalledProcessError)):
            self.verify(candidate)

    def test_effective_prepare_helper_cannot_be_removed(self):
        candidate = copy.deepcopy(self.config)
        candidate["environment"]["systemPackages"].pop(0)
        with self.assertRaises((batch.BatchError, subprocess.CalledProcessError)):
            self.verify(candidate)


class SensitiveEvalArgumentTests(unittest.TestCase):
    def test_cached_proof_read_forbids_local_remote_builds_and_substitution(self):
        expression = 'builtins.readFile cachedContext'
        self.assertEqual(batch.sensitive_eval_args(expression), [
            'eval', '--raw', '--impure', '--no-write-lock-file', '--offline',
            '--max-jobs', '0', '--builders', '', '--option', 'substitute', 'false',
            '--option', 'allow-import-from-derivation', 'true', '--expr', expression])

    def test_invalid_expression_is_refused_and_options_do_not_persist_mutation(self):
        for value in [None, b'expr', '', ' \n', 'expr\0tail']:
            with self.subTest(value=value), self.assertRaises(batch.BatchError):
                batch.sensitive_eval_args(value)
        arguments = batch.sensitive_eval_args('fixed-expression')
        arguments[arguments.index('--max-jobs') + 1] = '9'
        self.assertEqual(batch.sensitive_eval_args('fixed-expression')[6], '0')


if __name__ == "__main__":
    unittest.main()
