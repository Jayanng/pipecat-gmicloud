#
# Copyright (c) 2026, Jayanng
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Pipeline tests for GmicloudHttpTTSService.

These run the service through pipecat's own test harness (``run_test``), with a
local fake of GMI Cloud's request-queue API, in the style of pipecat's own
service tests (e.g. ``tests/test_bland_tts.py``). They assert the full frame
contract a pipeline depends on: started/stopped frames, error propagation, the
per-family request shapes, queued-response polling, and WAV header stripping.
"""

import struct

import aiohttp
import pytest
from aiohttp import web

from pipecat.frames.frames import (
    ErrorFrame,
    TTSAudioRawFrame,
    TTSSpeakFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.tests.utils import run_test

from pipecat_gmicloud import GmicloudHttpTTSService

QUEUE_PATH = "/api/v1/ie/requestqueue/apikey/requests"


def _wav(rate: int = 48000, channels: int = 1, num_samples: int = 4096) -> bytes:
    """Minimal PCM16 WAV with a correct 44-byte header."""
    data = struct.pack(
        f"<{num_samples * channels}h",
        *(((i * 97) % 2000) - 1000 for i in range(num_samples * channels)),
    )
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * channels * 2, channels * 2, 16)
        + b"data"
        + struct.pack("<I", len(data))
    )
    return header + data


def _audio_of(frames) -> bytes:
    return b"".join(f.audio for f in frames if isinstance(f, TTSAudioRawFrame))


async def _serve(captured: dict, queue_response: dict, *, wav: bytes | None = None,
                 poll_response: dict | None = None) -> tuple[str, object]:
    """Fake GMI queue endpoint (plus an audio host path) on one local app."""
    if wav is None:
        wav = _wav()

    async def queue_handler(request):
        captured["auth"] = request.headers.get("Authorization")
        captured["bodies"] = captured.get("bodies", []) + [await request.json()]
        return web.json_response(queue_response)

    async def poll_handler(request):
        captured["polls"] = captured.get("polls", 0) + 1
        return web.json_response(poll_response)

    async def audio_handler(request):
        return web.Response(body=wav, content_type="audio/wav")

    app = web.Application()
    app.router.add_post(QUEUE_PATH, queue_handler)
    app.router.add_get(f"{QUEUE_PATH}/{{request_id}}", poll_handler)
    app.router.add_get("/audio.wav", audio_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return f"http://127.0.0.1:{port}", runner


@pytest.mark.asyncio
async def test_inworld_sync_success_streamed_and_stripped():
    """Inworld family: sync response, WAV header stripped, frames contract kept."""
    captured = {}
    queue = {
        "request_id": "r-1",
        "model": "inworld-tts-2",
        "status": "success",
        "outcome": {"audio_url": "AUDIO"},
    }
    base, runner = await _serve(captured, queue)
    try:
        queue["outcome"]["audio_url"] = f"{base}/audio.wav"
        async with aiohttp.ClientSession() as session:
            tts = GmicloudHttpTTSService(
                api_key="test-key",
                aiohttp_session=session,
                url=base,
                settings=GmicloudHttpTTSService.Settings(model="inworld-tts-2", voice="Dennis"),
            )
            down_frames, up_frames = await run_test(tts, frames_to_send=[TTSSpeakFrame(text="Hello.")])

        frame_types = [type(f) for f in down_frames]
        assert TTSStartedFrame in frame_types
        assert TTSStoppedFrame in frame_types
        assert not any(isinstance(f, ErrorFrame) for f in down_frames + up_frames)

        assert captured["auth"] == "Bearer test-key"
        body = captured["bodies"][0]
        assert body["model"] == "inworld-tts-2"
        payload = body["payload"]
        assert payload["voice_id"] == "Dennis"
        assert payload["audio_encoding"] == "WAV"
        assert payload["speaking_rate"] == 1.0
        # No sample-rate request: the base resamples to the pipeline rate.
        assert "sample_rate_hertz" not in payload
        assert captured.get("polls", 0) == 0  # sync path, no polling

        audio = _audio_of(down_frames)
        assert audio
        assert not audio.startswith(b"RIFF")  # WAV header stripped for the pipeline
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_minimax_queued_response_is_polled():
    """MiniMax family: 'dispatched' response resolves by polling to success."""
    captured = {}
    queue = {"request_id": "r-2", "model": "minimax-tts-speech-2.8-turbo", "status": "dispatched"}
    poll = {
        "request_id": "r-2",
        "model": "minimax-tts-speech-2.8-turbo",
        "status": "success",
        "outcome": {"audio_url": "AUDIO"},
    }
    base, runner = await _serve(captured, queue, poll_response=poll, wav=_wav(rate=32000, channels=1))
    try:
        poll["outcome"]["audio_url"] = f"{base}/audio.wav"
        async with aiohttp.ClientSession() as session:
            tts = GmicloudHttpTTSService(
                api_key="test-key",
                aiohttp_session=session,
                url=base,
                poll_interval_secs=0.01,
                settings=GmicloudHttpTTSService.Settings(
                    model="minimax-tts-speech-2.8-turbo", extra_payload={"emotion": "auto"}
                ),
            )
            down_frames, up_frames = await run_test(tts, frames_to_send=[TTSSpeakFrame(text="Hello.")])

        frame_types = [type(f) for f in down_frames]
        assert TTSStartedFrame in frame_types
        assert TTSStoppedFrame in frame_types
        assert not any(isinstance(f, ErrorFrame) for f in down_frames + up_frames)

        payload = captured["bodies"][0]["payload"]
        assert payload["voice_id"] == "English_expressive_narrator"
        assert payload["format"] == "wav"
        assert payload["speed"] == "1.0"
        assert payload["emotion"] == "auto"  # extra_payload passthrough
        assert "audio_sample_rate" not in payload
        assert captured["polls"] >= 1  # queued path polled at least once

        assert _audio_of(down_frames)
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_failed_generation_yields_error_frame():
    """A failed queue response surfaces as an ErrorFrame, not a crash."""
    captured = {}
    queue = {"request_id": "r-3", "model": "inworld-tts-2", "status": "failed"}
    base, runner = await _serve(captured, queue)
    try:
        async with aiohttp.ClientSession() as session:
            tts = GmicloudHttpTTSService(
                api_key="test-key",
                aiohttp_session=session,
                url=base,
                poll_interval_secs=0.01,
            )
            down_frames, up_frames = await run_test(tts, frames_to_send=[TTSSpeakFrame(text="Hello.")])

        # Pipecat reports errors to both directions (upstream to the pipeline
        # and downstream to the transcript track), so one logical failure
        # surfaces twice; the context adds its own "completed with no audio"
        # error as well. Assert the turn error text on the deduplicated set.
        errors = [f for f in down_frames + up_frames if isinstance(f, ErrorFrame)]
        turn_errors = [f for f in errors if "completed with no audio" not in f.error]
        assert turn_errors, "expected a turn error"
        assert all("status='failed'" in f.error for f in turn_errors)
        assert not _audio_of(down_frames)
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_chatterbox_without_voice_uuid_is_rejected():
    """Chatterbox requires a Resemble voice UUID; missing voice yields ErrorFrame."""
    captured = {}
    queue = {"request_id": "r-4", "model": "Chatterbox-tts", "status": "success", "outcome": {}}
    base, runner = await _serve(captured, queue)
    try:
        async with aiohttp.ClientSession() as session:
            tts = GmicloudHttpTTSService(
                api_key="test-key",
                aiohttp_session=session,
                url=base,
                settings=GmicloudHttpTTSService.Settings(model="Chatterbox-tts"),
            )
            down_frames, up_frames = await run_test(tts, frames_to_send=[TTSSpeakFrame(text="Hello.")])

        errors = [f for f in down_frames + up_frames if isinstance(f, ErrorFrame)]
        assert any("Resemble voice UUID" in f.error for f in errors), [f.error for f in errors]
        assert captured.get("bodies", []) == []  # request never sent
    finally:
        await runner.cleanup()
