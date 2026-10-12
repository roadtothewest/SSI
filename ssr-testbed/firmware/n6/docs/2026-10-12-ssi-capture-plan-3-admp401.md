# Plan 3: micrófono analógico ADMP401 (`ssi_capture`)

**Objetivo:** reemplazar el INMP441 (defectuoso, ver `~/2026-2/SSI/notas/2026-10-10-microfono-inmp441.md`) por el SparkFun MEMS Microphone Breakout INMP401/ADMP401 (BOB-09868), que es analógico, sin perder el camino del INMP441, que queda como opción de compilación.

**Spec:** `2026-10-09-ssi-capture-spec.md` (v0.3). Este plan cambia la fuente del audio y la sincronía. El bloque de PROTOCOLO_SPI.md, `seq`, `ts` y `flags` no cambian.

## Hardware

| ADMP401 | DK | Pin N6 | Uso |
|---|---|---|---|
| VCC | IOREF (CN8-2), 3,3 V | — | Cable propio, separado del AFE (CN8-4) |
| GND | GND (CN8-7) | — | Segundo GND, separado del AFE (CN8-6) |
| AUD | A3 (CN7-4) | PA12 = ADC12_INP13 | Divisor ×0,5437 + buffer U7 → ADC2 |

- Salida de la placa: OPA344 ×67, en reposo VCC/2 (≈ 1,65 V → código ≈ 2041), ~200 mVpp a un brazo, 100 Hz a 15 kHz.
- A3 en vez de A0: A0 comparte el op-amp doble U8 con A1 (canal 1 del EMG). A3 va en U7, junto a A2, que queda libre.
- Sin cables en A2, D6, D8 ni el puente D6→D2.

## Diseño

- **Selección de compilación:** opción de CMake `SSI_MIC_ANALOG` (por defecto ON) → `SSI_MIC_SRC = SSI_MIC_ANALOG`. Con OFF se compila el INMP441 por SAI, como hasta ahora. El micrófono analógico obliga a usar la sincronía por LPTIM.
- **Interfaz común `mic.h`**: `mic_init/start/stop/blocks_done/errors/clock_hz`, `mic_copy(k)` y `mic_decode(audio)` (16 kHz, escala de 24 bits como el INMP441), `mic_diag_raw()`, `mic_right_activity()` y `mic_sck_output()`. La implementan `mic_sai.c` (I²S) y `mic_adc.c` (analógico); cada archivo se compila completo o vacío según `SSI_MIC_SRC`, igual que `sync.c`.
- **`hse.c`**: el arranque del cristal (`hse_start`, `hse_mode`), compartido por `mic_sai` (PLL4) y la sincronía por LPTIM (CLKP). Es idempotente.
- **Micrófono analógico (`mic_adc.c`):** ADC2, canal 13, 12 bits, 246,5 ciclos (igual que el EMG, así ambos muestrean con el mismo retardo tras el disparo), disparo LPTIM2_CH1 a 64 kHz, DMA circular de palabras en GPDMA1 canal 3 (2 × 640 muestras = 10 ms por mitad) con callbacks propios del DMA. La HAL del ADC1 ya usa los callbacks globales del ADC y la IRQ ADC1_2; el ADC2 no habilita interrupciones del ADC y cuenta los errores por el DMA. El reloj del ADC12 lo configura `emg_adc` (se inicializa antes).
- **Sincronía (`sync.c`, backend LPTIM):** LPTIM1 (EMG, 2 kHz, ARR 23999) y LPTIM2 (micrófono, 64 kHz, ARR 749), ambos con reloj CLKP = HSE 48 MHz y comparación en 375. Arrancan seguidos con las interrupciones deshabilitadas (< 0,1 µs de diferencia). El flanco del EMG *i* coincide con el de la muestra cruda 32*i*, que la decimación convierte en la muestra de audio 8*i*: c = 0, igual que antes.
- **Filtro (`audio_fir.c`, lógica pura):** FIR de fase lineal de 97 coeficientes (sinc con ventana de Kaiser, β = 6,755, corte en 8 kHz, ≥ 70 dB desde 9,5 kHz), coeficientes Q30 con suma exacta 2³⁰ (`tools/gen_audio_fir.py`), decimación ÷4 → 16 kHz, salida en la escala de 24 bits (código × 4096) y bloqueador de continua de un polo (a = 1 − 2⁻¹⁰, ≈ 2,5 Hz). Historia y bloqueador se ceban con la primera muestra (sin transitorio). **Retardo fijo: 48 muestras crudas = 12 muestras de audio = 0,75 ms**, que la Pi resta como hacía con el filtro del INMP441 (1078 µs).
- **`voz`** sigue siendo `>> 8` del valor de 24 bits: el fondo de escala del ADC equivale a ±32768.

## Decisiones (rulings)

- R1: 64 kHz y FIR, no muestreo directo a 16 kHz: la placa deja pasar hasta 15 kHz y a 16 kHz eso se mezclaría con la voz. Si sale mal: más CPU (≈ 1,5 M MAC/s, < 1 %).
- R2: el retardo del FIR no se compensa en el firmware; se documenta. Compensarlo exigiría tomar muestras de la ventana siguiente (+10 ms de latencia). Si sale mal: la Pi resta 0,75 ms.
- R3: EMG intacto (ADC1, 2 kHz, mismo código). Lo nuevo es el ADC2. Si sale mal: el ADC2 comparte el reloj del ADC12 y debe inicializarse después de `emg_adc`.
- R4: punto fijo (Q30, acumulador de 64 bits) en vez de float: el mismo código y los mismos resultados en el PC y en la placa.

## Tareas

1. **`audio_fir` + generador + prueba en el PC** (`test_audio_fir`): ganancia en continua, 1 kHz pasa con ±0,1 dB, 12 kHz y 20 kHz atenuados ≥ 60 dB, continua eliminada, bloques partidos iguales a uno entero, impulso centrado en la muestra 12 y saturación sin desborde.
2. **`mic.h` + `hse.c` + `mic_sai` adaptado** (acq, capture y mon usan `mic_*`). Compila el INMP441 (ETR y LPTIM) igual que antes.
3. **`mic_adc.c` + LPTIM2 en `sync.c` + orden de arranque en `capture.c` + opción `SSI_MIC_ANALOG`**. En la placa: `STAT` 100 ventanas/s sin pérdidas, `SIG` con el micrófono, `tools/mic_tone_check.sh` → PASS.
4. **P4 analógica:** `diag.py pulse --analog` (cruce de umbral en vez de "primera muestra distinta de 0"; el pulso de D7 entra por A1 y A3). Se espera c = 12 (el retardo del FIR) y constante en 10 reinicios.
5. **Documentación:** README (conexiones, INIT, latencias), spec §4 y nota para Vicente.
