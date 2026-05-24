# Plan de Hardware — Silent Speech Interface

## Visión General: Dos Etapas

```
ETAPA 1 — PLATAFORMA DE DESARROLLO (actual)
  Propósito: Generar dataset (vibración + audio) para entrenar modelo
  Hardware:  NUCLEO-H723ZG + IIS3DWB + INMP441 + TPS7A4700 + protoboard
  Procesamiento: PC (export.py → CWT + mel → .npz → Colab)
  Producto final: Solo dataset y modelo entrenado

ETAPA 2 — PRODUCTO FINAL (post-Muestra TECH)
  Propósito: Reconstrucción de voz embebida, autónoma, portátil
  Hardware:  STM32N6 (M55 + NPU) + IIS3DWB + parlante + batería Li-Po
  Procesamiento: 100% embebido (CWT/DWT en M55, inferencia en NPU, síntesis audio)
  Producto final: Sin PC, sin cable, uso diario adherido al cuello
```

---

# Etapa 1: Plataforma de Desarrollo

## 1.1 Arquitectura de Bloques

```
                    ┌──────────────────────────────────────────────┐
                    │             POWER TREE                        │
                    │                                              │
                    │  Powerbank 5V ──┬── NUCLEO-H723ZG (VIN)     │
                    │                 │                             │
                    │                 └── TPS7A4700 ── 3.3V ──┬── IIS3DWB VDD
                    │                                              └── INMP441 VDD
                    └──────────────────────────────────────────────┘

                    ┌──────────────────────────────────────────────┐
                    │           SENSOR BUS                          │
                    │                                              │
                    │  IIS3DWB ──SPI1──┐                           │
                    │  (CS:PA4, SCK:PA5, MISO:PA6, MOSI:PA7)      │
                    │  (INT1:PC0)      │                           │
                    │                  ├── STM32H723ZG             │
                    │  INMP441 ──I2S3──┘   (DMA ping-pong)         │
                    │  (BCK:PC10, WS:PA15, DOUT:PC7, L/R:GND)     │
                    │                                              │
                    │  TIM2 @ 1 MHz ── sync para ambos flujos DMA  │
                    └──────────────────────────────────────────────┘

                    ┌──────────────────────────────────────────────┐
                    │           USB STREAM                          │
                    │                                              │
                    │  STM32 USB_OTG_HS ──USB CDC──→ PC            │
                    │  (PA11:DM, PA12:DP, PA9:VBUS)                │
                    │  Bulk EP 512 bytes, frames autodescriptivos   │
                    └──────────────────────────────────────────────┘
```

## 1.2 Componentes

| Componente | Cant. | Especificación clave | Alternativa |
|---|---|---|---|
| NUCLEO-H723ZG | 1 | Cortex-M7 550MHz, SPI, I2S, USB-HS | NUCLEO-H743ZI |
| IIS3DWB | 1 | ODR 26.7kHz, BW 6.3kHz, SPI, LGA-14L | ADXL1001 (analógico, peor BW) |
| INMP441 | 1 | I2S 24-bit, 16kHz, SNR 61dBA | SPH0645LM4H (compatible I2S) |
| TPS7A4700 | 1 | LDO 3.3V, 4µVrms ruido, 1A | ADP7142 |
| Powerbank 5V 2A | 1 | Para pruebas portátiles | Batería Li-Po 18650 + step-up |
| Protoboard 830 ptos | 1 | 400+ puntos recomendado | Placa perforada + estaño |
| Cables dupont M-F | 20 | 20cm | Kit 40 cables |
| Cables dupont M-M | 10 | 10cm | — |
| JST SH 1.0mm 4-pin | 2 | Para conector flex PCB | Molex PicoBlade |
| 3M 1526L medical tape | 1 roll | 0.18mm, ISO 10993 | Hydrocolloid |
| Analizador lógico | 1 | 24MHz, 8ch | Saleae clone |

### Justificación de selección

**IIS3DWB vs acelerómetros convencionales:**
- Es el único acelerómetro MEMS en el mercado con ODR de 26.7 kHz y BW plano hasta 6.3 kHz en un paquete de 2.5×3 mm.
- Los acelerómetros de consumo (LSM6DSO, BMI270) tienen BW < 2 kHz, insuficiente para capturar armónicos laríngeos.
- Los acelerómetros industriales (ADXL1001) son analógicos, requieren ADC externo y son más grandes.

**NUCLEO-H723ZG vs alternativas:**
- SPI a 10 MHz + DMA cíclico para 26.7 kHz × 3 canales sin pérdidas.
- I2S nativo para INMP441 (no requiere codec externo).
- USB_OTG_HS para CDC Bulk streaming.
- Suficiente RAM (564 kB) para doble buffer + buffer circular de frames.

**INMP441 vs micrófonos analógicos:**
- Salida digital I2S directamente al periférico SAI del STM32.
- Sin circuitería analógica (elimina ruido de acoplo).
- SNR 61 dBA suficiente para referencia de voz a 5 cm del cuello.

## 1.3 Power Tree — Análisis Detallado

```
Powerbank 5V 2A
  │
  ├── NUCLEO-H723ZG (VIN pin, ~300mA @ 5V)
  │     └── ST-LINK V3 (~100mA)
  │     └── STM32H723ZG (~200mA en run @ 550MHz)
  │     └── LEDs + misc (~10mA)
  │
  └── TPS7A4700 (VIN)
        └── Salida 3.3V limpia
              ├── IIS3DWB: 1.1mA (peak) + 0.5mA interfaz SPI
              ├── INMP441: 1.4mA (peak)
              └── Total sensores: ~3mA
```

**¿Por qué un LDO externo si la NUCLEO ya tiene regulador?**
- El regulador onboard de la NUCLEO es conmutado (SMPS) con ripple de ~10-50mV.
- El IIS3DWB tiene sensibilidad de 75 µg/√Hz — el ruido de alimentación se acopla al eje Z.
- El TPS7A4700 tiene 4 µVrms de ruido y PSRR > 82dB @ 100Hz.
- Los sensores consumen < 3mA, el LDO opera en régimen de bajo ruido óptimo.

## 1.4 Distribución de Pines STM32

| Periférico | Señal | STM32 Pin | Puerto | Alternativa |
|---|---|---|---|---|
| SPI1 | SCK | PA5 | Arduino D13 | PB3 (SPI1 SCK alt) |
| SPI1 | MISO | PA6 | Arduino D12 | PB4 (SPI1 MISO alt) |
| SPI1 | MOSI | PA7 | Arduino D11 | PB5 (SPI1 MOSI alt) |
| SPI1 | CS | PA4 | Arduino D10 | Cualquier GPIO |
| IIS3DWB | INT1 | PC0 | Morpho | Cualquier EXTI |
| I2S3 | BCK | PC10 | Morpho | PB13 (I2S2_CK) |
| I2S3 | WS | PA15 | Morpho | PB12 (I2S2_WS) |
| I2S3 | DOUT | PC7 | Morpho | PB15 (I2S2_SD) |
| INMP441 | L/R | GND | — | Fijo a GND = Left channel |
| USB_OTG_HS | DM | PA11 | CN13 USB-HS | — |
| USB_OTG_HS | DP | PA12 | CN13 USB-HS | — |
| USB_OTG_HS | VBUS | PA9 | CN13 | Detección de VBUS |
| TIM2 | CH1 | PA0 | Morpho | Timer 2, usado como base 1 MHz |

## 1.5 Pipeline de Firmware (CMSISv2)

```
Reset
  │
  ├── SystemInit() ── clock config (HSE 8MHz → PLL → 550MHz)
  │
  ├── GPIO_Init() ── CS(PA4), INT1(PC0), USB_DM/DP
  │
  ├── DMA_Init() ── DMA1 Stream0 (SPI1 RX), DMA1 Stream1 (SPI1 TX)
  │                  DMA2 Stream0 (I2S3 RX)
  │
  ├── SPI1_Init() ── 10MHz, Mode 3 (CPOL=1, CPHA=1), 16-bit, MSB-first
  │
  ├── I2S3_Init() ── Master RX, Philips standard, 24-bit, 16kHz
  │
  ├── TIM2_Init() ── Prescaler = (550MHz / 1MHz) - 1 = 549, Period = 0xFFFFFFFF
  │
  ├── USB_CDC_Init() ── Configurar endpoint Bulk 512 bytes
  │                       Activar pull-up en DP para detección de host
  │
  ├── IIS3DWB_Init():
  │     ├── Leer WHO_AM_I (0x0F) → esperar 0x71
  │     ├── Reset por CTRL3_C (0x12) bit BOOT = 1
  │     ├── Configurar CTRL1_XL (0x10): ODR=26.7kHz, FS=±2g (0x60)
  │     ├── CTRL4_C (0x13): SPI 4-wire, no I3C (0x04)
  │     ├── CTRL6_C (0x15): Self-test off, low-pass off
  │     ├── FIFO deshabilitado (modo bypass)
  │     └── INT1 deshabilitado (polling por DMA)
  │
  ├── INMP441_Init():
  │     └── HAL_I2S_Init() con AudioFreq = 16000
  │
  ├── Start DMA:
  │     ├── SPI1: Transmit cmd byte → Receive DMA para ACC_SAMPLES*3*2 bytes
  │     └── I2S3: Receive DMA para AUDIO_SAMPLES*2*2 bytes (16-bit words, I2S 24-bit empaquetado)
  │
  └── Main Loop:
        ├── Revisar flags half/full de cada periférico
        ├── Procesar frame ACC (empaquetar X,Y,Z int16 + timestamp)
        ├── Procesar frame AUDIO (empaquetar int32 + timestamp)
        ├── Encolar en buffer TX USB
        └── Transmitir por CDC cuando haya datos disponibles
```

## 1.6 DMA Circular Ping-Pong

### SPI (IIS3DWB) — 26.7 kHz, 3 canales

```
Buffer A: int16[ACC_SAMPLES * 3]  ← DMA escribe aquí primero
Buffer B: int16[ACC_SAMPLES * 3]  ← DMA escribe aquí después

Flujo:
  1. DMA llena Buffer A (Half-Transfer callback → procesar buffer A)
  2. DMA llena Buffer B (Full-Transfer callback → procesar buffer B)
  3. Reinicia: DMA llena Buffer A (Half-Transfer → buffer A listo otra vez)

Cada callback:
  - Lee timestamp de TIM2 (1 MHz)
  - Copia buffer a frame temporal
  - Construye trama CDC: {0xAA, 0x55, 0x01, flags, timestamp, data_len=1536, data[1536]}
  - Pasa a cola TX USB
```

ACC_SAMPLES = 256 → cada medio buffer = 256 muestras × 3 ejes × 2 bytes = 1536 bytes.
Frecuencia: 26.7 kHz / 256 = ~104 frames/s, cada 9.6 ms.

### I2S (INMP441) — 16 kHz, 1 canal

```
Buffer A: int32[AUDIO_SAMPLES]
Buffer B: int32[AUDIO_SAMPLES]

Similar al SPI, pero con datos I2S 24-bit alineados a left en int32.
```

AUDIO_SAMPLES = 128 → cada medio buffer = 128 × 4 bytes = 512 bytes.
Frecuencia: 16 kHz / 128 = 125 frames/s, cada 8 ms.

## 1.7 Trama USB CDC

| Offset | Bytes | Campo | Valor |
|---|---|---|---|
| 0 | 1 | sync0 | 0xAA |
| 1 | 1 | sync1 | 0x55 |
| 2 | 1 | frame_type | 0x01=ACC, 0x02=AUDIO |
| 3 | 1 | flags | bit0=half(0)/full(1), bit1=overflow |
| 4 | 4 | timestamp | uint32 LE (µs desde inicio) |
| 8 | 2 | data_len | uint16 LE |
| 10 | N | data | payload |

**Header: 10 bytes.**

Frame ACC típico: 10 + 1536 = 1546 bytes → 3 paquetes Bulk 512 + 10 bytes.
Frame AUDIO típico: 10 + 512 = 522 bytes → 2 paquetes Bulk (512 + 10).

El host (PC) realinea por timestamp, no depende del orden de llegada.

## 1.8 Presupuesto de Tiempo — Main Loop

| Operación | Tiempo estimado | Notas |
|---|---|---|
| DMA Half/Full callback SPI | ~5 µs | Copiar buffer + timestamp |
| DMA Half/Full callback I2S | ~3 µs | Copiar buffer + timestamp |
| Construir frame CDC ACC | ~10 µs | Empaquetar 256 triplas |
| Construir frame CDC AUDIO | ~5 µs | Copiar 128 int32 |
| TX USB | ~50 µs | Bulk write (bloqueante hasta PHY) |
| Total por frame | ~70 µs | De 9600 µs disponibles (104 Hz) |
| Headroom | **>99%** | Sobra capacidad |

Conclusión: el H723ZG a 550 MHz tiene capacidad de sobra.

## 1.9 Captura de Dataset — Protocolo

### Estructura de sesión

```
dataset/sessions/{YYYY-MM-DD_HHmmss}/
  metadata.json     → parámetros de adquisición
  data.ssr          → frames binarios secuenciales
  info.md           → notas de la sesión (sujeto, posición sensor, texto)
```

### Parámetros de sesión (metadata.json)

```json
{
  "session_id": "2026-07-15_143022",
  "subject": "anon_01",
  "device": "NUCLEO-H723ZG",
  "sensors": {
    "acc": { "model": "IIS3DWB", "odr_hz": 26700, "range_g": 2, "samples_per_frame": 256 },
    "audio": { "model": "INMP441", "sample_rate_hz": 16000, "bits": 24, "samples_per_frame": 128 }
  },
  "sensor_position": "larynx_center",
  "prompt_set": "fonemas_espanol_v1",
  "environment": "sala_silenciosa",
  "duration_s": 600,
  "total_frames": { "acc": 62500, "audio": 37500 }
}
```

### Conjuntos de captura

| Conjunto | Contenido | Duración | # Sesiones |
|---|---|---|---|
| Fonemas español | /a/, /e/, /i/, /o/, /u/, /p/, /t/, /k/, /s/, /f/, /m/, /n/, /l/, /r/, /rr/ | 5 min | 5 |
| Palabras aisladas | 50 palabras comunes (casa, perro, agua, etc.) | 10 min | 5 |
| Frases cortas | 20 frases de 3-5 palabras | 10 min | 5 |
| Conversación guiada | Leer texto de 1 min, 3 variaciones | 15 min | 10 |

Total estimado: ~5 horas de captura distribuidas en múltiples sesiones.

### Control de calidad

- Verificar FPS estables en PC (104 ACC fps ±1, 125 AUDIO fps ±1)
- Tolerancia: 0 drops por cada 1000 frames
- Verificar offset temporal ACC vs AUDIO (< 1 ms)
- Rechazar sesiones con ruido eléctrico visible en ACC

---

# Etapa 2: Producto Final (Visión de Diseño)

## 2.1 Arquitectura Embebida

```
                    ┌──────────────────────────────────────┐
                    │         POWER TREE (FINAL)            │
                    │                                      │
                    │ Li-Po 3.7V 500mAh                    │
                    │   │                                  │
                    │   ├── TP4056 (cargador USB-C)        │
                    │   │                                  │
                    │   └── TPS7A4700 ── 3.3V ──┬── IIS3DWB VDD
                    │                           ├── STM32N6 VDD
                    │                           └── MAX98357 (amplificador)
                    │                                      │
                    │   └── TPS61232 (boost 3.7V→5V) ── parlante
                    └──────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
                    │      PROCESAMIENTO (STM32N6)          │
                    │                                      │
                    │  IIS3DWB ──SPI──┐                    │
                    │                ├── M55: CWT/DWT      │
                    │                │   (512 escalas,      │
                    │  Sensor flex   │   50-6000Hz)         │
                    │                │       │              │
                    │                │       ▼              │
                    │                │  NPU: inferencia     │
                    │                │   (modelo cuantizado)│
                    │                │       │              │
                    │                │       ▼              │
                    │                │  M55: síntesis mel → │
                    │                │        audio PCM     │
                    │                │           │          │
                    │                │           ▼          │
                    │                │  I2S out ── MAX98357──▶ parlante
                    └──────────────────────────────────────┘
```

## 2.2 STM32N6 — Selección y Justificación

| Recurso | Requerido | STM32N6 | Observación |
|---|---|---|---|
| CPU | 500+ DMIPS | Cortex-M55 @ 800MHz | Sí, con Helium (MVE) para CWT |
| NPU | 10+ GOPS | Neural-Art Accelerator (1 TOPS) | Sí, para modelo cuantizado int8 |
| RAM | 2+ MB | 4.2 MB SRAM | Suficiente para buffers + modelo |
| Flash | 8+ MB | 8 MB embebido | Modelo cuantizado ~2-4 MB |
| SPI | 1x a 10 MHz | Sí | IIS3DWB |
| I2S | 1x out | Sí | Audio síntesis → MAX98357 |
| USB | 1x OTG | Sí | Carga de modelo, debug |
| PDM | 1x in | Sí | Opcional micrófono digital directo |
| Paquete | Pequeño | UFBGA169 (7×7mm) | Adecuado para producto portátil |

### Procesamiento — Estimación de carga

| Etapa | Recurso | Tiempo estimado | Notas |
|---|---|---|---|
| CWT (ACC-X, 512 escalas, 1024 muestras) | M55 Helium (int16) | ~2 ms @ 800MHz | Loop vectorizado con MVE |
| Inferencia (modelo ~5M parámetros int8) | NPU (NDP100) | ~5 ms @ 1GHz | Optimizado para int8 |
| Síntesis mel → audio (HiFi-4/tensor) | M55 + DMA | ~3 ms | Buffer circular audio out |
| **Total por ventana** | | **~10 ms** | Budget: 30 ms (33 Hz) |
| **Headroom** | | **>66%** | Para buffering y overhead |

### Síntesis de audio

- Salida: I2S 16-bit, 22.05 kHz (o 16 kHz), DMA desde buffer circular
- Amplificador: MAX98357 (clase D, I2S in, salida directa a parlante 4Ω/3W)
- Parlante: mini speaker 30mm, 4Ω, 2W, montado en cavidad del enclosure

## 2.3 Dimensionamiento del Enclosure

### Restricciones mecánicas

| Componente | Dimensiones (mm) | Masa (g) |
|---|---|---|
| PCB principal (STM32N6 + audio) | 30 × 20 × 1.6 | 5 |
| Flex PCB sensor (IIS3DWB) | 15 × 8 × 0.2 | 0.008 |
| Parlante 30mm | 30 × 30 × 8 | 3 |
| Batería Li-Po 3.7V 500mAh | 35 × 20 × 5 | 12 |
| Cargador TP4056 + USB-C | 15 × 10 × 3 | 1 |
| Cableado FPC 10cm | — | 0.5 |
| Enclosure (resina impresa 3D) | 50 × 40 × 15 | 10 |
| **Total** | **~50 × 40 × 15 mm** | **~32 g** |

### Posición de uso

```
  Vista frontal del cuello
  ┌─────────────────────┐
  │                     │
  │    Laringe          │
  │      ◆              │  ◆ = Flex PCB con IIS3DWB
  │     /|\             │       Adherido a piel (3M 1526L)
  │    / | \            │
  │   /  |  \           │
  │      |              │
  │      | cable FPC    │
  │      |              │
  │   ┌──┴──┐           │  ┌──────┐ = Enclosure principal
  │   │     │           │       STM32N6 + batería + parlante
  │   └─────┘           │       Fijado al cuello con banda textil
  └─────────────────────┘
```

## 2.4 Modos de Operación

| Modo | Descripción | Consumo | Autonomía (500mAh) |
|---|---|---|---|
| **Inactivo** | Sensor en low-power, esperando vibración | ~50 µA | >400 días |
| **Escucha** | M55 + IIS3DWB activos, CWT continuo, NPU dormida | ~15 mA | ~33 h |
| **Inferencia** | Todo activo, procesando ventanas | ~80 mA | ~6 h |
| **Síntesis** | Inferencia + I2S + parlante (volumen medio) | ~200 mA | ~2.5 h |
| **Carga** | Solo TP4056 activo, dispositivo apagado | — | 2 h (carga completa) |

### Máquina de estados

```
  INACTIVO ──(detección de vibración > umbral)──▶ ESCUCHA
     ▲                                                │
     │                                                │
     │            ┌──(voz sintetizada entregada)──────┤
     │            │                                   │
     │     (silencio > 3s)                     (voz detectada)
     │            │                                   │
     └────────────┴─────◀─────── INFERENCIA ◀─────────┘
                                              │
                                              │
                                         (contexto > 500ms)
                                              │
                                              ▼
                                         SÍNTESIS
```

## 2.5 BOM Estimado — Producto Final

| Componente | Referencia | Cant. | $/ud. |
|---|---|---|---|
| MCU + NPU | STM32N6 (TBD variant) | 1 | ~12 |
| Accelerómetro | IIS3DWB | 1 | ~5 (volumen) |
| Amplificador audio | MAX98357 | 1 | ~2 |
| LDO | TPS7A4700 | 1 | ~3 |
| Cargador Li-Po | TP4056 + protección DW01 | 1 | ~0.5 |
| Boost 5V | TPS61232 | 1 | ~1 |
| Batería | Li-Po 3.7V 500mAh | 1 | ~4 |
| Parlante | 30mm 4Ω 2W | 1 | ~2 |
| USB-C connector | 16-pin | 1 | ~0.3 |
| Flex PCB | Poliimida 0.1mm 2 capas | 1 | ~2 |
| PCB principal | FR4 4 capas 30×20mm | 1 | ~3 |
| FPC cable | 10cm 6-pin 0.5mm pitch | 1 | ~1 |
| Enclosure | Resina 3D | 1 | ~2 |
| Adhesivo | 3M 1526L | — | ~1 |
| Pasivos varios | 0402 + 0603 | ~20 | ~0.5 |
| **Total** | | | **~40** |

---

# Roadmap a Muestra TECH 2026

```
Semana  | Mayo         | Junio          | Julio          | Agosto        | Septiembre      | Octubre
        |              |                |                |               |                 |
HW      | Comprar      | Montar         | —              | —             | Iniciar diseño  | Freeze
        | componentes  | protoboard     |                |               | PCB STM32N6     |
        |              | Test continuidad|               |               |                 |
        |              | WHO_AM_I       |                |               |                 |
────────|──────────────|────────────────|────────────────|───────────────|─────────────────|────────
FW      | —            | CMSISv2 SPI    | CMSISv2 USB CDC| Refinar       | —               | Demo
        |              | DMA ping-pong  | streaming      | estabilidad   |                 | final
        |              | I2S DMA        | frame builder  | buffer overflow|                |
────────|──────────────|────────────────|────────────────|───────────────|─────────────────|────────
PC      | Setup env    | ssr-ingest     | ssr-inspect    | export.py →   | —               | —
Tools   | Go + Python  | debug          | .ssr → .npz    |Validar .npz   |                 |
────────|──────────────|────────────────|────────────────|───────────────|─────────────────|────────
Dataset | —            | —              | Primeras       | Captura       | —               | —
        |              |                | sesiones       | masiva        |                 |
        |              |                | prueba 30s     | (10+ sesiones)|                 |
────────|──────────────|────────────────|────────────────|───────────────|─────────────────|────────
Modelo  | Paper review | Implementar    | Entrenar en    | Optimizar     | Cuantizar       | —
        | SOTA         | baseline Colab | Colab (variante| (ReLU, sin    | int8 para NPU   |
        |              |                | ReLU)          | atención)     |                 |
────────|──────────────|────────────────|────────────────|───────────────|─────────────────|────────
Muestra | —            | —              | —              | —             | Inscripción     | Muestra
TECH    |              |                |                |               | (hasta 15 Sep)  | TECH!
        |              |                |                |               | Preparar poster | 15 Oct
        |              |                |                |               | Ensayo pitch    |
───────────────────────────────────────────────────────────────────────────────────────────────
```

## Criterios de Evaluación — Estrategia

| Criterio | Peso | Estrategia para Muestra TECH |
|---|---|---|
| Creatividad e Innovación | **40%** | Enfoque único: acelerómetro ultra-wideband IIS3DWB para capturar vibración laríngea. Reconstrucción de voz para pacientes con laringectomía, parálisis de cuerdas vocales, afonía funcional, comunicación en ambientes extremos. Producto portátil, discreto, uso diario. |
| Nivel Técnico | **25%** | Demo en vivo del prototipo (NUCLEO + sensores capturando en tiempo real). Mostrar stream USB en PC con FPS estables. Tener un .npz generado de sesión real. Mostrar visualización CWT del ACC capture. |
| Presentación | **20%** | Video promocional del pipeline completo (persona usando el sensor → voz reconstruida → parlante). Poster técnico con arquitectura. Pitch de 3 minutos enfocado en el problema social y la innovación técnica. |
| Impacto Social | **15%** | Mercado amplio: laringectomizados, parálisis de pliegues vocales, afonía funcional, entornos ruidosos (bomberos, militares, construcción), comunicación silenciosa general. Escalable a múltiples idiomas sin cambiar hardware. |
