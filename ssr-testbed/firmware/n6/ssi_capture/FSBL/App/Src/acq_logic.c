#include "acq_logic.h"

acq_step_t acq_select(uint32_t *next, uint32_t emg_done, uint32_t aud_done, uint32_t *lost,
                      uint32_t *k)
{
  const uint32_t lo = (emg_done < aud_done) ? emg_done : aud_done;
  const uint32_t hi = (emg_done < aud_done) ? aud_done : emg_done;
  if (lo == 0u || lo - 1u < *next) {
    return ACQ_NONE;
  }
  const uint32_t newest = lo - 1u; /* newest window complete in both streams */
  if (newest > *next || hi > newest + 1u) {
    /* Older windows are gone; 'newest' too if the faster stream is writing over it. */
    const uint32_t first_intact = (hi > newest + 1u) ? newest + 1u : newest;
    *lost += first_intact - *next;
    *next = first_intact;
    return ACQ_SKIP;
  }
  *k = newest;
  *next = newest + 1u;
  return ACQ_BUILD;
}

uint32_t acq_isqrt64(uint64_t v)
{
  uint64_t r = 0u;
  uint64_t bit = 1ull << 62;
  while (bit > v) {
    bit >>= 2;
  }
  while (bit != 0u) {
    if (v >= r + bit) {
      v -= r + bit;
      r = (r >> 1) + bit;
    } else {
      r >>= 1;
    }
    bit >>= 2;
  }
  return (uint32_t)r;
}
