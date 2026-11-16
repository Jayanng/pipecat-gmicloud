# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-11-17

### Added

- `GmicloudTTSService`: Pipecat TTS service for GMI Cloud's inference engine
  (`POST /api/v1/ie/requestqueue/apikey/requests`).
- Automatic request-family mapping: Inworld (`voice_id`/`speaking_rate`),
  MiniMax (`voice_id`/`speed`/`format`/`audio_sample_rate`), Chatterbox
  (`voice_uuid`/`data`/`output_format`), plus `extra_payload` passthrough.
- Synchronous and queued responses (`queued`/`dispatched` resolved by polling
  `GET .../requests/{request_id}`).
- All 17 catalog TTS models covered: Inworld (4), MiniMax (10),
  Chatterbox (1), ElevenLabs catalog entries (2).
- Settings: model, voice, language, speed (speaking rate), temperature,
  sample rate (Hz), audio encoding, timestamp type, extra payload.
- Usage metrics (TTFB and TTS usage) wired to Pipecat's metrics framework.
- Foundational example: `examples/say-one-thing-gmicloud.py`.
- Live verification tooling: `scripts/probe_all_models.py` (17-model sweep)
  and `scripts/verify_live.py` (service-class runs). Verified against the
  live GMI Cloud API on 2026-11-17: 14 of 17 models produced audio
  (Inworld 4/4, MiniMax 10/10; Chatterbox needs a Resemble voice UUID;
  2 ElevenLabs entries are catalog `available: false`).
