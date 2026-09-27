# SSI — Silent Speech Interface

Plataforma modular de captura sincronizada para interfaz de habla silenciosa.
Adquiere tuplas (voz_mic, sEMG) desde un AFE sEMG diferencial de 4 canales
(submentoniano, platisma, labio inferior, laringe) sobre electrodos faciales +
micrófono digital de referencia, mediante un STM32 y streaming por USB-CDC a
PC.

**Mantra del proyecto:** matar dos pájaros de un tiro — (1) demostrar
causalidad sEMG → fonemas, no solo correlación, y (2) construir la
plataforma/estación de captura que genera el dataset masivo mínimo para que
el pipeline de software (CWT → Conv2D → TCN → vocoder) generalice más allá
de la demo. Detalle completo en `docs/refactor-emg-software.md` §0.

> **Sensor (sep. 2026):** potencial mioeléctrico de superficie (sEMG) en
> **4 canales** (el canal laríngeo es permanente), anterior en el tiempo al
> sonido, lo que permite sostener una afirmación de **causalidad** (no solo
> correlación) en el software. Diseño de hardware en
> `docs/afe-emg/AFE_EMG_Diseno.md` y `docs/afe-emg/AFE_valores_ltspice.md`;
> simulación LTspice en `sim/ltspice/` con resultados en
> `docs/afe-emg/resultados_simulacion.md`; refactor de software en
> `docs/refactor-emg-software.md`. El micrófono **INMP441 es un candidato
> recomendado, todavía NO comprado** — pendiente de que el usuario escuche
> las muestras de audio de la comparativa citada en el doc de refactor antes
> de confirmar la compra.

**Producto final:** Dispositivo autónomo 100% embebido (STM32N6 + parlante) que
reconstruye la voz a partir de activación neuromuscular facial. Sin PC.

## Pipeline de Desarrollo

```
AFE sEMG (4ch) ──ADC DMA──┐
                          ├── STM32 USB CDC ──→ PC (ssr-ingest Go) ──→ .ssr file
INMP441 ──────I2S DMA────┘                              │
                                                         ↓
                                                   export.py (CWT + NPZ)
                                                         │
                                                         ↓
                                                    Colab → modelo
```

## Pipeline del Producto Final

```
AFE sEMG (4ch) ──ADC──→ STM32N6 (M55: CWT + NPU: inferencia + M55: síntesis) ──I2S──→ MAX98357 ──→ parlante
```

## Estructura del Repositorio

```
ssr-testbed/
├── README.md
├── docs/              → Arquitectura, pinout, pipeline, diagramas
├── hardware/          → Wiring breakout (main-board)
├── firmware/          → Código STM32 (CMSISv2, I2S DMA, USB-CDC; captura EMG pendiente)
├── pc-tools/          → Go (ingest, inspect, replay) + Python (export, CWT)
├── dataset/           → Formato .ssr, sesiones grabadas
├── bom/               → Componentes, suppliers
└── scripts/           → Setup, flash
```

## Estado del Proyecto

| Componente                               | Estado                    |
|------------------------------------------|---------------------------|
| AFE sEMG (4 canales + RLD), diseño       | Cerrado (`docs/afe-emg/AFE_EMG_Diseno.md`); construcción pendiente |
| AFE sEMG, simulación LTspice (4 canales) | Hecha: `sim/ltspice/`, resultados en `docs/afe-emg/resultados_simulacion.md` |
| Micrófono INMP441                        | Candidato recomendado, **no comprado** — pendiente de confirmar (ver `docs/refactor-emg-software.md` §2) |
| Firmware STM32 (CMSISv2)                 | Falta la captura EMG 4 canales ADC+DMA, frame 0x03 (ver `docs/refactor-emg-software.md`) |
| ssr-ingest / inspect / replay (Go)       | Reconocen el frame EMG (0x03) |
| export.py (CWT)                          | Lee el frame EMG (CWT de los 4 canales); pendiente ventana/hop separados + lag causal |
| Corpus de entrenamiento                  | Por recapturar con AFE sEMG (foco actual) |
| Metodología de causalidad (lag, Granger) | Por implementar — define el éxito del proyecto |
| Modelo                                   | Investigación (arquitectura Conv2D→TCN reutilizable, ver sprints/sprint-1) |
| Producto final STM32N6                   | Planificado (post-Muestra) |

## Roadmap

El objetivo principal es tener la inferencia embebida en N6 (sEMG -> CWT -> DL -> Mel -> Parlante) para el 15 de octubre, fecha de la Muestra TECH 2026. El plan se divide en sprints semanales, con un enfoque inicial intensivo en el desarrollo de software.

**Sprint 9 (18 sep 2026):** la base de software de los Sprints 1–8 (CWT, Mel,
Depthwise Conv2D por canal → TCN causal → proyección a tokens de vocoder) es
agnóstica al sensor y recibe los 4 canales sEMG como entrada. Desde el
Sprint 9 se agrega un requisito: el software debe sostener
**causalidad** (precedencia temporal sEMG → voz), no solo correlación. Detalle
completo en `docs/refactor-emg-software.md`.

| Sprint       | Fecha (aprox.)         | Hitos Clave                                                                                                                                                                                                                                                                |
|--------------|------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Sprint 1** | 17 Jul - 24 Jul 2026   | **Software (100%):** Definición detallada de la arquitectura de tensores para MCU (C/C++) y PC (Python/Golang). Prototipo inicial de CWT en Python/Golang. Inicio de la generación de corpus de entrenamiento (primeras muestras).                                              |
| **Sprint 2** | 25 Jul - 01 Ago 2026   | **Software (100%):** Implementación de CWT en STM32 (C/C++). Verificación de equivalencia entre CWT en PC y MCU. Refinamiento del proceso de generación de corpus.                                                                                                                |
| **Sprint 3** | 02 Ago - 08 Ago 2026   | **Software (100%):** Implementación del algoritmo de Mel en Python/Golang (audio a mel y mel a audio). Pruebas de reproducibilidad: mel-spectrogram a audio. Continuación intensiva de la generación de corpus (foco en riqueza contextual).                                |
| **Sprint 4** | 09 Ago - 15 Ago 2026   | **Software (100%):** Implementación del algoritmo de Mel en STM32 (C/C++) (audio a mel y mel a audio). Verificación de equivalencia y reproducibilidad en MCU y PC. Dataset inicial "limpio" y etiquetado para entrenamiento.                                               |
| **Sprint 5** | 16 Ago - 22 Ago 2026   | **Integración:** Primeras pruebas de streaming de datos desde MCU a PC con CWT y Mel en tiempo real. Inicio del entrenamiento del modelo de inferencia (Deep Learning) con el dataset inicial en PC.                                                                           |
| **Sprint 6** | 23 Ago - 29 Ago 2026   | **Modelo y Hardware:** Primeras iteraciones de entrenamiento del modelo. Revisión de diseño del hardware del sensor. Inicio de cotización y/o fabricación de componentes críticos de hardware.                                                                                 |
| **Sprint 7** | 30 Ago - 05 Sep 2026   | **Optimización y Modelo:** Optimización del modelo de inferencia para despliegue en NPU de STM32N6 (si aplica). Pruebas de rendimiento del pipeline completo (sensor -> CWT -> Mel) en MCU.                                                                                   |
| **Sprint 8** | 06 Sep - 12 Sep 2026   | **Despliegue Preliminar:** Primer prototipo de inferencia embebida en STM32N6 (sin síntesis a parlante aún). Ajustes y correcciones del modelo y el firmware para mejorar la inferencia.                                                                                     |
| **Sprint 9** | 13 Sep - 19 Sep 2026   | **Pivote a sEMG (software):** Armado y validación de 1 canal completo del AFE sEMG (regla: 1 canal probado antes de replicar). Refactor de firmware (frame EMG 0x03), `ssr-ingest` y `export.py` para la fuente sEMG. Separación de ventana/hop de la CWT (bug del plan original, ver doc de refactor). |
| **Sprint 10**| 20 Sep - 26 Sep 2026   | **4 canales + recaptura de corpus:** Replicar el canal validado a los 4 sitios (submentoniano, platisma, labio inferior, laringe — CH4 dedicado, sin necesidad de reubicar electrodos). Implementar rutina de diagnóstico por canal (desconectado/sin habla/con habla, §3.4) y modos de captura por condición experimental (articulación silenciosa, vocal sostenida). Iniciar recaptura del corpus con sEMG real. |
| **Sprint 11**| 27 Sep - 03 Oct 2026   | **Causalidad, HMI y round-trip WORLD:** Implementar correlación cruzada con lag (envolvente sEMG vs. envolvente acústica) y, si el tiempo alcanza, Granger/transferencia de entropía. Reentrenar el modelo (misma arquitectura Conv2D→TCN) con el corpus sEMG. Construir el HMI multi-pestaña completo (§8 del doc de refactor: por canal, comparación CWT STM32 vs. Go, causalidad, round-trip WORLD). Extender `ssr-roundtrip` con la ruta WORLD (pyworld) y verificar bi-direccionalidad (§9). |
| **Sprint 12**| 04 Oct - 10 Oct 2026   | **Ensayos Generales:** Ensayos generales de la demostración para la Muestra TECH con el pipeline sEMG completo. Revisión final de todos los componentes y funcionalidades. Resolución de últimos bugs. Preparación de la narrativa de causalidad para el jurado (confusor del canal laríngeo CH4, sección 3.3 del doc de refactor). |
| **Muestra TECH** | **15 Oct 2026**    | **Presentación del prototipo funcional de SSI.**                                                                                                                                                                                                                           |

## Muestra TECH 2026

Presentación del prototipo funcional de SSI en la Muestra TECH 2026.
Criterios de evaluación: Creatividad (40%), Nivel Técnico (25%),
Presentación (20%), Impacto Social (15%).
