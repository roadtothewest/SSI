# Arquitectura del Sistema — SSI

## Visión General

SSI (Silent Speech Interface) es un sistema de reconstrucción de voz a partir de
vibraciones laríngeas. El proyecto tiene dos etapas:

1. **Plataforma de Desarrollo** — Captura sincronizada (vibración + audio) para
   generar dataset de entrenamiento. Usa NUCLEO-H723ZG + sensores + PC.
   _No hay inferencia embebida._

2. **Producto Final** — Sistema autónomo 100% embebido en STM32N6 (M55 + NPU)
   con parlante integrado. Sin PC, portátil, uso diario.

---

## Etapa 1: Plataforma de Desarrollo (Actual)

### Pipeline

```
IIS3DWB ──SPI DMA (26.7 kHz)──┐
                                ├── STM32H723ZG ──USB CDC──→ PC (ssr-ingest) → .ssr → .npz → Colab
INMP441 ──I2S DMA (16 kHz)─────┘
                                        TPS7A4700 LDO ── alimentación limpia sensores
```

### Bloques Funcionales

#### 1. Sensor de Vibración (IIS3DWB)

- Acelerómetro triaxial MEMS de ultra-alto ancho de banda
- ODR fijo: 26.7 kHz (no configurable, fijo por diseño HW)
- Ancho de banda plano: DC a 6.3 kHz
- Rango seleccionable: ±2g/±4g/±8g/±16g
- Interface: SPI full-duplex, 10 MHz mínimo
- Ruido: 75 µg/√Hz
- Encapsulado: LGA-14L (2.5 × 3 × 0.83 mm, masa ~2 mg)
- Montado en flex PCB de poliimida 0.1 mm → masa total < 10 mg

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
| SPI1 | 10 MHz, 16-bit, modo 3, DMA circular ping-pong. Doble buffer de 256 muestras triaxiales. |
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
- **export.py** (Python) — CWT Morlet (ACC) + mel-espectrograma (AUDIO) → .npz
  para entrenar modelo en Colab

### Formato de Trama USB

```
Byte 0:     Sync Word 0xAA
Byte 1:     Sync Word 0x55
Byte 2:     Tipo (0x01 = ACC, 0x02 = AUDIO)
Byte 3:     Flags (bit0: half/full, bit1: overflow)
Byte 4-7:   Timestamp (uint32, μs desde inicio)
Byte 8-9:   Data Length (uint16, N bytes)
Byte 10+:   Datos crudos
```

**ACC Frame (tipo 0x01):** Cada muestra = 3 × int16 (X, Y, Z) = 6 bytes.
256 muestras/frame → 1536 bytes payload → 1546 bytes total.

**AUDIO Frame (tipo 0x02):** Cada muestra = int32 (24-bit alineado a left) = 4 bytes.
128 muestras/frame → 512 bytes payload → 522 bytes total.

### Temporización

- TIM2 a 1 MHz (prescaler 549 desde 550 MHz HCLK, counter 32-bit)
- ACC: 26700 Hz / 256 muestras = ~104 fps, cada 9.6 ms
- AUDIO: 16000 Hz / 128 muestras = 125 fps, cada 8 ms
- Headroom de CPU > 99%

### Sincronización Temporal

- Ambos periféricos timestampean desde TIM2 (misma base de tiempo)
- El PC realinea post-captura usando timestamps
- Offset esperado: < 1 ms entre flujos

### Acople Mecánico (Flex PCB)

- Masa total conjunto: ~8 mg (flex + IIS3DWB + adhesivo)
- Relación vs. piel laríngea: 0.53% (masa efectiva ~1.5 g)
- Adhesivo: 3M 1526L (medical grade ISO 10993, 0.18 mm)
- Cableado: FPC 0.5 mm pitch, 10-15 cm, con lazo alivio tensión
- Frecuencia de resonancia piel-sensor: ~3.9 kHz (fuera de banda útil)

---

## Etapa 2: Producto Final (Visión)

### Pipeline Embebido

```
                    ┌──────────────────────────────────────┐
                    │  STM32N6                              │
                    │                                      │
IIS3DWB ──SPI──────▶  M55 (CWT/DWT) ──▶ NPU (inferencia) ──▶ M55 (síntesis) ──I2S──▶ MAX98357 ──▶ parlante
                    │  • 512 escalas    • modelo int8       • mel → PCM                amp clase D    30mm
                    │  • 50-6000 Hz     • 5M params         • 22.05 kHz               4Ω 2W
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
- **Uso:** Flex PCB adherido a laringe, enclosure fijado al cuello con banda textil
- **Reconstrucción en tiempo real:** Latencia < 50 ms desde vibración → voz
- **Parlante integrado:** Mini speaker 30mm, 2W, en cavidad del enclosure
- **Autonomía:** ~6 h en modo inferencia, >400 días en inactivo
- **Carga:** USB-C (TP4056), 2 h carga completa

### Modos de Operación

| Modo | Consumo | Descripción |
|---|---|---|
| Inactivo | ~50 µA | Sensor low-power, esperando vibración |
| Escucha | ~15 mA | M55 + IIS3DWB activos, CWT continuo, NPU dormida |
| Inferencia | ~80 mA | Todo activo, procesando ventanas de 1024 muestras |
| Síntesis | ~200 mA | Inferencia + I2S + parlante activo |
| Carga | — | TP4056 activo, dispositivo apagado |

### Propuesta de Valor

_Silent Speech Interface_ transforma las mínimas vibraciones laríngeas en voz
sintetizada, mediante un dispositivo portátil, discreto y autónomo.

**Mercado:** Pacientes laringectomizados, parálisis de cuerdas vocales, afonía
funcional, comunicación en entornos extremos (bomberos, militares, construcción),
comunicación silenciosa en general. Escalable a cualquier idioma — no requiere
cambios de hardware.

---

## Roadmap

| Mes | Hito |
|---|---|
| Mayo | Comprar componentes, montar protoboard |
| Junio | Firmware CMSISv2 funcional (SPI DMA, I2S DMA, USB CDC streaming estable) |
| Julio | Dataset v0.1 capturado + export.py validado |
| Agosto | Modelo entrenado en Colab (variante sin atención, ReLU) |
| Septiembre | Diseño conceptual PCB producto final + inscripción Muestra TECH |
| 15 Oct | **Muestra TECH — presentación** |
| Post-evento | Fabricar y validar producto final STM32N6 |
