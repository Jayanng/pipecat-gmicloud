#
# Copyright (c) 2026, Jayanng
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""GMI Cloud text-to-speech service implementations.

This module provides a Pipecat TTS integration for GMI Cloud's multimodal
inference engine (https://www.gmicloud.ai). GMI Cloud hosts production
text-to-speech models behind a single request-queue API, including:

- ``inworld-tts-2`` / ``inworld-tts-2-flash``: Inworld Realtime TTS-2 with
  282 voices across 200+ languages and locales, optimized for real-time use.
- ``minimax-tts-speech-2.8-turbo`` / ``minimax-tts-speech-2.8-hd``: MiniMax
  speech synthesis with real-time response.
- ``Chatterbox-tts``: Resemble AI's Chatterbox model.

Any GMI Cloud audio model id can be used through the ``model`` setting.

Verified against the live GMI Cloud API on 2026-11-17.
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


@dataclass
class GmicloudTTSSettings(TTSSettings):
    """Settings for :class:`GmicloudTTSService`.

    Parameters:
        speed: Speech speed multiplier (mapped to the API's ``speaking_rate``).
            Defaults to 1.0.
        temperature: Randomness of the synthesis. Left to the model's own
            default when unset.
        sample_rate_hertz: Output sample rate in Hz sent to the API.
            Defaults to 48000.
        audio_encoding: Output audio container sent to the API. The service
            expects a PCM-bearing container (``WAV`` by default) so it can
            stream raw audio frames into the Pipecat pipeline.
        timestamp_type: Optional alignment metadata request (for example
            ``WORD``). Supported by some models only; when set, alignment data
            is returned in the API response but is not surfaced as frames in
            this version.
    """

    speed: float | NotGiven = field(default_factory=lambda: NOT_GIVEN)
    temperature: float | None | NotGiven = field(default_factory=lambda: NOT_GIVEN)
    sample_rate_hertz: int = field(default=48000)
    audio_encoding: str = field(default="WAV")
    timestamp_type: str | None | NotGiven = field(default_factory=lambda: NOT_GIVEN)


class GmicloudTTSService(TTSService):
    """GMI Cloud text-to-speech service.

    Synthesizes speech through GMI Cloud's request-queue API
    (``POST /api/v1/ie/requestqueue/apikey/requests``). For speech models the
    queue responds synchronously with a status and an audio URL, which the
    service downloads and streams into the pipeline as raw audio frames.

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
            settings: Runtime-updatable settings.
            **kwargs: Additional arguments passed to the parent TTSService.
        """
        default_settings = self.Settings(
            model="inworld-tts-2",
            voice="Dennis",
            language=Language.EN,
            speed=1.0,
            temperature=None,
            sample_rate_hertz=48000,
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

    def can_generate_metrics(self) -> bool:
        """This service supports TTFB and TTS usage metrics."""
        return True

    def _build_payload(self, text: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "text": text,
            "audio_encoding": self._settings.audio_encoding,
            "sample_rate_hertz": self._settings.sample_rate_hertz,
            "speaking_rate": self._settings.speed,
        }
        if self._settings.voice:
            payload["voice_id"] = self._settings.voice
        if self._settings.temperature is not None:
            payload["temperature"] = self._settings.temperature
        if self._settings.timestamp_type is not None:
            payload["timestamp_type"] = self._settings.timestamp_type
        return payload

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame | None, None]:
        """Generate speech from text using GMI Cloud.

        Args:
            text: The text to convert to speech.
            context_id: Unique identifier for this TTS context.

        Yields:
            Frame: Audio frames containing the synthesized speech, or an
                ``ErrorFrame`` when the request fails.
        """
        url = f"{self._base_url}/api/v1/ie/requestqueue/apikey/requests"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        body = {"model": self._settings.model, "payload": self._build_payload(text)}

        try:
            async with self._session.post(url, json=body, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    yield ErrorFrame(
                        error=f"GMI Cloud API error: HTTP {response.status} - {error_text}"
                    )
                    return

                data = await response.json()
                request_id = data.get("request_id")
                status = data.get("status")
                outcome = data.get("outcome") or {}
                audio_url = outcome.get("audio_url")
                if not audio_url:
                    media = outcome.get("media") or []
                    if media:
                        audio_url = media[0].get("url")

                if status != "success" or not audio_url:
                    yield ErrorFrame(
                        error=(
                            f"GMI Cloud TTS failed: status={status!r}, "
                            f"request_id={request_id!r}"
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
