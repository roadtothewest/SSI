"""BoM modular del AFE sEMG AuraVox -> docs/afe-emg/BoM_AFE_AuraVox.xlsx
Modulos en el mismo orden que los recuadros del esquematico LTspice (CANAL.asc y hoja superior).
Regenerar:  python3 tools/make_bom_xlsx.py"""
import os
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'docs', 'afe-emg', 'BoM_AFE_AuraVox.xlsx'))
F = 'Arial'
HDR = PatternFill('solid', fgColor='1F3A5F')
MOD = PatternFill('solid', fgColor='D9E2F3')
INP = PatternFill('solid', fgColor='FFFF00')
thin = Side(style='thin', color='BFBFBF')
BOX = Border(left=thin, right=thin, top=thin, bottom=thin)
CLP = '$#,##0;($#,##0);-'

# (modulo, canales, filas): fila = (refs, componente, valor_diseno, valor_comprar, tipo, cant_por_canal, repuesto, buscar, notas)
#   cant_por_canal = None -> fila informativa (seccion de op-amp contada en el modulo OP-AMPS)
OPS = 'seccion de op-amp'
MODULES = [
    ('1 PROTECCION ESD', 4, [
        ('Rsp, Rsn', 'Resistencia serie de entrada', '100k', '100k', 'pelicula metalica 1 % 1/4 W', 2, 2, 'resistencia 100k 1% 1/4W', 'Limita la corriente de falla hacia el paciente y hacia el INA'),
        ('Dp1, Dp2, Dn1, Dn2', 'Diodo de clamp a VCC y GND', '1N4148', '1N4148', 'diodo de senal', 4, 4, '1N4148', '4 por canal x 4 = 16 (+4 repuesto = 20). Protegen el INA de descargas'),
    ]),
    ('2 FILTRO RFI', 4, [
        ('Rfp, Rfn', 'Resistencia del filtro RFI', '1k', '1k', 'pelicula metalica 1 %', 2, 2, 'resistencia 1k 1%', ''),
        ('Ccmp, Ccmn', 'Condensador de modo comun', '47p', '47p', 'ceramico C0G/NP0 5 %', 2, 2, 'condensador ceramico 47pF NP0', 'Si la simulacion final elige 330k sin Ccm, no se usan'),
        ('Cdif', 'Condensador diferencial', '100p', '100p', 'ceramico C0G/NP0 5 %', 1, 1, 'condensador ceramico 100pF NP0', ''),
    ]),
    ('3 AMPLIFICADOR DE INSTRUMENTACION', 4, [
        ('XINA', 'INA (POR DEFINIR, ver hoja Requisitos IC)', 'INA333', 'INA333 / AD623 / AD8226 / INA826', 'DIP-8 o modulo con RG accesible', 1, 1, 'INA333 o AD623AN DIP-8', 'G1 = 1 + 100k/RG para INA333/AD623/AD8226/INA826'),
        ('RGa, RGb', 'Resistencia de ganancia (partida en dos)', '2.61k', '2.7k', 'pelicula metalica 1 %, parear con multimetro', 2, 4, 'resistencia 2.7k 1%', 'Con 2 x 2.7k: G1 = 19.5 (diseno 20.16). El punto medio va al RLD'),
        ('C desac. INA', 'Desacople del INA', '100n', '100n', 'ceramico X7R', 1, 1, 'condensador ceramico 100nF', 'Pegado al pin de alimentacion'),
    ]),
    ('4 HPF 20 Hz (Sallen-Key)', 4, [
        ('Chp1, Chp2', 'Condensador del HPF', '100n', '100n', 'poliester/MKT (film) 5 %', 2, 2, 'condensador poliester 100nF 5%', 'Film, no ceramico: estabilidad y bajo ruido'),
        ('R1', 'Resistencia de realimentacion', '56.2k', '56k', 'pelicula metalica 1 %', 1, 1, 'resistencia 56k 1%', 'Con 56k/110k: f0 = 20.3 Hz, Q = 0.70'),
        ('Ra', 'Resistencia a VREF', '113k', '110k', 'pelicula metalica 1 %', 1, 1, 'resistencia 110k 1%', ''),
        ('XHP', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 11 OP-AMPS'),
    ]),
    ('5 G2 = 25', 4, [
        ('Rf', 'Resistencia de realimentacion', '240k', '240k', 'pelicula metalica 1 %', 1, 1, 'resistencia 240k 1%', ''),
        ('Rg', 'Resistencia de ganancia', '10k', '10k', 'pelicula metalica 1 %', 1, 1, 'resistencia 10k 1%', ''),
        ('Cg', 'Condensador de bloqueo DC (G = 1 en DC)', '10u', '10u', 'ceramico X7R o electrolitico 16 V', 1, 1, 'condensador 10uF', ''),
        ('XG2', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 11 OP-AMPS'),
    ]),
    ('6 LPF A 500 Hz (Q 0.541)', 4, [
        ('Rla1, Rla2', 'Resistencia del LPF A', '88.7k', '91k', 'pelicula metalica 1 %', 2, 2, 'resistencia 91k 1%', 'Con 91k: f0 = 487 Hz'),
        ('C11', 'Condensador de realimentacion', '3.9n', '3.9n', 'poliester 5 % o C0G', 1, 1, 'condensador poliester 3.9nF', ''),
        ('C12', 'Condensador a GND', '3.3n', '3.3n', 'poliester 5 % o C0G', 1, 1, 'condensador poliester 3.3nF', ''),
        ('XLA', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 11 OP-AMPS'),
    ]),
    ('7 LPF B 500 Hz (Q 1.306)', 4, [
        ('Rlb1, Rlb2', 'Resistencia del LPF B', '54.9k', '56k', 'pelicula metalica 1 %', 2, 2, 'resistencia 56k 1%', 'Con 56k: f0 = 495 Hz'),
        ('C21', 'Condensador de realimentacion', '15n', '15n', 'poliester 5 % o C0G', 1, 1, 'condensador poliester 15nF', ''),
        ('C22', 'Condensador a GND', '2.2n', '2.2n', 'poliester 5 % o C0G', 1, 1, 'condensador poliester 2.2nF', ''),
        ('XLB', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 11 OP-AMPS'),
    ]),
    ('8 BUFFER + SALIDA AL ADC', 4, [
        ('Rbk', 'Resistencia del bucket', '100', '100', 'pelicula metalica 1 %', 1, 1, 'resistencia 100 ohm 1%', ''),
        ('Cbk', 'Condensador del bucket', '1n', '1n', 'ceramico C0G/NP0', 1, 1, 'condensador ceramico 1nF NP0', ''),
        ('ADCk', 'Cable a Arduino A0..A3 del STM32N6570-DK', '-', 'jumper Dupont', '-', 1, 2, 'cable dupont macho-macho', 'CH1-A0 (PA5), CH2-A1 (PA9), CH3-A2 (PA10), CH4-A3 (PA12). Mas 1 cable de GND'),
        ('XBF', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 11 OP-AMPS'),
    ]),
    ('9 VREF 1.65 V (compartido)', 1, [
        ('RA1, RA2', 'Divisor de VREF', '100k', '100k', 'pelicula metalica 1 %', 2, 0, 'resistencia 100k 1%', ''),
        ('CA', 'Condensador del divisor', '10u', '10u', 'ceramico X7R o electrolitico', 1, 0, 'condensador 10uF', ''),
        ('XVR', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 11 OP-AMPS'),
    ]),
    ('10 RLD (compartido)', 1, [
        ('RSM1..RSM4', 'Sensado de modo comun (punto medio de RG)', '604k', '620k', 'pelicula metalica 1 %', 4, 1, 'resistencia 620k 1%', ''),
        ('CINT', 'Condensador del integrador', '1n', '1n', 'ceramico C0G/NP0', 1, 1, 'condensador ceramico 1nF NP0', 'Si oscila en banco: 2.2n'),
        ('RPAR', 'Resistencia en paralelo al integrador', '10M', '10M', 'pelicula 5 %', 1, 1, 'resistencia 10M', ''),
        ('RLIM', 'Resistencia de seguridad al electrodo RLD', '390k', '390k', 'pelicula metalica 1 %', 1, 1, 'resistencia 390k 1%', 'Limita la corriente al paciente'),
        ('XRLD', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 11 OP-AMPS'),
    ]),
    ('11 OP-AMPS (paquetes)', 1, [
        ('XHP..XBF x4, XRLD, XVR', 'Op-amp cuadruple (POR DEFINIR, ver hoja Requisitos IC)', 'MCP6004', 'cuadruple rail-to-rail', 'DIP-14', 6, 1, 'MCP6004 / MCP604 / TLV2374 / OPA4340', '22 secciones = 5 por canal x 4 + RLD + VREF (2 libres). Si es doble: 11 unidades DIP-8'),
        ('-', 'Zocalo DIP-14', '-', 'DIP-14', 'zocalo', 6, 1, 'zocalo DIP 14 pines', 'Si los op-amps son dobles: 11 zocalos DIP-8'),
        ('-', 'Desacople de cada op-amp', '100n', '100n', 'ceramico X7R', 6, 2, 'condensador ceramico 100nF', 'Pegado al pin de alimentacion'),
    ]),
    ('12 ALIMENTACION (a bateria)', 1, [
        ('-', 'Regulador LDO 3.3 V', 'MCP1700-3302E', 'MCP1700-3302E TO-92', 'LDO 250 mA', 1, 1, 'MCP1700 3.3V TO-92', 'Tu LDO de 3.0 V no sirve'),
        ('-', 'Condensadores del LDO (entrada y salida)', '1u', '1u', 'ceramico X7R', 2, 1, 'condensador ceramico 1uF', 'Ya tienes 2 x 1uF 0402 (SMD): sirven si los sueldas'),
        ('-', 'Condensador bulk del riel 3.3 V', '10u', '10u', 'ceramico o electrolitico', 1, 1, 'condensador 10uF', ''),
        ('-', 'Portapilas 3 x AA', '-', '3xAA', '-', 1, 0, 'portapilas 3 AA', '4.5 V nominal; mantiene el AFE aislado de la red'),
        ('-', 'Pilas AA', '-', 'AA', 'alcalina', 3, 3, 'pila AA', ''),
        ('-', 'Interruptor', '-', 'deslizante', '-', 1, 0, 'interruptor deslizante', ''),
    ]),
    ('13 ELECTRODOS Y CABLES', 1, [
        ('XE1P..XE4N, XER', 'Electrodo Ag/AgCl con broche', '-', '3M Red Dot 2228/2560', 'desechable', 9, 41, 'electrodo ECG 3M 2228', '9 por sesion (8 de senal + 1 RLD); caja de 50'),
        ('-', 'Cable con broche (snap) para electrodo', '-', 'broche 4 mm', '-', 9, 1, 'cable electrodo broche snap', 'O 3 cables ECG de 3 derivaciones'),
        ('-', 'Alcohol isopropilico / gel', '-', '-', '-', 1, 0, 'alcohol isopropilico', 'Preparar la piel'),
    ]),
    ('14 MECANICA E INTERCONEXION', 1, [
        ('-', 'Perfboard', '-', '10 x 15 cm', 'fibra de vidrio', 1, 1, 'placa perforada 10x15', ''),
        ('-', 'Zocalo DIP-8 (INA)', '-', 'DIP-8', 'zocalo', 4, 1, 'zocalo DIP 8 pines', 'Solo si el INA es DIP-8'),
        ('-', 'Adaptador SOIC/MSOP-8 a DIP-8', '-', '-', 'PCB adaptador', 4, 1, 'adaptador SOIC8 a DIP8', 'Solo si el INA es SMD'),
        ('-', 'Tira de headers macho/hembra', '-', '2.54 mm', '-', 2, 1, 'header 2.54mm 40 pines', ''),
        ('-', 'Cable para puentes', '-', '24 AWG rigido', '-', 1, 0, 'cable rigido 24 AWG', ''),
    ]),
]

COLS = ['Modulo', 'Ref. en esquematico', 'Componente', 'Valor de diseno', 'Valor a comprar', 'Tipo / tolerancia',
        'Cant. por canal', 'N canales', 'Cant. total', 'Repuesto', 'A comprar', 'Buscar como', 'Tienda',
        'Precio unit. (CLP)', 'Subtotal (CLP)', 'Estado', 'Notas']
WID = [26, 22, 38, 14, 22, 26, 9, 9, 9, 9, 10, 32, 18, 13, 14, 12, 60]


def hdr(ws, row, cols):
    for j, c in enumerate(cols, 1):
        x = ws.cell(row, j, c)
        x.font = Font(name=F, bold=True, color='FFFFFF'); x.fill = HDR; x.border = BOX
        x.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center')


def bom(wb):
    ws = wb.active; ws.title = 'BoM por modulo'
    ws['A1'] = 'BoM AFE sEMG AuraVox: 4 canales, 9 electrodos, RLD. Ordenada por modulo, igual que los recuadros del esquematico LTspice (sim/ltspice).'
    ws['A1'].font = Font(name=F, bold=True, size=12)
    ws['A2'] = 'Celdas amarillas = las llenas tu (tienda, precio, estado). Las cantidades y subtotales se calculan solos.'
    ws['A2'].font = Font(name=F, italic=True, size=9)
    hdr(ws, 4, COLS)
    dv = DataValidation(type='list', formula1='"Pendiente,Comprado,No hay,No aplica"', allow_blank=True)
    ws.add_data_validation(dv)
    r = 5
    for name, nch, rows in MODULES:
        ws.cell(r, 1, name)
        for j in range(1, len(COLS) + 1):
            c = ws.cell(r, j); c.fill = MOD; c.font = Font(name=F, bold=True); c.border = BOX
        ws.cell(r, 3, 'por canal (x4)' if nch == 4 else 'compartido')
        r += 1
        for refs, comp, vd, vc, tipo, qch, rep, buscar, nota in rows:
            vals = [name, refs, comp, vd, vc, tipo]
            for j, v in enumerate(vals, 1):
                ws.cell(r, j, v)
            if qch is not None:
                ws.cell(r, 7, qch); ws.cell(r, 8, nch); ws.cell(r, 9, f'=G{r}*H{r}')
                ws.cell(r, 10, rep); ws.cell(r, 11, f'=I{r}+J{r}')
                ws.cell(r, 15, f'=IF(N{r}="","",K{r}*N{r})')
                for j in (13, 14, 16):
                    ws.cell(r, j).fill = INP; ws.cell(r, j).font = Font(name=F, color='0000FF')
                ws.cell(r, 16, 'Pendiente'); dv.add(ws.cell(r, 16))
            ws.cell(r, 12, buscar); ws.cell(r, 17, nota)
            for j in range(1, len(COLS) + 1):
                c = ws.cell(r, j); c.border = BOX
                if c.font.name != F or c.font.color is None:
                    c.font = Font(name=F, color=c.font.color, bold=c.font.bold)
                c.alignment = Alignment(wrap_text=True, vertical='top')
            ws.cell(r, 14).number_format = CLP; ws.cell(r, 15).number_format = CLP
            r += 1
    last = r - 1
    # fila de ejemplo con precio real (MCP1700 en HUBOT)
    for rr in range(5, last + 1):
        if ws.cell(rr, 3).value == 'Regulador LDO 3.3 V':
            ws.cell(rr, 13, 'HUBOT'); ws.cell(rr, 14, 890)
            ws.cell(rr, 14).comment = None
            ws.cell(rr, 17, 'EJEMPLO de llenado: CLP 890 c/IVA en hubot.cl (30-sep-2026). Tu LDO de 3.0 V no sirve')
    ws.cell(last + 2, 14, 'TOTAL').font = Font(name=F, bold=True)
    ws.cell(last + 2, 15, f'=SUM(O5:O{last})').font = Font(name=F, bold=True)
    ws.cell(last + 2, 15).number_format = CLP
    for j, w in enumerate(WID, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = 'C5'
    ws.auto_filter.ref = f'A4:Q{last}'
    return last


def resumen(wb, last):
    ws = wb.create_sheet('Resumen')
    ws['A1'] = 'Resumen por modulo'; ws['A1'].font = Font(name=F, bold=True, size=12)
    hdr(ws, 3, ['Modulo', 'Items', 'Pendientes', 'Subtotal (CLP)'])
    r = 4
    rng = lambda c: f"'BoM por modulo'!${c}$5:${c}${last}"
    for name, _, _ in MODULES:
        ws.cell(r, 1, name)
        ws.cell(r, 2, f'=COUNTIFS({rng("A")},A{r},{rng("P")},"<>")')
        ws.cell(r, 3, f'=COUNTIFS({rng("A")},A{r},{rng("P")},"Pendiente")')
        ws.cell(r, 4, f'=SUMIF({rng("A")},A{r},{rng("O")})'); ws.cell(r, 4).number_format = CLP
        for j in range(1, 5):
            ws.cell(r, j).font = Font(name=F); ws.cell(r, j).border = BOX
        r += 1
    ws.cell(r, 1, 'TOTAL').font = Font(name=F, bold=True)
    ws.cell(r, 2, f'=SUM(B4:B{r - 1})'); ws.cell(r, 3, f'=SUM(C4:C{r - 1})')
    ws.cell(r, 4, f'=SUM(D4:D{r - 1})'); ws.cell(r, 4).number_format = CLP
    for j in range(1, 5):
        ws.cell(r, j).font = Font(name=F, bold=True); ws.cell(r, j).border = BOX
    ws.cell(r + 2, 1, 'El total solo suma las filas con precio. Llena el precio en la hoja BoM por modulo.').font = Font(name=F, italic=True, size=9)
    for j, w in enumerate([40, 10, 12, 16], 1):
        ws.column_dimensions[get_column_letter(j)].width = w


REQ = [
    ('OP-AMP (reemplazo del MCP6004): 22 secciones = HPF, G2, LPF A, LPF B y buffer en cada canal + RLD + VREF', [
        ('Alimentacion unica', 'Funciona con 3.3 V: Vmin <= 3.0 V (ideal <= 2.7 V), Vmax >= 3.6 V', 'Todo el AFE vive en 3.3 V a bateria'),
        ('Salida rail-to-rail', 'Llega a <= 0.1 V de cada riel con 10 kohm', 'La salida va de 0 a 3.3 V centrada en 1.65 V. LM358/LM324 no suben de ~1.8 V con 3.3 V'),
        ('Rango de entrada en modo comun', 'Minimo 0.8-2.5 V (VREF +-0.85 V); ideal rail-to-rail', 'En los filtros y buffers la entrada sigue a la salida'),
        ('Producto ganancia-ancho de banda (GBW)', '>= 0.5 MHz (ideal >= 1 MHz)', 'G2 = 25 hasta 500 Hz y LPF con Q = 1.3'),
        ('Estable a ganancia 1', 'Si', 'HPF, LPF y buffers son seguidores'),
        ('Corriente de polarizacion', '<= 10 nA (entrada CMOS ideal)', 'Resistencias de 56-240 kohm: 10 nA x 110k = 1.1 mV'),
        ('Offset', '<= 5 mV', 'G2 tiene ganancia 1 en DC: el offset no se amplifica'),
        ('Ruido de entrada', '<= 40 nV/rtHz', 'Va despues de G1 = 20: no domina'),
        ('Consumo', '<= 0.5 mA por amplificador', 'Bateria'),
        ('Encapsulado', 'DIP-8/DIP-14, o SOIC con adaptador', 'Perfboard'),
        ('SI sirven', 'MCP6004/MCP6002, MCP604/MCP602, MCP6024/MCP6022, TLV2374/TLV2372, OPA4340/OPA2340, OPA4344/OPA2344, AD8608/AD8606', ''),
        ('Con reservas', 'LMV324/LMV358 (entrada solo hasta V+ - 0.8 V; alcanza para +-0.85 V; suelen ser SMD)', ''),
        ('NO sirven', 'LM358, LM324, TL071/TL072/TL074, NE5532, LM741, LF347, JRC4558, LM833, TLC2272 (no llegan a los rieles con 3.3 V o necesitan mas voltaje)', ''),
    ]),
    ('INA (amplificador de instrumentacion): 4 unidades, una por canal', [
        ('Alimentacion unica', 'Funciona con 3.3 V: Vmin <= 3.0 V', 'Mismo riel que los op-amps'),
        ('Salida', 'Rail-to-rail, o al menos 0.2-3.1 V', 'La salida se centra en VREF = 1.65 V'),
        ('Rango de entrada en modo comun', 'Debe incluir 1.4-1.9 V con alimentacion de 3.3 V', 'El RLD mantiene el cuerpo en VREF = 1.65 V'),
        ('Ganancia', 'Fijada por una sola RG, con los dos pines de RG accesibles', 'El RLD sensa el punto medio de RG. Un modulo con potenciometro obliga a reemplazarlo por 2 resistencias'),
        ('Formula de ganancia', 'G = 1 + 100k/RG: INA333, AD623, AD8226, INA826 (RG = 2 x 2.7k). INA122: G = 5 + 200k/RG. INA126: G = 5 + 80k/RG', 'G1 objetivo ~20'),
        ('CMRR', '>= 90 dB a G = 20 (DC a 50 Hz)', 'Rechazo del 50 Hz de la red'),
        ('Corriente de polarizacion', '<= 25 nA', 'Con 100k de proteccion: <= 2.5 mV de offset'),
        ('Ruido de entrada', '<= 50 nV/rtHz', 'Senal sEMG de 25-50 uV RMS'),
        ('Ancho de banda a G = 20', '>= 5 kHz', 'Banda util 20-500 Hz'),
        ('Encapsulado', 'DIP-8, o SOIC/MSOP con adaptador, o modulo con RG accesible', 'Perfboard'),
        ('SI sirven', 'INA333 (ideal), AD8226, INA826', ''),
        ('Con reservas', 'AD623 (modo comun max ~ Vs - 1.5 V = 1.8 V con 3.3 V: margen de 0.15 V sobre VREF); INA122/INA126 (recalcular RG)', 'AD623AN DIP-8: 2 u por CLP 16.170 en Mercado Libre (30-sep-2026)'),
        ('NO sirven', 'AD620, INA128, INA129, INA114, INA118 (necesitan ~4.6 V o mas y no tienen salida rail-to-rail); AD8232 (frontend completo de 1 canal, choca con el RLD compartido)', ''),
    ]),
    ('LDO 3.3 V (alimentacion del AFE)', [
        ('Salida', '3.3 V fija, >= 50 mA', 'AFE completo consume < 10 mA'),
        ('Entrada', 'Hasta >= 6 V; dropout <= 0.3 V a 20 mA', '3 pilas AA = 4.5 V nueva, ~3.6 V gastada'),
        ('Estabilidad', 'Estable con condensadores ceramicos', ''),
        ('SI sirven', 'MCP1700-3302E (TO-92), MCP1702-3302, LP2950-3.3, HT7333', 'MCP1700: CLP 890 en hubot.cl'),
        ('Con reservas', 'AMS1117-3.3 (dropout ~1.1 V: usar 4 pilas AA)', ''),
        ('NO sirve', 'El LDO de 3.0 V que ya tienes', ''),
    ]),
]


def requisitos(wb):
    ws = wb.create_sheet('Requisitos IC')
    ws['A1'] = 'Condiciones que debe cumplir cada circuito integrado (para elegir reemplazos)'
    ws['A1'].font = Font(name=F, bold=True, size=12)
    r = 3
    for title, rows in REQ:
        ws.cell(r, 1, title)
        for j in range(1, 4):
            ws.cell(r, j).fill = MOD; ws.cell(r, j).font = Font(name=F, bold=True); ws.cell(r, j).border = BOX
        r += 1
        hdr(ws, r, ['Parametro', 'Requisito', 'Por que (en este diseno)']); r += 1
        for a, b, c in rows:
            for j, v in enumerate((a, b, c), 1):
                x = ws.cell(r, j, v); x.font = Font(name=F, bold=(j == 1)); x.border = BOX
                x.alignment = Alignment(wrap_text=True, vertical='top')
            r += 1
        r += 1
    for j, w in enumerate([30, 70, 60], 1):
        ws.column_dimensions[get_column_letter(j)].width = w


TIENDAS = [
    ('Katode', 'San Martin 133 E, Santiago Centro', 'Retiro el mismo dia, L-V 9:30-14:00', 'Pasivos, zocalos, perfboard. Op-amps solo clasicos (TL07x, NE5532): NO sirven', 'katode.cl'),
    ('HUBOT', 'Santiago', 'Despacho el mismo dia si se pide antes de las 12:30', 'MCP1700-3302E (CLP 890)', 'hubot.cl'),
    ('MCI Electronics', 'Santiago', 'Retiro en tienda 8:30-17:30', 'Kits de resistencias 1 %, modulos', 'mcielectronics.cl'),
    ('Afel', 'Santiago', 'Tienda y web', 'Pasivos y kits', 'afel.cl'),
    ('MechatronicStore', 'Curico', 'Envio; gratis sobre CLP 19.990', 'Modulo INA333 MCU-333 (CLP 6.790; RG es potenciometro), poliester', 'mechatronicstore.cl'),
    ('Mercado Libre', '-', 'Filtrar "Llega hoy" y vendedores de Santiago', 'AD623AN DIP-8 (2 u CLP 16.170), electrodos 3M 2228, cables con broche', 'mercadolibre.cl'),
    ('RS Chile', '-', 'Web, plazos segun stock', 'MCP6004-E/P CLP 809 c/IVA, minimo 30 u, sin stock al 30-sep', 'cl.rsdelivers.com'),
    ('Klinetix', 'Santiago', 'Despacho 1-2 dias habiles en RM', 'Electrodos 3M 2228 caja de 50 (agotado al 30-sep)', 'klinetix.cl'),
    ('DigiKey / Mouser', 'EE.UU.', '2-5 dias habiles, impuestos al recibir', 'Cualquier IC de la lista SI sirven', 'digikey.com / mouser.cl'),
]


def tiendas(wb):
    ws = wb.create_sheet('Tiendas')
    ws['A1'] = 'Donde buscar (datos revisados el 30-sep-2026)'; ws['A1'].font = Font(name=F, bold=True, size=12)
    hdr(ws, 3, ['Tienda', 'Ubicacion', 'Modalidad', 'Que tiene / buscar', 'Web'])
    for i, row in enumerate(TIENDAS, 4):
        for j, v in enumerate(row, 1):
            x = ws.cell(i, j, v); x.font = Font(name=F); x.border = BOX; x.alignment = Alignment(wrap_text=True, vertical='top')
    for j, w in enumerate([18, 32, 40, 70, 22], 1):
        ws.column_dimensions[get_column_letter(j)].width = w


if __name__ == '__main__':
    wb = Workbook()
    last = bom(wb); resumen(wb, last); requisitos(wb); tiendas(wb)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    wb.save(OUT)
    print(OUT)
