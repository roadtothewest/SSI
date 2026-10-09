#include "mon.h"

#include "capture.h"
#include "emg_adc.h"
#include "led.h"
#include "log.h"
#include "mic_sai.h"

void mon_thread_entry(ULONG arg)
{
  (void)arg;
  const int init = capture_init(TX_NULL); /* nobody waits on the flags yet */
  const int start = (init == 0) ? capture_start() : -99;
  log_printf("START rc=%d epoch=%u", start, (unsigned)capture_epoch());
  for (uint32_t i = 1u;; i++) {
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 10u);
    if (i % 5u == 0u) {
      led_toggle(LED_GREEN);
    }
    if (i % 10u == 0u) {
      const uint32_t eb = emg_adc_blocks_done();
      const uint32_t *w = (eb > 0u) ? emg_adc_window(eb - 1u) : TX_NULL;
      log_printf("CAP t=%lu emgblk=%lu audblk=%lu eerr=%lu aerr=%lu e0=%lu e1=%lu e2=%lu",
                 (unsigned long)(i / 10u), (unsigned long)eb, (unsigned long)mic_sai_blocks_done(),
                 (unsigned long)emg_adc_errors(), (unsigned long)mic_sai_errors(),
                 (unsigned long)(w ? w[0] : 0u), (unsigned long)(w ? w[1] : 0u),
                 (unsigned long)(w ? w[2] : 0u));
    }
  }
}
