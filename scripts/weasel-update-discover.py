#!/usr/bin/env python3
"""Bounded official-source discovery and exact pin transition validation.

This module never changes a repository or executes downloaded software.
validate_transition is also called independently by the privileged submitter.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import time
import urllib.parse
import urllib.request

SCHEMA_VERSION = 1
SOURCE_FILES = {
    "t3": "packages/t3code/source.json",
    "codex": "packages/codex-source/default.nix",
    "chatgpt": "packages/chatgpt/default.nix",
}
T3_API = "https://api.github.com/repos/pingdotgg/t3code"
T3_ASSETS = "https://github.com/pingdotgg/t3code/releases/download"
NPM_METADATA = "https://registry.npmjs.org/@openai%2Fcodex"
NPM_ASSETS = "https://registry.npmjs.org/@openai/codex/-/"
RPM_BASE = "https://persistent.oaistatic.com/codex-app-prod/linux/rpm/x86_64"
RPM_LATEST = "https://persistent.oaistatic.com/codex-app-prod/linux/rpm/latest/chatgpt.x86_64.rpm"
MAX_JSON = 4 * 1024 * 1024
MAX_ASSET = 768 * 1024 * 1024
MAX_RPM_HEADER = 2 * 1024 * 1024
SRI_RE = re.compile(r"sha256-[A-Za-z0-9+/]{43}=")
SEMVER_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-nightly\.([0-9]{8})\.(0|[1-9][0-9]*))?")
ALLOWED_HOSTS = {
    "t3": {"api.github.com", "github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"},
    "codex": {"registry.npmjs.org"},
    "chatgpt": {"persistent.oaistatic.com"},
}


class DiscoveryError(RuntimeError):
    pass


def lane_name(lane):
    if lane not in SOURCE_FILES:
        raise DiscoveryError("Unsupported lane")
    return lane


def version_key(value):
    if not isinstance(value, str) or len(value) > 128:
        raise DiscoveryError("Version must be a bounded string")
    match = SEMVER_RE.fullmatch(value)
    if not match:
        raise DiscoveryError("Unsupported stable/regular-nightly version")
    major, minor, patch = (int(x) for x in match.groups()[:3])
    date, sequence = match.groups()[3:]
    if date:
        try:
            dt.datetime.strptime(date, "%Y%m%d")
        except ValueError as error:
            raise DiscoveryError("Invalid nightly date") from error
        return major, minor, patch, 0, int(date), int(sequence)
    return major, minor, patch, 1, 0, 0


def sri(digest):
    return "sha256-" + base64.b64encode(digest).decode("ascii")


def object_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise DiscoveryError("Duplicate JSON key")
            result[key] = value
        return result
    try:
        return json.loads(data, object_pairs_hook=unique)
    except (ValueError, UnicodeDecodeError) as error:
        raise DiscoveryError("Invalid JSON metadata") from error


def pin_url(lane, version):
    lane_name(lane)
    version_key(version)
    if lane != "t3" and "-" in version:
        raise DiscoveryError("This lane accepts stable releases only")
    if lane == "t3":
        return f"{T3_ASSETS}/v{version}/T3-Code-{version}-x86_64.AppImage"
    if lane == "codex":
        return f"{NPM_ASSETS}codex-{version}-linux-x64.tgz"
    return f"{RPM_BASE}/chatgpt-{version}-1.x86_64.rpm"


def validate_pin(lane, pin):
    if lane == "codex":
        return validate_codex_source_pin(pin)
    if not isinstance(pin, dict) or set(pin) != {"version", "url", "hash"}:
        raise DiscoveryError("Pin must have exactly version, url and hash")
    if pin["url"] != pin_url(lane, pin["version"]):
        raise DiscoveryError("Pin URL is outside the exact official versioned path")
    if not isinstance(pin["hash"], str) or not SRI_RE.fullmatch(pin["hash"]):
        raise DiscoveryError("Pin must contain a SHA-256 SRI hash")
    if sri(base64.b64decode(pin["hash"][7:], validate=True)) != pin["hash"]:
        raise DiscoveryError("Noncanonical SHA-256 SRI hash")
    return dict(pin)



CODEX_BUNDLE = (
    "packages/codex-source/default.nix",
    "packages/codex-source/toolchain.nix",
    "packages/codex-source/codex-v0162-scoped-cancel.patch",
    "packages/codex-source/scoped-cancel-memory-tests.patch",
    "packages/codex-source/README.md",
)
CODEX_ADAPTER_REASON = (
    "Codex source/patch/toolchain updates require a reviewed source adapter and "
    "scoped-cancel patch rebase; npm binaries cannot replace this source bundle"
)


def _canonical_sri(value):
    if not isinstance(value, str) or not SRI_RE.fullmatch(value):
        raise DiscoveryError("Source pin must contain a SHA-256 SRI hash")
    if sri(base64.b64decode(value[7:], validate=True)) != value:
        raise DiscoveryError("Noncanonical SHA-256 SRI hash")
    return value


def validate_codex_source_pin(pin):
    if not isinstance(pin, dict) or set(pin) != {"kind", "version", "commit", "url", "hash"}:
        raise DiscoveryError("Codex source pin needs exactly kind/version/commit/url/hash")
    if pin["kind"] != "pinned-source":
        raise DiscoveryError("Codex source pin kind differs from pinned-source")
    version_key(pin["version"])
    if "-" in pin["version"]:
        raise DiscoveryError("Codex source version must be stable")
    commit = pin["commit"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise DiscoveryError("Codex source commit must be exact lowercase SHA-1")
    if pin["url"] != f"https://codeload.github.com/openai/codex/tar.gz/{commit}":
        raise DiscoveryError("Codex source URL does not match the exact official commit")
    _canonical_sri(pin["hash"])
    return dict(pin)


def _source_literal(text, key, indent):
    pattern = rf'(?m)^{" " * indent}{re.escape(key)} = "([^"\n]+)";$'
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1 or len(re.findall(rf"\b{re.escape(key)}\s*=(?!=)", text)) != 1:
        raise DiscoveryError("Expected one exact literal source assignment: " + key)
    return matches[0].group(1)


def _codex_source_fields(data):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DiscoveryError("Codex source is not UTF-8") from error
    blocks = {}
    for key, fetcher in (("src", "fetchzip"), ("v8", "fetchurl"), ("v8Binding", "fetchurl")):
        pattern = rf"(?ms)^  {key} = {fetcher} \{{\n(.*?)^  \}};$"
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1 or len(re.findall(rf"\b{key}\s*=", text)) != 1:
            raise DiscoveryError("Expected one exact literal source block: " + key)
        blocks[key] = {field: _source_literal(matches[0].group(1), field, 4)
                       for field in ("name", "url", "hash")}
        _canonical_sri(blocks[key]["hash"])
    url = blocks["src"]["url"]
    match = re.fullmatch(r"https://codeload\.github\.com/openai/codex/tar\.gz/([0-9a-f]{40})", url)
    if not match:
        raise DiscoveryError("Codex source archive must identify an exact official commit")
    commit = match.group(1)
    if blocks["src"]["name"] != "codex-" + commit or _source_literal(text, "STABLE_GIT_COMMIT", 4) != commit:
        raise DiscoveryError("Codex source name/embedded commit do not match the archive")
    version = _source_literal(text, "version", 2)
    pin = validate_codex_source_pin({"kind": "pinned-source", "version": version,
                                    "commit": commit, "url": url, "hash": blocks["src"]["hash"]})
    cargo_hash = _canonical_sri(_source_literal(text, "cargoHash", 2))
    release = re.fullmatch(
        r"https://github\.com/openai/codex/releases/download/rusty-v8-v([0-9]+\.[0-9]+\.[0-9]+)/"
        r"librusty_v8_ptrcomp_sandbox_release_x86_64-unknown-linux-gnu\.a\.gz", blocks["v8"]["url"])
    if not release or blocks["v8Binding"]["url"] != (
            "https://github.com/openai/codex/releases/download/rusty-v8-v" + release.group(1) +
            "/src_binding_ptrcomp_sandbox_release_x86_64-unknown-linux-gnu.rs"):
        raise DiscoveryError("V8 archive and binding must be paired official release assets")
    return pin, {"cargoHash": cargo_hash, "v8": blocks["v8"], "v8Binding": blocks["v8Binding"],
                 "v8Version": release.group(1), "sourceHashMode": "recursive-fetchzip-NAR-not-raw-tarball"}


def read_codex_source_pin(data):
    return _codex_source_fields(data)[0]


def codex_source_bundle(repository):
    repository = Path(repository)
    directory = repository / "packages/codex-source"
    if directory.is_symlink() or not directory.is_dir():
        raise DiscoveryError("Codex source bundle directory must be regular")
    observed = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise DiscoveryError("Codex source bundle must not contain symlinks")
        if path.is_file():
            observed.add(path.relative_to(repository).as_posix())
    if observed != set(CODEX_BUNDLE):
        raise DiscoveryError("Codex source bundle has missing or unexpected files")
    files, contents = {}, {}
    for name in CODEX_BUNDLE:
        path = repository / name
        if not path.is_file() or path.stat().st_size > MAX_JSON:
            raise DiscoveryError("Codex bundle file is absent or exceeds its bound")
        contents[name] = path.read_bytes()
        files[name] = hashlib.sha256(contents[name]).hexdigest()
    pin, dependencies = _codex_source_fields(contents[SOURCE_FILES["codex"]])
    text = contents["packages/codex-source/toolchain.nix"].decode("utf-8")
    revision = _source_literal(text, "rev", 4)
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise DiscoveryError("Frozen Rust package-set revision must be exact")
    nar_hash = _canonical_sri(_source_literal(text, "narHash", 4))
    if _source_literal(text, "type", 4) != "github" or _source_literal(text, "owner", 4) != "nixos" or _source_literal(text, "repo", 4) != "nixpkgs":
        raise DiscoveryError("Frozen Rust package set must be official Nixpkgs")
    return {"pin": pin, "files_sha256": files, "dependencies": dependencies,
            "toolchain": {"revision": revision, "narHash": nar_hash, "rustVersion": "1.95.0",
                          "note": "Toolchain builder frozen; non-Rust library arguments remain caller-bound"}}


def held_codex_source_discovery(current, net):
    current = validate_codex_source_pin(current)
    endpoint = f"{NPM_METADATA}/latest"
    metadata = net.json(endpoint)
    if not isinstance(metadata, dict) or metadata.get("name") != "@openai/codex":
        raise DiscoveryError("Unexpected npm latest package identity")
    selected = metadata.get("version")
    pin_url("codex", selected)  # Stable metadata validation only, never asset resolution.
    now = dt.datetime.now(dt.timezone.utc)
    return {"schema_version": SCHEMA_VERSION, "lane": "codex", "channel": "stable",
            "current": current, "candidate": None, "status": "held-local-patch",
            "reason": CODEX_ADAPTER_REASON, "adapter_status": "adapter-needed",
            "upstream_latest": selected, "checked_at": now.isoformat(),
            "next_review": (now.date() + dt.timedelta(days=1)).isoformat(),
            "source_files": list(CODEX_BUNDLE),
            "evidence": {"discovery_api": endpoint, "selected_version": selected,
                         "upstream_newer": version_key(selected) > version_key(current["version"]),
                         "verification": "Official CLI package metadata; no source/asset/patch rebase verification",
                         "payload_downloads": 0}}


def nix_fields(data):
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DiscoveryError("Nix source is not UTF-8") from error
    # Fail closed on aliases/duplicates; a trusted baseline still needs one
    # exact literal assignment for each field the adapter can replace.
    versions = list(re.finditer(r'(?m)^  version = "([^"\n]+)";$', text))
    hashes = list(re.finditer(r'(?m)^    hash = "([^"\n]+)";$', text))
    if (len(versions) != 1 or len(hashes) != 1
            or len(re.findall(r"\bversion\s*=", text)) != 1
            or len(re.findall(r"\bhash\s*=", text)) != 1):
        raise DiscoveryError("Expected unique exact literal version and src.hash assignments")
    return text, versions[0], hashes[0]


def read_pin(lane, data):
    lane_name(lane)
    if lane == "codex":
        return read_codex_source_pin(data)
    if lane == "t3":
        return validate_pin(lane, object_json(data))
    text, version, hash_field = nix_fields(data)
    template = {
        "codex": 'url = "https://registry.npmjs.org/@openai/codex/-/codex-${finalAttrs.version}-linux-x64.tgz";',
        "chatgpt": 'url = "https://persistent.oaistatic.com/codex-app-prod/linux/rpm/x86_64/chatgpt-${finalAttrs.version}-1.x86_64.rpm";',
    }[lane]
    if text.count(template) != 1:
        raise DiscoveryError("Unexpected source URL template")
    return validate_pin(lane, {"version": version.group(1), "url": pin_url(lane, version.group(1)), "hash": hash_field.group(1)})


def replace_pin(lane, old_bytes, pin):
    if lane == "codex":
        raise DiscoveryError(CODEX_ADAPTER_REASON)
    read_pin(lane, old_bytes)
    pin = validate_pin(lane, pin)
    if lane == "t3":
        return (json.dumps(pin, indent=2) + "\n").encode()
    text, version, hash_field = nix_fields(old_bytes)
    for start, end, replacement in sorted([
        (*version.span(1), pin["version"]),
        (*hash_field.span(1), pin["hash"]),
    ], reverse=True):
        text = text[:start] + replacement + text[end:]
    return text.encode()


def validate_transition(lane, before_bytes, after_bytes, network=True):
    if lane == "codex":
        raise DiscoveryError(CODEX_ADAPTER_REASON)
    old, new = read_pin(lane, before_bytes), read_pin(lane, after_bytes)
    if lane != "t3" and replace_pin(lane, before_bytes, new) != after_bytes:
        raise DiscoveryError("Transition modifies code outside version and src.hash")
    if version_key(new["version"]) <= version_key(old["version"]):
        raise DiscoveryError("Transition must be a version upgrade; no downgrade or same-version replacement")
    if network:
        exact, _ = verify_exact(lane, new["version"], Network(lane))
        if new != exact:
            raise DiscoveryError("Candidate pin does not match the exact published official artifact")
    return {"old": old, "new": new}


def learning_suffix(candidate_id, lane, old_version, new_version):
    lane_name(lane)
    version_key(old_version)
    version_key(new_version)
    if not isinstance(candidate_id, str) or not re.fullmatch(r"[0-9]{8}[A-Za-z0-9._-]{1,120}", candidate_id):
        raise DiscoveryError("Candidate ID must start with a date and contain only safe identifier characters")
    try:
        date = dt.datetime.strptime(candidate_id[:8], "%Y%m%d").date().isoformat()
    except ValueError as error:
        raise DiscoveryError("Candidate ID date invalid") from error
    return (f"\n\n### {date} (daily update candidate {candidate_id})\n\n"
            f"- Change: Prepare {lane} {old_version} -> {new_version} with exact official source metadata.\n"
            "- Verification: Candidate package and laptop builds plus required isolated functional gates passed; preserve their receipts.\n"
            f"- Activation: Pending independent submit verification; authoritative result is in /var/lib/weasel-updates/runs/{candidate_id}/journal.json.\n").encode("utf-8")


def safe_url(lane, url):
    try:
        parsed = urllib.parse.urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS[lane]
                or parsed.port not in {None, 443} or parsed.username or parsed.password or parsed.fragment):
            raise DiscoveryError("Network URL outside the lane's official HTTPS hosts")
    except ValueError as error:
        raise DiscoveryError("Malformed network URL") from error
    return url


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, lane):
        self.lane = lane
        super().__init__()

    def redirect_request(self, request, response, code, message, headers, new_url):
        safe_url(self.lane, new_url)
        return super().redirect_request(request, response, code, message, headers, new_url)


class Network:
    def __init__(self, lane, budget_seconds=300):
        self.lane = lane_name(lane)
        self.deadline = time.monotonic() + budget_seconds
        self.opener = urllib.request.build_opener(OfficialRedirect(lane))

    def open(self, url, headers=None):
        safe_url(self.lane, url)
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise DiscoveryError("Discovery network time budget exceeded")
        request = urllib.request.Request(url, headers={"User-Agent": "weasel-os-update-discovery/1", "Accept-Encoding": "identity", **(headers or {})})
        try:
            response = self.opener.open(request, timeout=min(45, remaining))
        except Exception as error:
            raise DiscoveryError(f"Official source request failed: {type(error).__name__}") from error
        safe_url(self.lane, response.geturl())
        if response.status not in {200, 206}:
            response.close()
            raise DiscoveryError("Unexpected official source HTTP status")
        return response

    def block(self, response, limit):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise DiscoveryError("Discovery network time budget exceeded")
        raw = getattr(getattr(response, "fp", None), "raw", None)
        socket = getattr(raw, "_sock", None)
        if socket is not None:
            socket.settimeout(min(45, remaining))
        try:
            return response.read1(limit)
        except (OSError, ValueError) as error:
            raise DiscoveryError("Official source bounded read failed") from error

    def read(self, url, limit=MAX_JSON, prefix=False):
        headers = {"Range": f"bytes=0-{limit-1}"} if prefix else {}
        with self.open(url, headers) as response:
            length = response.headers.get("Content-Length")
            if not prefix and length and int(length) > limit:
                raise DiscoveryError("Metadata exceeds the configured byte limit")
            maximum = limit if prefix else limit + 1
            chunks = bytearray()
            while len(chunks) < maximum:
                chunk = self.block(response, min(65536, maximum - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
            if not prefix and len(chunks) > limit:
                raise DiscoveryError("Metadata exceeds the configured byte limit")
        return bytes(chunks)

    def json(self, url):
        return object_json(self.read(url))

    def artifact(self, url, integrity=None, size=None):
        sha256, sha512 = hashlib.sha256(), hashlib.sha512()
        count = 0
        with self.open(url) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > MAX_ASSET:
                raise DiscoveryError("Artifact exceeds the configured byte limit")
            head = bytearray()
            while True:
                if time.monotonic() > self.deadline:
                    raise DiscoveryError("Discovery network time budget exceeded")
                chunk = self.block(response, 1024 * 1024)
                if not chunk:
                    break
                count += len(chunk)
                if count > MAX_ASSET:
                    raise DiscoveryError("Artifact exceeds the configured byte limit")
                sha256.update(chunk)
                sha512.update(chunk)
                if len(head) < MAX_RPM_HEADER:
                    head.extend(chunk[:MAX_RPM_HEADER-len(head)])
        if not count or (size is not None and count != size):
            raise DiscoveryError("Artifact empty or published byte size mismatch")
        if integrity is not None:
            if integrity != "sha512-" + base64.b64encode(sha512.digest()).decode():
                raise DiscoveryError("Published SHA-512 integrity verification failed")
        return {"hash": sri(sha256.digest()), "bytes": count, "prefix": bytes(head)}


def published_time(value):
    if not isinstance(value, str):
        raise DiscoveryError("Release lacks a published timestamp")
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DiscoveryError("Malformed release published timestamp") from error
    if stamp.tzinfo is None or stamp > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
        raise DiscoveryError("Release publish timestamp is invalid/future")
    return value


def t3_release_pin(release, version, net):
    if not isinstance(release, dict) or release.get("tag_name") != "v" + version or release.get("draft") is not False:
        raise DiscoveryError("Unexpected T3 release tag or draft")
    nightly = "-nightly." in version
    if release.get("prerelease") is not nightly:
        raise DiscoveryError("T3 channel and official prerelease flag disagree")
    if nightly and re.search(r"maintainer|preview", release.get("name") or "", re.I):
        raise DiscoveryError("Maintainer previews are not the regular nightly channel")
    published = published_time(release.get("published_at"))
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise DiscoveryError("T3 release assets missing")
    filename = f"T3-Code-{version}-x86_64.AppImage"
    apps = [a for a in assets if isinstance(a, dict) and a.get("name") == filename]
    sums = [a for a in assets if isinstance(a, dict) and a.get("name") == "SHA256SUMS"]
    if len(apps) != 1 or len(sums) != 1:
        raise DiscoveryError("T3 requires one architecture asset and checksum manifest")
    asset = apps[0]
    url = pin_url("t3", version)
    sums_url = f"{T3_ASSETS}/v{version}/SHA256SUMS"
    if asset.get("browser_download_url") != url or sums[0].get("browser_download_url") != sums_url:
        raise DiscoveryError("T3 asset URL tampered or unexpected")
    digest = asset.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise DiscoveryError("T3 asset lacks published SHA-256 digest")
    size = asset.get("size")
    if type(size) is not int or not 0 < size <= MAX_ASSET:
        raise DiscoveryError("T3 asset size invalid")
    matches = []
    try:
        manifest = net.read(sums_url, limit=1024 * 1024).decode("ascii")
    except UnicodeDecodeError as error:
        raise DiscoveryError("T3 checksum manifest is not ASCII") from error
    for line in manifest.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
        if match and match.group(2) == filename:
            matches.append(match.group(1))
    electron_evidence = {}
    if matches:
        if matches != [digest[7:]]:
            raise DiscoveryError("T3 SHA256SUMS does not uniquely match published asset digest")
    else:
        # Current regular nightlies publish SHA256SUMS for CLI archives only.
        # Verify every manifest entry against its published asset digest and
        # require the separate official Electron desktop SHA512+size manifest.
        seen = set()
        for line in manifest.splitlines():
            if not line:
                continue
            entry = re.fullmatch(r"([0-9a-f]{64}) [ *](.+)", line)
            if not entry or not entry.group(2).startswith(f"t3-{version}-") or entry.group(2) in seen:
                raise DiscoveryError("Unexpected CLI-only T3 checksum manifest")
            seen.add(entry.group(2))
            listed = [a for a in assets if isinstance(a, dict) and a.get("name") == entry.group(2)]
            if len(listed) != 1 or listed[0].get("digest") != "sha256:" + entry.group(1):
                raise DiscoveryError("CLI checksum manifest disagrees with published assets")
        if not seen:
            raise DiscoveryError("Empty T3 checksum manifest")
        electron_name = "nightly-linux.yml" if nightly else "latest-linux.yml"
        electron_assets = [a for a in assets if isinstance(a, dict) and a.get("name") == electron_name]
        electron_url = f"{T3_ASSETS}/v{version}/{electron_name}"
        if len(electron_assets) != 1 or electron_assets[0].get("browser_download_url") != electron_url:
            raise DiscoveryError("Missing official desktop checksum manifest")
        electron_integrity = electron_checksum(net.read(electron_url, limit=1024*1024), version, filename, size)
        electron_evidence = {"checksum_manifest_scope": "CLI-only", "desktop_checksum_manifest": electron_url, "electron_sha512": electron_integrity}
    pin = {"version": version, "url": url, "hash": sri(bytes.fromhex(digest[7:]))}
    return pin, {"release_api": f"{T3_API}/releases/tags/v{version}", "checksum_manifest": sums_url, "published_at": published, "published_size": size, "published_digest": digest, "channel": "regular-nightly" if nightly else "stable", **electron_evidence}


def electron_checksum(data, version, filename, size):
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as error:
        raise DiscoveryError("Desktop checksum manifest is not ASCII") from error
    if len(text) > 65536 or any(token in text for token in ["!!", "&", "<<:"]):
        raise DiscoveryError("Unexpected desktop manifest format")
    if re.findall(r"(?m)^version: ([^\n]+)$", text) != [version] or re.findall(r"(?m)^path: ([^\n]+)$", text) != [filename]:
        raise DiscoveryError("Desktop manifest version or architecture path mismatch")
    entries = re.findall(r"(?m)^  - url: ([^\n]+)\n((?:    [^\n]+\n)*)", text)
    found = [body for name, body in entries if name == filename]
    if len(found) != 1:
        raise DiscoveryError("Desktop manifest AppImage must be unique")
    hashes = re.findall(r"(?m)^    sha512: ([A-Za-z0-9+/]{86}==)$", found[0])
    sizes = re.findall(r"(?m)^    size: ([0-9]+)$", found[0])
    if len(hashes) != 1 or sizes != [str(size)] or re.findall(r"(?m)^sha512: ([^\n]+)$", text) != hashes:
        raise DiscoveryError("Desktop manifest hash or size mismatch")
    return "sha512-" + hashes[0]


def npm_exact_metadata(version, net):
    endpoint = f"{NPM_METADATA}/{version}-linux-x64"
    metadata = net.json(endpoint)
    if (not isinstance(metadata, dict) or metadata.get("name") != "@openai/codex"
            or metadata.get("version") != version + "-linux-x64"):
        raise DiscoveryError("Unexpected npm package name/platform version")
    distribution = metadata.get("dist", {})
    if not isinstance(distribution, dict) or distribution.get("tarball") != pin_url("codex", version):
        raise DiscoveryError("npm tarball URL outside the official platform package")
    integrity = distribution.get("integrity")
    if not isinstance(integrity, str) or not re.fullmatch(r"sha512-[A-Za-z0-9+/]{86}==", integrity):
        raise DiscoveryError("npm platform tarball requires SHA-512 integrity")
    return distribution, endpoint


def rpm_metadata(data):
    if len(data) < 112 or data[:4] != b"\xed\xab\xee\xdb":
        raise DiscoveryError("Official ChatGPT artifact is not an RPM")

    def header(offset, identity=True):
        if offset + 16 > len(data) or data[offset:offset+8] != b"\x8e\xad\xe8\x01\x00\x00\x00\x00":
            raise DiscoveryError("RPM header invalid/truncated")
        count, size = struct.unpack_from(">II", data, offset + 8)
        if count > 65536 or size > MAX_RPM_HEADER:
            raise DiscoveryError("RPM header exceeds bounds")
        start = offset + 16 + count * 16
        end = start + size
        if end > len(data):
            raise DiscoveryError("RPM header exceeds bounded metadata prefix")
        fields = {}
        for index in range(count):
            tag, typ, pos, number = struct.unpack_from(">IIII", data, offset + 16 + index * 16)
            if not identity or tag not in {1000, 1001, 1002, 1022}:
                continue
            if tag in fields or typ != 6 or number != 1 or pos >= size:
                raise DiscoveryError("RPM identity field is malformed/duplicated")
            stop = data.find(b"\0", start + pos, end)
            if stop == -1 or stop - start - pos > 128:
                raise DiscoveryError("RPM identity string invalid")
            try:
                fields[tag] = data[start+pos:stop].decode("ascii")
            except UnicodeDecodeError as error:
                raise DiscoveryError("RPM identity must be ASCII") from error
        return end, fields

    signature_end, _ = header(96, identity=False)
    _, fields = header((signature_end + 7) & ~7)
    if fields.get(1000) != "chatgpt" or fields.get(1002) != "1" or fields.get(1022) != "x86_64":
        raise DiscoveryError("RPM is not official ChatGPT release 1 for x86_64")
    version = fields.get(1001)
    version_key(version)
    if "-" in version:
        raise DiscoveryError("Unexpected ChatGPT prerelease RPM")
    return {"name": "chatgpt", "version": version, "release": "1", "arch": "x86_64"}


def verify_exact(lane, version, net):
    if lane == "codex":
        raise DiscoveryError(CODEX_ADAPTER_REASON)
    url = pin_url(lane, version)
    if lane == "t3":
        release = net.json(f"{T3_API}/releases/tags/v{version}")
        pin, evidence = t3_release_pin(release, version, net)
        artifact = net.artifact(pin["url"], integrity=evidence.get("electron_sha512"), size=evidence["published_size"])
        if artifact["hash"] != pin["hash"]:
            raise DiscoveryError("T3 exact downloaded artifact disagrees with published SHA-256")
        evidence.update(downloaded_bytes=artifact["bytes"], payload_sha256_verified=True)
        return pin, evidence
    if lane == "codex":
        distribution, endpoint = npm_exact_metadata(version, net)
        artifact = net.artifact(url, integrity=distribution["integrity"])
        return {"version": version, "url": url, "hash": artifact["hash"]}, {"package_api": endpoint, "npm_integrity": distribution["integrity"], "downloaded_bytes": artifact["bytes"], "payload_sha256_verified": True}
    artifact = net.artifact(url)
    metadata = rpm_metadata(artifact["prefix"])
    if metadata["version"] != version:
        raise DiscoveryError("Versioned RPM identity disagrees with its URL")
    return {"version": version, "url": url, "hash": artifact["hash"]}, {"rpm_identity": metadata, "versioned_url": url, "downloaded_bytes": artifact["bytes"], "payload_sha256_verified": True}


def discover(lane, current, channel=None, net=None):
    if lane == "codex":
        if channel not in (None, "stable"):
            raise DiscoveryError("Unsupported Codex channel")
        return held_codex_source_discovery(current, net or Network(lane))
    current = validate_pin(lane, current)
    net = net or Network(lane)
    evidence = {}
    if lane == "t3":
        channel = channel or "nightly"
        if channel not in {"nightly", "stable"}:
            raise DiscoveryError("Unsupported T3 channel")
        endpoint = f"{T3_API}/releases?per_page=50"
        releases = net.json(endpoint)
        if not isinstance(releases, list):
            raise DiscoveryError("T3 release list is malformed")
        matches = []
        for release in releases:
            if not isinstance(release, dict) or release.get("draft") is not False:
                continue
            tag = release.get("tag_name", "")
            if not isinstance(tag, str) or not tag.startswith("v"):
                continue
            version = tag[1:]
            try:
                version_key(version)
            except DiscoveryError:
                continue
            nightly = "-nightly." in version
            if nightly != (channel == "nightly") or release.get("prerelease") is not nightly:
                continue
            if nightly and re.search(r"maintainer|preview", release.get("name") or "", re.I):
                continue
            published_time(release.get("published_at"))
            matches.append((version_key(version), version, release))
        if not matches:
            raise DiscoveryError("No published matching T3 channel release within bounded catalog")
        _, selected, release = max(matches, key=lambda x: x[0])
        pin, evidence = t3_release_pin(release, selected, net)
        evidence["discovery_api"] = endpoint
        if version_key(selected) > version_key(current["version"]):
            artifact = net.artifact(pin["url"], integrity=evidence.get("electron_sha512"), size=evidence["published_size"])
            if artifact["hash"] != pin["hash"]:
                raise DiscoveryError("T3 downloaded bytes disagree with official digest")
            evidence.update(downloaded_bytes=artifact["bytes"], payload_sha256_verified=True)
        elif selected == current["version"] and pin != current:
            raise DiscoveryError("Same-version T3 release source changed")
    elif lane == "codex":
        metadata = net.json(f"{NPM_METADATA}/latest")
        if not isinstance(metadata, dict) or metadata.get("name") != "@openai/codex":
            raise DiscoveryError("Unexpected npm latest package identity")
        selected = metadata.get("version")
        pin_url(lane, selected)
        evidence = {"discovery_api": f"{NPM_METADATA}/latest", "selected_version": selected}
        if version_key(selected) > version_key(current["version"]):
            pin, exact_evidence = verify_exact(lane, selected, net)
            evidence.update(exact_evidence)
        else:
            pin = current
            evidence["verification"] = "Latest identity checked; unchanged payload not redownloaded"
    else:
        identity = rpm_metadata(net.read(RPM_LATEST, limit=MAX_RPM_HEADER, prefix=True))
        selected = identity["version"]
        evidence = {"discovery_url": RPM_LATEST, "latest_rpm_identity": identity}
        if version_key(selected) > version_key(current["version"]):
            pin, exact_evidence = verify_exact(lane, selected, net)
            evidence.update(exact_evidence)
        else:
            pin = current
            evidence["verification"] = "Latest RPM identity checked; unchanged payload not redownloaded"
    comparison = version_key(selected) > version_key(current["version"])
    older = version_key(selected) < version_key(current["version"])
    return {"schema_version": SCHEMA_VERSION, "lane": lane, "channel": channel or "stable", "current": current, "candidate": pin if comparison else None, "evidence": evidence, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "status": "candidate" if comparison else "held-prerelease" if older and lane == "t3" and "-" in current["version"] else "upstream-older" if older else "unchanged", "source_files": [SOURCE_FILES[lane]]}


def private_output(path, payload):
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise DiscoveryError("Output already exists; refusing to overwrite")
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lane", choices=sorted(SOURCE_FILES), required=True)
    parser.add_argument("--repository", type=Path, default=Path("/home/evilweasel/weasel-os"))
    parser.add_argument("--channel", choices=["nightly", "stable"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.channel and args.lane != "t3":
        parser.error("--channel only applies to T3")
    try:
        source = args.repository / SOURCE_FILES[args.lane]
        if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_JSON:
            raise DiscoveryError("Source pin must be a bounded regular file")
        bundle = codex_source_bundle(args.repository) if args.lane == "codex" else None
        result = discover(args.lane, read_pin(args.lane, source.read_bytes()), args.channel)
        if bundle is not None:
            result["source_bundle"] = bundle
        private_output(args.output, result)
        print(json.dumps({"status": result["status"], "lane": args.lane, "output": str(args.output)}, sort_keys=True))
    except (DiscoveryError, OSError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
