#
# Copyright (c) 2026, Jayanng
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Say one thing with GMI Cloud text-to-speech.

The foundational example for pipecat-gmicloud: a minimal Pipecat pipeline
that speaks a single sentence through GMI Cloud's inference engine.

Requires the GMI_CLOUD_API_KEY environment variable.

Usage:

    $ uv pip install pipecat-gmicloud
    $ GMI_CLOUD_API_KEY=... uv run python examples/say-one-thing-gmicloud.py
"""

import os

from dotenv import load_dotenv
from loguru import logger

from pipecat.frames.frames import EndFrame, TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineWorker, ProcessorUnusablePolicy
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.transports.livekit.transport import LiveKitParams
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

from pipecat_gmicloud import GmicloudTTSService

load_dotenv(override=True)


# We use lambdas to defer transport parameter creation until the transport
# type is selected at runtime.
transport_params = {
    "daily": lambda: DailyParams(audio_out_enabled=True),
    "livekit": lambda: LiveKitParams(audio_out_enabled=True),
    "twilio": lambda: FastAPIWebsocketParams(audio_out_enabled=True),
    "webrtc": lambda: TransportParams(audio_out_enabled=True),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    logger.info("Starting bot")

    tts = GmicloudTTSService(
        api_key=os.environ["GMI_CLOUD_API_KEY"],
        aiohttp_session=transport.aiohttp_session(),
        settings=GmicloudTTSService.Settings(
            model="inworld-tts-2",
            voice="Dennis",
        ),
    )

    worker = PipelineWorker(
        Pipeline([tts, transport.output()]),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    await runner.add_workers(worker)

    # Register an event handler so we can play the audio when the client joins
    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        await worker.queue_frames(
            [TTSSpeakFrame("Hello from GMI Cloud, through pipecat!"), EndFrame()]
        )

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point compatible with Pipecat Cloud."""
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
