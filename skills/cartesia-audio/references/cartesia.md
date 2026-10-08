# Verified Cartesia interface

Verified against official documentation on 2026-10-07. Refresh these sources before changing API/model defaults.

- [Bytes API](https://docs.cartesia.ai/api-reference/tts/bytes): `POST https://api.cartesia.ai/tts/bytes`, `Authorization: Bearer KEY`, `Cartesia-Version: 2026-08-14`. Use a standard API key, not an admin key. Current `voice` is a UUID string or `{ "id": UUID }`, without the legacy `mode` field. Use `language: "de"` or `locale: "de-DE"`, never both.
- [Current stable model](https://docs.cartesia.ai/build-with-cartesia/tts-models/latest): `sonic-3.6` tracks stable; the helper pins `sonic-3.6-2026-08-27`. Prefer stable over beta models. German is supported.
- [Emotion and nonverbal controls](https://docs.cartesia.ai/build-with-cartesia/capability-guides/volume-speed-emotion): `generation_config.emotion`, `.speed` (0.6–1.5), `.volume` (0.5–2.0). Primary emotions: neutral, calm, angry, content, sad, scared. Emotion control is documented only for English; the user's German use is experimental. `[laughter]` is documented; do not guess other bracketed vocalizations.
- [SSML](https://docs.cartesia.ai/build-with-cartesia/capability-guides/ssml-tags): sparse `<break time="350ms"/>` pauses; `<spell>ABC123</spell>` for actual spelling. Avoid consecutive breaks. Inline emotion switching is experimental; separate requests are more reliable when switching emotions.
- [Voices](https://docs.cartesia.ai/api-reference/voices/list): `GET /voices?language=de&limit=100`, page with `starting_after`. Response has `data`, `has_more`, and optional `next_page`. Prefer native `de-DE` in `accents`, not the deprecated language/country fields. Validate a selected voice with `GET /voices/ID`. Voice listing uses no speech-generation credits.
- [Prompting](https://docs.cartesia.ai/build-with-cartesia/capability-guides/prompting-tips): use full natural phrases, normal punctuation and capitalization, and a voice matching the language.

MP3 payload fields: `output_format = { "container": "mp3", "sample_rate": 44100, "bit_rate": 128000 }`. Every render sends `generation_config`, including its selected emotion. API success proves audio bytes were returned, not perceptual emotion quality.
