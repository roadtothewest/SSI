#!/usr/bin/env bash
# Usage: inject_test.sh 'SWD_ACTION' [uart_log.py args...]
#   SWD_ACTION: tools/swd.py arguments, e.g. 'cmd 1' (capture restart), 'cmd 7' (stall acq 30 ms),
#   'dma-suspend 0' (suspend the SAI DMA channel: real overrun error).
# Loads the current build, runs the action ~4 s after boot and checks the VCP log across it
# (12 s from the boot banner).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ACTION="$1"
shift
ENV_SH="${STM32_ENV:-$HOME/2026-2/SSI/tools/stm32-env.sh}"
# shellcheck disable=SC1090
if [ -f "$ENV_SH" ]; then source "$ENV_SH" >/dev/null; fi
"$HERE/run_test.sh" 12 "$@" &
TEST=$!
sleep 10 # run_test.sh: 1.5 s drain + ~4 s load, so this is ~4 s after boot
# shellcheck disable=SC2086
python3 "$HERE/swd.py" $ACTION >/dev/null
wait "$TEST"
