#include "capture.h"

#include "emg_adc.h"
#include "log.h"
#include "mic_sai.h"
#include "sync.h"

static uint8_t s_epoch;
static int s_running;

int capture_init(TX_EVENT_FLAGS_GROUP *flags)
{
  int step = 1;
  int rc = mic_sai_init(flags, CAP_EVT_AUD, CAP_EVT_ERR);
  if (rc == 0) {
    step = 2;
    rc = emg_adc_init(flags, CAP_EVT_EMG, CAP_EVT_ERR, sync_adc_trigger());
  }
  if (rc == 0) {
    step = 3;
    rc = sync_init();
  }
  log_printf("INIT cap=%d step=%d sync=%lu hse=%lu sai_ck=%lu adc_ck=%lu", rc, (rc == 0) ? 0 : step,
             (unsigned long)sync_source(), (unsigned long)mic_sai_hse_mode(),
             (unsigned long)mic_sai_clock_hz(), (unsigned long)emg_adc_clock_hz());
  return rc;
}

int capture_start(void)
{
  if (s_running) {
    capture_stop();
  }
  s_epoch++;
  /* Fixed order, fixed c: the ADC waits for its trigger, the trigger source is armed, and only
     then the SAI produces its first FS edge. */
  if (emg_adc_start() != 0) {
    return -1;
  }
  sync_start();
  if (mic_sai_start() != 0) {
    sync_stop();
    emg_adc_stop();
    return -2;
  }
  s_running = 1;
  return 0;
}

void capture_stop(void)
{
  mic_sai_stop(); /* no FS edges after this: no partial EMG sequence */
  sync_stop();
  emg_adc_stop();
  s_running = 0;
}

uint8_t capture_epoch(void)
{
  return s_epoch;
}
