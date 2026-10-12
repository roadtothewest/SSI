/*
 * Bloque SPI DK -> Raspberry Pi (AuraVox). Mismo formato que
 * pc-tools/auravoxd/frame/frame.go.
 *
 * - SPI5 esclavo, modo 0 (CPOL=0, CPHA=0), 8 bits, MSB primero. La Pi es maestro (~4 MHz).
 * - Cada 10 ms (20 tuplas de 500 us) el DK arma un bloque, calcula el CRC,
 *   lo deja en el buffer TX del DMA y sube DRDY. La Pi lee 538 bytes con CS bajo.
 *   Al terminar el DMA (o al subir NSS), el DK baja DRDY.
 * - seq sube en 1 por bloque: la Pi detecta bloques perdidos.
 * - adc[]: código crudo de 12 bits (0..4095) de A1, A2, A3.
 * - voz[]: INMP441 de 24 bits desplazado >> 8 (int16), 8 muestras por tupla.
 */
#ifndef AURAVOX_FRAME_H
#define AURAVOX_FRAME_H

#include <stdint.h>

#define AVX_SYNC0      0xAAu
#define AVX_SYNC1      0x55u
#define AVX_TYPE       0x04u
#define AVX_VERSION    1u
#define AVX_NTUPLES    20u
#define AVX_NVOICE     8u
#define AVX_NADC       3u

#define AVX_FLAG_ADC_OVERRUN  (1u << 0)
#define AVX_FLAG_SAI_OVERRUN  (1u << 1)

typedef struct __attribute__((packed)) {
    uint32_t ts_us;
    uint16_t adc[AVX_NADC];
    int16_t  voz[AVX_NVOICE];
} avx_tuple_t;                                  /* 26 B */

typedef struct __attribute__((packed)) {
    uint8_t     sync0, sync1, type, version;
    uint32_t    seq;
    uint32_t    t0_us;
    uint16_t    n;
    uint16_t    flags;
    avx_tuple_t t[AVX_NTUPLES];
    uint16_t    crc;                            /* CRC16 de todo lo anterior */
} avx_block_t;                                  /* 538 B */

_Static_assert(sizeof(avx_tuple_t) == 26, "avx_tuple_t debe medir 26 B");
_Static_assert(sizeof(avx_block_t) == 538, "avx_block_t debe medir 538 B");

/* CRC-16/CCITT-FALSE: polinomio 0x1021, inicial 0xFFFF ("123456789" -> 0x29B1). */
static inline uint16_t avx_crc16(const uint8_t *p, uint32_t len)
{
    uint16_t crc = 0xFFFFu;
    while (len--) {
        crc ^= (uint16_t)(*p++) << 8;
        for (int i = 0; i < 8; i++)
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1);
    }
    return crc;
}

/* Completa la cabecera y el CRC; las tuplas ya deben estar escritas en b->t[]. */
static inline void avx_block_seal(avx_block_t *b, uint32_t seq, uint16_t flags)
{
    b->sync0 = AVX_SYNC0; b->sync1 = AVX_SYNC1;
    b->type = AVX_TYPE;   b->version = AVX_VERSION;
    b->seq = seq;
    b->t0_us = b->t[0].ts_us;
    b->n = AVX_NTUPLES;
    b->flags = flags;
    b->crc = avx_crc16((const uint8_t *)b, sizeof(*b) - 2u);
}

#endif /* AURAVOX_FRAME_H */
