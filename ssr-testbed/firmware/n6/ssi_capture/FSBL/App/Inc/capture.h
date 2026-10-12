#ifndef CAPTURE_H
#define CAPTURE_H

#include <stdint.h>

#include "tx_api.h"

/* Driver events, set from the DMA callbacks into the group given to capture_init(). */
#define CAP_EVT_EMG 0x01u /* emg_adc finished a window */
#define CAP_EVT_AUD 0x02u /* mic finished a window */
#define CAP_EVT_ERR 0x04u /* SAI, ADC or DMA error */

/* Owns the start order that fixes c (spec §4). Single caller: acq (Task 5) or mon (Task 4). */
int capture_init(TX_EVENT_FLAGS_GROUP *flags); /* thread context; logs "INIT cap=..." */
int capture_start(void);                       /* restarts if running; epoch++ */
void capture_stop(void);
uint8_t capture_epoch(void);

#endif
