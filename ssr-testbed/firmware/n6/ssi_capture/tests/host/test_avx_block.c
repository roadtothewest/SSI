#include <stdio.h>
#include <string.h>

#include "avx_block.h"
#include "test_util.h"

static uint32_t rd32(const uint8_t *p)
{
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }

int main(int argc, char **argv)
{
  uint8_t blk[AVX_BLOCK_SIZE];
  uint16_t emg[AVX_TUPLES * AVX_ADC_CH];
  int32_t audio[AVX_TUPLES * AVX_VOZ_PER_TUPLE];

  /* CRC-16/CCITT-FALSE check value (PROTOCOLO_SPI.md §2) */
  CHECK_EQ(avx_crc16("123456789", 9), 0x29B1);
  CHECK_EQ(avx_crc16("", 0), 0xFFFF);
  CHECK_EQ(AVX_HDR_SIZE + AVX_TUPLES * AVX_TUPLE_SIZE + 2u, AVX_BLOCK_SIZE);

  for (int i = 0; i < 60; i++) emg[i] = (uint16_t)(100 + 66 * i); /* 100 .. 3994 */
  for (int i = 0; i < 160; i++) audio[i] = (i - 80) * 1000;
  audio[0] = -8388608; /* full scale: -32768 */
  audio[1] = 8388607;  /* 32767 */
  audio[2] = -1;       /* arithmetic shift: -1 */
  audio[3] = 255;      /* 0 */
  audio[4] = -257;     /* -2 */
  memset(blk, 0xEE, sizeof blk);
  avx_block_build(blk, 7u, 140000u, AVX_F_SAI_ERR, emg, audio);

  CHECK_EQ(blk[0], 0xAA);
  CHECK_EQ(blk[1], 0x55);
  CHECK_EQ(blk[2], 0x04);
  CHECK_EQ(blk[3], 1);
  CHECK_EQ(rd32(blk + 4), 7);
  CHECK_EQ(rd32(blk + 8), 140000);
  CHECK_EQ(rd16(blk + 12), 20);
  CHECK_EQ(rd16(blk + 14), AVX_F_SAI_ERR);
  for (int i = 0; i < 20; i++) {
    const uint8_t *t = blk + AVX_HDR_SIZE + AVX_TUPLE_SIZE * i;
    CHECK_EQ(rd32(t), 140000 + 500 * i);
    for (int c = 0; c < 3; c++) CHECK_EQ(rd16(t + 4 + 2 * c), emg[3 * i + c]);
    for (int k = 0; k < 8; k++) CHECK_EQ((int16_t)rd16(t + 10 + 2 * k), audio[8 * i + k] / 256 - (audio[8 * i + k] % 256 < 0));
  }
  const uint8_t *t0 = blk + AVX_HDR_SIZE;
  CHECK_EQ((int16_t)rd16(t0 + 10), -32768);
  CHECK_EQ((int16_t)rd16(t0 + 12), 32767);
  CHECK_EQ((int16_t)rd16(t0 + 14), -1);
  CHECK_EQ((int16_t)rd16(t0 + 16), 0);
  CHECK_EQ((int16_t)rd16(t0 + 18), -2);
  CHECK_EQ(rd16(blk + AVX_CRC_OFFSET), avx_crc16(blk, AVX_CRC_OFFSET));

  if (argc > 1) { /* sample for the Python cross-check (CTest avx_block_py) */
    FILE *f = fopen(argv[1], "wb");
    CHECK(f != NULL);
    if (f) {
      CHECK_EQ(fwrite(blk, 1, AVX_BLOCK_SIZE, f), AVX_BLOCK_SIZE);
      fclose(f);
    }
  }
  TEST_END();
}
