#include <math.h>
#include <stdlib.h>
#include <string.h>

#include "audio_fir.h"
#include "test_util.h"

#define FS_IN  64000.0
#define N_IN   64000u /* 1 s of ADC codes */
#define N_OUT  (N_IN / AFIR_DECIM)
#define SCALE  4096.0 /* one ADC code in the 24-bit output scale */
#define PI     3.14159265358979323846

static uint32_t s_in[N_IN];
static int32_t s_out[N_OUT];
static int32_t s_out2[N_OUT];

static void sine(double f, double amp, double bias)
{
  for (uint32_t n = 0; n < N_IN; n++) {
    s_in[n] = (uint32_t)lround(bias + amp * sin(2.0 * PI * f * n / FS_IN));
  }
}

static void run(void)
{
  afir_t f;
  afir_reset(&f);
  afir_process(&f, s_in, N_IN, s_out);
}

/* RMS of outputs [from, N_OUT): 12000 outputs = whole periods of 1 kHz and of the 4 kHz aliases. */
static double rms_tail(uint32_t from)
{
  double s = 0.0;
  for (uint32_t j = from; j < N_OUT; j++) {
    s += (double)s_out[j] * s_out[j];
  }
  return sqrt(s / (N_OUT - from));
}

static double db(double x, double ref)
{
  return 20.0 * log10(x / ref + 1e-30);
}

int main(void)
{
  /* constant input (the ADMP401 at rest, ~1.65 V): primed, so no start-up step at all */
  for (uint32_t n = 0; n < N_IN; n++) {
    s_in[n] = 2041u;
  }
  run();
  int32_t mx = 0;
  for (uint32_t j = 0; j < N_OUT; j++) {
    mx = abs(s_out[j]) > mx ? abs(s_out[j]) : mx;
  }
  CHECK(mx <= 1);

  /* the bias moves by 500 codes: the DC blocker (~2.5 Hz) removes it within 0.5 s */
  for (uint32_t n = N_IN / 4u; n < N_IN; n++) {
    s_in[n] = 2541u;
  }
  run();
  CHECK(abs(s_out[N_OUT - 1u]) < 2000); /* < 0.5 code */

  /* 1 kHz passes at unity gain: 1000 codes peak -> 1000 * 4096 / sqrt(2) RMS */
  sine(1000.0, 1000.0, 2041.0);
  run();
  const double ref = 1000.0 * SCALE / sqrt(2.0);
  const double g1k = db(rms_tail(N_OUT / 4u), ref);
  CHECK(fabs(g1k) < 0.1);

  /* 12 kHz and 20 kHz would alias to 4 kHz at 16 kHz: rejected by at least 60 dB */
  sine(12000.0, 1000.0, 2041.0);
  run();
  CHECK(db(rms_tail(N_OUT / 4u), ref) < -60.0);
  sine(20000.0, 1000.0, 2041.0);
  run();
  CHECK(db(rms_tail(N_OUT / 4u), ref) < -60.0);

  /* two 10 ms DMA halves give exactly what one call gives */
  sine(1000.0, 1000.0, 2041.0);
  run();
  afir_t f;
  afir_reset(&f);
  afir_process(&f, s_in, 640u, s_out2);
  afir_process(&f, s_in + 640u, 640u, s_out2 + 160u);
  CHECK(memcmp(s_out, s_out2, 320u * sizeof(int32_t)) == 0);

  /* latency: an impulse at ADC sample 0 shows up only in output 12 (48 samples = 0.75 ms) */
  for (uint32_t n = 0; n < N_IN; n++) {
    s_in[n] = 2048u;
  }
  afir_reset(&f);
  afir_process(&f, s_in, 4u, s_out); /* prime with the rest level */
  s_in[0] = 3048u;
  afir_process(&f, s_in, 640u, s_out);
  uint32_t at = 0;
  for (uint32_t j = 1; j < 160u; j++) {
    if (abs(s_out[j]) > abs(s_out[at])) {
      at = j;
    }
  }
  CHECK_EQ(at, AFIR_DELAY);
  CHECK_EQ(AFIR_DELAY, 12);
  CHECK(labs(s_out[12] - 1024000L) < 2000L); /* 1000 codes * 4096 * h[48] (= 1/4) */
  for (uint32_t j = 0; j < 12u; j++) {
    CHECK_EQ(s_out[j], 0);
  }

  /* full-scale steps (0 <-> 4095 at 1 kHz) overshoot (Gibbs): clamped, never overflow */
  for (uint32_t n = 0; n < N_IN; n++) {
    s_in[n] = ((n / 32u) & 1u) ? 4095u : 0u;
  }
  run();
  for (uint32_t j = 0; j < N_OUT; j++) {
    CHECK(s_out[j] <= AFIR_OUT_MAX && s_out[j] >= -AFIR_OUT_MAX);
  }
  TEST_END();
}
