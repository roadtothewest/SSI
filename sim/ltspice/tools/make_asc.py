"""Genera los esquematicos LTspice del AFE (jerarquicos):
  CANAL.asc + CANAL.asy   un canal (bloque), mismos componentes y nombres que AFE_CH
  AFE_4CH.asc             4 canales, 9 electrodos, RLD, VREF, cuerpo y red, estimulos
  INA333.asy, ELECTRODO.asy  simbolos propios
La conectividad se verifica con tools/check_asc.py (netlist de LTspice vs afe_channel.lib).
"""
import os

HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# desplazamiento (x) del pin y (y) de cada pin en R0, largo entre pines
TWO = {'res': (16, 16, 80), 'cap': (16, 0, 64), 'diode': (16, 0, 64),
       'voltage': (0, 16, 80), 'bv': (0, 16, 80)}
ROT = {'R0': lambda x, y: (x, y), 'R90': lambda x, y: (-y, x),
       'R180': lambda x, y: (-x, -y), 'R270': lambda x, y: (y, -x)}


class Sheet:
    def __init__(self, w=3400, h=1400):
        self.out = ['Version 4', f'SHEET 1 {w} {h}']
        self.wires, self.flags, self.syms, self.texts = [], [], [], []

    # --- primitivas ---
    def wire(self, *pts):
        for a, b in zip(pts[:-1], pts[1:]):
            assert a[0] == b[0] or a[1] == b[1], (a, b)
            self.wires.append(f'WIRE {a[0]} {a[1]} {b[0]} {b[1]}')

    def flag(self, p, net, iopin=None):
        self.flags.append(f'FLAG {p[0]} {p[1]} {net}')
        if iopin:
            self.flags.append(f'IOPIN {p[0]} {p[1]} {iopin}')

    def text(self, p, s, size=2, directive=False):
        s = s.replace('\n', '\\n')
        self.texts.append(f'TEXT {p[0]} {p[1]} Left {size} {"!" if directive else ";"}{s}')

    def symbol(self, sym, name, origin, rot, value=None, attrs=(), windows=()):
        l = [f'SYMBOL {sym} {origin[0]} {origin[1]} {rot}']
        l += [f'WINDOW {w}' for w in windows]
        l.append(f'SYMATTR InstName {name}')
        if value is not None:
            l.append(f'SYMATTR Value {value}')
        l += [f'SYMATTR {k} {v}' for k, v in attrs]
        self.syms.append('\n'.join(l))

    # --- componentes de 2 pines: se dan las coordenadas de sus dos pines ---
    def two(self, sym, name, p1, p2, value, attrs=()):
        px, a, L = TWO[sym]
        d = (p2[0] - p1[0], p2[1] - p1[1])
        rot = {(0, L): 'R0', (0, -L): 'R180', (L, 0): 'R270', (-L, 0): 'R90'}[d]
        rx, ry = ROT[rot](px, a)
        o = (p1[0] - rx, p1[1] - ry)
        win = {'R90': ('0 0 56 VBottom 2', '3 32 56 VTop 2'),
               'R270': ('0 32 56 VTop 2', '3 0 56 VBottom 2')}.get(rot, ())
        if sym in ('cap',) and rot in ('R90', 'R270'):
            win = ('0 0 32 VBottom 2', '3 32 32 VTop 2') if rot == 'R90' else ('0 32 32 VTop 2', '3 0 32 VBottom 2')
        self.symbol(sym, name, o, rot, value, attrs, win)

    def R(self, n, p1, p2, v): self.two('res', n, p1, p2, v)
    def C(self, n, p1, p2, v): self.two('cap', n, p1, p2, v)
    def D(self, n, a, k, v='D1N4148'): self.two('diode', n, a, k, v)

    def opamp(self, name, inp, value='OPA'):
        """opamp2 (In- arriba, In+ abajo). Devuelve dict de pines."""
        o = (inp[0] + 32, inp[1] - 80)
        self.symbol('OpAmps\\\\opamp2', name, o, 'R0', value)
        return {'inp': inp, 'inn': (o[0] - 32, o[1] + 48), 'vp': (o[0], o[1] + 32),
                'vn': (o[0], o[1] + 96), 'out': (o[0] + 32, o[1] + 64)}

    def supplies(self, pins, vp='VCC', vn='0'):
        self.wire(pins['vp'], (pins['vp'][0], pins['vp'][1] - 16)); self.flag((pins['vp'][0], pins['vp'][1] - 16), vp)
        self.wire(pins['vn'], (pins['vn'][0], pins['vn'][1] + 16)); self.flag((pins['vn'][0], pins['vn'][1] + 16), vn)

    def gnd(self, p, dy=16):
        q = (p[0], p[1] + dy); self.wire(p, q); self.flag(q, '0')

    def label(self, p, net, dx=0, dy=0, iopin=None):
        q = (p[0] + dx, p[1] + dy)
        if q != p:
            self.wire(p, q)
        self.flag(q, net, iopin)

    def save(self, fn):
        txt = '\n'.join(self.out + self.wires + self.flags + self.syms + self.texts) + '\n'
        open(os.path.join(HERE, fn), 'w', newline='\r\n').write(txt)


def follower_feedback(s, pins, top_y, extra_from=None):
    """Realimentacion de seguidor: In- -> linea superior -> salida."""
    ox = pins['out'][0] + 32
    s.wire(pins['out'], (ox, pins['out'][1]))
    xi = pins['inn'][0] - 16
    left = extra_from[0] if extra_from else xi
    if extra_from:
        s.wire(extra_from, (extra_from[0], top_y))
    s.wire((left, top_y), (ox, top_y), (ox, pins['out'][1]))
    s.wire(pins['inn'], (xi, pins['inn'][1]), (xi, top_y))
    return (ox, pins['out'][1])


# ---------------------------------------------------------------------------
def canal():
    s = Sheet(3500, 900)
    s.text((0, -256), 'CANAL sEMG (se instancia 4 veces en AFE_4CH.asc). Nombres = subcircuito AFE_CH de afe_channel.lib. Valores: docs/afe-emg/AFE_valores_ltspice.md', 2)
    s.flag((-96, 640), 'VCC', 'In'); s.flag((-96, 704), 'VREF', 'In')
    s.text((-96, 600), 'Alimentacion (puertos)', 1)
    # 1) proteccion + RFI + INA
    s.text((0, -160), '1) Proteccion ESD (Rs + 1N4148) + filtro RFI\nINA333: G1 = 1 + 100k/RG = 20.16\nRG partido: punto medio RGM -> RLD', 2)
    for side, y, sgn in (('p', 160, -1), ('n', 480, 1)):
        P = side.upper()
        s.label((32, y), 'E' + P, dx=-32, iopin='In')
        s.R(f'Rs{side}', (32, y), (112, y), '{RS}')
        s.wire((112, y), (176, y), (240, y))
        if side == 'p':
            s.D('Dp1', (176, 128), (176, 64)); s.wire((176, 160), (176, 128)); s.label((176, 64), 'VCC', dy=-16)
            s.D('Dp2', (176, 256), (176, 192)); s.wire((176, 160), (176, 192)); s.gnd((176, 256))
        else:
            s.D('Dn1', (176, 512), (176, 576)); s.wire((176, 480), (176, 512)); s.label((176, 576), 'VCC', dy=16)
            s.D('Dn2', (176, 384), (176, 448)); s.wire((176, 448), (176, 480)); s.label((176, 384), '0', dy=-16)
        s.R(f'Rf{side}', (240, y), (320, y), '1k')
        s.wire((320, y), (384, y), (416, y), (544, y))
    s.C('Ccmp', (384, 160), (384, 224), '{CCM}'); s.gnd((384, 224))
    s.C('Ccmn', (384, 480), (384, 416), '{CCM}'); s.label((384, 416), '0', dy=-16)
    s.wire((416, 160), (416, 288)); s.C('Cdif', (416, 288), (416, 352), '{CD}'); s.wire((416, 352), (416, 480))
    s.symbol('INA333', 'XINA', (640, 320), 'R0', 'INA333')
    s.wire((544, 224), (480, 224)); s.R('RGa', (480, 224), (480, 304), '2.61k')
    s.wire((480, 304), (480, 320), (480, 336)); s.R('RGb', (480, 336), (480, 416), '2.61k'); s.wire((480, 416), (544, 416))
    s.label((480, 320), 'RGM', dx=32, iopin='Out')
    s.label((640, 128), 'VCC', dy=-16); s.gnd((640, 512)); s.label((704, 512), 'VREF', dy=16)
    s.wire((736, 320), (768, 320)); s.flag((768, 320), 'INAOUT', 'Out')
    # 2) HPF Sallen-Key
    s.text((960, -96), '2) HPF Sallen-Key 2o orden\n20 Hz, ganancia 1', 2)
    s.label((992, 320), 'INAOUT', dx=-32)
    s.C('Chp1', (992, 320), (1056, 320), '100n')
    s.wire((1056, 320), (1088, 320), (1120, 320))
    s.R('R1', (1088, 320), (1088, 240), '56.2k')
    s.C('Chp2', (1120, 320), (1184, 320), '100n')
    s.wire((1184, 320), (1216, 320), (1248, 320))
    s.R('Ra', (1216, 320), (1216, 400), '113k'); s.label((1216, 400), 'VREF', dy=16)
    op = s.opamp('XHP', (1248, 320)); s.supplies(op)
    o = follower_feedback(s, op, 208, extra_from=(1088, 240))
    s.label(o, 'HPO', dx=32)
    # 3) G2
    s.text((1440, -96), '3) G2 = 1 + Rf/Rg = 25\n(Cg deja G = 1 en DC)', 2)
    s.label((1568, 320), 'HPO', dx=-64)
    op = s.opamp('XG2', (1568, 320)); s.supplies(op)
    s.wire(op['inn'], (1536, 288), (1536, 240), (1536, 176))
    s.R('Rf', (1536, 176), (1616, 176), '240k')
    s.wire((1616, 176), (1664, 176), (1664, 304)); s.wire(op['out'], (1664, 304), (1696, 304)); s.flag((1696, 304), 'G2O')
    s.R('Rg', (1536, 240), (1456, 240), '10k')
    s.C('Cg', (1456, 240), (1456, 304), '10u'); s.label((1456, 304), 'VREF', dy=32)

    # 4) y 5) LPF Sallen-Key
    def lpf(bx, names, vin, vout, vals, title):
        r1, r2, cfb, cg, x = names
        s.text((bx, -96), title, 2)
        s.label((bx + 32, 320), vin, dx=-32)
        s.R(r1, (bx + 32, 320), (bx + 112, 320), vals[0])
        s.wire((bx + 112, 320), (bx + 144, 320), (bx + 176, 320))
        s.C(cfb, (bx + 144, 320), (bx + 144, 256), vals[2])
        s.R(r2, (bx + 176, 320), (bx + 256, 320), vals[1])
        s.wire((bx + 256, 320), (bx + 288, 320), (bx + 320, 320))
        s.C(cg, (bx + 288, 320), (bx + 288, 384), vals[3]); s.gnd((bx + 288, 384))
        op = s.opamp(x, (bx + 320, 320)); s.supplies(op)
        o = follower_feedback(s, op, 208, extra_from=(bx + 144, 256))
        s.label(o, vout, dx=32)
    lpf(1792, ('Rla1', 'Rla2', 'C11', 'C12', 'XLA'), 'G2O', 'LAO', ('88.7k', '88.7k', '3.9n', '3.3n'),
        '4) LPF A Sallen-Key\n500 Hz, Q 0.541')
    lpf(2336, ('Rlb1', 'Rlb2', 'C21', 'C22', 'XLB'), 'LAO', 'LBO', ('54.9k', '54.9k', '15n', '2.2n'),
        '5) LPF B Sallen-Key\n500 Hz, Q 1.306')
    # 6) buffer + bucket
    s.text((2880, -96), '6) Buffer + bucket\nal ADC (100 ohm + 1 nF)', 2)
    s.label((2944, 320), 'LBO', dx=-32)
    op = s.opamp('XBF', (2944, 320)); s.supplies(op)
    o = follower_feedback(s, op, 208)
    s.R('Rbk', o, (o[0] + 80, o[1]), '100')
    e = (o[0] + 80, o[1])
    s.wire(e, (e[0] + 32, e[1]), (e[0] + 64, e[1]))
    s.C('Cbk', (e[0] + 32, e[1]), (e[0] + 32, e[1] + 64), '1n'); s.gnd((e[0] + 32, e[1] + 64))
    s.flag((e[0] + 64, e[1]), 'ADC', 'Out')
    s.save('CANAL.asc')


def symbols():
    canal_asy = """Version 4
SymbolType BLOCK
RECTANGLE Normal -128 -96 128 96
TEXT 0 -72 Center 2 CANAL sEMG
TEXT 0 -40 Center 1 prot+RFI, INA333 (G1 20)
TEXT 0 -16 Center 1 HPF 20 Hz, G2 25
TEXT 0 8 Center 1 LPF 4o orden 500 Hz
TEXT 0 32 Center 1 buffer + bucket
PIN -128 -48 LEFT 8
PINATTR PinName EP
PINATTR SpiceOrder 1
PIN -128 48 LEFT 8
PINATTR PinName EN
PINATTR SpiceOrder 2
PIN -48 -96 TOP 8
PINATTR PinName VCC
PINATTR SpiceOrder 3
PIN 48 -96 TOP 8
PINATTR PinName VREF
PINATTR SpiceOrder 4
PIN 128 0 RIGHT 8
PINATTR PinName ADC
PINATTR SpiceOrder 5
PIN -48 96 BOTTOM 8
PINATTR PinName RGM
PINATTR SpiceOrder 6
PIN 48 96 BOTTOM 8
PINATTR PinName INAOUT
PINATTR SpiceOrder 7
"""
    ina_asy = """Version 4
SymbolType CELL
LINE Normal -96 -192 -96 192
LINE Normal -96 -192 96 0
LINE Normal -96 192 96 0
TEXT -80 -160 Left 1 +IN
TEXT -80 160 Left 1 -IN
TEXT -80 -96 Left 1 RG
TEXT -80 96 Left 1 RG
TEXT -16 0 Center 2 INA333
WINDOW 0 16 -176 Left 2
WINDOW 3 16 176 Left 2
SYMATTR Prefix X
SYMATTR Value INA333
SYMATTR Description INA333 (TI). Modelo: models/INA333.LIB o models/ina_behav.lib
PIN -96 -160 NONE 0
PINATTR PinName IN+
PINATTR SpiceOrder 1
PIN -96 160 NONE 0
PINATTR PinName IN-
PINATTR SpiceOrder 2
PIN 0 -192 NONE 0
PINATTR PinName VCC
PINATTR SpiceOrder 3
PIN 0 192 NONE 0
PINATTR PinName VEE
PINATTR SpiceOrder 4
PIN 96 0 NONE 0
PINATTR PinName OUT
PINATTR SpiceOrder 5
PIN 64 192 NONE 0
PINATTR PinName REF
PINATTR SpiceOrder 6
PIN -96 -96 NONE 0
PINATTR PinName RG+
PINATTR SpiceOrder 7
PIN -96 96 NONE 0
PINATTR PinName RG-
PINATTR SpiceOrder 8
"""
    elec_asy = """Version 4
SymbolType CELL
RECTANGLE Normal -24 16 24 80
LINE Normal -12 28 12 28
LINE Normal -12 36 12 36
LINE Normal -6 44 6 44
TEXT 0 64 Center 0 Re||Ce
WINDOW 0 32 24 Left 2
WINDOW 39 32 56 Left 1
SYMATTR Prefix X
SYMATTR Value ELECTRODE
SYMATTR SpiceLine Vhc=0
SYMATTR Description Electrodo: media celda Vhc + 20k || 47n (subcircuito ELECTRODE de afe_channel.lib)
PIN 0 0 NONE 0
PINATTR PinName SKIN
PINATTR SpiceOrder 1
PIN 0 96 NONE 0
PINATTR PinName LEAD
PINATTR SpiceOrder 2
"""
    for fn, t in (('CANAL.asy', canal_asy), ('INA333.asy', ina_asy), ('ELECTRODO.asy', elec_asy)):
        open(os.path.join(HERE, fn), 'w', newline='\r\n').write(t)


# ---------------------------------------------------------------------------
def top():
    s = Sheet(3800, 3000)
    s.text((0, -320), 'AuraVox - AFE sEMG completo: 4 canales diferenciales, 9 electrodos (4 pares + RLD), 4 salidas ADC1..ADC4', 3)
    s.text((0, -256), 'Doble clic en un bloque CANAL (o clic derecho > Open Hierarchy) para ver el canal. Prueba por defecto = T7: senoidal + ruido (10x) en los 4 canales, RLD activo.', 2)
    # --- alimentacion y VREF ---
    s.text((0, -160), 'Alimentacion 3.3 V y VREF = 1.65 V', 2)
    s.two('voltage', 'VCC', (32, -64), (32, 16), '3.3'); s.label((32, -64), 'VCC', dy=-16); s.gnd((32, 16))
    s.R('RA1', (224, -96), (224, -16), '100k'); s.label((224, -96), 'VCC', dy=-16)
    s.wire((224, -16), (224, 0), (224, 16)); s.R('RA2', (224, 16), (224, 96), '100k'); s.gnd((224, 96))
    s.wire((224, 0), (288, 0), (352, 0)); s.C('CA', (288, 0), (288, 64), '10u'); s.gnd((288, 64))
    op = s.opamp('XVR', (352, 0)); s.supplies(op)
    o = follower_feedback(s, op, -128)
    s.label(o, 'VREF', dx=32)
    # --- red y cuerpo ---
    s.text((720, -160), 'Red 50 Hz acoplada al cuerpo; CGE = tierra del circuito <-> tierra (20p bateria, 1 = USB a PC)', 2)
    s.two('voltage', 'VM', (752, -64), (752, 16), 'SINE(0 {VMAINS_TRAN} 50) AC {VMAINS_AC}')
    s.label((752, -64), 'MAINS', dy=-16); s.label((752, 16), 'EARTH', dy=16)
    s.C('CMB', (944, -80), (944, -16), '3p'); s.label((944, -80), 'MAINS', dy=-16); s.label((944, -16), 'BODY', dy=16)
    s.C('CBE', (1104, -80), (1104, -16), '200p'); s.label((1104, -80), 'BODY', dy=-16); s.label((1104, -16), 'EARTH', dy=16)
    s.C('CGE', (1264, -80), (1264, -16), '{CGE}'); s.label((1264, -80), 'EARTH', dy=-16); s.gnd((1264, -16))
    s.R('RGE', (1424, -96), (1424, -16), '1G'); s.label((1424, -96), 'EARTH', dy=-16); s.gnd((1424, -16))
    # --- 4 canales ---
    hc = {1: ('5m', '-5m'), 2: ('12m', '0'), 3: ('-8m', '10m'), 4: ('3m', '-15m')}
    fk = {1: 'F1', 2: 'F2', 3: 'F3', 4: 'F4'}
    for k in range(1, 5):
        y = 400 + (k - 1) * 560
        s.text((0, y - 112), f'Canal {k}: estimulo diferencial (senoidal {fk[k]} + ruido) entre el cuerpo y el electrodo +; electrodo - con desbalance 51k||47n', 2)
        s.two('voltage', f'VL{k}', (32, y), (32, y + 80), f'PWL file=noise/lf_ch{k}.pwl')
        s.label((32, y), f'nl{k}', dy=-16); s.gnd((32, y + 80))
        s.two('voltage', f'VW{k}', (352, y), (352, y + 80), f'PWL file=noise/wh_ch{k}.pwl')
        s.label((352, y), f'nw{k}', dy=-16); s.gnd((352, y + 80))
        s.two('bv', f'BIN{k}', (672, y), (672, y + 80),
              f'V={{AS}}*sin(2*pi*{{{fk[k]}}}*time) + {{KN}}*({{NLF}}*V(nl{k})+{{NWH}}*V(nw{k}))')
        s.label((672, y + 80), 'BODY', dy=16)
        s.wire((672, y), (672, y - 32), (1312, y - 32), (1312, y))
        s.symbol('ELECTRODO', f'XE{k}P', (1312, y), 'R0', 'ELECTRODE', (('SpiceLine', f'Vhc={hc[k][0]}'),))
        s.label((1312, y + 96), f'EP{k}', dy=16)
        s.label((1552, y), 'BODY', dy=-16)
        s.symbol('ELECTRODO', f'XE{k}N', (1552, y), 'R0', 'ELECTRODE', (('SpiceLine', f'Vhc={hc[k][1]}'),))
        s.wire((1552, y + 96), (1552, y + 128), (1632, y + 128))
        s.R(f'RI{k}', (1632, y + 128), (1712, y + 128), '51k')
        s.wire((1632, y + 128), (1632, y + 192)); s.C(f'CI{k}', (1632, y + 192), (1696, y + 192), '47n')
        s.wire((1696, y + 192), (1712, y + 192), (1712, y + 128)); s.wire((1712, y + 128), (1760, y + 128))
        s.flag((1760, y + 128), f'EN{k}')
        # bloque CANAL en (2192, y+64): pines EP(-128,-48) EN(-128,48) VCC(-48,-96) VREF(48,-96) ADC(128,0) RGM(-48,96) INAOUT(48,96)
        cx, cy = 2192, y + 64
        s.symbol('CANAL', f'XCH{k}', (cx, cy), 'R0')
        s.label((cx - 128, cy - 48), f'EP{k}', dx=-64)
        s.label((cx - 128, cy + 48), f'EN{k}', dx=-64)
        s.label((cx - 48, cy - 96), 'VCC', dy=-32)
        s.label((cx + 48, cy - 96), 'VREF', dy=-32)
        s.label((cx + 128, cy), f'ADC{k}', dx=64)
        s.label((cx - 48, cy + 96), f'RGM{k}', dy=32)
        s.label((cx + 48, cy + 96), f'INA{k}', dy=32)
    # --- RLD ---
    bx, by = 2720, 400
    s.text((bx, by - 240), 'RLD: integrador inversor; sensado en el punto medio de RG de los 4 canales (604k c/u)', 2)
    s.text((bx, by - 208), 'RLDMODE 2 = RLD activo | 1 = sin RLD, referencia pasiva a VREF por 390k | 0 = sin RLD, referencia directa', 2)
    for k in range(1, 5):
        yy = by + (k - 1) * 64
        s.label((bx, yy), f'RGM{k}', dx=-32)
        s.R(f'RSM{k}', (bx, yy), (bx + 80, yy), '604k')
        s.wire((bx + 80, yy), (bx + 144, yy))
    s.wire((bx + 144, by), (bx + 144, by + 192))
    s.wire((bx + 144, by + 96), (bx + 208, by + 96))
    op = s.opamp('XRLD', (bx + 208, by + 128 + 32))
    s.supplies(op)
    s.wire((bx + 208, by + 96), (bx + 208, op['inn'][1]), op['inn'])
    s.label(op['inp'], 'VREF', dx=-48)
    s.wire((bx + 176, by + 96), (bx + 176, by - 16), (bx + 208, by - 16))
    s.C('CINT', (bx + 208, by - 16), (bx + 272, by - 16), '{CINT}')
    s.wire((bx + 176, by - 16), (bx + 176, by - 48), (bx + 208, by - 48))
    s.R('RPAR', (bx + 208, by - 48), (bx + 288, by - 48), '10Meg')
    s.wire((bx + 272, by - 16), (bx + 320, by - 16))
    s.wire((bx + 288, by - 48), (bx + 320, by - 48), (bx + 320, by - 16), (bx + 320, op['out'][1]))
    s.wire(op['out'], (bx + 320, op['out'][1]), (bx + 352, op['out'][1]))
    s.R('RLIM', (bx + 352, op['out'][1]), (bx + 432, op['out'][1]), '{if(RLDMODE==2,RLIM,1T)}')
    e = (bx + 432, op['out'][1])
    s.wire(e, (bx + 496, e[1]))
    s.R('RPAS', (bx + 464, e[1]), (bx + 464, e[1] + 80), '{if(RLDMODE==2,1T,if(RLDMODE==1,RLIM,1))}')
    s.label((bx + 464, e[1] + 80), 'VREF', dy=16)
    s.wire((bx + 496, e[1]), (bx + 528, e[1]), (bx + 528, e[1] - 96))
    s.symbol('ELECTRODO', 'XER', (bx + 528, e[1] - 192), 'R0', 'ELECTRODE', (('SpiceLine', 'Vhc=0'),))
    s.label((bx + 528, e[1] - 192), 'BODY', dy=-16)
    s.text((bx + 560, e[1] - 112), '9o electrodo (clavicula)', 1)
    # --- directivas ---
    d = (2720, 1100)
    s.text((d[0], d[1] - 48), 'Modelos y prueba (T7). Para RLD con/sin: .step param RLDMODE list 1 2 ; bateria vs USB: CGE', 2)
    s.text(d, """.include opa.lib
.include models/ina_behav.lib
.include afe_channel.lib
.param CASE=1
.param RATIO={if(CASE==2,100,10)} KN={if(CASE==0,0,1)}
.param NLF=1m NWH=300u NTOT={sqrt(NLF**2+NWH**2)} AS={NTOT*sqrt(2)/RATIO}
.param F1=73 F2=131 F3=211 F4=307
.param RLDMODE=2 CINT=1n RLIM=390k RS=100k CCM=47p CD=100p
.param CGE=1 VMAINS_TRAN={if(CASE==0,0,311)} VMAINS_AC=0
.tran 0 1.25 0 50u
.options gmin=100f plotwinsize=0""", 2, directive=True)
    s.save('AFE_4CH.asc')


if __name__ == '__main__':
    symbols(); canal(); top()
    print('ok')
