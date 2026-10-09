#ifndef ACQ_LOGIC_H
#define ACQ_LOGIC_H

#include <stdint.h>

typedef enum { ACQ_NONE = 0, ACQ_BUILD, ACQ_SKIP } acq_step_t;

/* Both DMA streams are double-buffered: window k lives in half k % 2 and stays intact
   while the stream's completed-window count is exactly k + 1.
   ACQ_BUILD: window *k is complete and intact in both streams; *next = *k + 1.
   ACQ_SKIP:  windows were overwritten before packaging; *lost grows, *next advances.
   ACQ_NONE:  window *next is not complete in both streams yet. */
acq_step_t acq_select(uint32_t *next, uint32_t emg_done, uint32_t aud_done, uint32_t *lost,
                      uint32_t *k);

/* floor(sqrt(v)): audio RMS in acq's statistics. */
uint32_t acq_isqrt64(uint64_t v);

#endif
