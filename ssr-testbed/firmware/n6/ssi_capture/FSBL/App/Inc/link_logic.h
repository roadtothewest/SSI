#ifndef LINK_LOGIC_H
#define LINK_LOGIC_H

#include <stdint.h>

/* SPI-slave link state machine of ssr-testbed/firmware/PROTOCOLO_SPI.md §4, without HAL.
   Each event returns a set of actions; the driver runs them in this order:
   DRDY_LOW, ABORT, RELEASE_CUR, RELEASE_NEW, HOLD_NEW, ARM_NEW or ARM_CUR, DRDY_HIGH
   (keeping DRDY low >= 10 us when both DRDY_LOW and DRDY_HIGH are set). */
#define LINK_A_DRDY_LOW    0x01u /* DRDY down */
#define LINK_A_ABORT       0x02u /* stop the armed SPI/DMA transfer (CS is high) */
#define LINK_A_RELEASE_CUR 0x04u /* free the armed block */
#define LINK_A_RELEASE_NEW 0x08u /* free the offered block (discarded) */
#define LINK_A_ARM_NEW     0x10u /* arm the DMA with the offered block, which becomes current */
#define LINK_A_ARM_CUR     0x20u /* re-arm the current block from byte 0 */
#define LINK_A_DRDY_HIGH   0x40u /* DRDY up: the Pi reads on this rising edge */
#define LINK_A_HOLD_NEW    0x80u /* keep the offered block as current without arming it */

/* HELD: a block is waiting for CS to rise, because the Pi was clocking an idle link (polling
   without DRDY, PROTOCOLO §4): arming it mid-transfer would corrupt that read. */
typedef enum { LINK_IDLE = 0, LINK_ARMED, LINK_HELD } link_state_t;

typedef struct {
  link_state_t state;
  uint32_t armed;    /* blocks offered to the Pi (DRDY rising edges) */
  uint32_t sent;     /* complete 538-byte transfers */
  uint32_t replaced; /* armed blocks replaced by a newer one before the Pi read them */
  uint32_t dropped;  /* blocks discarded without being offered (transfer in progress) */
  uint32_t aborted;  /* armed blocks restarted from byte 0 after an SPI error */
} link_logic_t;

/* A new block is ready (always the newest). busy: the Pi is in the middle of a read (CS low, or
   bytes went out since the previous block). */
uint32_t link_on_block(link_logic_t *l, int busy);
/* The SPI finished sending the armed block. */
uint32_t link_on_tx_done(link_logic_t *l);
/* CS rose while a block is held (it arrived during a read of an idle link): arm it now. CS edges
   in any other state mean nothing: the Pi 5 releases CS between bytes and when its FIFO runs dry,
   so a transfer ends by its byte count (tx_done), never by CS (P5, 2026-10-12). */
uint32_t link_on_nss_rise(link_logic_t *l);
/* SPI/DMA error (e.g. underrun) on the armed block: restart it from byte 0, at once when CS is
   high, or held until CS rises when the Pi is in the middle of a read. */
uint32_t link_on_error(link_logic_t *l, int nss_low);

#endif
