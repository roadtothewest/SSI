#ifndef __INMP441_H
#define __INMP441_H

#include "main.h"

#define INMP441_I2S               hi2s3

extern volatile uint8_t  inmp441_audio_ready;
extern volatile uint16_t inmp441_frame_count;
extern int32_t inmp441_audio_buf[AUDIO_SAMPLES_PER_FRAME];
extern int32_t inmp441_audio_buf2[AUDIO_SAMPLES_PER_FRAME];

bool inmp441_init(void);
bool inmp441_start_dma(void);

void HAL_I2S_TxHalfCpltCallback(I2S_HandleTypeDef *hi2s);
void HAL_I2S_TxCpltCallback(I2S_HandleTypeDef *hi2s);

#endif
