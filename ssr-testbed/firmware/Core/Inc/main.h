#ifndef __MAIN_H
#define __MAIN_H

#include "stm32h7xx_hal.h"
#include <stdint.h>
#include <stdbool.h>

#define AUDIO_SAMPLE_RATE_HZ 16000
#define AUDIO_SAMPLES_PER_FRAME 128

#define USB_TX_BUF_SIZE      2048

extern TIM_HandleTypeDef htim2;
extern I2S_HandleTypeDef hi2s3;
extern UART_HandleTypeDef huart3;

void SystemClock_Config(void);
void MX_GPIO_Init(void);
void MX_DMA_Init(void);
void MX_I2S3_Init(void);
void MX_TIM2_Init(void);
void MX_USB_OTG_HS_CDC_Init(void);
void Error_Handler(void);

#endif
