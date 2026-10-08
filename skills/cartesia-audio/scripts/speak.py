#!/usr/bin/env python3
"""Generate on-demand speech without exposing credentials or requiring an SDK."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request


API = "https://api.cartesia.ai"
CONFIG = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "cartesia-audio/config.json"
DEFAULTS = {
    "api_version": "2026-08-14",
    "model_id": "sonic-3.6-2026-08-27",
    "language": "de",
    "emotion": "calm",
    "speed": 1.0,
    "voice_id": None,
    "secret_ref": None,
    "secret_file": str(Path.home() / ".config/companion-secrets/cartesia-api-key"),
}
EMOTIONS = {"neutral", "calm", "angry", "content", "sad", "scared"}


class AudioError(Exception):
    pass


def settings():
    result = DEFAULTS.copy()
    if CONFIG.exists():
        result.update(json.loads(CONFIG.read_text()))
    return result


def save_settings(changes):
    current = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    current.update(changes)
    CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", dir=CONFIG.parent, delete=False) as handle:
        temporary = Path(handle.name)
        json.dump(current, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temporary.replace(CONFIG)


def credential_source(config):
    inherited = os.environ.get("CARTESIA_API_KEY", "")
    if inherited and not inherited.startswith("pass://"):
        return "environment"
    if config.get("secret_ref") or inherited.startswith("pass://"):
        return "proton-pass"
    if config.get("secret_file") and Path(config["secret_file"]).is_file():
        return "local-file"
    return "missing"


def api_key(config):
    source = credential_source(config)
    if source == "environment":
        key = os.environ["CARTESIA_API_KEY"].strip()
    elif source == "proton-pass":
        if os.environ.get("CARTESIA_AUDIO_VAULT_CHILD"):
            raise AudioError("Proton Pass did not resolve the configured secret reference.")
        executable = shutil.which("pass-cli")
        if not executable:
            raise AudioError("pass-cli is unavailable; install the declarative Proton Pass CLI package.")
        environment = os.environ.copy()
        environment.update(
            CARTESIA_API_KEY=config.get("secret_ref") or environment["CARTESIA_API_KEY"],
            PROTON_PASS_LINUX_KEYRING="dbus",
            CARTESIA_AUDIO_VAULT_CHILD="1",
        )
        # Proton resolves the key in the child environment and masks output.
        # Never fall back to another credential after a configured vault fails.
        result = subprocess.run(
            [executable, "run", "--", sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
            env=environment,
            check=False,
        )
        raise SystemExit(result.returncode)
    elif source == "local-file":
        path = Path(config["secret_file"])
        info = path.stat()
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise AudioError("The configured credential file must be owned by this user and private (0600).")
        key = path.read_text().strip()
    else:
        raise AudioError("No Cartesia credential configured. Use configure --secret-ref with a Proton Pass reference.")
    if not key or "\n" in key or "\r" in key:
        raise AudioError("The configured Cartesia credential is empty or malformed.")
    return key


def request(config, key, path, payload=None):
    headers = {
        "Authorization": "Bearer " + key,
        "Cartesia-Version": config["api_version"],
        "User-Agent": "weasel-cartesia-audio/1",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(API + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        # Provider bodies can echo request data. Report status only, never keys.
        advice = {
            400: "Check the model, voice, transcript and API schema.",
            401: "The credential was rejected.",
            402: "The account requires credits; do not purchase automatically.",
            403: "The credential or account lacks permission.",
            429: "Rate or account limit reached; do not retry paid generation blindly.",
        }.get(error.code, "The request failed; no automatic paid retry was made.")
        raise AudioError(f"Cartesia HTTP {error.code}. {advice}") from None
    except (urllib.error.URLError, TimeoutError):
        raise AudioError("Cartesia network request failed. No automatic retry was made; a generation may already have started.") from None


def json_request(config, key, path):
    body, _ = request(config, key, path)
    return json.loads(body)


def voices(config, key):
    found = []
    cursor = None
    for _ in range(20):
        query = {"language": config["language"], "limit": 100}
        if cursor:
            query["starting_after"] = cursor
        page = json_request(config, key, "/voices?" + urllib.parse.urlencode(query))
        data = page.get("data", [])
        found.extend(data)
        if not page.get("has_more"):
            return found
        next_cursor = page.get("next_page") or (data[-1]["id"] if data else None)
        if not next_cursor or next_cursor == cursor:
            raise AudioError("Voice pagination did not advance.")
        cursor = next_cursor
    raise AudioError("Voice list exceeded the pagination limit.")


def choose_voice(config, key):
    if config.get("voice_id"):
        return json_request(config, key, "/voices/" + urllib.parse.quote(config["voice_id"], safe=""))
    available = [voice for voice in voices(config, key) if voice.get("status", "ready") not in {"pending", "failed", "deleted"}]
    if not available:
        raise AudioError("No accessible voice matches the configured language.")

    def preference(voice):
        native = any(accent.get("is_native") and accent.get("locale", "").startswith(config["language"] + "-") for accent in voice.get("accents", []))
        return (not native, bool(voice.get("is_pro")), voice.get("name", ""), voice["id"])

    selected = min(available, key=preference)
    save_settings({"voice_id": selected["id"]})
    return selected


def split_text(text, limit=3500):
    # Prefer complete sentences so separate generations retain natural prosody.
    sentences = re.split(r"(?<=[.!?])\s+|\n\s*\n", text)
    tokens = []
    for sentence in sentences:
        if len(sentence) <= limit:
            tokens.append(sentence)
        else:
            # Keep control tags intact even for unusually long sentences.
            tokens.extend(re.findall(r"<[^>]+>|[^\s<>]+", sentence))
    chunks, current = [], ""
    for token in tokens:
        if len(token) > limit:
            raise AudioError("One transcript token exceeds the request limit; rewrite it for speech.")
        candidate = current + (" " if current else "") + token
        if len(candidate) > limit:
            chunks.append(current)
            current = token
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def prepare_t3_audio_root(root):
    # Keep project-local speech and transcripts private and out of Git. The
    # ignore file ignores itself too; never replace a user's existing rules.
    root.parent.mkdir(exist_ok=True, mode=0o700)
    root.mkdir(exist_ok=True, mode=0o700)
    try:
        descriptor = os.open(root / ".gitignore", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return
    with os.fdopen(descriptor, "w") as handle:
        handle.write("*\n")


def render(args, config, key):
    text = args.input.read_text().strip()
    if not text or len(text) > 20000:
        raise AudioError("Use a nonempty speech script of at most 20,000 characters; never silently truncate it.")
    if "```" in text or re.search(r"\[[^]]+\]\(\S+\)", text):
        raise AudioError("Rewrite Markdown links and code blocks into speech before rendering.")
    emotion = args.emotion or config["emotion"]
    if emotion not in EMOTIONS:
        raise AudioError("Choose one documented primary emotion: " + ", ".join(sorted(EMOTIONS)))
    speed = args.speed if args.speed is not None else config["speed"]
    if not 0.6 <= speed <= 1.5:
        raise AudioError("Speed must be between 0.6 and 1.5.")
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        raise AudioError("ffmpeg and ffprobe are required for validation and joining speech segments.")
    stamp = dt.datetime.now().astimezone().strftime("%Y-%m-%d/%H%M%S-%f")
    t3_client = os.environ.get("WEASEL_T3_CLIENT") == "1"
    root = Path.cwd() / ".t3-artifacts/audio" if t3_client else Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "cartesia-audio/outputs"
    output = args.output.expanduser().absolute() if args.output else (root / (stamp + "-antwort.mp3")).absolute()
    if output.suffix.lower() != ".mp3":
        raise AudioError("The output path must end in .mp3.")
    sidecars = [output.with_suffix(".txt"), output.with_suffix(".json")]
    if any(path.exists() for path in [output, *sidecars]):
        raise AudioError("An output or sidecar already exists; refusing to overwrite it.")
    if t3_client and not args.output:
        prepare_t3_audio_root(root)
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    chunks = split_text(text)
    voice = choose_voice(config, key)
    with tempfile.TemporaryDirectory(prefix="cartesia-audio-", dir=output.parent) as temporary:
        folder = Path(temporary)
        parts = []
        for index, chunk in enumerate(chunks):
            payload = {
                "model_id": config["model_id"],
                "transcript": chunk,
                "voice": voice["id"],
                "language": config["language"],
                "output_format": {"container": "mp3", "sample_rate": 44100, "bit_rate": 128000},
                # Always send the user's emotion preference. German emotion
                # control is experimental: the provider documents English only.
                "generation_config": {"emotion": emotion, "speed": speed, "volume": 1.0},
            }
            body, mime = request(config, key, "/tts/bytes", payload)
            if not body or "json" in mime:
                raise AudioError("Cartesia did not return audio bytes.")
            part = folder / f"{index:04d}.mp3"
            part.write_bytes(body)
            parts.append(part)
        candidate = folder / "complete.mp3"
        if len(parts) == 1:
            shutil.copyfile(parts[0], candidate)
        else:
            playlist = folder / "parts.txt"
            playlist.write_text("".join(f"file '{part.name}'\n" for part in parts))
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "1", "-i", str(playlist), "-c", "copy", str(candidate)], check=True)
        inspected = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_name,sample_rate", "-of", "json", str(candidate)], capture_output=True, text=True, check=True)
        audio = json.loads(inspected.stdout)
        duration = float(audio.get("format", {}).get("duration", 0))
        if duration <= 0 or not any(stream.get("codec_name") == "mp3" for stream in audio.get("streams", [])):
            raise AudioError("Generated file failed MP3/duration validation.")
        candidate.replace(output)
    transcript = output.with_suffix(".txt")
    transcript.write_text(text + "\n")
    metadata = {
        "audio_path": str(output), "transcript_path": str(transcript),
        "duration_seconds": round(duration, 2), "characters": len(text), "requests": len(chunks),
        "voice_id": voice["id"], "voice_name": voice.get("name"),
        "model_id": config["model_id"], "language": config["language"],
        "emotion": emotion, "emotion_support": "documented" if config["language"] == "en" else "experimental-outside-English",
        "client": "t3code" if t3_client else "codex",
    }
    if t3_client:
        try:
            metadata["preview_path"] = output.relative_to(Path.cwd()).as_posix()
        except ValueError:
            # An explicit output can be outside the workspace. Preserve that
            # request without pretending it has a project-relative preview.
            metadata["preview_path"] = None
    output.with_suffix(".json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(metadata, ensure_ascii=False))


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Report local dependencies and credential source without reading the key")
    sub.add_parser("voices", help="List accessible voices without synthesizing speech")
    configure = sub.add_parser("configure", help="Save nonsecret preferences; never pass an API key here")
    configure.add_argument("--voice")
    configure.add_argument("--secret-ref")
    render_parser = sub.add_parser("render", help="Generate an MP3 from an audio-ready script")
    render_parser.add_argument("--input", required=True, type=Path)
    render_parser.add_argument("--output", type=Path)
    render_parser.add_argument("--emotion", choices=sorted(EMOTIONS))
    render_parser.add_argument("--speed", type=float)
    args = parser.parse_args()
    config = settings()
    if args.command == "doctor":
        print(json.dumps({"credential_source": credential_source(config), "pass_cli": bool(shutil.which("pass-cli")), "ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe")), "voice_configured": bool(config.get("voice_id")), "model_id": config["model_id"], "language": config["language"]}))
        return
    if args.command == "configure":
        changes = {}
        if args.voice:
            changes["voice_id"] = args.voice
        if args.secret_ref:
            if not re.fullmatch(r"pass://[^/\s]+/[^/\s]+/[^/\s]+", args.secret_ref):
                raise AudioError("Use a pass://ShareID/ItemID/Field reference, never a literal API key.")
            changes["secret_ref"] = args.secret_ref
        if not changes:
            raise AudioError("Provide --voice or --secret-ref.")
        save_settings(changes)
        print(json.dumps({"configured": list(changes)}))
        return
    key = api_key(config)
    if args.command == "voices":
        print(json.dumps([{field: voice.get(field) for field in ["id", "name", "gender", "accents", "is_pro", "status"]} for voice in voices(config, key)], ensure_ascii=False))
    else:
        render(args, config, key)


if __name__ == "__main__":
    try:
        main()
    except (AudioError, OSError, ValueError, subprocess.CalledProcessError) as error:
        message = str(error) if isinstance(error, AudioError) else "Local audio preparation or validation failed. Check the input and configuration; no secret was printed."
        print(message, file=sys.stderr)
        raise SystemExit(1)
