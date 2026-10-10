#!/usr/bin/env python3
"""Check the DK -> RPi5 SPI link from the Raspberry Pi (PROTOCOLO_SPI.md), without auravoxd.

Runs on the RPi5 with SPI0 wired to the DK (spec §3) and python3-spidev installed. It polls
538-byte reads every few ms (the DRDY-less bring-up mode of PROTOCOLO §4: the firmware holds a
block that arrives during a read), so DRDY does not need to be wired. Copy this file and
avx_block.py to the Pi.

  python3 rpi_spi_check.py --secs 600 --hz 4000000
P5 acceptance: ~100 blocks/s, crc = 0 and gaps = 0 for 10 minutes.
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import avx_block  # noqa: E402


class BlockStats:
    """Classifies raw 538-byte reads the way the RPi5 side must."""

    def __init__(self):
        self.ok = self.idle = self.crc_err = self.dup = 0
        self.gaps = self.missing = self.flagged = self.ts_err = 0
        self.last_seq = None

    def feed(self, buf):
        if buf[:2] != b"\xaa\x55":
            self.idle += 1  # MISO 0x00/0xFF: no block armed (PROTOCOLO §4), not an error
            return
        p = avx_block.parse(buf)
        if not p["crc_ok"] or p["type"] != 4 or p["n"] != avx_block.N_TUPLES:
            self.crc_err += 1
            return
        seq = p["seq"]
        if self.last_seq is not None:
            if seq == self.last_seq:
                self.dup += 1
                return
            if seq != (self.last_seq + 1) & 0xFFFFFFFF:
                self.gaps += 1
                self.missing += (seq - self.last_seq - 1) & 0xFFFFFFFF
        self.last_seq = seq
        self.ok += 1
        if p["flags"]:
            self.flagged += 1
        if any(t[0] != (p["t0_us"] + 500 * i) & 0xFFFFFFFF for i, t in enumerate(p["tuples"])):
            self.ts_err += 1

    def summary(self):
        return (f"ok={self.ok} crc={self.crc_err} gaps={self.gaps} missing={self.missing} "
                f"dup={self.dup} flagged={self.flagged} ts_err={self.ts_err} idle={self.idle}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bus", type=int, default=0)
    ap.add_argument("--cs", type=int, default=0)
    ap.add_argument("--hz", type=int, default=4_000_000)
    ap.add_argument("--secs", type=float, default=60.0)
    ap.add_argument("--period", type=float, default=0.004, help="seconds between reads (< 10 ms)")
    ap.add_argument("--out", help="append every good block to this file")
    a = ap.parse_args()
    import spidev  # RPi: sudo apt install python3-spidev

    spi = spidev.SpiDev()
    spi.open(a.bus, a.cs)
    spi.mode = 0
    spi.bits_per_word = 8
    spi.max_speed_hz = a.hz
    st = BlockStats()
    out = open(a.out, "ab") if a.out else None
    zeros = [0] * avx_block.BLOCK_SIZE
    t0 = time.monotonic()
    next_report = t0 + 1.0
    try:
        while time.monotonic() - t0 < a.secs:
            buf = bytes(spi.xfer2(zeros))  # one transfer, CS low for all 538 bytes
            before = st.ok
            st.feed(buf)
            if out and st.ok != before:
                out.write(buf)
            now = time.monotonic()
            if now >= next_report:
                print(f"t={now - t0:6.1f} s rate={st.ok / (now - t0):6.1f} blk/s {st.summary()}",
                      flush=True)
                next_report += 1.0
            time.sleep(a.period)
    finally:
        spi.close()
        if out:
            out.close()
    rate = st.ok / max(1e-9, time.monotonic() - t0)
    ok = st.crc_err == 0 and st.gaps == 0 and rate > 95.0
    print(f"RESULT: {'PASS' if ok else 'FAIL'} rate={rate:.1f} {st.summary()}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
