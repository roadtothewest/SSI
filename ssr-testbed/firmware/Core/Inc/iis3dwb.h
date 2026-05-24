#ifndef __IIS3DWB_H
#define __IIS3DWB_H

#include "main.h"

#define IIS3DWB_SPI               hspi1
#define IIS3DWB_CS_PORT           GPIOA
#define IIS3DWB_CS_PIN            GPIO_PIN_4
#define IIS3DWB_INT_PORT          GPIOC
#define IIS3DWB_INT_PIN           GPIO_PIN_0

#define IIS3DWB_WHO_AM_I          0x0F
#define IIS3DWB_WHO_AM_I_VAL      0x71
#define IIS3DWB_CTRL1_XL          0x10
#define IIS3DWB_CTRL3_C           0x12
#define IIS3DWB_CTRL4_C           0x13
#define IIS3DWB_CTRL5_C           0x14
#define IIS3DWB_CTRL6_C           0x15
#define IIS3DWB_CTRL7_C           0x16
#define IIS3DWB_OUT_X_L_XL        0x28
#define IIS3DWB_FIFO_CTRL1        0x06
#define IIS3DWB_FIFO_CTRL2        0x07
#define IIS3DWB_FIFO_CTRL3        0x08
#define IIS3DWB_FIFO_CTRL4        0x09
#define IIS3DWB_FIFO_CTRL5        0x0A
#define IIS3DWB_WAKE_UP_THS       0x1B
#define IIS3DWB_WAKE_UP_DUR       0x1C
#define IIS3DWB_MD1_CFG           0x5E

#define IIS3DWB_SPI_TIMEOUT       100

extern volatile uint8_t  iis3dwb_acc_ready;
extern volatile uint16_t iis3dwb_frame_count;
extern int16_t iis3dwb_acc_buf[ACC_SAMPLES_PER_FRAME * 3];
extern int16_t iis3dwb_acc_buf2[ACC_SAMPLES_PER_FRAME * 3];

bool iis3dwb_init(void);
bool iis3dwb_read_reg(uint8_t reg, uint8_t *val);
bool iis3dwb_write_reg(uint8_t reg, uint8_t val);
bool iis3dwb_start_dma(void);
HAL_StatusTypeDef iis3dwb_dma_transfer(uint16_t *buf, uint16_t len);

void HAL_SPI_TxHalfCpltCallback(SPI_HandleTypeDef *hspi);
void HAL_SPI_TxCpltCallback(SPI_HandleTypeDef *hspi);
void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin);

#endif
