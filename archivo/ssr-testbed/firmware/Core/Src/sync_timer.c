#include "sync_timer.h"

bool sync_timer_init(void)
{
    HAL_StatusTypeDef ret = HAL_TIM_Base_Start(&htim2);
    return (ret == HAL_OK);
}

uint32_t sync_timer_get_us(void)
{
    return __HAL_TIM_GET_COUNTER(&htim2);
}

void sync_timer_reset(void)
{
    __HAL_TIM_SET_COUNTER(&htim2, 0);
}
