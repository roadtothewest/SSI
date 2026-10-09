#include "emg_adc.h"

#include "nc_mem.h"
#include "ssi_config.h"
#include "stm32n6xx_hal.h"

#define EMG_WORDS  (2u * SSI_WIN_EMG * SSI_EMG_CH) /* two windows, one word per conversion */
#define ADC_MAX_HZ 50000000u                       /* conservative; ST's example runs TIMG/6 */

static ADC_HandleTypeDef s_adc;
static DMA_HandleTypeDef s_dma;
static DMA_QListTypeDef s_list;
static DMA_NodeTypeDef s_node NC_MEM;
static uint32_t s_buf[EMG_WORDS] NC_MEM;

static TX_EVENT_FLAGS_GROUP *s_flags;
static ULONG s_flag_block;
static ULONG s_flag_error;
static uint32_t s_trigger;
static volatile uint32_t s_blocks;
static volatile uint32_t s_errors;

static int clock_init(void)
{
  RCC_PeriphCLKInitTypeDef clk = {0};
  clk.PeriphClockSelection = RCC_PERIPHCLK_ADC;
  clk.AdcClockSelection = RCC_ADCCLKSOURCE_TIMG;
  clk.AdcDivider = (HAL_RCCEx_GetTIMGFreq() + ADC_MAX_HZ - 1u) / ADC_MAX_HZ;
  if (HAL_RCCEx_PeriphCLKConfig(&clk) != HAL_OK || emg_adc_clock_hz() > ADC_MAX_HZ) {
    return -1;
  }
  __HAL_RCC_ADC12_CLK_ENABLE();
  /* Same RIF setting as ST's ADC example: ADC12 secure, unprivileged access allowed. */
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_ADC12,
                                        RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_NPRIV);
  return 0;
}

static void pins_init(void)
{
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  g.Mode = GPIO_MODE_ANALOG;
  g.Pull = GPIO_NOPULL;
  g.Pin = GPIO_PIN_9; /* PA9 = ADC1_INP10, A1 */
  HAL_GPIO_Init(GPIOA, &g);
  g.Pin = GPIO_PIN_3; /* PF3 = ADC1_INP16, A4 */
  HAL_GPIO_Init(GPIOF, &g);
  g.Pin = GPIO_PIN_10; /* PB10 = ADC1_INP8, A5 */
  HAL_GPIO_Init(GPIOB, &g);
  HAL_GPIO_ConfigPinAttributes(GPIOA, GPIO_PIN_9, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOF, GPIO_PIN_3, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOB, GPIO_PIN_10, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
}

static int adc_init(void)
{
  static const uint32_t k_channel[SSI_EMG_CH] = {ADC_CHANNEL_10, ADC_CHANNEL_16, ADC_CHANNEL_8};
  static const uint32_t k_rank[SSI_EMG_CH] = {ADC_REGULAR_RANK_1, ADC_REGULAR_RANK_2,
                                              ADC_REGULAR_RANK_3};
  ADC_MultiModeTypeDef mm = {0};
  ADC_ChannelConfTypeDef ch = {0};

  s_adc.Instance = ADC1;
  s_adc.Init.Resolution = ADC_RESOLUTION_12B;
  s_adc.Init.GainCompensation = 0;
  s_adc.Init.ScanConvMode = ADC_SCAN_ENABLE;
  s_adc.Init.EOCSelection = ADC_EOC_SEQ_CONV;
  s_adc.Init.LowPowerAutoWait = DISABLE;
  s_adc.Init.ContinuousConvMode = DISABLE;
  s_adc.Init.NbrOfConversion = SSI_EMG_CH;
  s_adc.Init.DiscontinuousConvMode = DISABLE;
  s_adc.Init.ExternalTrigConv = s_trigger;
  s_adc.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_RISING;
  s_adc.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DMA_CIRCULAR;
  s_adc.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
  s_adc.Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;
  s_adc.Init.OversamplingMode = DISABLE;
  if (HAL_ADC_Init(&s_adc) != HAL_OK) {
    return -2;
  }
  mm.Mode = ADC_MODE_INDEPENDENT;
  if (HAL_ADCEx_MultiModeConfigChannel(&s_adc, &mm) != HAL_OK) {
    return -3;
  }
  ch.SamplingTime = ADC_SAMPLETIME_246CYCLES_5; /* source: TSZ122 buffer of the DK */
  ch.SingleDiff = ADC_SINGLE_ENDED;
  ch.OffsetNumber = ADC_OFFSET_NONE;
  ch.Offset = 0;
  for (uint32_t i = 0; i < SSI_EMG_CH; i++) {
    ch.Channel = k_channel[i];
    ch.Rank = k_rank[i];
    if (HAL_ADC_ConfigChannel(&s_adc, &ch) != HAL_OK) {
      return -4;
    }
  }
  if (HAL_ADCEx_Calibration_Start(&s_adc, ADC_SINGLE_ENDED) != HAL_OK) {
    return -5;
  }
  return 0;
}

static int dma_init(void)
{
  DMA_NodeConfTypeDef n = {0};
  __HAL_RCC_GPDMA1_CLK_ENABLE();
  n.NodeType = DMA_GPDMA_LINEAR_NODE;
  n.Init.Request = GPDMA1_REQUEST_ADC1;
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
    return -6;
  }
  s_dma.Instance = GPDMA1_Channel1;
  s_dma.InitLinkedList.Priority = DMA_LOW_PRIORITY_HIGH_WEIGHT;
  s_dma.InitLinkedList.LinkStepMode = DMA_LSM_FULL_EXECUTION;
  s_dma.InitLinkedList.LinkAllocatedPort = DMA_LINK_ALLOCATED_PORT0;
  s_dma.InitLinkedList.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  s_dma.InitLinkedList.LinkedListMode = DMA_LINKEDLIST_CIRCULAR;
  if (HAL_DMAEx_List_Init(&s_dma) != HAL_OK || HAL_DMAEx_List_LinkQ(&s_dma, &s_list) != HAL_OK) {
    return -7;
  }
  __HAL_LINKDMA(&s_adc, DMA_Handle, s_dma);
  if (HAL_DMA_ConfigChannelAttributes(&s_dma, DMA_CHANNEL_SEC | DMA_CHANNEL_PRIV |
                                                  DMA_CHANNEL_SRC_SEC | DMA_CHANNEL_DEST_SEC) != HAL_OK) {
    return -8;
  }
  HAL_NVIC_SetPriority(GPDMA1_Channel1_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(GPDMA1_Channel1_IRQn);
  HAL_NVIC_SetPriority(ADC1_2_IRQn, 6, 0); /* overrun only: HAL_ADC_Start_DMA enables just OVR */
  HAL_NVIC_EnableIRQ(ADC1_2_IRQn);
  return 0;
}

int emg_adc_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error,
                 uint32_t trigger)
{
  int rc;
  s_trigger = trigger;
  s_flags = flags;
  s_flag_block = flag_block;
  s_flag_error = flag_error;
  if ((rc = clock_init()) != 0) {
    return rc;
  }
  pins_init();
  if ((rc = adc_init()) != 0) {
    return rc;
  }
  return dma_init();
}

int emg_adc_start(void)
{
  s_blocks = 0u;
  return (HAL_ADC_Start_DMA(&s_adc, s_buf, EMG_WORDS) == HAL_OK) ? 0 : -1;
}

void emg_adc_stop(void)
{
  (void)HAL_ADC_Stop_DMA(&s_adc);
}

uint32_t emg_adc_blocks_done(void)
{
  return s_blocks;
}

const uint32_t *emg_adc_window(uint32_t k)
{
  return &s_buf[(k & 1u) * (EMG_WORDS / 2u)];
}

uint32_t emg_adc_errors(void)
{
  return s_errors;
}

uint32_t emg_adc_clock_hz(void)
{
  return HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_ADC);
}

/* ISR context: count and notify, nothing else. */
static void notify(ULONG flag)
{
  if (s_flags != TX_NULL) {
    (void)tx_event_flags_set(s_flags, flag, TX_OR);
  }
}

void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc == &s_adc) {
    s_blocks++;
    notify(s_flag_block);
  }
}

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc == &s_adc) {
    s_blocks++;
    notify(s_flag_block);
  }
}

void HAL_ADC_ErrorCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc == &s_adc) {
    s_errors++;
    notify(s_flag_error);
  }
}

void GPDMA1_Channel1_IRQHandler(void)
{
  HAL_DMA_IRQHandler(&s_dma);
}

void ADC1_2_IRQHandler(void)
{
  HAL_ADC_IRQHandler(&s_adc);
}
