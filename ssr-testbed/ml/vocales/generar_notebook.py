"""Genera auravox_vocales_npu.ipynb (en esta misma carpeta) a partir de las celdas de abajo.

Uso: python3 generar_notebook.py
El notebook se edita aquí y se regenera; así no depende de que el .ipynb sobreviva.
"""
import json
import os

CELLS = []


def md(s):
    CELLS.append(("markdown", s.strip("\n")))


def code(s):
    CELLS.append(("code", s.strip("\n")))


md(r'''
# AuraVox: clasificador de vocales sEMG para la NPU del STM32N6570-DK

`.avx` de auravoxd → µV → CWT Morlet (la misma de `auravoxd/dsp/cwt.go`) → ventanas de **magnitud y fase** del escalograma de **CH3** → CNN feed-forward → ONNX → **int8 QDQ** → STM32Cube AI Studio (Neural-ART)

| | Forma (NCHW) | Contenido |
|---|---|---|
| entrada 1 `cwt_mag` | `[1, 1, 32, 32]` | escalograma de **CH3** (laringe): \|CWT\| en dB µV normalizada por frecuencia; 32 columnas de 10 ms (320 ms) × 32 frecuencias de 20 a 500 Hz |
| entrada 2 `cwt_fase` | `[1, 2, 32, 32]` | fase de la CWT de CH3 como cos y sin (sin el salto en ±π) |
| salida `logits` | `[1, 7]` (menos si falta alguna clase) | `desconectado, reposo, a, e, i, o, u`; el argmax se hace en el M55 |

- Los canales de entrada se eligen en `CANALES` (por defecto solo CH3).
- La etiqueta sale del **escalograma del audio** (ADMP401), que marca dónde hay voz y dónde silencio.
- El modelo usa solo operadores que la tabla oficial de ST Edge AI Core 4.0 asigna a la NPU, y se cuantiza como pide ST (QDQ, int8 por canal, ss/sa).

**Runtime:** conviene GPU T4 (*Entorno de ejecución → Cambiar tipo de entorno*). En CPU también funciona, pero la validación cruzada tarda unos 10–15 min en vez de 1–2.

**Sin grabaciones**, el notebook genera un dataset sintético con el mismo formato (`MODO_DEMO`). Sirve para probar el flujo y para avanzar con AI Studio y el firmware mientras se graba; no dice nada de la exactitud real.
''')

md(r'''
## Grabaciones y etiquetas

**Qué subir:** a una carpeta de Drive (`CARPETA_DRIVE`), los `.avx` de auravoxd **con su `.json`**. Se descargan desde la HMI (*Sesión → Grabaciones*) o desde `/home/aura/auravox` en la Pi.

**Protocolo ideal:** 5 rondas, una por tono, de grave a agudo: `desconectado, reposo, a, e, i, o, u, reposo` (40 grabaciones de 10–15 s).
- **No hace falta que estén todas.** Con 4 por vocal, o con alguna menos, el notebook entrena igual.
- Las clases que no tengan grabaciones se quitan del modelo.
- La validación cruzada usa la ronda si está en todas las etiquetas. Si no, reparte las grabaciones de cada clase en tantos pliegues como tenga la vocal con menos (2 a 5).

**Cómo sabe la clase de cada grabación** (en este orden de prioridad):
1. `ETIQUETAS` en la configuración: `{'20261015-143012': 'a', ...}`.
2. `etiquetas.csv` junto a los `.avx`, con columnas `archivo,clase,ronda` (ronda opcional).
3. El nombre del archivo: `r3_a.avx`, `a_2.avx`, `silencio_1.avx`… (`silencio` = `reposo`).
4. El orden cronológico, solo si son exactamente las 40 del protocolo.

Si no puede decidir, el notebook se detiene y deja una plantilla de `etiquetas.csv`. La plantilla trae ya `desconectado` y `reposo` según la condición marcada en la HMI; solo hay que escribir las vocales.

**Vocal sostenida o intercalada con silencio:** sirven las dos. Los silencios entre vocales se usan como `reposo` si están lejos de la voz (`GUARDA_REPOSO_MS`), porque el sEMG se adelanta al sonido.
''')

code(r'''
# Dependencias: torch, numpy, scipy, pandas y matplotlib ya vienen en Colab.
!pip -q install onnx==1.20.1 onnxruntime==1.24.3 onnxscript==0.6.2
''')

code(r'''
import os, sys, io, re, json, math, time, shutil, zipfile, warnings, itertools
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.fft as sfft
import scipy.ndimage as ndi
import scipy.signal as sps
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch
import torch
import torch.nn as nn
import torch.nn.functional as F
import onnx
import onnxruntime as ort
from onnxruntime.quantization import (CalibrationDataReader, CalibrationMethod, QuantFormat,
                                      QuantType, quantize_static)
from onnxruntime.quantization.shape_inference import quant_pre_process
try:
    from IPython.display import display
except ImportError:
    display = print

EN_COLAB = 'google.colab' in sys.modules
DEV = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f'torch {torch.__version__} · onnx {onnx.__version__} · onnxruntime {ort.__version__} · {DEV}')
''')

md(r'''
## Configuración
''')

code(r'''
# === CONFIG ===
CARPETA_DRIVE = '/content/drive/MyDrive/AuraVox/vocales'  # .avx + .json (+ etiquetas.csv opcional)
CARPETA_LOCAL = '/content/avx'                            # destino del .zip si se sube a mano
SALIDA = '/content/auravox_vocales'                       # resultados
MODO_DEMO = None          # None: demo solo si no hay grabaciones; True: forzar la demo
DURACION_DEMO_S = 12.0

# Señal: igual que auravoxd (stream.Conv). El .json de cada sesión trae su propia conversión.
FS, FS_VOZ, NCH = 2000, 16000, 3   # NCH: canales EMG en el .avx (CH1, CH2, CH3)
CANALES = [2]               # canales que entran al modelo: solo CH3 (laringe). Índices de adc[]: 0 = CH1 … 2 = CH3
CONV = dict(VrefADC=1.8, GDK=0.5437, VMid=1.65, Gain=2500.0)
RETARDO_VOZ_MUESTRAS = 12   # 0,75 ms del filtro de decimación de la ADMP401, a 16 kHz

# CWT: auravoxd/dsp/cwt.go (Morlet ω0 = 6) con los parámetros de analysis.go
FMIN, FMAX, NF, W0 = 20.0, 500.0, 32, 6.0
HOP_MS = 10
T_COLS = 32                 # columnas por ventana: 32 × 10 ms = 320 ms (16, 32 o 64)
DB_MIN, DB_MAX = -20.0, 60.0
Z_CLIP = 5.0                # recorte de la magnitud normalizada
USAR_FASE = True            # False: una sola entrada (magnitud)
FASE = 'absoluta'           # 'absoluta': cos/sin de φ de cada canal
                            # 'relativa': cos/sin de las diferencias de fase entre canales (requiere ≥ 2 canales)

# Clases y etiquetado. Las clases sin grabaciones se quitan solas.
CLASES = ['desconectado', 'reposo', 'a', 'e', 'i', 'o', 'u']
ALIAS = {'silencio': 'reposo', 'sin_electrodos': 'desconectado', 'desc': 'desconectado'}
ETIQUETAS = {}              # opcional, en vez de etiquetas.csv: {'20261015-143012': 'a', ...} (nombre sin .avx → clase)
PLAN_RONDA = ['desconectado', 'reposo', 'a', 'e', 'i', 'o', 'u', 'reposo']
N_RONDAS = 5
BORDE_S = 0.5               # se descartan el inicio y el final de cada grabación
# Voz y silencio se detectan con el escalograma del audio (misma CWT, 20–500 Hz: la banda de F0)
UMBRAL_VOZ_DB = 15.0        # voz: energía del escalograma del audio > piso de ruido + 15 dB
UMBRAL_SILENCIO_DB = 6.0    # silencio: energía < piso + 6 dB
MIN_VOZ_MS, MAX_HUECO_MS = 200, 150
GUARDA_VOZ_MS = 150         # margen dentro de cada tramo de voz (transiciones)
GUARDA_REPOSO_MS = 400      # silencio usable como reposo: a ≥ 400 ms de la voz
USAR_SILENCIOS_DE_VOCALES = True

# Entrenamiento
EPOCAS, BATCH, LR_MAX, WEIGHT_DECAY = 10, 64, 3e-3, 1e-4
DROPOUT, LABEL_SMOOTHING = 0.3, 0.05
PASO_TRAIN, PASO_VAL = 4, 8          # paso entre ventanas, en columnas
AUG_GANANCIA_DB, AUG_PENDIENTE_DB, AUG_RUIDO_DB = 3.0, 2.0, 0.5
ATENCION_SE = False         # atención por canales (squeeze-excitation), con operadores de hardware
COMPARAR_VARIANTES = False  # True: validación cruzada también sin fase (y con fase relativa si hay ≥ 2 canales)
SEMILLA = 0
''')

code(r'''
assert T_COLS in (16, 32, 64) and NF % 8 == 0, 'T_COLS debe ser 16, 32 o 64 y NF múltiplo de 8'
HOP = FS * HOP_MS // 1000
NIN = len(CANALES)                       # canales EMG de entrada al modelo
assert FASE == 'absoluta' or NIN > 1, "FASE = 'relativa' necesita al menos 2 canales en CANALES"
NOMBRE_CANAL = ['CH1', 'CH2', 'CH3']


def definir_clases(clases):
    global CLASES, NCLASES, I_DESC, I_REPOSO, VOCALES
    CLASES = list(clases)
    NCLASES = len(CLASES)
    I_DESC = CLASES.index('desconectado') if 'desconectado' in CLASES else None
    I_REPOSO = CLASES.index('reposo') if 'reposo' in CLASES else None
    VOCALES = [c for c in CLASES if c not in ('desconectado', 'reposo')]


definir_clases(CLASES)
COND_HMI = {'desconectado': 'desconectado', 'reposo': 'reposo', **{v: 'vocal' for v in VOCALES}}
OUT = Path(SALIDA)
EXP = OUT / 'export'
EXP.mkdir(parents=True, exist_ok=True)
np.random.seed(SEMILLA)
torch.manual_seed(SEMILLA)

# Figuras: tinta neutra, ejes discretos y un color fijo por clase
plt.rcParams.update({
    'figure.dpi': 110, 'figure.facecolor': '#fcfcfb', 'axes.facecolor': '#fcfcfb',
    'axes.edgecolor': '#c9c8c2', 'axes.labelcolor': '#52514e', 'axes.titlecolor': '#0b0b0b',
    'xtick.color': '#52514e', 'ytick.color': '#52514e', 'text.color': '#0b0b0b',
    'axes.spines.top': False, 'axes.spines.right': False, 'axes.titlesize': 10,
    'axes.titlelocation': 'left', 'font.size': 9, 'lines.linewidth': 2, 'legend.frameon': False})
COLOR_CLASE = dict(zip(CLASES, ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6']))
COLOR_IGNORADO = '#e4e3de'
AZUL = LinearSegmentedColormap.from_list(
    'azul', ['#fcfcfb', '#cde2fb', '#86b6ef', '#3987e5', '#1c5cab', '#0d366b'])
''')

md(r'''
## Lectura de las grabaciones `.avx`

Un `.avx` son bloques de 538 B seguidos, tal como llegan por SPI (`firmware/Core/Inc/auravox_frame.h`, little-endian):

- cabecera: `AA 55 04 01`, `seq`, `t0_us`, `n = 20` y `flags`;
- 20 tuplas de 500 µs, cada una con `ts_us`, `adc[3]` y `voz[8]`;
- CRC-16/CCITT-FALSE.

Una grabación se corta en **tramos contiguos** donde haya un salto de `seq`, un CRC malo o un overrun del ADC (`flags` bit 0). La CWT nunca cruza un hueco.
''')

code(r'''
BLOQUE = 538
DT_BLOQUE = np.dtype([
    ('sync', 'u1', (2,)), ('tipo', 'u1'), ('ver', 'u1'),
    ('seq', '<u4'), ('t0', '<u4'), ('n', '<u2'), ('flags', '<u2'),
    ('t', [('ts', '<u4'), ('adc', '<u2', (3,)), ('voz', '<i2', (8,))], (20,)),
    ('crc', '<u2')])
assert DT_BLOQUE.itemsize == BLOQUE


def _tabla_crc():
    t = np.zeros(256, np.uint16)
    for i in range(256):
        c = i << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
        t[i] = c
    return t


TABLA_CRC = _tabla_crc()


def crc16(raw):
    """CRC-16/CCITT-FALSE de cada fila de raw [n, L] (uint8), como frame.CRC16."""
    crc = np.full(raw.shape[0], 0xFFFF, np.uint16)
    for i in range(raw.shape[1]):
        crc = (crc << np.uint16(8)) ^ TABLA_CRC[(crc >> np.uint16(8)) ^ raw[:, i]]
    return crc


assert crc16(np.frombuffer(b'123456789', np.uint8)[None])[0] == 0x29B1


def leer_avx(ruta):
    b = np.fromfile(ruta, np.uint8)
    n = len(b) // BLOQUE
    if len(b) % BLOQUE:
        print(f'  aviso {Path(ruta).name}: {len(b) % BLOQUE} B sobrantes al final')
    raw = b[:n * BLOQUE].reshape(n, BLOQUE)
    blk = raw.view(DT_BLOQUE)[:, 0]
    ok = ((blk['sync'][:, 0] == 0xAA) & (blk['sync'][:, 1] == 0x55) & (blk['tipo'] == 4)
          & (blk['ver'] == 1) & (blk['n'] == 20) & (crc16(raw[:, :-2]) == blk['crc'])
          & ((blk['flags'] & 1) == 0))
    return blk, ok


def tramos_contiguos(blk, ok):
    idx = np.flatnonzero(ok)
    if idx.size == 0:
        return []
    seq = blk['seq'][idx].astype(np.int64)
    cortes = np.flatnonzero((np.diff(idx) != 1) | (np.diff(seq) != 1)) + 1
    return np.split(idx, cortes)


def leer_sesion(ruta):
    """Tramos contiguos de una sesión: códigos del ADC, sEMG en µV y voz en fracción del fondo de escala."""
    js = Path(ruta).with_suffix('.json')
    meta = json.loads(js.read_text()) if js.exists() else {}
    conv = {**CONV, **(meta.get('conv') or {})}
    blk, ok = leer_avx(ruta)
    partes = []
    for g in tramos_contiguos(blk, ok):
        cod = blk['t']['adc'][g].reshape(-1, NCH)
        uv = (cod * conv['VrefADC'] / 4095 / conv['GDK'] - conv['VMid']) / conv['Gain'] * 1e6
        voz = blk['t']['voz'][g].reshape(-1) / 32768.0
        partes.append(dict(cod=cod.copy(), uv=uv, voz=voz, seq0=int(blk['seq'][g[0]])))
    return partes, dict(bloques=len(blk), malos=int((~ok).sum()), tramos=len(partes), conv=conv)
''')

md(r'''
### Dataset de demostración

Grabaciones sintéticas con el mismo protocolo, formato y nombres que auravoxd:

- sEMG coloreado con un perfil por vocal en los 3 canales (amplitud y banda), y el canal laríngeo crece con el tono;
- piso del AFE y 50 Hz;
- voz armónica con el sEMG adelantado 80 ms;
- rondas 1–2 sostenidas, rondas 3–5 intercaladas;
- un hueco de `seq` para probar el corte en tramos.

Sirve para probar el flujo y para el port del firmware; **no dice nada sobre la exactitud real**.
''')

code(r'''
def escribir_avx(ruta, cod, voz, seq0=0, hueco=False):
    nb = len(cod) // 20
    blk = np.zeros(nb, DT_BLOQUE)
    blk['sync'] = (0xAA, 0x55)
    blk['tipo'], blk['ver'], blk['n'] = 4, 1, 20
    seq = (seq0 + np.arange(nb)).astype(np.uint32)
    ts = (10000 * seq[:, None].astype(np.uint64) + 500 * np.arange(20)).astype(np.uint32)
    blk['seq'], blk['t0'] = seq, ts[:, 0]
    blk['t']['ts'] = ts
    blk['t']['adc'] = cod[:nb * 20].reshape(nb, 20, NCH)
    blk['t']['voz'] = voz[:nb * 160].reshape(nb, 20, 8)
    blk['crc'] = crc16(blk.view(np.uint8).reshape(nb, BLOQUE)[:, :-2])
    if hueco:  # 3 bloques perdidos a mitad de la grabación
        blk = np.delete(blk, np.arange(nb // 2, nb // 2 + 3))
    blk.tofile(ruta)
    return len(blk)


def _ruido_banda(rng, n, fc, octavas):
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / FS)
    x = np.fft.irfft(X * np.exp(-0.5 * (np.log2(np.maximum(f, 1e-3) / fc) / (octavas / 2)) ** 2), n)
    return x / (x.std() + 1e-12)


def generar_demo(carpeta, dur_s=DURACION_DEMO_S, semilla=1):
    rng = np.random.default_rng(semilla)
    carpeta = Path(carpeta)
    if carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True)
    perfil = {'a': ([30, 10, 14], 85), 'e': ([20, 18, 20], 105), 'i': ([14, 30, 26], 125),
              'o': ([26, 24, 17], 95), 'u': ([10, 38, 11], 70)}       # µV por canal, centro en Hz
    f0_ronda = [110, 140, 175, 220, 270, 320, 380]
    n = int(dur_s * FS) // 20 * 20
    t, tv = np.arange(n) / FS, np.arange(8 * n) / FS_VOZ
    inicio = dt.datetime(2026, 10, 14, 10, 0, 0)
    k = 0
    for r in range(1, N_RONDAS + 1):
        for clase in PLAN_RONDA:
            gan = 10 ** (rng.uniform(-2, 2, NCH) / 20)                # impedancia de cada electrodo
            uv = 1.5 * np.stack([_ruido_banda(rng, n, 150, 3) for _ in range(NCH)], 1)
            uv += 0.8 * np.sin(2 * np.pi * 50 * t + rng.uniform(0, 2 * np.pi))[:, None]
            voz = 10 ** (-62 / 20) * rng.standard_normal(8 * n)
            if clase == 'desconectado':
                uv += 350 * rng.uniform(0.6, 1.4, NCH) * np.sin(2 * np.pi * 50 * t + rng.uniform(0, 6.3))[:, None]
                uv += 60 * np.sin(2 * np.pi * 150 * t)[:, None] + 25 * rng.standard_normal((n, NCH))
            elif clase in perfil:
                amp, fc = perfil[clase]
                tramos_voz = ([(1.0, dur_s - 1.0)] if r <= 2 else
                              [(a, a + 1.6) for a in np.arange(0.8, dur_s - 1.6, 2.8)])
                act, act_v = np.zeros(n), np.zeros(8 * n)
                for a, b in tramos_voz:
                    act[(t >= a - 0.08) & (t < b - 0.04)] = 1             # el sEMG se adelanta a la voz
                    act_v[(tv >= a) & (tv < b)] = 1
                act = np.convolve(act, np.hanning(121) / np.hanning(121).sum(), 'same')
                act_v = np.convolve(act_v, np.hanning(961) / np.hanning(961).sum(), 'same')
                fcr = fc * rng.uniform(0.92, 1.08)
                for c in range(NCH):
                    a_c = amp[c] * ((0.6 + 0.2 * r) if c == 2 else 1.0)   # laringe: sube con el tono
                    mod = 1 + 0.2 * np.sin(2 * np.pi * 0.5 * t + rng.uniform(0, 6.3))
                    uv[:, c] += a_c * gan[c] * mod * act * _ruido_banda(rng, n, fcr * (1 + 0.1 * c), 1.2)
                f0 = f0_ronda[r - 1] * (1 + 0.01 * np.sin(2 * np.pi * 5 * tv))
                fase = 2 * np.pi * np.cumsum(f0) / FS_VOZ
                tono = sum(np.sin(h * fase) / h for h in range(1, 9))
                voz += 0.2 * act_v * tono / tono.std()
            cod = np.clip(np.round((CONV['VMid'] + uv * 1e-6 * CONV['Gain']) * CONV['GDK']
                                   / CONV['VrefADC'] * 4095), 0, 4095).astype(np.uint16)
            vi16 = np.clip(np.round(voz * 32768), -32768, 32767).astype(np.int16)
            nombre = (inicio + dt.timedelta(seconds=40 * k)).strftime('%Y%m%d-%H%M%S')
            nb = escribir_avx(carpeta / f'{nombre}.avx', cod, vi16, seq0=1000 * k,
                              hueco=(r == 2 and clase == 'e'))
            meta = dict(start=inicio.isoformat(), stop=inicio.isoformat(), blockSize=BLOQUE, conv=CONV,
                        hopMs=HOP_MS, blocks=nb, dropped=0, marks=[dict(block=0, cond=COND_HMI[clase])],
                        utterances=None)
            (carpeta / f'{nombre}.json').write_text(json.dumps(meta, indent=2))
            k += 1
''')

md(r'''
## Datos

Por defecto se leen de `CARPETA_DRIVE`. Para subir un `.zip` a mano, poner `SUBIR_ZIP = True` en la celda siguiente.
''')

code(r'''
SUBIR_ZIP = False
if SUBIR_ZIP and EN_COLAB:
    from google.colab import files
    for nombre, datos in files.upload().items():
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            z.extractall(CARPETA_LOCAL)
        print('extraído', nombre, '→', CARPETA_LOCAL)
''')

code(r'''
def buscar_grabaciones():
    if EN_COLAB and CARPETA_DRIVE.startswith('/content/drive') and not Path('/content/drive/MyDrive').exists():
        try:
            from google.colab import drive
            drive.mount('/content/drive')
        except Exception as e:
            print('Drive no quedó montado:', e)
    for c in (CARPETA_DRIVE, CARPETA_LOCAL):
        if c and Path(c).is_dir():
            avx = sorted(Path(c).rglob('*.avx'))
            if avx:
                return Path(c), avx
    return None, []


CARPETA, ARCHIVOS = buscar_grabaciones()
DEMO = (not ARCHIVOS) if MODO_DEMO is None else bool(MODO_DEMO)
if DEMO:
    CARPETA = OUT / 'demo_avx'
    generar_demo(CARPETA)
    ARCHIVOS = sorted(CARPETA.glob('*.avx'))
    print(f'MODO DEMO: {len(ARCHIVOS)} grabaciones sintéticas en {CARPETA}')
else:
    print(f'{len(ARCHIVOS)} grabaciones en {CARPETA}')
RUTA = {a.name: a for a in ARCHIVOS}
assert len(RUTA) == len(ARCHIVOS), 'hay .avx con el mismo nombre en distintas subcarpetas'
''')

code(r'''
def _normalizar(clase):
    c = str(clase).strip().lower()
    return ALIAS.get(c, c)


def _clase_de_nombre(stem):
    toks = [_normalizar(t) for t in re.split(r'[_\-\s.]+', stem.lower())]
    hits = sorted({t for t in toks if t in CLASES})
    return hits[0] if len(hits) == 1 else None


def _ronda_de_nombre(stem):
    m = re.search(r'(?:^|[_\-\s])r(\d+)(?=$|[_\-\s])', stem, re.I)
    return int(m.group(1)) if m else np.nan


def _cond_json(nombre):
    js = RUTA[nombre].with_suffix('.json')
    marcas = (json.loads(js.read_text()).get('marks') or []) if js.exists() else []
    return marcas[0]['cond'] if marcas else ''


def armar_etiquetas():
    nombres = [a.name for a in ARCHIVOS]
    csv = CARPETA / 'etiquetas.csv'
    if ETIQUETAS:
        df = pd.DataFrame({'archivo': nombres,
                           'clase': [ETIQUETAS.get(a.stem, ETIQUETAS.get(a.name, '')) for a in ARCHIVOS],
                           'ronda': [_ronda_de_nombre(a.stem) for a in ARCHIVOS]})
        origen = 'ETIQUETAS de la configuración'
    elif csv.exists():
        df = pd.read_csv(csv, dtype={'archivo': str, 'clase': str})
        if 'ronda' not in df:
            df['ronda'] = np.nan
        origen = f'{csv}'
    elif all(_clase_de_nombre(a.stem) for a in ARCHIVOS):
        df = pd.DataFrame({'archivo': nombres,
                           'clase': [_clase_de_nombre(a.stem) for a in ARCHIVOS],
                           'ronda': [_ronda_de_nombre(a.stem) for a in ARCHIVOS]})
        origen = 'nombres de archivo'
    elif len(nombres) == len(PLAN_RONDA) * N_RONDAS:
        plan = [(r, c) for r in range(1, N_RONDAS + 1) for c in PLAN_RONDA]
        df = pd.DataFrame({'archivo': nombres, 'clase': [c for _, c in plan], 'ronda': [r for r, _ in plan]})
        origen = 'orden cronológico + protocolo (REVISAR que coincida con lo grabado)'
    else:
        # Plantilla: desconectado y reposo salen de la condición marcada en la HMI; las vocales hay que escribirlas
        cond = [_cond_json(n) for n in nombres]
        pre = [c if c in ('desconectado', 'reposo') else '' for c in cond]
        plantilla = OUT / 'etiquetas.csv'
        pd.DataFrame({'archivo': nombres, 'clase': pre, 'ronda': '', 'cond_hmi': cond}).to_csv(plantilla, index=False)
        print(pd.read_csv(plantilla).fillna('').to_string(index=False))
        raise RuntimeError(
            f'No se puede saber la clase de las {len(nombres)} grabaciones por el nombre ni por el orden del protocolo. '
            f'Completar la columna clase de {plantilla} (a, e, i, o, u, reposo/silencio, desconectado; ronda opcional), '
            f'dejarlo como etiquetas.csv junto a los .avx y volver a ejecutar. '
            f'Alternativa: renombrar a r1_a.avx/r1_a.json, o llenar ETIQUETAS en la configuración.')
    df = df[df['archivo'].isin(RUTA)].reset_index(drop=True)
    df['clase'] = [_normalizar(c) if isinstance(c, str) else '' for c in df['clase']]
    sin_clase = df.loc[df['clase'] == '', 'archivo'].tolist()
    if sin_clase:
        print(f'AVISO: {len(sin_clase)} grabaciones sin clase quedan fuera: {sin_clase}')
        df = df[df['clase'] != ''].reset_index(drop=True)
    desconocidas = sorted(set(df['clase']) - set(CLASES))
    assert not desconocidas, f'clases desconocidas en las etiquetas: {desconocidas}'
    df['cond_hmi'] = [_cond_json(a) for a in df['archivo']]
    distinta = [bool(c) and c != COND_HMI[k] for c, k in zip(df['cond_hmi'], df['clase'])]
    print('Etiquetas desde:', origen)
    if any(distinta):
        print('AVISO: la condición marcada en la HMI no coincide con la clase en:')
        print(df.loc[distinta, ['archivo', 'clase', 'cond_hmi']].to_string(index=False))
    df.to_csv(EXP / 'etiquetas.csv', index=False)
    return df


ETIQ = armar_etiquetas()
_conteo = ETIQ.groupby('clase').size().reindex(CLASES, fill_value=0)
if (_conteo == 0).any():
    print('Sin grabaciones, se quitan del modelo:', _conteo.index[_conteo == 0].tolist())
definir_clases([c for c in CLASES if _conteo[c] > 0])
assert len(VOCALES) >= 2, 'hacen falta grabaciones de al menos 2 vocales'
display(_conteo.reindex(CLASES).rename('grabaciones').to_frame().T)
display(ETIQ.head(8))
''')

md(r'''
## CWT

Réplica de `dsp.NewBank` / `Bank.Column`:

$$W(f, c) = \sum_{j=-h}^{h} x[c+j]\, w_f[j]\, e^{-i 2\pi f j / f_s}$$

$w_f$ es una gaussiana con $\sigma = \omega_0 / (2\pi f)$, truncada en $\pm 3\sigma$ y normalizada a $\sum w = 2$. Con esto, una senoide de amplitud $A$ da $|W| = A$, y la fase es la de la señal en el instante $c$.

- **En Colab** se calcula con FFT.
- **En el N6** bastan dos productos punto por frecuencia en cada columna: unos 11 000 MAC cada 10 ms para CH3, con `arm_dot_prod_f32` (Helium).
- Hay una columna cada `HOP` muestras, solo donde el núcleo más largo (20 Hz, ±143 ms) cabe entero, igual que en `RunCWT`.
- El audio usa la misma CWT a 16 kHz (como `bankV` de auravoxd), solo para etiquetar.
''')

code(r'''
def banco_cwt(fs=FS, fmin=FMIN, fmax=FMAX, nf=NF, w0=W0):
    """Réplica de dsp.NewBank (auravoxd/dsp/cwt.go)."""
    freqs, nucleos, semi = [], [], []
    for i in range(nf):
        f = fmin * (fmax / fmin) ** (i / (nf - 1))
        sigma = w0 / (2 * np.pi * f) * fs
        h = int(math.ceil(3 * sigma))
        j = np.arange(-h, h + 1)
        g = np.exp(-(j.astype(np.float64) ** 2) / (2 * sigma * sigma))
        nucleos.append(2 * g / g.sum() * np.exp(-2j * np.pi * f * j / fs))
        freqs.append(f)
        semi.append(h)
    return np.array(freqs), nucleos, np.array(semi)


FREQS, NUCLEOS, SEMI = banco_cwt()
HMAX = int(SEMI.max())
_G = np.zeros((NF, 2 * HMAX + 1), complex)
for _i, (_k, _h) in enumerate(zip(NUCLEOS, SEMI)):
    _G[_i, HMAX - _h:HMAX + _h + 1] = _k[::-1]


def cwt_columnas(x, cols):
    """W[k, f] = Σ_j x[cols[k]+j]·núcleo_f[j], igual que Bank.Column (fuera de x vale 0)."""
    nfft = sfft.next_fast_len(len(x) + _G.shape[1] - 1)
    y = sfft.ifft(sfft.fft(x, nfft)[None, :] * sfft.fft(_G, nfft, axis=1), axis=1)
    return y[:, np.asarray(cols) + HMAX].T


# Escalograma del audio: la misma CWT (20–500 Hz, ω0 = 6) a 16 kHz, como bankV de auravoxd.
FREQS_V, NUCLEOS_V, SEMI_V = banco_cwt(fs=FS_VOZ)


def cwt_filas(x, centros, nucleos, semi):
    """Como cwt_columnas, pero frecuencia por frecuencia (para señales largas a 16 kHz)."""
    hmax = int(max(semi))
    L = 2 * hmax + 1
    nfft = sfft.next_fast_len(len(x) + L - 1)
    X = sfft.fft(x, nfft)
    out = np.empty((len(centros), len(nucleos)), complex)
    for i, (k, h) in enumerate(zip(nucleos, semi)):
        g = np.zeros(L, complex)
        g[hmax - h:hmax + h + 1] = k[::-1]
        out[:, i] = sfft.ifft(X * sfft.fft(g, nfft))[np.asarray(centros) + hmax]
    return out


def _columna_directa(x, c):
    """Traducción literal de Bank.Column, solo para verificar."""
    out = np.zeros(NF, complex)
    for fi, (k, h) in enumerate(zip(NUCLEOS, SEMI)):
        jj = np.arange(max(-h, -c), min(h, len(x) - 1 - c) + 1)
        out[fi] = np.sum(x[c + jj] * k[jj + h])
    return out


_x = np.random.default_rng(0).standard_normal(3000)
_cols = np.array([0, 7, HMAX, 1500, 2999])
assert np.allclose(cwt_columnas(_x, _cols), np.stack([_columna_directa(_x, c) for c in _cols]), atol=1e-9)
assert np.allclose(cwt_filas(_x, _cols, NUCLEOS, SEMI), cwt_columnas(_x, _cols), atol=1e-9)
_s = 10 * np.cos(2 * np.pi * FREQS[12] * np.arange(4000) / FS + 0.3)
assert abs(abs(cwt_columnas(_s, [2000])[0, 12]) - 10) < 0.1
print(f'CWT: {NF} frecuencias de {FREQS[0]:.0f} a {FREQS[-1]:.0f} Hz; núcleo más largo ±{HMAX} muestras '
      f'({HMAX / FS * 1e3:.1f} ms); coincide con Bank.Column y da |W| = A para una senoide')
''')

md(r'''
## Etiquetado con el escalograma del audio

La entrada del modelo es solo el escalograma de **CH3** (`CANALES`). La etiqueta sale del audio:

- **Escalograma del audio:** la misma CWT (20–500 Hz, ω0 = 6) sobre el ADMP401 a 16 kHz, en los mismos instantes que las columnas del sEMG, corregida por los 0,75 ms del filtro del firmware. Su energía en la banda (donde está F0) marca la voz.
- **Piso de ruido:** mediana de esa energía en las grabaciones de `reposo` (o `silencio`).
- **`desconectado`:** toda la grabación, menos los bordes.
- **`reposo`:** toda, salvo las columnas con voz (toses, habla).
- **Vocal:** solo el interior de cada tramo con voz, con `GUARDA_VOZ_MS` hacia adentro. Los silencios, si `USAR_SILENCIOS_DE_VOCALES`, se usan como `reposo` cuando quedan a `GUARDA_REPOSO_MS` de la voz. Si una grabación de vocal no tiene voz detectable, se avisa y se toma entera como sostenida.

Una ventana entra al dataset solo si sus 32 columnas tienen la misma etiqueta. La figura de abajo muestra, para algunos ejemplos: la energía del audio con los umbrales y la franja de etiquetas, el escalograma del audio y el de CH3.
''')

code(r'''
def escalograma_voz(voz, cols):
    """Escalograma del audio en las columnas del sEMG: (|W|² en dBFS [K, NF], energía de la banda en dBFS [K]).
    La muestra EMG c corresponde a la de audio 8c, más los 0,75 ms del filtro de decimación de la ADMP401."""
    W = cwt_filas(voz, 8 * np.asarray(cols) + RETARDO_VOZ_MUESTRAS, NUCLEOS_V, SEMI_V)
    p = np.abs(W) ** 2
    esc = (10 * np.log10(p + 1e-20)).astype(np.float16)
    nivel = sps.medfilt(10 * np.log10(p.mean(axis=1) + 1e-20), 5)
    return esc, nivel


def mascara_voz(nivel, piso):
    v = nivel > piso + UMBRAL_VOZ_DB
    for (s,) in ndi.find_objects(ndi.label(~v)[0]):          # huecos cortos entre tramos de voz
        if (s.stop - s.start) * HOP_MS < MAX_HUECO_MS and s.start > 0 and s.stop < len(v):
            v[s] = True
    for (s,) in ndi.find_objects(ndi.label(v)[0]):           # golpes cortos
        if (s.stop - s.start) * HOP_MS < MIN_VOZ_MS:
            v[s] = False
    return v


def etiquetar(tr, clase, piso):
    K = len(tr['nivel'])
    lab = np.full(K, -1, np.int8)
    ci = CLASES.index(clase)
    if clase == 'desconectado':
        lab[:] = ci
    elif clase == 'reposo':
        lab[tr['nivel'] <= piso + UMBRAL_VOZ_DB] = ci
    else:
        voz = mascara_voz(tr['nivel'], piso)
        if not voz.any():
            print(f"  AVISO {SESIONES[tr['sesion']]['archivo']}: sin voz detectable; se toma como sostenida")
            lab[:] = ci
        else:
            g = int(round(GUARDA_VOZ_MS / HOP_MS))
            lab[ndi.binary_erosion(voz, np.ones(2 * g + 1, bool)) if g else voz] = ci
            if USAR_SILENCIOS_DE_VOCALES and I_REPOSO is not None:
                lejos = ndi.distance_transform_edt(~voz) * HOP_MS >= GUARDA_REPOSO_MS
                lab[(tr['nivel'] < piso + UMBRAL_SILENCIO_DB) & lejos] = I_REPOSO
    b = int(round(BORDE_S * 1000 / HOP_MS))
    lab[:b] = -1
    lab[K - b:] = -1
    return lab


SESIONES, TRAMOS = [], []
_t0 = time.time()
for fila in ETIQ.itertuples(index=False):
    partes, info = leer_sesion(RUTA[fila.archivo])
    for p in partes:
        N = len(p['uv'])
        if N < 2 * HMAX + T_COLS * HOP:
            continue
        cols = np.arange(HMAX, N - HMAX, HOP)
        W = np.stack([cwt_columnas(p['uv'][:, c], cols) for c in CANALES], axis=1)   # [K, canal, f]
        esc_voz, nivel = escalograma_voz(p['voz'], cols)
        TRAMOS.append(dict(sesion=len(SESIONES), W=W.astype(np.complex64), cols=cols, cod=p['cod'],
                           esc_voz=esc_voz, nivel=nivel, t=(p['seq0'] * 20 + cols) / FS))
    SESIONES.append(dict(archivo=fila.archivo, clase=fila.clase, ronda=fila.ronda, **info))
print(f'{len(SESIONES)} sesiones, {len(TRAMOS)} tramos contiguos, CWT en {time.time() - _t0:.1f} s; '
      f'bloques malos o con overrun: {sum(s["malos"] for s in SESIONES)}')

_rep = [tr['nivel'] for tr in TRAMOS if SESIONES[tr['sesion']]['clase'] == 'reposo']
PISO_VOZ = float(np.median(np.concatenate(_rep))) if _rep else None
print('Piso de ruido del escalograma del audio:',
      'sin grabaciones de reposo, se usa el percentil 10 de cada tramo' if PISO_VOZ is None else f'{PISO_VOZ:.1f} dBFS')
for tr in TRAMOS:
    piso = PISO_VOZ if PISO_VOZ is not None else float(np.percentile(tr['nivel'], 10))
    tr['lab'] = etiquetar(tr, SESIONES[tr['sesion']]['clase'], piso)
''')

code(r'''
def _franja_etiquetas(ax, t, lab):
    cambios = np.flatnonzero(np.diff(lab)) + 1
    for a, b in zip(np.r_[0, cambios], np.r_[cambios, len(lab)]):
        color = COLOR_CLASE[CLASES[lab[a]]] if lab[a] >= 0 else COLOR_IGNORADO
        ax.axvspan(t[a], t[min(b, len(t) - 1)], ymin=0.9, ymax=1.0, color=color, lw=0)


def _ejes_frecuencia(ax, nombre):
    ax.set_yticks([0.5, NF - 0.5], [f'{FREQS[0]:.0f} Hz', f'{FREQS[-1]:.0f} Hz'])
    ax.set_ylabel(nombre)


def figura_ejemplo(axs, tr):
    s = SESIONES[tr['sesion']]
    t = tr['t'] - tr['t'][0]
    ext = [t[0], t[-1], 0, NF]
    ax = axs[0]
    ax.plot(t, tr['nivel'], color='#52514e', lw=1.2)
    if PISO_VOZ is not None:
        ax.axhline(PISO_VOZ + UMBRAL_VOZ_DB, color='#52514e', ls='--', lw=1)
        ax.axhline(PISO_VOZ + UMBRAL_SILENCIO_DB, color='#52514e', ls=':', lw=1)
    _franja_etiquetas(ax, t, tr['lab'])
    ax.set_ylabel('audio [dBFS]')
    ronda = f" · ronda {int(s['ronda'])}" if s['ronda'] == s['ronda'] else ''
    ax.set_title(f"{s['archivo']} · {s['clase']}{ronda}")
    esc = tr['esc_voz'].astype(np.float32)
    vmin = PISO_VOZ if PISO_VOZ is not None else float(np.percentile(esc, 5))   # misma escala en todos
    axs[1].imshow(esc.T, aspect='auto', origin='lower', cmap=AZUL, vmin=vmin, vmax=vmin + 60,
                  extent=ext, interpolation='nearest')
    _ejes_frecuencia(axs[1], 'esc. audio')
    mag = np.clip(20 * np.log10(np.abs(tr['W']) + 1e-12), DB_MIN, DB_MAX)
    img = np.concatenate([mag[:, c, :].T for c in range(NIN)], axis=0)
    axs[2].imshow(img, aspect='auto', origin='lower', cmap=AZUL, vmin=-10, vmax=40,
                  extent=[t[0], t[-1], 0, NIN * NF], interpolation='nearest')
    for c in range(1, NIN):
        axs[2].axhline(c * NF, color='#fcfcfb', lw=2)
    if NIN == 1:
        _ejes_frecuencia(axs[2], f'|CWT| {NOMBRE_CANAL[CANALES[0]]}')
    else:
        axs[2].set_yticks([NF * (c + 0.5) for c in range(NIN)], [NOMBRE_CANAL[k] for k in CANALES])
        axs[2].set_ylabel('|CWT| dB µV')
    axs[3].imshow(np.angle(tr['W'][:, 0, :]).T, aspect='auto', origin='lower', cmap='twilight',
                  vmin=-np.pi, vmax=np.pi, extent=ext, interpolation='nearest')
    _ejes_frecuencia(axs[3], f'fase {NOMBRE_CANAL[CANALES[0]]}')
    axs[3].set_xlabel('tiempo [s]')


def _primer_tramo(cond):
    return next((tr for tr in TRAMOS if cond(SESIONES[tr['sesion']], tr)), None)


ejemplos = [tr for tr in (
    _primer_tramo(lambda s, tr: s['clase'] in VOCALES),
    _primer_tramo(lambda s, tr: s['clase'] in VOCALES and I_REPOSO is not None and (tr['lab'] == I_REPOSO).any()),
    _primer_tramo(lambda s, tr: s['clase'] == 'desconectado') or _primer_tramo(lambda s, tr: s['clase'] == 'reposo'))
    if tr is not None]
ejemplos = list({id(tr): tr for tr in ejemplos}.values())
fig, axs = plt.subplots(4 * len(ejemplos), 1, figsize=(11, 2.0 * 4 * len(ejemplos)),
                        gridspec_kw=dict(height_ratios=[1, 0.9, 0.9 * NIN, 0.7] * len(ejemplos)), squeeze=False)
for i, tr in enumerate(ejemplos):
    figura_ejemplo(axs[4 * i:4 * i + 4, 0], tr)
fig.legend(handles=[Patch(color=COLOR_CLASE[c], label=c) for c in CLASES] + [Patch(color=COLOR_IGNORADO, label='ignorado')],
           loc='upper center', ncol=8, bbox_to_anchor=(0.5, 1.0))
fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig(EXP / 'etiquetado.png', dpi=110)
plt.show()
''')

md(r'''
## Ventanas y tensores

Cada ventana son 32 columnas seguidas de un tramo, tomadas con paso `PASO_TRAIN`. La magnitud se normaliza por canal y frecuencia con la media y la desviación del set de entrenamiento (sin `desconectado`): el firmware usa las mismas constantes (`auravox_vocales.h`). La fase entra sin normalizar, porque ya está en [−1, 1].
''')

code(r'''
def feats_fase(W, modo):
    """[K, NIN, NF] complejo → [K, 2·planos, NF]: primero los cos y después los sin.
    'absoluta': un plano por canal; 'relativa': uno por par de canales (φi − φj)."""
    if modo == 'absoluta':
        u = W / (np.abs(W) + 1e-12)
    else:
        pares = list(itertools.combinations(range(W.shape[1]), 2))
        u = np.stack([W[:, i] * np.conj(W[:, j]) for i, j in pares], axis=1)
        u = u / (np.abs(u) + 1e-12)
    return np.concatenate([u.real, u.imag], axis=1).astype(np.float32)


def preparar_tensores(fase_modo):
    global MAG_NP, MAG_T, FASE_T, FASE_ACTUAL, NFASE
    W = np.concatenate([tr['W'] for tr in TRAMOS]).astype(np.complex128)
    MAG_NP = np.clip(20 * np.log10(np.abs(W) + 1e-12), DB_MIN, DB_MAX).astype(np.float32)
    MAG_T = torch.from_numpy(MAG_NP).to(DEV)
    FASE_T = torch.from_numpy(feats_fase(W, fase_modo)).to(DEV)
    FASE_ACTUAL = fase_modo
    NFASE = FASE_T.shape[1]


def ventanas():
    st, lo, y, se, ti = [], [], [], [], []
    off = 0
    for k, tr in enumerate(TRAMOS):
        lab, K = tr['lab'], len(tr['lab'])
        if K >= T_COLS:
            v = np.lib.stride_tricks.sliding_window_view(lab, T_COLS)[::PASO_TRAIN]
            ok = (v[:, 0] >= 0) & (v == v[:, :1]).all(axis=1)
            s = np.flatnonzero(ok) * PASO_TRAIN
            st.append(off + s); lo.append(s); y.append(lab[s])
            se.append(np.full(len(s), tr['sesion'])); ti.append(np.full(len(s), k))
        off += K
    return [np.concatenate(a) for a in (st, lo, y, se, ti)]


START_W, LOCAL_W, Y_W, SES_W, TRAMO_W = ventanas()
Y_W = Y_W.astype(np.int64)
START_T, Y_T = torch.from_numpy(START_W).to(DEV), torch.from_numpy(Y_W).to(DEV)
preparar_tensores(FASE)


def asignar_pliegues():
    rondas = np.array([SESIONES[s]['ronda'] for s in SES_W], dtype=float)
    if len(rondas) and not np.isnan(rondas).any():
        return rondas.astype(int), 'ronda (tono)'
    # Sin ronda en todas: las grabaciones de cada clase se reparten en n pliegues, con n = la vocal con menos
    # grabaciones (entre 2 y 5), así cada pliegue tiene una grabación de cada vocal.
    n = int(np.clip(min(sum(s['clase'] == c for s in SESIONES) for c in VOCALES), 2, 5))
    pl = np.zeros(len(SESIONES), int)
    for c in CLASES:
        for k, i in enumerate([i for i, s in enumerate(SESIONES) if s['clase'] == c]):
            pl[i] = k % n + 1
    return pl[SES_W], f'grabación ({n} pliegues; las etiquetas no traen ronda en todas)'


FOLD_W, CRITERIO_PLIEGUES = asignar_pliegues()
resumen = pd.DataFrame({
    'grabaciones': [sum(s['clase'] == c for s in SESIONES) for c in CLASES],
    'segundos etiquetados': [round(sum(int((tr['lab'] == i).sum()) for tr in TRAMOS) * HOP_MS / 1000, 1)
                             for i in range(NCLASES)],
    'ventanas': np.bincount(Y_W, minlength=NCLASES)}, index=CLASES).T
display(resumen)
print(f'{len(Y_W)} ventanas de {T_COLS} columnas ({T_COLS * HOP_MS} ms) con paso {PASO_TRAIN}; '
      f'pliegues por {CRITERIO_PLIEGUES}: {sorted(set(FOLD_W.tolist()))}')

AR_T, AR_F = torch.arange(T_COLS, device=DEV), torch.arange(NF, device=DEV)
RAMPA_F = torch.linspace(-0.5, 0.5, NF, device=DEV)
FREQS_T = torch.tensor(FREQS, dtype=torch.float32, device=DEV)


def calcular_norm(idx):
    """Media y desviación por canal y frecuencia (dB), sobre las columnas de las ventanas conectadas de idx."""
    st = START_W[idx] if I_DESC is None else START_W[idx][Y_W[idx] != I_DESC]
    x = MAG_NP[np.unique((st[:, None] + np.arange(T_COLS)).ravel())]
    return x.mean(0).astype(np.float32), np.maximum(x.std(0), 0.5).astype(np.float32)


def _norm_t(norm):
    return tuple(torch.from_numpy(a).to(DEV) for a in norm)


def lote(starts, norm_t, aug=False, fase_modo=None):
    """Ventanas → (mag [B, NIN, T, NF], fase [B, NFASE, T, NF]), en el formato NCHW de la red."""
    ix = starts[:, None] + AR_T[None, :]
    mag, fase = MAG_T[ix], FASE_T[ix]                        # [B, T, canal, NF]
    B = ix.shape[0]
    if aug:
        g = (torch.rand(B, 1, NIN, 1, device=DEV) * 2 - 1) * AUG_GANANCIA_DB
        p = (torch.rand(B, 1, NIN, 1, device=DEV) * 2 - 1) * AUG_PENDIENTE_DB
        mag = (mag + g + p * RAMPA_F + torch.randn_like(mag) * AUG_RUIDO_DB).clamp(DB_MIN, DB_MAX)
        if (fase_modo or FASE_ACTUAL) == 'absoluta':          # grilla de columnas corrida < 1 hop
            th = 2 * math.pi * FREQS_T * (torch.rand(B, 1, 1, 1, device=DEV) * HOP / FS)
            co, si, c, s = fase[:, :, :NIN], fase[:, :, NIN:], torch.cos(th), torch.sin(th)
            fase = torch.cat([co * c - si * s, si * c + co * s], dim=2)
    x = ((mag - norm_t[0]) / norm_t[1]).clamp(-Z_CLIP, Z_CLIP)
    if aug:                                                  # máscaras cortas de tiempo y frecuencia
        t0, tw = torch.randint(0, T_COLS, (B, 1), device=DEV), torch.randint(1, 5, (B, 1), device=DEV)
        f0, fw = torch.randint(0, NF, (B, 1), device=DEV), torch.randint(1, 4, (B, 1), device=DEV)
        mt = (AR_T >= t0) & (AR_T < t0 + tw) & (torch.rand(B, 1, device=DEV) < 0.5)
        mf = (AR_F >= f0) & (AR_F < f0 + fw) & (torch.rand(B, 1, device=DEV) < 0.5)
        keep = ~(mt[:, :, None, None] | mf[:, None, None, :])
        x, fase = x * keep, fase * keep
    return x.permute(0, 2, 1, 3).contiguous(), fase.permute(0, 2, 1, 3).contiguous()
''')

md(r'''
## Modelo: CNN feed-forward para la NPU

Sin recurrencia ni autoatención: cada ventana entra una vez y sale una predicción.

```
cwt_mag  [1,32,32] ─ Conv3×3(16) ReLU MaxPool2 ─┐
                                                 ├ Concat(24) ─ Conv3×3(32) ReLU MaxPool2 ─ Conv3×3(32) ReLU MaxPool2
cwt_fase [2,32,32] ─ Conv3×3(8)  ReLU MaxPool2 ─┘   [SE opcional] ─ AvgPool(2,1)×2: tiempo ─ Conv(1×4, 32) ReLU: frecuencia
                                                    ─ Flatten ─ Dropout ─ Linear(clases) → logits
```

Criterios, según la tabla oficial *ST Neural-ART NPU – Supported operators and limitations* (ST Edge AI Core 4.0, r1.3):

- Todo lo que usa va a hardware: `Conv`, `Relu`, `MaxPool`, `AveragePool`, `Concat`, `Gemm` y `Flatten`. Kernels de alto ≤ 3 y ventanas de pooling ≤ 3 (si son más grandes, el compilador las descompone). Canales intermedios de 8, 16 y 32, porque la tabla sugiere evitar números primos.
- **Una convolución propia por entrada.** La magnitud (±5) y la fase (±1) se cuantizan con escalas int8 distintas.
- **Se promedia el tiempo, no la frecuencia.** La cabeza sabe qué banda está activa, que es lo que discrimina en sEMG, pero no cuándo dentro de la ventana.
- **`Flatten` recibe `[32,1,1]`.** Así no depende del orden NCHW/NHWC y no hace falta transponer antes de la capa densa.
- **Softmax fuera del modelo.** El argmax de los logits int8 da la clase sin descuantizar.
- **Sobre la atención:** en esa misma tabla, BatchNorm, GELU, Sigmoid y Softmax (con `--expand-softmax`) figuran en hardware. Lo que cae al M55 en la autoatención es el `MatMul` con las dos entradas variables (Q·Kᵀ y A·V): *"Second input should be constant else SW fallback"*. La atención por canales (squeeze-excitation: promedio con AvgPool 2×2, Conv1×1, ReLU, Conv1×1, Sigmoid y Mul con broadcast por canal) usa solo operadores de hardware y se activa con `ATENCION_SE = True`.
''')

code(r'''
def _bloque(ci, co):
    return nn.Sequential(nn.Conv2d(ci, co, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2))


class SE(nn.Module):
    """Atención por canales. El promedio global se arma con AvgPool de ventana 2 (la NPU pide ≤ 3)."""

    def __init__(self, c, t, f, r=4):
        super().__init__()
        pools = []
        while t > 1 or f > 1:
            k = (2 if t > 1 else 1, 2 if f > 1 else 1)
            pools.append(nn.AvgPool2d(k))
            t, f = t // k[0], f // k[1]
        self.squeeze = nn.Sequential(*pools)
        self.excite = nn.Sequential(nn.Conv2d(c, c // r, 1), nn.ReLU(), nn.Conv2d(c // r, c, 1), nn.Sigmoid())

    def forward(self, x):
        return x * self.excite(self.squeeze(x))


class AuraVoxVocales(nn.Module):
    def __init__(self, usar_fase=USAR_FASE, se=ATENCION_SE, t=T_COLS, nf=NF, nclases=None, p=DROPOUT):
        super().__init__()
        self.usar_fase = usar_fase
        self.mag = _bloque(NIN, 16)
        if usar_fase:
            self.fase = _bloque(NFASE, 8)
        self.tronco = nn.Sequential(_bloque(24 if usar_fase else 16, 32), _bloque(32, 32))
        t3, f3 = t // 8, nf // 8
        self.se = SE(32, t3, f3) if se else nn.Identity()
        self.tiempo = nn.Sequential(*[nn.AvgPool2d((2, 1)) for _ in range(int(math.log2(t3)))])
        self.frecuencia = nn.Sequential(nn.Conv2d(32, 32, (1, f3)), nn.ReLU())
        self.cabeza = nn.Sequential(nn.Flatten(), nn.Dropout(p), nn.Linear(32, nclases or NCLASES))

    def forward(self, mag, fase=None):
        x = self.mag(mag)
        if self.usar_fase:
            x = torch.cat([x, self.fase(fase)], dim=1)
        x = self.se(self.tronco(x))
        return self.cabeza(self.frecuencia(self.tiempo(x)))


_m = AuraVoxVocales()
_y = _m(torch.zeros(2, NIN, T_COLS, NF), torch.zeros(2, NFASE, T_COLS, NF))
assert _y.shape == (2, NCLASES)
print(f'{sum(p.numel() for p in _m.parameters()):,} parámetros (≈ {sum(p.numel() for p in _m.parameters()) / 1024:.0f} KiB en int8)')
''')

md(r'''
## Entrenamiento: Adam + OneCycle, 10 épocas

- **Muestreo balanceado por clase:** `reposo` suele tener más ventanas.
- **Aumentos en dB, pensados para lo que cambia entre sesiones:**
  - ganancia por canal ±3 dB (impedancia del electrodo);
  - pendiente espectral ±2 dB;
  - ruido de 0,5 dB;
  - máscaras cortas de tiempo y frecuencia;
  - con fase absoluta, un corrimiento de la grilla de columnas de menos de un hop, que rota la fase de cada frecuencia como pasa en la placa, donde la grilla cae en cualquier punto.
- **Regularización:** dropout 0,3, weight decay 1e-4 y label smoothing 0,05.
- **Control del sobreajuste:** cada pliegue de la validación cruzada deja fuera grabaciones completas (una ronda u otra toma de cada vocal), y las curvas de train y val por época muestran la brecha. El modelo final se entrena con todo, con la misma receta y sin elegir épocas mirando la validación.
''')

code(r'''
def metricas(logits, y):
    pred = logits.argmax(1)
    cm = np.zeros((NCLASES, NCLASES), int)
    np.add.at(cm, (y, pred), 1)
    rec = np.diag(cm) / np.maximum(cm.sum(1), 1)
    prec = np.diag(cm) / np.maximum(cm.sum(0), 1)
    f1 = 2 * prec * rec / np.maximum(prec + rec, 1e-12)
    hay = cm.sum(1) > 0
    loss = F.cross_entropy(torch.as_tensor(logits, dtype=torch.float32), torch.as_tensor(y)).item()
    return dict(loss=loss, acc=float((pred == y).mean()), bacc=float(rec[hay].mean()), f1=float(f1[hay].mean()),
                cm=cm, pred=pred)


@torch.no_grad()
def evaluar(modelo, idx, norm_t):
    modelo.eval()
    out = []
    for b in range(0, len(idx), 512):
        x, f = lote(START_T[torch.as_tensor(idx[b:b + 512], device=DEV)], norm_t)
        out.append(modelo(x, f).float().cpu())
    return metricas(torch.cat(out).numpy(), Y_W[idx])


def entrenar(idx_tr, idx_va=None, usar_fase=USAR_FASE, se=ATENCION_SE, fase_modo=FASE,
             epocas=EPOCAS, semilla=SEMILLA, nombre='', verbose=True):
    torch.manual_seed(semilla)
    rng = np.random.default_rng(semilla)
    norm = calcular_norm(idx_tr)
    norm_t = _norm_t(norm)
    modelo = AuraVoxVocales(usar_fase, se).to(DEV)
    opt = torch.optim.Adam(modelo.parameters(), lr=LR_MAX, weight_decay=WEIGHT_DECAY)
    pasos = math.ceil(len(idx_tr) / BATCH)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=LR_MAX, epochs=epocas, steps_per_epoch=pasos,
                                                pct_start=0.3)
    cuenta = np.bincount(Y_W[idx_tr], minlength=NCLASES)
    peso = torch.tensor(1.0 / cuenta[Y_W[idx_tr]], dtype=torch.float)
    idx_tr_t = torch.as_tensor(idx_tr, device=DEV)
    sub_tr = rng.choice(idx_tr, min(len(idx_tr), 3000), replace=False)
    hist = []
    for ep in range(1, epocas + 1):
        modelo.train()
        t0 = time.time()
        orden = torch.multinomial(peso, pasos * BATCH, replacement=True).to(DEV)
        for b in range(pasos):
            sel = idx_tr_t[orden[b * BATCH:(b + 1) * BATCH]]
            x, f = lote(START_T[sel], norm_t, aug=True, fase_modo=fase_modo)
            loss = F.cross_entropy(modelo(x, f), Y_T[sel], label_smoothing=LABEL_SMOOTHING)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
            sched.step()
        mt = evaluar(modelo, sub_tr, norm_t)
        mv = evaluar(modelo, idx_va, norm_t) if idx_va is not None and len(idx_va) else None
        h = dict(epoca=ep, loss_tr=mt['loss'], acc_tr=mt['acc'],
                 loss_va=mv['loss'] if mv else np.nan, acc_va=mv['acc'] if mv else np.nan)
        hist.append(h)
        if verbose:
            va = f" · val loss {h['loss_va']:.3f} acc {h['acc_va']:.3f}" if mv else ''
            print(f"  {nombre} época {ep:2d}: train loss {h['loss_tr']:.3f} acc {h['acc_tr']:.3f}{va} "
                  f"({time.time() - t0:.1f} s)")
    return modelo, norm, hist
''')

code(r'''
def exportar_onnx(modelo, ruta, usar_fase):
    """ONNX opset 13, batch 1 fijo, como pide ST Edge AI (Quantized models → Quantize Pytorch models)."""
    m = modelo.eval().cpu()
    nombres = ['cwt_mag', 'cwt_fase'] if usar_fase else ['cwt_mag']
    ej = (torch.zeros(1, NIN, T_COLS, NF),) + ((torch.zeros(1, NFASE, T_COLS, NF),) if usar_fase else ())
    kw = dict(input_names=nombres, output_names=['logits'], opset_version=13, do_constant_folding=True)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        try:
            torch.onnx.export(m, ej, str(ruta), dynamo=False, **kw)
        except TypeError:                    # torch sin el argumento dynamo
            torch.onnx.export(m, ej, str(ruta), **kw)
        except Exception as e:               # torch sin el exportador TorchScript
            print('  exportador TorchScript no disponible:', type(e).__name__, '→ dynamo + opset 13')
            torch.onnx.export(m, ej, str(ruta), dynamo=True, opset_version=18,
                              input_names=nombres, output_names=['logits'])
            onnx.save(onnx.version_converter.convert_version(onnx.load(str(ruta)), 13), str(ruta))
    mo = onnx.load(str(ruta))
    if mo.ir_version > 8:                    # ST Edge AI 4.0 usa ONNX 1.15 (IR ≤ 9)
        mo.ir_version = 8
        onnx.save(mo, str(ruta))
    onnx.checker.check_model(mo)
    modelo.to(DEV)
    return nombres


def entradas_np(idx, norm):
    norm_t = _norm_t(norm)
    xs, fs = [], []
    for b in range(0, len(idx), 512):
        x, f = lote(START_T[torch.as_tensor(idx[b:b + 512], device=DEV)], norm_t)
        xs.append(x.cpu().numpy())
        fs.append(f.cpu().numpy())
    return np.concatenate(xs), np.concatenate(fs)


class LectorCalibracion(CalibrationDataReader):
    def __init__(self, nombres, xm, xf):
        self.nombres, self.xm, self.xf, self.i = nombres, xm, xf, 0

    def get_next(self):
        if self.i >= len(self.xm):
            return None
        d = {'cwt_mag': self.xm[self.i:self.i + 1]}
        if 'cwt_fase' in self.nombres:
            d['cwt_fase'] = self.xf[self.i:self.i + 1]
        self.i += 1
        return d

    def rewind(self):
        self.i = 0


def idx_calibracion(idx, por_clase=48, semilla=SEMILLA):
    rng = np.random.default_rng(semilla)
    sel = [rng.choice(idx[Y_W[idx] == c], min(por_clase, int((Y_W[idx] == c).sum())), replace=False)
           for c in range(NCLASES) if (Y_W[idx] == c).any()]
    return np.concatenate(sel)


def cuantizar(ruta_fp32, ruta_int8, idx_calib, norm):
    """QDQ, int8 por canal (ss/sa), MinMax: la receta recomendada por ST para la NPU."""
    nombres = [i.name for i in onnx.load(str(ruta_fp32)).graph.input]
    xm, xf = entradas_np(idx_calib, norm)
    pre = str(ruta_fp32).replace('.onnx', '_pre.onnx')
    quant_pre_process(str(ruta_fp32), pre, skip_symbolic_shape=True)
    quantize_static(pre, str(ruta_int8), LectorCalibracion(nombres, xm, xf), quant_format=QuantFormat.QDQ,
                    activation_type=QuantType.QInt8, weight_type=QuantType.QInt8, per_channel=True,
                    calibrate_method=CalibrationMethod.MinMax)
    os.remove(pre)


def evaluar_onnx(ruta, idx, norm):
    s = ort.InferenceSession(str(ruta), providers=['CPUExecutionProvider'])
    nombres = [i.name for i in s.get_inputs()]
    xm, xf = entradas_np(idx, norm)
    out = []
    for i in range(len(xm)):
        d = {'cwt_mag': xm[i:i + 1]}
        if 'cwt_fase' in nombres:
            d['cwt_fase'] = xf[i:i + 1]
        out.append(s.run(None, d)[0][0])
    return metricas(np.array(out), Y_W[idx])


def params_cuant(ruta):
    """(escala, zero point) de las entradas y de la salida del modelo QDQ."""
    m = onnx.load(str(ruta))
    ini = {i.name: onnx.numpy_helper.to_array(i) for i in m.graph.initializer}
    q = {}
    for n in m.graph.node:
        if n.op_type == 'QuantizeLinear' and n.input[0] in ('cwt_mag', 'cwt_fase'):
            q[n.input[0]] = (float(ini[n.input[1]]), int(ini[n.input[2]]))
        if n.op_type == 'DequantizeLinear' and n.output[0] == 'logits':
            q['logits'] = (float(ini[n.input[1]]), int(ini[n.input[2]]))
    return q


MAPEO_NPU = {  # tabla oficial ONNX → Neural-ART (ST Edge AI Core 4.0, r1.3)
    'Conv': 'HW', 'Gemm': 'HW', 'MaxPool': 'HW', 'AveragePool': 'HW (ventana ≤ 3)', 'Relu': 'HW',
    'Concat': 'HW', 'Flatten': 'HW', 'Reshape': 'HW', 'Sigmoid': 'HW', 'Mul': 'HW (broadcast por canal)',
    'GlobalAveragePool': 'HW (ventana limitada)'}


def revisar_npu(ruta):
    """Operadores del modelo int8, si quedaron cuantizados y cómo los asigna la tabla de ST."""
    m = onnx.load(str(ruta))
    prod = {o: n.op_type for n in m.graph.node for o in n.output}
    ini = {i.name for i in m.graph.initializer}
    filas = {}
    for n in m.graph.node:
        if n.op_type in ('QuantizeLinear', 'DequantizeLinear'):
            continue
        ent = [x for x in n.input if x and x not in ini]
        q = all(prod.get(x) == 'DequantizeLinear' for x in ent)
        f = filas.setdefault(n.op_type, dict(operador=n.op_type, nodos=0, cuantizados=0))
        f['nodos'] += 1
        f['cuantizados'] += int(q)
    df = pd.DataFrame(filas.values())
    df['tabla ST'] = [MAPEO_NPU.get(o, 'REVISAR') for o in df['operador']]
    return df
''')

md(r'''
## Validación cruzada

En cada pliegue, las grabaciones que quedan fuera se evalúan con el modelo en float y con el mismo modelo exportado y cuantizado a int8 (ONNX Runtime). La columna `acc_int8` es la exactitud honesta del modelo que corre en la NPU.
''')

code(r'''
def validacion_cruzada(usar_fase=USAR_FASE, fase_modo=FASE, se=ATENCION_SE, int8=True, verbose=True):
    if fase_modo != FASE_ACTUAL:
        preparar_tensores(fase_modo)
    filas, hists = [], []
    cm = np.zeros((NCLASES, NCLASES), int)
    for k in sorted(set(FOLD_W.tolist())):
        va = np.flatnonzero((FOLD_W == k) & (LOCAL_W % PASO_VAL == 0))
        tr = np.flatnonzero(FOLD_W != k)
        faltan = [CLASES[c] for c in range(NCLASES) if not (Y_W[tr] == c).any()]
        if faltan:
            print(f'  aviso pliegue {k}: el entrenamiento no tiene {faltan}')
        modelo, norm, hist = entrenar(tr, va, usar_fase, se, fase_modo, nombre=f'pliegue {k}', verbose=verbose)
        mf = evaluar(modelo, va, _norm_t(norm))
        fila = dict(pliegue=k, ventanas_val=len(va), acc=mf['acc'], acc_bal=mf['bacc'], f1_macro=mf['f1'])
        if int8:
            p32, p8 = OUT / f'cv{k}_fp32.onnx', OUT / f'cv{k}_int8.onnx'
            exportar_onnx(modelo, p32, usar_fase)
            cuantizar(p32, p8, idx_calibracion(tr), norm)
            mq = evaluar_onnx(p8, va, norm)
            fila.update(acc_int8=mq['acc'], acc_bal_int8=mq['bacc'])
        filas.append(fila)
        hists.append(pd.DataFrame(hist))
        cm += mf['cm']
    return pd.DataFrame(filas), hists, cm


_t0 = time.time()
CV, HIST, CM = validacion_cruzada()
print(f'validación cruzada en {time.time() - _t0:.0f} s')
display(CV.round(3))
_m = CV.drop(columns=['pliegue', 'ventanas_val'])
print('media ± desvío entre pliegues:  ' + ' · '.join(f'{c} {_m[c].mean():.3f} ± {_m[c].std():.3f}' for c in _m))
''')

code(r'''
H = pd.concat([h.assign(pliegue=i) for i, h in enumerate(HIST)])
g = H.groupby('epoca')
fig, axs = plt.subplots(1, 3, figsize=(12, 3.4), gridspec_kw=dict(width_ratios=[1, 1, 1.15]))
for ax, met, titulo in ((axs[0], 'loss', 'Pérdida (sin label smoothing)'), (axs[1], 'acc', 'Exactitud')):
    finales = []
    for sufijo, color, etiqueta in (('_tr', '#2a78d6', 'train'), ('_va', '#eb6834', 'val (fuera)')):
        m, s = g[met + sufijo].mean(), g[met + sufijo].std().fillna(0)
        ax.plot(m.index, m.values, color=color, label=etiqueta, marker='o', ms=4)
        ax.fill_between(m.index, m - s, m + s, color=color, alpha=0.15, lw=0)
        finales.append([float(m.values[-1]), etiqueta])
    lo, hi = ax.get_ylim()
    sep = 0.08 * (hi - lo)
    if abs(finales[0][0] - finales[1][0]) < sep:     # curvas juntas: separar las etiquetas directas
        medio = (finales[0][0] + finales[1][0]) / 2
        abajo, arriba = sorted(finales, key=lambda e: e[0])
        abajo[0], arriba[0] = medio - sep / 2, medio + sep / 2
    for y, etiqueta in finales:
        ax.annotate(etiqueta, (EPOCAS, y), xytext=(6, 0), textcoords='offset points',
                    color='#52514e', va='center', fontsize=8)
    ax.set_title(titulo)
    ax.set_xlabel('época')
    ax.grid(axis='y', color='#ecebe7', lw=0.8)
    ax.set_xlim(0.8, EPOCAS + 1.6)
axs[0].legend(loc='upper right')
cmn = CM / np.maximum(CM.sum(1, keepdims=True), 1)
axs[2].imshow(cmn, cmap=AZUL, vmin=0, vmax=1)
for i in range(NCLASES):
    for j in range(NCLASES):
        if CM[i].sum():
            axs[2].text(j, i, f'{100 * cmn[i, j]:.0f}', ha='center', va='center', fontsize=7.5,
                        color='#fcfcfb' if cmn[i, j] > 0.55 else '#0b0b0b')
axs[2].set_xticks(range(NCLASES), CLASES, rotation=45, ha='right')
axs[2].set_yticks(range(NCLASES), CLASES)
axs[2].set_xlabel('predicha')
axs[2].set_ylabel('real')
axs[2].set_title('Confusión de la validación cruzada [% por fila]')
axs[2].spines[:].set_visible(False)
fig.tight_layout()
fig.savefig(EXP / 'validacion_cruzada.png', dpi=110)
plt.show()
''')

code(r'''
if COMPARAR_VARIANTES:   # ¿aporta la fase? (solo float, para no multiplicar el tiempo)
    filas = []
    variantes = [('solo magnitud', False, FASE), ('magnitud + fase absoluta', True, 'absoluta')]
    if NIN > 1:
        variantes.append(('magnitud + fase relativa', True, 'relativa'))
    for nombre, uf, fm in variantes:
        cv, _, _ = validacion_cruzada(uf, fm, ATENCION_SE, int8=False, verbose=False)
        filas.append(dict(variante=nombre, acc=cv['acc'].mean(), desvio=cv['acc'].std(), acc_bal=cv['acc_bal'].mean()))
        print(f"{nombre}: {cv['acc'].mean():.3f} ± {cv['acc'].std():.3f}")
    display(pd.DataFrame(filas).round(3))
    preparar_tensores(FASE)
''')

md(r'''
## Modelo final y exportación

Se entrena con todas las ventanas, con la misma receta. Después se exporta, se cuantiza y se verifica que todos los nodos quedaron entre pares Q/DQ, porque un nodo en float correría en el M55. La exactitud de esta tabla es sobre datos vistos: la estimación honesta es la de la validación cruzada.
''')

code(r'''
if FASE_ACTUAL != FASE:
    preparar_tensores(FASE)
TODO = np.arange(len(Y_W))
MODELO, NORM, HIST_FINAL = entrenar(TODO, None, USAR_FASE, ATENCION_SE, FASE, nombre='final')
P32, P8 = EXP / 'auravox_vocales_fp32.onnx', EXP / 'auravox_vocales_int8.onnx'
ENTRADAS = exportar_onnx(MODELO, P32, USAR_FASE)
cuantizar(P32, P8, idx_calibracion(TODO), NORM)
QP = params_cuant(P8)
_sub = TODO[LOCAL_W % PASO_VAL == 0]
M32, M8 = evaluar_onnx(P32, _sub, NORM), evaluar_onnx(P8, _sub, NORM)
ACUERDO = float((M32['pred'] == M8['pred']).mean())
_mo = onnx.load(str(P8))
print(f"ONNX int8: opset {_mo.opset_import[0].version}, IR {_mo.ir_version}, {P8.stat().st_size / 1024:.0f} KiB; "
      f"entradas {ENTRADAS}")
print(f"sobre datos de entrenamiento: fp32 {M32['acc']:.3f} · int8 {M8['acc']:.3f} · "
      f"misma clase fp32/int8 en {100 * ACUERDO:.1f} % de las ventanas")
print('cuantización (escala, zero point):', {k: (round(v[0], 6), v[1]) for k, v in QP.items()})
display(revisar_npu(P8))
''')

code(r'''
def _c(nombre, a, tipo):
    """Arreglo C con llaves anidadas (sin avisos de -Wmissing-braces)."""
    a = np.asarray(a)

    def fmt(v):
        if tipo != 'float':
            return str(int(v))
        t = f'{float(v):.8g}'
        return (t if ('.' in t or 'e' in t) else t + '.0') + 'f'

    def lit(x, ind):
        if x.ndim == 1:
            txt = [fmt(v) for v in x]
            if len(txt) <= 12:
                return '{' + ', '.join(txt) + '}'
            filas = [', '.join(txt[i:i + 12]) for i in range(0, len(txt), 12)]
        else:
            partes = [lit(s, ind + '    ') for s in x]
            cortas = all('\n' not in q for q in partes)
            filas = [', '.join(partes[i:i + 6]) for i in range(0, len(partes), 6)] if cortas else partes
        return '{\n' + ind + '    ' + (',\n' + ind + '    ').join(filas) + '\n' + ind + '}'

    dims = ''.join(f'[{d}]' for d in a.shape)
    return f'static const {tipo} {nombre}{dims} = {lit(a, "")};\n'


def _q(x, sz):
    return np.clip(np.rint(x / sz[0]) + sz[1], -128, 127).astype(np.int8)


FECHA = dt.datetime.now().strftime('%Y-%m-%d %H:%M')
_nc = [NOMBRE_CANAL[k] for k in CANALES]
_planos = (_nc if FASE == 'absoluta' else [f'{a}−{b}' for a, b in itertools.combinations(_nc, 2)])
_desc_fase = f"cos y sin de φ{'' if FASE == 'absoluta' else ' relativa'}: [cos {', '.join(_planos)}, sin {', '.join(_planos)}]"
mu, sd = NORM
s_m, z_m = QP['cwt_mag']
s_o, z_o = QP['logits']
h = [f"""/*
 * auravox_vocales.h: constantes del clasificador de vocales para la NPU del STM32N6570-DK.
 * Generado por auravox_vocales_npu.ipynb el {FECHA}{' (MODO DEMO: datos sintéticos)' if DEMO else ''}.
 * Modelo: auravox_vocales_int8.onnx (QDQ, int8 por canal). Entradas NCHW, que ST Edge AI conserva por defecto
 * para ONNX (con --inputs-ch-position chlast pasan a NHWC).
 *
 *   Canales EMG de entrada: {', '.join(_nc)} (adc[{', '.join(map(str, CANALES))}] del bloque SPI).
 *   in[0] cwt_mag  int8 [1][{NIN}][T][NF]: q( clip( (clip(dB, DB_MIN, DB_MAX) - mu[c][f]) * inv_sd[c][f], ±Z_CLIP ) )
 *   in[1] cwt_fase int8 [1][{NFASE}][T][NF]: q( {_desc_fase} )
 *   out   logits   int8 [1][{NCLASES}]: clase = argmax (no hace falta descuantizar); nombres en avx_voc_clases
 *   q(x) = clamp(round_half_even(x / escala) + zp, -128, 127)
 *
 * CWT (auravoxd/dsp/cwt.go): W(f,c) = Σ_j x[c+j]·w_f[j]·e^(-i2πf·j/FS), j = -h_f..h_f, w_f gaussiana de
 * σ = W0/(2πf)·FS muestras, h_f = ceil(3σ), normalizada a Σw = 2. dB = 20·log10(|W| + 1e-12).
 * cos φ = Re W / (|W| + 1e-12), sin φ = Im W / (|W| + 1e-12).
 * x = sEMG en µV: (código·VREF_ADC/4095/GDK − VMID) / GAIN · 1e6.
 * Ventana: T columnas, una cada HOP muestras; la columna t de la ventana es la fila t de cada plano [c][t][:].
 */
#ifndef AURAVOX_VOCALES_H
#define AURAVOX_VOCALES_H

#include <stdint.h>
#include <math.h>

#define AVX_VOC_FS            {FS}
#define AVX_VOC_HOP           {HOP}
#define AVX_VOC_T             {T_COLS}
#define AVX_VOC_NF            {NF}
#define AVX_VOC_NCH           {NIN}      /* canales EMG de entrada (avx_voc_canal) */
#define AVX_VOC_NFASE         {NFASE}
#define AVX_VOC_NCLASES       {NCLASES}
#define AVX_VOC_USA_FASE      {int(USAR_FASE)}
#define AVX_VOC_FASE_RELATIVA {int(FASE == 'relativa')}
#define AVX_VOC_W0            {W0:.1f}f
#define AVX_VOC_FMIN          {FMIN:.1f}f
#define AVX_VOC_FMAX          {FMAX:.1f}f
#define AVX_VOC_HMAX          {HMAX}      /* semiancho del núcleo de FMIN, en muestras */
#define AVX_VOC_DB_MIN        ({DB_MIN:.1f}f)
#define AVX_VOC_DB_MAX        ({DB_MAX:.1f}f)
#define AVX_VOC_Z_CLIP        {Z_CLIP:.1f}f
#define AVX_VOC_VREF_ADC      {CONV['VrefADC']}f
#define AVX_VOC_GDK           {CONV['GDK']}f
#define AVX_VOC_VMID          {CONV['VMid']}f
#define AVX_VOC_GAIN          {CONV['Gain']:.1f}f
#define AVX_VOC_MAG_ESCALA    {s_m:.9g}f
#define AVX_VOC_MAG_ZP        ({z_m})"""]
if USAR_FASE:
    s_f, z_f = QP['cwt_fase']
    h.append(f'#define AVX_VOC_FASE_ESCALA   {s_f:.9g}f\n#define AVX_VOC_FASE_ZP       ({z_f})')
h.append(f'#define AVX_VOC_OUT_ESCALA    {s_o:.9g}f\n#define AVX_VOC_OUT_ZP        ({z_o})\n')
h.append(_c('avx_voc_canal', CANALES, 'uint8_t'))
h.append(_c('avx_voc_freqs', FREQS.astype(np.float32), 'float'))
h.append(_c('avx_voc_semi', SEMI, 'uint16_t'))
h.append('/* media y 1/desvío de la magnitud en dB, por canal y frecuencia */')
h.append(_c('avx_voc_mu', mu, 'float'))
h.append(_c('avx_voc_inv_sd', (1.0 / sd).astype(np.float32), 'float'))
h.append('static const char *const avx_voc_clases[AVX_VOC_NCLASES] = {'
         + ', '.join(f'"{c}"' for c in CLASES) + '};\n')
h.append("""static inline int8_t avx_voc_q(float x, float escala, int zp)
{
    float q = rintf(x / escala) + (float)zp;
    return (int8_t)(q < -128.0f ? -128.0f : (q > 127.0f ? 127.0f : q));
}

/* Magnitud de la CWT (dB) del canal c (índice en avx_voc_canal) y la frecuencia f → valor int8 de cwt_mag */
static inline int8_t avx_voc_q_mag(float db, int c, int f)
{
    db = db < AVX_VOC_DB_MIN ? AVX_VOC_DB_MIN : (db > AVX_VOC_DB_MAX ? AVX_VOC_DB_MAX : db);
    float z = (db - avx_voc_mu[c][f]) * avx_voc_inv_sd[c][f];
    z = z < -AVX_VOC_Z_CLIP ? -AVX_VOC_Z_CLIP : (z > AVX_VOC_Z_CLIP ? AVX_VOC_Z_CLIP : z);
    return avx_voc_q(z, AVX_VOC_MAG_ESCALA, AVX_VOC_MAG_ZP);
}

/* Índice NCHW del elemento [plano][t][f] de una entrada */
#define AVX_VOC_IDX(plano, t, f)  (((plano) * AVX_VOC_T + (t)) * AVX_VOC_NF + (f))

#endif /* AURAVOX_VOCALES_H */
""")
(EXP / 'auravox_vocales.h').write_text('\n'.join(h))

# Vectores de prueba: la cadena completa (códigos del ADC → dB → int8 → logits) en una ventana, y la NPU en 3
_elegidas = []
for c in [CLASES.index(v) for v in VOCALES] + [i for i in (I_REPOSO, I_DESC) if i is not None]:
    cand = np.flatnonzero((Y_W == c) & (LOCAL_W % PASO_VAL == 0))
    if len(cand):
        _elegidas.append(int(cand[len(cand) // 2]))
    if len(_elegidas) == 3:
        break
_elegidas = np.array(_elegidas)
xm, xf = entradas_np(_elegidas, NORM)
_s8 = ort.InferenceSession(str(P8), providers=['CPUExecutionProvider'])
_logits = np.stack([_s8.run(None, {'cwt_mag': xm[i:i + 1], **({'cwt_fase': xf[i:i + 1]} if USAR_FASE else {})})[0][0]
                    for i in range(len(_elegidas))])
_w = _elegidas[0]
_tr, _l0 = TRAMOS[TRAMO_W[_w]], LOCAL_W[_w]
_c0 = _tr['cols'][_l0] - HMAX
_c1 = _tr['cols'][_l0 + T_COLS - 1] + HMAX + 1
p = [f"""/*
 * auravox_vocales_prueba.h: vectores de prueba de auravox_vocales_npu.ipynb ({FECHA}{', DEMO' if DEMO else ''}).
 * 1) CWT: avx_voc_prueba_adc trae los códigos de adc[avx_voc_canal]; la columna t de la ventana se centra
 *    en la muestra HMAX + t*HOP; avx_voc_prueba_db es el dB µV recortado, [t][canal][f] (tolerancia ~0,01 dB).
 * 2) Entradas int8 NCHW esperadas (±1 LSB) y logits int8 que da ONNX Runtime (±2 LSB, mismo argmax).
 */
#ifndef AURAVOX_VOCALES_PRUEBA_H
#define AURAVOX_VOCALES_PRUEBA_H
#include <stdint.h>
#define AVX_VOC_PRUEBA_NS  {_c1 - _c0}
#define AVX_VOC_PRUEBA_N   {len(_elegidas)}
"""]
p.append(_c('avx_voc_prueba_adc', _tr['cod'][_c0:_c1][:, CANALES], 'uint16_t'))
p.append(_c('avx_voc_prueba_db', MAG_NP[START_W[_w] + np.arange(T_COLS)], 'float'))
p.append(_c('avx_voc_prueba_mag', _q(xm, QP['cwt_mag']).reshape(len(_elegidas), -1), 'int8_t'))
if USAR_FASE:
    p.append(_c('avx_voc_prueba_fase', _q(xf, QP['cwt_fase']).reshape(len(_elegidas), -1), 'int8_t'))
p.append(_c('avx_voc_prueba_logits', _q(_logits, QP['logits']), 'int8_t'))
p.append(_c('avx_voc_prueba_clase', Y_W[_elegidas], 'uint8_t'))
p.append('#endif /* AURAVOX_VOCALES_PRUEBA_H */\n')
(EXP / 'auravox_vocales_prueba.h').write_text('\n'.join(p))

# Datos de validación para STM32Cube AI Studio (claves m_inputs_<i> / m_outputs_1, salida one-hot)
_iv = idx_calibracion(np.flatnonzero(LOCAL_W % PASO_VAL == 0), por_clase=30, semilla=1)
xm, xf = entradas_np(_iv, NORM)
_oh = np.eye(NCLASES, dtype=np.float32)[Y_W[_iv]]
np.savez(EXP / 'auravox_vocales_val.npz', m_inputs_1=xm, m_outputs_1=_oh, **({'m_inputs_2': xf} if USAR_FASE else {}))
np.savez(EXP / 'auravox_vocales_val_int8.npz', m_inputs_1=_q(xm, QP['cwt_mag']), m_outputs_1=_oh,
         **({'m_inputs_2': _q(xf, QP['cwt_fase'])} if USAR_FASE else {}))

INFORME = dict(
    fecha=FECHA, demo=DEMO, versiones=dict(torch=torch.__version__, onnx=onnx.__version__, onnxruntime=ort.__version__),
    entradas=ENTRADAS, canales=[NOMBRE_CANAL[k] for k in CANALES], clases=CLASES,
    fase=FASE if USAR_FASE else None, atencion_se=ATENCION_SE,
    cwt=dict(fs=FS, fmin=FMIN, fmax=FMAX, nf=NF, w0=W0, hop_ms=HOP_MS, t_cols=T_COLS, hmax=HMAX),
    entrenamiento=dict(epocas=EPOCAS, batch=BATCH, lr_max=LR_MAX, weight_decay=WEIGHT_DECAY, dropout=DROPOUT),
    piso_voz_dbfs=PISO_VOZ, ventanas_por_clase=dict(zip(CLASES, np.bincount(Y_W, minlength=NCLASES).tolist())),
    pliegues=CRITERIO_PLIEGUES, validacion_cruzada=CV.to_dict('records'),
    cuantizacion={k: dict(escala=v[0], zp=v[1]) for k, v in QP.items()},
    final=dict(acc_fp32_train=M32['acc'], acc_int8_train=M8['acc'], acuerdo_fp32_int8=ACUERDO))
(EXP / 'informe.json').write_text(json.dumps(INFORME, indent=2, ensure_ascii=False,
                                             default=lambda o: o.item() if hasattr(o, 'item') else str(o)))
print('Escritos auravox_vocales.h, auravox_vocales_prueba.h, auravox_vocales_val*.npz e informe.json')
''')

code(r'''
_zip = shutil.make_archive(str(OUT / 'auravox_vocales_export'), 'zip', root_dir=EXP)
for f in sorted(EXP.iterdir()):
    print(f'  {f.name:34s} {f.stat().st_size / 1024:8.1f} KiB')
print('→', _zip)
if EN_COLAB:
    from google.colab import files
    if not DEMO and Path('/content/drive/MyDrive').exists():
        destino = Path(CARPETA_DRIVE) / f"modelo_{dt.datetime.now():%Y%m%d-%H%M}"
        shutil.copytree(EXP, destino, dirs_exist_ok=True)
        print('copiado a', destino)
    files.download(_zip)
''')

md(r'''
## Siguiente paso: STM32Cube AI Studio

En un PC que aguante las herramientas de ST:

1. **New project** → target **STM32N6570-DK** → activar **ST Neural-ART**.
2. Importar **`auravox_vocales_int8.onnx`**. El `_fp32` es solo de referencia: correría en el M55, no en la NPU.
3. **Analizar** y revisar en el reporte que todas las capas caigan en épocas de hardware. Sin opciones extra, ST Edge AI deja las entradas en **int8 NCHW** y la salida en int8, que es lo que asume `auravox_vocales.h`.
4. **Validar** en escritorio con `auravox_vocales_val.npz`, o con `auravox_vocales_val_int8.npz` si pide las entradas en int8. La exactitud debe acercarse a `acc_int8` de la validación cruzada (son ventanas vistas en el entrenamiento, así que puede salir algo mayor).
5. **Generar** el proyecto. Ese proyecto es la base del firmware final: ahí se porta el resto (captura EMG, micrófono, enlace SPI con la Pi, pantalla). La carpeta oculta **`.ai`** es el área de trabajo y respaldo de ST Edge AI Core.

**En el firmware**, cada 10 ms: CWT de CH3 por columna (CMSIS-DSP/Helium), ventana deslizante de 32 columnas, cuantizar con `auravox_vocales.h`, inferencia en la NPU y argmax. `auravox_vocales_prueba.h` verifica cada etapa contra este notebook.

El modelo de la demo tiene las mismas entradas y salidas que el real: el port se puede avanzar ya, y con las grabaciones solo se regenera la red.
''')


def to_ipynb(cells):
    nb_cells = []
    for kind, src in cells:
        lines = src.split("\n")
        source = [l + "\n" for l in lines[:-1]] + [lines[-1]]
        c = {"cell_type": kind, "metadata": {}, "source": source}
        if kind == "code":
            c["execution_count"] = None
            c["outputs"] = []
        nb_cells.append(c)
    return {
        "cells": nb_cells,
        "metadata": {
            "accelerator": "GPU",
            "colab": {"provenance": [], "gpuType": "T4", "name": "auravox_vocales_npu.ipynb"},
            "kernelspec": {"display_name": "Python 3", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 0,
    }


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "auravox_vocales_npu.ipynb")
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(to_ipynb(CELLS), f, ensure_ascii=False, indent=1)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, out)   # escritura atómica: un apagón no deja el .ipynb a medias
    print("escrito", out, len(CELLS), "celdas")
