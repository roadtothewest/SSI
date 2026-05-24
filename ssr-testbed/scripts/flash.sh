#!/bin/bash

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FIRMWARE_DIR="$PROJECT_DIR/firmware"

usage() {
    echo "Usage: $0 [board]"
    echo "  board: NUCLEO-H723ZG (default)"
    exit 1
}

BOARD="${1:-NUCLEO-H723ZG}"

case "$BOARD" in
    NUCLEO-H723ZG)
        BUILD_DIR="$FIRMWARE_DIR/build"
        BINARY="$BUILD_DIR/ssr-firmware.bin"
        OPENOCD_CFG="board/st_nucleo_h723zg.cfg"
        ;;
    *)
        echo "Unknown board: $BOARD"
        usage
        ;;
esac

if [ ! -f "$BINARY" ]; then
    echo "Binary not found: $BINARY"
    echo "Build first with: cd $FIRMWARE_DIR && make"
    exit 1
fi

echo "Flashing $BINARY to $BOARD..."

openocd -f "$OPENOCD_CFG" \
    -c "init" \
    -c "reset halt" \
    -c "flash write_image erase $BINARY 0x08000000" \
    -c "reset run" \
    -c "exit"

echo "Flash complete. Resetting target."
