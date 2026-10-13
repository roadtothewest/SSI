#ifndef LINK_H
#define LINK_H

#include <stdint.h>

#include "tx_api.h"

/* Link to the RPi5, ssr-testbed/firmware/PROTOCOLO_SPI.md §4: SPI5 slave, TX only, mode 0,
   8 bits, MSB first, hardware NSS (D10..D13 = PA3 NSS, PG2 MOSI, PH8 MISO, PE15 SCK), one
   538-byte block per DMA transfer, DRDY on PH5 (D4). The state machine is link_logic. */
#define LINK_EVT_BLOCK   0x01u /* acq queued a block */
#define LINK_EVT_TX_DONE 0x02u /* ISR: the armed block was sent */
#define LINK_EVT_NSS     0x04u /* ISR: CS rose */
#define LINK_EVT_ERROR   0x08u /* ISR: SPI or DMA error */

typedef struct {
  uint32_t armed;    /* blocks offered (DRDY rising edges) */
  uint32_t sent;     /* complete transfers */
  uint32_t replaced; /* unread blocks replaced by a newer one */
  uint32_t dropped;  /* blocks discarded during a transfer */
  uint32_t aborted;  /* incomplete transfers or errors, re-armed from byte 0 */
  uint32_t errors;   /* SPI/DMA error callbacks and failed arms */
} link_stats_t;      /* sent as one TX_8_ULONG message */

typedef struct {
  TX_QUEUE *in;                /* block pointers from acq (TX_1_ULONG) */
  TX_EVENT_FLAGS_GROUP *flags; /* LINK_EVT_*: acq sets LINK_EVT_BLOCK after queueing */
  TX_QUEUE *stats;             /* link_stats_t every 100 blocks armed (TX_8_ULONG) */
} link_cfg_t;

void link_configure(const link_cfg_t *cfg); /* before the thread runs */
void link_thread_entry(ULONG arg);
uint32_t link_loops(void);       /* increments on every pass of the link thread (watchdog) */
void link_debug_nss_pulse(void); /* bench: pull the unwired NSS low ~20 ms, then high */

#endif
