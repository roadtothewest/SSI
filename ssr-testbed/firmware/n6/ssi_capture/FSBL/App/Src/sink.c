#include "sink.h"

#include <string.h>

#include "avx_block.h"
#include "stm32n6xx_hal.h"

_Static_assert(sizeof(sink_stats_t) == 4u * sizeof(ULONG), "sink_stats_t is a TX_4_ULONG message");

#define SAMPLE_EVERY 100u

static sink_cfg_t s_cfg;
static sink_stats_t s_st;
static uint32_t s_last_seq;
static int s_have_seq;
/* Copy of every 100th block for tools/swd.py sample, cleaned to SRAM after the copy. */
static uint8_t s_sink_sample[AVX_BLOCK_SIZE] __attribute__((aligned(32), used));

static uint32_t rd32(const uint8_t *p)
{
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static uint16_t rd16(const uint8_t *p)
{
  return (uint16_t)(p[0] | (p[1] << 8));
}

void sink_configure(const sink_cfg_t *cfg)
{
  s_cfg = *cfg;
}

static void check(const uint8_t *blk)
{
  const uint32_t seq = rd32(blk + 4);
  if (blk[0] != AVX_SYNC0 || blk[1] != AVX_SYNC1 ||
      rd16(blk + AVX_CRC_OFFSET) != avx_crc16(blk, AVX_CRC_OFFSET)) {
    s_st.crc_err++;
  }
  if (s_have_seq && seq != s_last_seq + 1u) {
    s_st.gap++;
  }
  s_last_seq = seq;
  s_have_seq = 1;
  if (rd16(blk + 14) != 0u) {
    s_st.ovf++;
  }
}

void sink_thread_entry(ULONG arg)
{
  (void)arg;
  for (;;) {
    ULONG msg;
    if (tx_queue_receive(s_cfg.in, &msg, TX_WAIT_FOREVER) != TX_SUCCESS) {
      continue;
    }
    uint8_t *blk = (uint8_t *)(uintptr_t)msg;
    check(blk);
    if (++s_st.rx % SAMPLE_EVERY == 0u) {
      memcpy(s_sink_sample, blk, AVX_BLOCK_SIZE);
      SCB_CleanDCache_by_Addr(s_sink_sample, (int32_t)AVX_BLOCK_SIZE);
      (void)tx_queue_send(s_cfg.stats, &s_st, TX_NO_WAIT);
    }
    (void)tx_block_release(blk);
  }
}
