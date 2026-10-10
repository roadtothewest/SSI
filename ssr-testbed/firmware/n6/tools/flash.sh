#!/usr/bin/env bash
# Builds the firmware (default: ETR sync, the demo build), signs it as an FSBL and writes it to
# the DK's external flash at 0x70000000, then verifies it. The DK must be in development mode
# (BOOT1 = H). To boot from flash: BOOT0 = L, BOOT1 = L, reset; back to development: BOOT1 = H.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_SH="${STM32_ENV:-$HOME/2026-2/SSI/tools/stm32-env.sh}"
# shellcheck disable=SC1090
if [ -f "$ENV_SH" ]; then source "$ENV_SH" >/dev/null; fi
: "${STM32_DK_EXTLOADER:?set STM32_DK_EXTLOADER to MX66UW1G45G_STM32N6570-DK.stldr}"

SSI_SYNC_LPTIM="${SSI_SYNC_LPTIM:-OFF}" "$HERE/fw.sh" build >/dev/null
ELF="$HERE/../ssi_capture/FSBL/build/Debug/ssi_capture_FSBL.elf"
OUT="$HERE/../out/flash"
mkdir -p "$OUT"
BIN="$OUT/ssi_capture_FSBL.bin"
SIGNED="$OUT/ssi_capture_FSBL-trusted.bin"
arm-none-eabi-objcopy -O binary "$ELF" "$BIN"
# Same commands as the n6_smoke flash test (2026-10-08); -align is required with CubeProgrammer >= 2.21.
STM32_SigningTool_CLI -s -bin "$BIN" -nk -of 0x80000000 -t fsbl -o "$SIGNED" -hv 2.3 -align \
  -dump "$SIGNED" >/dev/null
echo "image: $(stat -c %s "$BIN") B, signed: $(stat -c %s "$SIGNED") B"
STM32_Programmer_CLI -c port=swd -hardRst -el "$STM32_DK_EXTLOADER" -d "$SIGNED" 0x70000000 -v \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -E 'Erasing|Download|verified|Error|error' || true
