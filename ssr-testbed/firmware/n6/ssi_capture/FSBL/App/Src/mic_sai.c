#include "mic.h"

#include "ssi_config.h"

#if SSI_MIC_SRC == SSI_MIC_I2S

#include <string.h>

#include "audio_decode.h"
#include "hse.h"
#include "nc_mem.h"
#include "stm32n6xx_hal.h"

#define MIC_WORDS (2u * 2u * SSI_WIN_AUDIO) /* two windows x two slots per frame */

static SAI_HandleTypeDef s_sai;
static DMA_HandleTypeDef s_dma;
static DMA_QListTypeDef s_list;
static DMA_NodeTypeDef s_node NC_MEM; /* the DMA reloads it after every block */
static uint32_t s_buf[MIC_WORDS] NC_MEM;
static uint32_t s_copy[MIC_WORDS / 2u]; /* window being decoded by acq */
static uint32_t s_ractive;

static TX_EVENT_FLAGS_GROUP *s_flags;
static ULONG s_flag_block;
static ULONG s_flag_error;
static volatile uint32_t s_blocks;
static volatile uint32_t s_errors;

/* HSE 48 MHz -> PLL4 1179.648 MHz -> IC7 /24 = 49.152 MHz. PLL1 (CPU) stays as CubeMX set it. */
static int audio_clock_init(void)
{
  RCC_OscInitTypeDef osc = {0};
  RCC_PeriphCLKInitTypeDef clk = {0};
  if (hse_start() != 0) {
    return -1;
  }
  osc.OscillatorType = RCC_OSCILLATORTYPE_NONE;
  osc.PLL1.PLLState = RCC_PLL_NONE;
  osc.PLL2.PLLState = RCC_PLL_NONE;
  osc.PLL3.PLLState = RCC_PLL_NONE;
  osc.PLL4.PLLState = RCC_PLL_ON;
  osc.PLL4.PLLSource = RCC_PLLSOURCE_HSE;
  osc.PLL4.PLLM = 1;
  osc.PLL4.PLLN = 24;
  osc.PLL4.PLLFractional = 9663677; /* 48 MHz * (24 + 9663677 / 2^24) = 1179.648 MHz */
  osc.PLL4.PLLP1 = 1;
  osc.PLL4.PLLP2 = 1;
  if (HAL_RCC_OscConfig(&osc) != HAL_OK) {
    return -2;
  }
  clk.PeriphClockSelection = RCC_PERIPHCLK_SAI2;
  clk.Sai2ClockSelection = RCC_SAI2CLKSOURCE_IC7;
  clk.ICSelection[RCC_IC7].ClockSelection = RCC_ICCLKSOURCE_PLL4;
  clk.ICSelection[RCC_IC7].ClockDivider = 24;
  if (HAL_RCCEx_PeriphCLKConfig(&clk) != HAL_OK) {
    return -3;
  }
  __HAL_RCC_SAI2_CLK_ENABLE();
  return 0;
}

static void pins_init(void)
{
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_GPIOE_CLK_ENABLE();
  g.Mode = GPIO_MODE_AF_PP;
  g.Speed = GPIO_SPEED_FREQ_LOW; /* slow edges: less SCK coupling into the A2 buffer (P7) */
  g.Alternate = GPIO_AF10_SAI2;
  g.Pull = GPIO_NOPULL;
  g.Pin = GPIO_PIN_12 | GPIO_PIN_13; /* SCK_B (A2), FS_B (D6) */
  HAL_GPIO_Init(GPIOE, &g);
  g.Pull = GPIO_PULLDOWN; /* SD is Hi-Z outside the mic's slot (INMP441 datasheet) */
  g.Pin = GPIO_PIN_7;     /* SD_B (D8) */
  HAL_GPIO_Init(GPIOE, &g);
  HAL_GPIO_ConfigPinAttributes(GPIOE, GPIO_PIN_7 | GPIO_PIN_12 | GPIO_PIN_13,
                               GPIO_PIN_SEC | GPIO_PIN_NPRIV);
}

static int sai_init(void)
{
  s_sai.Instance = SAI2_Block_B;
  s_sai.Init.AudioMode = SAI_MODEMASTER_RX;
  s_sai.Init.Synchro = SAI_ASYNCHRONOUS;
  s_sai.Init.OutputDrive = SAI_OUTPUTDRIVE_DISABLE;
  s_sai.Init.NoDivider = SAI_MASTERDIVIDER_ENABLE;
  s_sai.Init.FIFOThreshold = SAI_FIFOTHRESHOLD_EMPTY;
  s_sai.Init.AudioFrequency = SAI_AUDIO_FREQUENCY_MCKDIV;
  s_sai.Init.Mckdiv = 12; /* 49.152 MHz / 12 = 4.096 MHz = 256 x 16 kHz */
  s_sai.Init.MckOverSampling = SAI_MCK_OVERSAMPLING_DISABLE;
  s_sai.Init.SynchroExt = SAI_SYNCEXT_DISABLE;
  s_sai.Init.MckOutput = SAI_MCK_OUTPUT_DISABLE;
  s_sai.Init.MonoStereoMode = SAI_STEREOMODE;
  s_sai.Init.CompandingMode = SAI_NOCOMPANDING;
  s_sai.Init.TriState = SAI_OUTPUT_NOTRELEASED;
  s_sai.Init.PdmInit.Activation = DISABLE;
  s_sai.Init.PdmInit.MicPairsNbr = 1;
  s_sai.Init.PdmInit.ClockEnable = SAI_PDM_CLOCK1_ENABLE;
  /* Philips I2S: FS low = left slot, 24-bit data MSB first in 32-bit slots, 64 SCK per frame. */
  if (HAL_SAI_InitProtocol(&s_sai, SAI_I2S_STANDARD, SAI_PROTOCOL_DATASIZE_24BIT, 2) != HAL_OK) {
    return -4;
  }
  return 0;
}

static int dma_init(void)
{
  DMA_NodeConfTypeDef n = {0};
  __HAL_RCC_GPDMA1_CLK_ENABLE();
  n.NodeType = DMA_GPDMA_LINEAR_NODE;
  n.Init.Request = GPDMA1_REQUEST_SAI2_B;
  n.Init.BlkHWRequest = DMA_BREQ_SINGLE_BURST;
  n.Init.Direction = DMA_PERIPH_TO_MEMORY;
  n.Init.SrcInc = DMA_SINC_FIXED;
  n.Init.DestInc = DMA_DINC_INCREMENTED;
  n.Init.SrcDataWidth = DMA_SRC_DATAWIDTH_WORD;
  n.Init.DestDataWidth = DMA_DEST_DATAWIDTH_WORD;
  n.Init.SrcBurstLength = 1;
  n.Init.DestBurstLength = 1;
  n.Init.TransferAllocatedPort = DMA_SRC_ALLOCATED_PORT0 | DMA_DEST_ALLOCATED_PORT0;
  n.Init.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  n.Init.Mode = DMA_NORMAL;
  n.TriggerConfig.TriggerPolarity = DMA_TRIG_POLARITY_MASKED;
  n.TriggerConfig.TriggerSelection = GPDMA1_TRIGGER_GPDMA1_CH0_TCF;
  n.DataHandlingConfig.DataExchange = DMA_EXCHANGE_NONE;
  n.DataHandlingConfig.DataAlignment = DMA_DATA_RIGHTALIGN_ZEROPADDED;
  n.SrcSecure = DMA_CHANNEL_SRC_SEC;
  n.DestSecure = DMA_CHANNEL_DEST_SEC;
  if (HAL_DMAEx_List_BuildNode(&n, &s_node) != HAL_OK ||
      HAL_DMAEx_List_InsertNode(&s_list, NULL, &s_node) != HAL_OK ||
      HAL_DMAEx_List_SetCircularMode(&s_list) != HAL_OK) {
    return -5;
  }
  s_dma.Instance = GPDMA1_Channel0;
  s_dma.InitLinkedList.Priority = DMA_LOW_PRIORITY_HIGH_WEIGHT;
  s_dma.InitLinkedList.LinkStepMode = DMA_LSM_FULL_EXECUTION;
  s_dma.InitLinkedList.LinkAllocatedPort = DMA_LINK_ALLOCATED_PORT0;
  s_dma.InitLinkedList.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  s_dma.InitLinkedList.LinkedListMode = DMA_LINKEDLIST_CIRCULAR;
  if (HAL_DMAEx_List_Init(&s_dma) != HAL_OK || HAL_DMAEx_List_LinkQ(&s_dma, &s_list) != HAL_OK) {
    return -6;
  }
  __HAL_LINKDMA(&s_sai, hdmarx, s_dma);
  /* The FSBL runs secure: channel, source and destination secure, as in ST's example. */
  if (HAL_DMA_ConfigChannelAttributes(&s_dma, DMA_CHANNEL_SEC | DMA_CHANNEL_PRIV |
                                                  DMA_CHANNEL_SRC_SEC | DMA_CHANNEL_DEST_SEC) != HAL_OK) {
    return -7;
  }
  HAL_NVIC_SetPriority(GPDMA1_Channel0_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(GPDMA1_Channel0_IRQn);
  HAL_NVIC_SetPriority(SAI2_B_IRQn, 6, 0);
  HAL_NVIC_EnableIRQ(SAI2_B_IRQn);
  return 0;
}

int mic_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error)
{
  int rc;
  s_flags = flags;
  s_flag_block = flag_block;
  s_flag_error = flag_error;
  if ((rc = audio_clock_init()) != 0) {
    return rc;
  }
  pins_init();
  if ((rc = sai_init()) != 0) {
    return rc;
  }
  return dma_init();
}

int mic_start(void)
{
  s_blocks = 0u;
  return (HAL_SAI_Receive_DMA(&s_sai, (uint8_t *)s_buf, (uint16_t)MIC_WORDS) == HAL_OK) ? 0 : -1;
}

void mic_stop(void)
{
  (void)HAL_SAI_DMAStop(&s_sai);
}

uint32_t mic_blocks_done(void)
{
  return s_blocks;
}

void mic_copy(uint32_t k)
{
  memcpy(s_copy, &s_buf[(k & 1u) * (MIC_WORDS / 2u)], sizeof s_copy);
}

void mic_decode(int32_t *audio)
{
  audio_extract_left(s_copy, audio, SSI_WIN_AUDIO);
  s_ractive = audio_right_activity(s_copy, SSI_WIN_AUDIO);
}

const uint32_t *mic_diag_raw(void)
{
  return s_copy;
}

uint32_t mic_right_activity(void)
{
  return s_ractive;
}

uint32_t mic_errors(void)
{
  return s_errors;
}

uint32_t mic_clock_hz(void)
{
  return HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_SAI2);
}

void mic_sck_output(int on)
{
  GPIO_InitTypeDef g = {0};
  g.Pin = GPIO_PIN_12;
  g.Mode = on ? GPIO_MODE_AF_PP : GPIO_MODE_ANALOG;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_LOW;
  g.Alternate = GPIO_AF10_SAI2;
  HAL_GPIO_Init(GPIOE, &g);
}

/* ISR context: count and notify, nothing else. */
static void notify(ULONG flag)
{
  if (s_flags != TX_NULL) {
    (void)tx_event_flags_set(s_flags, flag, TX_OR);
  }
}

void HAL_SAI_RxHalfCpltCallback(SAI_HandleTypeDef *hsai)
{
  if (hsai == &s_sai) {
    s_blocks++;
    notify(s_flag_block);
  }
}

void HAL_SAI_RxCpltCallback(SAI_HandleTypeDef *hsai)
{
  if (hsai == &s_sai) {
    s_blocks++;
    notify(s_flag_block);
  }
}

void HAL_SAI_ErrorCallback(SAI_HandleTypeDef *hsai)
{
  if (hsai == &s_sai) {
    s_errors++;
    notify(s_flag_error);
  }
}

void GPDMA1_Channel0_IRQHandler(void)
{
  HAL_DMA_IRQHandler(&s_dma);
}

void SAI2_B_IRQHandler(void)
{
  HAL_SAI_IRQHandler(&s_sai);
}

#endif /* SSI_MIC_SRC == SSI_MIC_I2S */
