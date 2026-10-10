#include "mon.h"

#include <string.h>

#include "acq.h"
#include "led.h"
#include "log.h"
#include "mic_sai.h"
#include "nc_mem.h"
#include "link.h"
#include "stm32n6xx_hal.h"
#include "testpulse.h"

/* Debug mailbox: tools/swd.py writes a command over SWD, mon runs it and writes 0 back.
   NC memory, so debugger and CPU see the same value; NOLOAD, so cleared at thread start. */
enum {
  CMD_NONE = 0,
  CMD_RESTART = 1,   /* new epoch */
  CMD_DIAG = 2,      /* 1 s capture from window 30 (tools/diag.py) */
  CMD_PULSE_ON = 3,  /* D7 test pulses (P4) */
  CMD_PULSE_OFF = 4,
  CMD_SCK_OFF = 5,   /* P7: SCK pin (A2) to analog; the SAI and its FS keep running */
  CMD_SCK_ON = 6,
  CMD_STALL = 7,     /* block acq for 30 ms once: windows must be counted as lost */
  CMD_NSS_PULSE = 9, /* bench: CS low ~20 ms then high on the unwired NSS (link drop/abort paths) */
};
static volatile uint32_t s_mon_dbg_cmd NC_MEM __attribute__((used));

static mon_cfg_t s_cfg;

void mon_configure(const mon_cfg_t *cfg)
{
  s_cfg = *cfg;
}

static void run_cmd(uint32_t cmd)
{
  switch (cmd) {
    case CMD_RESTART:
      acq_request_restart();
      break;
    case CMD_DIAG:
      acq_request_diag();
      break;
    case CMD_PULSE_ON:
      testpulse_set(1);
      break;
    case CMD_PULSE_OFF:
      testpulse_set(0);
      break;
    case CMD_SCK_OFF:
      mic_sai_sck_output(0);
      break;
    case CMD_SCK_ON:
      mic_sai_sck_output(1);
      break;
    case CMD_STALL:
      acq_request_stall();
      break;
    case CMD_NSS_PULSE:
      link_debug_nss_pulse();
      break;
    default:
      break;
  }
  log_printf("CMD n=%lu", (unsigned long)cmd);
}

static void print_stats(uint32_t t, const acq_stats_t *a, const link_stats_t *k)
{
  log_printf("STAT t=%lu ms=%lu ep=%lu win=%lu emgblk=%lu audblk=%lu lost=%lu drop=%lu err=%lu "
             "arm=%lu sent=%lu repl=%lu ldrop=%lu abrt=%lu lerr=%lu",
             (unsigned long)t, (unsigned long)HAL_GetTick(), (unsigned long)a->epoch,
             (unsigned long)a->windows, (unsigned long)a->emg_blocks,
             (unsigned long)a->aud_blocks, (unsigned long)a->lost, (unsigned long)a->drop,
             (unsigned long)a->err, (unsigned long)k->armed, (unsigned long)k->sent,
             (unsigned long)k->replaced, (unsigned long)k->dropped, (unsigned long)k->aborted,
             (unsigned long)k->errors);
  log_printf("SIG t=%lu peak=%lu rms=%lu rslot=%lu e0lo=%u e0hi=%u e1lo=%u e1hi=%u e2lo=%u e2hi=%u",
             (unsigned long)t, (unsigned long)a->peak, (unsigned long)a->rms,
             (unsigned long)a->rslot, (unsigned)a->emg_min[0], (unsigned)a->emg_max[0],
             (unsigned)a->emg_min[1], (unsigned)a->emg_max[1], (unsigned)a->emg_min[2],
             (unsigned)a->emg_max[2]);
}

void mon_thread_entry(ULONG arg)
{
  union {
    acq_stats_t s;
    ULONG raw[16];
  } a;
  union {
    link_stats_t s;
    ULONG raw[8];
  } k;
  uint32_t t = 0u;
  uint32_t idle = 0u;
  (void)arg;
  memset(&k, 0, sizeof k);
  s_mon_dbg_cmd = CMD_NONE;
  for (;;) {
    if (tx_queue_receive(s_cfg.acq_stats, a.raw, TX_TIMER_TICKS_PER_SECOND / 10u) == TX_SUCCESS) {
      while (tx_queue_receive(s_cfg.link_stats, k.raw, TX_NO_WAIT) == TX_SUCCESS) {
        /* keep the newest */
      }
      print_stats(++t, &a.s, &k.s);
      led_toggle(LED_GREEN); /* blinking green = capturing (spec §5) */
      led_set(LED_RED, (a.s.err != 0u) || (k.s.errors != 0u));
      idle = 0u;
    } else if (++idle == 20u) { /* 2 s without data */
      log_printf("IDLE ms=%lu", (unsigned long)HAL_GetTick());
      idle = 0u;
    }
    const uint32_t cmd = s_mon_dbg_cmd;
    if (cmd != CMD_NONE) {
      run_cmd(cmd);
      s_mon_dbg_cmd = CMD_NONE;
    }
  }
}
