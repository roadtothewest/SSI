#include "avx_block.h"

static void put16(uint8_t *p, uint16_t v)
{
  p[0] = (uint8_t)v;
  p[1] = (uint8_t)(v >> 8);
}

static void put32(uint8_t *p, uint32_t v)
{
  p[0] = (uint8_t)v;
  p[1] = (uint8_t)(v >> 8);
  p[2] = (uint8_t)(v >> 16);
  p[3] = (uint8_t)(v >> 24);
}

uint16_t avx_crc16(const void *data, size_t len)
{
  const uint8_t *p = (const uint8_t *)data;
  uint16_t crc = 0xFFFFu;
  while (len--) {
    crc ^= (uint16_t)(*p++ << 8);
    for (int b = 0; b < 8; b++) {
      crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1);
    }
  }
  return crc;
}

void avx_block_build(uint8_t *blk, uint32_t seq, uint32_t t0_us, uint16_t flags,
                     const uint16_t *emg, const int32_t *audio)
{
  blk[0] = AVX_SYNC0;
  blk[1] = AVX_SYNC1;
  blk[2] = AVX_TYPE;
  blk[3] = AVX_VERSION;
  put32(blk + 4, seq);
  put32(blk + 8, t0_us);
  put16(blk + 12, AVX_TUPLES);
  put16(blk + 14, flags);
  uint8_t *t = blk + AVX_HDR_SIZE;
  for (uint32_t i = 0; i < AVX_TUPLES; i++, t += AVX_TUPLE_SIZE) {
    put32(t, t0_us + AVX_TUPLE_US * i);
    for (uint32_t c = 0; c < AVX_ADC_CH; c++) {
      put16(t + 4u + 2u * c, emg[AVX_ADC_CH * i + c]);
    }
    for (uint32_t k = 0; k < AVX_VOZ_PER_TUPLE; k++) {
      /* GCC: >> on a negative int is arithmetic, i.e. floor(sample / 256) */
      put16(t + 10u + 2u * k, (uint16_t)(int16_t)(audio[AVX_VOZ_PER_TUPLE * i + k] >> 8));
    }
  }
  put16(blk + AVX_CRC_OFFSET, avx_crc16(blk, AVX_CRC_OFFSET));
}
