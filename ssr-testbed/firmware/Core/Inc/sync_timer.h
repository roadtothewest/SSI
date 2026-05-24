#ifndef __SYNC_TIMER_H
#define __SYNC_TIMER_H

#include "main.h"

#define TIMER_FREQ_HZ             1000000

bool sync_timer_init(void);
uint32_t sync_timer_get_us(void);
void sync_timer_reset(void);

#endif
