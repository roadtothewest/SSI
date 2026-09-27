#include "main.h"
#include "inmp441.h"
#include "usb_cdc.h"
#include "frame.h"
#include "sync_timer.h"

UART_HandleTypeDef huart3;
I2S_HandleTypeDef hi2s3;
TIM_HandleTypeDef htim2;

static void MX_DEBUG_UART_Init(void)
{
    huart3.Instance = USART3;
    huart3.Init.BaudRate = 115200;
    huart3.Init.WordLength = UART_WORDLENGTH_8B;
    huart3.Init.StopBits = UART_STOPBITS_1;
    huart3.Init.Parity = UART_PARITY_NONE;
    huart3.Init.Mode = UART_MODE_TX_RX;
    huart3.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart3.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&huart3);
}

static void MX_I2S3_Init(void)
{
    hi2s3.Instance = SPI2;
    hi2s3.Init.Mode = I2S_MODE_MASTER_RX;
    hi2s3.Init.Standard = I2S_STANDARD_PHILIPS;
    hi2s3.Init.DataFormat = I2S_DATAFORMAT_24B;
    hi2s3.Init.MCLKOutput = I2S_MCLKOUTPUT_DISABLE;
    hi2s3.Init.AudioFreq = AUDIO_SAMPLE_RATE_HZ;
    hi2s3.Init.CPOL = I2S_CPOL_LOW;
    hi2s3.Init.ClockSource = I2S_CLOCK_PLL;
    hi2s3.Init.FirstBit = I2S_FIRSTBIT_MSB;
    HAL_I2S_Init(&hi2s3);
}

static void MX_TIM2_Init(void)
{
    htim2.Instance = TIM2;
    htim2.Init.Prescaler = (HAL_RCC_GetHCLKFreq() / TIMER_FREQ_HZ) - 1;
    htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
    htim2.Init.Period = 0xFFFFFFFF;
    htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
    htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
    HAL_TIM_Base_Init(&htim2);
}

static void MX_GPIO_Init(void)
{
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
}

static void MX_DMA_Init(void)
{
    __HAL_RCC_DMA1_CLK_ENABLE();
    __HAL_RCC_DMA2_CLK_ENABLE();

    HAL_NVIC_SetPriority(DMA1_Stream0_IRQn, 5, 0);
    HAL_NVIC_EnableIRQ(DMA1_Stream0_IRQn);
    HAL_NVIC_SetPriority(DMA1_Stream1_IRQn, 5, 0);
    HAL_NVIC_EnableIRQ(DMA1_Stream1_IRQn);
    HAL_NVIC_SetPriority(DMA2_Stream0_IRQn, 5, 0);
    HAL_NVIC_EnableIRQ(DMA2_Stream0_IRQn);
    HAL_NVIC_SetPriority(DMA2_Stream1_IRQn, 5, 0);
    HAL_NVIC_EnableIRQ(DMA2_Stream1_IRQn);
}

void SystemClock_Config(void)
{
    RCC_OscInitTypeDef RCC_OscInitStruct = {0};
    RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

    __HAL_RCC_PWR_CLK_ENABLE();
    __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLM = 5;
    RCC_OscInitStruct.PLL.PLLN = 192;
    RCC_OscInitStruct.PLL.PLLP = 2;
    RCC_OscInitStruct.PLL.PLLQ = 4;
    RCC_OscInitStruct.PLL.PLLR = 2;
    HAL_RCC_OscConfig(&RCC_OscInitStruct);

    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK
                                | RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
    HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4);
}

int main(void)
{
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_DMA_Init();
    MX_I2S3_Init();
    MX_TIM2_Init();
    MX_DEBUG_UART_Init();

    sync_timer_init();
    usb_cdc_init();

    if (!inmp441_init()) {
        Error_Handler();
    }

    HAL_TIM_Base_Start(&htim2);

    inmp441_start_dma();

    uint32_t last_print = 0;
    uint32_t last_audio_frames = 0;

    while (1)
    {
        /* Captura EMG de 4 canales (ADC + DMA, frame 0x03): pendiente,
         * ver docs/refactor-emg-software.md */
        if (inmp441_audio_ready) {
            inmp441_audio_ready = 0;
            frame_process_audio_half();
        }
        if (inmp441_audio_ready) {
            inmp441_audio_ready = 0;
            frame_process_audio_full();
        }

        uint32_t now = sync_timer_get_us();
        if (now - last_print > 1000000) {
            last_print = now;
            uint32_t audio_delta = inmp441_frame_count - last_audio_frames;
            last_audio_frames = inmp441_frame_count;

            char buf[64];
            int n = snprintf(buf, sizeof(buf),
                "AUDIO: %u fps\r\n", audio_delta);
            HAL_UART_Transmit(&huart3, (uint8_t*)buf, n, 100);
        }
    }
}

void Error_Handler(void)
{
    __disable_irq();
    while (1) {
        asm("nop");
    }
}

void assert_failed(uint8_t *file, uint32_t line)
{
    char buf[64];
    snprintf(buf, sizeof(buf), "Assert: %s:%lu\r\n", file, line);
    HAL_UART_Transmit(&huart3, (uint8_t*)buf, strlen(buf), 100);
}
