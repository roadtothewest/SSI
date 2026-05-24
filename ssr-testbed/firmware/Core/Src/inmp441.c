#include "inmp441.h"
#include "frame.h"
#include "usb_cdc.h"

volatile uint8_t  inmp441_audio_ready = 0;
volatile uint16_t inmp441_frame_count = 0;
int32_t inmp441_audio_buf[AUDIO_SAMPLES_PER_FRAME];
int32_t inmp441_audio_buf2[AUDIO_SAMPLES_PER_FRAME];

static int32_t *active_buf = NULL;
static bool use_buf2 = false;

bool inmp441_init(void)
{
    HAL_StatusTypeDef ret = HAL_I2S_Init(&INMP441_I2S);
    return (ret == HAL_OK);
}

bool inmp441_start_dma(void)
{
    use_buf2 = false;
    active_buf = inmp441_audio_buf;
    inmp441_audio_ready = 0;
    inmp441_frame_count = 0;

    HAL_StatusTypeDef ret = HAL_I2S_Receive_DMA(&INMP441_I2S,
        (uint16_t*)active_buf, AUDIO_SAMPLES_PER_FRAME * 2);

    if (ret == HAL_OK) {
        __HAL_I2S_ENABLE_IT(&INMP441_I2S, I2S_IT_FRE);
    }
    return (ret == HAL_OK);
}

void HAL_I2S_TxHalfCpltCallback(I2S_HandleTypeDef *hi2s)
{
    if (hi2s->Instance == INMP441_I2S.Instance) {
        inmp441_frame_count++;
        if (use_buf2) {
            active_buf = inmp441_audio_buf;
        } else {
            active_buf = inmp441_audio_buf2;
        }
        use_buf2 = !use_buf2;
        inmp441_audio_ready = 1;
        HAL_I2S_Receive_DMA(&INMP441_I2S,
            (uint16_t*)active_buf, AUDIO_SAMPLES_PER_FRAME * 2);
    }
}

void HAL_I2S_TxCpltCallback(I2S_HandleTypeDef *hi2s)
{
    if (hi2s->Instance == INMP441_I2S.Instance) {
        inmp441_frame_count++;
        if (use_buf2) {
            active_buf = inmp441_audio_buf;
        } else {
            active_buf = inmp441_audio_buf2;
        }
        use_buf2 = !use_buf2;
        inmp441_audio_ready = 1;
        HAL_I2S_Receive_DMA(&INMP441_I2S,
            (uint16_t*)active_buf, AUDIO_SAMPLES_PER_FRAME * 2);
    }
}
