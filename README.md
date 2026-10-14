# SSI — Silent Speech Interface

Plataforma de captura sincronizada para interfaz de habla silenciosa. Un AFE
sEMG diferencial de **3 canales + RLD** (submentoniano, labio inferior,
cuello/laringe) y un micrófono de referencia entran al **STM32N6570-DK**, que
arma tuplas `{timestamp, ADC1, ADC2, ADC3, voz}` y las envía por **SPI** a una
**Raspberry Pi 5**. La Pi (`auravoxd`, Go) las ordena y sirve una HMI web que
muestra las señales, la CWT y la causalidad sEMG → voz.

**Mantra del proyecto:** matar dos pájaros de un tiro — (1) demostrar
causalidad sEMG → fonemas, no solo correlación, y (2) construir la
plataforma/estación de captura que genera el dataset masivo mínimo para que
el pipeline de software (CWT → Conv2D → TCN → vocoder) generalice más allá
de la demo. Detalle (escrito para 4 canales) en `archivo/docs/refactor-emg-software.md` §0.

> **Sensor (oct. 2026):** potencial mioeléctrico de superficie (sEMG) en
> **3 canales** (CH1 submentoniano, CH2 labio inferior, CH3 cuello/laringe; el
> canal laríngeo es el control del confusor F0), anterior en el tiempo al
> sonido, lo que permite sostener una afirmación de **causalidad** (no solo
> correlación). AFE: módulos INA333 (G ≈ 19,2) + 6 × TS922, ganancia total
> 2500, 20–500 Hz, alimentado por un LDO TLV75733P. Diseño vigente: esquemático y
> notas en `sim/ltspice/` + BoM y alimentación en `docs/afe-emg/`.
> Micrófono: **ADMP401 analógico** (SparkFun) en A3 del DK; el primer INMP441
> salió defectuoso y queda como opción de compilación.

**Producto final:** Dispositivo autónomo 100% embebido (STM32N6 + parlante) que
reconstruye la voz a partir de activación neuromuscular facial. Sin PC.

## Pipeline de la Muestra

```
AFE sEMG (3ch) ──A1/A4/A5── ADC1 2 kHz ──┐
                                         ├── STM32N6570-DK ──SPI 538 B/10 ms + DRDY──→ Raspberry Pi 5
ADMP401 ─────────A3──────── ADC2 64 kHz ─┘   (firmware/n6)                              (auravoxd: HMI web,
                                                                                         CWT, causalidad)
```

Protocolo: `ssr-testbed/firmware/PROTOCOLO_SPI.md`.

## Pipeline del Producto Final

```
AFE sEMG (3ch) ──ADC──→ STM32N6 (M55: CWT + NPU: inferencia + M55: síntesis) ──I2S──→ MAX98357 ──→ parlante
```

## Estructura del Repositorio

```
docs/                  → índice de documentos vigentes (docs/README.md)
├── afe-emg/           → BoM, alimentación (LDO), datasheet 1N4148
└── muestra-tech/      → bases y plan de la Muestra TECH
sim/ltspice/           → esquemático y simulación del AFE (fuente de verdad del hardware)
datasheets/            → INA333, TS922
papers/                → ubicación de electrodos y causalidad sEMG → voz
ssr-testbed/
├── firmware/
│   ├── PROTOCOLO_SPI.md   → bloque SPI, tuplas, DRDY, pines
│   ├── auravox_frame.h    → struct C del bloque (referencia del protocolo)
│   └── n6/                → firmware de captura del N6
└── pc-tools/
    ├── auravoxd/          → servicio de la Raspberry: SPI + HMI web + CWT + causalidad
    └── avxcwt/            → análisis offline de sesiones .avx
archivo/               → documentos y código obsoletos (4 canales, H723, .ssr), con índice
```

## Estado del Proyecto (13-oct-2026)

| Componente | Estado |
|---|---|
| AFE sEMG, 3 canales + RLD | Armado en perfboard; LDO validado (3,3 V); validación del AFE en curso |
| Cables de electrodo | 4 cables dobles de 1,5 m (3 canales + RLD), por adaptar a plug DC (CPL175 / SP-2827) |
| Firmware N6 (`firmware/n6`) | Captura EMG 2 kHz + ADMP401 16 kHz, enlace SPI con DRDY: probado en el DK y con la Pi 5 (0 CRC, 0 huecos en 10 min) |
| `auravoxd` (Raspberry) | HMI web (señales, espectro, causalidad, sesión), grabación `.avx`; recibe 100 bloques/s del DK |
| Prueba con el AFE real | Pendiente: niveles en A1/A4/A5 y prueba en la piel |
| Producto final STM32N6 | Planificado (post-Muestra) |

## Muestra TECH 2026

Presentación del prototipo funcional de SSI en la Muestra TECH 2026.
Criterios de evaluación: Creatividad (40%), Nivel Técnico (25%),
Presentación (20%), Impacto Social (15%).
