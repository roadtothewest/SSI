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

| Componente                               | Estado                    |
|------------------------------------------|---------------------------|
| Plataforma de Desarrollo (cotización)    | En curso                  |
| Flex PCB sensor                          | Diseño (en validación)    |
| Firmware STM32 (CMSISv2)                 | En desarrollo             |
| ssr-ingest (Go)                          | En desarrollo             |
| export.py (CWT)                          | En desarrollo             |
| Corpus de entrenamiento                  | En desarrollo (foco actual)|
| Algoritmo Mel (MCU y PC)                 | En desarrollo (foco actual)|
| Modelo                                   | Investigación              |
| Producto final STM32N6                   | Planificado (post-Muestra) |

## Roadmap

El objetivo principal es tener la inferencia embebida en N6 (Accel. -> CWT -> DL -> Mel -> Parlante) para el 15 de octubre, fecha de la Muestra TECH 2026. El plan se divide en sprints semanales, con un enfoque inicial intensivo en el desarrollo de software.

| Sprint       | Fecha (aprox.)         | Hitos Clave                                                                                                                                                                                                                                                                |
|--------------|------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Sprint 1** | 17 Jul - 24 Jul 2026   | **Software (100%):** Definición detallada de la arquitectura de tensores para MCU (C/C++) y PC (Python/Golang). Prototipo inicial de CWT en Python/Golang. Inicio de la generación de corpus de entrenamiento (primeras muestras).                                              |
| **Sprint 2** | 25 Jul - 01 Ago 2026   | **Software (100%):** Implementación de CWT en STM32 (C/C++). Verificación de equivalencia entre CWT en PC y MCU. Refinamiento del proceso de generación de corpus.                                                                                                                |
| **Sprint 3** | 02 Ago - 08 Ago 2026   | **Software (100%):** Implementación del algoritmo de Mel en Python/Golang (audio a mel y mel a audio). Pruebas de reproducibilidad: mel-spectrogram a audio. Continuación intensiva de la generación de corpus (foco en riqueza contextual).                                |
| **Sprint 4** | 09 Ago - 15 Ago 2026   | **Software (100%):** Implementación del algoritmo de Mel en STM32 (C/C++) (audio a mel y mel a audio). Verificación de equivalencia y reproducibilidad en MCU y PC. Dataset inicial "limpio" y etiquetado para entrenamiento.                                               |
| **Sprint 5** | 16 Ago - 22 Ago 2026   | **Integración:** Primeras pruebas de streaming de datos desde MCU a PC con CWT y Mel en tiempo real. Inicio del entrenamiento del modelo de inferencia (Deep Learning) con el dataset inicial en PC.                                                                           |
| **Sprint 6** | 23 Ago - 29 Ago 2026   | **Modelo y Hardware:** Primeras iteraciones de entrenamiento del modelo. Revisión de diseño final de Flex PCB sensor. Inicio de cotización y/o fabricación de componentes críticos de hardware.                                                                                 |
| **Sprint 7** | 30 Ago - 05 Sep 2026   | **Optimización y Modelo:** Optimización del modelo de inferencia para despliegue en NPU de STM32N6 (si aplica). Pruebas de rendimiento del pipeline completo (Accel -> CWT -> Mel) en MCU.                                                                                   |
| **Sprint 8** | 06 Sep - 12 Sep 2026   | **Despliegue Preliminar:** Primer prototipo de inferencia embebida en STM32N6 (sin síntesis a parlante aún). Ajustes y correcciones del modelo y el firmware para mejorar la inferencia.                                                                                     |
| **Sprint 9** | 13 Sep - 19 Sep 2026   | **Integración Final (Audio):** Implementación de la etapa de síntesis (Mel a Audio) en STM32N6 y conexión con el parlante. Pruebas de integración completa del pipeline (Accel -> CWT -> DL -> Mel -> Parlante).                                                              |
| **Sprint 10**| 20 Sep - 26 Sep 2026   | **Afinación y Pruebas:** Afinación fina del sistema completo. Pruebas exhaustivas de funcionalidad, latencia y calidad de la voz reconstruida. Inicio de la preparación de la presentación para la Muestra TECH.                                                              |   
| **Sprint 11**| 27 Sep - 03 Oct 2026   | **Pulido y Presentación:** Pulido de la interfaz y experiencia de usuario. Preparación final de la demostración para la Muestra TECH. Documentación y materiales de presentación.                                                                                           |
| **Sprint 12**| 04 Oct - 10 Oct 2026   | **Ensayos Generales:** Ensayos generales de la demostración para la Muestra TECH. Revisión final de todos los componentes y funcionalidades. Resolución de últimos bugs.                                                                                                      |
| **Muestra TECH** | **15 Oct 2026**    | **Presentación del prototipo funcional de SSI.**                                                                                                                                                                                                                           |

## Muestra TECH 2026

Presentación del prototipo funcional de SSI en la Muestra TECH 2026.
Criterios de evaluación: Creatividad (40%), Nivel Técnico (25%),
Presentación (20%), Impacto Social (15%).
