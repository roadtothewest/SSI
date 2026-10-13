#!/usr/bin/env python3
"""Microphone check with a known sound: level of each test tone in a WAV.

The PC plays TONES at once (write_test_signal) while the DK captures audio (diag.py audio --out)
and the PC's own microphone records a reference (tools/mic_tone_check.sh). A working INMP441
shows every tone the reference shows; a deaf one shows only noise (2026-10-10).

  tone_lines.py gen OUT.wav [--secs S]          5-tone test signal (48 kHz, 16 bit)
  tone_lines.py levels IN.wav [--start S] [--fs HZ]   tone levels: dBFS and dB over the local median
"""
import argparse
import math
import os
import struct
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from diag import fft  # noqa: E402

TONES = (250, 500, 1000, 2000, 4000)
PASS_TONES = (1000, 2000)  # speech band; both must stand out
PASS_DB = 20.0             # over the local median; a deaf mic stays under +8 dB


def write_test_signal(path, secs=20.0, fs=48000, tone_dbfs=-20.0):
    """All TONES at once, tone_dbfs each (sum peak ~ -6 dBFS), 20 ms fades."""
    a = 32767 * 10 ** (tone_dbfs / 20)
    n, fade = int(secs * fs), int(0.02 * fs)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(fs)
        frames = bytearray()
        for i in range(n):
            g = min(1.0, i / fade, (n - 1 - i) / fade)
            v = sum(math.sin(2 * math.pi * f * i / fs) for f in TONES) * a * g
            frames += struct.pack("<h", int(max(-32767, min(32767, v))))
        w.writeframes(bytes(frames))


def load_wav(path, start=0.0, secs=1.0, fs=None):
    """First channel of a 16- or 24-bit WAV -> (samples, fs, full scale). fs overrides the header."""
    with wave.open(path) as w:
        rate, width, ch = w.getframerate(), w.getsampwidth(), w.getnchannels()
        w.setpos(int(start * rate))
        raw = w.readframes(int(secs * rate))
    if width not in (2, 3):
        raise ValueError(f"{path}: {8 * width}-bit WAV not supported")
    step, x = width * ch, []
    for i in range(0, len(raw) - step + 1, step):
        b = raw[i:i + width]
        x.append(struct.unpack("<h", b)[0] if width == 2 else
                 struct.unpack("<i", b + (b"\xff" if b[2] & 0x80 else b"\x00"))[0])
    return x, fs or rate, 1 << (8 * width - 1)


def tone_levels(x, fs, full, tones=TONES):
    """[(f, dBFS of the tone, dB over the median of its neighbourhood)] with a Hann window."""
    m = len(x)
    n = 1 << (m - 1).bit_length()
    mean = sum(x) / m
    win = [0.5 - 0.5 * math.cos(2 * math.pi * i / (m - 1)) for i in range(m)]
    mag = [abs(c) for c in fft([(v - mean) * win[i] for i, v in enumerate(x)] + [0.0] * (n - m))[: n // 2]]
    df, gain = fs / n, sum(win)
    out = []
    for f in tones:
        k = round(f / df)
        peak = max(mag[k - 3:k + 4])
        near = sorted(mag[max(1, k - 60):k - 10] + mag[k + 10:k + 60])
        med = near[len(near) // 2]
        out.append((f, 20 * math.log10(2 * peak / gain / full + 1e-12), 20 * math.log10(peak / (med + 1e-12))))
    return out


def passes(over_by_tone):
    return all(over_by_tone[f] >= PASS_DB for f in PASS_TONES)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="op", required=True)
    g = sub.add_parser("gen")
    g.add_argument("out")
    g.add_argument("--secs", type=float, default=20.0)
    lv = sub.add_parser("levels")
    lv.add_argument("wav")
    lv.add_argument("--start", type=float, default=0.0)
    lv.add_argument("--fs", type=int, help="real sample rate when the WAV header is wrong")
    a = ap.parse_args()
    if a.op == "gen":
        write_test_signal(a.out, a.secs)
        return 0
    levels = tone_levels(*load_wav(a.wav, a.start, fs=a.fs))
    print(f"{os.path.basename(a.wav)} @{a.start:.1f}s: " +
          "  ".join(f"{f} Hz {db:6.1f} dBFS (+{over:4.1f})" for f, db, over in levels))
    ok = passes({f: over for f, _, over in levels})
    print("TONES:", "PRESENT" if ok else "ABSENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
