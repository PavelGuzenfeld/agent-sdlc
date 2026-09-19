#!/usr/bin/env python3
"""Streams Kokoro TTS for a text file as raw signed 16-bit little-endian PCM on stdout.
Sample rate is 24000. Speed is a multiplier: higher is faster."""

import asyncio
import os
import sys

import numpy as np
from kokoro_onnx import Kokoro

DATA = os.path.expanduser("~/.local/share/kokoro")
MODEL = os.path.join(DATA, "kokoro-v1.0.onnx")
VOICES = os.path.join(DATA, "voices-v1.0.bin")


async def speak(path: str, voice: str, speed: float) -> None:
    with open(path, encoding="utf-8") as handle:
        text = handle.read().strip()
    if not text:
        return

    kokoro = Kokoro(MODEL, VOICES)
    out = sys.stdout.buffer
    async for samples, _rate in kokoro.create_stream(
        text, voice=voice, speed=speed, lang="en-us"
    ):
        pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
        out.write(pcm.tobytes())
        out.flush()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: ksay.py <text-file> <voice> <speed>")
    for required in (MODEL, VOICES):
        if not os.path.isfile(required):
            sys.exit(f"ksay.py: missing {required} — run ./install.sh --deps=say")
    asyncio.run(speak(sys.argv[1], sys.argv[2], float(sys.argv[3])))
