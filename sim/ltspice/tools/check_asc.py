"""Verifica que los esquematicos generados (AFE_4CH.asc + CANAL.asc) tengan exactamente
la misma conectividad que los netlists simulados (afe_channel.lib, afe_4ch_top.inc, t7_func.cir).
Usa el netlist que LTspice extrae del .asc (wine LTspice.exe -netlist AFE_4CH.asc)."""
import os, re, subprocess, sys
HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def elements(lines):
    """name -> lista de nodos (sin valor). Solo R, C, D, V, B, X."""
    out = {}
    for l in lines:
        l = l.split(';')[0].strip()
        if not l or l[0] in '*.+':
            continue
        t = l.split()
        name = t[0].replace('X§', '')
        if t[0].startswith('X§') and not name.upper().startswith('X'):
            name = 'X' + name
        k = name[0].upper()
        n = {'R': 2, 'C': 2, 'D': 2, 'V': 2, 'B': 2}.get(k)
        if k == 'X':
            # nodos hasta el nombre del subcircuito (primer token con letras que no es nodo conocido)
            toks = [x for x in t[1:] if '=' not in x]
            n = len(toks) - 1
        if n:
            out[name.upper()] = [x.upper() for x in t[1:1 + n]]
    return out


def block(txt, name):
    m = re.search(rf'^\.subckt {name}\b.*?$(.*?)^\.ends', txt, re.M | re.S | re.I)
    return m.group(1).splitlines()


def compare(ref, sch, what, fixed=('0',)):
    errs, m, inv = [], {f: f for f in fixed}, {f: f for f in fixed}
    for e in sorted(ref, key=lambda e: (e[0] in 'RC', -sum(n in fixed for n in ref[e]), e)):
        if e not in sch:
            errs.append(f'{what}: falta {e} en el esquematico'); continue
        if len(ref[e]) != len(sch[e]):
            errs.append(f'{what}: {e} tiene {len(sch[e])} pines, esperado {len(ref[e])}'); continue
        orders = [sch[e]]
        if e[0] in 'RC':  # sin polaridad: se acepta cualquier orden de pines
            orders.append(sch[e][::-1])
        for o in orders:
            if all(m.get(a, b) == b and inv.get(b, a) == a for a, b in zip(ref[e], o)):
                for a, b in zip(ref[e], o):
                    m[a], inv[b] = b, a
                break
        else:
            errs.append(f'{what}: {e} nodos ref {ref[e]} vs esquematico {sch[e]} (inconsistente)')
    for e in sorted(set(sch) - set(ref)):
        errs.append(f'{what}: {e} sobra en el esquematico')
    return errs


if __name__ == '__main__':
    subprocess.run(['wine', r'C:\Program Files\ADI\LTspice\LTspice.exe', '-netlist', 'AFE_4CH.asc'],
                   cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    net = open(os.path.join(HERE, 'AFE_4CH.net'), encoding='utf-8', errors='replace').read()
    lib = open(os.path.join(HERE, 'afe_channel.lib'), encoding='latin-1').read()
    errs = compare(elements(block(lib, 'AFE_CH')), elements(block(net, 'CANAL')), 'CANAL',
                   fixed=('0', 'EP', 'EN', 'VCC', 'VREF', 'ADC', 'RGM', 'INAOUT'))
    # nivel superior: afe_4ch_top.inc (sin R de sensado sobre electrodos) + VREFGEN aplanado + estimulos de t7
    top = open(os.path.join(HERE, 'afe_4ch_top.inc'), encoding='latin-1').read().splitlines()
    ref = elements(top)
    ref = {k: v for k, v in ref.items() if not k.startswith('RSE') and k != 'XVREF'}
    for e, nodes in elements(block(lib, 'VREFGEN')).items():
        ref[e if e != 'XVR' else 'XVR'] = ['VREF_DIV' if n == 'VD' else n for n in nodes]
    t7 = elements(open(os.path.join(HERE, 't7_func.cir'), encoding='latin-1').read().splitlines())
    ref.update({k: v for k, v in t7.items() if k[:2] in ('VL', 'VW') or k.startswith('BIN')})
    sch = {k: v for k, v in elements(net.split('* block symbol definitions')[0].splitlines()).items()}
    errs += compare(ref, sch, 'AFE_4CH', fixed=('0', 'VCC', 'VREF', 'BODY'))
    print('\n'.join(errs) if errs else 'OK: conectividad del esquematico = netlists simulados '
          f'({len(elements(block(net, "CANAL")))} elementos en CANAL, {len(sch)} en AFE_4CH)')
    sys.exit(1 if errs else 0)
