#include "diag.h"

#include <stddef.h>
#include <string.h>

#include "stm32n6xx_hal.h"

typedef struct {
  diag_hdr_t hdr;
  uint32_t raw[2u * SSI_WIN_AUDIO];                      /* first window, stereo, as received */
  int32_t audio[DIAG_WINDOWS * SSI_WIN_AUDIO];           /* left slot, sign-extended */
  uint16_t emg[DIAG_WINDOWS * SSI_WIN_EMG * SSI_EMG_CH]; /* interleaved ch0, ch1, ch2 */
} diag_buf_t;

_Static_assert(offsetof(diag_buf_t, raw) == 32u, "tools/diag.py layout");
_Static_assert(offsetof(diag_buf_t, audio) == 1312u, "tools/diag.py layout");
_Static_assert(offsetof(diag_buf_t, emg) == 65312u, "tools/diag.py layout");
_Static_assert(sizeof(diag_buf_t) == 77312u, "tools/diag.py layout"); /* 2 kHz EMG: 2000 x 3 */

/* Cacheable RAM (too big for NC): cleaned to SRAM before the debugger may read it. */
static diag_buf_t s_diag __attribute__((aligned(32), used));
static uint32_t s_min;
static uint32_t s_last;

void diag_arm(uint32_t min_window)
{
  s_diag.hdr.state = 1u;
  s_diag.hdr.n = 0u;
  s_diag.hdr.gaps = 0u;
  s_min = min_window;
  SCB_CleanDCache_by_Addr(&s_diag.hdr, (int32_t)sizeof s_diag.hdr); /* no stale "2" over SWD */
}

void diag_feed(uint32_t k, uint8_t epoch, const uint32_t *raw, const int32_t *audio,
               const uint16_t *emg)
{
  diag_hdr_t *h = &s_diag.hdr;
  if (h->state != 1u || k < s_min) {
    return;
  }
  if (h->n == 0u) {
    h->first_window = k;
    h->epoch = epoch;
    memcpy(s_diag.raw, raw, sizeof s_diag.raw);
  } else if (k != s_last + 1u || epoch != h->epoch) {
    h->gaps++;
  }
  s_last = k;
  memcpy(&s_diag.audio[h->n * SSI_WIN_AUDIO], audio, SSI_WIN_AUDIO * sizeof(int32_t));
  memcpy(&s_diag.emg[h->n * SSI_WIN_EMG * SSI_EMG_CH], emg,
         SSI_WIN_EMG * SSI_EMG_CH * sizeof(uint16_t));
  if (++h->n == DIAG_WINDOWS) {
    h->state = 2u;
    SCB_CleanDCache_by_Addr(&s_diag, (int32_t)sizeof s_diag);
  }
}
