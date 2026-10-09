#include "acq.h"

#include <string.h>

#include "acq_logic.h"
#include "audio_decode.h"
#include "avx_block.h"
#include "capture.h"
#include "diag.h"
#include "emg_adc.h"
#include "log.h"
#include "mic_sai.h"

_Static_assert(sizeof(acq_stats_t) <= 16u * sizeof(ULONG), "acq_stats_t must fit TX_16_ULONG");
_Static_assert(SSI_WIN_EMG == AVX_TUPLES && SSI_WIN_AUDIO == AVX_TUPLES * AVX_VOZ_PER_TUPLE &&
                   SSI_EMG_CH == AVX_ADC_CH,
               "a 10 ms window must be exactly one SPI block");

#define STATS_WINDOWS   100u                                /* one stats message per second */
#define DIAG_MIN_WINDOW (SSI_AUDIO_STARTUP / SSI_WIN_AUDIO) /* 30: after the INMP441 start-up */
#define WINDOW_US       (AVX_TUPLES * AVX_TUPLE_US)         /* 10000 */

static acq_cfg_t s_cfg;
static uint32_t s_raw[2u * SSI_WIN_AUDIO];
static int32_t s_audio[SSI_WIN_AUDIO];
static uint16_t s_emg[SSI_WIN_EMG * SSI_EMG_CH];

static uint32_t s_next;     /* next window to package (current epoch) */
static uint32_t s_seq_base; /* seq of window 0 of the current epoch: seq = s_seq_base + k */
static uint16_t s_pending;  /* AVX_F_* events not yet reported in a block */
static uint32_t s_adc_err;  /* driver error counts already reported */
static uint32_t s_sai_err;
static int s_started;
static uint8_t s_epoch;
static acq_stats_t s_st;
static uint64_t s_sq;   /* audio sum of squares in the stats period */
static uint32_t s_nwin; /* windows in the stats period */

void acq_configure(const acq_cfg_t *cfg)
{
  s_cfg = *cfg;
}

void acq_request_restart(void)
{
  (void)tx_event_flags_set(s_cfg.flags, ACQ_EVT_RESTART, TX_OR);
}

void acq_request_diag(void)
{
  (void)tx_event_flags_set(s_cfg.flags, ACQ_EVT_DIAG, TX_OR);
}

static void period_reset(void)
{
  s_st.peak = 0u;
  s_st.rslot = 0u;
  s_sq = 0u;
  s_nwin = 0u;
  for (uint32_t c = 0; c < SSI_EMG_CH; c++) {
    s_st.emg_min[c] = 0xFFFFu;
    s_st.emg_max[c] = 0u;
  }
}

static void start_capture(void)
{
  if (s_started) {
    /* Restart: leave one seq unused and set bit0, so the RPi5 sees the discontinuity. */
    s_seq_base += s_next + 1u;
    s_pending |= AVX_F_ADC_LOST;
  }
  const int rc = capture_start();
  if (rc != 0) {
    log_printf("ERR capture_start=%d", rc); /* streams stopped: logging costs no data */
  }
  s_started = 1;
  s_epoch = capture_epoch();
  s_next = 0u;
  period_reset();
}

static void check_errors(void)
{
  const uint32_t adc = emg_adc_errors();
  const uint32_t sai = mic_sai_errors();
  if (adc != s_adc_err) {
    s_adc_err = adc;
    s_pending |= AVX_F_ADC_LOST;
  }
  if (sai != s_sai_err) {
    s_sai_err = sai;
    s_pending |= AVX_F_SAI_ERR;
  }
}

static void update_stats(void)
{
  for (uint32_t i = 0; i < SSI_WIN_AUDIO; i++) {
    const int64_t s = s_audio[i];
    const uint32_t a = (uint32_t)(s < 0 ? -s : s);
    if (a > s_st.peak) {
      s_st.peak = a;
    }
    s_sq += (uint64_t)(s * s);
  }
  s_st.rslot += audio_right_activity(s_raw, SSI_WIN_AUDIO);
  for (uint32_t i = 0; i < SSI_WIN_EMG * SSI_EMG_CH; i++) {
    const uint32_t c = i % SSI_EMG_CH;
    if (s_emg[i] < s_st.emg_min[c]) {
      s_st.emg_min[c] = s_emg[i];
    }
    if (s_emg[i] > s_st.emg_max[c]) {
      s_st.emg_max[c] = s_emg[i];
    }
  }
}

static void build_window(uint32_t k)
{
  const uint32_t *ew = emg_adc_window(k);
  memcpy(s_raw, mic_sai_window(k), sizeof s_raw);
  for (uint32_t i = 0; i < SSI_WIN_EMG * SSI_EMG_CH; i++) {
    s_emg[i] = (uint16_t)ew[i];
  }
  /* Copy first, then check: a stream past k + 1 may have started rewriting window k's half
     during the copy. The window is lost; its seq is never sent, so the RPi5 sees a jump. */
  if (mic_sai_blocks_done() > k + 1u || emg_adc_blocks_done() > k + 1u) {
    s_st.lost++;
    s_pending |= AVX_F_ADC_LOST;
    return;
  }
  audio_extract_left(s_raw, s_audio, SSI_WIN_AUDIO);
  update_stats();
  diag_feed(k, s_epoch, s_raw, s_audio, s_emg);

  VOID *blk;
  if (tx_block_allocate(s_cfg.pool, &blk, TX_NO_WAIT) != TX_SUCCESS) {
    s_st.drop++; /* SPI backpressure: the seq jump reports it (spec §7) */
    return;
  }
  const uint32_t seq = s_seq_base + k;
  const uint16_t flags = s_pending;
  avx_block_build((uint8_t *)blk, seq, seq * WINDOW_US, flags, s_emg, s_audio);
  s_pending = 0u;
  ULONG msg = (ULONG)(uintptr_t)blk;
  if (tx_queue_send(s_cfg.out, &msg, TX_NO_WAIT) != TX_SUCCESS) {
    (void)tx_block_release(blk);
    s_pending |= flags; /* not sent: report the events on the next block */
    s_st.drop++;
    return;
  }
  s_st.windows++;
}

static void stats_push(void)
{
  union {
    acq_stats_t s;
    ULONG raw[16];
  } m;
  memset(&m, 0, sizeof m);
  s_st.emg_blocks = emg_adc_blocks_done();
  s_st.aud_blocks = mic_sai_blocks_done();
  s_st.err = s_adc_err + s_sai_err;
  s_st.rms = acq_isqrt64(s_sq / ((uint64_t)s_nwin * SSI_WIN_AUDIO));
  s_st.epoch = s_epoch;
  m.s = s_st;
  (void)tx_queue_send(s_cfg.stats, m.raw, TX_NO_WAIT); /* if mon lags, skip: never block acq */
  period_reset();
}

void acq_thread_entry(ULONG arg)
{
  (void)arg;
  if (capture_init(s_cfg.flags) != 0) {
    (void)tx_thread_suspend(tx_thread_identify()); /* the INIT line names the failing step */
  }
  start_capture();
  for (;;) {
    ULONG got = 0u;
    (void)tx_event_flags_get(s_cfg.flags,
                             CAP_EVT_EMG | CAP_EVT_AUD | CAP_EVT_ERR | ACQ_EVT_RESTART | ACQ_EVT_DIAG,
                             TX_OR_CLEAR, &got, TX_TIMER_TICKS_PER_SECOND / 10u);
    if ((got & ACQ_EVT_RESTART) != 0u) {
      start_capture();
    }
    if ((got & ACQ_EVT_DIAG) != 0u) {
      diag_arm(DIAG_MIN_WINDOW);
    }
    check_errors(); /* error recovery (stop, ERROR state, new epoch) is the link/ctrl's job */
    for (;;) {
      uint32_t k = 0u;
      uint32_t lost = 0u;
      const acq_step_t step =
          acq_select(&s_next, emg_adc_blocks_done(), mic_sai_blocks_done(), &lost, &k);
      if (lost != 0u) {
        s_st.lost += lost;
        s_pending |= AVX_F_ADC_LOST;
      }
      if (step == ACQ_NONE) {
        break;
      }
      if (step == ACQ_BUILD) {
        build_window(k);
        if (++s_nwin == STATS_WINDOWS) {
          stats_push();
        }
      }
    }
  }
}
