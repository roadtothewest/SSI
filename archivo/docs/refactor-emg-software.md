# Refactor de software a sEMG

**Estado:** especificación activa. Define la fuente sEMG de 4 canales en
todo el árbol de software del proyecto SSI (firmware, `ssr-ingest`, `export.py`,
arquitectura de modelo, HMI).

**Fecha:** septiembre 2026. Contexto: Muestra TECH 2026, 15 de octubre.

**Relación con otros documentos:**

- `docs/afe-emg/AFE_EMG_Diseno.md` es la fuente de verdad del **hardware**
  (AFE de 4 canales sEMG + RLD). Este documento no reabre esas decisiones.
- Este documento cubre lo que falta: la **metodología de causalidad** que el
  software debe sostener, el esquema de dataset, y el checklist de refactor
  del código existente.
- Donde algo no está decidido, queda marcado como **TODO** explícito. No se
  inventan decisiones de hardware ni de firmware que dependan de mediciones
  aún no hechas.

---

## 0. Mantra del proyecto (principio rector)

Todo lo que sigue existe para cumplir **dos objetivos simultáneos, no uno**:

1. **Demostrar causalidad sEMG → fonemas.** No basta con correlación (§3).
2. **Construir la plataforma/estación de captura** que permita generar el
   **dataset masivo mínimo** necesario para que el pipeline de software
   propuesto (CWT → Conv2D → TCN → vocoder) generalice más allá de la demo.

El benchmark completo (sEMG + AFE + mic + STM32 + Raspberry Pi) no es solo un
experimento de causalidad puntual: es, en sí mismo, el **generador de corpus**
del proyecto. Un servicio en Go arma el dataset en paralelo a otra rutina que
renderiza una HMI web en tiempo real. Cualquier decisión de diseño en este
documento se evalúa contra estos dos objetivos, no contra uno solo.

---

## 1. Decisiones ya cerradas (no reabrir)

| Decisión | Valor | Fuente |
|---|---|---|
| Sensor primario | sEMG diferencial, **4 canales** (submentoniano, platisma, labio inferior, laringe) + RLD | `AFE_EMG_Diseno.md` |
| AFE | Construcción propia (discreto, 4 canales), no comprar AFE comercial armado; HackEEG/ADS129x evaluados y descartados por no-disponibilidad (no por mérito técnico) | `AFE_EMG_Diseno.md` §1, §3-4; ver también §7.3 de este doc |
| Micrófono | **Digital I2S — INMP441**, candidato recomendado, **NO comprado aún** | `bom.csv`; investigación previa a la compra en §2 de este doc |
| Entrada auxiliar analógica de mic vía ADS129x | Descartada, no aplica (no se usa ADS129x) | Indicación explícita del usuario |
| Arquitectura de modelo (Conv2D paralelo por canal → TCN causal → vocoder WORLD) | Se mantiene sin cambios de topología | `sprints/sprint-1/DL.md`, `clave.md` — el pipeline es agnóstico al tipo de sensor, solo cambia la semántica de los 4 canales de entrada |

---

## 2. Micrófono digital: investigación previa a la compra

**Corrección importante: el INMP441 todavía NO está comprado.** El proyecto
tiene el datasheet descargado (`datasheets/INMP441.PDF`) y el testbed ya
documenta su cableado planeado (`ssr-testbed/docs/pinout.md`, I2S3), pero es
un candidato, no una compra confirmada. El criterio del usuario es exigente:
no sirve un audio que no sea **prístino**, porque ese audio es el "ground
truth" del que se extraen los vectores de apoyo (F0, envolvente espectral,
aperiodicidad — ver §5 de este doc) para entrenar y para verificar el
vocoder WORLD. Un mic mediocre contamina esa referencia, no solo la demo.

**Evidencia encontrada (calidad de audio real, no solo hoja de datos):**

- El canal técnico *atomic14* hizo una comparación directa grabada en video
  entre INMP441 y SPH0645 (otro MEMS I2S muy usado): el INMP441 gana en ruido,
  ancho de banda y estabilidad de timing I2S. El SPH0645 usa un framing I2S
  no estándar que obliga a parchear librerías; el INMP441 no tiene ese
  problema. — [ESP32 Audio Input - INMP441 and SPH0645 MEMS I2S Breakout Boards](https://www.youtube.com/watch?v=3g7l5bm7fZ8)
- El mismo canal probó el ICS-43434 como sucesor "drop-in" del INMP441, con
  specs equivalentes o mejores, aunque un reporte lo describe como "difícil
  de conseguir" — otra razón para no complicarse si el INMP441 ya funciona.
  Si en algún momento el INMP441 elegido da problemas, el ICS-43434 es el
  reemplazo directo a evaluar. — [ICS-43434, a replacement for the old INMP441](https://www.atomic14.com/videos/posts/VVGln_-XEgI)
- Prueba de escucha comparativa (no solo specs): en un comparativo con
  varios módulos MEMS baratos grabando simultáneamente, oyentes calificaron
  los clips del INMP441 con mejor inteligibilidad que las alternativas —
  evidencia de que el audio percibido, no solo el número de SNR, favorece al
  INMP441.
- Specs de fábrica: SNR 61 dBA, sensibilidad -26 dBFS, respuesta en
  frecuencia ~60 Hz–15 kHz (cubre sobradamente la banda de voz), salida I2S
  de 24 bits, filtro anti-aliasing integrado.

**Honestidad sobre "prístino":** el INMP441 es la mejor opción **validada con
audio real** en su rango de precio, no un micrófono de grado estudio. Para el
uso que le va a dar el proyecto (ground truth de entrenamiento y verificación
del vocoder, no masterización) es suficiente según la evidencia encontrada,
pero la palabra final la tiene el usuario escuchando las muestras del video de
atomic14 (no solo leyendo esta tabla) antes de confirmar la compra.

**Riesgo real, no de la elección sino del proveedor:** hay reportes dispersos
en foros (Arduino, ESP32, esphome) de módulos INMP441 baratos con canal
plano/sin respuesta o con timing incorrecto — típico de control de calidad
inconsistente en breakouts genéricos de AliExpress, no un defecto del chip
INMP441 en sí. Mitigación: comprar de un vendedor con buen historial, y al
recibir el módulo correr una prueba de señal conocida (silbido a frecuencia
fija o tono de calibración) antes de integrarlo al pipeline de captura,
descartándolo si el nivel no responde o el ruido de piso es anormal.

**Conclusión: candidato recomendado, pendiente de compra.** Acción concreta
antes de ordenar: escuchar las muestras de audio del video de atomic14
enlazado arriba. Si suena aceptable para el oído del usuario, comprar; si no,
evaluar ICS-43434 pese a su menor disponibilidad.

---

## 3. Metodología de causalidad — esto define el éxito del proyecto

Esta es la sección más importante del refactor. Medir sEMG no vale nada si el
software solo reporta una correlación de Pearson. El argumento nuevo del proyecto es que el sEMG es
la **causa** (activación neuromuscular), anterior en el tiempo al sonido — y
esa anterioridad tiene que ser medible.

### 3.1 Lo que no basta

Un coeficiente de correlación entre sEMG y voz demuestra correlación, no
causalidad.

### 3.2 Lo que sí sostiene la afirmación

1. **Precedencia temporal.** Correlación cruzada con lag entre la envolvente
   sEMG y la envolvente acústica. El sEMG debe adelantarse al audio en
   decenas de ms (retardo electromecánico + tiempo articulatorio). El valor
   del lag, su signo y su estabilidad entre repeticiones son el resultado
   principal a reportar.
2. **Causalidad de Granger** o transferencia de entropía desde features sEMG
   hacia features acústicos, si el tiempo del sprint lo permite (ver
   roadmap — es candidato a recortar antes que el punto 1).
3. **Visualización en el HMI:** índice de correlación o mapa de calor que
   reaccione al movimiento muscular en tiempo real, con los 5 streams
   sincronizados (INMP441 arriba, 4 canales sEMG abajo — CH4 es el canal
   laríngeo dedicado, ver §8 "Especificación de HMI multi-pestaña" para el
   diseño completo de la interfaz).

### 3.3 Confusor crítico: el canal laríngeo (CH4)

La vibración de las cuerdas vocales (F0 ≈ 80–250 Hz) cae dentro de la banda
sEMG (20–500 Hz) y puede acoplarse mecánicamente al electrodo del canal
laríngeo (CH4, ver `AFE_EMG_Diseno.md`). Eso produce correlación altísima con
la voz **en la dirección causal equivocada** (voz → electrodo, por acople
mecánico, no activación neuromuscular real). Es la objeción técnica más
probable de un jurado informado, y hay que tener la respuesta lista con
datos, no de palabra.

Controles obligatorios del protocolo de captura:

| Condición | Resultado esperado si la señal es genuina |
|---|---|
| Articulación silenciosa (mover la boca sin fonar) | sEMG presente, audio ausente |
| Vocal sostenida sin articular | Sin pico espectral en F0 en CH4 (laríngeo) |
| Signo del lag | sEMG adelantado respecto del audio, no al revés |

La articulación silenciosa tiene además valor narrativo para la demo: es la
condición que se parece al usuario objetivo (paciente laringectomizado).

### 3.4 Protocolo de diagnóstico por canal (piso de ruido es una lectura, no el objetivo)

**Corrección de encuadre:** el objetivo de esta rutina **no es "tratar el
ruido de 50 Hz"** ni la red eléctrica en general. El objetivo es diagnosticar,
canal por canal, la diferencia entre tres estados — **EMG desconectado**,
**señal sin habla** y **señal con habla** — para poder observar directamente
la "intención fonética" en cada canal cuando se conecte el benchmark completo
(sEMG + AFE + mic + STM32 + Raspberry Pi). El 50 Hz es una lectura más dentro
de esta rutina (indica si el RLD funciona en la práctica), no la razón de ser
del protocolo.

Condiciones a registrar, todas con el mismo montaje de electrodos, **por cada
uno de los 4 canales por separado** (no agregadas):

1. **Desconectado:** AFE apagado, o electrodos no puestos / entrada en corto.
2. **Sin habla:** AFE encendido, electrodos puestos, usuario callado (línea
   base real de "sin intención fonética").
3. **Con habla:** usuario hablando/articulando con normalidad.
4. Las tres condiciones de control de la tabla 3.3 (articulación silenciosa,
   vocal sostenida, signo del lag), específicas para CH4.

Esto se visualiza en la HMI como parte de la pestaña "por canal" (§8) —
gráfico crudo superpuesto o alternable entre las tres condiciones — que es
la forma concreta de "observar la diferencia" que pidió el usuario, no un
número aislado de dB a 50 Hz.

**Esto debe ser un comando ejecutable** (script en `pc-tools` o rutina de
firmware), no un procedimiento manual que se hace una vez y se olvida.

---

## 4. Esquema de datos y transporte

- **Requisito nuevo del esquema de tupla:** cada tupla del corpus debe llevar
  el lag medido (o los datos crudos suficientes para recalcularlo). Sin eso,
  el dataset solo sostiene correlación, no causalidad — es el mismo problema
  del punto 3.1 pero a nivel de formato de archivo, no de análisis.
- El frame EMG (tipo `0x03`, definido en `AFE_EMG_Diseno.md` §5.1) es la
  fuente de la CWT. El frame AUDIO (`0x02`, del INMP441) no cambia.
- El servicio Go (`ssr-ingest`) no debe caerse ante desconexiones del AFE.

---

## 5. Corrección de un supuesto del plan original: ventana vs. hop de la CWT

A la tasa de muestreo del AFE (1–2 kHz por canal), una ventana de 5 ms son
apenas 5–10 muestras, y ninguna wavelet resuelve 20–50 Hz con ese soporte. La
longitud de ventana debe ser **≥ 50–100 ms**; el barrido de 5/10/20 ms debe
hacerse sobre el **salto (hop)** entre ventanas, no sobre la longitud de la
ventana. Si el código de `export.py` o el firmware tratan "ventana" y "hop"
como el mismo parámetro, hay que separarlos explícitamente.

---

## 6. Checklist de refactor de software (archivo por archivo)

**Firmware (`ssr-testbed/firmware/`)**

- [x] Driver del sensor anterior eliminado (`main.c`, `frame.c`, `Makefile`,
      `usb_cdc.h`), 27-sep.
- [ ] `Core/Src/frame.c`: agregar `frame_process_emg_*`, leyendo 4 canales
      desde ADC+DMA, con `CDC_TYPE_EMG` (`0x03`). En `main.c` hay un
      comentario en el lazo principal donde va la llamada.
- [ ] Bug previo: `frame.c` usa `active_buf`, que es `static` en
      `inmp441.c` (no compila); y `inmp441.c` registra los callbacks de TX de
      I2S (`HAL_I2S_TxHalfCpltCallback`) en vez de los de RX.
- [ ] `Core/Src/sync_timer.c`: se reutiliza sin cambios (la base de tiempo
      común es agnóstica al sensor).

**PC — ingesta (`ssr-testbed/pc-tools/ssr-ingest/`, Go)**

- [x] Parser (`parser/frame.go`), `ssr-inspect` y `ssr-replay`: reconocen el
      frame `0x03` (27-sep).
- [ ] `storage/writer.go`: agregar el sensor EMG a `metadata.json` y su
      contador de frames. Además no compila por errores previos
      (`sha256.Sum256` usado como tipo, `WriteFrame` declarado dos veces).

**PC — exportación (`ssr-testbed/pc-tools/ssr-export/export.py`)**

- [x] `extract_emg_channels`: 4 canales int16 intercalados, timestamps con la
      tasa real del ADC (`--fs-emg`, 2 kHz por defecto); CWT de 20–500 Hz por
      canal, salida `cwt_mag` (4, escalas, N). Probado con un `.ssr`
      sintético (27-sep).
- [x] `align_channels`: alinea EMG y audio por timestamp.
- [ ] CWT: separar parámetro `window_ms` (≥50–100 ms) de `hop_ms` (5/10/20 ms)
      — ver §5 de este documento.
- [ ] Agregar el cálculo de correlación cruzada con lag (§3.2) como parte del
      pipeline de exportación, no como notebook aparte.

**Round-trip de audio (`ssr-testbed/pc-tools/ssr-roundtrip/`)**

- [ ] Extender `roundtrip.py`/`mel_utils.py` con una ruta basada en `pyworld`
      (dio/harvest → F0, cheaptrick → envolvente, d4c → aperiodicidad,
      synthesize → resíntesis), en paralelo a la ruta Mel+Griffin-Lim
      existente — ver §9. Reusar `compute_pesq`/`compute_stoi` para comparar
      objetivamente ambas rutas.

**Documentación del testbed (`ssr-testbed/docs/`)**

- [x] `architecture.md`, `pinout.md`, `pipeline.md` y diagramas describen la
      fuente sEMG (27-sep). Los pines del ADC siguen **bloqueados por una
      decisión pendiente** — ver TODO 7.1 más abajo.

**Modelo (`sprints/sprint-1/DL.md`, `clave.md`)**

- [x] Adaptados a 4 canales sEMG (submentoniano, platisma, labio inferior,
      laringe): ramas Conv2D paralelas por canal y TCN causal (27-sep).

**HMI**

- [ ] Implementar la especificación completa de §8 (multi-pestaña): por
      canal, comparación CWT STM32 vs. Go, causalidad, round-trip WORLD.
- [ ] Agregar modo de captura por condición experimental (§3.3 y §3.4),
      seleccionable desde la interfaz.

---

## 7. Preguntas abiertas (genuinas — no decidir por defecto)

### 7.1 MCU objetivo del testbed — **inconsistencia detectada, requiere decisión del usuario**

`ssr-testbed/docs/pinout.md` y `architecture.md` describen el testbed **actual**
sobre **NUCLEO-H723ZG**. `AFE_EMG_Diseno.md` §5 y el README (producto final)
describen la interfaz ADC sobre **STM32N6**. No se sabe, a partir del
repositorio, si el testbed migra ahora a una placa N6 (p. ej. STM32N6570-DK)
o si el H723ZG sigue siendo la plataforma de desarrollo hasta más adelante.
Esto determina el pinout real del ADC de 4 canales y no debe inventarse.
**TODO: decidir y documentar antes de tocar `pinout.md`.**

### 7.2 Resolución de ADC y ganancia total

`AFE_EMG_Diseno.md` asume ADC de 12 bits con oversampling a ~14 bits
efectivos. Falta verificar en la placa real elegida (según 7.1) si esa
resolución alcanza para la señal facial débil (decenas–cientos de µV) con la
ganancia del AFE ya definida (§3.3 del doc de AFE). **TODO: medir, no asumir.**

### 7.3 Mínimo de canales para la demo — **CERRADO EN 4**

**Decisión final (sep. 2026): 4 canales** (submentoniano, platisma, labio
inferior, laringe — CH4 dedicado). Esta pregunta se cerró primero en 3 por
presupuesto, y se **reabrió** a pedido explícito del usuario: el 4º canal
(laríngeo) vuelve como canal permanente, restaurando la tabla original de 4
sitios y los 9 electrodos (8 de señal + 1 referencia/RLD).

**Impacto en presupuesto:** el 4º canal agrega ~USD 8–14 sobre el estimado de
3 canales (~USD 30–54), llevando el total a **~USD 38–68** contra el tope de
USD 60 — riesgo real de pasarse levemente en el peor caso. Mitigaciones
documentadas en `bom.csv`: electrodos reusables en vez de pregelados
desechables, y usar un op-amp sobrante de los 4 chips cuádruples ya
comprados para el integrador RLD en vez de un 5to chip dedicado.

**HackEEG / ADS129x evaluados de nuevo y descartados** (no por mérito
técnico): HackEEG está descontinuado (Crowd Supply sin stock) y el chip
ADS1298/1299 pelado no tiene breakout comercial armado, viene en TQFP-64
(reflow, layout sensible) y es una parte de nicho de TI con baja
disponibilidad en Chile — ver el detalle completo en
`AFE_EMG_Diseno.md` §1. Queda documentado como ruta recomendada para una v2
post-Muestra (§5 de ese doc).

**No se vuelve a reabrir esta pregunta** salvo cambio de presupuesto o de
disponibilidad de componentes.

### 7.4 Tipo de inferencia del modelo

Sigue abierto qué tipo de inferencia (continuous speech u otro) se ajusta
mejor al corpus recapturado con sEMG. Define el Minimum Viable Dataset.
**TODO.**

---

## 8. Especificación de HMI multi-pestaña

El cliente web (Go) renderiza el HMI en tiempo real **en paralelo** a la
rutina que arma el dataset — no son pasos secuenciales, son dos rutinas
corriendo a la vez sobre el mismo stream de tuplas. La interfaz debe tener
**varias pestañas**, no una sola pantalla de "índice de correlación":

| Pestaña | Contenido | Para qué sirve |
|---|---|---|
| **Por canal** | Gráfico crudo de cada uno de los 4 canales sEMG + INMP441, con selector de condición (desconectado / sin habla / con habla, §3.4) | Ver directamente la "intención fonética": la diferencia visual entre las tres condiciones por canal |
| **Comparación CWT** | Escalograma calculado en el STM32N6 vs. el mismo cálculo hecho en Go/Raspberry Pi, lado a lado, con métricas de latencia y costo por ventana | Benchmark de procesamiento (ya mencionado en el documento AuraVox original §6.4, aterrizado aquí como requisito de UI concreto) |
| **Causalidad** | Índice de correlación cruzada con lag y/o mapa de calor (§3.2), reaccionando en tiempo real al movimiento muscular | Demostración en vivo del objetivo 1 del mantra (§0) |
| **Round-trip WORLD** | Comparación audio original vs. audio resintetizado desde los vectores de apoyo (§9), con métricas PESQ/STOI | Demostración en vivo de la bi-direccionalidad del vocoder |

La pestaña "por canal" es la que responde directamente a la corrección de
§3.4: no un solo número de ruido de 50 Hz, sino una comparación visual clara
entre las tres condiciones, por canal, que cualquier persona del jurado pueda
leer sin explicación técnica adicional.

## 9. Verificación de bi-direccionalidad del vocoder WORLD

Objetivo 2 del mantra (§0) necesita, además del hardware de captura, una
prueba de que el algoritmo de síntesis es determinista y reversible **antes**
de involucrar al DNN. Metodología pedida por el usuario:

1. **Análisis:** a partir de audio crudo (grabación real del INMP441),
   extraer los **vectores de apoyo**: F0, envolvente espectral y
   aperiodicidad (los tres parámetros del vocoder WORLD). En producción,
   estos mismos vectores son los que el DNN infiere a partir del sEMG — pero
   esta prueba no depende del DNN, solo del vocoder.
2. **Síntesis:** a partir de esos vectores de apoyo, resintetizar el audio
   original con el sintetizador determinista de WORLD.
3. **Verificación:** comparar audio original vs. audio resintetizado
   (round-trip). Si el algoritmo es correcto y determinista, la
   reconstrucción debe ser fiel independientemente de si los vectores vienen
   de análisis real (esta prueba) o de inferencia del DNN (producción).

**Ya existe un prototipo de esto en el repo, sin trackear todavía:**
`ssr-testbed/pc-tools/ssr-roundtrip/` (`roundtrip.py`, `mel_utils.py`,
`audio_io.py`) hace exactamente este round-trip, con métricas ya
implementadas (`compute_pesq`, `compute_stoi` en `roundtrip.py`) y un primer
par de audios de prueba (`dataset/roundtrip/original.wav` /
`reconstructed.wav`). **Pero usa Mel-spectrogram + Griffin-Lim**
(`mel_utils.py: audio_to_mel` / `mel_to_audio`), no WORLD — y eso contradice
la propia recomendación ya hecha en `sprints/sprint-1/clave.md`, que señala a
WORLD como el algoritmo correcto precisamente por ser bi-direccional y
determinista, a diferencia de Mel+Griffin-Lim (que introduce artefactos de
fase y suena "robótico/metálico").

**Tarea concreta (ver checklist §6):** extender `ssr-roundtrip` con una ruta
WORLD real usando la librería `pyworld` (`dio`/`harvest` → F0, `cheaptrick` →
envolvente espectral, `d4c` → aperiodicidad, `synthesize` → resíntesis),
reusando las métricas PESQ/STOI que el script ya calcula para poder comparar
objetivamente la fidelidad de ambas rutas (Mel actual vs. WORLD nuevo) y
quedarse con la que mejor puntúe — la expectativa, según `clave.md`, es que
WORLD gane.

## 10. Referencias

- `docs/afe-emg/AFE_EMG_Diseno.md` — diseño de hardware del AFE sEMG (4 canales).
- [ESP32 Audio Input - INMP441 and SPH0645 MEMS I2S Breakout Boards (atomic14, YouTube)](https://www.youtube.com/watch?v=3g7l5bm7fZ8)
- [ICS-43434, a replacement for the old INMP441 (atomic14)](https://www.atomic14.com/videos/posts/VVGln_-XEgI)
- `bom.csv` — estado de compra de componentes (INMP441 candidato, pendiente de compra; AFE sEMG de 4 canales cotizado — ver §7.3).
- [BioAmp EXG Pill — Crowd Supply](https://www.crowdsupply.com/upside-down-labs/bioamp-exg-pill) — pricing consultado sep. 2026: USD 35–249 según pack, sin RLD onboard.
- [HackEEG — Crowd Supply](https://www.crowdsupply.com/starcat/hackeeg) — USD 495–2090, descontinuado (sin stock) al consultar sep. 2026.
- `ssr-testbed/pc-tools/ssr-roundtrip/` — prototipo de round-trip de audio (Mel+Griffin-Lim, pendiente extender a WORLD — ver §9).
- `sprints/sprint-1/clave.md` — comparación Mel+Griffin-Lim vs. vocoder WORLD, recomienda WORLD.
