#ifndef ACQ_H
#define ACQ_H

#include <stdint.h>

#include "ssi_config.h"
#include "tx_api.h"

/* Requests to acq (any thread), on the same flags group as the CAP_EVT_* driver events. */
#define ACQ_EVT_RESTART 0x10u /* stop and restart the capture: new epoch, indices from 0 */
#define ACQ_EVT_DIAG    0x20u /* arm a 1 s diag capture from the first valid-audio window */
#define ACQ_EVT_STALL   0x40u /* debug: block acq for 30 ms once (tests the loss accounting) */
#define ACQ_EVT_HANG    0x80u /* debug: block acq for 2 s (tests the watchdog) */

typedef struct {
  uint32_t windows;    /* blocks queued since boot */
  uint32_t emg_blocks; /* windows completed in the current epoch */
  uint32_t aud_blocks;
  uint32_t lost;       /* windows overwritten before packaging, since boot */
  uint32_t drop;       /* blocks dropped (pool or queue full), since boot */
  uint32_t err;        /* SAI + ADC/DMA error callbacks, since boot */
  uint32_t peak;       /* last 100 windows: max |audio| */
  uint32_t rms;        /* last 100 windows: audio rms */
  uint32_t rslot;      /* last 100 windows: frames with right-slot data (must be 0) */
  uint16_t emg_min[SSI_EMG_CH];
  uint16_t emg_max[SSI_EMG_CH];
  uint32_t epoch;
} acq_stats_t;         /* one TX_16_ULONG message (64 bytes max) */

typedef struct {
  TX_EVENT_FLAGS_GROUP *flags; /* CAP_EVT_* from the drivers + ACQ_EVT_* requests */
  TX_BLOCK_POOL *pool;         /* PKT_SIZE blocks */
  TX_QUEUE *out;               /* packet pointers, TX_1_ULONG */
  TX_QUEUE *stats;             /* acq_stats_t every 100 windows, TX_16_ULONG */
  TX_EVENT_FLAGS_GROUP *out_flags; /* consumer to wake after each queued block (or TX_NULL) */
  ULONG out_flag;
} acq_cfg_t;

void acq_configure(const acq_cfg_t *cfg); /* before the thread runs */
void acq_thread_entry(ULONG arg);
void acq_request_restart(void);
void acq_request_diag(void);
void acq_request_stall(void);
void acq_request_hang(void);
uint32_t acq_loops(void); /* increments on every pass of the acq thread (watchdog) */

#endif
