"""Lector minimo de archivos .raw binarios de LTspice (AC y transitorio, con .step)
y de las lineas .step del .log."""
import re
import numpy as np


def read_raw(path, nsteps=None):
    """Devuelve (vars, runs). vars: lista de nombres; runs: lista de dict nombre->array.
    Un run por cada paso de .step. Con nsteps (de steps_from_cir) el corte es exacto;
    sin nsteps se corta donde el eje x vuelve a empezar."""
    data = open(path, 'rb').read()
    key = 'Binary:\n'.encode('utf-16le')
    i = data.find(key)
    if i < 0:
        raise ValueError(f'{path}: no es un .raw binario')
    hdr = data[:i].decode('utf-16le')
    body = data[i + len(key):]
    flags = re.search(r'Flags:(.*)', hdr).group(1).split()
    nvar = int(re.search(r'No. Variables:\s*(\d+)', hdr).group(1))
    npts = int(re.search(r'No. Points:\s*(\d+)', hdr).group(1))
    names = re.findall(r'^\t\d+\t(\S+)\t', hdr.split('\nVariables:\n')[1], re.M)
    assert len(names) == nvar, (len(names), nvar)
    if 'complex' in flags:
        arr = np.frombuffer(body, dtype='<c16', count=npts * nvar).reshape(npts, nvar)
        x = arr[:, 0].real
        cols = {n: arr[:, k] for k, n in enumerate(names)}
        cols[names[0]] = x
    elif 'double' in flags:
        arr = np.frombuffer(body, dtype='<f8', count=npts * nvar).reshape(npts, nvar)
        x = np.abs(arr[:, 0])
        cols = {n: arr[:, k] for k, n in enumerate(names)}
        cols[names[0]] = x
    else:
        dt = np.dtype([('x', '<f8')] + [(f'v{k}', '<f4') for k in range(1, nvar)])
        rec = np.frombuffer(body, dtype=dt, count=npts)
        x = np.abs(rec['x'])
        cols = {names[0]: x}
        cols.update({n: rec[f'v{k}'].astype(float) for k, n in enumerate(names) if k})
    # separar pasos
    if nsteps and 'complex' in flags:
        m = len(x) // nsteps
        starts = list(range(0, len(x) + 1, m))
    else:
        starts = [0] + [k for k in range(1, len(x)) if x[k] < x[k - 1]] + [len(x)]
    if nsteps:
        assert len(starts) - 1 == nsteps, (path, len(starts) - 1, nsteps)
    runs = [{n: v[a:b] for n, v in cols.items()} for a, b in zip(starts[:-1], starts[1:])]
    return names, runs


SI = {'t': 1e12, 'g': 1e9, 'meg': 1e6, 'k': 1e3, 'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'f': 1e-15}


def si(v):
    m = re.fullmatch(r'([-+0-9.eE]+)(meg|[tgkmunpf])?\w*', v.strip().lower())
    return float(m.group(1)) * (SI[m.group(2)] if m.group(2) else 1.0)


def steps_from_cir(cirpath):
    """Tabla de pasos a partir de las lineas '.step param X list a b c' del netlist.
    En LTspice la primera linea .step es la que varia mas rapido."""
    import itertools
    lines = [l for l in open(cirpath, encoding='latin-1') if l.lower().startswith('.step param')]
    axes = []
    for l in lines:
        tok = l.split(';')[0].split()
        name = tok[2].lower()
        assert tok[3].lower() == 'list', l
        axes.append((name, [si(v) for v in tok[4:]]))
    if not axes:
        return [{}]
    out = []
    for combo in itertools.product(*[vals for _, vals in reversed(axes)]):
        out.append({n: v for (n, _), v in zip(reversed(axes), combo)})
    return out


def read_steps(logpath):
    """Lista de dict param->valor, uno por paso, leida de las lineas '.step' del .log."""
    txt = open(logpath, 'rb').read().replace(b'\x00', b'').decode('latin-1')
    steps = []
    for line in txt.splitlines():
        if line.startswith('.step '):
            d = {}
            for k, v in re.findall(r'(\w+)=(\S+)', line):
                d[k.lower()] = float(v.replace('meg', 'e6').replace('k', 'e3').replace('p', 'e-12')
                                     .replace('n', 'e-9').replace('u', 'e-6').replace('m', 'e-3')
                                     .replace('f', 'e-15').replace('t', 'e12'))
            steps.append(d)
    return steps


def get(run, name):
    """Busca una variable ignorando mayusculas (LTspice guarda V(adc1), etc.)."""
    for n, v in run.items():
        if n.lower() == name.lower():
            return v
    raise KeyError(name)
