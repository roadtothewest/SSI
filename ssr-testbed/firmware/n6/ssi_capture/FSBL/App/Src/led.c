#include "led.h"

#include "stm32n6xx_hal.h"

/* MB1939: LD1 green on PO1 (active high, VDDIO2 bank), LD2 red on PG10 (active low). */
void led_init(void)
{
  GPIO_InitTypeDef g = {0};
  HAL_PWREx_EnableVddIO2();
  __HAL_RCC_GPIOO_CLK_ENABLE();
  __HAL_RCC_GPIOG_CLK_ENABLE();
  g.Mode = GPIO_MODE_OUTPUT_PP;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_LOW;
  g.Pin = GPIO_PIN_1;
  HAL_GPIO_Init(GPIOO, &g);
  g.Pin = GPIO_PIN_10;
  HAL_GPIO_Init(GPIOG, &g);
  led_set(LED_GREEN, 0);
  led_set(LED_RED, 0);
}

void led_set(led_t led, int on)
{
  if (led == LED_GREEN) {
    HAL_GPIO_WritePin(GPIOO, GPIO_PIN_1, on ? GPIO_PIN_SET : GPIO_PIN_RESET);
  } else {
    HAL_GPIO_WritePin(GPIOG, GPIO_PIN_10, on ? GPIO_PIN_RESET : GPIO_PIN_SET);
  }
}

void led_toggle(led_t led)
{
  if (led == LED_GREEN) {
    HAL_GPIO_TogglePin(GPIOO, GPIO_PIN_1);
  } else {
    HAL_GPIO_TogglePin(GPIOG, GPIO_PIN_10);
  }
}
