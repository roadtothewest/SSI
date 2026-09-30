"""Genera los PWL de la auditoria sEMG (AUDIT_SEMG.asc), 2 s, semilla fija.
  noise/semg_chK.pwl : sEMG util (V), rafagas con cadencia de silabas
  noise/nz_chK.pwl   : ruido (V) = artefacto de movimiento + ECG + ruido blanco
Modelo del sEMG: ruido gaussiano con el espectro de Shwedyk/Stulen
  P(f) = fh^4 f^2 / ((f^2 + fl^2)(f^2 + fh^2)^2)
modulado por una envolvente de activacion (rafagas con bordes suaves y tono de reposo del 5 %).
Amplitudes [SUPUESTO dentro de lo publicado: sEMG submentoniano normal ~10-80 uV]."""
import json, os
import numpy as np

T, FS = 2.0, 10000
OUT = os.path.join(os.path.dirname(__file__), '..', 'noise')
os.makedirs(OUT, exist_ok=True)
t = np.arange(int(T * FS) + 1) / FS

CH = {  # musculo, sEMG RMS en rafaga, pico R del ECG, desfase de rafagas [s]
    1: ('submentoniano', 50e-6, 120e-6, 0.000),
    2: ('platisma', 30e-6, 300e-6, 0.015),
    3: ('labio inferior', 40e-6, 50e-6, -0.010),
    4: ('laringe', 25e-6, 250e-6, 0.025),
}
BURSTS = [(0.30, 0.55), (0.72, 0.90), (1.05, 1.40), (1.58, 1.80)]   # ~4 silabas/s
FL, FH = 40.0, 120.0
MOTION_RMS, WHITE_RMS = 500e-6, 20e-6


def shaped(rng, psd):
    X = np.fft.rfft(rng.standard_normal(len(t)))
    f = np.fft.rfftfreq(len(t), 1 / FS)
    x = np.fft.irfft(X * np.sqrt(psd(f)), len(t))
    return x / x.std()


def envelope(shift):
    e = np.full_like(t, 0.05)
    for a, b in BURSTS:
        a, b = a + shift, b + shift
        r = 0.03                                   # bordes de 30 ms
        m = (t >= a) & (t <= b)
        w = np.ones(m.sum())
        n = int(r * FS)
        w[:n] = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n))
        w[-n:] = w[:n][::-1]
        e[m] = np.maximum(e[m], w)
    return e


def ecg(amp, rng):
    """PQRST por suma de gaussianas (McSharry), 72 lpm con variabilidad leve."""
    y = np.zeros_like(t)
    waves = [(-0.25, 0.10, 0.025), (-0.04, -0.12, 0.010), (0.0, 1.0, 0.010), (0.04, -0.25, 0.010), (0.30, 0.30, 0.040)]
    tb = 0.2
    while tb < T + 0.5:
        for dt, a, w in waves:
            y += a * np.exp(-0.5 * ((t - tb - dt) / w) ** 2)
        tb += 0.833 * (1 + 0.03 * rng.standard_normal())
    return amp * y


def write(name, x):
    np.savetxt(os.path.join(OUT, name), np.column_stack([t, x]), fmt='%.7g')


psd_semg = lambda f: FH ** 4 * f ** 2 / ((f ** 2 + FL ** 2) * (f ** 2 + FH ** 2) ** 2)
meta = {}
for k, (musc, a_rms, ecg_pk, shift) in CH.items():
    rng = np.random.default_rng(2000 + k)
    env = envelope(shift)
    semg = a_rms * env * shaped(rng, psd_semg)
    motion = MOTION_RMS * shaped(rng, lambda f: ((f > 0.1) & (f < 10)).astype(float))
    if k == 2:   # tiron de cable / movimiento de cabeza en el platisma
        motion += 1.5e-3 * (1 / (1 + np.exp(-(t - 1.2) / 0.02)) - 1 / (1 + np.exp(-(t - 1.5) / 0.05)))
    white = WHITE_RMS * shaped(rng, lambda f: (f < 5000).astype(float))
    noise = motion + ecg(ecg_pk, rng) + white
    write(f'semg_ch{k}.pwl', semg)
    write(f'nz_ch{k}.pwl', noise)
    f = np.fft.rfftfreq(len(t), 1 / FS); P = np.abs(np.fft.rfft(semg)) ** 2; c = np.cumsum(P) / P.sum()
    burst = env > 0.9
    meta[k] = dict(musculo=musc, semg_rms_rafaga_uV=round(semg[burst].std() * 1e6, 1),
                   ruido_rms_uV=round(noise.std() * 1e6, 1), fmediana_Hz=round(float(f[np.searchsorted(c, 0.5)]), 1),
                   snr_entrada_dB=round(20 * np.log10(semg[burst].std() / noise.std()), 1))
json.dump(meta, open(os.path.join(OUT, 'semg_meta.json'), 'w'), indent=1, ensure_ascii=False)
print(json.dumps(meta, indent=1, ensure_ascii=False))
