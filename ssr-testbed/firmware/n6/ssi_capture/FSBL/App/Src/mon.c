#include "mon.h"

#include "audio_decode.h"
#include "led.h"
#include "log.h"
#include "mic_sai.h"
#include "ssi_config.h"
#include "stm32n6xx_hal.h"

#define MS_PER_TICK (1000u / TX_TIMER_TICKS_PER_SECOND)

/* Task 3 probe: last complete audio window, read straight from the DMA buffer. Good enough
   once per second; acq (Task 5) copies and validates windows properly. */
static void audio_probe(uint32_t t)
{
  const uint32_t blk = mic_sai_blocks_done();
  uint32_t peak = 0u;
  uint32_t rslot = 0u;
  uint32_t raw0 = 0u;
  if (blk > 0u) {
    const uint32_t *w = mic_sai_window(blk - 1u);
    raw0 = w[0];
    for (uint32_t i = 0; i < SSI_WIN_AUDIO; i++) {
      const int32_t s = audio_sign_extend24(w[2u * i]);
      const uint32_t a = (uint32_t)(s < 0 ? -s : s);
      if (a > peak) {
        peak = a;
      }
    }
    rslot = audio_right_activity(w, SSI_WIN_AUDIO);
  }
  log_printf("AUD t=%lu blk=%lu err=%lu peak=%lu rslot=%lu raw0=%lu", (unsigned long)t,
             (unsigned long)blk, (unsigned long)mic_sai_errors(), (unsigned long)peak,
             (unsigned long)rslot, (unsigned long)raw0);
}

void mon_thread_entry(ULONG arg)
{
  (void)arg;
  const int init = mic_sai_init(TX_NULL, 0u, 0u);
  const int start = (init == 0) ? mic_sai_start() : -99;
  log_printf("INIT mic=%d start=%d hse=%lu sai_ck=%lu", init, start,
             (unsigned long)mic_sai_hse_mode(), (unsigned long)mic_sai_clock_hz());
  for (uint32_t i = 1u;; i++) {
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 10u);
    if (i % 5u == 0u) {
      led_toggle(LED_GREEN);
    }
    if (i % 10u == 0u) {
      log_printf("TICK t=%lu tx_ms=%lu hal_ms=%lu", (unsigned long)(i / 10u),
                 (unsigned long)(tx_time_get() * MS_PER_TICK), (unsigned long)HAL_GetTick());
      audio_probe(i / 10u);
    }
  }
}
