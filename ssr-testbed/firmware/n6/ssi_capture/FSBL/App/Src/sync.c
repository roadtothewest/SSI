#include "sync.h"

#include "hse.h"
#include "ssi_config.h"
#include "stm32n6xx_hal.h"

#if SSI_SYNC_SRC == SSI_SYNC_ETR

static TIM_HandleTypeDef s_tim;

int sync_init(void)
{
  GPIO_InitTypeDef g = {0};
  TIM_ClockConfigTypeDef clk = {0};
  TIM_MasterConfigTypeDef master = {0};

  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_TIM1_CLK_ENABLE();
  g.Pin = GPIO_PIN_0; /* TIM1_ETR, D2 */
  g.Mode = GPIO_MODE_AF_PP;
  g.Pull = GPIO_PULLDOWN; /* no edges while the bridge is open or the SAI is off */
  g.Speed = GPIO_SPEED_FREQ_LOW;
  g.Alternate = GPIO_AF1_TIM1;
  HAL_GPIO_Init(GPIOD, &g);
  HAL_GPIO_ConfigPinAttributes(GPIOD, GPIO_PIN_0, GPIO_PIN_SEC | GPIO_PIN_NPRIV);

  s_tim.Instance = TIM1;
  s_tim.Init.Prescaler = 0;
  s_tim.Init.CounterMode = TIM_COUNTERMODE_UP;
  s_tim.Init.Period = SSI_EMG_DIV - 1u; /* update = TRGO on every SSI_EMG_DIV-th FS edge */
  s_tim.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  s_tim.Init.RepetitionCounter = 0;
  s_tim.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&s_tim) != HAL_OK) {
    return -1;
  }
  clk.ClockSource = TIM_CLOCKSOURCE_ETRMODE2; /* count ETR rising edges */
  clk.ClockPolarity = TIM_CLOCKPOLARITY_NONINVERTED;
  clk.ClockPrescaler = TIM_CLOCKPRESCALER_DIV1;
  clk.ClockFilter = 0;
  if (HAL_TIM_ConfigClockSource(&s_tim, &clk) != HAL_OK) {
    return -2;
  }
  master.MasterOutputTrigger = TIM_TRGO_UPDATE;
  master.MasterOutputTrigger2 = TIM_TRGO2_RESET;
  master.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&s_tim, &master) != HAL_OK) {
    return -3;
  }
  return 0;
}

void sync_start(void)
{
  /* Preset to DIV - 1: the first FS rising edge (mid-frame 0) overflows the counter, so EMG
     sample i is converted at mid-frame SSI_EMG_DIV * i (c = 0, spec §4). */
  __HAL_TIM_SET_COUNTER(&s_tim, SSI_EMG_DIV - 1u);
  (void)HAL_TIM_Base_Start(&s_tim);
}

void sync_stop(void)
{
  (void)HAL_TIM_Base_Stop(&s_tim);
}

uint32_t sync_adc_trigger(void)
{
  return ADC_EXTERNALTRIG_T1_TRGO;
}

#else /* SSI_SYNC_LPTIM */

#define LPTIM_KERNEL_HZ 48000000u /* CLKP = HSE: the crystal that also feeds PLL4 (audio) */

static LPTIM_HandleTypeDef s_lptim;

int sync_init(void)
{
  RCC_PeriphCLKInitTypeDef clk = {0};
  LPTIM_OC_ConfigTypeDef oc = {0};

  if (hse_start() != 0) {
    return -4;
  }
  clk.PeriphClockSelection = RCC_PERIPHCLK_CKPER | RCC_PERIPHCLK_LPTIM1;
  clk.CkperClockSelection = RCC_CLKPCLKSOURCE_HSE;
  clk.Lptim1ClockSelection = RCC_LPTIM1CLKSOURCE_CLKP;
  if (HAL_RCCEx_PeriphCLKConfig(&clk) != HAL_OK) {
    return -1;
  }
  __HAL_RCC_LPTIM1_CLK_ENABLE();
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_LPTIM1,
                                        RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_NPRIV);
  s_lptim.Instance = LPTIM1;
  s_lptim.Init.Clock.Source = LPTIM_CLOCKSOURCE_APBCLOCK_LPOSC; /* count the kernel clock */
  s_lptim.Init.Clock.Prescaler = LPTIM_PRESCALER_DIV1;
  s_lptim.Init.Trigger.Source = LPTIM_TRIGSOURCE_SOFTWARE;
  s_lptim.Init.Period = LPTIM_KERNEL_HZ / (SSI_AUDIO_FS_HZ / SSI_EMG_DIV) - 1u; /* 23999 */
  s_lptim.Init.UpdateMode = LPTIM_UPDATE_IMMEDIATE;
  s_lptim.Init.CounterSource = LPTIM_COUNTERSOURCE_INTERNAL;
  s_lptim.Init.Input1Source = LPTIM_INPUT1SOURCE_GPIO;
  s_lptim.Init.Input2Source = LPTIM_INPUT2SOURCE_GPIO;
  s_lptim.Init.RepetitionCounter = 0;
  if (HAL_LPTIM_Init(&s_lptim) != HAL_OK) {
    return -2;
  }
  oc.Pulse = (s_lptim.Init.Period + 1u) / 2u;
  oc.OCPolarity = LPTIM_OCPOLARITY_HIGH;
  if (HAL_LPTIM_OC_ConfigChannel(&s_lptim, &oc, LPTIM_CHANNEL_1) != HAL_OK) {
    return -3;
  }
  return 0;
}

void sync_start(void)
{
  (void)HAL_LPTIM_PWM_Start(&s_lptim, LPTIM_CHANNEL_1);
}

void sync_stop(void)
{
  (void)HAL_LPTIM_PWM_Stop(&s_lptim, LPTIM_CHANNEL_1);
}

uint32_t sync_adc_trigger(void)
{
  return ADC_EXTERNALTRIG_LPTIM1_CH1;
}

#endif

uint32_t sync_source(void)
{
  return SSI_SYNC_SRC;
}
