# Archivo

Documentos y código que ya no describen el proyecto. Se movieron aquí el 2026-10-14 con `git mv` (el historial sigue en `git log --follow`). No usar como referencia: el documento vigente de cada tema está en `docs/README.md`.

| Archivo | Qué era | Por qué quedó obsoleto | Qué lo reemplaza |
|---|---|---|---|
| `CONTEXTO_CLAUDE.md` | Traspaso de la sesión de Claude Code del 18–26 sep | 4 canales, MCP6004, ×503 | `README.md`, `sim/ltspice/README.md` |
| `docs/refactor-emg-software.md` | Spec del software para sEMG (incluye el "mantra" §0) | 4 canales, `ssr-ingest`, `export.py` | `auravoxd/README.md`, `PROTOCOLO_SPI.md` |
| `docs/afe-emg/AFE_EMG_Diseno.md` | Análisis del AFE (7-ago) | Anterior al diseño cerrado | `sim/ltspice/README.md` |
| `docs/afe-emg/AFE_valores_ltspice.md` | Valores para LTspice (26-sep) | 4 canales, 6 × MCP6004 | `sim/ltspice/README.md` + BoM |
| `docs/afe-emg/resultados_simulacion.md` + `figs/` | Resultados de simulación | 4 canales | `sim/ltspice/README.md`. Ojo: `sim/ltspice/tools/make_figs.py` sigue escribiendo en `docs/afe-emg/figs/` |
| `docs/afe-emg/gemini_1_*.md`, `gemini_2_*.md` | Traspaso a Gemini para diseñar el AFE | 4 canales; era material de traspaso | `sim/ltspice/README.md` |
| `ssr-testbed/docs/` | Arquitectura, pinout y pipeline | NUCLEO-H723ZG, USB-CDC, 4 canales | `README.md`, `n6/README.md` |
| `ssr-testbed/bom/` | BoM y proveedores del testbed | Testbed H723 | `docs/afe-emg/BoM_*.xlsx` |
| `ssr-testbed/dataset/format-spec.md` | Formato `.ssr` | `auravoxd` graba `.avx` | `auravoxd/README.md` |
| `ssr-testbed/hardware/` | Cableado breakout | NUCLEO-H723ZG | `n6/README.md` |
| `ssr-testbed/scripts/` | Setup y flasheo | Firmware H723 | `n6/tools/` |
| `ssr-testbed/firmware/Core/`, `Makefile` | Firmware del H723 (INMP441 por USB-CDC) | Placa y micrófono reemplazados | `ssr-testbed/firmware/n6/`. `auravox_frame.h` salió de aquí a `ssr-testbed/firmware/` |
| `ssr-testbed/pc-tools/ssr-*` | ingest, export, inspect, replay, roundtrip | Formato `.ssr` / USB-CDC; `ssr-ingest` no compila | `auravoxd`, `avxcwt` |
| `sprints/` | Respuestas copiadas de LLM (red neuronal, NPU, UPS) | No son documentación del proyecto | — |
| `respeuesta_iagoogle.md` | Respuesta de LLM sobre un enlace inalámbrico de 20 km para un dron | Otro proyecto | — |
| `red_mel.txt` | Enlace a YAMNet del model zoo de ST | Referencia suelta (NPU, post-Muestra) | — |
| `bom.csv` | Lista de compras con enlaces | Incluye MCP6004 | `docs/afe-emg/BoM_*.xlsx` |
| `RoadmapSSI.xlsx` | Roadmap | El roadmap se quitó del README el 6-oct | `README.md` (estado) |
| `BIOAMP.png`, `BIOAMP1.png` | Imágenes del BioAmp EXG Pill | Sin uso en el repo | Submódulo `BioAmp-EXG-Pill/` |
| `datasheets/` | AD8232, INMP441, MCP6004 | Piezas que ya no se usan | `datasheets/` (raíz) |

Rutas viejas que todavía aparecen en `docs/muestra-tech/plan_hasta_15oct.txt` (plan fechado, no se reescribió).
