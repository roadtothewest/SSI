#ifndef SYNC_H
#define SYNC_H

#include <stdint.h>

/* EMG trigger, phase-locked to the audio frames (spec §4). Default (SSI_SYNC_ETR): TIM1 counts
   SAI FS rising edges on ETR (PD0/D2, bridged from D6) and fires TRGO on every SSI_EMG_DIV-th
   edge. Bench (SSI_SYNC_LPTIM): LPTIM1 PWM at FS / SSI_EMG_DIV from the HSE, no bridge. */
/* Analog microphone (SSI_MIC_ANALOG, plan 3): also LPTIM2 at 64 kHz for ADC2, same HSE, same
   compare count, started together with LPTIM1: EMG sample i = microphone sample 32i. */
int sync_init(void);           /* after mic_init and emg_adc_init (the LPTIM backend starts the HSE) */
void sync_start(void);         /* call before the SAI starts */
void sync_stop(void);
uint32_t sync_adc_trigger(void); /* ADC_EXTERNALTRIG_* for emg_adc_init */
uint32_t sync_mic_trigger(void); /* analog microphone only: LPTIM2 at 64 kHz, for mic_init */
uint32_t sync_source(void);      /* SSI_SYNC_ETR or SSI_SYNC_LPTIM */

#endif
