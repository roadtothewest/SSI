#ifndef APP_H
#define APP_H

#include "stm32n6xx_hal.h"

/* main(), USER CODE 2, before the kernel starts: logger, LEDs, boot report. */
void app_early_init(UART_HandleTypeDef *huart);
/* App_ThreadX_Init(): creates every RTOS object and thread (no HAL waits here:
   interrupts are still masked during tx_application_define). */
void app_start(void);

#endif
