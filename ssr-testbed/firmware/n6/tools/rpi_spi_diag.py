#!/usr/bin/env python3
"""P5 diagnosis on the RPi5: read like rpi_spi_check.py, keep every read and classify the bad ones.

Uses the block's own structure (t0_us = 10000 * seq, ts_i = t0_us + 500 * i) to find where a read
stops matching its block and why: a zero tail (the DK stopped sending), a byte slip (a byte lost or
repeated at a CS gap), a second AA 55 header (the DK restarted the block mid-read), or intact
timestamps with a bad CRC (bit errors).

  python3 rpi_spi_diag.py --secs 15            # mode 0, 4 MHz, a read every 4 ms
"""
import argparse
import collections
import struct
import time

import avx_block

HDR = b"\xaa\x55\x04\x01"
TS0 = avx_block.HEADER.size  # offset of tuple 0's ts_us
TSZ = avx_block.TUPLE.size


def u32(buf, p):
    return struct.unpack_from("<I", buf, p)[0]


def ts_hits(buf):
    """(offset, seq, tuple) of every ts_us-looking word confirmed by a neighbour tuple 26 B away."""
    hits = []
    for p in range(0, len(buf) - 3):
        v = u32(buf, p)
        s, r = divmod(v, 10000)
        if r % 500 or r // 500 >= avx_block.N_TUPLES or v == 0:
            continue
        nxt = p + TSZ + 4 <= len(buf) and u32(buf, p + TSZ) == v + 500
        prv = p - TSZ >= 0 and u32(buf, p - TSZ) == v - 500
        if nxt or prv:
            hits.append((p, s, r // 500))
    return hits


def classify(buf):
    """(class, detail) of one 538-byte read."""
    if buf[:2] != b"\xaa\x55":
        if all(b == 0 for b in buf) or all(b == 0xFF for b in buf):
            return "idle", ""
        hits = ts_hits(buf)
        hdr = buf.find(HDR)
        if hits:
            p, s, j = hits[0]
            return "idle_data", f"block seq={s} byte {TS0 + TSZ * j} at read offset {p} (hdr at {hdr})"
        return "idle_data", f"no block content (hdr at {hdr}) head={buf[:8].hex()}"
    p = avx_block.parse(buf)
    if p["crc_ok"]:
        return "ok", ""
    seq, t0 = p["seq"], p["t0_us"]
    if t0 != 10000 * seq & 0xFFFFFFFF:
        return "bad_header", f"seq={seq} t0={t0} head={buf[:16].hex()}"
    first = next((i for i in range(avx_block.N_TUPLES)
                  if u32(buf, TS0 + TSZ * i) != (t0 + 500 * i) & 0xFFFFFFFF), None)
    hdr2 = buf.find(HDR, 1)
    if first is None:
        return "bit_errors", f"seq={seq}: all 20 ts_us right, CRC wrong"
    off = TS0 + TSZ * first
    tail = buf[off:]
    nz = next((k for k, b in enumerate(tail) if b != 0), None)
    zrun = len(tail) if nz is None else nz
    hits = [(q, s, j) for q, s, j in ts_hits(buf) if q >= off]
    shifts = collections.Counter((s - seq, q - (TS0 + TSZ * j)) for q, s, j in hits)
    detail = (f"seq={seq} first bad ts at tuple {first} (byte {off}); zeros from there: {zrun}; "
              f"later ts (dseq, shift): {dict(shifts)}; 2nd header at {hdr2}")
    if zrun >= len(tail) - 2:
        return "zero_tail", detail
    if hdr2 > 0:
        return "restart", detail
    if shifts and all(ds == 0 for ds, _ in shifts):
        return "slip", detail
    if shifts:
        return "foreign", detail
    return "other", detail + f" bytes={buf[max(0, off - 4):off + 12].hex()}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bus", type=int, default=0)
    ap.add_argument("--cs", type=int, default=0)
    ap.add_argument("--mode", type=int, default=0)
    ap.add_argument("--hz", type=int, default=4_000_000)
    ap.add_argument("--secs", type=float, default=15.0)
    ap.add_argument("--period", type=float, default=0.004)
    ap.add_argument("--show", type=int, default=12, help="bad reads printed in detail")
    ap.add_argument("--raw", help="write every read (538 B each, in order) to this file")
    a = ap.parse_args()
    import spidev

    spi = spidev.SpiDev()
    spi.open(a.bus, a.cs)
    spi.mode = a.mode
    spi.bits_per_word = 8
    spi.max_speed_hz = a.hz
    zeros = [0] * avx_block.BLOCK_SIZE
    reads = []
    t0 = time.monotonic()
    try:
        while time.monotonic() - t0 < a.secs:
            t = time.monotonic()
            reads.append((t, bytes(spi.xfer2(zeros))))
            time.sleep(a.period)
    finally:
        spi.close()
    if a.raw:
        with open(a.raw, "wb") as f:
            f.writelines(buf for _, buf in reads)

    counts = collections.Counter()
    shown = 0
    prev_cls, prev_t = "-", t0
    for k, (t, buf) in enumerate(reads):
        cls, detail = classify(buf)
        counts[cls] += 1
        if cls not in ("ok", "idle") and shown < a.show:
            print(f"#{k} +{(t - prev_t) * 1e3:5.1f} ms after a {prev_cls} read: {cls}: {detail}")
            shown += 1
        prev_cls, prev_t = cls, t
    secs = reads[-1][0] - t0 if reads else 0.0
    print(f"SUMMARY mode={a.mode} hz={a.hz} reads={len(reads)} in {secs:.1f} s: "
          + " ".join(f"{c}={n}" for c, n in sorted(counts.items())))


if __name__ == "__main__":
    main()
