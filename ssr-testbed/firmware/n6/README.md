# Firmware de captura del STM32N6570-DK (`ssi_capture`)

Captura los 3 canales sEMG del AFE a **2 kHz** y el micrófono a **16 kHz** con un solo reloj (por defecto la ADMP401 analógica de SparkFun; el INMP441 por I²S queda como opción de compilación), y los envía a la RPi5 por SPI según [`../PROTOCOLO_SPI.md`](../PROTOCOLO_SPI.md): bloques de 538 B cada 10 ms con DRDY. Corre como FSBL + ThreadX en la N6. Sin CWT ni inferencia en la placa.

Documentos: [spec v0.3](docs/2026-10-09-ssi-capture-spec.md), [plan 1](docs/2026-10-09-ssi-capture-plan-1.md) (captura), [plan 2](docs/2026-10-09-ssi-capture-plan-2.md) (enlace, watchdog y flash) y [plan 3](docs/2026-10-12-ssi-capture-plan-3-admp401.md) (micrófono analógico ADMP401).

## Conexiones en el DK

| Señal | DK (conector Arduino) | Pin N6 | Nota |
|---|---|---|---|
| EMG CH1 / CH2 / CH3 | **A1 / A4 / A5** | PA9 / PF3 / PB10 | 0–3,3 V. La placa divide por 560/1030 antes del ADC (1,8 V) |
| ADMP401: AUD | **A3** (CN7-4) | PA12 (ADC2, canal 13) | VCC a IOREF (CN8-2) y GND a CN8-7: cables propios, separados del AFE (3V3 en CN8-4, GND en CN8-6) |
| SPI hacia la Pi: CS / MOSI / MISO / SCK | D10 / D11 / D12 / D13 | PA3 / PG2 / PH8 / PE15 | GPIO8 / 10 / 9 / 11 de la Pi (pines 24 / 19 / 21 / 23) |
| DRDY | D4 | PH5 | GPIO25 de la Pi (pin 22) |
| GND | GND | — | Común con la Pi. La isla (persona + AFE + DK + Pi) no se conecta a la tierra de protección |

**Diferencia con PROTOCOLO_SPI.md:** el EMG va en A1/A4/A5, no en A1/A2/A3. Con el INMP441, A2 lleva el SCK del micrófono; con la ADMP401, A3 lleva el audio (A3 comparte el op-amp U7 con A2, no con ningún canal de EMG). El orden de `adc[]` sigue siendo CH1, CH2, CH3; solo cambian los pines.

**Opción INMP441** (`SSI_MIC_ANALOG=OFF`): SCK / WS / SD en A2 / D6 / D8 (PE12 / PE13 / PE7), L/R a GND, VDD a 3V3, y el **puente D6 → D2** (PE13 → PD0), sin el cual no hay EMG. Sin cables en A3.

## Lo que recibe la Pi

- Formato: exactamente PROTOCOLO_SPI.md v1 (`AA 55 04 01`, `n` = 20, CRC-16/CCITT-FALSE). Verificado en el DK con `tools/avx_block.py`, que replica el decodificador.
- `seq` = número de ventana de 10 ms desde el arranque. Una ventana perdida o descartada consume su `seq`, así que la Pi ve el salto. Un reinicio de captura deja un `seq` sin usar.
- `ts_us` = 10 000 · `seq` + 500 · *i* (índice de muestra, no reloj).
- `flags`: bit0 = datos del ADC perdidos (overrun, ventana sobrescrita o reinicio); bit1 = error del SAI. La contrapresión del SPI no se marca: se ve como salto de `seq`.
- `adc[]`: códigos crudos de 12 bits. GDK (pin → ADC) = 560/1030 = **0,5437**. Con el AFE en reposo (1,65 V), el código es ≈ 2041.
- `voz[k]`: audio en la escala de 24 bits `>> 8`. Con la ADMP401, el fondo de escala del ADC (0–3,3 V en A3) equivale a ±32768 y la continua se elimina en el firmware. Con el INMP441, los primeros ~256 ms son ceros y el primer segundo trae un transitorio de arranque.
- Alineamiento: EMG y audio salen del mismo cristal (*c* = 0 nominal; se confirma con la prueba de pulsos P4). Con la ADMP401, LPTIM1 (EMG) y LPTIM2 (micrófono a 64 kHz) arrancan juntos y la muestra EMG *i* se toma junto con la muestra de audio 8*i*. Con el INMP441, a mitad de la trama 8*i*.
- Latencias fijas que la Pi debe compensar: filtro de decimación del firmware **750 µs** con la ADMP401 (12 muestras de audio; el INMP441 trae el suyo de 1078 µs), aire 2,9 ms/m y la cadena del AFE (recalcular en LTspice).
- DRDY: un flanco de subida por bloque. Si la Pi no leyó y llega otro bloque, se re-arma con el nuevo (nuevo flanco). Si la Pi está leyendo (CS bajo), la transferencia termina y el bloque nuevo se descarta. Si CS sube antes de 538 B, se re-arma desde el byte 0.

## Compilar, cargar y probar

Requisitos: toolchain de STM32 en el `PATH` (Matías: `source ~/2026-2/SSI/tools/stm32-env.sh`), CubeMX 6.18.1 con el paquete STM32Cube_FW_N6 V1.4.1. `ssi_capture/Drivers` y `ssi_capture/Middlewares` no están en git: se regeneran con `cd ~/STM32CubeMX && ./STM32CubeMX -q <ruta>/scripts/mx_generate_ssi_capture.txt` (ajustar la ruta del `.ioc` dentro del script).

```bash
tools/fw.sh build                                     # ADMP401 en A3 (por defecto): LPTIM1 + LPTIM2 desde el cristal
SSI_MIC_ANALOG=OFF tools/fw.sh build                  # INMP441 por SAI2, sincronía por el puente D6 -> D2
SSI_MIC_ANALOG=OFF SSI_SYNC_LPTIM=ON tools/fw.sh build  # INMP441 en banco: sin puente, EMG por LPTIM1
tools/fw.sh ram                         # cargar en RAM (modo desarrollo: BOOT1 = H)
tools/run_test.sh 65 --skip 2 --check 'STAT:lost==0 and drop==0 and err==0'   # VCP /dev/ttyACM0, 115200
cmake -S ssi_capture/tests/host -B ssi_capture/tests/host/build -G Ninja && cmake --build ssi_capture/tests/host/build && ctest --test-dir ssi_capture/tests/host/build
tools/flash.sh                          # firma y graba la flash externa; arranque: BOOT0 = BOOT1 = L, reset
```

Herramientas por SWD (no detienen la MCU):
- `tools/swd.py` con `sym`, `cmd N`, `sample`, `read32` y `dma-suspend`;
- `tools/diag.py` con `audio`, `emg`, `noise` y `pulse` (con la ADMP401: `pulse --analog`, pulso de D7 a A1 y A3 con AUD desconectado; se espera *c* = 12 = sincronía 0 + filtro 12);
- `tools/inject_test.sh 'acción'`;
- `tools/avx_block.py check bloque.bin --ts-check`;
- `tools/mic_tone_check.sh`: el PC reproduce 5 tonos (250 Hz a 4 kHz) y verifica que el micrófono los capte, con el micrófono del PC como referencia (micrófono libre, a ~20 cm de los parlantes);
- `tools/gen_audio_fir.py`: coeficientes del filtro de decimación de la ADMP401 y su respuesta.

En la Raspberry, para probar el enlace sin `auravoxd` (P5): copiar `tools/rpi_spi_check.py` y `tools/avx_block.py` y correr `python3 rpi_spi_check.py --secs 600` (requiere `python3-spidev`; lee por polling, sin DRDY). Aceptación: ~100 bloques/s, `crc=0` y `gaps=0`.

### Mensajes del VCP

| Línea | Contenido |
|---|---|
| `SSI capture fw …`, `CLK`, `NC`, `RST rsr= iwdg=` | Arranque: versión, reloj, región no cacheable y causa del reset |
| `INIT cap= step= sync= mic= hse= mic_ck= adc_ck=` | Inicialización de la captura (`sync` 0 = puente, 1 = LPTIM; `mic` 0 = INMP441, 1 = ADMP401; `mic_ck` = reloj del SAI o del ADC) |
| `INIT link=` | Enlace SPI |
| `WDG on=1` | Watchdog activo (~1 s) |
| `STAT t ms ep win emgblk audblk lost drop err arm sent repl ldrop abrt lerr` | Cada segundo. `arm`: bloques ofrecidos; `sent`: leídos completos por la Pi; `repl`: reemplazados sin leer |
| `SIG t peak rms rslot e0lo e0hi …` | Audio (pico, RMS, ranura derecha) y mínimo/máximo por canal EMG |
| `IDLE ms=` | Sin datos (por ejemplo, falta el puente). LED verde fijo |

Comandos de depuración por SWD (`tools/swd.py cmd N`):
- 1: reiniciar la captura;
- 2: captura de 1 s para `diag.py`;
- 3 y 4: encender y apagar los pulsos de prueba en D7;
- 5 y 6: desconectar y reconectar el pin SCK;
- 7: detener `acq` 30 ms;
- 8: colgar `acq` (el watchdog reinicia);
- 9: pulso de CS sin cables.

## Estado (2026-10-09)

Verificado en el DK, sin micrófono ni cables:
- relojes exactos (SAI 49,152 MHz y FS 16 kHz);
- ADC + DMA a 2 kHz (build de banco);
- 6400 bloques en 65 s sin pérdidas ni errores de CRC;
- formato del bloque;
- reinicio y recuperación ante fallas de DMA;
- enlace SPI sin maestro (re-armado, NSS);
- watchdog;
- flash grabada y verificada;
- arranque autónomo desde la flash (BOOT0 = BOOT1 = L, 2026-10-10).

Micrófono (2026-10-10): el primer INMP441 resultó **defectuoso**. Entrega tramas I²S correctas, pero no capta sonido: `tools/mic_tone_check.sh` da FAIL, con la referencia del PC captando los tonos a +18/+63 dB, y lo mismo pasa a 48 kHz. El firmware, el cableado y la alimentación (3,27 V) quedaron verificados. Detalle en `~/2026-2/SSI/notas/2026-10-10-microfono-inmp441.md` (fuera del repo).

Micrófono ADMP401 (2026-10-12, plan 3): firmware listo y probado en el PC (filtro de decimación y P4 analógica simulada); compila sin avisos en las tres variantes. Falta la prueba en la placa.

Pendiente:
- con la ADMP401 en A3: flujo (`STAT`), P3 con `tools/mic_tone_check.sh` y P4 con `diag.py pulse --analog`;
- con el INMP441 (si se usa uno nuevo): P3, P4 con el puente y ruido del SCK (P7);
- con la RPi5: transferencias reales (P5).
