# Diseño del Analog Front-End (AFE) EMG → Voz — Análisis Técnico

**Proyecto:** SSI — Silent Speech Interface (STM32N6)
**Fecha:** 2026-08-07
**Estado:** Análisis / especificación de diseño (sin archivos de hardware)
**Alcance:** Revisión del BioAmp EXG Pill v1.0 como referencia, arquitectura AFE de
3 canales sEMG con Right Leg Drive (RLD) activo, reemplazando al acelerómetro
IIS3DWB como fuente del pipeline CWT → Deep Learning → vocoder.

---

## 1. Resumen ejecutivo

> **Nota de decisión (sep. 2026):** se evaluó reemplazar este AFE discreto por
> 4x BioAmp EXG Pill armados + un RLD propio, para acelerar la construcción.
> Se descartó por presupuesto: 4 Pills cuestan ~USD 138 (2x Explorer Pack) y
> el tope fijado para todo el AFE es **USD 60**. HackEEG (la otra alternativa
> "lista") cuesta USD 495–2090 y además está descontinuado. La ruta discreta
> de 3 canales de este documento es la que entra en presupuesto, y el usuario
> tiene experiencia real con diseño y validación de circuitos con op-amps —
> el riesgo de tiempo de armar/depurar analógico, que era el motivo original
> para preferir un AFE pre-armado, es bajo en este caso. **Esta decisión no
> se reabre** salvo cambio de presupuesto. Detalle en
> `docs/refactor-emg-software.md` §7.3.

El proyecto SSI evoluciona de capturar **vibraciones laríngeas** (IIS3DWB) a
capturar **señales mioeléctricas superficiales (sEMG)** de 3 grupos musculares
(laringe, mentón, comisura labial) para decodificar intención fonética. La señal
cruda (20–500 Hz) alimentará un pipeline de STFT/CWT → Conv2D → TCN → vocoder
en el STM32N6.

Este documento:

1. Revisa el **BioAmp EXG Pill v1.0** (referencia AFE open-source) y reconstruye
   su topología real desde el netlist.
2. Demuestra que su pin **"DRL" es una tierra virtual bufferizada, NO un Right
   Leg Drive activo** — decisión crítica para el escalograma.
3. Define la arquitectura AFE de 3 canales con **RLD activo verdadero**,
   alimentación 3.3 V rail-to-rail, referencia a 1.65 V y banda 20–500 Hz.

**Decisión arquitectónica obligatoria:** se implementa RLD activo (cancelación de
ruido de línea 50 Hz). Sin RLD, el bin de 50 Hz del escalograma se satura y las
Conv2D aprenden características del ruido eléctrico en vez de la firma
mioeléctrica.

---

## 2. Revisión del BioAmp EXG Pill v1.0

### 2.1 Qué es

AFE monocanal de Upside Down Labs (CERN-OHL-S-2.0 hardware, MIT software),
25.4 × 10 mm, basado en **1× TL074** (quad JFET op-amp) alimentación única
3.3–5 V. No incluye filtro dedicado (el filtrado es por software en los sketches
Arduino). v1.0 agrega ganancia (R6/RG), filtro pasabanda (R12/C5) y modo de
electrodos (JP1/JP2) configurables.

### 2.2 Topología real (verificada por netlist)

La siguiente topología fue reconstruida extrayendo la conectividad completa del
archivo `hardware/BioAmp-EXG-Pill.kicad_pcb` (netlist por pad) y contrastada con
el esquemático:

```
                     ┌──────────────────────────────────────────────┐
                     │             U1 = TL074 (TSSOP-14)             │
                     │                                              │
  J2 pin2  IN+ ──────┤ R14 1M ─┐                                    │
  J2 pin3  IN- ──────┤ R13 1M ─┼─ JP2 ──► DRL (ref)                 │
                     │   C4 1nF ┘ (diferencial RFI)                 │
                     │                                              │
                     │   Unidad A + B = INA de 2 op-amps             │
                     │   R5=R7=22K, R2=R10=220K, R6=RG(no pob.)     │
                     │   G_ina = 440 kΩ / R6 + 11                   │
                     │            (R6=440Ω → ~1000×)                 │
                     │                       │                       │
                     │                       ▼ inaOUT                │
                     │   Unidad C (salida, inversor AC)              │
                     │   inaOUT ─ R1 1K ─ C1 47µF ─ bpfIN            │
                     │   (HPF ≈ 3.4 Hz)                              │
                     │   realimentación R3 1M || C2 1nF (LPF ≈159Hz) │
                     │   + R12/C5 (BPFC) + R4 220K (JP1) conf.       │
                     │                       │                       │
                     │                       ▼ bpfOUT                 │
                     │   Unidad D = seguidor de R8/R9 (1M/1M)         │
                     │   → ampRef = VCC/2  (TIERRA VIRTUAL)          │
                     └──────────┬────────────────────────────────────┘
                                │
                     J2 pin1  DRL = R11 (0Ω) = ampRef = VCC/2
```

Componentes clave (valores confirmados por BOM):

| Componente | Valor | Función |
|---|---|---|
| U1 | TL074 | INA 2-op-amp + buffer de referencia + etapa de salida |
| R5, R7 | 22K | Red de ganancia INA |
| R2, R10 | 220K | Red de ganancia INA |
| R6 | RG (no poblado) | Resistencia de ganancia INA |
| R8, R9 | 1M | Divisor de referencia → `ampRef = VCC/2` |
| C3 | 10µF | Desacople de la referencia |
| R11 | 0Ω | **Puentea DRL a ampRef** |
| R13, R14 | 1M | Bias de entrada (retorno a DRL vía JP2) |
| R1, C1 | 1K, 47µF | Acople AC → HPF ≈ 3.4 Hz |
| R3, C2 | 1M, 1nF | Realimentación → LPF ≈ 159 Hz |
| C4 | 1nF | Cap diferencial RFI de entrada |

### 2.3 El "DRL" del pill NO es un Right Leg Drive

**Hallazgo crítico.** En el esquemático y PCB existe la net `DRL`, pero su
implementación es:

- La unidad D del TL074 es un **seguidor de voltaje** que buferiza el divisor
  R8/R9 → `ampRef = VCC/2`.
- El pin de referencia (etiquetado `DRL` en el conector J2) está **cortocircuitado
  a `ampRef` mediante R11 (0Ω)**.
- **No existe** un lazo que sensa el modo común residual (`Vcm`) de la INA, no lo
  invierte ni lo realimenta amplificado al cuerpo.

Es decir, el pill implementa una **referencia conducida** (driven reference /
tierra virtual de media tensión, de baja impedancia). Esto **ayuda** a fijar el
modo común (el cuerpo queda cerca del riel medio y la CM no satura la entrada),
pero **no cancela activamente** el ruido de línea inyectado por acoplamiento
capacitivo del cuerpo a la red eléctrica. Evidencia:

- La documentación oficial lo llama **"REF"** y recomienda: operación a batería,
  mantener ≥5 m de distancia de artefactos AC y no conectar cargadores durante la
  adquisición.
- Issue #28 del repo: para adaptar a ADC de 3.3 V se "actualiza el divisor de
  referencia para crear Ref = Vmax_ADC/2" — confirmando que es un divisor
  (tierra virtual) y no un lazo de cancelación.
- En modo 2-electrodos la propia doc advierte "bastante propenso a ruido de alta
  interferencia por falta de referencia adecuada en el cuerpo".

**Conclusión:** La topología del pill NO cumple el requisito obligatorio de RLD
activo de la especificación. Debe diseñarse un RLD verdadero.

### 2.4 Otras limitaciones del pill frente a la especificación

| Requisito SSI | BioAmp EXG Pill v1.0 | Brecha |
|---|---|---|
| Canales | 1 | Se requieren 3 → 3× pill o placa dedicada |
| RLD activo | No (solo tierra virtual) | **Crítica — rediseñar** |
| Banda 20–500 Hz | HPF 3.4 Hz / LPF ~159 Hz default | Recalibrar filtros |
| Ganancia ~1000× en 1.ª etapa | INA discreta, G=11 (default) → ~1000× (RG=440Ω) | CMRR limitado (~70–90 dB) vs INA dedicada (>100 dB) |
| InAmp médico | TL074 (JFET genérico) | INA128/AD8226/INA333 según spec |
| ADC 3.3 V STM32N6 | Salida centrada en VCC/2 (diseñada a 5 V) | Rediseñar a 1.65 V |
| TL074 a 3.3 V | Fuera de spec (TL074 clásico exige ≥10 V totales) | Op-amp rail-to-rail 3.3 V |

Nota sobre ganancia del pill: la ganancia diferencial de su INA es
`G = 440 kΩ/R6 + 11`. Con R6 sin poblar, G=11; la etapa de salida aporta
`−R3/R1 = −1000`, dando una ganancia total ≈ **11 000×** (apropiada para EEG,
µV). Para sEMG se reduce vía RG y se puentea el pasabanda. Esta ganancia enorme
demuestra que el diseño apunta a µV (EEG/EOG) y requiere recalibración para
sEMG de 0.1–5 mV.

---

## 3. Arquitectura AFE propuesta (3 canales + RLD activo)

### 3.1 Decisión de alimentación y referencia

- **Alimentación:** 3.3 V limpia (LDO de bajo ruido, p. ej. TPS7A4700 3.3 V,
  ya presente en el testbed).
- **Referencia analógica:** tierra virtual bufferizada a **1.65 V** (divisor +
  OpAmp rail-to-rail) aplicada al pin REF de los 3 INAs.
- **Op-amps:** rail-to-rail 3.3 V (TL074H/TL084H, MCP6004, OPA4313, TLV2464).
  El TL074 clásico NO opera correctamente a 3.3 V.

### 3.2 Diagrama de bloques por canal (×3)

```
Electrodos IN+/IN- (sitio muscular)
      │
      ▼
[Protección ESD/AC]  ← diodos + resistor serie 10–100kΩ + ferrita
      │
      ▼
[Filtro RFI diferencial]  ← R 1kΩ + C 470pF (cutoff ~340 kHz, ancho)
      │
      ▼
[INA dedicada]  AD8226 / INA333
      │  G1 = 100 (RG: AD8226≈499Ω, INA333≈1.01kΩ)
      │  REF = 1.65 V   ·   CMRR > 90 dB @G100
      │       │
      │       └────► bias de entrada (retorno CM)
      ▼
[Post-amplificador 2.ª etapa]  no inversor rail-to-rail
      │  G2 = 5–10  →  G_total ≈ 500–1000
      ▼
[HPF 2.º orden 20 Hz]  Sallen-Key (Butterworth/Bessel), elimina offset
      ▼
[LPF 4.º orden 500 Hz]  Sallen-Key anti-aliasing (fs ≥ 1 kHz), fase lineal
      ▼
ADC STM32N6 (ADC12, 12-bit + sobremuestreo) — 3 canales @ 1–2 kHz
```

### 3.3 Presupuesto de ganancia

sEMG superficial típico: 0.1–5 mV pico (contracciones fuertes hasta ~5 mV).
Rango ADC = 3.3 V (swing útil ±1.65 V respecto a 1.65 V).

| Señal de entrada | G_total | Salida pico a pico | Notas |
|---|---|---|---|
| 0.1 mV (reposo/ruido) | 1000 | 0.2 V | OK |
| 1 mV | 1000 | 2 V | OK |
| 5 mV (máx) | 1000 | 10 V | **Satura — requiere G menor** |

Configuración recomendada: `G1 = 100` (INA) + `G2 = 5` (post) = **G_total = 500**
con margen, y posibilidad de subir a ~1000 ajustando G2. Los RG se seleccionan al
0.1% para mantener el CMRR y la ganancia precisa entre canales (crítico para
escalogramas comparables).

### 3.4 Right Leg Drive (RLD) activo — implementación

```
            ┌──────── Vcm promedio (resistencias de promediado 100kΩ)
            │   │   │
CH1 IN+ ────┘   │   └──── CH3 IN+     (modo común de las 3 entradas)
CH2 IN+ ────────┘

  Vcm ──────► [OpAmp inversor]  ganancia −A (A ≈ 10–20)
                 │  ● realimentación con polo dominante (C ≈ 10–100 pF)
                 │  ● resistor serie de seguridad R_s ≈ 100 kΩ
                 ▼
             Electrodo de muñeca (bajo actividad muscular/óseo)
```

1. **Sensado de Vcm:** promediado resistivo del modo común de las 3 entradas
   diferenciales (técnica estándar de dispositivos de 2/3 canales; equivalente
   al Vcm de un INA de 3 derivaciones).
2. **Inversión y amplificación:** OpAmp rail-to-rail configura el bucle con
   `Gain = −A·Vcm`. A≈10–20 es suficiente para reducir el ruido de línea en
   ~20–40 dB antes de la primera etapa.
3. **Estabilidad:** se agrega polo dominante (C en paralelo con la realimentación)
   para evitar oscilación del lazo RLD.
4. **Seguridad:** resistor serie R_s (~100 kΩ) limita la corriente al paciente;
   diodos de sujeción a los rieles; el sistema opera **flotante a batería**
   (aislado galvánicamente de la red).
5. **Retorno de bias:** los pines de referencia/bias de entrada de los INAs se
   retornan al nodo RLD (equivalente funcional de R13/R14+JP2 del pill pero con
   el bucle activo), asegurando el camino DC del modo común.

**Efecto en el escalograma:** al cancelar el ruido de 50 Hz en el dominio
analógico, se evita el filtro Notch digital — que es agresivo y distorsiona la
fase de la señal útil. El RLD preserva la linealidad de fase necesaria para un
CWT coherente y descarga ciclos de reloj del STM32N6.

### 3.5 Diseño de filtros (20–500 Hz)

- **HPF 20 Hz:** elimina el voltaje de offset piel-electrodo (decenas a cientos
  de mV) y artefactos de movimiento. Segundo orden, Sallen-Key.
- **LPF 500 Hz:** anti-aliasing estricto para fs ≥ 1 kHz (el spec pide 1–2 kHz).
  Cuarto orden recomendado; respuesta **Bessel** (fase lineal / retardo de grupo
  constante) o Butterworth aceptable. Evitar elipticidad agresiva (ringing).
- **Nota sobre EMG:** la potencia dominante del sEMG está en 50–150 Hz; la banda
  completa 20–500 Hz preserva el espectro para el escalograma.
- **Jitter del ADC:** el muestreo debe ser DMA con base de tiempo común (TIMER),
  mismo esquema que el testbed actual con IIS3DWB.

### 3.6 Presupuesto de ruido y CMRR

- **INA dedicada:** CMRR > 90 dB @ G=100 (AD8226) y hasta 100 dB (INA333,
  zero-drift). vs. ~70–90 dB del discreto TL074 (dependiente del match 0.1%).
- **Ruido referido a entrada (RTI):** AD8226 @G100 ≈ ~500 nV/√Hz típico (RTI),
  INA333 ≈ ~55 nV/√Hz con chopper. Con banda 500 Hz, ruido RTI integrado
  ≈ 1–2 µVrms, muy por debajo del sEMG (0.1–5 mV).
- **Objetivo:** ruido de línea residual < –60 dB respecto a la señal EMG para que
  el bin de 50 Hz del CWT no domine el escalograma.

---

## 4. Selección de componentes

**Advertencia de abastecimiento (verificada en cotización, sep. 2026):**
los listados de INA333 en AliExpress aparecen a precios implausibles (~USD
0.03–0.24/unidad en lotes de 5) — patrón típico de IC de instrumentación
falsificado o re-marcado, no un precio real de fábrica. El AD8226 tiene
listados más creíbles (~USD 1–7/unidad según lote y vendedor), por lo que se
prefiere sobre INA333 para esta compra puntual. Mitigación al recibir:
comprar de un vendedor con historial largo y buena calificación, y validar en
banco antes de soldar en serio — medir la ganancia real de cada unidad contra
la calculada en §3.3 y descartar cualquiera que no coincida (síntoma típico
de un chip falso).

| Bloque | Componente | Justificación |
|---|---|---|
| InAmp | **AD8226** (recomendado — preferir sobre INA333, ver advertencia arriba) | Single-supply 2.7–36 V, salida rail-to-rail, G = 1 + 49.4k/RG, CMRR 80–90 dB. Cumple el "INA128/AD8226" del spec y opera a 3.3 V. |
| InAmp alt. | **INA333** | Rail-to-rail I/O, 1.8–5.5 V, zero-drift, CMRR 100 dB @G≥10, G = 1 + 100k/RG. Mejor para 3.3 V. |
| InAmp descartado | **INA128** | Requiere ≥4.5 V de alimentación simple — **NO opera a 3.3 V** (nota de corrección al spec). |
| Op-amps genéricos | TL074H / MCP6004 / OPA4313 | Rail-to-rail 3.3 V para post-amp, filtros, referencia y RLD. |
| Referencia 1.65 V | Divisor + seguidor rail-to-rail + cap 10µF | Tierra virtual de baja impedancia. |
| RLD | OpAmp rail-to-rail + R_s 100kΩ + C polo dominante | Lazo de cancelación CM. |
| Protección | Diodos schottky a rieles + resistor serie + ferrita | ESD y artefactos AC. |
| Filtros | Sallen-Key 2.º/4.º orden (Bessel) | 20 Hz HPF / 500 Hz LPF. |

---

## 5. Interfaz con el STM32N6 (reemplazo del IIS3DWB)

- **ADC:** ADC12 del STM32N6 (12-bit nativo), 3 canales, muestreo DMA a 1–2 kHz,
  base de tiempo TIMER común (mismo diseño que el flujo I2S del mic).
- **Sobremuestreo:** oversampling + promedio para mejorar la resolución efectiva
  (~14+ bits) si se requiere mayor rango dinámico del escalograma.
- **Salida de los 3 canales:** centrada en 1.65 V, swing ±1.65 V, impedancia de
  salida baja (buffer) → conexión directa al ADC (sin divisor).
- **Sincronización:** los 3 canales EMG comparten timestamp con el mic de ground
  truth (**INMP441**, ya decidido y adquirido — ver `docs/refactor-emg-software.md`)
  vía TIMER 1 MHz.

### 5.1 Formato de trama propuesto (extensión del .ssr)

```
Byte 0-1:  Sync 0xAA 0x55
Byte 2:    Tipo 0x03 = EMG
Byte 3:    Flags
Byte 4-7:  Timestamp µs
Byte 8-9:  Data Length
Byte 10+:  N muestras × 3 × int16 (CH1, CH2, CH3)
```

Compatible con el formato existente (`docs/architecture.md` del testbed): se
agrega el frame tipo EMG al lado de ACC (0x01) y AUDIO (0x02). En la etapa de
desarrollo, EMG reemplaza a ACC como fuente del CWT.

---

## 6. Integración con el pipeline de Deep Learning

```
AFE EMG (3ch, 20-500Hz, RLD activo) ──ADC DMA──┐
                                               ├── STM32N6 (M55) ──► CWT Morlet
Mic INMP441 (ground truth) ───I2S DMA───────┘        (3 escalogramas apilados)
                                                        │
                                                        ▼
                                Conv2D×3 (paralelo) ──► TCN ──► FC ──► latente
                                                                       │
                                                                       ▼
                                                              Vocoder → voz
```

- Los 3 escalogramas (uno por canal) se concatenan/apilan como entrada 3D de las
  Conv2D paralelas, tal como define el documento de especificaciones.
- El RLD garantiza un bin de 50 Hz limpio → las Conv2D aprenden la firma
  mioeléctrica, no el ruido de red.

---

## 7. Riesgos y decisiones pendientes

| # | Riesgo / decisión | Mitigación |
|---|---|---|
| 1 | Aislamiento paciente (IEC 60601) | Sistema flotante a batería; RLD con R_s y diodos; evaluación de normativa para prototipo. |
| 2 | Posición de electrodos en rostro (artefactos de habla, movimiento) | Electrodo único de referencia en muñeca; validación anatómica (laringe/mentón/comisura). |
| 3 | CMRR entre canales (match de RG) | RG 0.1%; calibración de ganancia por canal en firmware. |
| 4 | Oscilación del lazo RLD | Polo dominante + resistor serie; validación en prototipo. |
| 5 | Ruido de contacto (electrodos Ag/AgCl pregeliados) | Preparación de piel (Nuprep + alcohol, ver doc del pill). |
| 6 | Saturación con contracciones fuertes | Ganancia configurable (G_total 500 default, ajuste a 1000). |
| 7 | Reemplazo del IIS3DWB en firmware | Nuevo frame 0x03 EMG; migrar export.py CWT al dominio EMG. |

---

## 8. Referencias

- Upside Down Labs, *BioAmp EXG Pill v1.0* (repo local + docs oficiales).
- Analog Devices, *AD8226* (Single-Supply, Rail-to-Rail Low Cost In-Amp, datasheet).
- Texas Instruments, *INA333* (Micropower Zero-Drift Rail-to-Rail In-Amp, datasheet).
- Texas Instruments, *INA128* (datasheet — alimentación mínima 4.5 V simple).
- Analog Devices, *AN-837 — DRL / driven-reference design*.
- Especificación técnica SSI: "Interfaz EMG a Voz mediante Deep Learning y Vocoder (STM32N6)".
- `ssr-testbed/docs/architecture.md` — formato de trama y pipeline actual.
