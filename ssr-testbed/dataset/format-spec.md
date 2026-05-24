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
| 2      | 1     | frame_type    | uint8   | 0x01=ACC, 0x02=AUDIO                 |
| 3      | 1     | flags         | uint8   | Bit0: half/full, Bit1: overflow flag |
| 4      | 4     | timestamp     | uint32  | μs desde inicio de captura (little-endian) |
| 8      | 2     | data_len      | uint16  | Bytes de datos que siguen (little-endian) |
| 10     | N     | data          | uint8[] | Datos del frame (ver abajo)          |

**Total cabecera: 10 bytes.**

### ACC Frame (type=0x01)

data contiene muestras de aceleración empaquetadas secuencialmente:

| Subcampo | Tipo      | Descripción                          |
|----------|-----------|--------------------------------------|
| axis     | int16[3]  | X, Y, Z en little-endian por muestra |
| ...      | ...       | Repetir data_len/6 veces             |

Cada muestra = 6 bytes. Para 256 muestras por frame:
data_len = 1536, data = 1536 bytes, frame total = 1546 bytes.

Factor de escala: int16 → g = valor / 16384 (para rango ±2g)

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
[Frame ACC #0] [Frame AUDIO #0] [Frame ACC #1] [Frame AUDIO #1] ...
```

La secuencia exacta depende del orden de llegada por USB-CDC (no se
reordena — los timestamps permiten reconstruir la alineación temporal).

## Sesión

Una sesión se guarda en:

```
dataset/sessions/{YYYY-MM-DD_HHmmss}/
├── metadata.json     → {device, sample_rate, odr, range, duration, notes}
├── data.ssr          → frames binarios
├── info.md           → Notas de la sesión (posición sensor, sujeto, etc.)
└── check             → sha256sum del data.ssr
```

### metadata.json

```json
{
  "session_id": "2026-05-24_143022",
  "device": "NUCLEO-H723ZG",
  "sensors": {
    "acc": { "model": "IIS3DWB", "odr_hz": 26700, "range_g": 2, "samples_per_frame": 256 },
    "audio": { "model": "INMP441", "sample_rate_hz": 16000, "bits": 24, "samples_per_frame": 128 }
  },
  "duration_s": 300,
  "total_frames": { "acc": 31250, "audio": 18750 },
  "notes": "Sensor sobre laringe, sujeto en reposo, voz en inglés"
}
```

## Herramientas

- `ssr-ingest` — genera archivos .ssr desde streaming USB-CDC
- `ssr-inspect` — lee metadatos, imprime frames, valida integridad
- `ssr-replay` — reproduce archivo .ssr a través del mismo pipe (debug)
- `export.py` — convierte .ssr → .npz (CWT features + mel-audio)
