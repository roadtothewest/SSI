#!/usr/bin/env python3
"""SPI block of ssr-testbed/firmware/PROTOCOLO_SPI.md v1: parse and check 538-byte blocks.

Mirrors what auravoxd (RPi5) decodes; used by the host tests and the SWD checks.
"""
import argparse
import struct
import sys

BLOCK_SIZE = 538
CRC_OFFSET = 536
HEADER = struct.Struct("<BBBBIIHH")  # sync0 sync1 type version seq t0_us n flags: 16 bytes
TUPLE = struct.Struct("<I3H8h")      # ts_us adc[3] voz[8]: 26 bytes
N_TUPLES = 20
FIELDS = ("type", "version", "seq", "t0_us", "n", "flags")


def crc16(data):
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no final XOR."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def parse(buf: bytes) -> dict:
    if len(buf) != BLOCK_SIZE:
        raise ValueError(f"block size {len(buf)} != {BLOCK_SIZE}")
    s0, s1, typ, ver, seq, t0, n, flags = HEADER.unpack_from(buf, 0)
    return {
        "sync_ok": (s0, s1) == (0xAA, 0x55),
        "type": typ, "version": ver, "seq": seq, "t0_us": t0, "n": n, "flags": flags,
        "crc_ok": crc16(buf[:CRC_OFFSET]) == struct.unpack_from("<H", buf, CRC_OFFSET)[0],
        "tuples": [TUPLE.unpack_from(buf, HEADER.size + TUPLE.size * i) for i in range(N_TUPLES)],
    }


def value(p, key):
    """Header field, or tsI / adcI_C / vozI_K for tuple I."""
    for prefix, base, width in (("ts", 0, 1), ("adc", 1, 3), ("voz", 4, 8)):
        if key.startswith(prefix) and key[len(prefix):].replace("_", "").isdigit():
            parts = key[len(prefix):].split("_")
            i = int(parts[0])
            j = int(parts[1]) if len(parts) > 1 else 0
            if j >= width:
                raise KeyError(key)
            return p["tuples"][i][base + j]
    return p[key]


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="validate a block file")
    c.add_argument("file")
    c.add_argument("--expect", nargs="*", default=[], help="key=value (int, 0x.. allowed)")
    c.add_argument("--ts-check", action="store_true",
                   help="ts_us of tuple i = t0_us + 500 i, and t0_us = 10000 * seq (firmware rule)")
    a = ap.parse_args()
    with open(a.file, "rb") as f:
        p = parse(f.read())
    ok = p["sync_ok"] and p["crc_ok"]
    print(" ".join(f"{k}={p[k]}" for k in FIELDS), f"sync_ok={p['sync_ok']} crc_ok={p['crc_ok']}")
    if a.ts_check:
        for i, tup in enumerate(p["tuples"]):
            if tup[0] != (p["t0_us"] + 500 * i) & 0xFFFFFFFF:
                print(f"MISMATCH ts{i}: got {tup[0]}, expected t0_us + {500 * i}")
                ok = False
        if p["t0_us"] != (10000 * p["seq"]) & 0xFFFFFFFF:
            print(f"MISMATCH t0_us: got {p['t0_us']}, expected 10000 * seq = {10000 * p['seq']}")
            ok = False
    for item in a.expect:
        key, want = item.split("=", 1)
        got = value(p, key)
        if got != int(want, 0):
            print(f"MISMATCH {key}: got {got}, expected {want}")
            ok = False
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
