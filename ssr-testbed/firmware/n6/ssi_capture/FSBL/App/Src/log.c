#include "log.h"

#include <stdarg.h>
#include <stdio.h>

#include "tx_api.h"

static UART_HandleTypeDef *s_uart;
static TX_MUTEX s_mutex;
static int s_rtos;
static char s_line[192];

void log_init(UART_HandleTypeDef *huart)
{
  s_uart = huart;
}

void log_rtos_init(void)
{
  if (tx_mutex_create(&s_mutex, "log", TX_INHERIT) == TX_SUCCESS) {
    s_rtos = 1;
  }
}

void log_printf(const char *fmt, ...)
{
  if (s_uart == NULL) {
    return;
  }
  /* Before the scheduler runs there is a single context: no lock needed. */
  const int locked = s_rtos && (tx_thread_identify() != TX_NULL);
  if (locked) {
    tx_mutex_get(&s_mutex, TX_WAIT_FOREVER);
  }
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(s_line, sizeof s_line - 2u, fmt, ap);
  va_end(ap);
  if (n < 0) {
    n = 0;
  } else if (n > (int)sizeof s_line - 3) {
    n = (int)sizeof s_line - 3;
  }
  s_line[n++] = '\r';
  s_line[n++] = '\n';
  (void)HAL_UART_Transmit(s_uart, (uint8_t *)s_line, (uint16_t)n, 100);
  if (locked) {
    tx_mutex_put(&s_mutex);
  }
}
