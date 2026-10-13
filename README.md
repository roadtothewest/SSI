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

## Muestra TECH 2026

Presentación del prototipo funcional de SSI en la Muestra TECH 2026.
Criterios de evaluación: Creatividad (40%), Nivel Técnico (25%),
Presentación (20%), Impacto Social (15%).
