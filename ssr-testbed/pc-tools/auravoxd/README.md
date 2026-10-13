# auravoxd

`auravoxd` es el servicio Go de la Raspberry Pi. Hace dos cosas a la vez:
- recibe por SPI las tuplas `{timestamp, ADC1, ADC2, ADC3, Voz}` del STM32N6570-DK y las ordena;
- sirve una HMI web que demuestra la causalidad sEMG → voz.

Es un solo binario estático, sin dependencias en la Pi. La HMI va embebida y funciona sin internet.

## Uso rápido
```bash
make test                          # vet + tests (incluye la prueba de punta a punta con datos simulados)
make build && ./auravoxd -src sim  # en la laptop: abrir http://localhost:8080
make deploy                        # compila para arm64, copia a aura@192.168.0.103 e instala el servicio
```
- Si la Pi usa Raspberry Pi OS de 32 bits (`uname -m` = `armv7l`): `make deploy ARCH=arm`.
- En la Pi:
  - ver el estado: `systemctl status auravoxd`;
  - ver el log en vivo: `journalctl -u auravoxd -f`;
  - abrir la HMI en `http://192.168.0.103:8080`.

| Flag | Default | Qué es |
|---|---|---|
| `-src` | `spi` | `spi`, `sim` (sEMG 60 ms antes que la voz) o `file -file sesion.avx` |
| `-spi-dev`, `-spi-hz` | `/dev/spidev0.0`, 4 MHz | SPI0 de la Pi, que es el maestro |
| `-gpiochip`, `-drdy` | `gpiochip0`, `25` | Línea DRDY del DK. `-drdy -1`: sin DRDY, lee cada 10 ms |
| `-vref-adc`, `-gdk`, `-vmid`, `-gain` | 1.8, 0.5437, 1.65, 2500 | Conversión del código del ADC a µV RTI. GDK = divisor 560/1030 del DK (MB1939); en reposo el código es ≈ 2041 |
| `-voz-delay` | 0.75 | Retardo fijo de la voz en ms (FIR del firmware con la ADMP401; 1.078 con el INMP441). Se resta de τ\*, del adelanto del onset y del lag por frecuencia. Con `-src sim` vale 0 salvo que se indique |
| `-hop` | 10 | Hop de la CWT en ms (5/10/20). También se cambia desde la HMI |
| `-data` | `./data` | Carpeta de las sesiones (`.avx` crudo + `.json`) |

## Conexión DK ↔ Pi (SPI0, 3,3 V en los dos lados)
| Señal | Pi (pin físico) | DK (Arduino) |
|---|---|---|
| SCLK | GPIO11 (23) | D13 |
| MISO (DK → Pi) | GPIO9 (21) | D12 |
| MOSI | GPIO10 (19) | D11 |
| CS | GPIO8 / CE0 (24) | D10 |
| DRDY (DK → Pi) | GPIO25 (22) | D4 |
| GND | 25 | GND |

El AFE entra al DK por A1 (CH1), A4 (CH2) y A5 (CH3); el micrófono ADMP401 por A3. Detalle en `firmware/PROTOCOLO_SPI.md` y en el README del firmware (`firmware/n6/`).

## Trama
- El formato está en `frame/frame.go` y en `firmware/Core/Inc/auravox_frame.h`; los dos son iguales.
- Es un bloque de 538 B cada 10 ms:
  - una cabecera con sync `AA 55`, `seq` y `t0_us`;
  - 20 tuplas de 26 B: `ts_us`, 3 ADC de 12 bits y 8 muestras de voz int16 a 16 kHz;
  - un CRC16-CCITT al final.
- El DK es esclavo SPI con DMA:
  - arma el bloque, lo sella con `avx_block_seal()` y sube DRDY;
  - la Pi lee los 538 B;
  - el DK baja DRDY.
- Probado con la Raspberry Pi 5: 100 bloques/s sin errores de CRC ni huecos.

## Pestañas de la HMI
1. **Señales:** 3 gráficos horizontales (CH1 submentoniano, CH2 labio inferior, CH3 cuello) + voz.
   - Ventana de 5 s, en µV RTI.
   - Cada carril muestra el RMS y el 50 Hz del último segundo, y un punto que se enciende cuando el canal está activo.
   - Sirve para comparar silencio y piso de ruido contra habla.
2. **CWT:** escalogramas Morlet (ω0 = 6) de 20 a 500 Hz, en magnitud o fase, de los 3 sEMG y la voz, con una columna por hop.
   - El deslizador **retardo biológico** adelanta la voz en pantalla para alinearla con el sEMG.
   - Por defecto toma el τ\* medido.
3. **Causalidad**, por canal:
   - **r(τ)** de las envolventes en ±300 ms;
   - la **cross-wavelet sEMG × voz** (1,5–16 Hz, magnitud y fase);
   - el **lag por frecuencia** Δt = φ/(2πf).

   Debajo van la tabla resumen, los últimos enunciados y el control del confusor laríngeo.
4. **Sesión:**
   - condición actual (desconectado / reposo / habla / articulación silenciosa / vocal sostenida);
   - grabar y detener;
   - RMS y 50 Hz por condición, y SNR habla/reposo;
   - estado del enlace (CRC, bloques perdidos);
   - sesiones grabadas para descargar.

## Estadísticas y de dónde salen
- **τ\***: lag del máximo de la correlación cruzada entre la envolvente del sEMG y la de la voz.
  - La envolvente es |x| pasado por un pasa-bajos de 10 Hz, a 200 Hz. Es la misma para el sEMG y la voz, así que los retardos de grupo se cancelan.
  - Se busca en ±300 ms (Le et al. 2026 no encuentran estructura fuera de ese rango).
  - τ > 0 = el sEMG se adelanta. Se espera ~+50 ms (Jou et al. 2006: el mejor WER se obtiene retrasando el EMG 50 ms).
  - Por enunciado se reportan τ\*, r(τ\*) y r(0). El resumen da la mediana e IQR y el **% de enunciados con el sEMG adelantado**, que mide la estabilidad del signo (refactor §3.2).
- **Adelanto del onset:** onset de la voz − onset del sEMG.
  - Umbral = media + 3·DE de la línea base, con histéresis (Stepp et al. 2009).
- **Cross-wavelet:** Wxy = Wx·conj(Wy) sobre las envolventes.
  - Si el sEMG se adelanta Δ, la fase es 2πfΔ. La fase se desenrolla cerca de τ\*.
  - La coherencia se calcula solo con las columnas fuera del cono de influencia.
- **Por condición:** RMS en µV RTI y amplitud de 50 Hz (sirve para ver la efectividad del RLD con y sin él). SNR = 20·log10(RMS habla / RMS reposo).
- **Confusor laríngeo** (refactor §3.3):
  - se calcula la F0 de la voz y el pico de cada canal sEMG en F0 respecto de la mediana del espectro de 20–500 Hz;
  - si CH3 supera 10 dB durante una vocal sostenida, hay acople mecánico de la voz y no es actividad muscular.

## Estructura
```
main.go       goroutines: source → decoder → store; recorder; cwt; stats; web
frame/        formato del bloque, CRC16
source/       spi.go (spidev + DRDY con go-gpiocdev), sim.go, file.go
stream/       buffers circulares alineados por número de muestra + envolventes
dsp/          filtros, banco Morlet, correlación cruzada, F0, umbrales
analysis/     CWT por hop, enunciados, cross-wavelet, estadísticas
record/       sesiones .avx (bloques crudos) + .json (condiciones, enunciados)
web/          servidor SSE + HMI embebida (static/)
deploy/       auravoxd.service, install.sh
```
