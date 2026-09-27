#include "frame.h"
#include "inmp441.h"
#include "usb_cdc.h"
#include "sync_timer.h"
#include <string.h>

static uint8_t tx_frame_buf[2048];
static audio_frame_t last_audio;

void frame_build_audio(cdc_frame_t *cdc, const audio_frame_t *audio)
{
    cdc->sync0 = CDC_SYNC0;
    cdc->sync1 = CDC_SYNC1;
    cdc->frame_type = CDC_TYPE_AUDIO;
    cdc->flags = 0;
    cdc->timestamp = audio->timestamp;
    cdc->data_len = audio->count * sizeof(int32_t);

    uint8_t *ptr = cdc->data;
    for (uint16_t i = 0; i < audio->count; i++) {
        ptr[0] = audio->samples[i] & 0xFF;
        ptr[1] = (audio->samples[i] >> 8) & 0xFF;
        ptr[2] = (audio->samples[i] >> 16) & 0xFF;
        ptr[3] = (audio->samples[i] >> 24) & 0xFF;
        ptr += 4;
    }
}

void frame_process_audio_half(void)
{
    uint32_t ts = sync_timer_get_us();
    int32_t *buf;

    if (inmp441_audio_buf2 == active_buf) {
        buf = inmp441_audio_buf;
    } else {
        buf = inmp441_audio_buf2;
    }

    last_audio.timestamp = ts;
    last_audio.count = AUDIO_SAMPLES_PER_FRAME;
    last_audio.valid = true;

    for (uint16_t i = 0; i < AUDIO_SAMPLES_PER_FRAME; i++) {
        last_audio.samples[i] = buf[i];
    }

    cdc_frame_t *cdc = (cdc_frame_t*)tx_frame_buf;
    frame_build_audio(cdc, &last_audio);
    usb_cdc_send_frame(CDC_TYPE_AUDIO, ts,
        cdc->data, cdc->data_len);
}

void frame_process_audio_full(void)
{
    frame_process_audio_half();
}
