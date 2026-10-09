#!/usr/bin/env bash
# Usage: restart_test.sh [uart_log.py args...]
# Loads the current build, asks mon for a capture restart over SWD ~4 s after boot and checks
# the VCP log across it (12 s from the boot banner): STAT lines must go on with ep=2.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_SH="${STM32_ENV:-$HOME/2026-2/SSI/tools/stm32-env.sh}"
# shellcheck disable=SC1090
if [ -f "$ENV_SH" ]; then source "$ENV_SH" >/dev/null; fi
"$HERE/run_test.sh" 12 "$@" &
TEST=$!
sleep 10 # run_test.sh: 1.5 s drain + ~4 s load, so this is ~4 s after boot
python3 "$HERE/swd.py" cmd 1 >/dev/null
wait "$TEST"
