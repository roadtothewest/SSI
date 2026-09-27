"""Genera los archivos PWL de ruido para T7 (uno por canal y componente, RMS unitario).
  lf_chK.pwl : artefacto de movimiento / deriva de linea base, gaussiano, banda 0.1-10 Hz, fs 1 kHz
  wh_chK.pwl : ruido blanco gaussiano, plano hasta ~8 kHz, fs 20 kHz
La amplitud real se fija en el netlist con NLF y NWH. Semilla fija: reproducible."""
import numpy as np, os

T = 1.25
OUT = os.path.join(os.path.dirname(__file__), '..', 'noise')
os.makedirs(OUT, exist_ok=True)


def band_noise(rng, fs, f1, f2):
    n = int(T * fs) + 1
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / fs)
    X[(f < f1) | (f > f2)] = 0
    x = np.fft.irfft(X, n)
    return x / np.sqrt(np.mean(x ** 2))


def write(name, fs, x):
    t = np.arange(len(x)) / fs
    np.savetxt(os.path.join(OUT, name), np.column_stack([t, x]), fmt='%.7g')


for k in range(1, 5):
    rng = np.random.default_rng(1000 + k)
    write(f'lf_ch{k}.pwl', 1000, band_noise(rng, 1000, 0.1, 10))
    x = rng.standard_normal(int(T * 20000) + 1)
    write(f"wh_ch{k}.pwl", 20000, x / np.sqrt(np.mean(x ** 2)))
print('ok', sorted(os.listdir(OUT)))
