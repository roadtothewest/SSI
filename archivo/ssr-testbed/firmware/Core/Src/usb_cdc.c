#include "usb_cdc.h"
#include <string.h>

static uint8_t usb_tx_buf[USB_TX_BUF_SIZE];
static uint16_t usb_tx_len = 0;
static volatile bool usb_tx_busy = false;
static volatile bool usb_connected = false;

static void usb_cdc_init_gpio(void)
{
    GPIO_InitTypeDef GPIO_InitStruct = {0};

    __HAL_RCC_GPIOA_CLK_ENABLE();

    GPIO_InitStruct.Pin = GPIO_PIN_11 | GPIO_PIN_12;
    GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
    GPIO_InitStruct.Alternate = GPIO_AF10_OTG2_HS;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

    GPIO_InitStruct.Pin = GPIO_PIN_9;
    GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
    GPIO_InitStruct.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
}

bool usb_cdc_init(void)
{
    usb_cdc_init_gpio();
    usb_connected = true;
    usb_tx_busy = false;
    usb_tx_len = 0;
    return true;
}

bool usb_cdc_send_frame(uint8_t type, uint32_t timestamp,
                        const uint8_t *data, uint16_t len)
{
    if (!usb_connected) return false;

    while (usb_tx_busy) {
        asm("nop");
    }

    if (len + CDC_HEADER_SIZE > USB_TX_BUF_SIZE) {
        return false;
    }

    cdc_frame_t *frame = (cdc_frame_t*)usb_tx_buf;
    frame->sync0 = CDC_SYNC0;
    frame->sync1 = CDC_SYNC1;
    frame->frame_type = type;
    frame->flags = 0;
    frame->timestamp = timestamp;
    frame->data_len = len;
    memcpy(frame->data, data, len);

    usb_tx_len = len + CDC_HEADER_SIZE;

    return true;
}

bool usb_cdc_is_connected(void)
{
    return usb_connected;
}

void usb_cdc_tx_complete(void)
{
    usb_tx_busy = false;
}
