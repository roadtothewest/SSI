"""Verifica que los esquematicos generados (AFE_4CH.asc + CANAL.asc) tengan exactamente
la misma conectividad que los netlists simulados (afe_channel.lib, afe_4ch_top.inc, t7_func.cir).
Usa el netlist que LTspice extrae del .asc (wine LTspice.exe -netlist AFE_4CH.asc)."""
import os, re, subprocess, sys
HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def elements(lines):
    """name -> lista de nodos (sin valor). Solo R, C, L, D, V, B, E, X."""
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
        n = {'R': 2, 'C': 2, 'L': 2, 'D': 2, 'V': 2, 'B': 2, 'E': 4}.get(k)
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


STIM = ('VL', 'VW', 'VSG', 'VNZ', 'BIN', 'VIN', 'BW', 'LSEM', 'CSEM', 'RSEM', 'BSEM', 'VENV', 'VECG', 'EDK', 'RDK', 'CSH', 'VUSB', 'XLDO', 'CLDOI', 'CLDOO', 'CBULK')
PROBE = re.compile(r'^(W|F|SEMG)\d$|^(ENV|ECG|RLDO)$')


def check(asc):
    subprocess.run(['wine', r'C:\Program Files\ADI\LTspice\LTspice.exe', '-netlist', asc],
                   cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    net = open(os.path.join(HERE, asc[:-4] + '.net'), encoding='utf-8', errors='replace').read()
    os.remove(os.path.join(HERE, asc[:-4] + '.net'))
    lib = open(os.path.join(HERE, 'afe_channel.lib'), encoding='latin-1').read()
    errs = compare(elements(block(lib, 'AFE_CH')), elements(block(net, 'CANAL')), 'CANAL',
                   fixed=('0', 'EP', 'EN', 'VCC', 'VREF', 'ADC', 'RGM', 'INAOUT'))
    top = open(os.path.join(HERE, 'afe_3ch_top.inc'), encoding='latin-1').read().splitlines()
    ref = {k: v for k, v in elements(top).items() if not k.startswith('RSE') and k != 'XVREF'}
    ref.update({k: v[:6] for k, v in ref.items() if k.startswith('XCH')})
    ref.pop('RPAS', None)   # sin modos: el RLD va siempre al electrodo por RLIM
    ref.pop('VCC', None)   # el esquematico genera 3.3 V con el TLV75733P desde 5 V   # el bloque CANAL ya no expone INAOUT
    for e, nodes in elements(block(lib, 'VREFGEN')).items():
        ref[e] = ['VREF_DIV' if n == 'VD' else n for n in nodes]
    sch = {k: v for k, v in elements(net.split('* block symbol definitions')[0].splitlines()).items()
           if not k.startswith(STIM)}
    errs += compare(ref, sch, asc, fixed=('0', 'VCC', 'VREF', 'BODY'))
    # sin cables abiertos: ningun NC_ y toda red con >= 2 pines (salvo nodos de generadores leidos por expresion)
    allel = elements(net.split('* block symbol definitions')[0].splitlines())
    allel.update({'CANAL:' + k: v for k, v in elements(block(net, 'CANAL')).items()})
    cnt = {}
    for e, nodes in allel.items():
        pre = 'CANAL:' if e.startswith('CANAL:') else ''
        for n in nodes:
            cnt[pre + n] = cnt.get(pre + n, 0) + 1
    ports = {'CANAL:' + p for p in ('EP', 'EN', 'VCC', 'VREF', 'ADC', 'RGM')}
    for n, c in sorted(cnt.items()):
        if 'NC_' in n:
            errs.append(f'{asc}: pin sin conectar ({n})')
        elif c < 2 and n not in ports and n != '0' and not PROBE.match(n.split(':')[-1]):
            errs.append(f'{asc}: red {n} con un solo pin')
    print(f'{asc}: ' + ('\n'.join(errs) if errs else 'OK, conectividad = netlists simulados '
          f'({len(elements(block(net, "CANAL")))} elementos en CANAL, {len(sch)} en el nivel superior)'))
    return not errs


if __name__ == '__main__':
    ok = [check(a) for a in (sys.argv[1:] or ['AuraVox_AFE.asc'])]
    sys.exit(0 if all(ok) else 1)
