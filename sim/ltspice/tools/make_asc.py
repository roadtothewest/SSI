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

    def box(self, x1, y1, x2, y2, title, detail=''):
        """Recuadro punteado de una etapa, con titulo grande y detalle."""
        self.texts.append(f'RECTANGLE Normal {x1} {y1} {x2} {y2} 2')
        self.text((x1 + 24, y1 + 40), title, 3)
        if detail:
            self.text((x1 + 24, y1 + 88), detail, 2)

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
    """Un canal, 8 etapas en recuadros numerados, en dos filas, con la senal cableada."""
    s = Sheet(3000, 1300)
    s.text((-96, -480), 'CANAL sEMG:  EP/EN  ->  1 ESD  ->  2 RFI  ->  3 INA333  ->  4 HPF  ->  5 G2  ->  6 LPF A  ->  7 LPF B  ->  8 buffer  ->  ADC', 3)
    s.text((-96, -416), 'Ganancia total 503 (54 dB), banda 20-500 Hz. Este bloque se usa 4 veces en AFE_4CH.asc (XCH1..XCH4). Nombres = subcircuito AFE_CH de afe_channel.lib', 2)
    s.flag((-352, -224), 'VCC', 'In'); s.flag((-352, -160), 'VREF', 'In')
    s.text((-384, -288), 'Alimentacion', 2)
    P, N = 0, 384                      # lineas + y - de la entrada
    # ---- 1 ESD
    s.box(-96, -336, 384, 512, '1  PROTECCION ESD', 'Rs {RS} + 1N4148 a VCC y GND')
    for side, y in (('p', P), ('n', N)):
        s.label((32, y), 'E' + side.upper(), dx=-64, iopin='In')
        s.R(f'Rs{side}', (32, y), (112, y), '{RS}')
        s.wire((112, y), (208, y), (448, y))
    s.D('Dp1', (208, -32), (208, -96)); s.wire((208, P), (208, -32)); s.label((208, -96), 'VCC', dy=-16)
    s.D('Dp2', (208, 128), (208, 64)); s.wire((208, P), (208, 64)); s.gnd((208, 128))
    s.D('Dn1', (208, 416), (208, 480)); s.wire((208, N), (208, 416)); s.label((208, 480), 'VCC', dy=16)
    s.D('Dn2', (208, 256), (208, 320)); s.wire((208, 320), (208, N)); s.label((208, 256), '0', dy=-16)
    # ---- 2 RFI
    s.box(384, -336, 800, 512, '2  FILTRO RFI', 'Rf 1k, Ccm {CCM}, Cd {CD}')
    for side, y in (('p', P), ('n', N)):
        s.R(f'Rf{side}', (448, y), (528, y), '1k')
        s.wire((528, y), (592, y), (656, y), (720, y), (944, y))
    s.C('Ccmp', (592, P), (592, 64), '{CCM}'); s.gnd((592, 64))
    s.wire((656, P), (656, 160)); s.C('Cdif', (656, 160), (656, 224), '{CD}'); s.wire((656, 224), (656, N))
    s.C('Ccmn', (720, N), (720, N + 64), '{CCM}'); s.gnd((720, N + 64))
    # ---- 3 INA333
    s.box(800, -336, 1296, 512, '3  INA333, G1 = 20.16', 'G1 = 1+100k/RG, RG = 2 x 2.61k\npunto medio RGM -> RLD')
    s.symbol('INA333', 'XINA', (1040, 192), 'R0', 'INA333')
    s.wire((944, 96), (880, 96)); s.R('RGa', (880, 96), (880, 176), '2.61k')
    s.wire((880, 176), (880, 192), (880, 208)); s.R('RGb', (880, 208), (880, 288), '2.61k'); s.wire((880, 288), (944, 288))
    s.label((880, 192), 'RGM', dx=-48, iopin='Out')
    s.label((1040, -48), 'VCC', dy=-16); s.gnd((1040, 432)); s.label((1104, 432), 'VREF', dy=16)
    s.wire((1200, 192), (1264, 192), (1312, 192)); s.flag((1264, 192), 'INAOUT', 'Out')
    # ---- 4 HPF
    s.box(1296, -336, 1952, 512, '4  HPF 20 Hz  (Sallen-Key 2o orden)', 'ganancia 1, Q 0.707')
    s.C('Chp1', (1312, 192), (1376, 192), '100n')
    s.wire((1376, 192), (1440, 192), (1536, 192))
    s.R('R1', (1440, 192), (1440, 112), '56.2k')
    s.C('Chp2', (1536, 192), (1600, 192), '100n')
    s.wire((1600, 192), (1664, 192), (1728, 192))
    s.R('Ra', (1664, 192), (1664, 272), '113k'); s.label((1664, 272), 'VREF', dy=16)
    op = s.opamp('XHP', (1728, 192)); s.supplies(op)
    s.wire((1440, 112), (1440, 32), (1824, 32), (1824, op['out'][1]))
    s.wire(op['inn'], (1712, op['inn'][1]), (1712, 32))
    s.wire(op['out'], (1824, op['out'][1]), (1888, op['out'][1]))
    s.flag((1888, op['out'][1]), 'HPO')
    # salto de fila: HPO baja a la fila 2
    Y2 = 1056
    s.wire((1888, op['out'][1]), (2016, op['out'][1]), (2016, 624), (-160, 624), (-160, Y2), (256, Y2))
    # ---- 5 G2
    s.box(-96, 688, 576, 1232, '5  G2 = 1 + Rf/Rg = 25', 'Cg: ganancia 1 en DC')
    op = s.opamp('XG2', (256, Y2)); s.supplies(op)
    s.wire(op['inn'], (224, op['inn'][1]), (224, Y2 - 112), (224, Y2 - 176))
    s.R('Rf', (224, Y2 - 176), (304, Y2 - 176), '240k')
    s.wire((304, Y2 - 176), (368, Y2 - 176), (368, op['out'][1]))
    s.R('Rg', (224, Y2 - 112), (144, Y2 - 112), '10k')
    s.C('Cg', (144, Y2 - 112), (80, Y2 - 112), '10u'); s.label((80, Y2 - 112), 'VREF', dx=-48)
    s.wire(op['out'], (368, op['out'][1]), (496, op['out'][1]), (640, op['out'][1])); s.flag((496, op['out'][1]), 'G2O')
    y = op['out'][1]

    # ---- 6 y 7 LPF Sallen-Key (ganancia 1)
    def lpf(bx, y0, names, vals, vout, box):
        r1, r2, cfb, cg, x = names
        s.box(*box)
        s.R(r1, (bx, y0), (bx + 80, y0), vals[0])
        s.wire((bx + 80, y0), (bx + 176, y0), (bx + 272, y0))
        s.C(cfb, (bx + 176, y0), (bx + 176, y0 - 64), vals[2])
        s.R(r2, (bx + 272, y0), (bx + 352, y0), vals[1])
        s.wire((bx + 352, y0), (bx + 448, y0), (bx + 544, y0))
        s.C(cg, (bx + 448, y0), (bx + 448, y0 + 64), vals[3]); s.gnd((bx + 448, y0 + 64))
        op = s.opamp(x, (bx + 544, y0)); s.supplies(op)
        top = y0 - 128
        s.wire((bx + 176, y0 - 64), (bx + 176, top), (bx + 640, top), (bx + 640, op['out'][1]))
        s.wire(op['inn'], (bx + 528, op['inn'][1]), (bx + 528, top))
        s.wire(op['out'], (bx + 640, op['out'][1]), (bx + 704, op['out'][1]), (bx + 800, op['out'][1]))
        s.flag((bx + 704, op['out'][1]), vout)
        return op['out'][1]
    y = lpf(640, y, ('Rla1', 'Rla2', 'C11', 'C12', 'XLA'), ('88.7k', '88.7k', '3.9n', '3.3n'), 'LAO',
            (576, 688, 1408, 1232, '6  LPF A 500 Hz  (Q 0.541)', 'Butterworth 4o orden, seccion 1'))
    y = lpf(1440, y, ('Rlb1', 'Rlb2', 'C21', 'C22', 'XLB'), ('54.9k', '54.9k', '15n', '2.2n'), 'LBO',
            (1408, 688, 2208, 1232, '7  LPF B 500 Hz  (Q 1.306)', 'Butterworth 4o orden, seccion 2'))
    # ---- 8 buffer + bucket
    s.box(2208, 688, 2848, 1232, '8  BUFFER + BUCKET -> ADC', '100 ohm + 1 nF')
    s.wire((2240, y), (2304, y))
    op = s.opamp('XBF', (2304, y)); s.supplies(op)
    top = y - 128
    s.wire(op['inn'], (2288, op['inn'][1]), (2288, top), (2400, top), (2400, op['out'][1]))
    s.wire(op['out'], (2400, op['out'][1]), (2464, op['out'][1]))
    b = (2464, op['out'][1])
    s.R('Rbk', b, (b[0] + 80, b[1]), '100')
    e = (b[0] + 80, b[1])
    s.wire(e, (e[0] + 96, e[1]), (e[0] + 224, e[1]))
    s.C('Cbk', (e[0] + 96, e[1]), (e[0] + 96, e[1] + 64), '1n'); s.gnd((e[0] + 96, e[1] + 64))
    s.flag((e[0] + 224, e[1]), 'ADC', 'Out')
    s.save('CANAL.asc')


def symbols():
    canal_asy = """Version 4
SymbolType BLOCK
RECTANGLE Normal -192 -160 192 160
TEXT 0 -112 Center 2 CANAL sEMG
TEXT 0 -40 Center 1 1 ESD  2 RFI  3 INA333 x20
TEXT 0 -8 Center 1 4 HPF 20 Hz  5 G2 x25
TEXT 0 24 Center 1 6-7 LPF 500 Hz  8 buffer
TEXT 0 104 Center 1 ganancia 503, 20-500 Hz
PIN -192 -64 LEFT 8
PINATTR PinName EP
PINATTR SpiceOrder 1
PIN -192 64 LEFT 8
PINATTR PinName EN
PINATTR SpiceOrder 2
PIN -64 -160 TOP 8
PINATTR PinName VCC
PINATTR SpiceOrder 3
PIN 64 -160 TOP 8
PINATTR PinName VREF
PINATTR SpiceOrder 4
PIN 192 0 RIGHT 8
PINATTR PinName ADC
PINATTR SpiceOrder 5
PIN -64 160 BOTTOM 8
PINATTR PinName RGM
PINATTR SpiceOrder 6
PIN 64 160 BOTTOM 8
PINATTR PinName INAOUT
PINATTR SpiceOrder 7
"""
    ina_asy = """Version 4
SymbolType CELL
LINE Normal -96 -240 -96 240
LINE Normal -96 -240 160 0
LINE Normal -96 240 160 0
LINE Normal 0 -150 0 -240
LINE Normal 0 150 0 240
LINE Normal 64 90 64 240
TEXT -88 -192 Left 1 +IN
TEXT -88 192 Left 1 -IN
TEXT -88 -96 Left 1 RG+
TEXT -88 96 Left 1 RG-
TEXT 8 -136 Left 1 V+
TEXT 8 136 Left 1 V-
TEXT 72 80 Left 1 REF
TEXT -8 0 Center 2 INA333
WINDOW 0 24 -256 Left 2
WINDOW 3 104 256 Left 2
SYMATTR Prefix X
SYMATTR Value INA333
SYMATTR Description INA333 (TI). Modelo: models/INA333.LIB o models/ina_behav.lib
PIN -96 -192 NONE 0
PINATTR PinName IN+
PINATTR SpiceOrder 1
PIN -96 192 NONE 0
PINATTR PinName IN-
PINATTR SpiceOrder 2
PIN 0 -240 NONE 0
PINATTR PinName VCC
PINATTR SpiceOrder 3
PIN 0 240 NONE 0
PINATTR PinName VEE
PINATTR SpiceOrder 4
PIN 160 0 NONE 0
PINATTR PinName OUT
PINATTR SpiceOrder 5
PIN 64 240 NONE 0
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
MODES = {
    't7': dict(
        file='AFE_4CH.asc',
        title='Prueba general: senoidal (73/131/211/307 Hz) 10x menor que el ruido en los 4 canales, RLD activo, USB a PC',
        directives=""".include opa.lib
.include models/ina_behav.lib
.include afe_channel.lib
.param CASE=1
.param RATIO={if(CASE==2,100,10)} KN={if(CASE==0,0,1)}
.param NLF=1m NWH=300u NTOT={sqrt(NLF**2+NWH**2)} AS={NTOT*sqrt(2)/RATIO}
.param F1=73 F2=131 F3=211 F4=307
.func stim(f,a,b) {AS*sin(2*pi*f*time)+KN*(NLF*a+NWH*b)}
.param RLDMODE=2 CINT=1n RLIM=390k RS=100k CCM=47p CD=100p
.param CMB=3p RIMB=51k RER=20k
.param CGE=1 VMAINS_TRAN={if(CASE==0,0,311)} VMAINS_AC=0
.tran 0 0.5 0 50u
.param RLIM_EF={if(RLDMODE==2,RLIM,1T)} RPAS_EF={if(RLDMODE==2,1T,if(RLDMODE==1,RLIM,1))}
.options gmin=100f plotwinsize=0""",
        notes='Correr (Run) y graficar ADC1..ADC4. 0.5 s tarda ~3 min. CASE=2: senoidal 100x menor; CASE=0: sin ruido.'),
    'rld': dict(
        file='AUDIT_RLD.asc',
        title='Auditoria RLD: red de 311 Vpk por el cuerpo, sin senal, comparacion SIN RLD (paso 1) vs CON RLD (paso 2)',
        directives=""".include opa.lib
.include models/ina_behav.lib
.include afe_channel.lib
.step param RLDMODE list 1 2
.param CINT=1n RLIM=390k RS=100k CCM=47p CD=100p
.param CMB=3p RIMB=51k RER=20k
.param CGE=1 VMAINS_TRAN=311 VMAINS_AC=0
.tran 0 0.3 0 50u
.meas tran adc1_50Hz_Vpp PP V(adc1) FROM 0.2 TO 0.3
.meas tran adc2_50Hz_Vpp PP V(adc2) FROM 0.2 TO 0.3
.meas tran cuerpo_cm_Vpp PP V(body)-V(vref) FROM 0.2 TO 0.3
.meas tran rti1_uVpp param adc1_50Hz_Vpp/503*1e6
.param RLIM_EF={if(RLDMODE==2,RLIM,1T)} RPAS_EF={if(RLDMODE==2,1T,if(RLDMODE==1,RLIM,1))}
.options gmin=100f plotwinsize=0""",
        notes='Run, luego graficar ADC1..ADC4: el paso 1 (sin RLD, referencia pasiva 390k) muestra 50 Hz; el paso 2 (con RLD) casi nada. Resultados numericos: View > SPICE Error Log.'),
    'semg': dict(
        file='AUDIT_SEMG.asc',
        title='Auditoria sEMG: senal mioelectrica (CH1 submentoniano, CH2 platisma, CH3 labio, CH4 laringe) + ruido mayor (movimiento, ECG, red, blanco)',
        directives=""".include opa.lib
.include models/ina_behav.lib
.include afe_channel.lib
.param KN=1
.param RLDMODE=2 CINT=1n RLIM=390k RS=100k CCM=47p CD=100p
.param CMB=3p RIMB=51k RER=20k
.param CGE=1 VMAINS_TRAN=311 VMAINS_AC=0
.tran 0 2 0 50u
.param RLIM_EF={if(RLDMODE==2,RLIM,1T)} RPAS_EF={if(RLDMODE==2,1T,if(RLDMODE==1,RLIM,1))}
.options gmin=100f plotwinsize=0""",
        notes='Run (~12 min) y comparar V(sg1) (sEMG limpio) con V(adc1) y V(n1)-V(body) (entrada con ruido). KN=0 quita el ruido; RLDMODE=1 quita el RLD.'),
}


def top(mode='t7'):
    cfg = MODES[mode]
    s = Sheet(3600, 2800)
    s.text((-1280, -1008), 'AuraVox - AFE sEMG: 4 canales diferenciales, 9 electrodos (4 pares + RLD), 4 salidas ADC1..ADC4', 4)
    s.text((-1280, -928), cfg['title'], 3)
    s.text((-1280, -864), 'Flujo: ESTIMULO -> ELECTRODOS -> CANAL (x4) -> ADC.  Doble clic en un bloque CANAL (o clic derecho > Open Hierarchy) para ver sus 8 etapas.', 2)
    # --- alimentacion y VREF ---
    s.box(-1280, -800, -224, -256, 'ALIMENTACION 3.3 V Y VREF 1.65 V', 'divisor 2 x 100k + 10u, seguidor MCP6004')
    s.two('voltage', 'VCC', (-1184, -560), (-1184, -480), '3.3'); s.label((-1184, -560), 'VCC', dy=-16); s.gnd((-1184, -480))
    s.R('RA1', (-928, -592), (-928, -512), '100k'); s.label((-928, -592), 'VCC', dy=-16)
    s.wire((-928, -512), (-928, -496), (-928, -480)); s.R('RA2', (-928, -480), (-928, -400), '100k'); s.gnd((-928, -400))
    s.wire((-928, -496), (-848, -496), (-704, -496)); s.C('CA', (-848, -496), (-848, -432), '10u'); s.gnd((-848, -432))
    op = s.opamp('XVR', (-704, -496)); s.supplies(op)
    o = follower_feedback(s, op, -624)
    s.label(o, 'VREF', dx=64)
    # --- red y cuerpo ---
    s.box(-160, -800, 1408, -256, 'CUERPO Y RED 50 Hz', 'CMB red-cuerpo, CBE cuerpo-tierra, CGE circuito-tierra (20p bateria, 1 = USB a PC)')
    s.two('voltage', 'VM', (-64, -560), (-64, -480), 'SINE(0 {VMAINS_TRAN} 50) AC {VMAINS_AC}')
    s.label((-64, -560), 'MAINS', dy=-16); s.label((-64, -480), 'EARTH', dy=16)
    s.C('CMB', (416, -576), (416, -512), '{CMB}'); s.label((416, -576), 'MAINS', dy=-16); s.label((416, -512), 'BODY', dy=16)
    s.C('CBE', (640, -576), (640, -512), '200p'); s.label((640, -576), 'BODY', dy=-16); s.label((640, -512), 'EARTH', dy=16)
    s.C('CGE', (864, -576), (864, -512), '{CGE}'); s.label((864, -576), 'EARTH', dy=-16); s.gnd((864, -512))
    s.R('RGE', (1088, -592), (1088, -512), '1G'); s.label((1088, -592), 'EARTH', dy=-16); s.gnd((1088, -512))
    # --- recuadros de columnas ---
    s.box(-1280, -192, -224, 2464, 'ESTIMULO POR CANAL', 'diferencial, entre el cuerpo y el electrodo +')
    s.box(-160, -192, 704, 2464, 'ELECTRODOS (8 de senal)', '20k||47n; el - de cada par + 51k||47n')
    s.box(768, -192, 1472, 2464, 'AFE: 4 CANALES', 'bloque CANAL = 8 etapas')
    hc = {1: ('5m', '-5m'), 2: ('12m', '0'), 3: ('-8m', '10m'), 4: ('3m', '-15m')}
    musc = {1: 'submentoniano', 2: 'platisma', 3: 'labio inferior', 4: 'laringe'}
    for k in range(1, 5):
        y = 64 + (k - 1) * 608
        s.text((-1248, y - 64), f'CH{k}  {musc[k]}', 3)
        xb = -512
        if mode == 't7':
            s.two('voltage', f'VL{k}', (-1184, y + 48), (-1184, y + 128), f'PWL file=noise/lf_ch{k}.pwl')
            s.label((-1184, y + 48), f'nl{k}', dy=-16); s.gnd((-1184, y + 128))
            s.two('voltage', f'VW{k}', (-1184, y + 288), (-1184, y + 368), f'PWL file=noise/wh_ch{k}.pwl')
            s.label((-1184, y + 288), f'nw{k}', dy=-16); s.gnd((-1184, y + 368))
            expr = f'V=stim({{F{k}}},V(nl{k}),V(nw{k}))'
            s.two('bv', f'BIN{k}', (xb, y + 48), (xb, y + 128), expr)
        elif mode == 'semg':
            s.two('voltage', f'VSG{k}', (-1184, y + 48), (-1184, y + 128), f'PWL file=noise/semg_ch{k}.pwl')
            s.label((-1184, y + 48), f'sg{k}', dy=-16); s.gnd((-1184, y + 128))
            s.two('voltage', f'VNZ{k}', (-1184, y + 288), (-1184, y + 368), f'PWL file=noise/nz_ch{k}.pwl')
            s.label((-1184, y + 288), f'nz{k}', dy=-16); s.gnd((-1184, y + 368))
            s.two('bv', f'BIN{k}', (xb, y + 48), (xb, y + 128), f'V=V(sg{k}) + {{KN}}*V(nz{k})')
        else:
            s.two('voltage', f'VIN{k}', (xb, y + 48), (xb, y + 128), '0')
        s.label((xb, y + 128), 'BODY', dy=16)
        s.wire((xb, y + 48), (xb, y), (256, y), (256, y + 32))
        s.flag((xb, y), f'n{k}')
        # electrodos: + en x=256, - en x=0
        s.symbol('ELECTRODO', f'XE{k}P', (256, y + 32), 'R0', 'ELECTRODE', (('SpiceLine', f'Vhc={hc[k][0]}'),))
        s.wire((256, y + 128), (256, y + 192), (576, y + 192), (832, y + 192))
        s.label((0, y + 96), 'BODY', dx=-64)
        s.symbol('ELECTRODO', f'XE{k}N', (0, y + 96), 'R0', 'ELECTRODE', (('SpiceLine', f'Vhc={hc[k][1]}'),))
        s.wire((0, y + 192), (0, y + 320), (384, y + 320))
        s.R(f'RI{k}', (384, y + 320), (464, y + 320), '{RIMB}')
        s.wire((384, y + 320), (384, y + 416)); s.C(f'CI{k}', (384, y + 416), (448, y + 416), '47n')
        s.wire((448, y + 416), (464, y + 416), (464, y + 320)); s.wire((464, y + 320), (576, y + 320), (832, y + 320))
        s.flag((576, y + 192), f'EP{k}'); s.flag((576, y + 320), f'EN{k}')
        # bloque CANAL: pines EP(-192,-64) EN(-192,64) VCC(-64,-160) VREF(64,-160) ADC(192,0) RGM(-64,160) INAOUT(64,160)
        cx, cy = 1024, y + 256
        s.symbol('CANAL', f'XCH{k}', (cx, cy), 'R0')
        s.label((cx - 64, cy - 160), 'VCC', dy=-32)
        s.label((cx + 64, cy - 160), 'VREF', dy=-32)
        s.wire((cx + 192, cy), (cx + 320, cy)); s.flag((cx + 320, cy), f'ADC{k}')
        s.label((cx - 64, cy + 160), f'RGM{k}', dy=32)
        s.label((cx + 64, cy + 160), f'INA{k}', dy=32)
    # --- RLD ---
    s.box(1536, -192, 2848, 928, 'RLD (9o electrodo, clavicula)', 'integrador inversor; sensa el punto medio de RG de los 4 canales (604k c/u)')
    s.text((1568, 48), 'RLDMODE 2 = RLD activo (RLIM 390k) | 1 = sin RLD: ref. pasiva a VREF por 390k (RPAS) | 0 = ref. directa', 2)
    bx, by = 1696, 400
    for k in range(1, 5):
        yy = by + (k - 1) * 96
        s.label((bx, yy), f'RGM{k}', dx=-64)
        s.R(f'RSM{k}', (bx, yy), (bx + 80, yy), '604k')
        s.wire((bx + 80, yy), (bx + 176, yy))
    s.wire((bx + 176, by), (bx + 176, by + 288))
    op = s.opamp('XRLD', (bx + 352, by + 176))
    s.supplies(op)
    s.wire((bx + 176, by + 144), (bx + 240, by + 144), (bx + 320, by + 144), op['inn'])
    s.label(op['inp'], 'VREF', dx=-64)
    s.wire((bx + 240, by + 144), (bx + 240, by - 48), (bx + 320, by - 48))
    s.C('CINT', (bx + 320, by - 48), (bx + 384, by - 48), '{CINT}')
    s.wire((bx + 240, by - 48), (bx + 240, by - 176), (bx + 320, by - 176))
    s.R('RPAR', (bx + 320, by - 176), (bx + 400, by - 176), '10Meg')
    s.wire((bx + 384, by - 48), (bx + 480, by - 48))
    s.wire((bx + 400, by - 176), (bx + 480, by - 176), (bx + 480, by - 48), (bx + 480, op['out'][1]))
    s.wire(op['out'], (bx + 480, op['out'][1]), (bx + 576, op['out'][1]))
    s.R('RLIM', (bx + 576, op['out'][1]), (bx + 656, op['out'][1]), '{RLIM_EF}')
    e = (bx + 656, op['out'][1])
    s.wire(e, (bx + 800, e[1]), (bx + 960, e[1]))
    s.R('RPAS', (bx + 800, e[1]), (bx + 800, e[1] + 80), '{RPAS_EF}')
    s.label((bx + 800, e[1] + 80), 'VREF', dy=16)
    s.wire((bx + 960, e[1]), (bx + 960, e[1] - 96))
    s.symbol('ELECTRODO', 'XER', (bx + 960, e[1] - 192), 'R0', 'ELECTRODE', (('SpiceLine', 'Vhc=0 Re={RER}'),))
    s.label((bx + 960, e[1] - 192), 'BODY', dy=-16)
    s.flag((bx + 480, e[1]), 'RLDO')
    # --- directivas ---
    s.box(1536, 992, 2848, 2464, 'SIMULACION', cfg['notes'])
    s.text((1568, 1184), cfg['directives'], 2, directive=True)
    s.save(cfg['file'])


if __name__ == '__main__':
    symbols(); canal()
    for m in MODES:
        top(m)
    print('ok')
