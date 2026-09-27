"""Corre netlists de LTspice en modo batch (wine) y, con --unroll, reparte cada paso
de .step en un proceso aparte (en paralelo) para aprovechar los nucleos.

  python3 tools/run.py t2_ac.cir t4_cm.cir          # tal cual, uno tras otro
  python3 tools/run.py --unroll -j 3 t7_func.cir    # un proceso por paso, 3 a la vez

Los netlists desenrollados quedan como _u_<nombre>_s<k>.cir (+ .raw/.log), ignorados por git.
"""
import argparse, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
from ltraw import steps_from_cir, read_raw

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LTSPICE = r'C:\Program Files\ADI\LTspice\LTspice.exe'


def run_one(cir, timeout=3600):
    t0 = time.time()
    subprocess.run(['wine', LTSPICE, '-b', cir], cwd=HERE, timeout=timeout,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = os.path.join(HERE, cir[:-4] + '.log')
    txt = open(log, 'rb').read().replace(b'\x00', b'').decode('latin-1') if os.path.exists(log) else ''
    bad = [l for l in txt.splitlines() if re.search(r'error|cannot|failed to find|singular', l, re.I)
           and 'Gmin stepping' not in l and 'Source stepping' not in l]
    print(f'{cir}: {time.time() - t0:.0f} s' + (f'  AVISO: {bad[:3]}' if bad else ''), flush=True)
    return cir


def unroll(cir):
    """Escribe un netlist por paso de .step; devuelve [(paso, archivo)]."""
    name = cir[:-4]
    lines = open(os.path.join(HERE, cir), encoding='latin-1').read().splitlines()
    body = [l for l in lines if not l.lower().startswith('.step')]
    out = []
    for k, st in enumerate(steps_from_cir(os.path.join(HERE, cir))):
        fn = f'_u_{name}_s{k}.cir'
        params = ' '.join(f'{p}={v:.12g}' for p, v in st.items())
        txt = [body[0], f'* paso {k} de {cir}: {params}', f'.param {params}'] + body[1:]
        open(os.path.join(HERE, fn), 'w').write('\n'.join(txt) + '\n')
        out.append((st, fn))
    return out


def load_unrolled(cir):
    """[(paso, run)] leyendo los .raw de los netlists desenrollados."""
    res = []
    for k, st in enumerate(steps_from_cir(os.path.join(HERE, cir))):
        _, runs = read_raw(os.path.join(HERE, f'_u_{cir[:-4]}_s{k}.raw'))
        res.append((st, runs[0]))
    return res


def load(cir):
    """[(paso, run)] leyendo el .raw del netlist con .step."""
    st = steps_from_cir(os.path.join(HERE, cir))
    _, runs = read_raw(os.path.join(HERE, cir[:-4] + '.raw'), len(st))
    return list(zip(st, runs))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cir', nargs='+')
    ap.add_argument('--unroll', action='store_true')
    ap.add_argument('-j', type=int, default=3)
    a = ap.parse_args()
    jobs = []
    for c in a.cir:
        jobs += [fn for _, fn in unroll(c)] if a.unroll else [c]
    with ThreadPoolExecutor(a.j if a.unroll else 1) as ex:
        list(ex.map(run_one, jobs))
