#ifndef MIC_SAI_H
#define MIC_SAI_H

#include <stdint.h>

#include "tx_api.h"

/* INMP441 on SAI2 block B: master RX, Philips I2S, 24-bit data in 32-bit slots, both slots
   captured (left = mic with L/R to GND; right must stay silent). Audio clock: HSE 48 MHz ->
   PLL4 1179.648 MHz -> IC7 /24 = 49.152 MHz -> MCKDIV 12 -> FS = 16 kHz exactly.
   Circular DMA over two windows of SSI_WIN_AUDIO frames: window k lives in half k % 2.
   The DMA callbacks set flag_block (flag_error on SAI/DMA errors) when flags != TX_NULL. */
int mic_sai_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error);
int mic_sai_start(void);                     /* resets the window count; FS edges start here */
void mic_sai_stop(void);
uint32_t mic_sai_blocks_done(void);          /* windows completed since the last start */
const uint32_t *mic_sai_window(uint32_t k);  /* 2 * SSI_WIN_AUDIO words: L0, R0, L1, R1, ... */
uint32_t mic_sai_errors(void);
uint32_t mic_sai_clock_hz(void);             /* SAI2 kernel clock, expected 49152000 */
uint32_t mic_sai_hse_mode(void);             /* 1 crystal, 2 digital bypass, 0 not started */
void mic_sai_sck_output(int on);             /* P7: 0 = SCK pin (PE12/A2) analog, 1 = AF10 */

#endif
