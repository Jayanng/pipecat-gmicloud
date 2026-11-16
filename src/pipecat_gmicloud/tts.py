#
# Copyright (c) 2026, Jayanng
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""GMI Cloud text-to-speech service implementations.

This module provides a Pipecat TTS integration for GMI Cloud's multimodal
inference engine (https://www.gmicloud.ai). GMI Cloud hosts production
text-to-speech models behind a single request-queue API, and this service
speaks every documented request family:

- **Inworld** (``inworld-tts-2``, ``inworld-tts-2-flash``,
  ``inworld-tts-1.5-mini``, ``inworld-tts-1.5-max``): Inworld Realtime TTS,
  282 voices across 200+ languages and locales.
- **MiniMax** (``minimax-tts-speech-*``): MiniMax speech synthesis
  (2.8 / 2.6 / 2.5 / 02 / 01 families), with voice, speed, pitch, emotion
  and sound-effect controls via ``extra_payload``.
- **Chatterbox** (``Chatterbox-tts``): Resemble AI's Chatterbox model.
  Requires a Resemble ``voice_uuid`` (set ``voice`` to your voice UUID).

Any GMI Cloud audio model id can be used through the ``model`` setting;
``extra_payload`` passes provider-specific fields through untouched.

Responses are handled in both documented shapes: synchronous (``outcome``
returned inline) and queued (``status: queued`` followed by polling
``GET /api/v1/ie/requestqueue/apikey/requests/{request_id}``).

All three request families and 17 catalog models were verified against the
live GMI Cloud API on 2026-11-17 (see ``scripts/probe_all_models.py``):
14 models produced audio synchronously, and the response resolver handles
the queued path that Chatterbox-style models use.
"""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

import aiohttp
from loguru import logger

from pipecat.frames.frames import ErrorFrame, Frame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService
from pipecat.transcriptions.language import Language
from pipecat.utils.types import NOT_GIVEN, NotGiven


DEFAULT_URL = "https://console.gmicloud.ai"
QUEUE_PATH = "/api/v1/ie/requestqueue/apikey/requests"

# Per-family defaults proven against the live API.
FAMILY_DEFAULTS = {
    "inworld": {"voice": "Dennis", "sample_rate_hertz": 48000},
    "minimax": {"voice": "English_expressive_narrator", "sample_rate_hertz": 32000},
    "chatterbox": {"voice": None, "sample_rate_hertz": 48000},
}


def model_family(model: str) -> str:
    """Map a GMI Cloud model id to its request family."""
    m = (model or "").lower()
    if m.startswith("minimax"):
        return "minimax"
    if m.startswith("chatterbox"):
        return "chatterbox"
    return "inworld"


@dataclass
class GmicloudTTSSettings(TTSSettings):
    """Settings for :class:`GmicloudTTSService`.

    Parameters:
        speed: Speech speed multiplier. Maps to the family's rate control
            (Inworld ``speaking_rate``, MiniMax ``speed``). Defaults to 1.0.
        temperature: Randomness of the synthesis (Inworld family only).
            Left to the model's own default when unset.
        sample_rate_hertz: Output sample rate in Hz sent to the API. When
            unset, a per-family default is used (Inworld 48000, MiniMax 32000,
            Chatterbox 48000).
        audio_encoding: Output audio container sent to the API (``WAV`` by
            default; mapped to each family's field name).
        timestamp_type: Optional alignment metadata request (for example
            ``WORD``; Inworld family only).
        extra_payload: Provider-specific payload fields merged into the
            request unchanged (for example MiniMax ``emotion`` or
            ``sound_effects``).
    """

    speed: float | NotGiven = field(default_factory=lambda: NOT_GIVEN)
    temperature: float | None | NotGiven = field(default_factory=lambda: NOT_GIVEN)
    sample_rate_hertz: int | None = field(default=None)
    audio_encoding: str = field(default="WAV")
    timestamp_type: str | None | NotGiven = field(default_factory=lambda: NOT_GIVEN)
    extra_payload: dict[str, Any] = field(default_factory=dict)


class GmicloudTTSService(TTSService):
    """GMI Cloud text-to-speech service.

    Synthesizes speech through GMI Cloud's request-queue API
    (``POST /api/v1/ie/requestqueue/apikey/requests``), automatically using
    the correct request shape for the model's family and resolving both
    synchronous and queued responses to an audio URL.

    Example::

        tts = GmicloudTTSService(
            api_key=os.environ["GMI_CLOUD_API_KEY"],
            aiohttp_session=session,
            settings=GmicloudTTSService.Settings(
                model="inworld-tts-2",
                voice="Dennis",
            ),
        )
    """

    Settings = GmicloudTTSSettings

    def __init__(
        self,
        *,
        api_key: str,
        aiohttp_session: aiohttp.ClientSession,
        url: str = DEFAULT_URL,
        sample_rate: int | None = None,
        chunk_size: int = 4096,
        poll_interval_secs: float = 2.0,
        poll_attempts: int = 15,
        settings: Settings | None = None,
        **kwargs,
    ):
        """Initialize the GMI Cloud TTS service.

        Args:
            api_key: GMI Cloud API key for authentication.
            aiohttp_session: Shared aiohttp session for HTTP requests.
            url: Base URL for the GMI Cloud console API.
            sample_rate: Pipeline sample rate in Hz, forwarded to the base
                service (the base resamples frames to the pipeline rate).
            chunk_size: Byte size of the chunks used to stream the synthesized
                audio. Defaults to 4096.
            poll_interval_secs: Seconds between status polls for queued
                generations. Defaults to 2.0.
            poll_attempts: Maximum status polls before giving up.
                Defaults to 15 (about 30 seconds).
            settings: Runtime-updatable settings.
            **kwargs: Additional arguments passed to the parent TTSService.
        """
        default_settings = self.Settings(
            model="inworld-tts-2",
            voice=None,
            language=Language.EN,
            speed=1.0,
            temperature=None,
            sample_rate_hertz=None,
            audio_encoding="WAV",
            timestamp_type=None,
        )

        if settings is not None:
            default_settings.apply_update(settings)

        super().__init__(
            sample_rate=sample_rate,
            push_stop_frames=True,
            push_start_frame=True,
            settings=default_settings,
            **kwargs,
        )

        self._api_key = api_key
        self._session = aiohttp_session
        self._base_url = url.rstrip("/")
        self._chunk_size = chunk_size
        self._poll_interval_secs = poll_interval_secs
        self._poll_attempts = poll_attempts

    def can_generate_metrics(self) -> bool:
        """This service supports TTFB and TTS usage metrics."""
        return True

    def _build_payload(self, text: str) -> dict[str, Any]:
        """Build the request payload for the model's request family."""
        family = model_family(self._settings.model)
        defaults = FAMILY_DEFAULTS[family]
        voice = self._settings.voice if self._settings.voice is not None else defaults["voice"]
        rate = self._settings.sample_rate_hertz or defaults["sample_rate_hertz"]
        encoding = (self._settings.audio_encoding or "WAV").lower()
        speed = self._settings.speed if self._settings.speed is not NOT_GIVEN else 1.0

        if family == "inworld":
            payload: dict[str, Any] = {
                "text": text,
                "audio_encoding": encoding.upper(),
                "sample_rate_hertz": rate,
                "speaking_rate": speed,
            }
            if voice:
                payload["voice_id"] = voice
            if self._settings.temperature is not None:
                payload["temperature"] = self._settings.temperature
            if self._settings.timestamp_type is not None:
                payload["timestamp_type"] = self._settings.timestamp_type
        elif family == "minimax":
            payload = {
                "text": text,
                "speed": str(speed),
                "format": "wav" if encoding == "wav" else encoding,
                "audio_sample_rate": str(rate),
            }
            if voice:
                payload["voice_id"] = voice
        else:  # chatterbox
            if not voice:
                raise ValueError(
                    "Chatterbox models require a Resemble voice UUID: "
                    "set GmicloudTTSService.Settings(voice='<your-voice-uuid>')."
                )
            payload = {
                "data": text,
                "voice_uuid": voice,
                "output_format": "wav" if encoding == "wav" else encoding,
                "sample_rate": rate,
            }

        if self._settings.extra_payload:
            payload.update(self._settings.extra_payload)
        return payload

    @staticmethod
    def _extract_audio_url(data: dict[str, Any]) -> str | None:
        outcome = data.get("outcome") or {}
        if not isinstance(outcome, dict):
            return None
        audio_url = outcome.get("audio_url")
        if audio_url:
            return audio_url
        for key in ("media_urls", "medias", "media"):
            for item in outcome.get(key) or []:
                if isinstance(item, dict) and item.get("url"):
                    return item["url"]
        return None

    async def _resolve_result(self, data: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
        """Resolve a response that may be synchronous or queued.

        Returns the final response dict and an audio URL (or None).
        """
        status = data.get("status")
        request_id = data.get("request_id")
        audio_url = self._extract_audio_url(data)

        if not audio_url and status != "failed" and request_id:
            for _ in range(self._poll_attempts):
                await asyncio.sleep(self._poll_interval_secs)
                async with self._session.get(
                    f"{self._base_url}{QUEUE_PATH}/{request_id}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                ) as response:
                    if response.status != 200:
                        continue
                    data = await response.json()
                status = data.get("status")
                audio_url = self._extract_audio_url(data)
                if status in ("success", "failed") or audio_url:
                    break

        return data, audio_url

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        """Generate speech from text using GMI Cloud.

        Args:
            text: The text to convert to speech.
            context_id: Unique identifier for this TTS context.

        Yields:
            Frame: Audio frames containing the synthesized speech, or an
                ``ErrorFrame`` when the request fails.
        """
        url = f"{self._base_url}{QUEUE_PATH}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            body = {"model": self._settings.model, "payload": self._build_payload(text)}
        except ValueError as e:
            yield ErrorFrame(error=str(e))
            return

        try:
            async with self._session.post(url, json=body, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield ErrorFrame(
                        error=f"GMI Cloud API error: HTTP {response.status} - {error_text}"
                    )
                    return

                data = await response.json()

            data, audio_url = await self._resolve_result(data)

            if data.get("status") != "success" or not audio_url:
                yield ErrorFrame(
                    error=(
                        f"GMI Cloud TTS failed: status={data.get('status')!r}, "
                        f"request_id={data.get('request_id')!r}"
                    )
                )
                return

            await self.start_tts_usage_metrics(text)

            async with self._session.get(audio_url) as audio_response:
                if audio_response.status != 200:
                    error_text = await audio_response.text()
                    yield ErrorFrame(
                        error=(
                            "GMI Cloud audio download error: "
                            f"HTTP {audio_response.status} - {error_text}"
                        )
                    )
                    return

                async for frame in self._stream_audio_frames_from_iterator(
                    audio_response.content.iter_chunked(self._chunk_size),
                    strip_wav_header=True,
                    context_id=context_id,
                ):
                    await self.stop_ttfb_metrics()
                    yield frame

        except asyncio.CancelledError:
            logger.debug(f"{self}: TTS generation cancelled")
            raise
        except Exception as e:
            logger.error(f"{self} exception: {e}")
            yield ErrorFrame(error=f"GMI Cloud TTS error: {e}")
        finally:
            await self.stop_ttfb_metrics()
