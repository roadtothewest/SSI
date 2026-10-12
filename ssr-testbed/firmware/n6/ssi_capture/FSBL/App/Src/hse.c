#include "hse.h"

#include "stm32n6xx_hal.h"

static uint32_t s_mode;

/* MB1939 board config says crystal; several DK examples use the digital bypass. Keep the
   mode that reaches HSERDY (a wrong mode only times out). */
int hse_start(void)
{
  static const uint32_t k_modes[2] = {RCC_HSE_ON, RCC_HSE_BYPASS_DIGITAL};
  RCC_OscInitTypeDef osc = {0};
  if (s_mode != 0u) {
    return 0;
  }
  osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  osc.PLL1.PLLState = RCC_PLL_NONE;
  osc.PLL2.PLLState = RCC_PLL_NONE;
  osc.PLL3.PLLState = RCC_PLL_NONE;
  osc.PLL4.PLLState = RCC_PLL_NONE;
  for (uint32_t i = 0; i < 2u; i++) {
    osc.HSEState = k_modes[i];
    if (HAL_RCC_OscConfig(&osc) == HAL_OK) {
      s_mode = i + 1u;
      return 0;
    }
    osc.HSEState = RCC_HSE_OFF;
    (void)HAL_RCC_OscConfig(&osc);
  }
  return -1;
}

uint32_t hse_mode(void)
{
  return s_mode;
}
