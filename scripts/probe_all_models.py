#
# Copyright (c) 2026, Jayanng
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Live probe of every text-to-speech model in the GMI Cloud catalog.

Calls each TTS model once with its family's documented payload shape and
records the live result: sync vs queued response, audio URL, audio duration.

Usage:

    $ GMI_CLOUD_API_KEY=... python scripts/probe_all_models.py
"""

import asyncio
import json
import os
import re
import subprocess
import sys

import aiohttp

API = "https://console.gmicloud.ai/api/v1/ie/requestqueue/apikey/requests"
TEXT = "Live check from the pipecat GMI integration."

INWORLD = ["inworld-tts-2", "inworld-tts-2-flash", "inworld-tts-1.5-mini", "inworld-tts-1.5-max"]
MINIMAX = [
    "minimax-tts-speech-2.8-turbo", "minimax-tts-speech-2.8-hd",
    "minimax-tts-speech-2.6-turbo", "minimax-tts-speech-2.6-hd",
    "minimax-tts-speech-2.5-hd-preview", "minimax-tts-speech-2.5-turbo-preview",
    "minimax-tts-speech-02-hd", "minimax-tts-speech-02-turbo",
    "minimax-tts-speech-01-hd", "minimax-tts-speech-01-turbo",
]
CHATTERBOX = ["Chatterbox-tts"]
UNAVAILABLE = ["elevenlabs-tts-v3", "elevenlabs-tts-multilingual-v2"]


def payload_for(model: str) -> dict:
    if model in INWORLD:
        return {
            "text": TEXT,
            "voice_id": "Dennis",
            "audio_encoding": "WAV",
            "sample_rate_hertz": 48000,
            "speaking_rate": 1.0,
        }
    if model in MINIMAX:
        return {
            "text": TEXT,
            "voice_id": "English_expressive_narrator",
            "speed": "1",
            "vol": "1",
            "pitch": "0",
            "emotion": "auto",
            "language_boost": "auto",
            "format": "wav",
            "audio_sample_rate": "32000",
            "bitrate": "128000",
            "channel": "2",
        }
    if model in CHATTERBOX:
        return {
            "voice_uuid": "default",
            "data": TEXT,
            "output_format": "wav",
            "sample_rate": 48000,
        }
    return {"text": TEXT}


def ffprobe_duration(path: str) -> str:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout.strip() or "n/a"
    except Exception:
        return "n/a"


async def probe(session: aiohttp.ClientSession, key: str, model: str) -> dict:
    row = {"model": model}
    try:
        async with session.post(
            API,
            json={"model": model, "payload": payload_for(model)},
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        ) as r:
            body_text = await r.text()
            row["http"] = r.status
            try:
                data = json.loads(body_text)
            except Exception:
                row["error"] = body_text[:200]
                return row
        row["status"] = data.get("status")
        row["request_id"] = data.get("request_id")
        if row.get("status") not in (None, "success"):
            # queued/processing/failed: poll status endpoint
            for _ in range(12):
                await asyncio.sleep(5)
                async with session.get(
                    f"{API}/{row['request_id']}",
                    headers={"Authorization": f"Bearer {key}"},
                ) as pr:
                    pdata = await pr.json()
                row["status"] = pdata.get("status")
                data = pdata
                if row["status"] in ("success", "failed"):
                    break
        outcome = data.get("outcome") or {}
        audio_url = outcome.get("audio_url")
        if not audio_url:
            for m in (outcome.get("media_urls") or outcome.get("medias") or outcome.get("media") or []):
                if isinstance(m, dict) and m.get("url"):
                    audio_url = m["url"]
                    break
        row["audio_url"] = bool(audio_url)
        usage = outcome.get("usage") or {}
        if usage:
            row["usage"] = usage
        if audio_url and row["status"] == "success":
            safe = re.sub(r"[^a-zA-Z0-9._-]", "_", model)
            path = f"verify/audio/{safe}.wav"
            os.makedirs("verify/audio", exist_ok=True)
            async with session.get(audio_url) as ar:
                blob = await ar.read()
            open(path, "wb").write(blob)
            row["bytes"] = len(blob)
            row["duration_s"] = ffprobe_duration(path)
        if row["status"] == "failed":
            row["error"] = json.dumps(data)[:200]
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"
    return row


async def main() -> int:
    key = os.environ["GMI_CLOUD_API_KEY"]
    models = INWORLD + MINIMAX + CHATTERBOX + UNAVAILABLE
    results = []
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as session:
        for model in models:
            row = await probe(session, key, model)
            results.append(row)
            print(json.dumps(row), flush=True)
    with open("verify/models-live.json", "w") as f:
        json.dump(results, f, indent=1)
    ok = sum(1 for r in results if r.get("status") == "success" and r.get("audio_url"))
    print(f"\nTOTAL: {len(results)} models probed, {ok} produced audio")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
