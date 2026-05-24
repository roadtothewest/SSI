PROJECT = ssr-firmware
BUILD_DIR = build

C_SOURCES = \
    Core/Src/main.c \
    Core/Src/iis3dwb.c \
    Core/Src/inmp441.c \
    Core/Src/usb_cdc.c \
    Core/Src/frame.c \
    Core/Src/sync_timer.c

C_INCLUDES = \
    -ICore/Inc \
    -IDrivers/STM32H7xx_HAL_Driver/Inc \
    -IDrivers/CMSIS/Include \
    -IDrivers/CMSIS/Device/ST/STM32H7xx/Include

# Toolchain
PREFIX = arm-none-eabi-
CC = $(PREFIX)gcc
OBJCOPY = $(PREFIX)objcopy
SIZE = $(PREFIX)size

# MCU
MCU = -mcpu=cortex-m7 -mthumb -mfpu=fpv5-d16 -mfloat-abi=hard

# Config
OPENOCD_CFG = board/st_nucleo_h723zg.cfg

CFLAGS = $(MCU) $(C_INCLUDES) -O2 -Wall -Werror \
    -DSTM32H723xx -DHSE_VALUE=8000000 \
    -ffunction-sections -fdata-sections

LDFLAGS = $(MCU) -TSTM32H723ZGTx_FLASH.ld \
    -Wl,--gc-sections -Wl,--print-memory-usage

LDLIBS = -lm

all: $(BUILD_DIR)/$(PROJECT).bin

$(BUILD_DIR)/$(PROJECT).elf: $(C_SOURCES) | $(BUILD_DIR)
	$(CC) $(CFLAGS) $^ $(LDFLAGS) $(LDLIBS) -o $@

$(BUILD_DIR)/$(PROJECT).bin: $(BUILD_DIR)/$(PROJECT).elf
	$(OBJCOPY) -O binary $< $@
	$(SIZE) $<

$(BUILD_DIR):
	mkdir -p $@

flash: $(BUILD_DIR)/$(PROJECT).bin
	openocd -f $(OPENOCD_CFG) \
	    -c "init" \
	    -c "reset halt" \
	    -c "flash write_image erase $< 0x08000000" \
	    -c "reset run" \
	    -c "exit"

clean:
	rm -rf $(BUILD_DIR)

.PHONY: all flash clean
