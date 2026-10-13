#ifndef AUDIO_FIR_H
#define AUDIO_FIR_H

#include <stddef.h>
#include <stdint.h>

/* ADMP401 decimation (plan 3): 12-bit ADC codes at 64 kHz -> audio at 16 kHz in the INMP441's
   24-bit scale (one code = 4096), DC removed. Linear-phase FIR, 97 taps (tools/gen_audio_fir.py),
   then a one-pole DC blocker (~2.5 Hz). Pure logic: the caller owns the state. */
#define AFIR_TAPS    97u
#define AFIR_DECIM   4u
#define AFIR_DELAY   ((AFIR_TAPS - 1u) / 2u / AFIR_DECIM) /* 12 outputs = 0.75 ms, fixed latency */
#define AFIR_OUT_MAX ((1 << 23) - 1)

typedef struct {
  int32_t hist[2u * AFIR_TAPS]; /* doubled ring: the last AFIR_TAPS inputs are always contiguous */
  uint32_t head;
  int primed;
  int32_t dc_x1;
  int32_t dc_y1;
} afir_t;

void afir_reset(afir_t *f); /* the next input sample primes the history and the DC blocker */
/* n codes (a multiple of AFIR_DECIM, starting at a multiple of AFIR_DECIM since the reset) ->
   n / AFIR_DECIM outputs. Output j is computed right after input 4j: it shows input 4(j - 12). */
void afir_process(afir_t *f, const uint32_t *codes, size_t n, int32_t *out);

#endif
