# Documentos vigentes

Una fuente por tema. Si un documento no está en esta tabla, no es la referencia: lo obsoleto está en `archivo/` (ver `archivo/README.md`).

| Tema | Documento vigente |
|---|---|
| Visión general, pipeline y estado | `README.md` (raíz) |
| AFE: esquemático, valores y simulación (3 canales) | `sim/ltspice/AuraVox_AFE.asc` + `sim/ltspice/README.md` |
| AFE: lista de materiales | `docs/afe-emg/BoM_AFE_AuraVox.xlsx` y `BoM_AFE_AuraVox_compacta.xlsx` (+ `.pdf`) |
| AFE: alimentación (LDO TLV75733P, módulos INA333) | `docs/afe-emg/alimentacion_ldo.md` |
| Enlace N6 → Raspberry (bloque SPI, DRDY, pines) | `ssr-testbed/firmware/PROTOCOLO_SPI.md` + `ssr-testbed/firmware/auravox_frame.h` |
| Firmware de captura de la STM32N6570-DK | `ssr-testbed/firmware/n6/README.md` (spec y planes en `n6/docs/`) |
| Servicio y HMI de la Raspberry Pi 5 | `ssr-testbed/pc-tools/auravoxd/README.md` |
| Análisis offline de sesiones `.avx` | `ssr-testbed/pc-tools/avxcwt/main.go` (`go run . sesion.avx`) |
| Muestra TECH 2026 | `docs/muestra-tech/BASES_MT_2026.pdf`; plan de Vicente al 15-oct en `plan_hasta_15oct.txt` (fechado: cita rutas y piezas de antes, como el INMP441) |
| Concepto del proyecto (sep. 2026) | `docs/AuraVox.pdf` |
| Datasheets de piezas en uso | `datasheets/` (INA333, TS922), `docs/afe-emg/datasheets/` (1N4148) |
| Papers | `papers/` (`papers/ubicacion/LEEME_ubicacion_electrodos.md`) |

Pendiente conocido: `sim/ltspice/README.md` y la BoM todavía dicen A1–A3; el firmware lee CH1 en A1, CH2 en A4 y CH3 en A5 (`PROTOCOLO_SPI.md`).
