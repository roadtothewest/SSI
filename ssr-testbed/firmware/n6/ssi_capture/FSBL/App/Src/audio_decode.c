#include "audio_decode.h"

void audio_extract_left(const uint32_t *stereo, int32_t *out, size_t frames)
{
  for (size_t i = 0; i < frames; i++) {
    out[i] = audio_sign_extend24(stereo[2u * i]);
  }
}

uint32_t audio_right_activity(const uint32_t *stereo, size_t frames)
{
  uint32_t n = 0;
  for (size_t i = 0; i < frames; i++) {
    if ((stereo[2u * i + 1u] & 0x00FFFFFFu) != 0u) {
      n++;
    }
  }
  return n;
}
