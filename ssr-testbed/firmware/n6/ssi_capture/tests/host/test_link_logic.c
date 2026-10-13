#include "link_logic.h"
#include "test_util.h"

int main(void)
{
  link_logic_t l = {0};

  /* idle: a block is armed and DRDY rises (it was low since the last transfer) */
  CHECK_EQ(link_on_block(&l, 0), LINK_A_ARM_NEW | LINK_A_DRDY_HIGH);
  CHECK_EQ(l.state, LINK_ARMED);
  CHECK_EQ(l.armed, 1);

  /* the Pi reads all 538 bytes: block freed, DRDY falls, link idle */
  CHECK_EQ(link_on_tx_done(&l), LINK_A_RELEASE_CUR | LINK_A_DRDY_LOW);
  CHECK_EQ(l.state, LINK_IDLE);
  CHECK_EQ(l.sent, 1);
  CHECK_EQ(link_on_nss_rise(&l), 0); /* CS release after a full transfer: nothing to do */
  CHECK_EQ(link_on_tx_done(&l), 0);     /* spurious completion while idle */

  /* unread block and a newer one ready, CS high: replace it with a fresh DRDY edge (§4) */
  CHECK_EQ(link_on_block(&l, 0), LINK_A_ARM_NEW | LINK_A_DRDY_HIGH);
  CHECK_EQ(link_on_block(&l, 0),
           LINK_A_DRDY_LOW | LINK_A_ABORT | LINK_A_RELEASE_CUR | LINK_A_ARM_NEW | LINK_A_DRDY_HIGH);
  CHECK_EQ(l.state, LINK_ARMED);
  CHECK_EQ(l.replaced, 1);
  CHECK_EQ(l.armed, 3);

  /* a newer block while the Pi is reading (CS low): finish the transfer, drop the new block */
  CHECK_EQ(link_on_block(&l, 1), LINK_A_RELEASE_NEW);
  CHECK_EQ(l.dropped, 1);
  CHECK_EQ(l.state, LINK_ARMED);

  /* CS rises in the middle of a transfer (glitches on the CS line): not an end, the 538-byte
     count ends the transfer (P5, 2026-10-12/13) */
  CHECK_EQ(link_on_nss_rise(&l), 0);
  CHECK_EQ(l.aborted, 0);
  CHECK_EQ(l.state, LINK_ARMED);

  /* idle CS edges are ignored */
  CHECK_EQ(link_on_tx_done(&l), LINK_A_RELEASE_CUR | LINK_A_DRDY_LOW);
  CHECK_EQ(link_on_nss_rise(&l), 0);

  /* a Pi that reads every block: armed == sent, nothing replaced */
  link_logic_t r = {0};
  for (int i = 0; i < 100; i++) {
    link_on_block(&r, 0);
    link_on_tx_done(&r);
  }
  CHECK_EQ(r.armed, 100);
  CHECK_EQ(r.sent, 100);
  CHECK_EQ(r.replaced + r.dropped + r.aborted, 0);

  /* polling Pi without DRDY (PROTOCOLO §4, -drdy -1): a block that arrives while the Pi clocks
     zeros out of an idle link is held, never armed mid-transfer, and armed when CS rises */
  link_logic_t h = {0};
  CHECK_EQ(link_on_block(&h, 1), LINK_A_HOLD_NEW);
  CHECK_EQ(h.state, LINK_HELD);
  CHECK_EQ(h.armed, 0);
  CHECK_EQ(link_on_tx_done(&h), 0);
  CHECK_EQ(link_on_block(&h, 1), LINK_A_RELEASE_CUR | LINK_A_HOLD_NEW); /* newer one held instead */
  CHECK_EQ(h.dropped, 1);
  CHECK_EQ(link_on_nss_rise(&h), LINK_A_ARM_CUR | LINK_A_DRDY_HIGH);
  CHECK_EQ(h.state, LINK_ARMED);
  CHECK_EQ(h.armed, 1);
  /* a block found held with CS already high (its CS event not processed yet): arm the newest */
  link_logic_t g = {0};
  link_on_block(&g, 1);
  CHECK_EQ(link_on_block(&g, 0), LINK_A_RELEASE_CUR | LINK_A_ARM_NEW | LINK_A_DRDY_HIGH);
  CHECK_EQ(g.state, LINK_ARMED);
  CHECK_EQ(g.dropped, 1);

  /* SPI error (underrun) on an armed block: restart it from byte 0, but never under the Pi's
     clock: with CS high re-arm now, with CS low hold it until CS rises */
  link_logic_t e = {0};
  CHECK_EQ(link_on_error(&e, 0), 0); /* idle: nothing armed */
  link_on_block(&e, 0);
  CHECK_EQ(link_on_error(&e, 0), LINK_A_DRDY_LOW | LINK_A_ABORT | LINK_A_ARM_CUR | LINK_A_DRDY_HIGH);
  CHECK_EQ(e.aborted, 1);
  CHECK_EQ(e.state, LINK_ARMED);
  CHECK_EQ(link_on_error(&e, 1), LINK_A_DRDY_LOW | LINK_A_ABORT);
  CHECK_EQ(e.aborted, 2);
  CHECK_EQ(e.state, LINK_HELD);
  CHECK_EQ(link_on_nss_rise(&e), LINK_A_ARM_CUR | LINK_A_DRDY_HIGH);
  CHECK_EQ(e.state, LINK_ARMED);

  /* no Pi at all: every block replaces the previous one, the pool never fills */
  link_logic_t n = {0};
  for (int i = 0; i < 100; i++) {
    link_on_block(&n, 0);
  }
  CHECK_EQ(n.armed, 100);
  CHECK_EQ(n.replaced, 99);
  CHECK_EQ(n.sent, 0);
  TEST_END();
}
