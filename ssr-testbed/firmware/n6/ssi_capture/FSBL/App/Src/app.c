#include "app.h"

#include "led.h"
#include "log.h"
#include "mon.h"
#include "ssi_config.h"
#include "tx_api.h"

extern uint32_t __snoncacheable;  /* ssi_capture_fsbl.ld */
extern uint32_t __enoncacheable;

#define NC_BASE 0x341F8000u
#define NC_END  0x34200000u

static TX_THREAD s_mon;
static ULONG s_mon_stack[1024]; /* 4 KB: vsnprintf */

void app_early_init(UART_HandleTypeDef *huart)
{
  const uint32_t s = (uint32_t)&__snoncacheable;
  const uint32_t e = (uint32_t)&__enoncacheable;
  log_init(huart);
  led_init();
  log_printf("SSI capture fw %lu.%lu.%lu (%s %s)", (unsigned long)((SSI_FW_VERSION >> 16) & 0xFFu),
             (unsigned long)((SSI_FW_VERSION >> 8) & 0xFFu), (unsigned long)(SSI_FW_VERSION & 0xFFu),
             __DATE__, __TIME__);
  log_printf("CLK cpu=%lu", (unsigned long)SystemCoreClock);
  log_printf("NC 0x%08lx..0x%08lx %s", (unsigned long)s, (unsigned long)e,
             (s >= NC_BASE && e <= NC_END) ? "OK" : "FAIL");
}

void app_start(void)
{
  log_rtos_init();
  tx_thread_create(&s_mon, "mon", mon_thread_entry, 0, s_mon_stack, sizeof s_mon_stack, 10, 10,
                   TX_NO_TIME_SLICE, TX_AUTO_START);
}
