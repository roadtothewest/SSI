# CONTEXTO_CLAUDE.md — Traspaso completo de la sesión Claude Code (18–26 sep 2026)

Documento maestro para retomar el proyecto en otro PC (y para simular el AFE en PLECS). Es autosuficiente: el historial de chat y la memoria de Claude Code **no** se trasladan entre PCs (viven en `~/.claude/` del PC viejo).

## 0. Cómo retomar

```bash
git clone --recurse-submodules https://github.com/roadtothewest/SSI.git
# si ya lo clonaste sin submódulos:
git submodule update --init
```

- Repo **privado**, rama `master`. `BioAmp-EXG-Pill/` es un **submódulo** (upstream `upsidedownlabs/BioAmp-EXG-Pill`, commit `86bb1f4`), solo referencia.
- Con Claude Code en el PC nuevo: abrir `claude` en la raíz del repo y pedirle que lea primero este archivo.
- Para reanudar *esta misma* sesión habría que copiar `~/.claude/projects/-home-ludicolo-SSI/` del PC viejo y tener el repo en la misma ruta (`/home/ludicolo/SSI`); no verificado, es opcional.
- Orden de lectura: este archivo → `docs/afe-emg/gemini_2_diseno_afe.md` → `docs/afe-emg/gemini_1_contexto_y_decisiones.md` → `docs/afe-emg/AFE_EMG_Diseno.md` → `docs/refactor-emg-software.md` → `README.md`.

**Leyenda de confianza** (misma que los docs gemini):
[VERIFICADO-DS] leído en datasheet (AD8232 Rev. A, págs. 16–23, ahora en `datasheets/AD8232.PDF`) · [REPO] de documentos del repo · [WEB] resumen automático de web · [MEMORIA] citado de memoria, verificar · [USUARIO] decisión del usuario · **[CÁLCULO]** cálculo hecho al preparar este traspaso (revisar).

---

## 1. Resumen ejecutivo

- **Proyecto:** SSI / AuraVox — estación de captura sincronizada sEMG + voz y generador de corpus. Muestra TECH 2026: **15 oct 2026** (19 días desde el 26 sep).
- **Mantra [USUARIO]:** "matar dos pájaros de un tiro": (1) demostrar causalidad sEMG → fonemas; (2) crear la plataforma que genera el dataset masivo mínimo para que el pipeline generalice.
- **Hardware:** AFE sEMG **discreto propio, 4 canales + RLD**, perfboard, tope **USD 60**. INA333 + 6× MCP6004 (26 sep).
- **Cadena por canal acordada:** protección → RFI → INA → **HPF → G2** → LPF 4º orden → **buffer** → ADC (1 ADC, 4 canales, scan+DMA).
- **Micrófono:** INMP441 (I2S) candidato, **no comprado**.
- **Simulación:** hecha en **LTspice** con los 4 canales, 9 electrodos y RLD (`sim/ltspice/`, resultados en `docs/afe-emg/resultados_simulacion.md`). El plan PLECS de §6 queda como referencia.
- **Riesgos top:** (a) seguridad con alimentación de red (necesita aislamiento); (b) hallazgos H1–H4 de §5 (RFI+protección y sensado del RLD, tal como están, degradan señal/CMRR); (c) presupuesto (6 chips cuádruples, no 4); (d) LDO comprado es 3,0 V; (e) MCU del testbed sin decidir (NUCLEO-H723ZG vs STM32N6).

---

## 2. Estado del repositorio

### 2.1 Commits de esta sesión

| Hash | Contenido |
|---|---|
| `82aec25` | Pivot a sEMG (README, bom.csv, `AFE_EMG_Diseno.md`, nuevo `refactor-emg-software.md`) |
| `01b267f` | Correcciones: mic no comprado, AFE a 4 canales, HMI multi-pestaña, verificación WORLD |
| `0abf5f4` | Traspaso a Gemini (`gemini_1_…`, `gemini_2_…`) |
| (este) | Todo el contenido local + este archivo + correcciones de BOM y diagrama |

### 2.2 Qué se agregó en este push

- Todo lo que estaba sin trackear: `BIOAMP*.png`, `datasheets/INMP441.PDF`, `papers/`, `red_mel.txt`, `respeuesta_iagoogle.md`, `sprints/sprint-1/{DL,clave}.md`, `ssr-testbed/pc-tools/ssr-roundtrip/`.
- `BioAmp-EXG-Pill/` como submódulo (162 MB, repo git propio; no se vendorizó).
- Copiados desde `~/Descargas`: `datasheets/AD8232.PDF` y `docs/AuraVox.pdf` (propuesta original).
- `.gitignore`: `__pycache__/`, `*.pyc`, `*.lck` (KiCad), `.~lock.*#` (LibreOffice).
- `bom.csv`: corregida la nota del LDO (es 3,0 V, no sirve como riel 3,3 V) y los op-amps cuádruples 4 → 6.
- `AFE_EMG_Diseno.md` §3.2: diagrama al orden acordado (HPF antes de G2, con buffer) + aviso hacia §5 de este archivo.

### 2.3 Mapa del repo

| Ruta | Qué es | Estado |
|---|---|---|
| `README.md` | Descripción, pipeline, estado, roadmap por sprints | Vigente |
| `CONTEXTO_CLAUDE.md` | Este traspaso | Vigente |
| `bom.csv` | BOM (INMP441 candidato, AFE 4 canales: 4× INA333, 6× MCP6004) | Vigente, estimado |
| `docs/afe-emg/AFE_EMG_Diseno.md` | Diseño del AFE (análisis netlist del BioAmp §2, arquitectura §3, interfaz §5) | Parcial: ver §5 |
| `docs/afe-emg/gemini_1_contexto_y_decisiones.md` | Contexto y decisiones (snapshot 19-sep) | Vigente |
| `docs/afe-emg/gemini_2_diseno_afe.md` | Diseño técnico, debates, errores, 15 puntos abiertos | Vigente; complementa §5–6 |
| `docs/refactor-emg-software.md` | Mantra, causalidad, HMI multi-pestaña, WORLD, checklist de refactor | Vigente |
| `docs/AuraVox.pdf` | Propuesta original (2 págs.) | Referencia |
| `datasheets/` | INMP441, AD8232, INA333, MCP6004 | Referencia |
| `papers/` | Freeman_RLD.pdf (RLD); `old/` sEMG continuous speech, etc. | Referencia |
| `BioAmp-EXG-Pill/` | Submódulo upstream (KiCad, docs) | Referencia |
| `BIOAMP.png`, `BIOAMP1.png` | Capturas del BioAmp Pill | Referencia |
| `sprints/sprint-1/` | Notas de arquitectura DL (Conv2D→TCN→WORLD), NPU STM32N6; `gpt-ups-pelao.md` (batería) | Vigente (adaptadas a 4 canales sEMG) |
| `red_mel.txt` | Link al model zoo de ST (yamnet) | Referencia |
| `respeuesta_iagoogle.md` | Notas de telemetría para dron, **no relacionadas** con SSI | Ajeno |
| `ssr-testbed/firmware/` | Firmware STM32 (audio I2S + USB-CDC) | **Falta captura EMG** (ADC+DMA, frame 0x03) |
| `ssr-testbed/pc-tools/ssr-ingest` (Go), `ssr-export` (Python CWT), `ssr-inspect`, `ssr-replay` | Herramientas PC | Leen el frame EMG 0x03; `export.py`: falta ventana/hop + lag |
| `ssr-testbed/pc-tools/ssr-roundtrip/` | Round-trip de audio Mel+Griffin-Lim con PESQ/STOI | Extender a WORLD (`pyworld`) |
| `ssr-testbed/docs/{architecture,pinout,pipeline}.md` | Testbed sEMG; pines del ADC pendientes | Bloqueado por decisión de MCU |
| `sim/ltspice/` | Netlists, esquemáticos `.asc` (4 canales), modelos y scripts de la simulación del AFE | Vigente |
| `BASES_MT_2026.pdf`, `RoadmapSSI.xlsx` | Bases del concurso, roadmap | Referencia |

---

## 3. Decisiones (consolidado)

| Tema | Decisión | Estado |
|---|---|---|
| Sensor | sEMG diferencial | Cerrado |
| Canales | 4: CH1 submentoniano, CH2 platisma, CH3 labio inferior, CH4 laringe (canal de control del confusor F0) | Cerrado |
| Electrodos | 9 (8 señal + 1 RLD); ver H2 si se agrega retorno de bias | Cerrado |
| AFE | Discreto propio, perfboard "Ruta B". BioAmp ×4 (~USD 138), HackEEG (descontinuado), ADS129x pelado (TQFP-64, sin breakout), ADS1292R (1 canal útil) descartados | Cerrado |
| ADS1299 | Técnicamente superior; ruta para v2 post-Muestra | Pospuesto |
| Presupuesto | Tope USD 60 [USUARIO]; estimado 4 canales CLP 36–65 mil + 2 cuádruples extra | Riesgo |
| Orden de etapas | INA → HPF → G2 → LPF → buffer | Cerrado [USUARIO] |
| Buffer de salida | Sí | Cerrado [USUARIO] |
| Ferrita | No | Cerrado [USUARIO] |
| INA | AD8226 (abastecimiento más seguro) o INA333 (CMRR/bias mejores); ver H3 | Abierto |
| G1 | 100 en el repo; se recomienda simular 10–100 (ver §6 T3) | Abierto |
| Micrófono | INMP441 candidato, no comprado; confirmar escuchando muestras | Abierto |
| Alimentación | Usuario quiere red + notch "post AC/DC"; exige aislamiento galvánico | Abierto (seguridad) |
| MCU testbed | NUCLEO-H723ZG (docs testbed) vs STM32N6570-DK (README/AFE) | Abierto |
| RLD sensado | Repo: resistores sobre entradas; ver H2 | Abierto |

---

## 4. Diseño del AFE — valores de partida para simular

Todos los valores de esta sección son **[CÁLCULO] propuestas de partida** salvo indicación. Alimentación 3,3 V única, VREF = 1,65 V.

### 4.1 Cadena y bloques compartidos

```
Electrodo± ─[Rs]─┬─(clamps a rieles)─[RFI]─► INA (G1, REF=VREF) ─► HPF SK 20 Hz ─► G2 ─► LPF A (Q bajo) ─► LPF B (Q alto) ─► Buffer ─[RC]─► ADC
                 (por línea)
Compartido: VREF (divisor + seguidor + 10 µF) · RLD (lazo lateral → electrodo muñeca vía R de seguridad) · 1 ADC scan+DMA
```

### 4.2 Tabla de valores

| Bloque | Componentes | Valores de partida | Notas |
|---|---|---|---|
| Protección | Rs por línea + diodos clamp baja fuga (BAV199/FJH1100 [VERIFICADO-DS p.19]) | Rs parametrizar {47k, 100k, 330k} | AD8232: corriente al sujeto < 10 µA ⇒ Rs ≥ V/10 µA ≈ 330 kΩ a 3,3 V [VERIFICADO-DS p.19]; repo decía 10–100 kΩ. Ver H1, H3 |
| RFI | Ccm por línea a GND, Cdiff entre líneas post-R | **Ccm = 47 pF C0G ≤ 5 %, Cdiff = 100–220 pF C0G**; R de 1 kΩ opcional | **Reemplaza** 1k/470p/Cdiff≈4,7 nF (ver H1). AD8232 usa los R de protección como R del filtro RFI [VERIFICADO-DS p.20] |
| INA | AD8226 o INA333, RG pines 1–8 | G = 1 + 49,4k/RG (AD8226) · G = 1 + 100k/RG (INA333) [REPO] | G1=100: RG 499 Ω / 1,01 kΩ · G1=20: RG 2,61 kΩ / 5,23 kΩ. RG 0,1 %. Pinout [MEMORIA]: 1,8 RG · 2 −IN · 3 +IN · 4 −VS · 5 REF · 6 OUT · 7 +VS |
| HPF | Sallen-Key 2º orden, ganancia unitaria, Butterworth | C1 = C2 = **100 nF** (film), Ra (nodo→salida) = **56,2 kΩ**, Rb (entrada + → **VREF**) = **113 kΩ** | f0 ≈ 19,97 Hz, Q ≈ 0,709. Ecuaciones: ω0 = 1/(C√(Ra·Rb)), Q = ½√(Rb/Ra). Rb a VREF recentra la salida en 1,65 V |
| G2 | No inversor, Rg a VREF | G1=100 ⇒ G2=5: Rg 10k, Rf 40,2k · G1=20 ⇒ G2=25: Rg 10k, Rf 240k | Vout = VREF + (1+Rf/Rg)·v_ac |
| LPF A | SK unit. gain, R1=R2=R; C1 realim., C2 a VREF | Butterworth Q=0,5412: **R = 29,4 kΩ, C1 = 12 nF, C2 = 10 nF** → f0 ≈ 494 Hz, Q ≈ 0,548 | Q = ½√(C1/C2), f0 = 1/(2πR√(C1C2)) |
| LPF B | ídem | Butterworth Q=1,3066: **R = 54,9 kΩ, C1 = 15 nF, C2 = 2,2 nF** → f0 ≈ 504 Hz, Q ≈ 1,306 | Sección de Q alto al final (orden por Q creciente [MEMORIA]) |
| LPF alt. Bessel | 2 secciones | fc 500 Hz: f0₁ = 709,6 Hz Q 0,5219 · f0₂ = 795,6 Hz Q 0,8055 [MEMORIA tabla ADI] | Fase lineal, corte más suave |
| Buffer | Seguidor | — | Aísla el SK del sample-and-hold |
| RC al ADC | Serie + shunt C0G pegado al pin | R 100–470 Ω, C 1–10 nF | Según guía ADC de ST (AN2834 [MEMORIA]) |
| VREF | Divisor 2×10k + 10 µF + seguidor | corte ≈ 3,2 Hz | Idealmente derivar de la referencia del ADC (ratiométrico) [VERIFICADO-DS p.17] |
| RLD | Promedio de Vcm → integrador inversor (no inv. a VREF) → R seguridad → electrodo muñeca | Estilo AD8232: R_in efectiva 150 kΩ + C_int 1 nF ⇒ cruce ≈ 1 kHz, ≈26 dB a 50 Hz [VERIFICADO-DS p.17]. Con N resistores de promedio en paralelo: R_avg = N × 150k (4 ⇒ 600 kΩ c/u). R seguridad ≥ 330 kΩ | Sensado: ver H2. Ganancia de lazo < 1 en cualquier otro polo (cuerpo, R seguridad) [VERIFICADO-DS p.23] |
| Op-amps genéricos | OPA4313 (recomendado) o MCP6004 [MEMORIA] | 22 en total = 6 cuádruples | Rail-to-rail I/O a 3,3 V, GBW ≥ 1 MHz, offset bajo, buena recuperación de sobrecarga. Evitar TL074 clásico |

Conteo: 5 op-amps/canal (HPF, G2, LPF A, LPF B, buffer) × 4 = 20, + RLD + seguidor VREF = **22 → 6 chips cuádruples** (+ 4 INAs = 10 chips). Fusionar G2 con un SK con ganancia bajaría a 18 / 5 chips (no acordado).

### 4.3 Ganancia y rango

- G_total objetivo ≈ 500 (G1·G2). ADC 12 bit / 3,3 V ⇒ 0,8 mV/LSB. 100 µV × 500 = 50 mV ≈ 62 LSB; 5 mV × 500 = 2,5 V pp (cabe).
- INA con G1 = 100 satura con ≈ ±15 mV diferenciales (offset + señal), suponiendo ±1,5 V útiles [CÁLCULO; verificar swing real].
- 100 µV–100 mV (60 dB) no cabe con ganancia fija: los artefactos grandes se dejan saturar y se detectan por software.
- Verificar el "diamond plot" (salida vs modo común) del INA elegido a 3,3 V única [MEMORIA: concepto estándar de INA de 3 op-amps].

---

## 5. Hallazgos al preparar el traspaso (NO discutidos en la conversación)

Varios **corrigen respuestas de Claude en la conversación**. Revisar antes de simular.

**H1 — El filtro RFI no puede diseñarse aparte de la resistencia de protección.** El corte "≈340 kHz" (1 kΩ·470 pF) ignora que Rs (y la impedancia del electrodo) está en serie. Con R_total = Rs + 1k:
- Diferencial: f_d = 1/(2π·R·(2·Cdiff + Ccm)). Con Rs = 100k, Cdiff = 4,7 nF, Ccm = 470 pF ⇒ **f_d ≈ 160 Hz**, dentro de la banda sEMG (con 330k ≈ 49 Hz).
- Modo común → diferencial por desbalance de Ccm: ≈ 2π·f·R·ΔC. Con Rs = 100k, Ccm = 470 pF ±10 % a 50 Hz ⇒ ≈ −57 dB (CMRR efectivo limitado por los capacitores, no por el INA).
- Con Ccm = 47 pF (5 %) y Cdiff = 220 pF, Rs = 100k: f_d ≈ 3,2 kHz (−0,1 dB a 500 Hz), f_cm ≈ 33 kHz, conversión ≈ −82 dB. Con Rs = 330k usar Cdiff ≈ 100 pF (f_d ≈ 2 kHz).

**H2 — Sensar el modo común del RLD con resistores sobre las entradas carga las entradas.** Un resistor de 100 kΩ desde cada entrada al nodo sumador (tierra virtual) baja la impedancia de entrada de ~GΩ a ~100 kΩ:
- con Rs y el electrodo en serie forma un divisor (≈ −6 dB de señal);
- si se conectan IN+ e IN− del mismo canal ("usar los 8", como recomendó Claude) quedan ~200 kΩ entre las entradas de cada par;
- el desbalance de impedancias de electrodo convierte modo común en diferencial (CMRR efectivo ≈ 20·log(Z_in/ΔZ_e): 100k/10k ⇒ ~20 dB).
- Alternativas: **RG partido en dos mitades y usar el punto medio** (Vcm ya buffereado por la etapa de entrada del INA; circuitos ECG de las hojas de datos INA128/AD620 [MEMORIA]; verificar en el INA elegido que ese nodo refleje Vcm y su desplazamiento DC, y en INA333 si hay rizado de chopper); o resistores de promedio ≥ 10 MΩ; o buffers por entrada. Esto reemplaza el consejo de la conversación de tomar el nodo "después de la protección" y de "usar los 8".

**H3 — Rs grande + INA de entrada bipolar.** AD8226 tiene corriente de bias del orden de decenas de nA [MEMORIA] ⇒ con 330 kΩ, mV de offset y desbalance; INA333 (CMOS, pA [MEMORIA]) lo hace despreciable. Ruido térmico de Rs (2 líneas, 20–500 Hz) [CÁLCULO]: 2×100k ⇒ 57,6 nV/√Hz ⇒ 1,26 µVrms; 2×330k ⇒ 105 nV/√Hz ⇒ 2,29 µVrms (frente a 100 µV mínimos).

**H4 — Retorno de bias / REF.** `AFE_EMG_Diseno.md` §3.4 punto 5 dice retornar "los pines de referencia/bias de los INAs" al nodo RLD. El pin **REF del INA va a VREF**, nunca al RLD. El retorno de bias de las entradas lo da el cuerpo (llevado por el electrodo RLD) o resistores de alto valor (10 MΩ) a VREF/RLD como en el AD8232 [VERIFICADO-DS pp.18–19]. Con pull-ups de 10 MΩ, un electrodo desconectado lleva la entrada a un riel de forma determinista ⇒ estado "desconectado" visible en la HMI (lo que pidió el usuario).

**H5 — Muestreo vs LPF.** Con LPF de 500 Hz, fs = 1 kHz no da antialiasing (Nyquist = corte). Butterworth 4º orden: −24 dB en fs/2 con fs = 2 kHz; con **fs = 8 kHz por canal, −72 dB en Nyquist** (= rango de 12 bits) [CÁLCULO]. Recomendación: sobremuestrear a ≥ 8 kHz/canal (32 kS/s total, trivial para el ADC) y decimar digitalmente a 2 kHz antes de la CWT.

**H6 — Alimentación.** LDO comprado = 3,0 V. Opciones: comprar LDO 3,3 V de bajo ruido o correr el AFE a 3,0 V con VREF = 1,5 V (se pierde ~9 % del rango si el ADC usa 3,3 V). Separar el riel analógico del digital de la placa del MCU.

**H7 — Seguridad con red.** Hay electrodos en cara y cuello. El spec original: captura solo a batería (o notebook a batería / aislador USB para el ST-LINK; ojo con HDMI de la Pi). Un notch no reemplaza el aislamiento galvánico.

**H8 — Encapsulados.** AD8226ARMZ es MSOP-8 y los cuádruples SOIC/TSSOP (SMD); la "Ruta B" es perfboard through-hole ⇒ adaptadores SMD→DIP o variantes DIP.

---

## 6. Plan de simulación en PLECS

**Advertencia [MEMORIA, verificar en tu versión]:** PLECS modela op-amps de forma ideal/conductual (ganancia, límites de salida) y no trae macromodelos SPICE de AD8226/INA333/OPA4313. Para GBW real, ruido, swing real y recuperación de sobrecarga, contrastar después en LTspice (modelos ADI) o TINA-TI (modelos TI).

### 6.1 Modelos a construir

- **Electrodo:** R_e ∥ C_e en serie con una fuente DC de media celda por electrodo. Desbalance de prueba 51 kΩ ∥ 47 nF en una línea (prueba de CMRR estilo IEC 60601-2-27 [MEMORIA]).
- **Cuerpo:** fuente de modo común de 50 Hz (barrer 0,1–10 V) acoplada a todos los electrodos; opcional C cuerpo–red ~2–3 pF y cuerpo–tierra ~200 pF [MEMORIA].
- **sEMG:** ruido filtrado 20–500 Hz, 0,1–5 mV, en ráfagas (habla on/off); artefacto de movimiento 0,1–10 Hz hasta decenas de mV.
- **INA:** de 3 op-amps ideales para poder usar el punto medio de RG (H2): dos seguidores de entrada con RG entre sus entradas inversoras y R1 de realimentación (R1 = 24,7 kΩ equivale a 1+49,4k/RG, AD8226; R1 = 50 kΩ equivale a INA333), y amplificador diferencial de 4 R iguales con referencia a VREF. Desajustar esas 4 R (0,01–0,1 %) para fijar CMRR ~80–100 dB. Límites de salida 0,1–3,2 V. Alternativa simple: fuente controlada Vout = VREF + G1·Vd + G1·Vcm/CMRR con saturación.
- **Op-amps:** ideales con ganancia finita, un polo (GBW 1–3 MHz) y límites de salida 0–3,3 V.
- **Protección:** diodos a rieles tras Rs.
- **ADC:** muestreo (zero-order hold) + cuantización de 12 bit en 0–3,3 V, fs parametrizable.

### 6.2 Pruebas y criterios

| # | Prueba | Criterio de aceptación |
|---|---|---|
| T1 | Punto de operación DC | Nodos de señal ≈ 1,65 V en reposo |
| T2 | Barrido AC completo | Ganancia de banda ≈ G_total; −3 dB ≈ 20 Hz y 500 Hz; 40 dB/déc (HPF) y 80 dB/déc (LPF); retardo de grupo Bessel vs Butterworth |
| T3 | Offset de electrodo (DC 5, 15, 50, 300 mV) | Elegir G1 máximo sin saturar el INA con el offset esperado; tiempo de recuperación tras escalón |
| T4 | 50 Hz modo común + desbalance de electrodo | 50 Hz en salida con/sin RLD; comparar sensado por resistores vs punto medio de RG (H2); efecto de Rs y caps RFI (H1) |
| T5 | Estabilidad del lazo RLD | Margen de fase aceptable; barrer C_int 0,47–4,7 nF y R de seguridad 100k–1M con modelo de cuerpo |
| T6 | Artefacto de 100 mV (ráfaga) | Tiempo hasta volver a zona lineal |
| T7 | Rango dinámico: 100 µV y 5 mV a 100 Hz | Sin recorte; códigos ADC suficientes sobre el ruido |
| T8 | Aliasing: tonos cerca de fs/2 | fs = 2 kHz vs 8 kHz + decimación (H5) |
| T9 | Falla: riel en la entrada del INA | Corriente hacia el electrodo < 10 µA |
| T10 | Electrodo desconectado | Comportamiento con/sin pull-ups 10 MΩ (H4); umbral detectable por software |
| T11 | Monte Carlo (Ccm 5 %, RG 0,1 %, R 1 %) | Dispersión de ganancia entre los 4 canales y CMRR peor caso |

### 6.3 Decisiones que debe cerrar la simulación

G1 (y G2) · Rs · Ccm/Cdiff · método de sensado del RLD y valores del integrador · Bessel vs Butterworth · fs y sobremuestreo · método de recuperación de sobrecarga · INA (AD8226 vs INA333).

Primer paso en banco después: **1 canal completo validado** antes de replicar los otros 3.

---

## 7. Software y firmware pendiente (resumen de `docs/refactor-emg-software.md`)

- Firmware: agregar la captura EMG de 4 canales ADC+DMA, frame `0x03` (N × 4 × int16) con timestamp µs; `sync_timer.c` se reutiliza. Bug previo a corregir: `frame.c` usa `active_buf`, que es `static` en `inmp441.c`, y el driver del micrófono usa los callbacks de TX de I2S en vez de los de RX.
- `ssr-ingest` (Go): frame `0x03` ya reconocido; no caerse ante desconexiones del AFE. `storage/writer.go` no compila (errores previos: `sha256.Sum256` usado como tipo, `WriteFrame` duplicado).
- `ssr-export` (Python): ya lee el frame EMG (4 canales, `--fs-emg`, CWT por canal); falta separar `window_ms` (≥ 50–100 ms) de `hop_ms` (5/10/20 ms); correlación cruzada con lag.
- `ssr-roundtrip`: agregar ruta `pyworld` (dio/harvest, cheaptrick, d4c, synthesize) y comparar con Mel+Griffin-Lim vía PESQ/STOI.
- HMI multi-pestaña: por canal (desconectado / sin habla / con habla), comparación CWT STM32 vs Go, causalidad, round-trip WORLD.
- Causalidad: lag sEMG→audio (decenas de ms), controles del confusor laríngeo (articulación silenciosa, vocal sostenida, signo del lag), Granger si alcanza.
- Esquema de dataset: cada tupla con el lag medido o datos crudos para recalcularlo.
- Bloqueado: pinout del testbed hasta decidir MCU (H723ZG vs N6).

---

## 8. BOM y presupuesto

`bom.csv`: INMP441 candidato (CLP ~1.000, no comprado); AFE 4 canales: 4× INA333, **6** MCP6004-I/P, pasivas, perfboard, 9 electrodos (reusables preferidos). Estimado CLP 36–65 mil (≈ USD 38–68) **más** 2 cuádruples extra y adaptadores SMD→DIP ⇒ probablemente supera USD 60. Riesgo de falsificación en AliExpress (sobre todo INA333 a precios de centavos): validar ganancia de cada unidad en banco.

## 9. Micrófono

INMP441 (I2S, SNR 61 dBA, −26 dBFS, 24 bit). Evidencia [WEB]: comparativa atomic14 vs SPH0645 (https://www.youtube.com/watch?v=3g7l5bm7fZ8), ICS-43434 como alternativa (https://www.atomic14.com/videos/posts/VVGln_-XEgI). Acción: **escuchar las muestras** antes de comprar; al recibir, probar con tono conocido.

## 10. Errores de Claude en la sesión (no repetir)

1. Afirmó "INMP441 comprado y validado" (falso; corregido).
2. Cerró canales en 3 como decisión propia (el usuario reabrió a 4).
3. "Fast Restore del AD8232 ≈ diodos": falso, usa comparador de ventana + switches que ponen 10 kΩ en paralelo con los R del HPF [VERIFICADO-DS pp.17–18].
4. Llamó "sumador" al no inversor con Rg a VREF.
5. Confundió al usuario reutilizando nombres Rf/Rg cerca del RLD.
6. Propuso un capacitor de acople extra tras el INA (retirado por el reorden).
7. Conteo de op-amps (dijo 5 cuádruples; son 6).
8. Nota "LDO reutilizable como 3,3 V" (es 3,0 V; corregido en BOM).
9. Corte RFI 340 kHz ignorando Rs (H1), sensado RLD sobre entradas y "usar los 8" (H2), REF al RLD en el doc (H4).
10. Citó de memoria pinout del INA, CMRR, SLOA058, OpenBCI sin verificar.

## 11. Cómo trabajar con el usuario (para la próxima sesión)

- Español de Chile, directo. Diseñador analógico con experiencia en op-amps: quiere conexiones exactas y números, no generalidades.
- Responder **solo lo preguntado** cuando lo pide; sin relleno ni repetir contexto.
- Verificar contra el datasheet real antes de afirmar equivalencias; decir explícitamente qué es de memoria.
- Operaciones git pedidas: hacerlas de inmediato, sin rodeos.
- No cerrar decisiones que son del usuario (canales, presupuesto, compras).
- Atribución de commits: línea `Co-Authored-By` de Claude (y `Claude-Session` si la sesión lo indica).

## 12. Referencias

- `datasheets/AD8232.PDF` (Rev. A): Architecture Overview p.16, RLD p.17, Fast Restore pp.17–18, Input Protection p.19, RFI p.20, Eliminating Electrode Offsets / HPF pp.21–22, LPF y ganancia / manejo del ADC / electrodo conducido p.23.
- `papers/Freeman_RLD.pdf` (RLD).
- Winter & Webster, "Driven-right-leg circuit design", IEEE TBME 1983 [MEMORIA]. Datasheets ADS1298/ADS1299 sección RLD; esquemático OpenBCI Cyton [MEMORIA]. Hojas de datos INA128 / AD620 (circuitos ECG con RG partido) [MEMORIA]. TI SLOA058 "Single-Supply Op Amp Circuit Collection" [MEMORIA]. ST AN2834 (precisión ADC STM32) [MEMORIA].
- Crowd Supply: BioAmp EXG Pill, HackEEG (enlaces en `docs/afe-emg/gemini_1_contexto_y_decisiones.md`).
