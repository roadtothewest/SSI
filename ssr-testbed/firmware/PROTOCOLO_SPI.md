# Firmware del STM32N6570-DK: lo que espera la Raspberry Pi (`auravoxd`)

Especificación para escribir el firmware del DK. Cubre:
- qué se muestrea y a qué tasa;
- el formato exacto del bloque SPI (las "tuplas");
- el protocolo SPI + DRDY;
- cómo la Pi interpreta cada campo;
- qué falla si algo no se cumple.

La referencia de verdad es el código:
- `ssr-testbed/firmware/Core/Inc/auravox_frame.h`: struct C + CRC + `avx_block_seal()`, listo para incluir;
- `ssr-testbed/pc-tools/auravoxd/frame/frame.go`: el decodificador de la Pi;
- `pc-tools/auravoxd/source/spi.go`: el maestro SPI y la espera de DRDY;
- `pc-tools/auravoxd/stream/store.go`: la validación de `seq`, los flags y la conversión a µV.

El firmware que lo implementa está en `ssr-testbed/firmware/n6/` (rama `feat/n6-capture-fw`); su README tiene las conexiones, cómo compilar y las pruebas.

## 1. Qué captura el DK
| Señal | Fuente en el DK | Tasa | Formato en la tupla |
|---|---|---|---|
| CH1 submentoniano | ADC, pin Arduino **A1** | **2 kHz** | `adc[0]`: código crudo de 12 bits, 0..4095, alineado a la derecha |
| CH2 labio inferior | ADC, pin Arduino **A4** | 2 kHz | `adc[1]` |
| CH3 cuello/laringe | ADC, pin Arduino **A5** | 2 kHz | `adc[2]` |
| Voz | Micrófono analógico ADMP401 en **A3** (ADC2 a 64 kHz, FIR y decimación ÷4 en el firmware) | **16 kHz** | `voz[0..7]`: int16 = muestra en escala de 24 bits `>> 8` |

| AFE / micrófono | Pin Arduino del DK | Pin del N6 |
|---|---|---|
| CH1 | A1 | PA9 (ADC1_INP10) |
| CH2 | A4 | PF3 (ADC1_INP16) |
| CH3 | A5 | PB10 (ADC1_INP8) |
| ADMP401 AUD | A3 | PA12 (ADC2_INP13) |

- **El EMG no puede ir en A2 y A3:** A3 lleva el micrófono, y A2 comparte con A3 el op-amp doble U7 de la placa.
- **Las 3 muestras de ADC de una tupla se toman en el mismo instante** (o con unos µs de diferencia por el scan). El orden de `adc[]` es fijo: CH1, CH2, CH3.
- **Muestras de voz:** 16 kHz / 2 kHz = **8 por tupla**. `voz[k]` corresponde al instante `ts_us + k·62,5 µs`.
- **Si el ADC se configura con otra resolución** (10, 14 o 16 bits), hay que escalar a 12 bits antes de escribir `adc[]`. La Pi asume siempre 0..4095.

### Cómo la Pi convierte el ADC a µV
```
µV = (código · VrefADC / 4095 / GDK − VMid) / Gain · 1e6
```
- Valores por defecto (flags de `auravoxd`): `VrefADC = 1.8` V, `GDK = 0.5437`, `VMid = 1.65` V, `Gain = 2500`.
- **`GDK` = 560/1030 = 0,5437:** la placa pasa cada pin analógico del Arduino por un divisor 470k/560k y un buffer TSZ122 antes del ADC de 1,8 V (esquemático MB1939, hoja 9). La entrada es de alta impedancia, así que no carga al AFE.
  - Para confirmarlo en el banco: pon un DC conocido en A1, lee el código y calcula `GDK = código·1.8/4095 / V_pin`. Si difiere, ajusta `-gdk` en `auravoxd`.
- Con la salida del AFE en reposo (1,65 V), el código esperado es ≈ 1,65·0,5437/1,8·4095 ≈ **2041**.
- Excursión útil del AFE: 0,25–3,05 V en el pin. Con GDK = 0,5437 son 0,14–1,66 V en el ADC, dentro del rango de 1,8 V.

### Voz
- **ADMP401 (por defecto):**
  - el breakout de SparkFun (OPA344 ×67) da VCC/2 en reposo; se alimenta desde el 3V3 del DK (CN8-4);
  - el firmware lo muestrea a 64 kHz con el ADC2, aplica un FIR de 97 coeficientes, decima ÷4 y quita la continua;
  - el fondo de escala del ADC (0–3,3 V en A3) equivale a ±32768 en `voz`;
  - **el FIR retrasa la voz 0,75 ms fijos (12 muestras).** `auravoxd` los resta de todos los lags con `-voz-delay 0.75` (valor por defecto).
- **INMP441 (opción de compilación, `SSI_MIC_ANALOG=OFF`; el primero que se compró salió defectuoso):**
  - el pin L/R va a GND, así que el micrófono transmite en el slot izquierdo;
  - el slot derecho se descarta;
  - slots de 32 bits con 24 bits útiles;
  - SCK = 64·fs = 1,024 MHz y WS = 16 kHz. El DK es maestro I2S y genera SCK y WS.
- **Conversión a `voz`:**
  - si el SAI entrega la palabra de 32 bits con los 24 bits arriba (alineados a la izquierda): `voz = (int16_t)((int32_t)palabra >> 16)`;
  - si el SAI está en 24 bits alineados a la derecha: extiende el signo de 24 a 32 bits y haz `>> 8`.
  - su filtro de decimación interno retrasa la voz 1,078 ms: usar `auravoxd -voz-delay 1.078`.
- La Pi normaliza con `voz / 32768`, lo que da un rango de [−1, 1] (dBFS).
- Rangos de la HMI: el escalograma de la voz va de −80 a −10 dBFS. La detección de frases usa umbrales adaptativos, sin nivel absoluto.

## 2. El bloque SPI (538 B cada 10 ms, little-endian)
Cada bloque trae **20 tuplas**, o sea 20 × 500 µs = 10 ms → **100 bloques/s** (~54 kB/s).

| Offset | Tamaño | Campo | Valor |
|---|---|---|---|
| 0 | 1 | `sync0` | `0xAA` |
| 1 | 1 | `sync1` | `0x55` |
| 2 | 1 | `type` | `0x04` |
| 3 | 1 | `version` | `1` |
| 4 | 4 | `seq` | u32, **+1 por bloque generado** (también por los que no se alcanzan a enviar) |
| 8 | 4 | `t0_us` | u32 = `t[0].ts_us` |
| 12 | 2 | `n` | u16 = **20** (otro valor → la Pi descarta el bloque) |
| 14 | 2 | `flags` | bit0 = overrun del ADC, bit1 = overrun o desajuste del SAI; el resto en 0 |
| 16 | 20 × 26 | `t[20]` | tuplas (abajo) |
| 536 | 2 | `crc` | CRC-16/CCITT-FALSE de los bytes 0..535 |

**Tupla (26 B):**

| Offset en la tupla | Tamaño | Campo |
|---|---|---|
| 0 | 4 | `ts_us` u32: µs del instante de muestreo del ADC |
| 4 | 2 × 3 | `adc[3]` u16: CH1 (A1), CH2 (A4), CH3 (A5) |
| 10 | 2 × 8 | `voz[8]` i16 |

- **CRC-16/CCITT-FALSE:** polinomio 0x1021, valor inicial 0xFFFF, sin reflexión ni XOR final. Prueba: `"123456789"` → `0x29B1`. Está implementado en `avx_crc16()`.
- **Para sellar:** escribe las 20 tuplas y llama a `avx_block_seal(&blk, seq++, flags)`, que completa la cabecera y el CRC. Los `_Static_assert` del `.h` garantizan los 26 y 538 B.
- **`ts_us`:**
  - debe ser monotónico y avanzar **500 µs exactos** por tupla;
  - lo más simple es `ts_us = índice_de_muestra_ADC · 500`, sin depender de otro timer;
  - con u32 da la vuelta cada ~71 min, y la Pi lo tolera;
  - la Pi solo lo usa para mostrarlo: **alinea las señales por número de muestra, no por `ts_us`**.

## 3. Lo que la Pi asume (y por qué importa)
1. **No se pierden ni se duplican muestras dentro del flujo.**
   - La Pi concatena las tuplas tal cual llegan: EMG a 2 kHz y voz a 16 kHz.
   - Si se pierde un bloque, `seq` salta y la Pi cuenta el hueco ("Pérdidas" en la HMI), pero **no rellena**: las dos señales se desplazan juntas, sin desalinearse entre sí.
2. **La voz y el ADC de una tupla son del mismo intervalo de 500 µs.**
   - Esto es lo más delicado. La HMI mide el retardo sEMG → voz (τ\*, del orden de +50 ms).
   - Cualquier desfase fijo entre el ADC y la voz en el firmware **se suma directamente a τ\***. Por ejemplo, tomar la voz de una mitad de buffer DMA anterior agrega 10 ms de error.
   - Objetivo: desfase < 1 ms, y documentar cualquier latencia fija conocida, como la del filtro del micrófono (0,75 ms con la ADMP401, que `auravoxd` resta con `-voz-delay`).
3. **Tasas exactas.**
   - El ADC lo dispara un timer a 2 kHz y el SAI corre a 16 kHz con su propio PLL. Si los dos relojes no son exactamente 1:8, la cola de voz crece o se vacía con el tiempo.
   - En ese caso, el firmware **duplica o descarta una muestra de voz** para mantener 8 por tupla y **marca el bit1 de `flags`**.
   - Es mejor derivar los dos relojes de la misma fuente.
4. **Si el ADC pierde datos** (overrun del DMA o del buffer), marca el bit0 de `flags`. La Pi cuenta como "Desbordes" todo bloque con `flags ≠ 0`.

## 4. Protocolo físico SPI + DRDY
- **La Pi es maestro** SPI0, en modo **0** (CPOL = 0, CPHA = 0), con palabras de 8 bits, MSB primero, a **4 MHz**: 538 B tardan ≈ 1,1 ms.
- **El DK es esclavo** (SPI5) con DMA de TX y **NSS por software**: una lectura termina al completar los 538 B, nunca por CS. Con NSS por hardware, los flancos espurios de la línea CS deseleccionaban el SPI a mitad de byte y corrían los bits. El firmware lee CS como GPIO solo para decidir cuándo armar un bloque.
- Lo que la Pi envía por MOSI son ceros y se ignora.
- Cada lectura es **una sola transferencia de 538 B con CS bajo todo el tiempo**.

### Pines
| Señal | Raspberry Pi (pin físico) | DK (Arduino) |
|---|---|---|
| SCLK | GPIO11 (23) | D13 (PE15) |
| MISO (DK → Pi) | GPIO9 (21) | D12 (PH8) |
| MOSI (Pi → DK) | GPIO10 (19) | D11 (PG2) |
| CS | GPIO8 / CE0 (24) | D10 (PA3) |
| **DRDY** (DK → Pi) | **GPIO25 (22)** | **D4 (PH5)**, salida push-pull |
| GND | 25 (u otro GND) | GND |

- Los niveles lógicos son de 3,3 V en los dos lados.
- Verificado con la Raspberry Pi 5 (P5, 2026-10-13): 60 002 bloques en 10 min a 4 MHz, modo 0, con `crc=0` y `gaps=0`; con DRDY, `auravoxd` recibió 7192 bloques sin errores.

### Secuencia por bloque
```
DK: armar bloque N → seal → limpiar D-cache → armar DMA TX (538 B) → DRDY ↑
Pi: ve el flanco ↑ de DRDY → CS ↓ → 538 B → CS ↑
DK: callback de TX completo (o NSS ↑) → DRDY ↓ → queda libre para el bloque N+1
```
- **El DMA tiene que estar armado antes de subir DRDY:** en modo 0, el primer bit sale por MISO antes del primer flanco de SCK.
- **La Pi reacciona al flanco de subida de DRDY.** Por eso **DRDY tiene que bajar entre un bloque y otro**. Si la Pi no leyó el bloque N y ya está listo el N+1, haz lo siguiente, siempre que **NSS esté alto** (no hay transferencia en curso):
  1. aborta el DMA;
  2. re-ármalo con el bloque N+1;
  3. baja DRDY ≥ 10 µs y vuelve a subirlo.

  Si NSS está bajo, termina la transferencia en curso y descarta el bloque nuevo. En los dos casos `seq` sigue subiendo, así que la Pi ve el hueco.
- **Respaldo de la Pi:** si no ve un flanco en 100 ms, lee el nivel de DRDY y, si está alto, lee igual.
- **Si una transferencia queda incompleta** (NSS sube antes de los 538 B), aborta y re-arma desde el byte 0. Así el siguiente bloque empieza alineado con `AA 55`.
- **Modo sin DRDY,** para probar el enlace antes de cablear DRDY: `auravoxd -src spi -drdy -1`. La Pi lee cada 10 ms y descarta las lecturas con `seq` repetido.
- **Si el DK no tiene bloque**, MISO queda en 0x00 o 0xFF. La Pi lo ve como "sin sync" y lo ignora en silencio, sin contarlo como error.

## 5. Arquitectura sugerida del firmware
Es la arquitectura original con el INMP441 por SAI. La implementación real (`firmware/n6/`) usa LPTIM1 para el EMG y LPTIM2 + ADC2 para la ADMP401, los dos desde el mismo cristal.

```
TIMx (2 kHz, TRGO) ──► ADC (scan A1, A4, A5) ──► DMA circular  adc_buf[2][20][3]
                                                  └─ callbacks de mitad / completo cada 10 ms ─┐
SAI (I2S maestro RX, 16 kHz, slots de 32 bits) ──► DMA circular ──► FIFO de voz (int16)        │
                                                                                              ▼
                                         armar avx_block_t (20 tuplas = 20 ADC + 160 voz)
                                         → avx_block_seal(&blk[i], seq++, flags)
                                         → SCB_CleanDCache_by_Addr(blk[i], 544)
                                         → si el SPI está libre: HAL_SPI_Transmit_DMA(blk[i], 538) + DRDY ↑
SPI TX completo / NSS ↑ ──► DRDY ↓, buffer libre
```
- **Dos `avx_block_t`** (doble buffer): mientras uno se transmite, se arma el otro.
- **D-cache (Cortex-M55):**
  - buffers alineados a 32 B;
  - `SCB_CleanDCache_by_Addr` antes del DMA de TX;
  - `InvalidateDCache` sobre los buffers RX del ADC y del SAI antes de leerlos;
  - o bien poner los buffers en una región no cacheable (MPU).
- **N6 / RIF:** los canales DMA (GPDMA/HPDMA) y los periféricos tienen que tener los atributos de seguridad y privilegio correctos en CubeMX. Si no, el DMA no corre y no aparece ningún error.
- **Tomar las 160 muestras de voz en el mismo callback que las 20 del ADC,** con la cola de voz como búfer de compensación. Así el desfase ADC–voz queda acotado y fijo (sección 3).
- **Opcional, modo de prueba:** un define que genere tuplas sintéticas, por ejemplo una rampa en `adc[]` y una senoide en `voz[]`. Sirve para validar SPI, DRDY y CRC antes de conectar el AFE.

## 6. Qué muestra la HMI del enlace (para depurar)
Pestaña **Sesión → Enlace** (también en `journalctl -u auravoxd -f` en la Pi):

| Indicador | Esperado | Si no |
|---|---|---|
| Bloques por segundo | **100** | < 100: la Pi no ve DRDY o el DK no arma a tiempo |
| Pérdidas: CRC | 0 | Ruido en los cables, velocidad muy alta (prueba 1–2 MHz con `-spi-hz`), struct mal empaquetado o caché sin limpiar |
| Pérdidas: saltos de `seq` | 0 (≤ unos pocos en 10 min) | La Pi leyó tarde; revisa la lógica de re-armado de DRDY |
| Desbordes | 0 | `flags ≠ 0`: el DK perdió datos del ADC o desajustó la voz |
| "Sin señal" en la cabecera | No aparece | Más de 1 s sin bloques válidos |

**Criterio de aceptación (plan A5.3):** 10 minutos con 0 CRC y 0 saltos. Además, si desconectas y reconectas el DK, la Pi vuelve a recibir sola.

## 7. Comprobaciones rápidas
1. **CRC:** `avx_crc16("123456789", 9) == 0x29B1`.
2. **Tamaños:** `sizeof(avx_tuple_t) == 26` y `sizeof(avx_block_t) == 538` (lo aseguran los `_Static_assert`).
3. **Con un analizador lógico:**
   - DRDY sube cada 10 ms;
   - CS baja ~1,1 ms;
   - los primeros bytes de MISO son `AA 55 04 01`, seguidos de `seq` en little-endian.
4. **En reposo, con el AFE conectado:** `adc[]` ≈ 2041. Un aplauso se ve en `voz[]`.
5. **En la HMI, pestaña Señales:** los 3 canales y la voz se mueven. Al hablar, Causalidad muestra un τ\* positivo.
