# pipecat-gmicloud

A [Pipecat](https://github.com/pipecat-ai/pipecat) text-to-speech service for
[GMI Cloud](https://www.gmicloud.ai)'s multimodal inference engine. Community-maintained
by [@Jayanng](https://github.com/Jayanng), built and verified against the live GMI Cloud
API on 2026-11-17.

GMI Cloud hosts production text-to-speech models behind a single request-queue API:

| Model id | What it is |
|---|---|
| `inworld-tts-2` | Inworld Realtime TTS-2: 282 voices, 200+ languages and locales, built for real-time |
| `inworld-tts-2-flash` | Same voices and languages, ~2.5x lower latency |
| `minimax-tts-speech-2.8-turbo` / `-hd` | MiniMax speech synthesis, real-time response |
| `Chatterbox-tts` | Resemble AI's Chatterbox model |

Any GMI Cloud audio model id works through the `model` setting.

## Installation

```bash
uv pip install pipecat-gmicloud
```

Requires a GMI Cloud API key ([get one here](https://console.gmicloud.ai/)).

## Usage

```python
import os
import aiohttp

from pipecat_gmicloud import GmicloudTTSService

async with aiohttp.ClientSession() as session:
    tts = GmicloudTTSService(
        api_key=os.environ["GMI_CLOUD_API_KEY"],
        aiohttp_session=session,
        settings=GmicloudTTSService.Settings(
            model="inworld-tts-2",
            voice="Dennis",
        ),
    )
    # Drop into any Pipecat pipeline:
    # Pipeline([tts, transport.output()])
```

### Settings

| Setting | Default | Description |
|---|---|---|
| `model` | `inworld-tts-2` | Any GMI Cloud audio model id |
| `voice` | `Dennis` | Voice id (Inworld ships 282, e.g. `Alex`, `Luna`, `Sarah`) |
| `language` | `Language.EN` | Language hint (voices define the spoken language) |
| `speed` | `1.0` | Speaking-rate multiplier |
| `temperature` | model default | Randomness of the synthesis |
| `sample_rate_hertz` | `48000` | Output sample rate requested from the API |
| `audio_encoding` | `WAV` | Output container; PCM-bearing formats stream into Pipecat |
| `timestamp_type` | unset | Optional alignment request, e.g. `WORD` (model dependent) |

## Running the example

`examples/say-one-thing-gmicloud.py` speaks one sentence through GMI Cloud,
using the standard Pipecat runner and transports:

```bash
uv pip install pipecat-gmicloud
GMI_CLOUD_API_KEY=... uv run python examples/say-one-thing-gmicloud.py
```

## Live verification

This integration was run against the live GMI Cloud API before release:
`inworld-tts-2`, voice "Dennis", WAV at 48 kHz. The adapter produced 318
audio frames (7.36 s of PCM speech) from a single request
(`scripts/verify_live.py` reproduces the check):

```bash
GMI_CLOUD_API_KEY=... python scripts/verify_live.py verify_live.wav
```

## Pipecat compatibility

Tested with Pipecat v1.16.0 (`pipecat-ai`).

## Notes

- The service follows Pipecat's community integration patterns
  (`TTSService` / `TTSSettings`, `run_tts` audio streaming, TTFB and usage metrics).
- Attribution: this is a community-maintained integration. GMI Cloud is the
  service provider; this package is not maintained by the Pipecat team or by
  GMI Cloud.

## License

BSD-2-Clause, same spirit as Pipecat. See [LICENSE](LICENSE).
