#ifndef __USB_CDC_H
#define __USB_CDC_H

#include "main.h"

#define CDC_SYNC0                 0xAA
#define CDC_SYNC1                 0x55
#define CDC_TYPE_ACC              0x01
#define CDC_TYPE_AUDIO            0x02

typedef __PACKED_STRUCT {
    uint8_t  sync0;
    uint8_t  sync1;
    uint8_t  frame_type;
    uint8_t  flags;
    uint32_t timestamp;
    uint16_t data_len;
    uint8_t  data[];
} cdc_frame_t;

#define CDC_HEADER_SIZE           10
#define CDC_FRAME_ACC_SIZE        (CDC_HEADER_SIZE + ACC_SAMPLES_PER_FRAME * 3 * 2)
#define CDC_FRAME_AUDIO_SIZE      (CDC_HEADER_SIZE + AUDIO_SAMPLES_PER_FRAME * 4)

bool usb_cdc_init(void);
bool usb_cdc_send_frame(uint8_t type, uint32_t timestamp,
                        const uint8_t *data, uint16_t len);
bool usb_cdc_is_connected(void);

void usb_cdc_tx_complete(void);

#endif
