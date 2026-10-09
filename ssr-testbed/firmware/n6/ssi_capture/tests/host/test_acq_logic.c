#include "acq_logic.h"
#include "test_util.h"

static acq_step_t step(uint32_t *next, uint32_t e, uint32_t a, uint32_t *lost, uint32_t *k)
{
  *k = 0xFFFFFFFFu;
  return acq_select(next, e, a, lost, k);
}

int main(void)
{
  uint32_t next, lost, k;

  /* nothing completed yet */
  next = 0; lost = 0;
  CHECK_EQ(step(&next, 0, 0, &lost, &k), ACQ_NONE);
  CHECK_EQ(step(&next, 1, 0, &lost, &k), ACQ_NONE); /* audio window 0 pending */

  /* steady state: both streams finished window 0 */
  CHECK_EQ(step(&next, 1, 1, &lost, &k), ACQ_BUILD);
  CHECK_EQ(k, 0);
  CHECK_EQ(next, 1);
  CHECK_EQ(lost, 0);
  CHECK_EQ(step(&next, 1, 1, &lost, &k), ACQ_NONE); /* already built */

  /* audio one window ahead of EMG is normal while the EMG half is in flight */
  CHECK_EQ(step(&next, 1, 2, &lost, &k), ACQ_NONE);
  CHECK_EQ(step(&next, 2, 2, &lost, &k), ACQ_BUILD);
  CHECK_EQ(k, 1);

  /* consumer starved: window 2 overwritten in audio (a = 4 means window 3 done, 4 in flight
     in half 0 = window 2's half) */
  next = 2; lost = 0;
  CHECK_EQ(step(&next, 3, 4, &lost, &k), ACQ_SKIP);
  CHECK_EQ(lost, 1);
  CHECK_EQ(next, 3);
  CHECK_EQ(step(&next, 3, 4, &lost, &k), ACQ_NONE); /* EMG window 3 not complete yet */
  CHECK_EQ(step(&next, 4, 4, &lost, &k), ACQ_BUILD);
  CHECK_EQ(k, 3);

  /* long starvation: jump to the newest window still intact in both streams */
  next = 0; lost = 0;
  CHECK_EQ(step(&next, 5, 5, &lost, &k), ACQ_SKIP);
  CHECK_EQ(lost, 4);
  CHECK_EQ(next, 4);
  CHECK_EQ(step(&next, 5, 5, &lost, &k), ACQ_BUILD);
  CHECK_EQ(k, 4);

  /* EMG two windows ahead of audio: window overwritten in EMG */
  next = 0; lost = 0;
  CHECK_EQ(step(&next, 2, 1, &lost, &k), ACQ_SKIP);
  CHECK_EQ(lost, 1);
  CHECK_EQ(next, 1);

  /* integer square root for the audio RMS */
  CHECK_EQ(acq_isqrt64(0u), 0);
  CHECK_EQ(acq_isqrt64(15u), 3);
  CHECK_EQ(acq_isqrt64(16u), 4);
  CHECK_EQ(acq_isqrt64(8388607ull * 8388607ull), 8388607);
  CHECK_EQ(acq_isqrt64(UINT64_MAX), 4294967295ll);
  TEST_END();
}
