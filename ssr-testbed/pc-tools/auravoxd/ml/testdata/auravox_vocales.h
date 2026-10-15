/*
 * auravox_vocales.h: constantes del clasificador de vocales para la NPU del STM32N6570-DK.
 * Generado por auravox_vocales_npu.ipynb el 2026-10-15 05:40.
 * Modelo: auravox_vocales_int8.onnx (QDQ, int8 por canal). Entradas NCHW, que ST Edge AI conserva por defecto
 * para ONNX (con --inputs-ch-position chlast pasan a NHWC).
 *
 *   Canales EMG de entrada: CH3 (adc[2] del bloque SPI).
 *   in[0] cwt_mag  int8 [1][1][T][NF]: q( clip( (clip(dB, DB_MIN, DB_MAX) - mu[c][f]) * inv_sd[c][f], ±Z_CLIP ) )
 *   in[1] cwt_fase int8 [1][2][T][NF]: q( cos y sin de φ: [cos CH3, sin CH3] )
 *   out   logits   int8 [1][6]: clase = argmax (no hace falta descuantizar); nombres en avx_voc_clases
 *   q(x) = clamp(round_half_even(x / escala) + zp, -128, 127)
 *
 * CWT (auravoxd/dsp/cwt.go): W(f,c) = Σ_j x[c+j]·w_f[j]·e^(-i2πf·j/FS), j = -h_f..h_f, w_f gaussiana de
 * σ = W0/(2πf)·FS muestras, h_f = ceil(3σ), normalizada a Σw = 2. dB = 20·log10(|W| + 1e-12).
 * cos φ = Re W / (|W| + 1e-12), sin φ = Im W / (|W| + 1e-12).
 * x = sEMG en µV: (código·VREF_ADC/4095/GDK − VMID) / GAIN · 1e6.
 * Ventana: T columnas, una cada HOP muestras; la columna t de la ventana es la fila t de cada plano [c][t][:].
 */
#ifndef AURAVOX_VOCALES_H
#define AURAVOX_VOCALES_H

#include <stdint.h>
#include <math.h>

#define AVX_VOC_FS            2000
#define AVX_VOC_HOP           20
#define AVX_VOC_T             32
#define AVX_VOC_NF            32
#define AVX_VOC_NCH           1      /* canales EMG de entrada (avx_voc_canal) */
#define AVX_VOC_NFASE         2
#define AVX_VOC_NCLASES       6
#define AVX_VOC_USA_FASE      1
#define AVX_VOC_FASE_RELATIVA 0
#define AVX_VOC_W0            6.0f
#define AVX_VOC_FMIN          20.0f
#define AVX_VOC_FMAX          500.0f
#define AVX_VOC_HMAX          287      /* semiancho del núcleo de FMIN, en muestras */
#define AVX_VOC_DB_MIN        (-20.0f)
#define AVX_VOC_DB_MAX        (60.0f)
#define AVX_VOC_Z_CLIP        5.0f
#define AVX_VOC_VREF_ADC      1.8f
#define AVX_VOC_GDK           0.5437f
#define AVX_VOC_VMID          1.65f
#define AVX_VOC_GAIN          2500.0f
#define AVX_VOC_MAG_ESCALA    0.0347101912f
#define AVX_VOC_MAG_ZP        (16)
#define AVX_VOC_FASE_ESCALA   0.00784313772f
#define AVX_VOC_FASE_ZP       (0)
#define AVX_VOC_OUT_ESCALA    0.0517425016f
#define AVX_VOC_OUT_ZP        (-7)

static const uint8_t avx_voc_canal[1] = {2};

static const float avx_voc_freqs[32] = {
    20.0f, 22.188341f, 24.616125f, 27.309547f, 30.297678f, 33.612762f, 37.290569f, 41.370796f, 45.897465f, 50.91943f, 56.490887f, 62.671951f,
    69.529335f, 77.137032f, 85.577133f, 94.940735f, 105.32887f, 116.85365f, 129.63942f, 143.82419f, 159.561f, 177.0197f, 196.38869f, 217.87695f,
    241.7164f, 268.16431f, 297.50604f, 330.05829f, 366.1723f, 406.23779f, 450.68713f, 500.0f
};

static const uint16_t avx_voc_semi[32] = {
    287, 259, 233, 210, 190, 171, 154, 139, 125, 113, 102, 92,
    83, 75, 67, 61, 55, 50, 45, 40, 36, 33, 30, 27,
    24, 22, 20, 18, 16, 15, 13, 12
};

/* media y 1/desvío de la magnitud en dB, por canal y frecuencia */
static const float avx_voc_mu[1][32] = {
    {
        -11.855948f, -10.344532f, -9.2150688f, -8.5080843f, -7.7551432f, -6.4563718f, 0.038491387f, 9.7136726f, 15.263374f, 16.500866f, 14.584217f, 10.457282f,
        5.3196397f, 2.3434362f, 3.6703265f, 5.3649282f, 5.3275208f, 3.6760201f, 2.3873887f, 1.6640158f, 2.3529813f, 4.1713228f, 4.8294921f, 4.4607863f,
        4.072166f, 4.4253778f, 4.6412153f, 4.49827f, 4.474658f, 4.3386459f, 4.0594845f, 3.5963597f
    }
};

static const float avx_voc_inv_sd[1][32] = {
    {
        0.17492843f, 0.16484936f, 0.15409538f, 0.1408712f, 0.12866195f, 0.12396675f, 0.15659304f, 0.2037355f, 0.22560057f, 0.22867753f, 0.22129987f, 0.2027185f,
        0.17078024f, 0.16815841f, 0.13312566f, 0.11174023f, 0.11085751f, 0.11687693f, 0.14773147f, 0.16070467f, 0.17129388f, 0.15448265f, 0.13087836f, 0.13826422f,
        0.15727846f, 0.15824135f, 0.15074717f, 0.15095171f, 0.15598595f, 0.15989174f, 0.16623321f, 0.16980134f
    }
};

static const char *const avx_voc_clases[AVX_VOC_NCLASES] = {"reposo", "a", "e", "i", "o", "u"};

static inline int8_t avx_voc_q(float x, float escala, int zp)
{
    float q = rintf(x / escala) + (float)zp;
    return (int8_t)(q < -128.0f ? -128.0f : (q > 127.0f ? 127.0f : q));
}

/* Magnitud de la CWT (dB) del canal c (índice en avx_voc_canal) y la frecuencia f → valor int8 de cwt_mag */
static inline int8_t avx_voc_q_mag(float db, int c, int f)
{
    db = db < AVX_VOC_DB_MIN ? AVX_VOC_DB_MIN : (db > AVX_VOC_DB_MAX ? AVX_VOC_DB_MAX : db);
    float z = (db - avx_voc_mu[c][f]) * avx_voc_inv_sd[c][f];
    z = z < -AVX_VOC_Z_CLIP ? -AVX_VOC_Z_CLIP : (z > AVX_VOC_Z_CLIP ? AVX_VOC_Z_CLIP : z);
    return avx_voc_q(z, AVX_VOC_MAG_ESCALA, AVX_VOC_MAG_ZP);
}

/* Índice NCHW del elemento [plano][t][f] de una entrada */
#define AVX_VOC_IDX(plano, t, f)  (((plano) * AVX_VOC_T + (t)) * AVX_VOC_NF + (f))

#endif /* AURAVOX_VOCALES_H */
