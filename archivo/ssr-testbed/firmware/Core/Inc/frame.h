#ifndef __FRAME_H
#define __FRAME_H

#include "main.h"

typedef struct {
    uint32_t timestamp;
    int32_t  samples[AUDIO_SAMPLES_PER_FRAME];
    uint16_t count;
    bool     valid;
} audio_frame_t;

void frame_build_audio(cdc_frame_t *cdc, const audio_frame_t *audio);
void frame_process_audio_half(void);
void frame_process_audio_full(void);

uint32_t frame_get_timestamp(void);

#endif
