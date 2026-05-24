# SSI — Silent Speech Interface

Plataforma modular de captura sincronizada para interfaz de habla silenciosa.
Adquiere tuplas (voz_mic, vibracion_acc) desde acelerómetro IIS3DWB en flex PCB
adherida a la piel de la laringe + micrófono INMP441 de referencia, mediante un
STM32 y streaming por USB-CDC a PC.

**Producto final:** Dispositivo autónomo 100% embebido (STM32N6 + parlante) que
reconstruye la voz a partir de vibraciones mínimas de la laringe. Sin PC.

## Pipeline de Desarrollo

```
IIS3DWB ──SPI DMA──┐
                    ├── STM32 USB CDC ──→ PC (ssr-ingest Go) ──→ .ssr file
INMP441 ──I2S DMA──┘                              │
                                                   ↓
                                             export.py (CWT + NPZ)
                                                   │
                                                   ↓
                                              Colab → modelo
```

## Pipeline del Producto Final

```
IIS3DWB ──SPI──→ STM32N6 (M55: CWT + NPU: inferencia + M55: síntesis) ──I2S──→ MAX98357 ──→ parlante
```

## Estructura del Repositorio

```
ssr-testbed/
├── README.md
├── docs/              → Arquitectura, pinout, pipeline, diagramas
├── hardware/          → Flex PCB, acople mecánico, wiring breakout,
│                        enclosure, plan de hardware
├── firmware/          → Código STM32 (CMSISv2, SPI DMA, I2S DMA, USB-CDC)
├── pc-tools/          → Go (ingest, inspect, replay) + Python (export, CWT)
├── dataset/           → Formato .ssr, sesiones grabadas
├── bom/               → Componentes, suppliers
└── scripts/           → Setup, flash
```

## Estado del Proyecto

| Componente | Estado |
|---|---|
| Hardware — Plataforma Desarrollo | Planificado |
| Flex PCB sensor | Diseño |
| Firmware STM32 (CMSISv2) | Pendiente |
| ssr-ingest (Go) | Pendiente |
| export.py (CWT) | Pendiente |
| Dataset v0.1 | Pendiente |
| Modelo (variante ReLU) | Investigación |
| Producto final STM32N6 | Planificado (post-Muestra) |

## Roadmap

| Mes | Hito |
|---|---|
| Mayo 2026 | Compra de componentes, montaje protoboard |
| Junio 2026 | Firmware CMSISv2 funcional (SPI DMA, I2S DMA, USB CDC streaming) |
| Julio 2026 | Dataset v0.1 capturado, export.py validado |
| Agosto 2026 | Modelo entrenado en Colab |
| Septiembre 2026 | Diseño PCB producto final, inscripción Muestra TECH |
| **15 Oct 2026** | **Muestra TECH — presentación** |
| Post-evento | Producto final STM32N6 — fabricación y validación |

## Muestra TECH 2026

Presentación del prototipo funcional de SSI en la Muestra TECH 2026.
Criterios de evaluación: Creatividad (40%), Nivel Técnico (25%),
Presentación (20%), Impacto Social (15%).
