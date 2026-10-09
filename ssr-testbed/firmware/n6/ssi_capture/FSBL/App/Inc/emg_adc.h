#ifndef EMG_ADC_H
#define EMG_ADC_H

#include <stdint.h>

#include "tx_api.h"

/* ADC1 regular scan, ranks 1..3 = INP10 (PA9, A1), INP16 (PF3, A4), INP8 (PB10, A5); 12 bits,
   246.5-cycle sampling, one sequence per trigger (2 kHz, sync module). Circular DMA over two windows of
   SSI_WIN_EMG sequences: window k lives in half k % 2. The callbacks set flag_block
   (flag_error on ADC overrun or DMA error) when flags != TX_NULL. */
int emg_adc_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error,
                 uint32_t trigger); /* trigger: ADC_EXTERNALTRIG_* from sync_adc_trigger() */
int emg_adc_start(void);                     /* arms the ADC: conversions start at the next trigger */
void emg_adc_stop(void);
uint32_t emg_adc_blocks_done(void);          /* windows completed since the last start */
const uint32_t *emg_adc_window(uint32_t k);  /* SSI_WIN_EMG * SSI_EMG_CH words: s0c0, s0c1, ... */
uint32_t emg_adc_errors(void);
uint32_t emg_adc_clock_hz(void);             /* ADC kernel clock after the divider */

#endif
