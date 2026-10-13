#include "link.h"

#include <string.h>

#include "avx_block.h"
#include "link_logic.h"
#include "log.h"
#include "stm32n6xx_hal.h"

_Static_assert(sizeof(link_stats_t) <= 8u * sizeof(ULONG), "link_stats_t must fit TX_8_ULONG");

#define STATS_EVERY    100u  /* blocks armed between stats messages (1 s) */
#define DRDY_LOW_SPINS 4000u /* >= 10 us of DRDY low before a new rising edge (PROTOCOLO §4) */
#define NSS_HIGH_READS 1000u /* CS must read high this many times in a row (~10 us) to arm a held block */

static link_cfg_t s_cfg;
static SPI_HandleTypeDef s_spi;
static DMA_HandleTypeDef s_dma;
static EXTI_HandleTypeDef s_exti;
static link_logic_t s_lk;
static uint8_t *s_cur;
static volatile uint32_t s_loops;
static volatile uint32_t s_errors;
static volatile uint32_t s_nss_ignored;  /* CS rises that did not arm a held block (Pi 5 CS gaps) */
static volatile uint32_t s_stalls;       /* partial transfers abandoned by the Pi (no progress in 10 ms) */
static uint32_t s_left_last = AVX_BLOCK_SIZE; /* CTSIZE at the previous block */
static int s_nss_irq_on;
static volatile uint32_t s_err_arm;      /* HAL_SPI_Transmit_DMA refused to arm */
static volatile uint32_t s_err_cb;       /* SPI/DMA errors reported by the HAL */
static volatile uint32_t s_err_codes;    /* OR of HAL_SPI_ERROR_* seen in the callback */
/* Copy of every 100th armed block for tools/swd.py sample, cleaned to SRAM after the copy. */
static uint8_t s_link_sample[AVX_BLOCK_SIZE] __attribute__((aligned(32), used));

void link_configure(const link_cfg_t *cfg)
{
  s_cfg = *cfg;
}

uint32_t link_loops(void)
{
  return s_loops;
}

/* ISR context: notify only. */
static void notify(ULONG flag)
{
  (void)tx_event_flags_set(s_cfg.flags, flag, TX_OR);
}

static void nss_rise_cb(void)
{
  notify(LINK_EVT_NSS);
}

static void nss_pin(uint32_t pull)
{
  GPIO_InitTypeDef g = {0};
  g.Pin = GPIO_PIN_3; /* SPI5_NSS, D10 */
  g.Mode = GPIO_MODE_AF_PP;
  g.Pull = pull;
  g.Speed = GPIO_SPEED_FREQ_HIGH;
  g.Alternate = GPIO_AF5_SPI5;
  HAL_GPIO_Init(GPIOA, &g);
}

static void pins_init(void)
{
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_GPIOG_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  nss_pin(GPIO_PULLUP); /* unwired CS reads "not selected" */
  g.Mode = GPIO_MODE_AF_PP;
  g.Speed = GPIO_SPEED_FREQ_HIGH;
  g.Alternate = GPIO_AF5_SPI5;
  g.Pull = GPIO_NOPULL;
  g.Pin = GPIO_PIN_2; /* MOSI, D11 (the Pi sends zeros, ignored) */
  HAL_GPIO_Init(GPIOG, &g);
  g.Pin = GPIO_PIN_15; /* SCK, D13 */
  HAL_GPIO_Init(GPIOE, &g);
  g.Pull = GPIO_PULLDOWN;
  g.Pin = GPIO_PIN_8; /* MISO, D12: reads 0x00 while the slave does not drive it */
  HAL_GPIO_Init(GPIOH, &g);
  HAL_GPIO_WritePin(GPIOH, GPIO_PIN_5, GPIO_PIN_RESET);
  g.Mode = GPIO_MODE_OUTPUT_PP;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_LOW;
  g.Alternate = 0;
  g.Pin = GPIO_PIN_5; /* DRDY, D4 */
  HAL_GPIO_Init(GPIOH, &g);
  HAL_GPIO_ConfigPinAttributes(GPIOA, GPIO_PIN_3, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOG, GPIO_PIN_2, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOE, GPIO_PIN_15, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOH, GPIO_PIN_5 | GPIO_PIN_8, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
}

static int spi_init(void)
{
  RCC_PeriphCLKInitTypeDef clk = {0};
  clk.PeriphClockSelection = RCC_PERIPHCLK_SPI5;
  clk.Spi5ClockSelection = RCC_SPI5CLKSOURCE_PCLK2;
  if (HAL_RCCEx_PeriphCLKConfig(&clk) != HAL_OK) {
    return -1;
  }
  __HAL_RCC_SPI5_CLK_ENABLE();
  s_spi.Instance = SPI5;
  s_spi.Init.Mode = SPI_MODE_SLAVE;
  s_spi.Init.Direction = SPI_DIRECTION_2LINES_TXONLY;
  s_spi.Init.DataSize = SPI_DATASIZE_8BIT;
  s_spi.Init.CLKPolarity = SPI_POLARITY_LOW; /* mode 0 */
  s_spi.Init.CLKPhase = SPI_PHASE_1EDGE;
  s_spi.Init.NSS = SPI_NSS_HARD_INPUT;
  s_spi.Init.FirstBit = SPI_FIRSTBIT_MSB;
  s_spi.Init.TIMode = SPI_TIMODE_DISABLE;
  s_spi.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  s_spi.Init.CRCPolynomial = 0x7;
  s_spi.Init.NSSPMode = SPI_NSS_PULSE_DISABLE;
  s_spi.Init.NSSPolarity = SPI_NSS_POLARITY_LOW;
  s_spi.Init.FifoThreshold = SPI_FIFO_THRESHOLD_01DATA;
  s_spi.Init.MasterSSIdleness = SPI_MASTER_SS_IDLENESS_00CYCLE;
  s_spi.Init.MasterInterDataIdleness = SPI_MASTER_INTERDATA_IDLENESS_00CYCLE;
  s_spi.Init.MasterReceiverAutoSusp = SPI_MASTER_RX_AUTOSUSP_DISABLE;
  s_spi.Init.MasterKeepIOState = SPI_MASTER_KEEP_IO_STATE_DISABLE;
  s_spi.Init.IOSwap = SPI_IO_SWAP_DISABLE;
  s_spi.Init.ReadyMasterManagement = SPI_RDY_MASTER_MANAGEMENT_INTERNALLY;
  s_spi.Init.ReadyPolarity = SPI_RDY_POLARITY_HIGH;
  return (HAL_SPI_Init(&s_spi) == HAL_OK) ? 0 : -2;
}

static int dma_init(void)
{
  __HAL_RCC_GPDMA1_CLK_ENABLE();
  s_dma.Instance = GPDMA1_Channel2;
  s_dma.Init.Request = GPDMA1_REQUEST_SPI5_TX;
  s_dma.Init.BlkHWRequest = DMA_BREQ_SINGLE_BURST;
  s_dma.Init.Direction = DMA_MEMORY_TO_PERIPH;
  s_dma.Init.SrcInc = DMA_SINC_INCREMENTED;
  s_dma.Init.DestInc = DMA_DINC_FIXED;
  s_dma.Init.SrcDataWidth = DMA_SRC_DATAWIDTH_BYTE;
  s_dma.Init.DestDataWidth = DMA_DEST_DATAWIDTH_BYTE;
  s_dma.Init.Priority = DMA_LOW_PRIORITY_HIGH_WEIGHT;
  s_dma.Init.SrcBurstLength = 1;
  s_dma.Init.DestBurstLength = 1;
  s_dma.Init.TransferAllocatedPort = DMA_SRC_ALLOCATED_PORT0 | DMA_DEST_ALLOCATED_PORT0;
  s_dma.Init.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  s_dma.Init.Mode = DMA_NORMAL;
  if (HAL_DMA_Init(&s_dma) != HAL_OK) {
    return -3;
  }
  __HAL_LINKDMA(&s_spi, hdmatx, s_dma);
  if (HAL_DMA_ConfigChannelAttributes(&s_dma, DMA_CHANNEL_SEC | DMA_CHANNEL_PRIV |
                                                  DMA_CHANNEL_SRC_SEC | DMA_CHANNEL_DEST_SEC) != HAL_OK) {
    return -4;
  }
  HAL_NVIC_SetPriority(GPDMA1_Channel2_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(GPDMA1_Channel2_IRQn);
  HAL_NVIC_SetPriority(SPI5_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(SPI5_IRQn);
  return 0;
}

static int nss_irq_init(void)
{
  EXTI_ConfigTypeDef e = {0};
  e.Line = EXTI_LINE_3;
  e.Mode = EXTI_MODE_INTERRUPT;
  e.Trigger = EXTI_TRIGGER_RISING;
  e.GPIOSel = EXTI_GPIOA; /* PA3 stays in its SPI5_NSS alternate function */
  if (HAL_EXTI_SetConfigLine(&s_exti, &e) != HAL_OK ||
      HAL_EXTI_RegisterCallback(&s_exti, HAL_EXTI_RISING_CB_ID, nss_rise_cb) != HAL_OK) {
    return -5;
  }
  /* Lower priority than SPI5: a complete transfer's EOT is handled before its CS edge. */
  HAL_NVIC_SetPriority(EXTI3_IRQn, 7, 0); /* enabled only while a block is held */
  return 0;
}

static int nss_low(void)
{
  return HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_3) == GPIO_PIN_RESET;
}

/* The Pi 5 SPI (RP1, DesignWare) releases CS between bytes in mode 0 and whenever its TX FIFO runs
   dry (P5, 2026-10-12): a CS rise is not the end of a read. Only a CS that stays high lets a held
   block be armed. */
static int nss_high_stable(void)
{
  for (uint32_t i = 0; i < NSS_HIGH_READS; i++) {
    if (nss_low()) {
      return 0;
    }
  }
  return 1;
}

/* Bytes of the armed block not yet clocked out (AVX_BLOCK_SIZE until the Pi starts reading). */
static uint32_t tx_left(void)
{
  return (s_spi.Instance->SR & SPI_SR_CTSIZE_Msk) >> SPI_SR_CTSIZE_Pos;
}

/* A read is in progress when CS is low or when bytes went out since the previous block (CS may be
   high between bytes). A partial read that did not move in 10 ms was abandoned: not busy. */
static int link_busy(void)
{
  const uint32_t left = (s_lk.state == LINK_ARMED) ? tx_left() : AVX_BLOCK_SIZE;
  const int partial = left != 0u && left < AVX_BLOCK_SIZE;
  const int moving = partial && left != s_left_last;
  if (partial && !moving) {
    s_stalls++;
  }
  s_left_last = left;
  return nss_low() || moving;
}

/* EXTI3 only matters while a block is held: elsewhere the Pi 5's CS gaps would flood the thread. */
static void nss_irq_update(void)
{
  if (s_lk.state == LINK_HELD && !s_nss_irq_on) {
    HAL_EXTI_ClearPending(&s_exti, EXTI_TRIGGER_RISING);
    HAL_NVIC_ClearPendingIRQ(EXTI3_IRQn);
    HAL_NVIC_EnableIRQ(EXTI3_IRQn);
    s_nss_irq_on = 1;
    if (!nss_low()) {
      notify(LINK_EVT_NSS); /* CS rose before the IRQ was on */
    }
  } else if (s_lk.state != LINK_HELD && s_nss_irq_on) {
    HAL_NVIC_DisableIRQ(EXTI3_IRQn);
    s_nss_irq_on = 0;
  }
}

static void drdy(int high)
{
  HAL_GPIO_WritePin(GPIOH, GPIO_PIN_5, high ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

static void arm(uint8_t *blk)
{
  if (HAL_SPI_Transmit_DMA(&s_spi, blk, (uint16_t)AVX_BLOCK_SIZE) != HAL_OK) {
    s_errors++;
    s_err_arm++;
  }
}

/* Runs link_logic actions in the order link_logic.h documents. */
static void run(uint32_t a, uint8_t *blk)
{
  if ((a & LINK_A_DRDY_LOW) != 0u) {
    drdy(0);
  }
  if ((a & LINK_A_ABORT) != 0u) {
    (void)HAL_SPI_Abort(&s_spi);
  }
  if ((a & LINK_A_RELEASE_CUR) != 0u && s_cur != NULL) {
    (void)tx_block_release(s_cur);
    s_cur = NULL;
  }
  if ((a & LINK_A_RELEASE_NEW) != 0u) {
    (void)tx_block_release(blk);
  }
  if ((a & LINK_A_HOLD_NEW) != 0u) {
    s_cur = blk; /* armed later, when CS rises */
  }
  if ((a & LINK_A_ARM_NEW) != 0u) {
    s_cur = blk;
    arm(s_cur);
  }
  if ((a & LINK_A_ARM_CUR) != 0u && s_cur != NULL) {
    arm(s_cur);
  }
  if ((a & LINK_A_DRDY_HIGH) != 0u) {
    if ((a & LINK_A_DRDY_LOW) != 0u) {
      for (volatile uint32_t n = DRDY_LOW_SPINS; n != 0u; n--) {
      }
    }
    drdy(1);
  }
  nss_irq_update();
}

static void stats_push(void)
{
  union {
    link_stats_t s;
    ULONG raw[8];
  } m;
  memset(&m, 0, sizeof m);
  m.s.armed = s_lk.armed;
  m.s.sent = s_lk.sent;
  m.s.replaced = s_lk.replaced;
  m.s.dropped = s_lk.dropped;
  m.s.aborted = s_lk.aborted;
  m.s.errors = s_errors;
  (void)tx_queue_send(s_cfg.stats, m.raw, TX_NO_WAIT);
  if (s_cur != NULL) {
    memcpy(s_link_sample, s_cur, AVX_BLOCK_SIZE);
    SCB_CleanDCache_by_Addr(s_link_sample, (int32_t)AVX_BLOCK_SIZE);
  }
}

void link_debug_nss_pulse(void)
{
  nss_pin(GPIO_PULLDOWN); /* unwired CS follows the pull: "transfer in progress" */
  tx_thread_sleep(2u);    /* ~20 ms: new blocks find CS low and are dropped */
  nss_pin(GPIO_PULLUP);   /* rising edge without a single clock: incomplete transfer */
}

void SPI5_IRQHandler(void)
{
  HAL_SPI_IRQHandler(&s_spi);
}

void GPDMA1_Channel2_IRQHandler(void)
{
  HAL_DMA_IRQHandler(&s_dma);
}

void EXTI3_IRQHandler(void)
{
  HAL_EXTI_IRQHandler(&s_exti);
}

void HAL_SPI_TxCpltCallback(SPI_HandleTypeDef *hspi)
{
  if (hspi == &s_spi) {
    notify(LINK_EVT_TX_DONE);
  }
}

void HAL_SPI_ErrorCallback(SPI_HandleTypeDef *hspi)
{
  if (hspi == &s_spi) {
    s_errors++;
    s_err_cb++;
    s_err_codes |= hspi->ErrorCode;
    notify(LINK_EVT_ERROR);
  }
}

void link_thread_entry(ULONG arg)
{
  (void)arg;
  int rc;
  pins_init();
  if ((rc = spi_init()) == 0 && (rc = dma_init()) == 0) {
    rc = nss_irq_init();
  }
  log_printf("INIT link=%d", rc);
  if (rc != 0) {
    (void)tx_thread_suspend(tx_thread_identify());
  }
  for (;;) {
    ULONG got = 0u;
    (void)tx_event_flags_get(s_cfg.flags,
                             LINK_EVT_BLOCK | LINK_EVT_TX_DONE | LINK_EVT_NSS | LINK_EVT_ERROR,
                             TX_OR_CLEAR, &got, TX_TIMER_TICKS_PER_SECOND / 10u);
    s_loops++;
    /* A read ends by its byte count (EOT): completion first, then errors, then a held block. */
    if ((got & LINK_EVT_TX_DONE) != 0u) {
      run(link_on_tx_done(&s_lk), NULL);
    }
    if ((got & LINK_EVT_ERROR) != 0u) {
      run(link_on_error(&s_lk, nss_low()), NULL);
    }
    if ((got & LINK_EVT_NSS) != 0u) {
      if (s_lk.state == LINK_HELD && nss_high_stable()) {
        run(link_on_nss_rise(&s_lk), NULL);
      } else {
        s_nss_ignored++;
      }
    }
    ULONG msg;
    while (tx_queue_receive(s_cfg.in, &msg, TX_NO_WAIT) == TX_SUCCESS) {
      const uint32_t armed = s_lk.armed;
      run(link_on_block(&s_lk, link_busy()), (uint8_t *)(uintptr_t)msg);
      if (s_lk.armed != armed && s_lk.armed % STATS_EVERY == 0u) {
        stats_push();
      }
    }
  }
}
