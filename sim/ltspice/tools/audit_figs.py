"""Analisis de la auditoria (27-30 sep): RLD (t8_rld_robustez.cir, AUDIT_RLD.asc) y sEMG realista (AUDIT_SEMG.asc).
Requiere haber corrido las simulaciones (ver docs/afe-emg/resultados_simulacion.md, seccion 6).
Salida: docs/afe-emg/figs/audit_*.png y audit_metricas.json"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy import signal

sys.path.insert(0, os.path.dirname(__file__))
from ltraw import read_raw, get
from run import load
import make_figs as mf   # estilo y paleta comunes

HERE, OUT, S, INK, INK2 = mf.HERE, mf.OUT, mf.S, mf.INK, mf.INK2
G = 503.3
M = {}
MUSC = {1: 'submentoniano', 2: 'platisma', 3: 'labio inferior', 4: 'laringe'}


# ------------------------------------------------------------------ RLD robustez (AC, INA333 de TI)
def rld():
    r = load('t8_rld_robustez.cir')
    rows = {}
    for st, run in r:
        key = (st['rimb'], st['rer'], st['cmb'], st['cge'] > 1e-3)
        rti = np.mean([abs(get(run, f'V(adc{k})')[0]) for k in (1, 2, 3, 4)]) / G * 1e6
        drive = abs(get(run, 'V(rldo)')[0] - get(run, 'V(vref)')[0])
        rows.setdefault(key, {})[int(st['rldmode'])] = (rti, drive)
    tab = []
    for (rimb, rer, cmb, usb), d in sorted(rows.items(), key=lambda kv: (kv[0][3], kv[0][2], kv[0][1], kv[0][0])):
        tab.append(dict(desbalance=f'{rimb / 1e3:g}k' if rimb > 10 else '0', electrodo_RLD=f'{rer / 1e3:g}k',
                        acople_red=f'{cmb * 1e12:g}p', conexion='USB a PC' if usb else 'bateria',
                        sin_RLD_uVpk=round(d[1][0], 2), con_RLD_uVpk=round(d[2][0], 2),
                        mejora_dB=round(20 * np.log10(d[1][0] / d[2][0]), 1),
                        salida_RLD_Vpk=round(d[2][1], 3)))
    M['rld_robustez'] = tab
    # figura: mejora con RLD en cada condicion
    fig, ax = plt.subplots(figsize=(11, 4.2))
    labels = [f"{t['conexion'][:3]} {t['acople_red']}\nRe {t['electrodo_RLD']} des {t['desbalance']}" for t in tab]
    x = np.arange(len(tab)); w = 0.4
    ax.bar(x - w / 2, [t['sin_RLD_uVpk'] for t in tab], w - 0.04, color=S[1], label='Sin RLD (ref. pasiva 390k)')
    ax.bar(x + w / 2, [t['con_RLD_uVpk'] for t in tab], w - 0.04, color=S[0], label='Con RLD')
    ax.set_yscale('log'); ax.set_xticks(x, labels, fontsize=6.5, rotation=90)
    ax.set_ylabel('50 Hz a la salida, RTI [uV pico]')
    ax.set_title('Auditoria RLD: 50 Hz en 24 condiciones (bateria/USB, acople 3/30 pF, electrodo RLD 20k/200k, desbalance 0/51k/200k)')
    ax.legend(loc='upper left', fontsize=8)
    mf.save(fig, 'audit_rld_robustez.png')


# ------------------------------------------------------------------ sEMG realista
FS = 10000
BURSTS = [(0.30, 0.55), (0.72, 0.90), (1.05, 1.40), (1.58, 1.80)]


def uni(run, name, fs=FS):
    t = run['time']; tt = np.arange(0, 2.0, 1 / fs)
    return tt, np.interp(tt, t, get(run, name))


def digital(y):
    sos = np.vstack([signal.butter(4, 20, 'highpass', fs=FS, output='sos'),
                     signal.tf2sos(*signal.iirnotch(50, 30, fs=FS))])
    return signal.sosfilt(sos, y - y[0])


def env(x, win=0.05):
    n = int(win * FS)
    return np.sqrt(np.convolve(x ** 2, np.ones(n) / n, mode='same'))


def semg():
    runs = {c: read_raw(os.path.join(HERE, f'_u_semg_c{c}.raw'))[1][0] for c in (0, 1, 2)}
    res = {}
    fig, axs = plt.subplots(4, 3, figsize=(14, 11), sharex=True)
    for k in (1, 2, 3, 4):
        tt, sg = uni(runs[1], f'V(sg{k})')
        _, nin = uni(runs[1], f'V(n{k})'); _, body = uni(runs[1], 'V(body)')
        din = nin - body                                   # entrada diferencial total (sEMG + ruido)
        _, y0 = uni(runs[0], f'V(adc{k})')                 # AFE con solo sEMG (referencia)
        _, y1 = uni(runs[1], f'V(adc{k})')                 # con ruido, RLD activo
        _, y2 = uni(runs[2], f'V(adc{k})')                 # con ruido, sin RLD
        w = tt >= 0.2
        burst = np.zeros_like(tt, bool)
        for a, b in BURSTS:
            burst |= (tt >= a + 0.05) & (tt <= b - 0.05)
        rest = w & ~burst & (np.abs(tt - 1.0) > 0.0)
        y0c, y1c, y2c = y0 - y0[w].mean(), y1 - y1[w].mean(), y2 - y2[w].mean()
        snr = lambda ref, err, m: 20 * np.log10(ref[m].std() / err[m].std())
        d0, d1, d2 = digital(y0), digital(y1), digital(y2)
        # latencia: correlacion cruzada sEMG de entrada vs salida limpia
        xc = signal.correlate(y0c[w], sg[w], mode='full'); lags = signal.correlation_lags(w.sum(), w.sum(), mode='full')
        lag_ms = lags[np.argmax(xc)] / FS * 1e3
        e_true = env(sg); e1 = env(d1); e0 = env(d0)
        fmed = lambda x: (lambda f, P: float(f[np.searchsorted(np.cumsum(P) / P.sum(), 0.5)]))(*signal.welch(x[burst], FS, nperseg=2048))
        res[f'ch{k}'] = dict(
            musculo=MUSC[k],
            semg_uVrms_rafaga=round(sg[burst].std() * 1e6, 1),
            ruido_entrada_uVrms=round((din - sg)[w].std() * 1e6, 1),
            snr_entrada_dB=round(snr(sg, din - sg, burst), 1),
            snr_salida_con_RLD_dB=round(snr(y0c, y1c - y0c, burst), 1),
            snr_salida_sin_RLD_dB=round(snr(y0c, y2c - y0c, burst), 1),
            snr_salida_filtro_digital_dB=round(snr(d0, d1 - d0, burst & (tt > 0.4)), 1),
            corr_envolvente_salida_vs_verdad=round(float(np.corrcoef(e1[tt > 0.4], e_true[tt > 0.4])[0, 1]), 3),
            corr_envolvente_limpia_vs_verdad=round(float(np.corrcoef(e0[tt > 0.4], e_true[tt > 0.4])[0, 1]), 3),
            contraste_rafaga_reposo=round(float(e1[burst & (tt > 0.4)].mean() / e1[rest & (tt > 0.4)].mean()), 1),
            latencia_ms=round(float(lag_ms), 2),
            fmediana_entrada_Hz=round(fmed(sg), 1), fmediana_salida_Hz=round(fmed(y0c) , 1),
            adc_min_V=round(float(y1[w].min()), 3), adc_max_V=round(float(y1[w].max()), 3),
            ina_min_V=round(float(uni(runs[1], 'V(ina1)' if k == 1 else 'V(ina2)')[1][w].min()), 3) if k <= 2 else None,
            ina_max_V=round(float(uni(runs[1], 'V(ina1)' if k == 1 else 'V(ina2)')[1][w].max()), 3) if k <= 2 else None)
        # figura
        row = axs[k - 1]; x = tt[w]
        row[0].plot(x, din[w] * 1e6, color=INK2, lw=0.5, label='entrada = sEMG + ruido')
        row[0].plot(x, sg[w] * 1e6, color=S[0], lw=0.9, label='sEMG util')
        row[0].set_ylabel(f'CH{k} {MUSC[k]}\nentrada [uV]', fontsize=9)
        row[1].plot(x, y1c[w] * 1e3, color=S[1], lw=0.6, label='salida ADC (RLD activo)')
        row[1].plot(x, y0c[w] * 1e3, color=S[0], lw=0.7, label='salida con solo sEMG')
        row[1].set_ylabel('ADC - media [mV]', fontsize=9)
        row[2].plot(x, e1[w] / G * 1e6, color=S[2], lw=1.4, label='envolvente de la salida + filtro digital')
        row[2].plot(x, e_true[w] * 1e6, color=S[0], lw=1.4, ls='--', label='envolvente real del sEMG')
        row[2].set_ylabel('envolvente RTI [uV rms]', fontsize=9)
        for a, b in BURSTS:
            for c in row:
                c.axvspan(a, b, color='#e4e3df', zorder=0)
    for c, t in zip(axs[0], ('Entrada diferencial (ruido 10-23x mayor que el sEMG)', 'Salida del AFE', 'Activacion recuperada (RMS 50 ms)')):
        c.set_title(t)
    for c in axs[0]:
        c.legend(fontsize=7, loc='upper right')
    for c in axs[-1]:
        c.set_xlabel('tiempo [s]  (sombreado = rafagas de activacion)')
    fig.tight_layout()
    mf.save(fig, 'audit_semg.png')
    M['semg'] = res


if __name__ == '__main__':
    rld(); semg()
    json.dump(M, open(os.path.join(OUT, 'audit_metricas.json'), 'w'), indent=1, ensure_ascii=False)
    print(json.dumps(M, indent=1, ensure_ascii=False))
