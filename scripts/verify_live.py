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

    $ GMI_CLOUD_API_KEY=... python scripts/verify_live.py [output.wav] [model] [voice]

Examples:

    $ python scripts/verify_live.py verify_live.wav
    $ python scripts/verify_live.py minimax.wav minimax-tts-speech-2.8-turbo
    $ python scripts/verify_live.py inworld.wav inworld-tts-2-flash
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
    out_path = sys.argv[1] if len(sys.argv) > 1 else "verify_live.wav"
    model = sys.argv[2] if len(sys.argv) > 2 else "inworld-tts-2"
    voice = sys.argv[3] if len(sys.argv) > 3 else None

    text = (
        "Live verification for the pipecat GMI Cloud integration. "
        "This audio was synthesized by the Gmicloud TTS service."
    )

    settings_kwargs = {"model": model}
    if voice:
        settings_kwargs["voice"] = voice

    async with aiohttp.ClientSession() as session:
        tts = GmicloudTTSService(
            api_key=api_key,
            aiohttp_session=session,
            settings=GmicloudTTSService.Settings(**settings_kwargs),
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

        print(f"OK [{model}]: {len(chunks)} frames, {len(audio)} PCM bytes")
        print(f"OK: sample_rate={sample_rate} channels={channels}")
        print(f"OK: wrote {out_path}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
