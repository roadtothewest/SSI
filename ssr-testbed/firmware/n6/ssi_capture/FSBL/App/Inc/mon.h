#ifndef MON_H
#define MON_H

#include "tx_api.h"

typedef struct {
  TX_QUEUE *acq_stats;  /* acq_stats_t, TX_16_ULONG */
  TX_QUEUE *link_stats; /* link_stats_t, TX_8_ULONG */
} mon_cfg_t;

void mon_configure(const mon_cfg_t *cfg); /* before the thread runs */
void mon_thread_entry(ULONG arg);

#endif
