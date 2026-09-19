#!/usr/bin/env python3
"""Narrates a pane's last Claude answer: Haiku renders it for ears, Kokoro speaks it.
Model load runs concurrently with the API request; sentences stream into TTS as they land."""

import json
import os
import queue
import re
import subprocess
import sys
import threading

import numpy as np

BIN = os.path.expanduser("~/.claude/bin")
DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "claude-say")
KOKORO_DATA = os.path.expanduser("~/.local/share/kokoro")
SAMPLE_RATE = 24000
FORCE_FLUSH_AT = 300

ABBREV = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
          "e.g", "i.e", "fig", "no", "approx", "inc", "ltd", "co", "al"}
BOUNDARY = re.compile(r'([.!?…])(["\')\]]*)(\s+)')


def tone(name):
    path = os.path.join(BIN, "say-tones", name + ".raw")
    if os.path.isfile(path):
        with open(path, "rb") as handle:
            subprocess.run(APLAY_ARGS, stdin=subprocess.DEVNULL, input=handle.read())


APLAY_ARGS = ["aplay", "-q", "-r", str(SAMPLE_RATE), "-f", "S16_LE", "-t", "raw", "-c", "1", "-"]


def false_boundary(buf, match):
    head = buf[:match.start(1)]
    word = re.split(r"[\s(\[\"']", head)[-1].lower() if head else ""
    if word in ABBREV or re.fullmatch(r"[a-z]", word):
        return True
    return bool(re.match(r"\s*\d", buf[match.end(3):])) and head[-1:].isdigit()


def drain(buf):
    """Split off every complete sentence; return (sentences, remainder)."""
    sentences, cut = [], 0
    for match in BOUNDARY.finditer(buf):
        if false_boundary(buf, match):
            continue
        piece = buf[cut:match.end(2)].strip()
        if piece:
            sentences.append(piece)
            cut = match.end(3)
    rest = buf[cut:]
    if not sentences and len(rest) > FORCE_FLUSH_AT and " " in rest:
        head, _, rest = rest.rpartition(" ")
        sentences.append(head.strip())
    return sentences, rest


def load_kokoro(box, ready):
    from kokoro_onnx import Kokoro
    box.append(Kokoro(os.path.join(KOKORO_DATA, "kokoro-v1.0.onnx"),
                      os.path.join(KOKORO_DATA, "voices-v1.0.bin")))
    ready.set()


def speak(work, box, ready, sink, voice, speed):
    ready.wait()
    while True:
        sentence = work.get()
        if sentence is None:
            return
        samples, _ = box[0].create(sentence, voice=voice, speed=speed, lang="en-us")
        sink.write((np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2").tobytes())
        sink.flush()


def api_key():
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()
    with open(os.path.expanduser("~/.anthropic-key"), encoding="utf-8") as handle:
        return handle.read().strip()


def main():
    pane = sys.argv[1]
    voice = sys.argv[2] if len(sys.argv) > 2 else "af_heart"
    speed = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    extra = sys.argv[4] if len(sys.argv) > 4 else ""

    stem = os.path.join(DIR, "p" + pane)
    with open(stem + ".txt", encoding="utf-8") as handle:
        payload = json.load(handle)
    open(stem + ".spoken", "w").close()
    with open(stem + ".pid", "w") as handle:
        handle.write(str(os.getpgrp()))

    box, ready, work = [], threading.Event(), queue.Queue()
    threading.Thread(target=load_kokoro, args=(box, ready), daemon=True).start()

    import anthropic
    client = anthropic.Anthropic(api_key=api_key())
    with open(os.path.join(BIN, "say-prompt.md"), encoding="utf-8") as handle:
        system = handle.read()
    if extra:
        system += "\n\nAdditional instruction for this rendering: " + extra

    prompt = "Question asked:\n{question}\n\nAnswer to render:\n{answer}".format(**payload)
    player = subprocess.Popen(APLAY_ARGS, stdin=subprocess.PIPE)
    worker = threading.Thread(target=speak, args=(work, box, ready, player.stdin, voice, speed))
    worker.start()

    buf = ""
    try:
        with client.messages.stream(model="claude-haiku-4-5", max_tokens=2000,
                                    system=system,
                                    messages=[{"role": "user", "content": prompt}]) as stream:
            for chunk in stream.text_stream:
                buf += chunk
                sentences, buf = drain(buf)
                for sentence in sentences:
                    work.put(sentence)
        if buf.strip():
            work.put(buf.strip())
    finally:
        work.put(None)
        worker.join()
        player.stdin.close()
        player.wait()
        try:
            os.remove(stem + ".pid")
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        tone("error")
        raise
