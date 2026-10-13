# Especificación resumida — Firmware de captura SSI (STM32N6570-DK)

Versión 0.3 · 9 oct 2026 · Matías Pérez (diseño con Claude) · Estado: **v0.2 aprobada por Matías; v0.3 adopta el protocolo SPI de Vicente**

- Cambios en v0.2: pines corregidos tras leer el UM3300 Rev 1 y el esquemático MB1939-N6570-C02. IOREF = 3,3 V. El audio pasa de I²S2 a SAI2 bloque B, porque I²S2_CK no es accesible. Los canales de EMG pasan de A1–A3 a A1/A4/A5.
- Cambios en v0.3 (2026-10-09): el enlace adopta **`ssr-testbed/firmware/PROTOCOLO_SPI.md`** (Vicente), que es lo que implementa el servicio `auravoxd` de la RPi5. Esto reemplaza la §6 anterior (paquetes de 1024 B con CRC-32, INFO, STATUS y comandos). En consecuencia:
  - el EMG baja a **2 kHz** (FS/8);
  - la voz viaja en **int16** (24 bits >> 8);
  - el CRC es CRC-16/CCITT-FALSE;
  - no hay comandos: el DK transmite desde que arranca.
  - Se mantiene el reloj único (EMG bloqueado a la FS del audio), que es lo que el propio protocolo recomienda (§3.3). El SAI sigue capturando las dos ranuras I²S, para diagnosticar el pin L/R.

## 1. Objetivo y alcance

La N6 **solo adquiere y transmite**:

- 3 canales sEMG del AFE + audio del micrófono INMP441;
- streaming por SPI a la **RPi5** (servicio `auravoxd` de Vicente), que guarda el dataset, calcula el lag y sirve la HMI web.

**Fuera de alcance:** CWT, inferencia y síntesis en la N6 `[DECISIÓN Matías 2026-10-08]`; software de la RPi5.

## 2. Requisitos y criterios de aceptación

| # | Requisito | Criterio |
|---|---|---|
| R1 | EMG de 3 canales a **2 kHz**, 12 bits | 100 bloques/s de 20 muestras; período = 8 tramas de audio exactas |
| R2 | Audio a **16 kHz** (24 bits capturados, int16 en el enlace) | Muestras I²S íntegras y con signo correcto |
| R3 | EMG y audio en un **solo dominio de reloj** | La muestra EMG *i* se toma en la trama de audio 8*i* + *c*, con *c* constante en todas las sesiones |
| R4 | Alineamiento EMG ↔ audio | Incertidumbre < 1 ms tras compensar latencias fijas (sección 4) |
| R5 | Streaming continuo a la RPi5 | 10 min con 0 errores de CRC y 0 saltos de `seq`; si el DK se reconecta, la Pi vuelve a recibir sola (PROTOCOLO §6) |
| R6 | Arranque autónomo | Corre desde la flash externa (BOOT0 = BOOT1 = L) sin debugger |
| R7 | Arquitectura | Modular y sobre ThreadX (regla del proyecto) |

## 3. Hardware y pines

| Función | Pin N6 | DK | Notas |
|---|---|---|---|
| EMG CH1 / CH2 / CH3 | PA9 / PF3 / PB10 = ADC1_INP10 / INP16 / INP8 | A1 / A4 / A5 | Divisor 470k/560k + buffer TSZ122 en la placa: 0–3,31 V en el conector → 0–1,8 V en el ADC |
| SAI2_SCK_B → SCK del micrófono | PE12 | A2 | Llega al conector por SB21 (0 Ω). PA10 queda sin usar |
| SAI2_FS_B → WS del micrófono | PE13 | D6 | Libre en la placa |
| SAI2_SD_B ← SD del micrófono | PE7 | D8 | Pull-down de 100 kΩ (datasheet) o el interno |
| TIM1_ETR (sincronización) | PD0 | D2 | **Puente D6 → D2** |
| SPI5 NSS / MOSI / MISO / SCK | PA3 / PG2 / PH8 / PE15 | D10 / D11 / D12 / D13 | → RPi5 GPIO8 / 10 / 9 / 11 (pines 24 / 19 / 21 / 23) |
| DRDY (salida) | PH5 | D4 | → RPi5 GPIO25 (pin 22). Libre en la placa |
| 3,3 V del micrófono | — | CN8 +3V3 | Mismo riel que IOREF (VDD3V3) |
| GND común | — | GND | → GND de la RPi5 |

- **IOREF = 3,3 V** `[UM3300 tabla 16; MB1939 hoja 9: IOREF = VDD3V3]`. Las E/S digitales del conector son de 3,3 V (VDD de la N6 = 3,3 V). El SPI va directo a la RPi5, sin traductores de nivel. El INMP441 se alimenta con 3,3 V (VIH = 2,31 V).
- **Entradas A0–A5 son solo de entrada:** cada pin ADC es la salida de un buffer TSZ122 alimentado a 1,8 V, así que no puede sacar señales al conector. Por eso I²S2 no sirve: sus únicos CK (PA9, PA12, PB10) son salidas de buffer. El juego SAI2 B es el único completo y accesible en el conector Arduino (alternativa descartada: I2S3, que usa A0, A1 y el STMod+).
- **Diferencia con PROTOCOLO_SPI.md:** ese documento asume los canales en A1, A2 y A3. En el DK no puede ser así: A2 lleva el SCK del micrófono y comparte el doble op-amp U7 con A3. El orden CH1, CH2, CH3 de `adc[]` se mantiene; solo cambian los pines: **A1, A4 y A5**.
- **Ganancia del pin al ADC (GDK)** = 560/1030 = **0,5437** `[MB1939 hoja 9]`; `auravoxd` usa 0,545 por defecto.
- **Gemelos digitales:** cada red del conector A*x* está unida por un 0 Ω a un GPIO de 3,3 V. PC10 (A1), PC12 (A4) y PH2 (A5) deben quedar en modo analógico (estado de reset).
- PA5 (A0) solo llega al ADC2 y además pasa por SB49.
- **STMod+ vacío:** comparte SPI5 y USART2 con el conector Arduino. D13 también maneja el LED LD6 (inofensivo).
- INMP441: L/R a GND (canal izquierdo).
- El AFE debe entregar 0–3,3 V en A1/A4/A5 (alimentado desde CN8 +3V3).

## 4. Sincronización (un solo reloj)

```
SAI2-B (maestro) ── FS 16 kHz (D6) ──┬──> INMP441 (muestrea en cada trama)
                                     └──> puente D6→D2 ──> TIM1_ETR: cuenta 8 ──> TRGO ──> ADC1 (escaneo de 3 canales)
```

- El TIM1 cuenta flancos de subida de la FS (a mitad de cada trama I²S) con ARR = 7. Al arrancar, su contador se precarga en 7, de modo que el primer TRGO cae en el primer flanco. La muestra EMG *i* se toma entonces a mitad de la trama 8*i*: *c* = 0 nominal. Se verifica en la prueba P4.
- La tupla *i* del protocolo lleva la muestra EMG *i* y las tramas de audio 8*i* … 8*i* + 7, con `ts_us` = 500 · *i* (índice global de muestra EMG). Cada muestra se identifica por su **índice**, nunca por el instante de un callback.
- La RPi5 compensa estas latencias fijas (se documentan en el README del firmware, porque el protocolo no tiene paquete INFO):

| Elemento | Retardo |
|---|---|
| Filtro interno del INMP441 | 1078 µs (17,2/fs, datasheet) |
| Sonido boca → micrófono | 2,9 ms/m (distancia fija; 10 cm → 0,29 ms) |
| Cadena analógica del AFE | Recalcular con LTspice (diseño anterior ≈ 0,6 ms) |
| Muestra EMG dentro de la tupla | +31 µs respecto de `voz[0]` (a mitad de trama), si *c* = 0 |
| Divisor + buffer TSZ122 de la placa | µs (despreciable) |
| Disparo y conversión del ADC | µs (despreciable) |

## 5. Arquitectura del firmware

Proyecto único **FSBL + ThreadX (API nativa)** generado con CubeMX (CMake/GCC) en `ssr-testbed/firmware/n6/ssi_capture/`. Patrón soportado por ST (ejemplo `Tx_Thread_Creation` de la N657).

| Módulo | Responsabilidad |
|---|---|
| `sync` | TIM1 en modo reloj externo por ETR, ARR = 7, TRGO al ADC |
| `emg_adc` | ADC1, 3 canales en escaneo (INP10, INP16, INP8), muestreo de 246,5 ciclos (la fuente es un op-amp de poco ancho de banda), GPDMA circular, medios bloques de 20 muestras |
| `mic_sai` | SAI2 bloque B maestro RX, I²S estándar, 24 bits en ranuras de 32; se capturan las dos ranuras y se usa la 0 (la 1 debe llegar en cero: diagnóstico del pin L/R); DMA circular de 160 tramas por medio bloque |
| `capture` | Orden de arranque y parada que fija *c* |
| `avx_block` | Formato del bloque de PROTOCOLO_SPI.md: tuplas, CRC-16, sellado |
| `acq` | Hilo que empareja ventanas de 10 ms y arma los bloques |
| `link_logic` | Máquina de estados del enlace (PROTOCOLO §4), lógica pura probada en el PC |
| `link` | SPI5 esclavo solo TX + DMA, NSS por hardware con flanco por EXTI3, DRDY en PH5 |
| `app` | Objetos de ThreadX e hilos; causa del reset al arrancar |
| `mon` | Estadísticas por el VCP, LED, watchdog (IWDG ~1 s, refrescado solo si `acq` y `link` siguen vivos) y comandos de depuración por SWD |
| `diag`, `testpulse` | Depuración: captura de 1 s por SWD; pulsos en D7 para P4 |

| Hilo | Prioridad | Función |
|---|---|---|
| `acq` | Alta | Espera *event flags* de los DMA, decodifica el audio y arma el bloque de cada ventana de 10 ms (EMG del bloque *n* + audio del bloque *n*) |
| `link` | Media (5) | Toma bloques de la cola, arma el DMA del SPI y maneja DRDY |
| `testpulse` | Baja (9) | Solo en la prueba P4 |
| `mon` | Baja (10) | Estadísticas, LED, watchdog y depuración |

- **ISR mínimas:** solo contadores y `tx_event_flags_set`. Sin lógica dentro de los callbacks de la HAL.
- **Memoria:** buffers DMA y bloques en una región **no cacheable** (MPU), alineados a 32 B. *Block pool* de 16 bloques.
- **LED:** verde parpadeando = capturando; verde fijo = sin datos (IDLE); rojo = error.

## 6. Protocolo SPI

**Contrato:** `ssr-testbed/firmware/PROTOCOLO_SPI.md` (Vicente). Resumen:

- Bloque de **538 B cada 10 ms**, little-endian: `AA 55`, `type = 0x04`, `version = 1`, `seq` u32, `t0_us` u32, `n` u16 = 20, `flags` u16, 20 tuplas de 26 B (`ts_us` u32, `adc[3]` u16, `voz[8]` i16) y `crc` u16 = CRC-16/CCITT-FALSE de los bytes 0..535.
- SPI modo 0, 8 bits, MSB primero, 4 MHz; la Pi es maestra y lee 538 B con CS bajo. DRDY sube con el bloque listo y el DMA ya armado. Las reglas de re-armado y de transferencia incompleta están en PROTOCOLO §4. Sin bloque, MISO queda en 0x00 o 0xFF.

Decisiones del firmware dentro del contrato:

- `seq` = número global de ventana de 10 ms desde el arranque. Una ventana perdida antes de armarse también consume su `seq`, así que la Pi ve el hueco.
- `ts_us` = 500 · índice global de muestra EMG = `seq` · 10 000 + 500 · *i* (u32, da la vuelta cada ~71 min).
- `flags`: bit0 = se perdieron datos del ADC (overrun o ventana sobrescrita antes de armarse); bit1 = error del SAI. Nada más: la Pi cuenta como desborde todo bloque con `flags ≠ 0`.
- `voz[k]` = muestra de 24 bits con signo `>> 8` (desplazamiento aritmético).
- `adc[]` = códigos de 12 bits de CH1, CH2 y CH3 = A1, A4 y A5.
- Los primeros ~256 ms de audio son ceros (arranque del INMP441). No se marcan.

**Carga del enlace:** 53,8 kB/s, ~11 % de un enlace a 4 MHz.

## 7. Manejo de errores

- **Error de DMA, ADC o SAI:** marcar bit0 o bit1 en el siguiente bloque y reiniciar la captura (están acopladas por la FS). `seq` sigue subiendo.
- **Backpressure del SPI:** descartar y contar. Nunca se bloquea la adquisición. `seq` sigue subiendo, y la Pi ve los saltos.
- **Electrodo suelto o saturación:** no se marca; la Pi ve los códigos.
- **Watchdog:** si `acq` o `link` dejan de reportar, el sistema se reinicia.

## 8. Pruebas

| # | Prueba | Aceptación |
|---|---|---|
| P1 | Compilar, cargar en RAM y arrancar desde flash | LED según el estado |
| P2 | ADC con señal en A1/A4/A5 (0–3,3 V) | 2 kHz por índices; con el AFE en reposo, código ≈ 1,65 · 0,5437 / 1,8 · 4095 ≈ 2041 |
| P3 | Micrófono con tono o silbido; SCK en A2 y FS en D6 con el osciloscopio | Espectro correcto |
| P4 | Sincronización | *c* constante en 10 reinicios, con un pulso común por A1 y SD |
| P5 | Enlace con la RPi5 | 10 min: 0 errores de CRC y 0 saltos de `seq`; reconexión sola |
| P6 | Calibración con un mismo pulso por ambas vías | Desfase residual medido y < 1 ms tras compensar |
| P7 | Interferencia del SCK (entra al buffer U7A y al riel de 1,8 V, que también es VREF+): EMG con entradas a un nivel fijo, con y sin el pin SCK activo | Diferencia de ruido < 1 LSB rms |

## 9. Pendientes y riesgos

1. **Avisar a Vicente:** canales en A1/A4/A5 (no A1/A2/A3) en su cableado y en PROTOCOLO_SPI.md; GDK medido = 0,5437. Su header `auravox_frame.h` y su decodificador Go aún no están en el repo: cuando lleguen, cruzar con las pruebas del firmware.
2. Recalcular la latencia del AFE actual con LTspice.
3. Interferencia del SCK de audio en el ADC (P7). Al ser síncrona con el muestreo, debería verse como un offset fijo y no como ruido.
4. El AFE debe quedar alimentado a 3,3 V y con salida dentro de 0–3,3 V.
5. El puente D6 → D2 es obligatorio: sin él no hay EMG.
