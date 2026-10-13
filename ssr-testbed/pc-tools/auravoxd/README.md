# auravoxd

`auravoxd` es el servicio Go de la Raspberry Pi. Hace dos cosas a la vez:
- recibe por SPI las tuplas `{timestamp, ADC1, ADC2, ADC3, Voz}` del STM32N6570-DK y las ordena;
- sirve una HMI web que demuestra la causalidad sEMG → voz.

Es un solo binario estático, sin dependencias en la Pi. La HMI va embebida y funciona sin internet.

## Uso rápido
```bash
make test                          # vet + tests (incluye la prueba de punta a punta con datos simulados)
make build && ./auravoxd -src sim  # en la laptop: abrir http://localhost:8080
make deploy                        # compila para arm64, copia a aura@auravox.lan e instala el servicio (PI=aura@<IP> para otra red)
```
- Si la Pi usa Raspberry Pi OS de 32 bits (`uname -m` = `armv7l`): `make deploy ARCH=arm`.
- En la Pi:
  - ver el estado: `systemctl status auravoxd`;
  - ver el log en vivo: `journalctl -u auravoxd -f`;
  - abrir la HMI en `http://auravox.lan` desde la red AuraVox (ver abajo), o en `http://<IP de la Pi>` desde otra red.

| Flag | Default | Qué es |
|---|---|---|
| `-src` | `spi` | `spi`, `sim` (sEMG 60 ms antes que la voz) o `file -file sesion.avx` |
| `-spi-dev`, `-spi-hz` | `/dev/spidev0.0`, 4 MHz | SPI0 de la Pi, que es el maestro |
| `-gpiochip`, `-drdy` | `gpiochip0`, `25` | Línea DRDY del DK. `-drdy -1`: sin DRDY, lee cada 10 ms |
| `-vref-adc`, `-gdk`, `-vmid`, `-gain` | 1.8, 0.545, 1.65, 2500 | Conversión del código del ADC a µV RTI. **GDK es un supuesto: medirlo en el banco** |
| `-hop` | 10 | Hop de la CWT en ms (5/10/20). También se cambia desde la HMI |
| `-data` | `./data` | Carpeta de las sesiones (`.avx` crudo + `.json`) |
| `-addr` | `:8080` | Dirección de la HMI. El servicio de la Pi usa `:80` |

## Red de la demo: AuraVox

La Pi emite su propia red Wi-Fi, así la HMI tiene siempre la misma dirección y no depende del hotspot de un celular (que cambia de subred en cada encendido) ni de mDNS (`.local` no resuelve en Chrome de Android).

```bash
# Una vez, en la Pi (la clave no va al repo):
sudo nmcli device wifi hotspot ifname wlan0 con-name auravox-ap ssid AuraVox band bg channel 6 password "<clave>"
sudo nmcli connection modify auravox-ap connection.autoconnect yes connection.autoconnect-priority 20
```
- La Pi queda en `10.42.0.1` y reparte IPs (10.42.0.10–254) con el dnsmasq de NetworkManager.
- `install.sh` instala `deploy/auravox-dns.conf`, que le da el nombre `auravox.lan`. Si se instala con la red ya activa, aplicarlo con `sudo nmcli connection up auravox-ap`.
- HMI: `http://auravox.lan` (con `http://`, o Chrome lo toma como búsqueda). SSH: `ssh aura@auravox.lan`.
- En el celular: aceptar quedarse en una red sin internet; si la HMI no carga, apagar los datos móviles. Con un DNS privado fijo (p. ej. `dns.google`) el nombre no resuelve: dejarlo en automático.
- Volver a otra red Wi-Fi guardada: `sudo nmcli connection up <perfil>`; dejar de levantar AuraVox al arrancar: `connection.autoconnect no`.

## Conexión DK ↔ Pi (SPI0, 3,3 V en los dos lados)
| Señal | Pi (pin físico) | DK (Arduino) |
|---|---|---|
| SCLK | GPIO11 (23) | D13 |
| MISO (DK → Pi) | GPIO9 (21) | D12 |
| MOSI | GPIO10 (19) | D11 |
| CS | GPIO8 / CE0 (24) | D10 (NSS) |
| DRDY (DK → Pi) | GPIO25 (22) | D libre, a definir en CubeMX |
| GND | 25 | GND |

## Trama
- El formato está en `frame/frame.go` y en `firmware/Core/Inc/auravox_frame.h`; los dos son iguales.
- Es un bloque de 538 B cada 10 ms:
  - una cabecera con sync `AA 55`, `seq` y `t0_us`;
  - 20 tuplas de 26 B: `ts_us`, 3 ADC de 12 bits y 8 muestras de voz int16 a 16 kHz (`ts_us` es uint32: da la vuelta cada 71,6 min);
  - un CRC16-CCITT al final.
- El DK es esclavo SPI con DMA:
  - arma el bloque, lo sella con `avx_block_seal()` y sube DRDY;
  - la Pi lee los 538 B;
  - el DK baja DRDY.

  Conviene usar doble buffer, para armar el siguiente mientras se envía el actual.

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
   - sesiones grabadas: **Reproducir** o descargar.

## Reproducir una sesión grabada

Para la demo, una sesión grabada antes en buenas condiciones se puede mostrar en lugar de la señal en vivo, sin reiniciar el servicio.

- En **Sesión → Grabaciones**, **Reproducir** junto a un `.avx`. La cabecera muestra *Reproduciendo …* en todas las pestañas, y **Volver a en vivo** regresa al DK.
- La sesión corre a tiempo real (un bloque cada 10 ms) y en bucle, con el mismo análisis que en vivo.
- Las marcas de condición del `.json` se aplican en su bloque, así que la tabla por condición queda como en la grabación. Al volver a en vivo se restaura la condición que había.
- Mientras se reproduce no se puede grabar (`409`): una grabación de una grabación no sirve.
- Cada cambio de fuente reinicia los contadores del enlace y las estadísticas, para no mezclar lo vivo con lo grabado. La vuelta del bucle no cuenta como bloque perdido.
- El SPI y la línea DRDY siguen abiertos durante la reproducción (`source.Mux`): volver a en vivo es inmediato.
- API: `GET /api/source` → `{"mode":"live"}` o `{"mode":"file","file":"X.avx"}`; `POST /api/source` con `{"file":"X.avx"}` o `{"file":""}` (en vivo). Nombre inválido → `400`; inexistente → `404`.
- Las sesiones grabadas en otro equipo se copian (`.avx` y su `.json`) a la carpeta `-data` (en la Pi, `/home/aura/auravox`).

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
source/       spi.go (spidev + DRDY con go-gpiocdev), sim.go, file.go, mux.go (en vivo ↔ sesión)
stream/       buffers circulares alineados por número de muestra + envolventes
dsp/          filtros, banco Morlet, correlación cruzada, F0, umbrales
analysis/     CWT por hop, enunciados, cross-wavelet, estadísticas
record/       sesiones .avx (bloques crudos) + .json (condiciones, enunciados)
web/          servidor SSE + HMI embebida (static/)
deploy/       auravoxd.service, install.sh
```
