#ifndef AUDIO_DECODE_H
#define AUDIO_DECODE_H

#include <stddef.h>
#include <stdint.h>

/* SAI RX words carry the INMP441's 24-bit two's complement sample right-aligned;
   bits 31..24 are ignored (zero-padded or sign-extended both decode correctly). */
static inline int32_t audio_sign_extend24(uint32_t raw)
{
  return (int32_t)((raw & 0x00FFFFFFu) ^ 0x00800000u) - 0x00800000;
}

/* stereo = [L0, R0, L1, R1, ...]; writes the left slot (L/R pin tied to GND). */
void audio_extract_left(const uint32_t *stereo, int32_t *out, size_t frames);
/* Frames whose right slot is non-zero: should stay 0 (SD is Hi-Z there, pulled down). */
uint32_t audio_right_activity(const uint32_t *stereo, size_t frames);

#endif
