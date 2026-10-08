#!/usr/bin/env python3
"""Semantic failure cases for source policy and official artifact validation."""
import base64
import importlib.util
import json
import hashlib
import io
import time
from pathlib import Path
import struct
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("discovery", ROOT / "scripts/weasel-update-discover.py")
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
HASH = d.sri(bytes(32))


def pin(lane, version):
    return {"version": version, "url": d.pin_url(lane, version), "hash": HASH}


def rpm(version="26.1008.1", arch="x86_64", name="chatgpt"):
    def header(values):
        body = bytearray()
        index = bytearray()
        for tag, text in values:
            index.extend(struct.pack(">IIII", tag, 6, len(body), 1))
            body.extend(text.encode() + b"\0")
        return b"\x8e\xad\xe8\x01\0\0\0\0" + struct.pack(">II", len(values), len(body)) + index + body
    lead = b"\xed\xab\xee\xdb" + bytes(92)
    signature = header([])
    return lead + signature + header([(1000, name), (1001, version), (1002, "1"), (1022, arch)])


def release(version, preview=False):
    return {"tag_name": "v" + version, "name": "maintainer preview" if preview else version,
            "draft": False, "prerelease": "-" in version,
            "published_at": "2026-10-08T00:00:00Z", "assets": [
                {"name": f"T3-Code-{version}-x86_64.AppImage", "browser_download_url": d.pin_url("t3", version), "digest": "sha256:" + "00" * 32, "size": 100},
                {"name": "SHA256SUMS", "browser_download_url": f"{d.T3_ASSETS}/v{version}/SHA256SUMS"}]}


class FakeNetwork:
    def __init__(self, releases=None, manifest=None, hash_value=HASH):
        self.releases = releases or []
        self.manifest = manifest
        self.hash_value = hash_value
        self.downloads = []

    def json(self, url):
        return self.releases

    def read(self, url, limit=None, prefix=False):
        if self.manifest is not None:
            return self.manifest
        version = url.split("/v", 1)[1].split("/", 1)[0]
        return ("00" * 32 + "  " + f"T3-Code-{version}-x86_64.AppImage\n").encode()

    def artifact(self, url, integrity=None, size=None):
        self.downloads.append(url)
        return {"hash": self.hash_value, "bytes": size or 100, "prefix": b""}


class PinTests(unittest.TestCase):
    def test_stable_catches_up_to_nightly_without_downgrade(self):
        self.assertGreater(d.version_key("0.0.46"), d.version_key("0.0.46-nightly.20261008.2833"))
        self.assertLess(d.version_key("0.0.45"), d.version_key("0.0.46-nightly.20261008.2833"))
        self.assertGreater(d.version_key("0.0.46-nightly.20261009.2"), d.version_key("0.0.46-nightly.20261008.9999"))

    def test_maintainer_preview_tag_and_invalid_date_rejected(self):
        for value in ["0.0.46-maintainer-preview.1", "0.0.46-nightly.20261301.1", "0.0.46-nightly.20261008.1;exit", "00.0.46"]:
            with self.assertRaises(d.DiscoveryError):
                d.version_key(value)

    def test_json_duplicate_and_url_tamper_rejected(self):
        data = json.dumps(pin("t3", "0.0.46"))
        with self.assertRaises(d.DiscoveryError):
            d.read_pin("t3", data.replace('"version":', '"version":"0.0.45", "version":').encode())
        tampered = pin("t3", "0.0.46")
        tampered["url"] += "?token=anything"
        with self.assertRaises(d.DiscoveryError):
            d.validate_pin("t3", tampered)

    def test_nix_only_version_and_hash(self):
        for lane in ["codex", "chatgpt"]:
            before = (ROOT / d.SOURCE_FILES[lane]).read_bytes()
            old = d.read_pin(lane, before)
            new = pin(lane, "99.1.1")
            after = d.replace_pin(lane, before, new)
            self.assertEqual(d.validate_transition(lane, before, after, network=False), {"old": old, "new": new})
            with self.assertRaises(d.DiscoveryError):
                d.validate_transition(lane, before, after + b"\n# added code/comment\n", network=False)
            with self.assertRaises(d.DiscoveryError):
                d.read_pin(lane, before + b'\n  version = "99.1.1";\n')
            with self.assertRaises(d.DiscoveryError):
                d.read_pin(lane, before.replace(b'  version = "', b'  version = arbitrary; # "'))

    def test_t3_downgrade_and_same_version_replacement_rejected(self):
        before = json.dumps(pin("t3", "0.0.46-nightly.20261008.2833")).encode()
        for version in ["0.0.45", "0.0.46-nightly.20261008.2833", "0.0.46-nightly.20261008.1"]:
            with self.assertRaises(d.DiscoveryError):
                d.validate_transition("t3", before, json.dumps(pin("t3", version)).encode(), network=False)

    def test_regular_nightly_filters_preview_and_stable(self):
        versions = [release("0.0.46-nightly.20261008.2834"), release("0.0.46-nightly.20261008.9999", preview=True), release("0.0.46")]
        current = pin("t3", "0.0.46-nightly.20261008.2833")
        net = FakeNetwork(versions)
        result = d.discover("t3", current, "nightly", net)
        self.assertEqual(result["candidate"]["version"], "0.0.46-nightly.20261008.2834")
        self.assertEqual(len(net.downloads), 1)

    def test_old_stable_is_visible_hold_without_downgrade(self):
        current = pin("t3", "0.0.46-nightly.20261008.2833")
        net = FakeNetwork([release("0.0.45")])
        result = d.discover("t3", current, "stable", net)
        self.assertEqual(result["status"], "held-prerelease")
        self.assertIsNone(result["candidate"])
        self.assertEqual(net.downloads, [])

    def test_checksum_disagreement_duplicate_and_asset_url_rejected(self):
        candidate = release("0.0.46")
        name = "T3-Code-0.0.46-x86_64.AppImage"
        for manifest in [("11" * 32 + "  " + name + "\n").encode(), ("00" * 32 + "  " + name + "\n") .encode() * 2]:
            with self.assertRaises(d.DiscoveryError):
                d.t3_release_pin(candidate, "0.0.46", FakeNetwork(manifest=manifest))
        candidate["assets"][0]["browser_download_url"] = "https://github.com/evil/t3/releases/a"
        with self.assertRaises(d.DiscoveryError):
            d.t3_release_pin(candidate, "0.0.46", FakeNetwork())

    def test_download_hash_disagrees(self):
        with self.assertRaises(d.DiscoveryError):
            d.discover("t3", pin("t3", "0.0.45"), "stable", FakeNetwork([release("0.0.46")], hash_value=d.sri(bytes([1]) * 32)))

    def test_official_host_redirect_policy(self):
        for url in ["http://github.com/pingdotgg/t3code", "https://github.com.evil.example/a", "https://evil@github.com/a", "https://github.com:444/a", "https://127.0.0.1/a", "file:///tmp/a", "https://github.com/a#secret"]:
            with self.assertRaises(d.DiscoveryError):
                d.safe_url("t3", url)
        self.assertEqual(d.safe_url("t3", "https://release-assets.githubusercontent.com/a?sig=public"), "https://release-assets.githubusercontent.com/a?sig=public")

    def test_rpm_identity_and_bounds(self):
        self.assertEqual(d.rpm_metadata(rpm())["version"], "26.1008.1")
        for data in [rpm(arch="aarch64"), rpm(name="other"), rpm()[:125], b"not a package", rpm(version="26.1008.1;exit")]:
            with self.assertRaises(d.DiscoveryError):
                d.rpm_metadata(data)

    def test_private_output_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "metadata.json"
            d.private_output(path, {"ok": True})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(d.DiscoveryError):
                d.private_output(path, {"ok": False})

    def test_rpm_signature_namespace_does_not_shadow_identity(self):
        signature = (b"\x8e\xad\xe8\x01\0\0\0\0" + struct.pack(">II", 1, 4)
                     + struct.pack(">IIII", 1000, 4, 0, 1) + struct.pack(">I", 100))
        source = rpm()
        data = source[:96] + signature + bytes((-len(signature)) % 8) + source[112:]
        self.assertEqual(d.rpm_metadata(data)["version"], "26.1008.1")

    def test_desktop_manifest_identity_size_duplicates_and_hash(self):
        encoded = base64.b64encode(bytes(64)).decode()
        name = "T3-Code-0.0.46-x86_64.AppImage"
        manifest = (f"version: 0.0.46\nfiles:\n  - url: {name}\n    sha512: {encoded}\n"
                    f"    size: 100\npath: {name}\nsha512: {encoded}\n").encode()
        self.assertEqual(d.electron_checksum(manifest, "0.0.46", name, 100), "sha512-" + encoded)
        for changed in [manifest.replace(b"size: 100", b"size: 101"), manifest.replace(b"version: 0.0.46", b"version: 0.0.47"), manifest + b"path: other\n", manifest.replace(b"files:", b"files: !!tag")]:
            with self.assertRaises(d.DiscoveryError):
                d.electron_checksum(changed, "0.0.46", name, 100)

    def test_cli_only_checksums_require_official_desktop_manifest(self):
        candidate = release("0.0.46-nightly.20261008.2833")
        filename = "t3-0.0.46-nightly.20261008.2833-linux-x64.tar.gz"
        candidate["assets"].append({"name": filename, "digest": "sha256:" + "00" * 32})
        manifest = ("00" * 32 + "  " + filename + "\n").encode()
        with self.assertRaises(d.DiscoveryError):
            d.t3_release_pin(candidate, candidate["tag_name"][1:], FakeNetwork(manifest=manifest))

    def test_npm_platform_name_and_url_integrity_policy(self):
        integrity = "sha512-" + base64.b64encode(bytes(64)).decode()
        class Metadata:
            def __init__(self, value): self.value = value
            def json(self, url): return self.value
        proper = {"name": "@openai/codex", "version": "0.162.0-linux-x64", "dist": {"tarball": d.pin_url("codex", "0.162.0"), "integrity": integrity}}
        self.assertEqual(d.npm_exact_metadata("0.162.0", Metadata(proper))[0]["integrity"], integrity)
        for bad in [{**proper, "name": "@someone/codex"}, {**proper, "version": "0.162.0"}, {**proper, "dist": {"tarball": "https://registry.npmjs.org/other.tgz", "integrity": integrity}}, {**proper, "dist": {"tarball": proper["dist"]["tarball"], "integrity": "sha1-weak"}}]:
            with self.assertRaises(d.DiscoveryError):
                d.npm_exact_metadata("0.162.0", Metadata(bad))

    def test_streaming_integrity_size_and_total_budget(self):
        class Response(io.BytesIO):
            headers = {}
        net = d.Network("codex")
        net.open = lambda url, headers=None: Response(b"payload")
        correct = "sha512-" + base64.b64encode(hashlib.sha512(b"payload").digest()).decode()
        result = net.artifact(d.pin_url("codex", "0.162.0"), integrity=correct, size=7)
        self.assertEqual(result["hash"], d.sri(hashlib.sha256(b"payload").digest()))
        with self.assertRaises(d.DiscoveryError):
            net.artifact(d.pin_url("codex", "0.162.0"), integrity="sha512-invalid")
        with self.assertRaises(d.DiscoveryError):
            net.artifact(d.pin_url("codex", "0.162.0"), size=8)
        net.deadline = time.monotonic() - 1
        with self.assertRaises(d.DiscoveryError):
            net.artifact(d.pin_url("codex", "0.162.0"))
        net.deadline = time.monotonic() + 30
        with self.assertRaises(d.DiscoveryError):
            net.read(d.pin_url("codex", "0.162.0"), limit=3)

    def test_learning_append_has_deterministic_date_no_injection(self):
        value = d.learning_suffix("20261008T100000Z-deadbeef", "codex", "0.160.0", "0.162.0")
        self.assertIn(b"2026-10-08", value)
        self.assertIn(b"Activation: Pending", value)
        self.assertIn(b"/var/lib/weasel-updates/runs/20261008T100000Z-deadbeef/journal.json", value)
        for candidate_id in ["20261008/evil", "20261008\ncode", "20261301T00"]:
            with self.assertRaises(d.DiscoveryError):
                d.learning_suffix(candidate_id, "codex", "0.160.0", "0.162.0")

    def test_exact_validation_does_not_query_latest(self):
        calls = []
        old_function = d.verify_exact
        try:
            def exact(lane, version, net):
                calls.append(version)
                return pin(lane, version), {"exact": True}
            d.verify_exact = exact
            before = json.dumps(pin("t3", "0.0.45")).encode()
            after = json.dumps(pin("t3", "0.0.46")).encode()
            d.validate_transition("t3", before, after, network=True)
            self.assertEqual(calls, ["0.0.46"])
        finally:
            d.verify_exact = old_function


if __name__ == "__main__":
    unittest.main()
