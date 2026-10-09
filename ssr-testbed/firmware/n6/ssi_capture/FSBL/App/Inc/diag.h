#ifndef DIAG_H
#define DIAG_H

#include <stdint.h>

#include "ssi_config.h"

/* One-second capture of acq's decoded windows, read over SWD by tools/diag.py. The layout of
   s_diag (diag.c) is that tool's contract. Only acq calls these functions. */
#define DIAG_WINDOWS 100u

typedef struct {
  uint32_t state;        /* 0 idle, 1 filling, 2 done (D-cache cleaned) */
  uint32_t first_window; /* k of the first captured window */
  uint32_t n;            /* windows captured */
  uint32_t gaps;         /* discontinuities inside the capture (missing window or new epoch) */
  uint32_t epoch;
  uint32_t reserved[3];
} diag_hdr_t;

void diag_arm(uint32_t min_window);
void diag_feed(uint32_t k, uint8_t epoch, const uint32_t *raw, const int32_t *audio,
               const uint16_t *emg);

#endif
