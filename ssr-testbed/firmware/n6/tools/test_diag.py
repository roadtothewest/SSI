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


def simulate_analog_pulses(rnd, emg_shift=0, seconds=1.0):
    """The firmware's analog chain in Python: ADC2 at 64 kHz -> audio_fir -> 16 kHz, EMG at 2 kHz.
    D7 pulses (0 / 3.3 V, ~10 ms, random phase) on A1 and A3: codes ~25 low, ~4082 high."""
    import gen_audio_fir
    coef = gen_audio_fir.quantize(gen_audio_fir.design())
    n_raw = int(64000 * seconds)
    low, high = 25, 4082
    raw = [low] * n_raw
    t = 3000.0 + rnd.uniform(0, 32)
    while t < n_raw - 3000:
        r0 = math.ceil(t)
        for r in range(r0, min(n_raw, r0 + 640)):
            raw[r] = high
        t += 1400 + rnd.uniform(0, 32)
    x = [v - 2048 for v in raw]
    hist = [x[0]] * (gen_audio_fir.TAPS - 1)
    audio, dc_x1, dc_y1 = [], x[0] * 4096, 0
    for r, v in enumerate(x):
        hist.append(v)
        if r % 4 == 0:
            acc = sum(c * h for c, h in zip(coef, hist[-gen_audio_fir.TAPS:]))
            y = (acc >> 18) - dc_x1 + dc_y1 - ((dc_y1 + 512) >> 10)
            dc_x1 = acc >> 18
            dc_y1 = max(-(1 << 23) + 1, min((1 << 23) - 1, y))
            audio.append(dc_y1)
            del hist[:-gen_audio_fir.TAPS]
    emg = []
    for m in range(n_raw // 32):
        r = 32 * m + emg_shift  # emg_shift > 0: EMG sample m is taken later than ADC2 sample 32m
        emg += [raw[min(n_raw - 1, r)], low, low]
    return {"audio": audio, "emg": emg}


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

    # P4 with the analog microphone: the D7 pulse reaches A1 (EMG) and A3 (ADC2 -> FIR). With the
    # LPTIMs aligned (EMG sample i = ADC2 sample 32i), c must be the FIR latency: 12.
    for shift, want in ((0, 12), (32, 20)):  # EMG sampled one ADC2 window (32) late: c + 8
        d = simulate_analog_pulses(rnd, emg_shift=shift)
        ds = diag.pulse_offsets(d, analog=True)
        c = min(ds) + diag.EMG_DIV - 1 if ds else None
        if len(ds) < 30 or c != want or max(ds) - min(ds) > diag.EMG_DIV:
            failures.append(f"analog P4 (EMG shift {shift}): n={len(ds)} c={c}, expected {want}")

    print("\n".join(failures) if failures else "diag OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
