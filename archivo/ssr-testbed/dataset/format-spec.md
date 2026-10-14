# Formato de Archivo .ssr (Silent Speech Raw)

## Estructura General

.ssr es un formato binario secuencial de frames. Sin cabecera global
—cada frame es autodescriptivo— para permitir streaming directo a disco.

```
Archivo .ssr = Frame[0] + Frame[1] + ... + Frame[N]
```

## Formato de Frame

| Offset | Bytes | Campo         | Tipo    | Descripción                          |
|--------|-------|---------------|---------|--------------------------------------|
| 0      | 1     | sync0         | uint8   | 0xAA — Sync word byte 1              |
| 1      | 1     | sync1         | uint8   | 0x55 — Sync word byte 2              |
| 2      | 1     | frame_type    | uint8   | 0x02=AUDIO, 0x03=EMG                 |
| 3      | 1     | flags         | uint8   | Bit0: half/full, Bit1: overflow flag |
| 4      | 4     | timestamp     | uint32  | μs desde inicio de captura (little-endian) |
| 8      | 2     | data_len      | uint16  | Bytes de datos que siguen (little-endian) |
| 10     | N     | data          | uint8[] | Datos del frame (ver abajo)          |

**Total cabecera: 10 bytes.**

### EMG Frame (type=0x03)

data contiene muestras del ADC de los 4 canales sEMG, intercaladas por muestra
(docs/afe-emg/AFE_EMG_Diseno.md §5.1):

| Subcampo | Tipo      | Descripción                              |
|----------|-----------|------------------------------------------|
| ch       | int16[4]  | CH1, CH2, CH3, CH4 en little-endian      |
| ...      | ...       | Repetir data_len/8 veces                 |

Cada muestra = 8 bytes. Para 100 muestras por frame (50 ms a 2 kHz):
data_len = 800, data = 800 bytes, frame total = 810 bytes.

Escala: códigos del ADC (sin signo desplazado a int16 centrado en VREF);
voltaje referido a la entrada = V_ADC / 503 (ganancia nominal del AFE).

### AUDIO Frame (type=0x02)

data contiene muestras de audio I2S 24-bit alineadas a left en int32:

| Subcampo | Tipo      | Descripción                          |
|----------|-----------|--------------------------------------|
| sample   | int32     | 24-bit en MSB, LE                    |
| ...      | ...       | Repetir data_len/4 veces             |

Cada muestra = 4 bytes. Para 128 muestras por frame:
data_len = 512, data = 512 bytes, frame total = 522 bytes.

Formato PCM 24-bit, signed, little-endian. Escala: ±2^23 = ±1.0

## Estructura de Archivo (Resultante)

```
[Frame EMG #0] [Frame AUDIO #0] [Frame EMG #1] [Frame AUDIO #1] ...
```

La secuencia exacta depende del orden de llegada por USB-CDC (no se
reordena — los timestamps permiten reconstruir la alineación temporal).

## Sesión

Una sesión se guarda en:

```
dataset/sessions/{YYYY-MM-DD_HHmmss}/
├── metadata.json     → {device, sample_rate, odr, range, duration, notes}
├── data.ssr          → frames binarios
├── info.md           → Notas de la sesión (posición de electrodos, sujeto, etc.)
└── check             → sha256sum del data.ssr
```

### metadata.json

```json
{
  "session_id": "2026-05-24_143022",
  "device": "NUCLEO-H723ZG",
  "sensors": {
    "emg": { "model": "AFE sEMG 4ch (INA333 + MCP6004)", "fs_hz": 2000, "channels": 4, "gain": 503, "samples_per_frame": 100 },
    "audio": { "model": "INMP441", "sample_rate_hz": 16000, "bits": 24, "samples_per_frame": 128 }
  },
  "duration_s": 300,
  "total_frames": { "emg": 6000, "audio": 37500 },
  "notes": "Electrodos submentoniano/platisma/labio inferior/laringe, RLD en clavícula"
}
```

## Herramientas

- `ssr-ingest` — genera archivos .ssr desde streaming USB-CDC
- `ssr-inspect` — lee metadatos, imprime frames, valida integridad
- `ssr-replay` — reproduce archivo .ssr a través del mismo pipe (debug)
- `export.py` — convierte .ssr → .npz (CWT de los 4 canales EMG + mel-audio)
