#include "mic.h"

#include "ssi_config.h"

#if SSI_MIC_SRC == SSI_MIC_ANALOG

#include <string.h>

#include "audio_fir.h"
#include "nc_mem.h"
#include "stm32n6xx_hal.h"
#include "sync.h"

#define MIC_RAW_WIN (SSI_WIN_AUDIO * AFIR_DECIM) /* 640 codes at 64 kHz per 10 ms window */
#define MIC_WORDS   (2u * MIC_RAW_WIN)           /* two windows, one word per conversion */

_Static_assert(MIC_RAW_WIN >= 2u * SSI_WIN_AUDIO, "diag reads 2 * SSI_WIN_AUDIO raw words");

static ADC_HandleTypeDef s_adc;
static DMA_HandleTypeDef s_dma;
static DMA_QListTypeDef s_list;
static DMA_NodeTypeDef s_node NC_MEM;
static uint32_t s_buf[MIC_WORDS] NC_MEM;
static uint32_t s_copy[MIC_RAW_WIN]; /* window being decoded by acq */
static afir_t s_fir;

static TX_EVENT_FLAGS_GROUP *s_flags;
static ULONG s_flag_block;
static ULONG s_flag_error;
static volatile uint32_t s_blocks;
static volatile uint32_t s_errors;

static void pins_init(void)
{
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE();
  g.Mode = GPIO_MODE_ANALOG;
  g.Pull = GPIO_NOPULL;
  g.Pin = GPIO_PIN_12; /* PA12 = ADC12_INP13, A3 */
  HAL_GPIO_Init(GPIOA, &g);
  HAL_GPIO_ConfigPinAttributes(GPIOA, GPIO_PIN_12, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
}

/* ADC2 shares the ADC12 kernel clock, the RIF setting and the independent multimode setting that
   emg_adc_init configured: call this after it. */
static int adc_init(void)
{
  ADC_ChannelConfTypeDef ch = {0};
  s_adc.Instance = ADC2;
  s_adc.Init.Resolution = ADC_RESOLUTION_12B;
  s_adc.Init.GainCompensation = 0;
  s_adc.Init.ScanConvMode = ADC_SCAN_DISABLE;
  s_adc.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  s_adc.Init.LowPowerAutoWait = DISABLE;
  s_adc.Init.ContinuousConvMode = DISABLE;
  s_adc.Init.NbrOfConversion = 1;
  s_adc.Init.DiscontinuousConvMode = DISABLE;
  s_adc.Init.ExternalTrigConv = sync_mic_trigger();
  s_adc.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_RISING;
  s_adc.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DMA_CIRCULAR;
  s_adc.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
  s_adc.Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;
  s_adc.Init.OversamplingMode = DISABLE;
  if (HAL_ADC_Init(&s_adc) != HAL_OK) {
    return -11;
  }
  ch.Channel = ADC_CHANNEL_13;
  ch.Rank = ADC_REGULAR_RANK_1;
  ch.SamplingTime = ADC_SAMPLETIME_246CYCLES_5; /* as the EMG: same delay after the trigger */
  ch.SingleDiff = ADC_SINGLE_ENDED;
  ch.OffsetNumber = ADC_OFFSET_NONE;
  ch.Offset = 0;
  if (HAL_ADC_ConfigChannel(&s_adc, &ch) != HAL_OK) {
    return -12;
  }
  if (HAL_ADCEx_Calibration_Start(&s_adc, ADC_SINGLE_ENDED) != HAL_OK) {
    return -13;
  }
  return 0;
}

static void dma_half(DMA_HandleTypeDef *hdma);
static void dma_full(DMA_HandleTypeDef *hdma);
static void dma_error(DMA_HandleTypeDef *hdma);

/* The ADC HAL callbacks and the shared ADC1_2 IRQ belong to emg_adc (ADC1): ADC2 raises no ADC
   interrupt and the DMA channel reports the windows through its own callbacks. */
static int dma_init(void)
{
  DMA_NodeConfTypeDef n = {0};
  __HAL_RCC_GPDMA1_CLK_ENABLE();
  n.NodeType = DMA_GPDMA_LINEAR_NODE;
  n.Init.Request = GPDMA1_REQUEST_ADC2;
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
  n.SrcAddress = (uint32_t)&ADC2->DR;
  n.DstAddress = (uint32_t)s_buf;
  n.DataSize = sizeof s_buf;
  n.SrcSecure = DMA_CHANNEL_SRC_SEC;
  n.DestSecure = DMA_CHANNEL_DEST_SEC;
  if (HAL_DMAEx_List_BuildNode(&n, &s_node) != HAL_OK ||
      HAL_DMAEx_List_InsertNode(&s_list, NULL, &s_node) != HAL_OK ||
      HAL_DMAEx_List_SetCircularMode(&s_list) != HAL_OK) {
    return -14;
  }
  s_dma.Instance = GPDMA1_Channel3;
  s_dma.InitLinkedList.Priority = DMA_LOW_PRIORITY_HIGH_WEIGHT;
  s_dma.InitLinkedList.LinkStepMode = DMA_LSM_FULL_EXECUTION;
  s_dma.InitLinkedList.LinkAllocatedPort = DMA_LINK_ALLOCATED_PORT0;
  s_dma.InitLinkedList.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  s_dma.InitLinkedList.LinkedListMode = DMA_LINKEDLIST_CIRCULAR;
  if (HAL_DMAEx_List_Init(&s_dma) != HAL_OK || HAL_DMAEx_List_LinkQ(&s_dma, &s_list) != HAL_OK) {
    return -15;
  }
  if (HAL_DMA_ConfigChannelAttributes(&s_dma, DMA_CHANNEL_SEC | DMA_CHANNEL_PRIV |
                                                  DMA_CHANNEL_SRC_SEC | DMA_CHANNEL_DEST_SEC) != HAL_OK) {
    return -16;
  }
  s_dma.XferHalfCpltCallback = dma_half;
  s_dma.XferCpltCallback = dma_full;
  s_dma.XferErrorCallback = dma_error;
  HAL_NVIC_SetPriority(GPDMA1_Channel3_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(GPDMA1_Channel3_IRQn);
  return 0;
}

int mic_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error)
{
  int rc;
  s_flags = flags;
  s_flag_block = flag_block;
  s_flag_error = flag_error;
  pins_init();
  if ((rc = adc_init()) != 0) {
    return rc;
  }
  return dma_init();
}

/* Before sync_start: the ADC waits for its first LPTIM2 edge. */
int mic_start(void)
{
  s_blocks = 0u;
  afir_reset(&s_fir);
  LL_ADC_REG_SetDataTransferMode(s_adc.Instance, LL_ADC_REG_DMA_TRANSFER_UNLIMITED);
  if (HAL_DMAEx_List_Start_IT(&s_dma) != HAL_OK) {
    return -1;
  }
  if (HAL_ADC_Start(&s_adc) != HAL_OK) {
    (void)HAL_DMA_Abort(&s_dma);
    return -2;
  }
  return 0;
}

void mic_stop(void)
{
  (void)HAL_ADC_Stop(&s_adc);
  (void)HAL_DMA_Abort(&s_dma);
}

uint32_t mic_blocks_done(void)
{
  return s_blocks;
}

void mic_copy(uint32_t k)
{
  memcpy(s_copy, &s_buf[(k & 1u) * MIC_RAW_WIN], sizeof s_copy);
}

void mic_decode(int32_t *audio)
{
  afir_process(&s_fir, s_copy, MIC_RAW_WIN, audio);
}

const uint32_t *mic_diag_raw(void)
{
  return s_copy;
}

uint32_t mic_right_activity(void)
{
  return 0u;
}

uint32_t mic_errors(void)
{
  return s_errors;
}

uint32_t mic_clock_hz(void)
{
  return HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_ADC);
}

void mic_sck_output(int on)
{
  (void)on;
}

/* ISR context: count and notify, nothing else. */
static void notify(ULONG flag)
{
  if (s_flags != TX_NULL) {
    (void)tx_event_flags_set(s_flags, flag, TX_OR);
  }
}

static void dma_half(DMA_HandleTypeDef *hdma)
{
  (void)hdma;
  s_blocks++;
  notify(s_flag_block);
}

static void dma_full(DMA_HandleTypeDef *hdma)
{
  (void)hdma;
  s_blocks++;
  notify(s_flag_block);
}

static void dma_error(DMA_HandleTypeDef *hdma)
{
  (void)hdma;
  s_errors++;
  notify(s_flag_error);
}

void GPDMA1_Channel3_IRQHandler(void)
{
  HAL_DMA_IRQHandler(&s_dma);
}

#endif /* SSI_MIC_SRC == SSI_MIC_ANALOG */
