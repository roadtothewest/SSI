#!/usr/bin/env python3
"""Host test of tone_lines: test-signal generation, WAV reading (16/24 bit) and tone detection."""
import math
import os
import random
import struct
import sys
import tempfile
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tone_lines  # noqa: E402


def write_wav24(path, x, fs):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(fs)
        w.writeframes(b"".join(struct.pack("<i", int(v))[:3] for v in x))


def main():
    failures = []
    rnd = random.Random(2)
    with tempfile.TemporaryDirectory() as d:
        # a DK capture: 16 kHz, 24 bit, 1 and 2 kHz tones over noise and slow drift
        fs = 16000
        x = [3000 * math.sin(2 * math.pi * 1000 * i / fs) + 3000 * math.sin(2 * math.pi * 2000 * i / fs)
             + 20000 * math.sin(2 * math.pi * 3 * i / fs) + rnd.gauss(0, 2000) for i in range(fs)]
        p = os.path.join(d, "dk.wav")
        write_wav24(p, x, fs)
        lv = {f: over for f, _, over in tone_lines.tone_levels(*tone_lines.load_wav(p))}
        for f in (1000, 2000):
            if lv[f] < 20:
                failures.append(f"{f} Hz present but only +{lv[f]:.1f} dB")
        for f in (250, 500, 4000):
            if lv[f] > 12:
                failures.append(f"{f} Hz absent but +{lv[f]:.1f} dB")
        if not tone_lines.passes(lv):
            failures.append("pass criterion rejects a capture with 1 and 2 kHz present")

        # noise only: the criterion must fail
        y = [rnd.gauss(0, 2000) for _ in range(fs)]
        write_wav24(p, y, fs)
        if tone_lines.passes({f: o for f, _, o in tone_lines.tone_levels(*tone_lines.load_wav(p))}):
            failures.append("pass criterion accepts noise only")

        # the playback signal: 48 kHz, 16 bit, all five tones, read back from a window
        g = os.path.join(d, "tones.wav")
        tone_lines.write_test_signal(g, secs=2.0)
        lv = {f: over for f, _, over in tone_lines.tone_levels(*tone_lines.load_wav(g, start=0.5))}
        if min(lv.values()) < 40:
            failures.append(f"generated signal misses a tone: {lv}")

    print("\n".join(failures) if failures else "tone_lines OK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
