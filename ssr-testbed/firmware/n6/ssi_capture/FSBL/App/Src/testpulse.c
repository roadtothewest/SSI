#include "testpulse.h"

#include "stm32n6xx_hal.h"

#define TP_ON 0x1u

static TX_EVENT_FLAGS_GROUP s_evt;
static uint32_t s_lcg = 12345u;

static uint32_t rnd(void)
{
  s_lcg = s_lcg * 1664525u + 1013904223u;
  return s_lcg >> 8;
}

void testpulse_init(void)
{
  GPIO_InitTypeDef g = {0};
  (void)tx_event_flags_create(&s_evt, "tp");
  __HAL_RCC_GPIOD_CLK_ENABLE();
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_6, GPIO_PIN_RESET);
  g.Pin = GPIO_PIN_6;
  g.Mode = GPIO_MODE_OUTPUT_PP;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOD, &g);
}

void testpulse_set(int on)
{
  if (on) {
    (void)tx_event_flags_set(&s_evt, TP_ON, TX_OR);
  } else {
    (void)tx_event_flags_set(&s_evt, ~(ULONG)TP_ON, TX_AND);
  }
}

void testpulse_thread_entry(ULONG arg)
{
  (void)arg;
  for (;;) {
    ULONG got;
    (void)tx_event_flags_get(&s_evt, TP_ON, TX_OR, &got, TX_WAIT_FOREVER); /* blocks while off */
    tx_thread_sleep(1u); /* low: ~10 ms */
    /* 0 to ~2 ms (depends on CPU speed and -O level; it only has to span >> 250 us). */
    for (volatile uint32_t n = rnd() % 120000u; n != 0u; n--) {
    }
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_6, GPIO_PIN_SET);
    tx_thread_sleep(1u); /* high until the next 10 ms tick */
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_6, GPIO_PIN_RESET);
  }
}
