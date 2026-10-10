#!/usr/bin/env python3
"""1-second diagnostic captures over SWD (firmware module diag) and their analysis.

s_diag layout (diag.c): u32 header[8] = {state, first_window, n, gaps, epoch, 0, 0, 0},
u32 raw[320] at 32, i32 audio[16000] at 1312, u16 emg[2000][3] at 65312; 77312 bytes.

  diag.py audio [--tone HZ] [--out DIR]          P3: dominant tone, rms, peak, WAV
  diag.py emg [--ch N --tone HZ] [--out DIR]     P2: EMG statistics, CSV, generator tone
  diag.py noise                                  P7: EMG noise with the SCK pin on vs off
  diag.py pulse [--restarts N]                   P4: c from the D7 pulse seen on A1 and SD
"""
import argparse
import cmath
import math
import os
import struct
import sys
import time
import wave
from array import array

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swd  # noqa: E402

FS_AUDIO, FS_EMG, CH = 16000, 2000, 3
EMG_DIV = FS_AUDIO // FS_EMG  # 8 audio frames per EMG sample
AUDIO_FMIN = 50.0  # Hz: the INMP441 passband starts at 60 Hz; below it, drift outweighs the tone
SIZE, OFF_RAW, OFF_AUDIO, OFF_EMG = 77312, 32, 1312, 65312
CMD_RESTART, CMD_DIAG, CMD_PULSE_ON, CMD_PULSE_OFF, CMD_SCK_OFF, CMD_SCK_ON = 1, 2, 3, 4, 5, 6
SSI_SYNC_C = 0       # keep equal to ssi_config.h
EMG_THRESHOLD = 2048  # pulse test: A1 driven to 0 / 3.3 V


def capture(timeout=8.0):
    addr, size = swd.symbol("s_diag")
    if size != SIZE:
        raise RuntimeError(f"s_diag is {size} bytes, this tool expects {SIZE}")
    swd.cmd(CMD_DIAG)
    end = time.time() + timeout
    while swd.read32(addr) != 2:
        if time.time() > end:
            raise TimeoutError("diag capture did not finish")
        time.sleep(0.3)
    buf = swd.read(addr, SIZE)
    _, first, n, gaps, epoch = struct.unpack_from("<5I", buf, 0)
    raw = array("I", buf[OFF_RAW:OFF_AUDIO])
    audio = array("i", buf[OFF_AUDIO:OFF_EMG])
    emg = array("H", buf[OFF_EMG:SIZE])
    if sys.byteorder != "little":
        for x in (raw, audio, emg):
            x.byteswap()
    if n != 100 or gaps != 0:
        raise RuntimeError(f"incomplete capture: n={n} gaps={gaps}")
    return {"first": first, "epoch": epoch, "raw": raw, "audio": audio, "emg": emg}


def fft(x):
    """Iterative radix-2 FFT; len(x) must be a power of two."""
    a = [complex(v) for v in x]
    n = len(a)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    size = 2
    while size <= n:
        w = cmath.exp(-2j * math.pi / size)
        half = size // 2
        for start in range(0, n, size):
            wk = 1 + 0j
            for k in range(start, start + half):
                t = wk * a[k + half]
                a[k + half] = a[k] - t
                a[k] += t
                wk *= w
        size *= 2
    return a


def dominant(x, fs, fmin=0.0):
    """Strongest tone in Hz at or above fmin: Hann window, FFT, parabolic interpolation on the log
    magnitude."""
    m = len(x)
    n = 1 << (m - 1).bit_length()
    mean = sum(x) / m
    win = [(v - mean) * (0.5 - 0.5 * math.cos(2 * math.pi * i / (m - 1))) for i, v in enumerate(x)]
    mag = [abs(c) for c in fft(win + [0.0] * (n - m))[: n // 2]]
    k = max(range(max(2, math.ceil(fmin * n / fs)), n // 2 - 1), key=mag.__getitem__)
    a, b, c = (math.log(mag[k + d] + 1e-12) for d in (-1, 0, 1))
    den = a - 2 * b + c
    return (k + (0.5 * (a - c) / den if den else 0.0)) * fs / n


def stats(v):
    n = len(v)
    mean = sum(v) / n
    return mean, math.sqrt(sum((x - mean) ** 2 for x in v) / n), min(v), max(v)


def write_wav(path, audio):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(FS_AUDIO)
        w.writeframes(b"".join(struct.pack("<i", s)[:3] for s in audio))


def cmd_audio(a):
    d = capture()
    au = d["audio"]
    f0 = dominant(au, FS_AUDIO, AUDIO_FMIN)
    rms = math.sqrt(sum(s * s for s in au) / len(au))
    peak = max(abs(s) for s in au)
    print(f"AUDIO epoch={d['epoch']} first={d['first']} f0={f0:.2f} rms={rms:.0f} peak={peak} "
          f"raw0={d['raw'][0]:#010x}")
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        write_wav(os.path.join(a.out, "audio.wav"), au)
        print(f"wav -> {os.path.join(a.out, 'audio.wav')}")
    return a.tone is None or (abs(f0 - a.tone) <= 2.0 and peak > 10000)


def cmd_emg(a):
    d = capture()
    e = d["emg"]
    for c in range(CH):
        mean, std, lo, hi = stats(e[c::CH])
        print(f"EMG ch{c} mean={mean:.1f} std={std:.2f} min={lo} max={hi}")
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        path = os.path.join(a.out, "emg.csv")
        with open(path, "w") as f:
            f.write("i,ch0,ch1,ch2\n")
            for i in range(len(e) // CH):
                f.write(f"{i},{e[CH * i]},{e[CH * i + 1]},{e[CH * i + 2]}\n")
        print(f"csv -> {path}")
    if a.tone is None:
        return True
    f0 = dominant(e[a.ch::CH], FS_EMG)
    print(f"EMG ch{a.ch} f0={f0:.2f}")
    return abs(f0 - a.tone) <= 1.0


def cmd_noise(a):
    swd.cmd(CMD_SCK_ON)
    on = capture()
    swd.cmd(CMD_SCK_OFF)
    try:
        off = capture()
    finally:
        swd.cmd(CMD_SCK_ON)
    ok = True
    for c in range(CH):
        m1, s1, _, _ = stats(on["emg"][c::CH])
        m0, s0, _, _ = stats(off["emg"][c::CH])
        print(f"NOISE ch{c} std_on={s1:.3f} std_off={s0:.3f} dstd={s1 - s0:+.3f} dmean={m1 - m0:+.2f}")
        ok = ok and abs(s1 - s0) < 1.0
    return ok


def pulse_offsets(d):
    """d = j - 8m per pulse: j = first non-zero audio frame, m = first EMG ch0 sample over the
    threshold. With EMG sample i taken at frame 8i + c, d spans {c-7 .. c+1}; c = min(d) + 7."""
    au, ch0 = d["audio"], d["emg"][0::CH]
    out = []
    for j in range(1, len(au)):
        if au[j] == 0 or au[j - 1] != 0:
            continue
        for m in range(max(1, j // EMG_DIV - 4), min(len(ch0), j // EMG_DIV + 4)):
            if ch0[m] > EMG_THRESHOLD >= ch0[m - 1]:
                out.append(j - EMG_DIV * m)
                break
    return out


def cmd_pulse(a):
    swd.cmd(CMD_PULSE_ON)
    cs = []
    ok = True
    try:
        for r in range(1, a.restarts + 1):
            swd.cmd(CMD_RESTART)
            d = capture()
            ds = pulse_offsets(d) + pulse_offsets(capture())  # 2 s: min bin is ~10 % of pulses
            if len(ds) < 60:
                print(f"PULSE r={r} epoch={d['epoch']} n={len(ds)}: too few pulses (D7 -> A1 and D8?)")
                return False
            c = min(ds) + EMG_DIV - 1
            cs.append(c)
            ok = ok and max(ds) - min(ds) <= EMG_DIV
            print(f"PULSE r={r} epoch={d['epoch']} n={len(ds)} dmin={min(ds)} dmax={max(ds)} c={c}")
    finally:
        swd.cmd(CMD_PULSE_OFF)
    ok = ok and len(set(cs)) == 1 and abs(cs[0]) < 16  # constant (R3); |c| * 62.5 us < 1 ms (R4)
    print(f"SYNC c={cs[0]} frames = {cs[0] * 62.5:.1f} us; SSI_SYNC_C={SSI_SYNC_C}")
    if cs[0] != SSI_SYNC_C:
        print("NOTE: set SSI_SYNC_C to the measured c in ssi_config.h and in this tool")
    return ok


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="op", required=True)
    p = sub.add_parser("audio")
    p.add_argument("--tone", type=float)
    p.add_argument("--out")
    p = sub.add_parser("emg")
    p.add_argument("--ch", type=int, default=0)
    p.add_argument("--tone", type=float)
    p.add_argument("--out")
    sub.add_parser("noise")
    p = sub.add_parser("pulse")
    p.add_argument("--restarts", type=int, default=10)
    a = ap.parse_args()
    ok = {"audio": cmd_audio, "emg": cmd_emg, "noise": cmd_noise, "pulse": cmd_pulse}[a.op](a)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
