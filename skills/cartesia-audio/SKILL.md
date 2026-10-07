---
name: cartesia-audio
description: Give requested answers or explanations as natural spoken audio using Cartesia, with emotion controls and an MP3 playable in chat. Use for requests such as "als Audio", "lies mir das vor", or "zu lang, bitte zum Anhören"; keep ordinary answers as text unless audio is requested.
---

# Cartesia Audio

Create audio on demand from the current answer or the answer the user references. If the user asks for audio because an answer is too long, default to a concise spoken adaptation that preserves decisions, qualifications, and actionable details. Preserve all substantive detail when they request a complete reading. Match the user's language; the local default is German.

## Prepare speech

Write a speech script before synthesis. Turn headings, tables, bullets and diagrams into connected spoken sentences. Explain commands and code in ordinary language; keep exact copyable code, URLs and citations in the written companion, not in the narration. Avoid Markdown, emoji, raw file paths, citation markers and reading URLs letter by letter. Use natural punctuation and a few deliberate `<break time="350ms"/>` pauses. Do not mechanically spell out every number.

Always choose and send an appropriate documented emotion: normally `calm` or `content`, with `sad`, `scared` or `angry` only when the content calls for it. The user explicitly wants emotion controls for German too: send them, but describe their German effect as experimental because Cartesia currently documents emotions only for English. Never claim a successful API call proves the emotion was audible. Use documented `[laughter]` only where laughter suits the message; do not insert laughter into serious content merely to satisfy "emotes". Do not invent `[sigh]`, `[chuckle]`, `[happy]` or tags from other providers.

## Generate and deliver

Use the bundled helper; it needs Python 3, ffmpeg and ffprobe, not a Cartesia SDK:

```bash
python3 /home/evilweasel/.codex/skills/cartesia-audio/scripts/speak.py doctor
python3 /home/evilweasel/.codex/skills/cartesia-audio/scripts/speak.py render --input /absolute/path/spoken-answer.txt --emotion calm
```

Find the current skill directory if this machine uses another home path. The helper selects and remembers an accessible native German voice when none is configured, chunks long scripts at sentence boundaries, includes emotion controls on every request, validates the MP3, and prints only nonsecret output metadata. Read [provider details](references/cartesia.md) when changing models, voices, controls or API behavior.

Prefer Proton Pass for credentials. Use `$proton-pass-cli` to log in and identify the exact Cartesia item, then save only a reference:

```bash
python3 /home/evilweasel/.codex/skills/cartesia-audio/scripts/speak.py configure --secret-ref 'pass://SHARE_ID/ITEM_ID/FIELD'
```

The helper resolves the reference through masked `pass-cli run`; the key stays in the child process environment. Never put a literal key in commands, chat, Git, Nix or output files. A configured Proton reference must fail closed if authentication fails. During initial migration the helper can read the pre-existing private local Cartesia credential file; `doctor` identifies this as `local-file`, and it must never be described as verified Proton access. That file belongs to an existing setup: read it only for the authorized Cartesia task, without starting any Companion processes.

For voice choice:

```bash
python3 /home/evilweasel/.codex/skills/cartesia-audio/scripts/speak.py voices
python3 /home/evilweasel/.codex/skills/cartesia-audio/scripts/speak.py configure --voice VOICE_UUID
```

Save outputs under the helper's durable local data directory by default. On successful rendering, use its absolute `audio_path` in the final answer:

```markdown
![Audioantwort](/absolute/path/antwort.mp3)

[MP3 herunterladen](/absolute/path/antwort.mp3)
```

Keep the written reply short: the player, duration, and any essential copyable commands or links. Link the saved transcript when useful. Do not repeat the entire long answer beside its audio unless requested. Never claim playback was heard or app rendering verified merely from ffprobe validation. Do not autoplay through desktop speakers.

Cartesia requests use the user's account credits. Audio requests authorize the needed synthesis; keep setup tests short, never buy credits, and avoid automatic paid retries after uncertain network failures. If generation fails, report the actual status and preserve the written answer rather than presenting a partial file as complete.
