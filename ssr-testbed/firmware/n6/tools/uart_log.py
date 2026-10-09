#!/usr/bin/env python3
"""Capture the ST-LINK VCP and check it (standard library only).

--start REGEX        drop everything before the first line matching REGEX (the boot banner),
                     then capture --secs seconds; the ST-LINK VCP replays stale bytes on open
--drain SECS         discard input for SECS first (run_test.sh drains before the reset)
--expect REGEX       must appear in the log
--reject REGEX       must not appear
--check 'TAG[/N]:EXPR'
                     evaluated on every 'TAG k=v k=v' line after the first N lines of that TAG
                     (N defaults to --skip; use /0 for one-shot lines such as INIT);
                     EXPR sees the fields as ints, plus d_<field> = change since the previous line.
"""
import argparse
import os
import re
import select
import sys
import termios
import time

KV_LINE = re.compile(r"^([A-Z]+)((?:\s+[a-z_0-9]+=-?\d+)+)\s*$")
KV = re.compile(r"([a-z_0-9]+)=(-?\d+)")


def open_tty(path, baud):
    fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    speed = getattr(termios, f"B{baud}")
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = attrs[5] = speed
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIFLUSH)
    return fd


def capture(dev, baud, secs, start=None, wait=20.0, drain=0.0):
    """Return the text read in secs seconds; with start, timing begins at that line.
    drain: seconds of input discarded first (bytes the VCP bridge buffered earlier)."""
    fd = open_tty(dev, baud)
    t_drain = time.time() + drain
    while time.time() < t_drain:
        if select.select([fd], [], [], 0.05)[0]:
            try:
                os.read(fd, 4096)
            except BlockingIOError:
                pass
    end = time.time() + (wait + secs if start else secs)
    data = b""
    started = start is None
    try:
        while time.time() < end:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                try:
                    data += os.read(fd, 4096)
                except BlockingIOError:
                    pass
            if not started:
                text = data.decode("ascii", "replace")
                m = re.search(r"^.*" + start, text, re.M)
                if m:
                    data = data[m.start():]
                    started = True
                    end = time.time() + secs
    finally:
        os.close(fd)
    if not started:
        return None
    return data.decode("ascii", "replace").replace("\r", "")


def kv_lines(text):
    for raw in text.splitlines():
        m = KV_LINE.match(raw.strip())
        if m:
            yield m.group(1), {k: int(v) for k, v in KV.findall(m.group(2))}, raw.strip()


def run_checks(text, checks, skip):
    ok = True
    for spec in checks:
        tag, expr = spec.split(":", 1)
        n_skip = skip
        if "/" in tag:
            tag, n = tag.split("/", 1)
            n_skip = int(n)
        prev, seen, evaluated = None, 0, 0
        for t, fields, raw in kv_lines(text):
            if t != tag:
                continue
            seen += 1
            env = dict(fields)
            if prev is not None:
                env.update({f"d_{k}": v - prev.get(k, 0) for k, v in fields.items()})
            prev = fields
            if seen <= n_skip:
                continue
            evaluated += 1
            try:
                passed = bool(eval(expr, {"__builtins__": {}, "abs": abs, "min": min, "max": max}, env))
            except NameError as e:
                passed = False
                print(f"CHECK ERROR {spec}: {e}")
            if not passed:
                print(f"CHECK FAILED {spec}\n  line: {raw}")
                ok = False
        if evaluated == 0:
            print(f"CHECK FAILED {spec}: no {tag} lines after skip={n_skip}")
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--secs", type=float, default=5.0)
    ap.add_argument("--skip", type=int, default=1)
    ap.add_argument("--start")
    ap.add_argument("--wait", type=float, default=20.0)
    ap.add_argument("--drain", type=float, default=0.0)
    ap.add_argument("--expect", action="append", default=[])
    ap.add_argument("--reject", action="append", default=[])
    ap.add_argument("--check", action="append", default=[])
    ap.add_argument("--out")
    a = ap.parse_args()
    text = capture(a.dev, a.baud, a.secs, a.start, a.wait, a.drain)
    if text is None:
        print(f"MISSING START: {a.start} (waited {a.wait} s)")
        print("RESULT: FAIL")
        return 1
    sys.stdout.write(text)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text)
    ok = True
    for rx in a.expect:
        if not re.search(rx, text, re.M):
            print(f"MISSING: {rx}")
            ok = False
    for rx in a.reject:
        if re.search(rx, text, re.M):
            print(f"FORBIDDEN: {rx}")
            ok = False
    ok = run_checks(text, a.check, a.skip) and ok
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
