# SSI / AuraVox — Contexto y decisiones (documento 1 de 2)

**Propósito:** traspaso a Gemini para terminar de diseñar el AFE sEMG. Es una transcripción por tema (no turno a turno) de la conversación con Claude Code del 18–19 sep 2026. El detalle del circuito está en `gemini_2_diseno_afe.md`.

**Adjuntar también a Gemini:** `docs/afe-emg/AFE_EMG_Diseno.md` (diseño previo del repo; su diagrama §3.2 quedó **desactualizado**, ver documento 2 §2) y `AD8232.PDF` (Analog Devices, Rev. A).

## Leyenda de confianza (se usa en ambos documentos)

| Etiqueta | Significado |
|---|---|
| [VERIFICADO-DS] | Leído directamente en un datasheet durante la sesión (AD8232 Rev. A, págs. 16–23). |
| [REPO] | Viene de documentos del repositorio; no se re-verificó contra datasheets. |
| [WEB] | Resumen automático de una página web; puede ser inexacto. |
| [MEMORIA] | Dato que Claude citó de memoria; **verificar antes de usar**. |
| [USUARIO] | Decisión o afirmación del usuario. |

## Qué se le pide a Gemini

Cerrar el esquemático del AFE sEMG (4 canales + RLD): valores de componentes, cálculos de ganancia y cortes, netlist por bloque y riesgos. No reabrir lo que figura como cerrado en la tabla de decisiones. Verificar contra datasheet todo lo marcado [MEMORIA] o [REPO]. Los puntos abiertos están en el documento 2 §12.

## 1. Proyecto y plazo

- **SSI (Silent Speech Interface) / AuraVox**, "Estación de Auditoría – Corpus Generator". Autores: Matías Pérez y Vicente Andrade (AuraVox.pdf, sep 2026).
- **Muestra TECH 2026: 15 de octubre de 2026.** Fecha de esta transcripción: 19 sep 2026 (26 días). Criterios de evaluación [REPO]: Creatividad 40 %, Nivel Técnico 25 %, Presentación 20 %, Impacto Social 15 %.
- Repo: https://github.com/roadtothewest/SSI (rama `master`). Estos dos `.md` no están commiteados.
- Arquitectura [USUARIO]: sEMG → AFE → STM32 (ADC+DMA) + micrófono digital (I2S) → SPI → Raspberry Pi 5. En la Pi, un servicio en Go arma el dataset "en paralelo a otra rutina que renderiza la HMI (en tiempo real)". El spec original usa STM32N6570-DK con RTOS y 3 tasks (A: sEMG, B: micrófono, C: empaquetado y envío SPI) [REPO].

## 2. Mantra del proyecto (palabras del usuario)

> "nosotros queremos matar dos pájaros de un tiro. 1. Demostrar causalidad sEMG -> fonemas. 2. Crear la plataforma que permite generar el dataset masivo mínimo para lograr generalidad en el software (pipeline) propuesto."

Metas en el orden que dio el usuario:
1. **Resolver la limitación física actual:** un AFE para 3 o 4 canales (2 electrodos por canal) más el RLD "con la normalización de ruido".
2. Ver en la HMI las CWT, idealmente comparando la calculada en el STM con la calculada en Go.
3. Demostrar la **bi-direccionalidad del algoritmo de síntesis WORLD**: desde audio crudo generar "vectores de apoyo" (en producción se infieren con la DNN) y desde ellos sintetizar el audio original, para verificar el algoritmo determinista a la salida de la DNN.

## 3. Estado y decisiones

| Tema | Decisión | Estado |
|---|---|---|
| Sensor | sEMG diferencial. El acelerómetro IIS3DWB **se descartó por completo** (medía un efecto del habla, no su causa). Costo hundido ≈ CLP 28.000. | Cerrado |
| Canales | **4**: CH1 submentoniano, CH2 platisma, CH3 labio inferior, CH4 laringe. Primero se cerró en 3 por presupuesto; el usuario pidió reabrirlo y quedó en 4. | Cerrado |
| Electrodos | 9 (8 de señal + 1 electrodo de RLD/referencia). | Cerrado |
| Ruta de AFE | Discreto propio, "Ruta B" perfboard (sin PCB fabricado, sin espera de manufactura). El usuario tiene "vasta experiencia diseñando y validando circuitos basados en op amps". | Cerrado |
| Presupuesto | **Tope duro USD 60** para todo el AFE [USUARIO]. Estimado del BOM para 4 canales: CLP 36.000–65.000 (≈ USD 38–68). Riesgo de pasarse; ver documento 2 §12 (el conteo de op-amps subió). | Abierto (riesgo) |
| Micrófono | **INMP441 (digital I2S), NO comprado todavía.** Es candidato recomendado. El usuario exige audio "prístino" y quiere confirmarlo con evidencia antes de comprar. | Abierto |
| Alimentación | El usuario dijo: "creo que no lo haré portátil, usaré alimentación de red, pero puedo usar un notch post conversión ac/dc". Ver alerta de seguridad (§7). | Abierto |
| Ferrita en entradas | El usuario la descartó: "no me tinca la ferrita, nunca la he usado, no quiero añadir dinámicas raras". | Cerrado |
| Buffer de salida antes del ADC | Sí ("Si vamos con buffer de salida"). | Cerrado |
| Orden de etapas | INA → HPF → G2 → LPF → buffer → ADC (ver documento 2 §2 y §6). | Cerrado |
| MCU del testbed | Sin resolver: `pinout.md`/`architecture.md` del repo describen NUCLEO-H723ZG; el README y el diseño de AFE asumen STM32N6. Determina el pinout real del ADC. | Abierto |

## 4. Alternativas de AFE evaluadas y descartadas

| Opción | Datos | Por qué se descartó |
|---|---|---|
| 4× BioAmp EXG Pill (Upside Down Labs) | [WEB] Crowd Supply: US$ 35 (1 unidad con 100 electrodos), US$ 69 (2 placas), US$ 249 (8 placas); 1 canal por placa; entrada 4,5–40 V. Diseñada para MCU de 5 V. | ≈ US$ 138 para 4 placas, más del doble del tope. Además su pin "DRL" **no es un RLD**: por netlist [REPO] es un seguidor de VCC/2 unido a `DRL` por R11 = 0 Ω, sin lazo que sense el modo común. |
| HackEEG (Starcat, ADS1299) | [WEB] US$ 495–2090; 8 canales apilables a 32; Crowd Supply lo marca "No longer available". | Descontinuado (no hay unidades) y fuera de presupuesto. Técnicamente muy superior (RLD real en silicio, ADC delta-sigma de 24 bits, PGA por canal). |
| Chip ADS1298/1299 pelado en PCB propio | [REPO] TQFP-64, exige reflow y layout muy sensible al bypass; no existe breakout comercial armado; pieza de nicho, poca disponibilidad en Chile. | Inviable en 26 días. Queda como ruta recomendada para una v2 post-Muestra. |
| ADS1292R (ProtoCentral) | [REPO] Da 1 canal sEMG útil por placa (el segundo se usa para respiración) y no expone el pin CLK para sincronizar placas. | Descartado. |
| Comprar un AFE armado en general | Ninguna placa armada con RLD activo y 3–4 canales entra en USD 60. | La única ruta dentro del presupuesto es construirlo. |

Citas [WEB]: los precios y la disponibilidad salieron de una lectura automática de https://www.crowdsupply.com/upside-down-labs/bioamp-exg-pill y https://www.crowdsupply.com/starcat/hackeeg; confirmar en el sitio.

## 5. Micrófono INMP441 (evidencia reunida)

- El canal atomic14 lo comparó en video contra el SPH0645 con grabaciones reales; según el resumen, el INMP441 gana en ruido, ancho de banda y estabilidad de timing I2S: https://www.youtube.com/watch?v=3g7l5bm7fZ8 [WEB].
- El mismo canal presenta el ICS-43434 como reemplazo directo, con specs equivalentes o algo mejores, pero una fuente lo describe como "difícil de conseguir": https://www.atomic14.com/videos/posts/VVGln_-XEgI [WEB].
- Un comparativo con oyentes calificó los clips del INMP441 con mejor inteligibilidad que otros MEMS baratos [WEB, sin fuente primaria verificada].
- Specs citadas: SNR 61 dBA, sensibilidad −26 dBFS, respuesta ≈ 60 Hz–15 kHz, salida I2S de 24 bits [WEB/MEMORIA].
- Claude no puede escuchar audio: el juicio de "prístino" lo tiene que dar el usuario **escuchando las muestras** del video antes de comprar.
- Riesgo real: módulos genéricos de AliExpress con canal muerto o timing incorrecto. Mitigación: vendedor con historial y prueba con tono conocido al recibirlo.

## 6. Lo que el software le pide al AFE

Requisitos que bajan al hardware [REPO salvo indicación]:

- **Sincronía entre los 4 canales y la voz** ("es fundamental" [USUARIO]). Un solo ADC del STM en modo scan + DMA disparado por timer, mismo reloj que el I2S del micrófono. El desfase entre canales es de microsegundos, despreciable frente a los retardos de decenas de ms que se quieren medir.
- Banda 20–500 Hz, muestreo 1–2 kHz por canal, 4 canales.
- Trama propuesta: tipo `0x03` = EMG, `N muestras × 4 × int16` (CH1..CH4), con timestamp en µs.
- CWT: ventana ≥ 50–100 ms (una ventana de 5 ms son 10 muestras y no resuelve 20–50 Hz); el barrido de 5/10/20 ms se hace sobre el *hop*, no sobre la longitud de ventana.
- Los rangos extremos de entrada importan porque el software debe detectar saturación y electrodo suelto por canal (por umbral si el AFE no lo hace).
- **Protocolo de diagnóstico por canal** [USUARIO, corrigiendo un encuadre previo]: el objetivo *no* es "tratar el ruido de 50 Hz" sino poder ver, por canal, la diferencia entre **EMG desconectado**, **señal sin habla** y **señal con habla**, para observar la "intención fonética". El 50 Hz es solo una lectura más.
- HMI web con varias pestañas: por canal (crudo, con las tres condiciones), comparación CWT STM32 vs Go/Pi (latencia y costo por ventana), causalidad (correlación cruzada con lag) y round-trip WORLD (PESQ/STOI).
- Causalidad: correlación cruzada con lag entre envolvente sEMG y acústica (el sEMG debe adelantarse decenas de ms). Confusor crítico: la vibración de las cuerdas vocales (F0 ≈ 80–250 Hz) cae dentro de la banda sEMG y puede acoplarse al electrodo laríngeo (CH4). Controles: articulación silenciosa, vocal sostenida sin articular, signo del lag.
- WORLD: el repo ya tiene `ssr-testbed/pc-tools/ssr-roundtrip/` (sin trackear), pero usa Mel + Griffin-Lim, no WORLD; queda como tarea extenderlo con `pyworld` reutilizando PESQ/STOI.

## 7. Alertas transversales

1. **Seguridad con alimentación de red:** el spec original decía captura solo con batería (o notebook a batería / aislador USB) porque hay electrodos sobre cuello y cara. El usuario ahora quiere alimentación de red. Eso exige aislamiento galvánico (fuente aislada o de grado médico, aislador USB para el ST-LINK, y considerar el HDMI/monitor de la Pi). Un notch después de la conversión AC/DC **no** reemplaza el aislamiento. Claude no lo advirtió en el momento; queda registrado aquí.
2. **LDO ya comprado ≠ 3,3 V:** el LDO del BOM es de **3,0 V** (TLV70030 o MIC5205-3.0), no de 3,3 V. La nota "reutilizable como riel 3.3 V" que escribió Claude en `bom.csv` es incorrecta. El testbed menciona un TPS7A4700 de 3,3 V que no figura como comprado.
3. **Conteo de op-amps subió** al confirmar el buffer de salida (documento 2 §7 y §12); el BOM del repo aún dice 4 chips cuádruples.
4. **Cadena de etapas del repo desactualizada:** `AFE_EMG_Diseno.md` §3.2 sigue con INA → post-amp → HPF → LPF sin buffer.
