#!/bin/bash

set -euo pipefail

echo "=== SSR Testbed Setup ==="
echo ""

INSTALL_GO=false
INSTALL_PYTHON=false
INSTALL_STM32=false

# --- Go ---
if command -v go &>/dev/null; then
    echo "[OK] Go $(go version | grep -oP 'go\d+\.\d+')"
else
    echo "[MISSING] Go"
    INSTALL_GO=true
fi

# --- Python ---
if command -v python3 &>/dev/null; then
    echo "[OK] Python3 $(python3 --version | cut -d' ' -f2)"
else
    echo "[MISSING] Python3"
    INSTALL_PYTHON=true
fi

# --- pip packages ---
if command -v pip3 &>/dev/null; then
    echo "[OK] pip3"
    if [ -f "pc-tools/ssr-export/requirements.txt" ]; then
        pip3 install -r pc-tools/ssr-export/requirements.txt --quiet
        echo "[OK] Python dependencies installed"
    fi
fi

# --- STM32 tools ---
if command -v arm-none-eabi-gcc &>/dev/null; then
    echo "[OK] arm-none-eabi-gcc $(arm-none-eabi-gcc --version | head -1 | grep -oP '\d+\.\d+\.\d+')"
else
    echo "[MISSING] ARM GCC toolchain (arm-none-eabi-gcc)"
    INSTALL_STM32=true
fi

if command -v openocd &>/dev/null; then
    echo "[OK] OpenOCD $(openocd --version | head -1 | grep -oP '\d+\.\d+\.\d+')"
else
    echo "[MISSING] OpenOCD"
    INSTALL_STM32=true
fi

if command -v stm32cubeMX &>/dev/null; then
    echo "[OK] STM32CubeMX"
else
    echo "[INFO] STM32CubeMX not found (optional for .ioc editing)"
fi

# --- Install suggestions ---
echo ""
if $INSTALL_GO; then
    echo "Install Go: sudo apt install golang-go"
fi
if $INSTALL_PYTHON; then
    echo "Install Python: sudo apt install python3 python3-pip python3-venv"
fi
if $INSTALL_STM32; then
    echo "Install ARM GCC:"
    echo "  sudo apt install gcc-arm-none-eabi openocd stlink-tools"
fi

echo ""
echo "Setup complete."
