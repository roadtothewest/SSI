"""Genera los esquematicos LTspice del AFE (jerarquicos):
  CANAL.asc + CANAL.asy   un canal (bloque), mismos componentes y nombres que AFE_CH
  AFE_4CH.asc             4 canales, 9 electrodos, RLD, VREF, cuerpo y red, estimulos
  INA333.asy, ELECTRODO.asy  simbolos propios
La conectividad se verifica con tools/check_asc.py (netlist de LTspice vs afe_channel.lib).
"""
import os, sys

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
    def D(self, n, a, k, v='1N4148'): self.two('diode', n, a, k, v)

    def opamp(self, name, inp, value='TS922'):
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
    s.text((-96, -480), 'CANAL sEMG:  EP/EN  ->  1 ESD  ->  2 RFI  ->  3 INA333 x20  ->  4 HPF 20 Hz  ->  5 LPF MFB x25  ->  6 LPF SK  ->  7 bucket  ->  ADC', 3)
    s.text((-96, -416), 'Ganancia total 503 (54 dB), banda 20-500 Hz. Este bloque se usa 3 veces en AuraVox_AFE.asc (XCH1..XCH3). Nombres = subcircuito AFE_CH de afe_channel.lib', 2)
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
        s.R(f'Rf{side}', (448, y), (528, y), '{RRFI}')
        s.wire((528, y), (592, y), (656, y), (720, y), (944, y))
    s.C('Ccmp', (592, P), (592, 64), '{CCM}'); s.gnd((592, 64))
    s.wire((656, P), (656, 160)); s.C('Cdif', (656, 160), (656, 224), '{CD}'); s.wire((656, 224), (656, N))
    s.C('Ccmn', (720, N), (720, N + 64), '{CCM}'); s.gnd((720, N + 64))
    # ---- 3 INA333
    s.box(800, -336, 1296, 512, '3  INA333, G1 = 20.16', 'G1 = 1+100k/RG, RG = 2 x 2.61k\npunto medio RGM -> RLD')
    s.symbol('INA333', 'XINA', (1040, 192), 'R0', 'INA333')
    s.wire((944, 96), (880, 96)); s.R('RGa', (880, 96), (880, 176), '{RGH}')
    s.wire((880, 176), (880, 192), (880, 208)); s.R('RGb', (880, 208), (880, 288), '{RGH}'); s.wire((880, 288), (944, 288))
    s.label((880, 192), 'RGM', dx=-48, iopin='Out')
    s.label((1040, -48), 'VCC', dy=-16); s.gnd((1040, 432)); s.label((1104, 432), 'VREF', dy=16)
    s.wire((1200, 192), (1264, 192), (1312, 192)); s.flag((1264, 192), 'INAOUT')
    # ---- 4 HPF
    s.box(1296, -336, 1952, 512, '4  HPF 20 Hz  (Sallen-Key 2o orden)', 'ganancia 1, Q 0.707')
    s.C('Chp1', (1312, 192), (1376, 192), '{CHP}')
    s.wire((1376, 192), (1440, 192), (1536, 192))
    s.R('R1', (1440, 192), (1440, 112), '{RHP1}')
    s.C('Chp2', (1536, 192), (1600, 192), '{CHP}')
    s.wire((1600, 192), (1664, 192), (1728, 192))
    s.R('Ra', (1664, 192), (1664, 272), '{RHP2}'); s.label((1664, 272), 'VREF', dy=16)
    op = s.opamp('XHP', (1728, 192)); s.supplies(op)
    s.wire((1440, 112), (1440, 32), (1824, 32), (1824, op['out'][1]))
    s.wire(op['inn'], (1712, op['inn'][1]), (1712, 32))
    s.wire(op['out'], (1824, op['out'][1]), (1888, op['out'][1]))
    s.flag((1888, op['out'][1]), 'HPO')
    # salto de fila: HPO baja a la fila 2
    Y2 = 1056
    s.wire((1888, op['out'][1]), (2016, op['out'][1]), (2016, 624), (-160, 624), (-160, Y2), (128, Y2))
    # ---- 5 LPF MFB con ganancia
    s.box(-96, 688, 736, 1232, '5  LPF MFB 500 Hz, ganancia -25 (Q 0.54)', 'Butterworth 4o orden, seccion 1; invierte (no importa)')
    s.R('Rm1', (128, Y2), (208, Y2), '{RM1}')
    s.wire((208, Y2), (272, Y2), (352, Y2))
    s.C('Cm1', (272, Y2), (272, Y2 + 64), '{CM1}'); s.gnd((272, Y2 + 64))
    s.R('Rm2', (272, Y2), (272, Y2 - 80), '{RM2}'); s.wire((272, Y2 - 80), (272, Y2 - 176), (672, Y2 - 176))
    s.R('Rm3', (352, Y2), (432, Y2), '{RM3}')
    s.wire((432, Y2), (496, Y2), (576, Y2))
    s.C('Cm2', (496, Y2), (496, Y2 - 64), '{CM2}'); s.wire((496, Y2 - 64), (496, Y2 - 112), (672, Y2 - 112))
    op = s.opamp('XMF', (576, Y2 + 32)); s.supplies(op)
    s.label(op['inp'], 'VREF', dx=-48)
    s.wire((672, Y2 - 176), (672, Y2 - 112), (672, op['out'][1]))
    s.wire(op['out'], (672, op['out'][1]), (736, op['out'][1]), (800, op['out'][1])); s.flag((736, op['out'][1]), 'MFO')
    y = op['out'][1]

    # ---- 6 LPF Sallen-Key (ganancia 1)
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
    y = lpf(800, y, ('Rlb1', 'Rlb2', 'C21', 'C22', 'XLB'), ('{RLB}', '{RLB}', '{C21}', '{C22}'), 'LBO',
            (736, 688, 1568, 1232, '6  LPF Sallen-Key 500 Hz (Q 1.31)', 'Butterworth 4o orden, seccion 2'))
    # ---- 7 bucket
    s.box(1568, 688, 2112, 1232, '7  BUCKET -> ADC', '100 ohm + 1 nF (sin buffer)')
    s.R('Rbk', (1600, y), (1680, y), '{RBK}')
    s.wire((1680, y), (1776, y), (1904, y))
    s.C('Cbk', (1776, y), (1776, y + 64), '{CBK}'); s.gnd((1776, y + 64))
    s.flag((1904, y), 'ADC', 'Out')
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
    ldo_asy = """Version 4
SymbolType CELL
RECTANGLE Normal -64 -48 64 48
TEXT 0 -24 Center 2 TLV75733P
TEXT -56 -8 Left 1 IN
TEXT -56 24 Left 1 EN
TEXT 56 -8 Right 1 OUT
TEXT 0 32 Center 1 GND
WINDOW 0 -64 -64 Left 2
SYMATTR Prefix X
SYMATTR Value TLV75733P
SYMATTR Description LDO 3.3 V 1 A, SOT-23-5 (TI). Modelo conductual: models/tlv757_behav.lib
PIN -64 -16 NONE 0
PINATTR PinName IN
PINATTR SpiceOrder 1
PIN 0 48 NONE 0
PINATTR PinName GND
PINATTR SpiceOrder 2
PIN -64 16 NONE 0
PINATTR PinName EN
PINATTR SpiceOrder 3
PIN 64 -16 NONE 0
PINATTR PinName OUT
PINATTR SpiceOrder 4
"""
    for fn, t in (('CANAL.asy', canal_asy), ('INA333.asy', ina_asy), ('ELECTRODO.asy', elec_asy), ('TLV75733P.asy', ldo_asy)):
        open(os.path.join(HERE, fn), 'w', newline='\r\n').write(t)


# ---------------------------------------------------------------------------
VALORES = """.param RS=100k RRFI=1k CCM=47p CD=100p RGH=2.7k
.param CHP=100n RHP1=56k RHP2=110k
.param RM1=3k RM2=75k RM3=20k CM1=68n CM2=1n
.param RLB=56k C21=15n C22=2.2n
.param RBK=100 CBK=1n RSM=620k CINT=1n RLIM=390k"""

ESTIMULO = """.param KN=1 KSEM=25 NMOV=4.28m NWHT=82.4u
.param AS1=50u AS2=40u AS3=25u
.param GE1=120u GE2=50u GE3=250u
.param CMB=3p RIMB=51k RER=20k CGE=1 VMAINS_TRAN=311 VMAINS_AC=0
.param GDK={1.8/3.3}"""

SIM = """.include opa.lib
.include models/ina_behav.lib
.include afe_channel.lib
.include models/tlv757_behav.lib
.step param RLDMODE list 1 2
.param RLIM_EF={if(RLDMODE==2,RLIM,1T)} RPAS_EF={if(RLDMODE==2,1T,if(RLDMODE==1,RLIM,1))}
.tran 0 1.2 0 50u
.options gmin=100f plotwinsize=0 gminsteps=0 srcsteps=0
.meas tran CM_cuerpo_Vpp PP V(body)-V(vref) FROM 0.3 TO 1.2"""
for _k in range(1, 4):
    SIM += f"""
.meas tran sEMG{_k}_uVrms RMS 1e6*V(semg{_k}) FROM 0.35 TO 0.49
.meas tran ADC{_k}_rafaga_mVrms RMS 1000*(V(adc{_k})-1.65) FROM 0.35 TO 0.49
.meas tran ADC{_k}_reposo_mVrms RMS 1000*(V(adc{_k})-1.65) FROM 0.58 TO 0.70
.meas tran SNR{_k}_salida_dB param 20*log10(ADC{_k}_rafaga_mVrms/ADC{_k}_reposo_mVrms)
.meas tran PIN{_k}_min_V MIN V(pin{_k}) FROM 0.3 TO 1.2
.meas tran PIN{_k}_max_V MAX V(pin{_k}) FROM 0.3 TO 1.2"""

DKPIN = {1: 'A1 = PA9 (ADC12_INP10)', 2: 'A2 = PA10 (ADC12_INP11)', 3: 'A3 = PA12 (ADC12_INP13)'}
MUSC = {1: 'submentoniano', 2: 'labio inferior', 3: 'laringe'}


def top():
    from make_bom_xlsx import compact_rows
    s = Sheet(4400, 3800)
    s.text((-1600, -1072), 'AuraVox - AFE sEMG: 3 entradas diferenciales (7 electrodos) -> 3 salidas al ADC del STM32N6570-DK', 4)
    s.text((-1600, -992), 'Un Run = 2 pasos: paso 1 SIN RLD (referencia pasiva 390k), paso 2 CON RLD. Resultados: View > SPICE Error Log. Doble clic en un bloque CANAL para ver sus 8 etapas.', 3)
    s.text((-1600, -928), 'QUE GRAFICAR: V(semg1) (sEMG limpio) | V(n1)-V(body) (entrada con ruido) | V(adc1)..V(adc3) (salidas del AFE) | V(pin1)..V(pin3) (lo que ve el ADC, 0-1.8 V) | V(body)-V(vref) (modo comun)', 2)
    # --- alimentacion y VREF ---
    s.box(-2560, -864, -800, -256, 'ALIMENTACION: 5 V USB/powerbank -> TLV75733P -> 3.3 V, Y VREF', '5 V desde el pin +5V del STM32N6570-DK; divisor 2 x 100k + 10u y seguidor TS922')
    s.two('voltage', 'VUSB', (-2464, -560), (-2464, -480), '5'); s.label((-2464, -560), 'V5', dy=-16); s.gnd((-2464, -480))
    s.symbol('TLV75733P', 'XLDO', (-2176, -528), 'R0', 'TLV75733P')
    s.wire((-2240, -544), (-2304, -544), (-2336, -544)); s.flag((-2336, -544), 'V5')
    s.wire((-2240, -512), (-2272, -512), (-2272, -544))
    s.C('CLDOI', (-2304, -544), (-2304, -480), '1u'); s.gnd((-2304, -480))
    s.gnd((-2176, -480))
    s.wire((-2112, -544), (-2048, -544), (-1968, -544), (-1904, -544)); s.flag((-1904, -544), 'VCC')
    s.C('CLDOO', (-2048, -544), (-2048, -480), '1u'); s.gnd((-2048, -480))
    s.C('CBULK', (-1968, -544), (-1968, -480), '10u'); s.gnd((-1968, -480))
    s.R('RA1', (-1296, -592), (-1296, -512), '100k'); s.label((-1296, -592), 'VCC', dy=-16)
    s.wire((-1296, -512), (-1296, -496), (-1296, -480)); s.R('RA2', (-1296, -480), (-1296, -400), '100k'); s.gnd((-1296, -400))
    s.wire((-1296, -496), (-1216, -496), (-1088, -496)); s.C('CA', (-1216, -496), (-1216, -432), '10u'); s.gnd((-1216, -432))
    op = s.opamp('XVR', (-1088, -496)); s.supplies(op)
    o = follower_feedback(s, op, -624)
    s.label(o, 'VREF', dx=64)
    # --- generadores comunes ---
    s.box(-736, -864, 112, -256, 'GENERADORES COMUNES', 'envolvente de habla (rafagas) y ECG')
    s.two('voltage', 'VENV', (-640, -560), (-640, -480), 'PULSE(0.05 1 0.3 30m 30m 170m 420m)')
    s.label((-640, -560), 'env', dy=-16); s.gnd((-640, -480))
    s.symbol('voltage', 'VECG', (-256, -576), 'R0', windows=('0 24 16 Left 2', '3 -400 136 Left 0'), value='PWL REPEAT FOREVER (0 0 0.08 0 0.12 0.12 0.16 0 0.20 -0.12 0.22 1 0.24 -0.25 0.27 0 0.42 0 0.50 0.3 0.58 0 0.833 0) ENDREPEAT')
    s.label((-256, -560), 'ecg', dy=-16); s.gnd((-256, -480))
    # --- cuerpo y red ---
    s.box(176, -864, 1472, -256, 'CUERPO Y RED 50 Hz', 'CMB red-cuerpo, CBE cuerpo-tierra, CGE circuito-tierra (1 = USB a PC, peor caso)')
    s.two('voltage', 'VM', (272, -560), (272, -480), 'SINE(0 {VMAINS_TRAN} 50) AC {VMAINS_AC}')
    s.label((272, -560), 'MAINS', dy=-16); s.label((272, -480), 'EARTH', dy=16)
    s.C('CMB', (704, -576), (704, -512), '{CMB}'); s.label((704, -576), 'MAINS', dy=-16); s.label((704, -512), 'BODY', dy=16)
    s.C('CBE', (928, -576), (928, -512), '200p'); s.label((928, -576), 'BODY', dy=-16); s.label((928, -512), 'EARTH', dy=16)
    s.C('CGE', (1120, -576), (1120, -512), '{CGE}'); s.label((1120, -576), 'EARTH', dy=-16); s.gnd((1120, -512))
    s.R('RGE', (1328, -592), (1328, -512), '1G'); s.label((1328, -592), 'EARTH', dy=-16); s.gnd((1328, -512))
    # --- columnas ---
    s.box(-1600, -192, -224, 2464, 'ENTRADA DIFERENCIAL POR CANAL', 'sEMG = ruido blanco filtrado 90 Hz x envolvente; ruido = movimiento + ECG + blanco')
    s.box(-160, -192, 704, 2464, 'ELECTRODOS (6 de senal)', '20k||47n; el - de cada par + 51k||47n')
    s.box(768, -192, 1472, 2464, 'AFE: 3 CANALES', 'bloque CANAL = 7 etapas')
    s.box(1536, -192, 2400, 2464, 'STM32N6570-DK: ARDUINO A1..A3', 'amplificador de la placa 3.3 V -> 1.8 V + muestreo del ADC')
    hc = {1: ('5m', '-5m'), 2: ('12m', '0'), 3: ('-8m', '10m')}
    for k in range(1, 4):
        y = 64 + (k - 1) * 608
        s.text((-1568, y - 64), f'CH{k}  {MUSC[k]}', 3)
        # sEMG: blanco -> pasabanda -> x envolvente
        s.two('bv', f'BW{k}', (-1504, y + 48), (-1504, y + 128), f'V=white(2e4*time+{k}e5)')
        s.label((-1504, y + 48), f'w{k}', dy=-16); s.gnd((-1504, y + 128))
        s.symbol('e', f'EF{k}', (-1216, y + 32), 'R0', 'Laplace=(s/(2*pi*63))/((s/(2*pi*90))**2+s/(2*pi*63)+1)')
        s.label((-1264, y + 64), f'w{k}', dx=-32); s.wire((-1264, y + 112), (-1264, y + 144)); s.flag((-1264, y + 144), '0')
        s.label((-1216, y + 48), f'f{k}', dy=-16); s.gnd((-1216, y + 128))
        s.two('bv', f'BSEM{k}', (-1504, y + 288), (-1504, y + 368), f'V={{AS{k}}}*{{KSEM}}*V(f{k})*V(env)')
        s.label((-1504, y + 288), f'semg{k}', dy=-16); s.gnd((-1504, y + 368))
        expr = f'V=V(semg{k})+{{KN}}*({{NMOV}}*white(3*time+{k*7}e3)+{{NWHT}}*white(2e4*time+{k*3}e5)+{{GE{k}}}*V(ecg))'
        s.symbol('bv', f'BIN{k}', (-512, y + 32), 'R0', expr, windows=('0 24 16 Left 2', '3 -40 136 Left 0'))
        s.label((-512, y + 128), 'BODY', dy=16)
        s.wire((-512, y + 48), (-512, y), (256, y), (256, y + 32))
        s.flag((-512, y), f'n{k}')
        s.symbol('ELECTRODO', f'XE{k}P', (256, y + 32), 'R0', 'ELECTRODE', (('SpiceLine', f'Vhc={hc[k][0]}'),))
        s.wire((256, y + 128), (256, y + 192), (576, y + 192), (832, y + 192))
        s.label((0, y + 96), 'BODY', dx=-64)
        s.symbol('ELECTRODO', f'XE{k}N', (0, y + 96), 'R0', 'ELECTRODE', (('SpiceLine', f'Vhc={hc[k][1]}'),))
        s.wire((0, y + 192), (0, y + 320), (384, y + 320))
        s.R(f'RI{k}', (384, y + 320), (464, y + 320), '{RIMB}')
        s.wire((384, y + 320), (384, y + 416)); s.C(f'CI{k}', (384, y + 416), (448, y + 416), '47n')
        s.wire((448, y + 416), (464, y + 416), (464, y + 320)); s.wire((464, y + 320), (576, y + 320), (832, y + 320))
        s.flag((576, y + 192), f'EP{k}'); s.flag((576, y + 320), f'EN{k}')
        cx, cy = 1024, y + 256
        s.symbol('CANAL', f'XCH{k}', (cx, cy), 'R0')
        s.label((cx - 64, cy - 160), 'VCC', dy=-32)
        s.label((cx + 64, cy - 160), 'VREF', dy=-32)
        s.label((cx - 64, cy + 160), f'RGM{k}', dy=32)
        # salida -> STM32N6570-DK
        s.wire((cx + 192, cy), (cx + 320, cy), (1600, cy), (1648, cy), (1712, cy)); s.flag((cx + 320, cy), f'adc{k}')
        s.R(f'RDKIN{k}', (1648, cy), (1648, cy + 80), '1Meg'); s.gnd((1648, cy + 80))
        s.symbol('e', f'EDK{k}', (1760, cy - 32), 'R0', '{GDK}')
        s.wire((1712, cy + 48), (1712, cy + 80)); s.flag((1712, cy + 80), '0'); s.gnd((1760, cy + 64))
        s.wire((1760, cy - 16), (1824, cy - 16)); s.R(f'RDK{k}', (1824, cy - 16), (1904, cy - 16), '1k')
        s.wire((1904, cy - 16), (1968, cy - 16), (2064, cy - 16)); s.C(f'CSH{k}', (1968, cy - 16), (1968, cy + 48), '5p'); s.gnd((1968, cy + 48))
        s.flag((2064, cy - 16), f'pin{k}')
        s.text((1568, cy - 128), f'CH{k} -> {DKPIN[k]}', 2)
    # --- RLD ---
    bx0 = 2464
    s.box(bx0, -192, bx0 + 1312, 928, 'RLD (9o electrodo, clavicula)', 'integrador inversor; sensa el punto medio de RG de los 4 canales')
    s.text((bx0 + 32, 48), 'RLDMODE 2 = con RLD (RLIM 390k) | 1 = sin RLD: ref. pasiva a VREF por 390k (RPAS)', 2)
    bx, by = bx0 + 160, 400
    for k in range(1, 4):
        yy = by + (k - 1) * 96
        s.label((bx, yy), f'RGM{k}', dx=-64)
        s.R(f'RSM{k}', (bx, yy), (bx + 80, yy), '{RSM}')
        s.wire((bx + 80, yy), (bx + 176, yy))
    s.wire((bx + 176, by), (bx + 176, by + 288))
    op = s.opamp('XRLD', (bx + 352, by + 176)); s.supplies(op)
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
    # --- valores, estimulo, simulacion, BoM ---
    s.box(bx0, 992, bx0 + 1312, 1504, 'VALORES (editar aqui si cambias un componente)', 'E24; el bloque CANAL los usa en sus 3 copias')
    s.text((bx0 + 32, 1184), VALORES, 2, directive=True)
    s.box(bx0, 1568, bx0 + 1312, 3040, 'ESTIMULO Y SIMULACION', 'KN=0 quita el ruido. AS = sEMG (V rms); GE = ECG pico; NMOV/NWHT calibrados a 500/20 uV rms')
    s.text((bx0 + 32, 1760), ESTIMULO + '\n' + SIM, 2, directive=True)
    s.box(-1600, 3104, 3776, 3680, 'BoM (3 canales, a comprar; detalle en docs/afe-emg/BoM_AFE_AuraVox.xlsx)', '')
    rows = compact_rows()
    cols = [rows[i::4] for i in range(4)]
    for c, rr in enumerate(cols):
        s.text((-1568 + c * 1344, 3216), '\n'.join(f'{q:>3} x {v}  {t}' for v, q, t in rr), 2)
    s.save('AuraVox_AFE.asc')


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(__file__))
    symbols(); canal(); top()
    print('ok')
