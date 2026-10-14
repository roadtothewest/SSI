# Pipeline de Datos

## Etapa 1: Captura (HW + Firmware)

```
┌─────────────────┐     ┌──────────────┐     ┌───────────────┐
│ AFE sEMG 4ch    │────▶│ ADC + DMA    │────▶│ USB CDC       │
│ (ADC 2 kHz/ch)  │     │ Ping-Pong    │     │ Bulk EP       │
└─────────────────┘     └──────────────┘     └───────┬───────┘
                                                      │
┌─────────────────┐     ┌──────────────┐              │
│ INMP441 (I2S)   │────▶│ STM32 DMA    │──────────────┘
│ SR: 16 kHz      │     │ Ping-Pong    │
└─────────────────┘     └──────────────┘
```

## Etapa 2: Ingesta (PC — Go: ssr-ingest)

```
USB CDC stream
  → parser.go: detecta sync word 0xAA55
    → frame.go: decodifica tipo, timestamp, payload
      → ring.go: buffer circular 10 segundos
        → stats.go: muestra tasa, drops, latencia
          → writer.go: escribe a disco (.ssr binario)
```

## Etapa 3: Post-Procesamiento (PC — Python: export.py)

```
.ssr file
  → separar canales (EMG + AUDIO)
    → aplicar CWT a los 4 canales EMG (wavelet Morlet, escalas log 20-500 Hz)
      → mel-espectrograma a AUDIO
        → alinear temporalmente por timestamps
          → exportar a .npz (diccionario con arrays)
            → subir a Google Drive → Colab
```

## Etapa 4: Entrenamiento (Colab)

```
CWT features (EMG, 4 canales) → Conv2D x4 → TCN → vocoder → audio sintetizado
```
