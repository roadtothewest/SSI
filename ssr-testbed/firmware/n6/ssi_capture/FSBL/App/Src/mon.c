#include "mon.h"

#include "led.h"
#include "log.h"
#include "stm32n6xx_hal.h"

#define MS_PER_TICK (1000u / TX_TIMER_TICKS_PER_SECOND)

void mon_thread_entry(ULONG arg)
{
  (void)arg;
  for (uint32_t i = 1u;; i++) {
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 10u);
    if (i % 5u == 0u) {
      led_toggle(LED_GREEN);
    }
    if (i % 10u == 0u) {
      log_printf("TICK t=%lu tx_ms=%lu hal_ms=%lu", (unsigned long)(i / 10u),
                 (unsigned long)(tx_time_get() * MS_PER_TICK), (unsigned long)HAL_GetTick());
    }
  }
}
