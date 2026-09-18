# Refactor de software: de acelerómetro a sEMG

**Estado:** especificación activa. Reemplaza los supuestos de acelerómetro en
todo el árbol de software del proyecto SSI (firmware, `ssr-ingest`, `export.py`,
arquitectura de modelo, HMI).

**Fecha:** septiembre 2026. Contexto: Muestra TECH 2026, 15 de octubre.

**Relación con otros documentos:**

- `docs/afe-emg/AFE_EMG_Diseno.md` es la fuente de verdad del **hardware**
  (AFE de 3 canales sEMG + RLD). Este documento no reabre esas decisiones.
- Este documento cubre lo que falta: la **metodología de causalidad** que el
  software debe sostener, el esquema de dataset, y el checklist de refactor
  del código existente.
- Donde algo no está decidido, queda marcado como **TODO** explícito. No se
  inventan decisiones de hardware ni de firmware que dependan de mediciones
  aún no hechas.

---

## 1. Decisiones ya cerradas (no reabrir)

| Decisión | Valor | Fuente |
|---|---|---|
| Sensor primario | sEMG diferencial, 3 canales (submentoniano, platisma, comisura labial) + RLD | `AFE_EMG_Diseno.md` |
| Acelerómetro IIS3DWB | Descartado por completo | README, esta sesión |
| AFE | Construcción propia (discreto), no comprar AFE comercial armado | `AFE_EMG_Diseno.md` §3-4; motivo: costo |
| Micrófono | **Digital I2S — INMP441**, ya comprado | `bom.csv`; validación en §2 de este doc |
| Entrada auxiliar analógica de mic vía ADS129x | Descartada, no aplica (no se usa ADS129x) | Indicación explícita del usuario |
| Arquitectura de modelo (Conv2D paralelo por canal → TCN causal → vocoder WORLD) | Se mantiene sin cambios de topología | `sprints/sprint-1/DL.md`, `clave.md` — el pipeline es agnóstico al tipo de sensor, solo cambia la semántica de los 3 canales de entrada |

---

## 2. Micrófono digital: validación de la elección

El proyecto ya tenía decidido y comprado el INMP441 (breakout I2S, ver
`bom.csv` y `datasheets/INMP441.PDF`), y ya está cableado en el testbed
(`ssr-testbed/docs/pinout.md`, I2S3). No hace falta elegir de nuevo; lo que
pedía el usuario era **confirmar con evidencia externa** que no es un error de
compra.

**Evidencia encontrada:**

- El canal técnico *atomic14* hizo una comparación directa grabada en video
  entre INMP441 y SPH0645 (otro MEMS I2S muy usado): el INMP441 gana en ruido,
  ancho de banda y estabilidad de timing I2S. El SPH0645 usa un framing I2S
  no estándar que obliga a parchear librerías; el INMP441 no tiene ese
  problema. — [ESP32 Audio Input - INMP441 and SPH0645 MEMS I2S Breakout Boards](https://www.youtube.com/watch?v=3g7l5bm7fZ8)
- El mismo canal probó el ICS-43434 como sucesor "drop-in" del INMP441, con
  specs equivalentes o mejores. Si en algún momento el INMP441 comprado da
  problemas, el ICS-43434 es el reemplazo directo a evaluar — pero no hay
  motivo para cambiar hoy. — [ICS-43434, a replacement for the old INMP441](https://www.atomic14.com/videos/posts/VVGln_-XEgI)
- Specs de fábrica: SNR 61 dBA, sensibilidad -26 dBFS, salida I2S de 24 bits,
  filtro anti-aliasing integrado. Suficiente como referencia de "ground
  truth" de audio para entrenar el modelo (no es un requisito de grabación
  profesional).

**Riesgo real, no de la elección sino del proveedor:** hay reportes dispersos
en foros (Arduino, ESP32, esphome) de módulos INMP441 baratos con canal
plano/sin respuesta o con timing incorrecto — típico de control de calidad
inconsistente en breakouts genéricos de AliExpress, no un defecto del chip
INMP441 en sí. Mitigación de bajo costo: al recibir el módulo, correr una
prueba de señal conocida (silbido a frecuencia fija o tono de calibración)
antes de integrarlo al pipeline de captura, y descartarlo si el nivel no
responde o el ruido de piso es anormal.

**Conclusión: se mantiene el INMP441.** No se evalúan más alternativas salvo
que la prueba de recepción falle.

---

## 3. Metodología de causalidad — esto define el éxito del proyecto

Esta es la sección más importante del refactor. Medir sEMG en vez de vibración
no vale nada si el software solo reporta una correlación de Pearson: eso ya lo
podía hacer el acelerómetro. El argumento nuevo del proyecto es que el sEMG es
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
   reaccione al movimiento muscular en tiempo real, con los 4 streams
   sincronizados (INMP441 arriba, 3 canales sEMG abajo — ver §7.3 sobre por
   qué son 3 y no 4 canales sEMG).

### 3.3 Confusor crítico: el canal laríngeo (o el más cercano a la laringe)

La vibración de las cuerdas vocales (F0 ≈ 80–250 Hz) cae dentro de la banda
sEMG (20–500 Hz) y puede acoplarse mecánicamente al electrodo más cercano a la
laringe. Eso produce correlación altísima con la voz **en la dirección causal
equivocada** (voz → electrodo, por acople mecánico, no activación
neuromuscular real). Es la objeción técnica más probable de un jurado
informado, y hay que tener la respuesta lista con datos, no de palabra.

Controles obligatorios del protocolo de captura:

| Condición | Resultado esperado si la señal es genuina |
|---|---|
| Articulación silenciosa (mover la boca sin fonar) | sEMG presente, audio ausente |
| Vocal sostenida sin articular | Sin pico espectral en F0 en el canal cercano a la laringe |
| Signo del lag | sEMG adelantado respecto del audio, no al revés |

La articulación silenciosa tiene además valor narrativo para la demo: es la
condición que se parece al usuario objetivo (paciente laringectomizado).

### 3.4 Protocolo de piso de ruido

Condiciones a registrar, todas con el mismo montaje de electrodos:

1. AFE apagado.
2. AFE encendido, sin electrodos o con entrada en corto.
3. AFE encendido, electrodos puestos, usuario callado.
4. Las tres condiciones de la tabla 3.3.

Objetivo: diferenciar el stream sEMG con voz del stream en silencio, y
resolver si el baseline es ruido puro o contiene información útil. La
magnitud del 50 Hz en la condición 3 es la que confirma si el RLD ya
implementado (ver `AFE_EMG_Diseno.md` §3.4) está funcionando en la práctica,
no solo en el papel.

**Esto debe ser un comando ejecutable** (script en `pc-tools` o rutina de
firmware), no un procedimiento manual que se hace una vez y se olvida.

---

## 4. Esquema de datos y transporte

- **Requisito nuevo del esquema de tupla:** cada tupla del corpus debe llevar
  el lag medido (o los datos crudos suficientes para recalcularlo). Sin eso,
  el dataset solo sostiene correlación, no causalidad — es el mismo problema
  del punto 3.1 pero a nivel de formato de archivo, no de análisis.
- El frame EMG (tipo `0x03`, definido en `AFE_EMG_Diseno.md` §5.1) reemplaza
  al frame ACC (`0x01`) como fuente de la CWT. El frame AUDIO (`0x02`, del
  INMP441) no cambia.
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

- [ ] `Core/Src/iis3dwb.c` y su driver SPI: eliminar o archivar: ya no hay
      acelerómetro que inicializar por SPI.
- [ ] `Core/Src/frame.c` — `frame_process_acc_half` / `frame_process_acc_full`:
      reemplazar por `frame_process_emg_*`, leyendo 3 canales desde ADC+DMA
      en vez de 3 ejes desde el buffer SPI del IIS3DWB. Frame type pasa de
      `CDC_TYPE_ACC` a `CDC_TYPE_EMG` (`0x03`).
- [ ] `Core/Src/main.c:170` (llamador de `frame_process_acc_full`): actualizar
      la llamada al nuevo handler EMG.
- [ ] `Core/Src/sync_timer.c`: se reutiliza sin cambios (la base de tiempo
      común es agnóstica al sensor).

**PC — ingesta (`ssr-testbed/pc-tools/ssr-ingest/`, Go)**

- [ ] `storage/writer.go` (`NewWriter` y writers de frame): agregar tipo de
      frame EMG junto a ACC/AUDIO, o reemplazar ACC por EMG si no se necesita
      retrocompatibilidad con sesiones viejas.
- [ ] Parser/decodificador de frame: sumar el caso `0x03` del formato de
      `AFE_EMG_Diseno.md` §5.1.

**PC — exportación (`ssr-testbed/pc-tools/ssr-export/export.py`)**

- [ ] `extract_acc_channel` → `extract_emg_channel`: mismo patrón de
      deserialización, pero 3 canales sEMG (int16) en vez de x/y/z, y el
      divisor de timestamp debe usar la tasa real del ADC (1–2 kHz), no los
      26.7 kHz del IIS3DWB.
- [ ] `align_channels`: revisar que siga alineando por timestamp sin asumir
      la ODR del acelerómetro.
- [ ] CWT: separar parámetro `window_ms` (≥50–100 ms) de `hop_ms` (5/10/20 ms)
      — ver §5 de este documento.
- [ ] Agregar el cálculo de correlación cruzada con lag (§3.2) como parte del
      pipeline de exportación, no como notebook aparte.

**Documentación del testbed (`ssr-testbed/docs/`)**

- [ ] `architecture.md`, `pinout.md`, `pipeline.md`: describen todavía al
      IIS3DWB sobre SPI y el NUCLEO-H723ZG. **Bloqueados por una decisión
      pendiente** — ver TODO 7.1 más abajo — no reescribir el pinout hasta
      resolverla, para no inventar una asignación de pines que después haya
      que deshacer.

**Modelo (`sprints/sprint-1/DL.md`, `clave.md`)**

- [ ] No requieren cambio de arquitectura. Sí requieren relabeling: donde dice
      "eje X/Y/Z del acelerómetro" leer "canal 1/2/3 sEMG (submentoniano/
      platisma/comisura labial)". El razonamiento de ramas Conv2D paralelas
      por canal y TCN causal aplica igual.

**HMI**

- [ ] Agregar modo de captura por condición experimental (§3.3 y §3.4),
      seleccionable desde la interfaz.
- [ ] Panel: voz (INMP441) arriba, 3 canales sEMG abajo, en tiempo real, más
      índice de correlación visual.

---

## 7. Preguntas abiertas (genuinas — no decidir por defecto)

### 7.1 MCU objetivo del testbed — **inconsistencia detectada, requiere decisión del usuario**

`ssr-testbed/docs/pinout.md` y `architecture.md` describen el testbed **actual**
sobre **NUCLEO-H723ZG**. `AFE_EMG_Diseno.md` §5 y el README (producto final)
describen la interfaz ADC sobre **STM32N6**. No se sabe, a partir del
repositorio, si el testbed migra ahora a una placa N6 (p. ej. STM32N6570-DK)
o si el H723ZG sigue siendo la plataforma de desarrollo hasta más adelante.
Esto determina el pinout real del ADC de 3 canales y no debe inventarse.
**TODO: decidir y documentar antes de tocar `pinout.md`.**

### 7.2 Resolución de ADC y ganancia total

`AFE_EMG_Diseno.md` asume ADC de 12 bits con oversampling a ~14 bits
efectivos. Falta verificar en la placa real elegida (según 7.1) si esa
resolución alcanza para la señal facial débil (decenas–cientos de µV) con la
ganancia del AFE ya definida (§3.3 del doc de AFE). **TODO: medir, no asumir.**

### 7.3 Mínimo de canales para la demo — **CERRADO**

**Decisión (sep. 2026): 3 canales** (submentoniano, platisma, comisura
labial), no 4. Se evaluó volver a 4 canales (uno dedicado a laringe) usando
4x BioAmp EXG Pill en vez del AFE discreto, porque con Pills el costo marginal
de un canal extra es solo otra placa. Esa ruta se descartó por presupuesto:
4 Pills cuestan ~USD 138 (2x Explorer Pack) contra un tope duro de **USD 60**
fijado por el usuario para todo el AFE; HackEEG (la otra opción "lista") sale
USD 495–2090 y además está descontinuado (Crowd Supply lo marca sin stock).
Con el AFE discreto ya diseñado en `AFE_EMG_Diseno.md`, un 4º canal agrega
~25% más partes y tiempo de armado/debug — exactamente lo que puede hacer
pasarse del tope de USD 60. **No se reabre esta pregunta salvo cambio de
presupuesto.**

El canal laríngeo se pierde como *canal permanente*, pero el control del
confusor de §3.3 no depende de tenerlo simultáneo a los otros 3: en una
sesión de captura dedicada, se reubica temporalmente el electrodo de uno de
los 3 canales sobre el sitio laríngeo para correr esa condición de control.
Es un ajuste de protocolo de captura, no de hardware, y no requiere volver a
abrir el diseño del AFE.

### 7.4 Tipo de inferencia del modelo

Sigue abierto qué tipo de inferencia (continuous speech u otro) se ajusta
mejor al corpus recapturado con sEMG. Define el Minimum Viable Dataset.
**TODO.**

---

## 8. Referencias

- `docs/afe-emg/AFE_EMG_Diseno.md` — diseño de hardware del AFE sEMG.
- [ESP32 Audio Input - INMP441 and SPH0645 MEMS I2S Breakout Boards (atomic14, YouTube)](https://www.youtube.com/watch?v=3g7l5bm7fZ8)
- [ICS-43434, a replacement for the old INMP441 (atomic14)](https://www.atomic14.com/videos/posts/VVGln_-XEgI)
- `bom.csv` — estado de compra de componentes (acelerómetro descartado, INMP441 validado, AFE sEMG cotizado — ver §7.3).
- [BioAmp EXG Pill — Crowd Supply](https://www.crowdsupply.com/upside-down-labs/bioamp-exg-pill) — pricing consultado sep. 2026: USD 35–249 según pack, sin RLD onboard.
- [HackEEG — Crowd Supply](https://www.crowdsupply.com/starcat/hackeeg) — USD 495–2090, descontinuado (sin stock) al consultar sep. 2026.
