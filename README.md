# pipecat-gmicloud

A [Pipecat](https://github.com/pipecat-ai/pipecat) text-to-speech service for
[GMI Cloud](https://www.gmicloud.ai)'s multimodal inference engine. Community-maintained
by [@Jayanng](https://github.com/Jayanng).

One service, every TTS model in GMI Cloud's catalog: Inworld Realtime TTS,
MiniMax speech synthesis and Resemble AI's Chatterbox, behind a single
request-queue API. The adapter speaks each model family's request shape and
resolves both synchronous and queued responses.

**Every model below was called live on 2026-11-17 before release** (see
[Live verification](#live-verification)).

## Models

| Model id | Family | What it is | Live check |
|---|---|---|---|
| `inworld-tts-2` | Inworld | Flagship Realtime TTS-2: 282 voices, 200+ languages and locales | ✅ 2.86 s audio |
| `inworld-tts-2-flash` | Inworld | Same voices and languages, ~2.5x lower latency | ✅ 3.56 s |
| `inworld-tts-1.5-mini` | Inworld | Fast TTS with phoneme timing and visemes for lip-sync | ✅ 2.98 s |
| `inworld-tts-1.5-max` | Inworld | Best quality of the 1.5 family, visemes included | ✅ 3.00 s |
| `minimax-tts-speech-2.8-turbo` | MiniMax | Latest turbo, real-time response, intelligent parsing | ✅ 3.27 s |
| `minimax-tts-speech-2.8-hd` | MiniMax | Latest HD, real-time response | ✅ 3.11 s |
| `minimax-tts-speech-2.6-turbo` | MiniMax | Turbo generation | ✅ 2.98 s |
| `minimax-tts-speech-2.6-hd` | MiniMax | HD generation | ✅ 3.07 s |
| `minimax-tts-speech-2.5-hd-preview` | MiniMax | Emotional voice control, HD preview | ✅ 3.02 s |
| `minimax-tts-speech-2.5-turbo-preview` | MiniMax | Emotional voice control, turbo preview | ✅ 3.02 s |
| `minimax-tts-speech-02-hd` | MiniMax | HD generation | ✅ 3.19 s |
| `minimax-tts-speech-02-turbo` | MiniMax | Turbo generation | ✅ 2.89 s |
| `minimax-tts-speech-01-hd` | MiniMax | HD generation | ✅ 2.60 s |
| `minimax-tts-speech-01-turbo` | MiniMax | Turbo generation | ✅ 2.73 s |
| `Chatterbox-tts` | Chatterbox | Resemble AI's premier TTS | ⚠️ needs a Resemble `voice_uuid` |
| `elevenlabs-tts-v3` | ElevenLabs | 70+ languages, expressive | ⛔ catalog `available: false` (HTTP 404) |
| `elevenlabs-tts-multilingual-v2` | ElevenLabs | Multilingual with voice cloning | ⛔ catalog `available: false` (HTTP 404) |

**14 of 17 produced real audio live.** Chatterbox works when you pass your own
Resemble voice UUID (`settings.voice`); the two ElevenLabs entries are listed
in GMI's catalog but not serving today. Any GMI audio model id works through
the `model` setting.

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

Switching models is one setting:

```python
settings=GmicloudTTSService.Settings(
    model="minimax-tts-speech-2.8-turbo",   # MiniMax request shape applied automatically
    extra_payload={"emotion": "auto"},       # provider-specific fields pass through
)
```

### Settings

| Setting | Default | Description |
|---|---|---|
| `model` | `inworld-tts-2` | Any GMI Cloud audio model id |
| `voice` | per family | Inworld: `Dennis` (282 voices, e.g. `Alex`, `Luna`, `Sarah`); MiniMax: `English_expressive_narrator`; Chatterbox: your Resemble `voice_uuid` (required) |
| `language` | `Language.EN` | Language hint (voices define the spoken language) |
| `speed` | `1.0` | Speaking-rate multiplier (maps to each family's rate field) |
| `temperature` | model default | Randomness (Inworld family only) |
| `sample_rate_hertz` | per family | Output sample rate (Inworld/Chatterbox 48000, MiniMax 32000) |
| `audio_encoding` | `WAV` | Output container; PCM-bearing formats stream into Pipecat |
| `timestamp_type` | unset | Optional alignment request, e.g. `WORD` (Inworld family only) |
| `extra_payload` | `{}` | Provider-specific fields merged into the request unchanged |

### Request families

GMI Cloud models do not share one request shape, and this service maps them
automatically:

- **Inworld**: `voice_id`, `audio_encoding`, `sample_rate_hertz`, `speaking_rate`, `temperature`, `timestamp_type`
- **MiniMax**: `voice_id`, `speed`, `format`, `audio_sample_rate`, plus `emotion`, `pitch`, `sound_effects` via `extra_payload`
- **Chatterbox**: `voice_uuid`, `data`, `output_format`, `sample_rate`

Responses may arrive synchronously (`outcome` inline) or as `queued` /
`dispatched` (polled via `GET /api/v1/ie/requestqueue/apikey/requests/{request_id}`);
the service resolves both.

## Running the example

`examples/say-one-thing-gmicloud.py` speaks one sentence through GMI Cloud,
using the standard Pipecat runner and transports:

```bash
uv pip install pipecat-gmicloud
GMI_CLOUD_API_KEY=... uv run python examples/say-one-thing-gmicloud.py
```

## Live verification

Everything in the table above was called against the live GMI Cloud API on
2026-11-17 (`scripts/probe_all_models.py` reproduces the sweep: 17 models,
one real request each, audio downloaded and measured). The service class
itself was then run end to end (`scripts/verify_live.py`):

```bash
GMI_CLOUD_API_KEY=... python scripts/verify_live.py out.wav inworld-tts-2
GMI_CLOUD_API_KEY=... python scripts/verify_live.py out.wav minimax-tts-speech-2.8-turbo
```

Results: `inworld-tts-2` 7.08 s PCM at 48 kHz, `inworld-tts-2-flash` 7.70 s
at 48 kHz, `minimax-tts-speech-2.8-turbo` 18.62 s at 32 kHz (queued response
resolved by polling).

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
