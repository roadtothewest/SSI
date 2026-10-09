#ifndef SINK_H
#define SINK_H

#include <stdint.h>

#include "tx_api.h"

/* Provisional block consumer (the SPI link replaces it): checks every block as auravoxd on the
   RPi5 does (PROTOCOLO_SPI.md §3, §6), then releases it. */
typedef struct {
  uint32_t rx;      /* blocks received since boot */
  uint32_t crc_err; /* bad sync bytes or CRC-16 */
  uint32_t gap;     /* seq jumps (lost or dropped windows) */
  uint32_t ovf;     /* blocks with flags != 0 (the Pi's "Desbordes") */
} sink_stats_t;     /* one TX_4_ULONG message */

typedef struct {
  TX_QUEUE *in;    /* block pointers from acq */
  TX_QUEUE *stats; /* sink_stats_t every 100 blocks */
} sink_cfg_t;

void sink_configure(const sink_cfg_t *cfg);
void sink_thread_entry(ULONG arg);

#endif
