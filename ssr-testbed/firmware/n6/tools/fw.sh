#!/usr/bin/env bash
# Build ssi_capture and load it to RAM on the DK (development mode, BOOT1 = H).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FSBL="$HERE/../ssi_capture/FSBL"
ELF="$FSBL/build/Debug/ssi_capture_FSBL.elf"
# Toolchain on PATH: Matías's env script if present (override with STM32_ENV).
ENV_SH="${STM32_ENV:-$HOME/2026-2/SSI/tools/stm32-env.sh}"
# shellcheck disable=SC1090
if [ -f "$ENV_SH" ]; then source "$ENV_SH" >/dev/null; fi

case "${1:-}" in
  build)
    cd "$FSBL"
    # SSI_MIC_ANALOG=OFF: INMP441 on SAI2 instead of the ADMP401 on A3 (plan 3).
    # SSI_SYNC_LPTIM=ON (INMP441 only): bench build without the D6->D2 bridge (see ssi_config.h).
    cmake --preset Debug -DSSI_MIC_ANALOG="${SSI_MIC_ANALOG:-ON}" -DSSI_SYNC_LPTIM="${SSI_SYNC_LPTIM:-OFF}" >/dev/null
    cmake --build --preset Debug
    ;;
  ram)
    STM32_Programmer_CLI -c port=SWD mode=UR -hardRst >/dev/null 2>&1 || true
    sleep 0.5
    GDBLOG="$(mktemp)"
    # Without -e the server exits after the first detach: one load per call.
    ST-LINK_gdbserver -p 61234 -l 1 -d -cp "$STM32_PROG_ROOT" -m 1 -g >"$GDBLOG" 2>&1 &
    GDBS=$!
    sleep 2
    arm-none-eabi-gdb -batch -ex 'target extended-remote :61234' -ex load -ex detach "$ELF" \
      | grep -E '^(Loading|Start address|Transfer rate)' || { cat "$GDBLOG"; exit 1; }
    wait "$GDBS" || true
    ;;
  *)
    echo "usage: fw.sh build|ram" >&2
    exit 2
    ;;
esac
