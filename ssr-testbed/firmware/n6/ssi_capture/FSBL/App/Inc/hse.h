#ifndef HSE_H
#define HSE_H

#include <stdint.h>

/* The 48 MHz HSE: one crystal for the audio clock (PLL4) and the LPTIM triggers (CLKP), so EMG
   and audio never drift apart. hse_start is idempotent; thread context (HAL waits). */
int hse_start(void);      /* 0 when HSERDY */
uint32_t hse_mode(void);  /* 1 crystal, 2 digital bypass, 0 not started */

#endif
