# Clasificador de vocales para la NPU del N6 (`auravox_vocales_npu.ipynb`)

Notebook de Google Colab que entrena el clasificador de vocales sEMG para la NPU (Neural-ART) del STM32N6570-DK y deja listo lo que necesitan STM32Cube AI Studio y el firmware.

```
.avx + .json (auravoxd) → µV → CWT Morlet (= auravoxd/dsp/cwt.go) → ventanas de 320 ms, magnitud + fase
→ CNN feed-forward (PyTorch, Adam + OneCycle, 10 épocas) → ONNX opset 13 → int8 QDQ por canal → AI Studio
```

Entra solo el escalograma de **CH3** (laringe). Las etiquetas salen del **escalograma del audio** (ADMP401), que marca voz y silencio.

El notebook se genera con `generar_notebook.py`: se edita ahí y se corre `python3 generar_notebook.py`. La escritura es atómica, para que un apagón no deje el `.ipynb` corrupto.

## Uso

1. Abrir en Colab (*Archivo → Subir notebook*) con runtime GPU T4.
2. Dejar las grabaciones (`.avx` + `.json` de auravoxd) en `MyDrive/AuraVox/vocales`. No hace falta el protocolo completo: con 4 por vocal entrena igual. La clase de cada una se da con `ETIQUETAS` en la configuración, con un `etiquetas.csv` (`archivo,clase,ronda`) o con el nombre del archivo (`r1_a.avx`, `silencio_2.avx`). Si falta, el notebook deja una plantilla. Sin grabaciones corre en modo demo.
3. *Ejecutar todo*. Al final se descarga `auravox_vocales_export.zip`; con datos reales también se copia a Drive.

## Qué sale

| Archivo | Para qué |
|---|---|
| `auravox_vocales_int8.onnx` | STM32Cube AI Studio (NPU) |
| `auravox_vocales_fp32.onnx` | referencia |
| `auravox_vocales.h` | firmware: CWT, normalización, cuantización de las entradas y clases |
| `auravox_vocales_prueba.h` | firmware: vectores ADC → dB → int8 → logits para verificar el port |
| `auravox_vocales_val.npz` / `_int8.npz` | validación en AI Studio (`m_inputs_1/2`, `m_outputs_1` one-hot) |
| `etiquetas.csv`, `informe.json`, `*.png` | etiquetas usadas, métricas y figuras |

## Modelo

- Entradas (CH3): `cwt_mag` `[1,1,32,32]` y `cwt_fase` `[1,2,32,32]` (cos/sin), int8 NCHW. Salida: `logits` `[1,7]` int8 para `desconectado, reposo, a, e, i, o, u` (las clases sin grabaciones se quitan). Los canales se eligen en `CANALES`.
- Operadores: Conv, ReLU, MaxPool, AveragePool, Concat, Gemm y Flatten, todos en HW según *ST Neural-ART NPU – Supported operators and limitations* (ST Edge AI Core 4.0). Son unos 21 k parámetros; el ONNX int8 pesa unos 39 KiB.
- Opciones: `CANALES`, `USAR_FASE`, `FASE` (`relativa` necesita ≥ 2 canales), `ATENCION_SE` (squeeze-excitation, también todo HW) y `COMPARAR_VARIANTES` (¿aporta la fase?).

## Verificado (2026-10-15, modo demo, sin herramientas de ST)

- Con solo CH3, 29 grabaciones (4 por vocal, 3 de `u`) y etiquetas por `ETIQUETAS` con el alias `silencio`: corre de punta a punta; sin etiquetas se detiene y deja la plantilla. El header compila sin avisos y reproduce el int8 esperado.
- Con los 3 canales (versión anterior), el notebook corre de punta a punta con torch 2.12.1, onnx 1.20.1 y onnxruntime 1.24.3: con fase, sin fase y con SE + fase relativa.
- La CWT coincide con una traducción literal de `Bank.Column` y da |W| = A para una senoide.
- El ONNX int8 queda en opset 13 / IR 7, con todos los nodos entre pares Q/DQ.
- Con los 3 canales, un programa en C que sigue solo `auravox_vocales.h` reproduce en float32 los vectores de `auravox_vocales_prueba.h`: dB con error ≤ 0,0013 dB, `cwt_mag` idéntico y `cwt_fase` a ±1 LSB (4 de 6144 valores).

Pendiente: correrlo con las grabaciones reales y revisar en AI Studio que todas las capas queden en épocas de hardware.
