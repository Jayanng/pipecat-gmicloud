# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-11-17

### Added

- `GmicloudTTSService`: Pipecat TTS service for GMI Cloud's inference engine
  (`POST /api/v1/ie/requestqueue/apikey/requests`).
- Model presets work out of the box: `inworld-tts-2`, `inworld-tts-2-flash`,
  `minimax-tts-speech-2.8-turbo`, `minimax-tts-speech-2.8-hd`,
  `Chatterbox-tts`; any GMI audio model id can be passed via settings.
- Settings: model, voice, language, speed (speaking rate), temperature,
  sample rate (Hz), audio encoding, timestamp type.
- Usage metrics (TTFB and TTS usage) wired to Pipecat's metrics framework.
- Foundational example: `examples/say-one-thing-gmicloud.py`.
- Verified against the live GMI Cloud API on 2026-11-17
  (`inworld-tts-2`, voice "Dennis", WAV/48 kHz; request id
  `9c50e662-c180-4335-b6de-6e1300d5a2f2`).
