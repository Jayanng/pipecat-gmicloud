#
# Copyright (c) 2026, Jayanng
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Live verification harness for GmicloudTTSService.

Runs the adapter end to end against the live GMI Cloud API and writes the
synthesized speech to a WAV file. Requires the GMI_CLOUD_API_KEY environment
variable.

Usage:

    $ uv pip install -e .
    $ GMI_CLOUD_API_KEY=... python scripts/verify_live.py
"""

import asyncio
import os
import sys
import wave

import aiohttp

from pipecat.frames.frames import ErrorFrame, TTSAudioRawFrame

from pipecat_gmicloud import GmicloudTTSService


async def main() -> int:
    api_key = os.environ["GMI_CLOUD_API_KEY"]
    text = (
        "Live verification for the pipecat GMI Cloud integration. "
        "This audio was synthesized by the Gmicloud TTS service."
    )
    out_path = sys.argv[1] if len(sys.argv) > 1 else "verify_live.wav"

    async with aiohttp.ClientSession() as session:
        tts = GmicloudTTSService(
            api_key=api_key,
            aiohttp_session=session,
            settings=GmicloudTTSService.Settings(
                model="inworld-tts-2",
                voice="Dennis",
            ),
        )

        sample_rate = None
        channels = None
        chunks: list[bytes] = []

        async for frame in tts.run_tts(text, "verify-context"):
            if isinstance(frame, ErrorFrame):
                print(f"ERROR: {frame.error}")
                return 1
            if isinstance(frame, TTSAudioRawFrame):
                if sample_rate is None:
                    sample_rate = frame.sample_rate
                    channels = frame.num_channels
                chunks.append(frame.audio)

        if not chunks:
            print("ERROR: no audio frames produced")
            return 1

        audio = b"".join(chunks)
        with wave.open(out_path, "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(2)  # PCM16
            wav.setframerate(sample_rate)
            wav.writeframes(audio)

        print(f"OK: {len(chunks)} frames, {len(audio)} PCM bytes")
        print(f"OK: sample_rate={sample_rate} channels={channels}")
        print(f"OK: wrote {out_path}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
