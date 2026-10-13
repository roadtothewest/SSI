#include "link_logic.h"

uint32_t link_on_block(link_logic_t *l, int busy)
{
  if (l->state == LINK_IDLE && busy) {
    l->state = LINK_HELD; /* the Pi is clocking zeros: wait for CS to rise */
    return LINK_A_HOLD_NEW;
  }
  if (l->state == LINK_HELD) {
    l->dropped++; /* the held block was never offered */
    if (busy) {
      return LINK_A_RELEASE_CUR | LINK_A_HOLD_NEW;
    }
    l->state = LINK_ARMED;
    l->armed++;
    return LINK_A_RELEASE_CUR | LINK_A_ARM_NEW | LINK_A_DRDY_HIGH;
  }
  if (l->state == LINK_IDLE) {
    l->state = LINK_ARMED;
    l->armed++;
    return LINK_A_ARM_NEW | LINK_A_DRDY_HIGH;
  }
  if (busy) {
    l->dropped++; /* never cut a transfer: the Pi sees the seq jump instead */
    return LINK_A_RELEASE_NEW;
  }
  l->replaced++;
  l->armed++;
  return LINK_A_DRDY_LOW | LINK_A_ABORT | LINK_A_RELEASE_CUR | LINK_A_ARM_NEW | LINK_A_DRDY_HIGH;
}

uint32_t link_on_tx_done(link_logic_t *l)
{
  if (l->state != LINK_ARMED) {
    return 0u;
  }
  l->state = LINK_IDLE;
  l->sent++;
  return LINK_A_RELEASE_CUR | LINK_A_DRDY_LOW;
}

uint32_t link_on_nss_rise(link_logic_t *l)
{
  if (l->state != LINK_HELD) {
    return 0u;
  }
  l->state = LINK_ARMED;
  l->armed++;
  return LINK_A_ARM_CUR | LINK_A_DRDY_HIGH;
}

uint32_t link_on_error(link_logic_t *l, int nss_low)
{
  if (l->state != LINK_ARMED) {
    return 0u;
  }
  l->aborted++; /* restart from byte 0 so the next read starts with AA 55 */
  if (nss_low) {
    l->state = LINK_HELD;
    return LINK_A_DRDY_LOW | LINK_A_ABORT;
  }
  return LINK_A_DRDY_LOW | LINK_A_ABORT | LINK_A_ARM_CUR | LINK_A_DRDY_HIGH;
}
