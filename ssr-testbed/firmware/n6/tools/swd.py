#!/usr/bin/env python3
"""Read and write ssi_capture variables over SWD while the firmware runs.

STM32_Programmer_CLI in HOTPLUG mode (no halt, no reset) plus the ELF symbol table
(arm-none-eabi-nm). Source ~/2026-2/SSI/tools/stm32-env.sh first.

  swd.py sym NAME        address and size of a symbol
  swd.py cmd N           write the mon debug mailbox and wait until mon has run it
  swd.py sample OUT.bin  last SPI block sampled by sink, CRC-checked
  swd.py dma-suspend N   suspend GPDMA1 channel N (fault injection: 0 = SAI, 1 = ADC)
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import avx_block  # noqa: E402

ELF = os.path.join(HERE, "..", "ssi_capture", "FSBL", "build", "Debug", "ssi_capture_FSBL.elf")
CLI = "STM32_Programmer_CLI"
CONNECT = ["-c", "port=SWD", "mode=HOTPLUG"]


def symbol(name, elf=ELF):
    out = subprocess.run(["arm-none-eabi-nm", "-S", elf], check=True, capture_output=True,
                         text=True).stdout
    hits = [f for f in (line.split() for line in out.splitlines()) if len(f) == 4 and f[3] == name]
    if len(hits) != 1:
        raise KeyError(f"{name}: {len(hits)} matches in {elf}")
    return int(hits[0][0], 16), int(hits[0][1], 16)


def _cli(*args):
    r = subprocess.run([CLI, *CONNECT, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{CLI} {' '.join(args)} failed:\n{r.stdout[-600:]}")
    return r.stdout


def read(addr, size):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "dump.bin")
        _cli("-u", hex(addr), str(size), path)
        with open(path, "rb") as f:
            data = f.read()
    if len(data) != size:
        raise RuntimeError(f"read {len(data)} of {size} bytes at {addr:#x}")
    return data


def read32(addr):
    return struct.unpack("<I", read(addr, 4))[0]


def write32(addr, value):
    _cli("-w32", hex(addr), hex(value))


def cmd(n, timeout=6.0):
    addr, _ = symbol("s_mon_dbg_cmd")
    write32(addr, n)
    end = time.time() + timeout
    while time.time() < end:
        if read32(addr) == 0:
            return
        time.sleep(0.2)
    raise TimeoutError(f"mon did not take command {n} (is the firmware running?)")


def sample(retries=3):
    addr, _ = symbol("s_sink_sample")
    for _ in range(retries):
        buf = read(addr, avx_block.BLOCK_SIZE + 2)[: avx_block.BLOCK_SIZE]  # word-sized read
        p = avx_block.parse(buf)
        if p["sync_ok"] and p["crc_ok"]:
            return buf
        time.sleep(0.3)  # torn read while sink was copying: read again
    raise RuntimeError("no valid block in s_sink_sample")


GPDMA1_CCR0 = 0x50021064  # GPDMA1_BASE_S + 0x64: channel 0 CCR; channels are 0x80 apart
DMA_CCR_SUSP = 1 << 2


def dma_suspend(channel):
    """Fault injection. The effect is checked on the VCP log: the firmware may already have
    aborted and restarted the channel when we could read it back."""
    addr = GPDMA1_CCR0 + 0x80 * channel
    try:
        write32(addr, read32(addr) | DMA_CCR_SUSP)
    except RuntimeError:
        pass  # the CLI verifies by reading back, and the DMA changes the register


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="op", required=True)
    sub.add_parser("sym").add_argument("name")
    sub.add_parser("cmd").add_argument("n", type=int)
    sub.add_parser("sample").add_argument("out")
    sub.add_parser("dma-suspend").add_argument("channel", type=int)
    a = ap.parse_args()
    if a.op == "sym":
        addr, size = symbol(a.name)
        print(f"{a.name} addr={addr:#010x} size={size}")
    elif a.op == "cmd":
        cmd(a.n)
        print(f"CMD {a.n} OK")
    elif a.op == "dma-suspend":
        dma_suspend(a.channel)
        print(f"GPDMA1 channel {a.channel} suspended")
    else:
        with open(a.out, "wb") as f:
            f.write(sample())
        print(f"sample -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
