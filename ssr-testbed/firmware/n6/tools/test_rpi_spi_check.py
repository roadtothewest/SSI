#!/usr/bin/env python3
"""Host test of rpi_spi_check.BlockStats with blocks derived from the C-built sample."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import avx_block  # noqa: E402
import rpi_spi_check  # noqa: E402


def with_seq(block, seq):
    b = bytearray(block)
    struct.pack_into("<II", b, 4, seq, (10000 * seq) & 0xFFFFFFFF)
    struct.pack_into("<H", b, 14, 0)  # the C sample carries flags = 2: start from a clean block
    for i in range(avx_block.N_TUPLES):
        struct.pack_into("<I", b, avx_block.HEADER.size + avx_block.TUPLE.size * i,
                         (10000 * seq + 500 * i) & 0xFFFFFFFF)
    struct.pack_into("<H", b, avx_block.CRC_OFFSET, avx_block.crc16(bytes(b[:avx_block.CRC_OFFSET])))
    return bytes(b)


def main(sample_path):
    base = open(sample_path, "rb").read()
    st = rpi_spi_check.BlockStats()
    st.feed(bytes(538))                    # idle link: MISO zeros
    st.feed(b"\xff" * 538)                 # idle link, other polarity
    for seq in (10, 11, 12):
        st.feed(with_seq(base, seq))
    st.feed(with_seq(base, 12))            # same block read twice
    st.feed(with_seq(base, 15))            # windows 13 and 14 never arrived
    bad = bytearray(with_seq(base, 16))
    bad[100] ^= 0x01                       # corrupted on the wire
    st.feed(bytes(bad))                    # rejected: for the Pi, seq 16 is lost too
    flagged = bytearray(with_seq(base, 17))
    struct.pack_into("<H", flagged, 14, 1)  # bit0: ADC data lost
    struct.pack_into("<H", flagged, avx_block.CRC_OFFSET, avx_block.crc16(bytes(flagged[:avx_block.CRC_OFFSET])))
    st.feed(bytes(flagged))

    failures = []
    for name, got, want in (("idle", st.idle, 2), ("ok", st.ok, 5), ("dup", st.dup, 1),
                            ("gaps", st.gaps, 2), ("missing", st.missing, 3),
                            ("crc", st.crc_err, 1), ("flagged", st.flagged, 1),
                            ("ts_err", st.ts_err, 0)):
        if got != want:
            failures.append(f"{name}: got {got}, expected {want}")
    print("\n".join(failures) if failures else "BlockStats OK", st.summary())
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
