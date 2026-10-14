# Arquitectura del Sistema — SSI

## Visión General

SSI (Silent Speech Interface) es un sistema de reconstrucción de voz a partir de
la actividad eléctrica de los músculos del habla (sEMG de superficie). El
proyecto tiene dos etapas:

1. **Plataforma de Desarrollo** — Captura sincronizada (sEMG 4 canales + audio) para
   generar dataset de entrenamiento. Usa NUCLEO-H723ZG + sensores + PC.
   _No hay inferencia embebida._

2. **Producto Final** — Sistema autónomo 100% embebido en STM32N6 (M55 + NPU)
   con parlante integrado. Sin PC, portátil, uso diario.

---

## Etapa 1: Plataforma de Desarrollo (Actual)

### Pipeline

```
AFE sEMG 4ch ──ADC DMA (2 kHz/ch)──┐
                                    ├── MCU ──USB CDC──→ PC (ssr-ingest) → .ssr → .npz → Colab
INMP441 ──I2S DMA (16 kHz)──────────┘
                                        TPS7A4700 LDO ── alimentación limpia sensores
```

### Bloques Funcionales

#### 1. Front-end sEMG (AFE discreto, 4 canales)

- 4 canales diferenciales, 9 electrodos (4 pares + RLD), 4 salidas a ADC
- Por canal: protección ESD + filtro RFI → INA333 (G1 = 20) → HPF 20 Hz →
  G2 = 25 → LPF Butterworth 4º orden 500 Hz → buffer
- Ganancia total 503 (54 dB), banda 20–500 Hz, alimentación única 3.3 V, VREF 1.65 V
- Right Leg Drive compartido, sensado en el punto medio de RG de los 4 canales
- Diseño, valores y simulación: `docs/afe-emg/` y `sim/ltspice/`

#### 2. Sensor de Audio de Referencia (INMP441)

- Micrófono MEMS digital con interfaz I2S
- Salida: I2S 24-bit (sin codec externo)
- Frecuencia de muestreo: 16 kHz
- SNR: 61 dBA
- Sensibilidad: -26 dBFS (94 dB SPL)
- Conexión directa al periférico SAI del STM32

#### 3. Unidad de Procesamiento (STM32H723ZG — NUCLEO)

| Periférico | Configuración |
|---|---|
| ADC | 4 canales, 2 kHz por canal, disparo por timer, DMA circular ping-pong (pines según MCU, pendiente). |
| I2S3 | 16 kHz, 24-bit, DMA circular. Buffer de 128 muestras. |
| TIM2 | Base de tiempo común a 1 MHz. Ambos flujos DMA comparten el mismo timer. Cada frame lleva timestamp en µs. |
| USB OTG_HS | CDC Virtual COM Port, Bulk endpoint de 512 bytes. Streaming sin pérdida de paquetes. |

_No se ejecuta CWT ni inferencia en el microcontrolador — todo el procesamiento
ocurre en PC durante esta etapa._

#### 4. PC (Dataset Generation)

- **ssr-ingest** (Go) — Captura streaming USB CDC, parsea frames, buffer circular
  10s, escritura a disco (.ssr)
- **ssr-inspect** (Go) — Análisis offline de archivos .ssr
- **ssr-replay** (Go) — Reproducción offline de sesiones para debug
- **export.py** (Python) — CWT Morlet (4 canales EMG) + mel-espectrograma (AUDIO) → .npz
  para entrenar modelo en Colab

### Formato de Trama USB

```
Byte 0:     Sync Word 0xAA
Byte 1:     Sync Word 0x55
Byte 2:     Tipo (0x02 = AUDIO, 0x03 = EMG)
Byte 3:     Flags (bit0: half/full, bit1: overflow)
Byte 4-7:   Timestamp (uint32, μs desde inicio)
Byte 8-9:   Data Length (uint16, N bytes)
Byte 10+:   Datos crudos
```

**EMG Frame (tipo 0x03):** Cada muestra = 4 × int16 (CH1..CH4) = 8 bytes.
100 muestras/frame → 800 bytes payload → 810 bytes total.

**AUDIO Frame (tipo 0x02):** Cada muestra = int32 (24-bit alineado a left) = 4 bytes.
128 muestras/frame → 512 bytes payload → 522 bytes total.

### Temporización

- TIM2 a 1 MHz (prescaler 549 desde 550 MHz HCLK, counter 32-bit)
- EMG: 2000 Hz / 100 muestras = 20 fps, cada 50 ms
- AUDIO: 16000 Hz / 128 muestras = 125 fps, cada 8 ms
- Headroom de CPU > 99%

### Sincronización Temporal

- Ambos periféricos timestampean desde TIM2 (misma base de tiempo)
- El PC realinea post-captura usando timestamps
- Offset esperado: < 1 ms entre flujos

### Electrodos

- Ag/AgCl pregelificados, preparación de piel antes de cada sesión
- Pares diferenciales: submentoniano, platisma, labio inferior, laringe
- RLD en la clavícula (9º electrodo)
- Cables cortos y trenzados por par hasta el AFE

---

## Etapa 2: Producto Final (Visión)

### Pipeline Embebido

```
                    ┌──────────────────────────────────────┐
                    │  STM32N6                              │
                    │                                      │
AFE sEMG ──ADC─────▶  M55 (CWT/DWT) ──▶ NPU (inferencia) ──▶ M55 (síntesis) ──I2S──▶ MAX98357 ──▶ parlante
 4 canales          │  • 64 escalas     • modelo int8       • mel → PCM                amp clase D    30mm
                    │  • 20-500 Hz      • 5M params         • 22.05 kHz               4Ω 2W
                    │  • 2 ms/ventana   • 5 ms/ventana      • 3 ms/ventana
                    │                                      │
                    │  TIMER sync @ 1 MHz                  │
                    │  Batería Li-Po 500mAh ─── TPS7A4700   │
                    │  USB-C (carga + debug)                │
                    └──────────────────────────────────────┘
```

### Características del Producto Final

- **Totalmente autónomo:** Sin PC, sin cables de datos
- **Factor de forma:** 50 × 40 × 15 mm, ~32 g
- **Uso:** Electrodos sEMG en rostro y cuello, enclosure fijado al cuello con banda textil
- **Reconstrucción en tiempo real:** Latencia < 50 ms desde activación muscular → voz
- **Parlante integrado:** Mini speaker 30mm, 2W, en cavidad del enclosure
- **Autonomía:** ~6 h en modo inferencia, >400 días en inactivo
- **Carga:** USB-C (TP4056), 2 h carga completa

### Modos de Operación

| Modo | Consumo | Descripción |
|---|---|---|
| Inactivo | ~50 µA | AFE apagado, esperando activación |
| Escucha | ~15 mA | M55 + AFE activos, CWT continuo, NPU dormida |
| Inferencia | ~80 mA | Todo activo, procesando ventanas de 1024 muestras |
| Síntesis | ~200 mA | Inferencia + I2S + parlante activo |
| Carga | — | TP4056 activo, dispositivo apagado |

### Propuesta de Valor

_Silent Speech Interface_ transforma la actividad eléctrica de los músculos del
habla en voz sintetizada, mediante un dispositivo portátil, discreto y autónomo.

**Mercado:** Pacientes laringectomizados, parálisis de cuerdas vocales, afonía
funcional, comunicación en entornos extremos (bomberos, militares, construcción),
comunicación silenciosa en general. Escalable a cualquier idioma — no requiere
cambios de hardware.

---

## Roadmap

| Mes | Hito |
|---|---|
| Mayo | Comprar componentes, montar protoboard |
| Junio | Firmware CMSISv2 funcional (ADC DMA, I2S DMA, USB CDC streaming estable) |
| Julio | Dataset v0.1 capturado + export.py validado |
| Agosto | Modelo entrenado en Colab (variante sin atención, ReLU) |
| Septiembre | Diseño conceptual PCB producto final + inscripción Muestra TECH |
| 15 Oct | **Muestra TECH — presentación** |
| Post-evento | Fabricar y validar producto final STM32N6 |
