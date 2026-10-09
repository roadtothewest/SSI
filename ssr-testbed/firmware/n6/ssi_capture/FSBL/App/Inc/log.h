#ifndef LOG_H
#define LOG_H

#include "stm32n6xx_hal.h"

/* Line logger on the ST-LINK VCP (USART1, handle created by CubeMX code in main.c).
   Thread-safe after log_rtos_init(). Never call from an ISR: it blocks on the UART. */
void log_init(UART_HandleTypeDef *huart);
void log_rtos_init(void);
void log_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

#endif
