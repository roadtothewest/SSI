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
| `-vref-adc`, `-gdk`, `-vmid`, `-gain` | 1.8, 0.5437, 1.65, 2500 | Conversión del código del ADC a µV RTI. GDK = divisor 560/1030 del DK (MB1939); en reposo el código es ≈ 2041 |
| `-voz-delay` | 0.75 | Retardo fijo de la voz en ms (FIR del firmware con la ADMP401; 1.078 con el INMP441). Se resta de τ\*, del adelanto del onset y del lag por frecuencia. Con `-src sim` vale 0 salvo que se indique |
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
| CS | GPIO8 / CE0 (24) | D10 |
| DRDY (DK → Pi) | GPIO25 (22) | D4 |
| GND | 25 | GND |

El AFE entra al DK por A1 (CH1), A4 (CH2) y A5 (CH3); el micrófono ADMP401 por A3. Detalle en `firmware/PROTOCOLO_SPI.md` y en el README del firmware (`firmware/n6/`).

## Trama
- El formato está en `frame/frame.go` y en `firmware/auravox_frame.h`; los dos son iguales.
- Es un bloque de 538 B cada 10 ms:
  - una cabecera con sync `AA 55`, `seq` y `t0_us`;
  - 20 tuplas de 26 B: `ts_us`, 3 ADC de 12 bits y 8 muestras de voz int16 a 16 kHz (`ts_us` es uint32: da la vuelta cada 71,6 min);
  - un CRC16-CCITT al final.
- El DK es esclavo SPI con DMA:
  - arma el bloque, lo sella con `avx_block_seal()` y sube DRDY;
  - la Pi lee los 538 B;
  - el DK baja DRDY.
- Probado con la Raspberry Pi 5: 100 bloques/s sin errores de CRC ni huecos.

## Pestañas de la HMI
1. **Señales:** un gráfico por canal activo (nombre según **Sesión → Canales**) + voz.
   - Ventana de 5 s, en µV RTI (con ganancia 1, µV en el pin).
   - Cada carril muestra el RMS y el 50 Hz del último segundo, y un punto que se enciende cuando el canal está activo.
   - Sirve para comparar silencio y piso de ruido contra habla.
2. **CWT:** escalogramas Morlet (ω0 = 6) de 20 a 500 Hz, en magnitud o fase, de los 3 sEMG y la voz, con una columna por hop.
   - El deslizador **retardo biológico** adelanta la voz en pantalla para alinearla con el sEMG.
   - Por defecto toma el τ\* medido.
3. **Causalidad**, solo con los canales activos:
   - el número grande es el τ\* del **canal principal**: el activo con más frases sobre el azar (empate: mayor r); sin frases, el de mayor r en vivo;
   - una ficha por canal con τ\*, r y cuántas frases superan el azar;
   - **r(τ)** de las envolventes en ±300 ms (últimos 3 s), con la **banda de azar** en gris;
   - las últimas frases: τ\* y r por canal, atenuados si no superan el azar, y el control del confusor laríngeo.
4. **Sesión:**
   - condición actual (desconectado / reposo / habla / articulación silenciosa / vocal sostenida);
   - **canales**: nombre, ganancia y si está conectado (ver abajo);
   - grabar y detener;
   - RMS y 50 Hz por condición, y SNR habla/reposo;
   - estado del enlace (CRC, bloques perdidos);
   - sesiones grabadas: **Reproducir**, **Renombrar**, descargar (`.avx` y `.json`) o **Borrar**.

## Canales

Lo conectado a A1/A4/A5 cambia según el montaje (AFE propio, MyoWare), así que cada canal tiene nombre, ganancia y un interruptor **conectado**, editables en **Sesión → Canales** sin reiniciar el servicio.

- Ganancia = del electrodo al pin Arduino: AFE AuraVox 2500, MyoWare 2.0 RAW 200. Con **1**, los valores son µV en el pin (MyoWare 1.0 RAW: su ganancia no está documentada).
- Un canal desconectado no aparece en Señales, Espectro, Causalidad ni en la tabla por condición, y no entra en el número grande.
- Se guarda en `canales.cfg` dentro de `-data`; sin ese archivo: los nombres del AFE, `-gain` y los tres activos.
- La ganancia nueva vale desde el bloque siguiente. Cada grabación guarda en su `.json` los canales con que se grabó (`chans`).
- API: `GET /api/channels`; `POST /api/channels` con `[{"name","gain","on"} ×3]`. Nombre vacío o de más de 32 caracteres, o ganancia fuera de (0, 10⁶] → `400`.

## Clasificador (modelo de Colab)

`auravoxd` corre el clasificador que exporta el cuaderno de Colab (`auravox_vocales_npu.ipynb`) y muestra la clase y sus probabilidades arriba de **Señales**. Funciona en vivo y también al reproducir una sesión. El botón **Ocultar modelo / Mostrar modelo** de esa pestaña esconde el panel; cada navegador recuerda su elección.

- **Cambiar de modelo:** en **Sesión → Modelo → Subir modelo (.zip)**, el mismo `.zip` que sale del cuaderno. `auravoxd` lo descomprime, comprueba que carga y que evalúa una ventana, y recién entonces lo activa. El anterior queda en `<data>/ml/anterior/`. Por API: `curl --data-binary @modelo.zip http://auravox.lan/api/ml/model`.
- **Contrato con el cuaderno:** el `.zip` trae
  - un `.onnx` con entradas float `cwt_mag [1,nch,T,NF]` y `cwt_fase [1,2·nch,T,NF]`, y logits por clase en la salida. Si hay dos, se usa el `int8`, que es el que iría a la NPU de la N6;
  - la cabecera C (`auravox_vocales.h`) con las `AVX_VOC_*`, `avx_voc_canal`, `avx_voc_mu`, `avx_voc_inv_sd` y `avx_voc_clases`. Es la misma que usaría el firmware, así que la Pi y la N6 preprocesan igual;
  - `informe.json` (opcional): fecha, entradas y validación cruzada, que se muestran en la HMI.
- **Preproceso** (`ml/features.go`): CWT con `dsp.Bank` (la misma del entrenamiento), dB acotado a [`DB_MIN`, `DB_MAX`], z-score por frecuencia acotado a ±`Z_CLIP`, y cos/sin de la fase absoluta. Usa los códigos crudos del ADC con la conversión del modelo (`VREF_ADC`, `GDK`, `VMID`, `GAIN`), no la ganancia de **Canales**. Aún no calcula la fase relativa.
- **Evaluación:** cada 100 ms sobre la última ventana (T·HOP = 320 ms, que llega con ~144 ms de atraso por el semiancho del núcleo de 20 Hz), con las probabilidades promediadas sobre las 3 últimas. El `.onnx` lo evalúa `ml/runner.py`, un proceso Python con onnxruntime que no sabe nada del preproceso: un modelo nuevo de la misma familia no requiere cambiar código.
- **Python en la Pi, sin `pip` ni `sudo`:** `make deploy-ml-lib` descarga en el PC las ruedas de onnxruntime y numpy para Python 3.13/aarch64 (`deploy/ml-lib.sh`) y las copia a `<data>/ml/lib`, que el evaluador pone en `PYTHONPATH`. Hay que hacerlo una vez, desde la red AuraVox.
- **Flags:** `-ml=false` lo apaga; `-ml-python` elige el intérprete (por defecto `python3`).
- **API:** `GET /api/ml` → `{state, model, clases, canal, winMs, accBal, ort, pred:{clase, probs, ms, stale}}`, con `state` = `sin-modelo`, `cargando`, `activo` o `error` (y `err`).
- **Prueba con las grabaciones del entrenamiento:** `AURAVOX_ML_PY=<python con onnxruntime> AURAVOX_ML_MODEL=<carpeta del .zip> AURAVOX_ML_AVX=<carpeta de .avx> go test ./ml -run Recordings -v`. Con el modelo del 2026-10-15 da 66 % de las ventanas con la clase del archivo (silencios 100 %), igual con int8 que con fp32.

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

## Renombrar y borrar grabaciones

- En **Sesión → Grabaciones**, cada sesión (su `.avx` y su `.json`) aparece una vez, con su duración. **Renombrar** y **Borrar** actúan sobre los dos archivos juntos.
- Nombres: letras, números, `-` y `_`, hasta 64 caracteres; los espacios pasan a `_`. Sin puntos ni barras, así que un nombre no puede salir de la carpeta.
- Renombrar nunca pisa otra sesión (`409`). Borrar pide confirmación y no se puede deshacer.
- La sesión que se está grabando o reproduciendo no se puede renombrar ni borrar (`409`): primero **Detener** o **Volver a en vivo**.
- API: `GET /api/files` → `[{"name","size","secs","meta"}]`; `POST /api/files/{nombre}/rename` con `{"to":"nuevo"}` → `{"name":"nuevo"}`; `DELETE /api/files/{nombre}`. Nombre inválido → `400`; inexistente → `404`.

## Estadísticas y de dónde salen
- **τ\***: lag del máximo de la correlación cruzada entre la envolvente del sEMG y la de la voz.
  - La envolvente es |x| pasado por un pasa-bajos de 10 Hz, a 200 Hz. Es la misma para el sEMG y la voz, así que los retardos de grupo se cancelan.
  - Se busca en ±300 ms (Le et al. 2026 no encuentran estructura fuera de ese rango).
  - τ > 0 = el sEMG se adelanta. Se espera ~+50 ms (Jou et al. 2006: el mejor WER se obtiene retrasando el EMG 50 ms).
  - Por enunciado se reportan τ\*, r(τ\*) y r(0). El resumen da la mediana e IQR y el **% de enunciados con el sEMG adelantado**, que mide la estabilidad del signo (refactor §3.2).
- **Nivel de azar:** dos envolventes sin relación también dan un máximo de r(τ). Su p95 (`dsp.ChanceR`) es ≈ 9,6/√n con n muestras de envolvente: 0,39 en la ventana en vivo de 3 s y ≈ 0,55 en una frase típica (duración + 0,8 s). Sale de simular ruido contra voz en ráfagas con la misma cadena, y `dsp_test.go` lo comprueba.
  - Un τ\* es **significativo** si r(τ\*) supera ese nivel y el pico no está a ≤ 25 ms del borde de ±300 ms (ahí el máximo verdadero puede estar fuera). El τ\* en vivo solo se informa si es significativo, y el resumen por canal usa solo las frases significativas.
  - Con el montaje del 2026-10-15 (MyoWare 1.0 en el omohioideo), en las sesiones de vocales espaciadas 12 de 18 frases del CH3 superan el azar (11 con τ\* > 0, mediana ≈ +170 ms); el masetero y la entrada al aire, ninguna.
- **Adelanto del onset:** onset de la voz − onset del sEMG.
  - Umbral = media + 3·DE de la línea base, con histéresis (Stepp et al. 2009).
  - Se guarda en el `.json` de cada sesión, pero la HMI no lo muestra: con el montaje del 2026-10-15 solo se pudo medir en 6 de 18 frases y con signos mezclados.
- La **cross-wavelet** sEMG × voz se quitó el 2026-10-15: no se podía leer en la demo y su lag por frecuencia nunca llegó a la pantalla.
- **Por condición:** RMS en µV RTI y amplitud de 50 Hz (sirve para ver la efectividad del RLD con y sin él). SNR = 20·log10(RMS habla / RMS reposo).
- **Confusor laríngeo** (refactor §3.3):
  - se calcula la F0 de la voz y el pico de cada canal sEMG en F0 respecto de la mediana del espectro de 20–500 Hz;
  - si el canal principal supera 10 dB, hay acople mecánico de la voz y no es actividad muscular;
  - no se calcula si F0 cae a menos de 5 Hz de un armónico de 50 Hz (con F0 = 100 Hz mediría la red).

## Estructura
```
main.go       goroutines: source → decoder → store; recorder; cwt; stats; web
frame/        formato del bloque, CRC16
source/       spi.go (spidev + DRDY con go-gpiocdev), sim.go, file.go, mux.go (en vivo ↔ sesión)
stream/       buffers circulares alineados por número de muestra + envolventes
dsp/          filtros, banco Morlet, correlación cruzada, F0, umbrales
analysis/     CWT por hop, enunciados, correlación con nivel de azar, estadísticas
ml/           clasificador: modelo del cuaderno, preproceso CWT, evaluador ONNX (runner.py)
record/       sesiones .avx (bloques crudos) + .json (condiciones, enunciados)
web/          servidor SSE + HMI embebida (static/), canales (canales.cfg)
deploy/       auravoxd.service, install.sh, ml-lib.sh (Python del clasificador para la Pi)
```
