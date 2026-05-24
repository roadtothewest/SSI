#ifndef __FRAME_H
#define __FRAME_H

#include "main.h"

typedef struct {
    uint32_t timestamp;
    int16_t  acc_x[ACC_SAMPLES_PER_FRAME];
    int16_t  acc_y[ACC_SAMPLES_PER_FRAME];
    int16_t  acc_z[ACC_SAMPLES_PER_FRAME];
    uint16_t count;
    bool     valid;
} acc_frame_t;

typedef struct {
    uint32_t timestamp;
    int32_t  samples[AUDIO_SAMPLES_PER_FRAME];
    uint16_t count;
    bool     valid;
} audio_frame_t;

void frame_build_acc(cdc_frame_t *cdc, const acc_frame_t *acc);
void frame_build_audio(cdc_frame_t *cdc, const audio_frame_t *audio);
void frame_process_acc_half(void);
void frame_process_acc_full(void);
void frame_process_audio_half(void);
void frame_process_audio_full(void);

uint32_t frame_get_timestamp(void);

#endif
