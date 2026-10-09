#include "app.h"

#include "acq.h"
#include "led.h"
#include "log.h"
#include "mon.h"
#include "nc_mem.h"
#include "avx_block.h"
#include "sink.h"
#include "ssi_config.h"
#include "testpulse.h"
#include "tx_api.h"

extern uint32_t __snoncacheable; /* ssi_capture_fsbl.ld */
extern uint32_t __enoncacheable;

#define NC_BASE 0x341F8000u
#define NC_END  0x34200000u

#define POOL_BLOCKS 16u                                /* spec §5: 160 ms of blocks */
#define BLOCK_BYTES ((AVX_BLOCK_SIZE + 3u) & ~3u)       /* ThreadX rounds blocks to 4 B */

static TX_EVENT_FLAGS_GROUP s_acq_flags;
static TX_BLOCK_POOL s_pool;
static UCHAR s_pool_mem[POOL_BLOCKS * (BLOCK_BYTES + sizeof(void *))] NC_MEM; /* + block header */
static TX_QUEUE s_pkt_q;
static ULONG s_pkt_q_mem[POOL_BLOCKS];
static TX_QUEUE s_acq_stats_q;
static ULONG s_acq_stats_mem[4u * 16u];
static TX_QUEUE s_sink_stats_q;
static ULONG s_sink_stats_mem[4u * 4u];

static TX_THREAD s_acq;
static TX_THREAD s_sink;
static TX_THREAD s_tp;
static TX_THREAD s_mon;
static ULONG s_acq_stack[1024]; /* 4 KB */
static ULONG s_sink_stack[512];
static ULONG s_tp_stack[256];
static ULONG s_mon_stack[1024]; /* vsnprintf */

void app_early_init(UART_HandleTypeDef *huart)
{
  const uint32_t s = (uint32_t)&__snoncacheable;
  const uint32_t e = (uint32_t)&__enoncacheable;
  log_init(huart);
  led_init();
  log_printf("SSI capture fw %lu.%lu.%lu (%s %s)", (unsigned long)((SSI_FW_VERSION >> 16) & 0xFFu),
             (unsigned long)((SSI_FW_VERSION >> 8) & 0xFFu), (unsigned long)(SSI_FW_VERSION & 0xFFu),
             __DATE__, __TIME__);
  log_printf("CLK cpu=%lu", (unsigned long)SystemCoreClock);
  log_printf("NC 0x%08lx..0x%08lx %s", (unsigned long)s, (unsigned long)e,
             (s >= NC_BASE && e <= NC_END) ? "OK" : "FAIL");
}

void app_start(void)
{
  UINT rc = TX_SUCCESS;
  log_rtos_init();
  rc |= tx_event_flags_create(&s_acq_flags, "acq");
  rc |= tx_block_pool_create(&s_pool, "blk_pool", BLOCK_BYTES, s_pool_mem, sizeof s_pool_mem);
  rc |= tx_queue_create(&s_pkt_q, "blk_q", TX_1_ULONG, s_pkt_q_mem, sizeof s_pkt_q_mem);
  rc |= tx_queue_create(&s_acq_stats_q, "acq_st", TX_16_ULONG, s_acq_stats_mem,
                        sizeof s_acq_stats_mem);
  rc |= tx_queue_create(&s_sink_stats_q, "sink_st", TX_4_ULONG, s_sink_stats_mem,
                        sizeof s_sink_stats_mem);

  const acq_cfg_t acq = {&s_acq_flags, &s_pool, &s_pkt_q, &s_acq_stats_q};
  const sink_cfg_t sink = {&s_pkt_q, &s_sink_stats_q};
  const mon_cfg_t mon = {&s_acq_stats_q, &s_sink_stats_q};
  acq_configure(&acq);
  sink_configure(&sink);
  mon_configure(&mon);
  testpulse_init();

  /* Preemption threshold = priority: tx_user.h defines TX_DISABLE_PREEMPTION_THRESHOLD. */
  rc |= tx_thread_create(&s_acq, "acq", acq_thread_entry, 0, s_acq_stack, sizeof s_acq_stack, 2, 2,
                         TX_NO_TIME_SLICE, TX_AUTO_START);
  rc |= tx_thread_create(&s_sink, "sink", sink_thread_entry, 0, s_sink_stack, sizeof s_sink_stack,
                         8, 8, TX_NO_TIME_SLICE, TX_AUTO_START);
  rc |= tx_thread_create(&s_tp, "testpulse", testpulse_thread_entry, 0, s_tp_stack,
                         sizeof s_tp_stack, 9, 9, TX_NO_TIME_SLICE, TX_AUTO_START);
  rc |= tx_thread_create(&s_mon, "mon", mon_thread_entry, 0, s_mon_stack, sizeof s_mon_stack, 10,
                         10, TX_NO_TIME_SLICE, TX_AUTO_START);
  if (rc != TX_SUCCESS) {
    log_printf("ERR app_start rc=%u", (unsigned)rc);
  }
}
