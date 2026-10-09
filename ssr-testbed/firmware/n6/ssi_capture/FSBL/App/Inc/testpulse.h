#ifndef TESTPULSE_H
#define TESTPULSE_H

#include "tx_api.h"

/* Sync test (P4): ~10 ms pulses on PD6 (D7), about 45 per second. Each rising edge is delayed
   by a random 0-2 ms busy-wait: that spans several 8-frame EMG periods (500 us each), so the
   edges land at a nearly uniform phase of that period. */
void testpulse_init(void); /* app_start: pin low, flags created */
void testpulse_thread_entry(ULONG arg);
void testpulse_set(int on); /* any thread */

#endif
