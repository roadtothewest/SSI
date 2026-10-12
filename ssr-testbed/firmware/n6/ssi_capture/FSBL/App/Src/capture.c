#include "capture.h"

#include "emg_adc.h"
#include "hse.h"
#include "log.h"
#include "mic.h"
#include "ssi_config.h"
#include "sync.h"

static uint8_t s_epoch;
static int s_running;

int capture_init(TX_EVENT_FLAGS_GROUP *flags)
{
  int step = 1;
#if SSI_MIC_SRC == SSI_MIC_ANALOG
  /* ADC2 (microphone) uses the ADC12 clock and settings that emg_adc_init configures. */
  int rc = emg_adc_init(flags, CAP_EVT_EMG, CAP_EVT_ERR, sync_adc_trigger());
  if (rc == 0) {
    step = 2;
    rc = mic_init(flags, CAP_EVT_AUD, CAP_EVT_ERR);
  }
#else
  int rc = mic_init(flags, CAP_EVT_AUD, CAP_EVT_ERR);
  if (rc == 0) {
    step = 2;
    rc = emg_adc_init(flags, CAP_EVT_EMG, CAP_EVT_ERR, sync_adc_trigger());
  }
#endif
  if (rc == 0) {
    step = 3;
    rc = sync_init();
  }
  log_printf("INIT cap=%d step=%d sync=%lu mic=%d hse=%lu mic_ck=%lu adc_ck=%lu", rc,
             (rc == 0) ? 0 : step, (unsigned long)sync_source(), SSI_MIC_SRC,
             (unsigned long)hse_mode(), (unsigned long)mic_clock_hz(),
             (unsigned long)emg_adc_clock_hz());
  return rc;
}

int capture_start(void)
{
  if (s_running) {
    capture_stop();
  }
  s_epoch++;
  if (emg_adc_start() != 0) {
    return -1;
  }
#if SSI_MIC_SRC == SSI_MIC_ANALOG
  /* Fixed order, fixed c: both ADCs wait for their triggers, then sync starts both LPTIMs. */
  if (mic_start() != 0) {
    emg_adc_stop();
    return -2;
  }
  sync_start();
#else
  /* Fixed order, fixed c: the ADC waits for its trigger, the trigger source is armed, and only
     then the SAI produces its first FS edge. */
  sync_start();
  if (mic_start() != 0) {
    sync_stop();
    emg_adc_stop();
    return -2;
  }
#endif
  s_running = 1;
  return 0;
}

void capture_stop(void)
{
#if SSI_MIC_SRC == SSI_MIC_ANALOG
  sync_stop(); /* no triggers after this: no partial sequence in either ADC */
  mic_stop();
#else
  mic_stop(); /* no FS edges after this: no partial EMG sequence */
  sync_stop();
#endif
  emg_adc_stop();
  s_running = 0;
}

uint8_t capture_epoch(void)
{
  return s_epoch;
}
