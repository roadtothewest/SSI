#!/usr/bin/env bash
# Usage: run_test.sh SECS [uart_log.py args...]
# Starts the VCP reader, loads the current build to RAM (reset + load) and returns the check result.
# SECS counts from the boot banner, so the ~4 s load and stale VCP bytes are excluded.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SECS="$1"
shift
python3 -I "$HERE/uart_log.py" --drain 1 --start "SSI capture fw" --secs "$SECS" "$@" &
READER=$!
sleep 1.5 # let the reader drain stale VCP bytes before the reset
"$HERE/fw.sh" ram >/dev/null
wait "$READER"
