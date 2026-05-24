#include "frame.h"
#include "iis3dwb.h"
#include "inmp441.h"
#include "usb_cdc.h"
#include "sync_timer.h"
#include <string.h>

static uint8_t tx_frame_buf[2048];
static acc_frame_t last_acc;
static audio_frame_t last_audio;

void frame_build_acc(cdc_frame_t *cdc, const acc_frame_t *acc)
{
    cdc->sync0 = CDC_SYNC0;
    cdc->sync1 = CDC_SYNC1;
    cdc->frame_type = CDC_TYPE_ACC;
    cdc->flags = 0;
    cdc->timestamp = acc->timestamp;
    cdc->data_len = acc->count * 3 * sizeof(int16_t);

    uint8_t *ptr = cdc->data;
    for (uint16_t i = 0; i < acc->count; i++) {
        ptr[0] = acc->acc_x[i] & 0xFF;
        ptr[1] = (acc->acc_x[i] >> 8) & 0xFF;
        ptr[2] = acc->acc_y[i] & 0xFF;
        ptr[3] = (acc->acc_y[i] >> 8) & 0xFF;
        ptr[4] = acc->acc_z[i] & 0xFF;
        ptr[5] = (acc->acc_z[i] >> 8) & 0xFF;
        ptr += 6;
    }
}

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

void frame_process_acc_half(void)
{
    uint32_t ts = sync_timer_get_us();
    int16_t *buf;

    if (iis3dwb_acc_buf2 == active_buf) {
        buf = iis3dwb_acc_buf;
    } else {
        buf = iis3dwb_acc_buf2;
    }

    last_acc.timestamp = ts;
    last_acc.count = ACC_SAMPLES_PER_FRAME;
    last_acc.valid = true;

    for (uint16_t i = 0; i < ACC_SAMPLES_PER_FRAME; i++) {
        last_acc.acc_x[i] = buf[i * 3];
        last_acc.acc_y[i] = buf[i * 3 + 1];
        last_acc.acc_z[i] = buf[i * 3 + 2];
    }

    cdc_frame_t *cdc = (cdc_frame_t*)tx_frame_buf;
    frame_build_acc(cdc, &last_acc);
    usb_cdc_send_frame(CDC_TYPE_ACC, ts,
        cdc->data, cdc->data_len);
}

void frame_process_acc_full(void)
{
    frame_process_acc_half();
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
