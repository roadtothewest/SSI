#ifndef LED_H
#define LED_H

typedef enum { LED_GREEN = 0, LED_RED = 1 } led_t;

void led_init(void);
void led_set(led_t led, int on);
void led_toggle(led_t led);

#endif
