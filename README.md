# pipecat-gmicloud

A [Pipecat](https://github.com/pipecat-ai/pipecat) text-to-speech service for
[GMI Cloud](https://www.gmicloud.ai)'s multimodal inference engine. Community-maintained
by [@Jayanng](https://github.com/Jayanng) (GMI Cloud Ambassador). This is not an
official GMI Cloud or Pipecat project.

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

**14 of 17 produced real audio live.** Chatterbox requires a Resemble voice
UUID (`settings.voice`): our live probe with a placeholder UUID was rejected
with HTTP 400, so a completed call needs your own Resemble voice. The two
ElevenLabs entries are listed in GMI's catalog but not serving today. Any GMI
audio model id works through the `model` setting.

## Installation

```bash
uv pip install pipecat-gmicloud
```

Requires a GMI Cloud API key ([get one here](https://console.gmicloud.ai/)).

## Usage

```python
import os
import aiohttp

from pipecat_gmicloud import GmicloudHttpTTSService

async with aiohttp.ClientSession() as session:
    tts = GmicloudHttpTTSService(
        api_key=os.environ["GMI_CLOUD_API_KEY"],
        aiohttp_session=session,
        settings=GmicloudHttpTTSService.Settings(
            model="inworld-tts-2",
            voice="Dennis",
        ),
    )
    # Drop into any Pipecat pipeline:
    # Pipeline([tts, transport.output()])
```

Switching models is one setting:

```python
settings=GmicloudHttpTTSService.Settings(
    model="minimax-tts-speech-2.8-turbo",   # MiniMax request shape applied automatically
    extra_payload={"emotion": "auto"},       # provider-specific fields pass through
)
```

### Constructor parameters

| Parameter | Default | Description |
|---|---|---|
| `api_key` | required | GMI Cloud API key |
| `aiohttp_session` | required | Shared `aiohttp.ClientSession` |
| `url` | `https://console.gmicloud.ai` | GMI Cloud console API base URL |
| `audio_format` | `WAV` | Output container requested from the API; PCM-bearing formats stream into Pipecat |
| `poll_interval_secs` | `2.0` | Seconds between status polls for queued generations |
| `poll_attempts` | `15` | Maximum status polls (~30 s) before giving up |

### Settings (runtime-updatable)

| Setting | Default | Description |
|---|---|---|
| `model` | `inworld-tts-2` | Any GMI Cloud audio model id |
| `voice` | per family | Inworld: `Dennis` (282 voices, e.g. `Alex`, `Luna`, `Sarah`); MiniMax: `English_expressive_narrator`; Chatterbox: your Resemble `voice_uuid` (required) |
| `language` | `Language.EN` | Language hint (voices define the spoken language) |
| `speed` | `1.0` | Speaking-rate multiplier (maps to each family's rate field) |
| `temperature` | model default | Randomness (Inworld family only) |
| `timestamp_type` | unset | Optional alignment request, e.g. `WORD` (Inworld family only) |
| `extra_payload` | `{}` | Provider-specific fields merged into the request unchanged |

### Request families

GMI Cloud models do not share one request shape, and this service maps them
automatically:

- **Inworld**: `voice_id`, `audio_encoding`, `speaking_rate`, `temperature`, `timestamp_type`
- **MiniMax**: `voice_id`, `speed`, `format`, plus `emotion`, `pitch`, `sound_effects` via `extra_payload`
- **Chatterbox**: `voice_uuid`, `data`, `output_format` (any other documented field, e.g. `sample_rate`, via `extra_payload`)

Responses may arrive synchronously (`outcome` inline) or as `queued` /
`dispatched` (polled via `GET /api/v1/ie/requestqueue/apikey/requests/{request_id}`);
the service resolves both.

### Output audio

The model's WAV response (mono or stereo at the model's native rate) is
streamed into Pipecat and resampled to the pipeline rate as it plays, so no
sample-rate configuration is required. Note that MiniMax ignores
`audio_sample_rate` request values (verified live: a 16000 request returned
32000 Hz audio).

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

Results (after the 2026-11-17 audit): `inworld-tts-2` 7.25 s PCM at 48 kHz
(mono), `minimax-tts-speech-2.8-turbo` 17.76 s at 32 kHz (mono, `dispatched`
response resolved by polling). Earlier runs: `inworld-tts-2-flash` 7.70 s at
48 kHz.

## Pipecat compatibility

Tested with Pipecat v1.16.0 (`pipecat-ai`).

## Notes

- The service follows Pipecat's community integration conventions
  (`TTSService` / `TTSSettings`, `@traced_tts`, `run_tts` audio streaming,
  `push_error` error reporting, TTFB and usage metrics).
- Attribution: this is a community-maintained integration by a GMI Cloud
  Ambassador. GMI Cloud is the service provider; this package is not
  maintained by the Pipecat team or by GMI Cloud.

## License

BSD-2-Clause, same spirit as Pipecat. See [LICENSE](LICENSE).
