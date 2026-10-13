#ifndef MIC_H
#define MIC_H

#include <stdint.h>

#include "tx_api.h"

/* Audio source: 10 ms windows of SSI_WIN_AUDIO samples at 16 kHz, in the INMP441's 24-bit scale
   (full scale = 2^23). One implementation per build (SSI_MIC_SRC, ssi_config.h):
   - SSI_MIC_I2S (mic_sai.c): INMP441 on SAI2 block B, master RX, Philips I2S, 24-bit data in
     32-bit slots, both slots captured (left = mic with L/R to GND; right must stay silent).
     HSE 48 MHz -> PLL4 1179.648 MHz -> IC7 /24 = 49.152 MHz -> MCKDIV 12 -> FS = 16 kHz.
   - SSI_MIC_ANALOG (mic_adc.c): ADMP401 breakout on A3 (PA12, ADC2 channel 13), 12 bits at
     64 kHz triggered by sync (LPTIM2), decimated by audio_fir (fixed latency AFIR_DELAY).
   Circular DMA over two windows: window k lives in half k % 2. The DMA callbacks set flag_block
   (flag_error on errors) when flags != TX_NULL. */
int mic_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error);
int mic_start(void);             /* resets the window count and the decoder state */
void mic_stop(void);
uint32_t mic_blocks_done(void);  /* windows completed since the last start */
uint32_t mic_errors(void);
uint32_t mic_clock_hz(void);     /* SAI2 kernel clock (49152000) or ADC clock */

/* acq, in window order: copy window k out of the DMA buffer, check that the DMA did not reach
   it meanwhile, then decode the copy. */
void mic_copy(uint32_t k);
void mic_decode(int32_t *audio);        /* SSI_WIN_AUDIO samples */
const uint32_t *mic_diag_raw(void);     /* 2 * SSI_WIN_AUDIO words of the copy, for diag */
uint32_t mic_right_activity(void);      /* I2S: frames of the copy with a non-zero right slot */

void mic_sck_output(int on);  /* I2S P7: 0 = SCK pin (PE12/A2) analog, 1 = AF10; analog: no-op */

#endif
