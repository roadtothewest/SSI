"""Figuras y metricas de las simulaciones del AFE -> docs/afe-emg/figs/*.png + metricas.json
Correr despues de:  python3 tools/run.py t2_ac.cir t4_cm.cir t4b_rfi.cir t5_rld.cir
                    python3 tools/run.py --unroll -j 3 t6_rld_tran.cir t7_func.cir
"""
import json, os, sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))
from ltraw import get
from run import load, load_unrolled

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OUT = os.path.abspath(os.path.join(HERE, '..', '..', 'docs', 'afe-emg', 'figs'))
os.makedirs(OUT, exist_ok=True)

# paleta categorica (orden fijo) y tinta
S = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300']
INK, INK2, GRID, BG = '#0b0b0b', '#52514e', '#e4e3df', '#fcfcfb'
plt.rcParams.update({
    'figure.facecolor': BG, 'axes.facecolor': BG, 'savefig.facecolor': BG,
    'axes.edgecolor': '#b9b8b3', 'axes.labelcolor': INK2, 'xtick.color': INK2, 'ytick.color': INK2,
    'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.8, 'axes.spines.top': False,
    'axes.spines.right': False, 'font.size': 10, 'axes.titlesize': 11, 'axes.titleweight': 'bold',
    'axes.titlecolor': INK, 'legend.frameon': False, 'lines.linewidth': 1.6, 'figure.dpi': 110})
M = {}
G_NOM = 503.3  # ganancia nominal de la cadena (54.04 dB) para referir a la entrada


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), dpi=130, bbox_inches='tight')
    plt.close(fig)
    print('fig', name)


def band(ax):
    for f in (20, 500):
        ax.axvline(f, color=INK2, lw=0.8, ls=':', zorder=0)


# --------------------------------------------------------------------- T2
def t2():
    r = load('t2_ac.cir')
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    run = r[0][1]; f = run['frequency']
    for k in range(4):
        g = 20 * np.log10(np.abs(get(run, f'V(adc{k + 1})')))
        ax[0].semilogx(f, g, color=S[k], lw=2.2 - 0.4 * k, label=f'CH{k + 1}')
    ax[0].set(xlim=(1, 2e4), ylim=(-20, 60), xlabel='Frecuencia [Hz]', ylabel='Ganancia [dB]',
              title='Respuesta de los 4 canales (curvas superpuestas)')
    band(ax[0]); ax[0].legend(loc='lower center', ncol=4)
    g = 20 * np.log10(np.abs(get(run, 'V(adc1)')))
    i = lambda x: np.argmin(abs(f - x))
    gmax = g.max(); lf, hf = np.log10(f), g > gmax - 3
    i1 = np.argmax(hf); i2 = len(g) - 1 - np.argmax(hf[::-1])
    fl = 10 ** np.interp(gmax - 3, g[i1 - 1:i1 + 1], lf[i1 - 1:i1 + 1])
    fh = 10 ** np.interp(-(gmax - 3), -g[i2:i2 + 2], lf[i2:i2 + 2])
    ax[0].annotate(f'{gmax:.1f} dB\n-3 dB: {fl:.1f} Hz y {fh:.0f} Hz', (60, gmax), (2.2, 42), color=INK, fontsize=9)
    run1 = r[1][1]
    g1 = 20 * np.log10(np.abs(get(run1, 'V(adc1)')))
    for k in (2, 3, 4):
        x = 20 * np.log10(np.abs(get(run1, f'V(adc{k})')) + 1e-30) - g1
        ax[1].semilogx(f, x, color=S[k - 1], label=f'CH1 -> CH{k}')
    ax[1].set(xlim=(1, 2e4), ylim=(-140, -40), xlabel='Frecuencia [Hz]', ylabel='Diafonia relativa a CH1 [dB]',
              title='Diafonia: senal solo en CH1')
    band(ax[1]); ax[1].legend(loc='upper right')
    save(fig, 't2_respuesta_4ch.png')
    M['t2'] = {'g_dB': round(gmax, 2), 'fL': round(fl, 2), 'fH': round(fh, 1),
               'g_ch': [round(20 * np.log10(abs(get(run, f'V(adc{k})')[i(100)])), 3) for k in (1, 2, 3, 4)],
               'xtalk100_dB': round(float(20 * np.log10(abs(get(run1, 'V(adc2)')[i(100)]) / abs(get(run1, 'V(adc1)')[i(100)]))), 1)}


# --------------------------------------------------------------------- T4
CASES = {0: 'Sin RLD: ref. directa\n(sin R de seguridad)', 4: 'Sin RLD: ref. pasiva\npor 390k',
         1: 'RLD, sensado en\npunto medio de RG', 2: 'RLD, sensado 100k\nsobre electrodos', 3: 'Solo los 100k,\nsin RLD'}


def t4():
    r = load('t4_cm.cir')
    val = {}
    for st, run in r:
        val[(int(st['case']), st['cge'] > 1e-3)] = [abs(get(run, f'V(adc{k})')[0]) / G_NOM * 1e6 for k in (1, 2, 3, 4)]
    order = [0, 4, 1, 2, 3]
    fig, ax = plt.subplots(figsize=(10, 4))
    x = np.arange(len(order)); w = 0.38
    for j, (usb, lab) in enumerate(((False, 'A bateria (CGE 20 pF)'), (True, 'Circuito a tierra (USB a PC)'))):
        v = [np.mean(val[(c, usb)]) for c in order]
        b = ax.bar(x + (j - 0.5) * w, v, w - 0.04, color=S[j], label=lab)
        for xi, vi in zip(x + (j - 0.5) * w, v):
            ax.text(xi, vi * 1.15, f'{vi:.0f}' if vi >= 10 else f'{vi:.2g}', ha='center', va='bottom', fontsize=8, color=INK)
    ax.set_yscale('log'); ax.set_ylim(0.1, 5000)
    ax.set_xticks(x, [CASES[c] for c in order], fontsize=8.5)
    ax.set_ylabel('50 Hz a la salida, RTI [uV pico]')
    ax.set_title('T4: 50 Hz de red en los 4 canales (promedio; los 4 canales dan lo mismo)')
    ax.legend(loc='upper left')
    save(fig, 't4_50hz_rld_sensado.png')
    M['t4'] = {f'case{c}_{"usb" if u else "bat"}': [round(v, 3) for v in val[(c, u)]] for c in order for u in (False, True)}


# --------------------------------------------------------------------- T4b
RFI = {1: 'Pizarra 100k/470p/4.7n', 2: 'Gemini 330k/470p/4.7n', 3: 'Propuesta 100k/47p/100p', 4: 'Propuesta 330k/-/47p'}


def t4b():
    r = load('t4b_rfi.cir')
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8), gridspec_kw={'width_ratios': [1.4, 1]})
    res = {}
    for st, run in r:
        mode, rfi, usb = int(st['mode']), int(st['rfi']), st['cge'] > 1e-3
        f = run['frequency']; a = np.abs(get(run, 'V(adc1)')); i = np.argmin(abs(f - 50))
        if mode == 1 and not usb:
            ax[0].semilogx(f, 20 * np.log10(a), color=S[rfi - 1], label=RFI[rfi])
            res[(rfi, 'g500')] = 20 * np.log10(a[np.argmin(abs(f - 500))])
            res[(rfi, 'g100')] = 20 * np.log10(a[np.argmin(abs(f - 100))])
        if mode == 0:
            res[(rfi, 'usb' if usb else 'bat')] = a[i] / G_NOM * 1e6
    ax[0].set(xlim=(5, 2e4), ylim=(-10, 60), xlabel='Frecuencia [Hz]', ylabel='Ganancia CH1 [dB]',
              title='T4b: filtro RFI de entrada, respuesta')
    band(ax[0]); ax[0].legend(loc='lower center', fontsize=8)
    x = np.arange(4); w = 0.38
    for j, (key, lab) in enumerate((('bat', 'A bateria'), ('usb', 'USB a PC'))):
        v = [res[(k, key)] for k in (1, 2, 3, 4)]
        ax[1].bar(x + (j - 0.5) * w, v, w - 0.04, color=S[j], label=lab)
    ax[1].set_yscale('log'); ax[1].set_xticks(x, ['Pizarra', 'Gemini', '100k/47p', '330k/-/47p'], fontsize=8.5)
    ax[1].set(ylabel='50 Hz RTI [uV pico]', title='50 Hz residual (RLD activo)'); ax[1].legend(fontsize=8)
    save(fig, 't4b_rfi.png')
    M['t4b'] = {RFI[k]: {'g100': round(res[(k, 'g100')], 2), 'g500': round(res[(k, 'g500')], 2),
                         'bat_uV': round(res[(k, 'bat')], 3), 'usb_uV': round(res[(k, 'usb')], 3)} for k in (1, 2, 3, 4)}


# --------------------------------------------------------------------- T5
def t5():
    r = load('t5_rld.cir')
    pick = lambda **kw: [run for st, run in r if all(abs(st[k] - v) <= 1e-3 * abs(v) + 1e-18 for k, v in kw.items())][0]
    fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
    names = {0: 'Sin RLD, ref. directa', 1: 'Sin RLD, ref. pasiva 390k', 2: 'RLD activo (Cint 1 nF)'}
    for m in (0, 1, 2):
        run = pick(rldmode=m, cint=1e-9, rlim=390e3, cge=1)
        f = run['frequency']; v = np.abs(get(run, 'V(body)') - get(run, 'V(vref)'))
        ax[0].loglog(f, v * 1e3 / 311, color=S[m], label=names[m])
    ax[0].axvline(50, color=INK2, lw=0.8, ls=':')
    ax[0].set(xlim=(1, 1e5), xlabel='Frecuencia de la interferencia [Hz]', ylabel='Modo comun cuerpo-VREF [mV por V de red]',
              title='T5: modo comun en el cuerpo, con y sin RLD (USB a PC)')
    ax[0].legend(fontsize=8)
    base = pick(rldmode=1, cint=1e-9, rlim=390e3, cge=1)
    vb = np.abs(get(base, 'V(body)') - get(base, 'V(vref)'))
    peaks = {}
    for j, c in enumerate((470e-12, 1e-9, 2.2e-9, 4.7e-9)):
        run = pick(rldmode=2, cint=c, rlim=390e3, cge=1)
        s = np.abs(get(run, 'V(body)') - get(run, 'V(vref)')) / vb
        ax[1].semilogx(f, 20 * np.log10(s), color=S[j], label=f'Cint {c * 1e9:g} nF')
        peaks[f'{c * 1e9:g}n'] = {'pico_dB': round(float(20 * np.log10(s.max())), 2), 'f_pico': round(float(f[s.argmax()]), 0),
                                  'S50_dB': round(float(20 * np.log10(s[np.argmin(abs(f - 50))])), 1)}
    ax[1].axhline(0, color=INK2, lw=0.8); ax[1].axvline(50, color=INK2, lw=0.8, ls=':')
    ax[1].set(xlim=(1, 1e5), ylim=(-50, 12), xlabel='Frecuencia [Hz]', ylabel='S(f) = Vcm con RLD / Vcm pasiva 390k [dB]',
              title='Supresion del RLD y estabilidad (RLIM 390k)')
    ax[1].legend(fontsize=8, loc='lower right')
    save(fig, 't5_rld_frecuencia.png')
    M['t5'] = peaks


# --------------------------------------------------------------------- T6
def fit(t, y, f):
    X = np.column_stack([np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones_like(t)])
    c, *_ = np.linalg.lstsq(X, y, rcond=None)
    return np.hypot(c[0], c[1]), y - X @ c


def uniform(run, name, t0, t1, fs):
    t = run['time']; tt = np.arange(t0, t1, 1 / fs)
    return tt, np.interp(tt, t, get(run, name))


def t6():
    r = load_unrolled('t6_rld_tran.cir')
    names = {0: 'Sin RLD, referencia directa (sin R de seguridad)', 1: 'Sin RLD, referencia pasiva por 390k', 2: 'Con RLD (integrador, Cint 1 nF)'}
    res = {}
    fig, ax = plt.subplots(3, 2, figsize=(11, 7.5), sharex=True)
    for st, run in r:
        m, usb = int(st['rldmode']), st['cge'] > 1e-3
        a = ax[m, 1 if usb else 0]
        amps = []
        for k in range(4):
            tt, y = uniform(run, f'V(adc{k + 1})', 0.2, 0.3, 20000)
            amp, _ = fit(tt, y, 50)
            amps.append(amp / G_NOM * 1e6)
            a.plot((tt - 0.2) * 1e3, (y - 1.65) * 1e3, color=S[k], lw=1.3, label=f'ADC{k + 1}')
        res[f'mode{m}_{"usb" if usb else "bat"}_rti_uVpk'] = [round(x, 2) for x in amps]
        a.set_title(f'{names[m]}\n{"USB a PC" if usb else "a bateria"}: 50 Hz = {np.mean(amps):.2g} uVpk RTI', fontsize=9.5)
        a.set_ylabel('ADC - 1.65 V [mV]')
    for a in ax[-1]:
        a.set_xlabel('t - 200 ms [ms]')
    ax[0, 0].legend(ncol=4, fontsize=8, loc='upper right')
    fig.suptitle('T6: salidas ADC1..ADC4 con red de 311 Vpk y sin senal (las 4 curvas se superponen; misma escala por columna)', fontweight='bold', color=INK)
    for col in (0, 1):
        lim = max(abs(np.array(ax[m, col].get_ylim())).max() for m in range(3))
        for m in range(3):
            ax[m, col].set_ylim(-lim, lim)
    fig.tight_layout()
    save(fig, 't6_rld_tiempo.png')
    M['t6'] = res


# --------------------------------------------------------------------- T7
FK = [73, 131, 211, 307]
NTOT = np.sqrt(1e-3 ** 2 + 300e-6 ** 2)   # NLF, NWH de t7_func.cir
AS0 = NTOT * np.sqrt(2) / 10              # amplitud de la senoidal del caso limpio (CASE 0)


def pwl_uniform(fn, tt):
    d = np.loadtxt(os.path.join(HERE, 'noise', fn))
    return np.interp(tt, d[:, 0], d[:, 1])


def ideal(x, fs, fH, H):
    """Aplica la respuesta H(f) del AFE (T2, AC) a la senal x (registro completo, con relleno de ceros)."""
    n = 1 << int(np.ceil(np.log2(2 * len(x))))
    ff = np.fft.rfftfreq(n, 1 / fs)
    mag = np.interp(np.log10(np.maximum(ff, 1e-3)), np.log10(fH), np.abs(H), left=0, right=0)
    ph = np.interp(np.log10(np.maximum(ff, 1e-3)), np.log10(fH), np.unwrap(np.angle(H)))
    return np.fft.irfft(np.fft.rfft(x, n) * mag * np.exp(1j * ph), n)[:len(x)]


def digital(y, fs):
    """Etapa digital sugerida para la MCU (NO es parte del AFE): HPF Butterworth 4o orden 20 Hz + notch 50 Hz Q=30."""
    from scipy import signal
    sos = np.vstack([signal.butter(4, 20, 'highpass', fs=fs, output='sos'),
                     signal.tf2sos(*signal.iirnotch(50, 30, fs=fs))])
    return signal.sosfilt(sos, y - y[0])


def t7():
    r = {int(st['case']): run for st, run in load_unrolled('t7_func.cir')}
    fs, t0, t1 = 20000, 0.25, 1.25
    Hrun = load('t2_ac.cir')[0][1]
    fH = Hrun['frequency']
    res, curves = {}, {}
    snr = lambda a, rr: 10 * np.log10((a ** 2 / 2) / np.var(rr))
    for case in (1, 2):
        ratio = 10 if case == 1 else 100
        AS = NTOT * np.sqrt(2) / ratio
        for k in range(4):
            H = get(Hrun, f'V(adc{k + 1})')
            tt, d = uniform(r[case], f'V(d{k + 1})', 0, 1.25, fs)
            _, y = uniform(r[case], f'V(adc{k + 1})', 0, 1.25, fs)
            _, y0 = uniform(r[0], f'V(adc{k + 1})', 0, 1.25, fs)
            w = tt >= t0
            lf = 1e-3 * pwl_uniform(f'lf_ch{k + 1}.pwl', tt)
            wh = 300e-6 * pwl_uniform(f'wh_ch{k + 1}.pwl', tt)
            sn = AS * np.sin(2 * np.pi * FK[k] * tt)
            chk = np.std(d - (sn + lf + wh))            # la entrada simulada = suma conocida
            aout, rout = fit(tt[w], y[w], FK[k]); a0, _ = fit(tt[w], y0[w], FK[k])
            ain, _ = fit(tt[w], d[w], FK[k])   # incluye el ruido que cae en la frecuencia de la senoidal
            a50, _ = fit(tt[w], rout, 50)
            o_lf, o_wh = ideal(lf, fs, fH, H)[w], ideal(wh, fs, fH, H)[w]
            yd = digital(y, fs)
            ad, rd = fit(tt[w], yd[w], FK[k])
            ideal_noise = o_lf + o_wh
            res[f'r{ratio}_ch{k + 1}'] = {
                'snr_in_dB': round(snr(AS, (lf + wh)[w]), 1),
                'snr_out_dB': round(snr(aout, rout), 1),
                'snr_out_ideal_dB': round(snr(aout, ideal_noise), 1),
                'snr_out_digital_dB': round(snr(ad, rd), 1),
                'ganancia_med': round(aout / ain, 1), 'ganancia_limpia': round(a0 / AS0, 1),
                'err_ganancia_%': round((aout / ain) / (a0 / AS0) * 100 - 100, 2),
                'ruido_out_rti_uVrms': round(np.std(rout) / G_NOM * 1e6, 1),
                'pred_lf_rti_uVrms': round(np.std(o_lf) / G_NOM * 1e6, 1),
                'pred_wh_rti_uVrms': round(np.std(o_wh) / G_NOM * 1e6, 1),
                'red50_out_rti_uVpk': round(a50 / G_NOM * 1e6, 2),
                'chk_entrada_uV': round(chk * 1e6, 3)}
            if k == 0:
                curves[ratio] = (tt, d, y, y0, yd, AS)
    M['t7'] = res
    # figura: tiempo (CH1) para las dos razones
    fig, ax = plt.subplots(2, 3, figsize=(13, 6.4))
    sl = lambda tt: (tt >= 0.8) & (tt < 1.0)
    for row, ratio in enumerate((10, 100)):
        tt, d, y, y0, yd, AS = curves[ratio]; m = sl(tt); x = (tt[m] - 0.8) * 1e3
        ref = (y0[m] - y0[m].mean()) * (AS / AS0)
        a = ax[row, 0]
        a.plot(x, d[m] * 1e6, color=INK2, lw=0.5, label='entrada = senoidal + ruido')
        a.plot(x, AS * np.sin(2 * np.pi * 73 * tt[m]) * 1e6, color=S[0], lw=2, label='senoidal sola')
        a.set(ylabel='CH1 entrada [uV]', title=f'Entrada: senoidal 73 Hz {ratio}x menor que el ruido (RMS)')
        a = ax[row, 1]
        a.plot(x, (y[m] - 1.65) * 1e3, color=S[1], lw=1, label='salida ADC1')
        a.plot(x, ref * 1e3, color=S[0], lw=2, ls='--', label='senoidal esperada (corrida sin ruido)')
        a.set(ylabel='ADC1 - 1.65 V [mV]', title='Salida del AFE')
        a = ax[row, 2]
        a.plot(x, yd[m] * 1e3, color=S[2], lw=1, label='salida + filtro digital')
        a.plot(x, ref * 1e3, color=S[0], lw=2, ls='--', label='senoidal esperada')
        a.set(ylabel='[mV]', title='Salida + HPF 4o 20 Hz + notch 50 Hz (MCU)')
        for a in ax[row]:
            a.legend(fontsize=7.5, loc='upper right')
    for a in ax[-1]:
        a.set_xlabel('t - 800 ms [ms]')
    fig.tight_layout()
    save(fig, 't7_tiempo_ch1.png')
    # figura: espectros entrada vs salida referida a la entrada, 4 canales
    fig, ax = plt.subplots(2, 4, figsize=(13, 5.8), sharex=True, sharey=True)
    for row, case in enumerate((1, 2)):
        for k in range(4):
            tt, d = uniform(r[case], f'V(d{k + 1})', t0, t1, fs)
            _, y = uniform(r[case], f'V(adc{k + 1})', t0, t1, fs)
            win = np.hanning(len(tt)); enbw = fs * np.sum(win ** 2) / np.sum(win) ** 2
            asd = lambda x: np.abs(np.fft.rfft((x - x.mean()) * win)) * np.sqrt(2) / np.sum(win) / np.sqrt(enbw)
            ff = np.fft.rfftfreq(len(tt), 1 / fs)
            a = ax[row, k]
            a.loglog(ff[1:], asd(d)[1:] * 1e9, color=INK2, lw=0.5, label='entrada')
            a.loglog(ff[1:], asd(y)[1:] / G_NOM * 1e9, color=S[k], lw=0.8, label='salida / 503')
            a.set_title(f'CH{k + 1}, {FK[k]} Hz, senoidal {10 if case == 1 else 100}x menor', fontsize=9)
            if k == 0:
                a.set_ylabel('Densidad RTI [nV/rtHz]')
                a.legend(fontsize=8, loc='lower left')
    for a in ax[-1]:
        a.set_xlabel('Frecuencia [Hz]')
    ax[0, 0].set_xlim(1, 1e4); ax[0, 0].set_ylim(1, 3e5)
    fig.suptitle('T7: espectro de la entrada y de la salida dividida por la ganancia nominal (503); el pico es la senoidal',
                 fontweight='bold', color=INK)
    fig.tight_layout()
    save(fig, 't7_espectros.png')


if __name__ == '__main__':
    for fn in (t2, t4, t4b, t5, t6, t7):
        fn()
    json.dump(M, open(os.path.join(OUT, 'metricas.json'), 'w'), indent=1, ensure_ascii=False)
    print(json.dumps(M, indent=1, ensure_ascii=False))
