#ifndef AVX_BLOCK_H
#define AVX_BLOCK_H

#include <stddef.h>
#include <stdint.h>

/* SPI block of ssr-testbed/firmware/PROTOCOLO_SPI.md v1 (decoded by auravoxd on the RPi5):
   538 bytes, little-endian = 16-byte header + 20 tuples of 26 bytes + CRC-16 at 536. */
#define AVX_SYNC0         0xAAu
#define AVX_SYNC1         0x55u
#define AVX_TYPE          0x04u
#define AVX_VERSION       1u
#define AVX_TUPLES        20u
#define AVX_ADC_CH        3u
#define AVX_VOZ_PER_TUPLE 8u
#define AVX_HDR_SIZE      16u
#define AVX_TUPLE_SIZE    26u
#define AVX_CRC_OFFSET    536u
#define AVX_BLOCK_SIZE    538u
#define AVX_TUPLE_US      500u /* 2 kHz EMG */

#define AVX_F_ADC_LOST    0x0001u /* bit0: ADC data lost (overrun or window overwritten) */
#define AVX_F_SAI_ERR     0x0002u /* bit1: SAI overrun or error */

/* CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no final XOR. */
uint16_t avx_crc16(const void *data, size_t len);

/* One 10 ms window -> one sealed block. emg: AVX_TUPLES x AVX_ADC_CH codes (CH1..CH3 per
   tuple); audio: AVX_TUPLES x AVX_VOZ_PER_TUPLE sign-extended 24-bit samples, sent as
   sample >> 8. Tuple i gets ts_us = t0_us + 500 * i. */
void avx_block_build(uint8_t *blk, uint32_t seq, uint32_t t0_us, uint16_t flags,
                     const uint16_t *emg, const int32_t *audio);

#endif
