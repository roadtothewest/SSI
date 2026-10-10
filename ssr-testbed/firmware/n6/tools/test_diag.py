#!/usr/bin/env python3
"""Host test of the P3 decision in diag.py: a 1 kHz tone must pass even when slow drift is stronger.

Real INMP441 captures carry drift and handling noise below a few tens of Hz, often larger than
the test tone. The hardware boundary (diag.capture, SWD) is replaced by a synthetic capture.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diag  # noqa: E402


class Args:
    tone = 1000.0
    out = None


def fake_capture(audio):
    return lambda timeout=8.0: {"first": 0, "epoch": 1, "raw": [0], "audio": audio, "emg": []}


def main():
    rnd = random.Random(1)
    fs = diag.FS_AUDIO
    failures = []

    # tone 5000, 3 Hz drift 20000, noise 1000: the drift is the largest line in the spectrum
    audio = [int(5000 * math.sin(2 * math.pi * 1000 * i / fs) + 20000 * math.sin(2 * math.pi * 3 * i / fs)
                 + rnd.gauss(0, 1000)) for i in range(fs)]
    diag.capture = fake_capture(audio)
    if not diag.cmd_audio(Args()):
        failures.append("1 kHz tone under 3 Hz drift: P3 failed")

    # drift and noise only: no tone, P3 must fail
    audio = [int(20000 * math.sin(2 * math.pi * 3 * i / fs) + rnd.gauss(0, 1000)) for i in range(fs)]
    diag.capture = fake_capture(audio)
    if diag.cmd_audio(Args()):
        failures.append("no tone: P3 passed")

    # the EMG path keeps the full band (AFE passband starts at 20 Hz)
    emg = [1000 * math.sin(2 * math.pi * 25 * i / diag.FS_EMG) for i in range(diag.FS_EMG)]
    if abs(diag.dominant(emg, diag.FS_EMG) - 25) > 1:
        failures.append("EMG 25 Hz tone not found")

    print("\n".join(failures) if failures else "diag OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
