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
    ('1 PROTECCION ESD', 3, [
        ('Rsp, Rsn', 'Resistencia serie de entrada', '100k', '100k', 'pelicula metalica 1 % 1/4 W', 2, 2, 'resistencia 100k 1% 1/4W', 'Limita la corriente de falla hacia el paciente y hacia el INA'),
        ('Dp1, Dp2, Dn1, Dn2', 'Diodo de clamp a VCC y GND', '1N4148', '1N4148', 'diodo de senal', 4, 4, '1N4148', '4 por canal x 4 = 16 (+4 repuesto = 20). Protegen el INA de descargas'),
    ]),
    ('2 FILTRO RFI', 3, [
        ('Rfp, Rfn', 'Resistencia del filtro RFI', '1k', '1k', 'pelicula metalica 1 %', 2, 2, 'resistencia 1k 1%', ''),
        ('Ccmp, Ccmn', 'Condensador de modo comun', '47p', '47p', 'ceramico C0G/NP0 5 %', 2, 2, 'condensador ceramico 47pF NP0', 'Si la simulacion final elige 330k sin Ccm, no se usan'),
        ('Cdif', 'Condensador diferencial', '100p', '100p', 'ceramico C0G/NP0 5 %', 1, 1, 'condensador ceramico 100pF NP0', ''),
    ]),
    ('3 AMPLIFICADOR DE INSTRUMENTACION', 3, [
        ('XINA', 'INA333 (modulo MCU-333)', 'INA333', 'INA333 modulo MCU-333', 'modulo; RG: quitar potenciometro', 1, 1, 'modulo MCU-333 INA333', 'Desoldar el trimmer de RG y poner RGa+RGb (2.7k+2.7k) con cable del punto medio al RLD. Alimentar por el pin 3.3V (no VCC) y llevar el pin VREF a tu VREF con buffer. Verificar pines con multimetro. Respaldo: AD623AN DIP-8'),
        ('RGa, RGb', 'Resistencia de ganancia (partida en dos)', '2.61k', '2.7k', 'pelicula metalica 1 %, parear con multimetro', 2, 4, 'resistencia 2.7k 1%', 'Con 2 x 2.7k: G1 = 19.5 (diseno 20.16). El punto medio va al RLD'),
        ('C desac. INA', 'Desacople del INA', '100n', '100n', 'ceramico X7R', 1, 1, 'condensador ceramico 100nF', 'Pegado al pin de alimentacion'),
    ]),
    ('4 HPF 20 Hz (Sallen-Key)', 3, [
        ('Chp1, Chp2', 'Condensador del HPF', '100n', '100n', 'poliester/MKT (film) 5 %', 2, 2, 'condensador poliester 100nF 5%', 'Film, no ceramico: estabilidad y bajo ruido'),
        ('R1', 'Resistencia de realimentacion', '56.2k', '56k', 'pelicula metalica 1 %', 1, 1, 'resistencia 56k 1%', 'Con 56k/110k: f0 = 20.3 Hz, Q = 0.70'),
        ('Ra', 'Resistencia a VREF', '113k', '110k', 'pelicula metalica 1 %', 1, 1, 'resistencia 110k 1%', ''),
        ('XHP', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 10 OP-AMPS'),
    ]),
    ('5 G2 + LPF A: MFB 500 Hz x125 (Q 0.54)', 3, [
        ('Cm0', 'Condensador de bloqueo DC a la entrada del MFB', '10u', '10u', 'ceramico X7R 16 V o electrolitico BIPOLAR (NP)', 1, 1, 'condensador ceramico 10uF X7R / electrolitico bipolar 10uF', 'NO usar electrolitico polarizado: ambos lados quedan en ~1.65 V y la senal lo invierte. Sin Cm0, Ib del TS922 x Ra (110k) x G2 desplaza la salida'),
        ('Rm1', 'Resistencia de entrada (fija la ganancia)', '2.4k', '2.4k', 'pelicula metalica 1 %', 1, 1, 'resistencia 2.4k 1%', 'Ganancia = Rm2/Rm1 = 125 (total 2500). No poner trimmer aqui: cambia el Q del filtro'),
        ('Rm2', 'Resistencia de realimentacion', '300k', '300k', 'pelicula metalica 1 %', 1, 1, 'resistencia 300k 1%', 'Si no hay 300k: 2 x 150k en serie'),
        ('Rm3', 'Resistencia a la entrada inversora', '2.2k', '2.2k', 'pelicula metalica 1 %', 1, 1, 'resistencia 2.2k 1%', ''),
        ('Cm1', 'Condensador a GND = 2 condensadores EN PARALELO', '150n', '100n + 47n en paralelo', 'poliester 100 V (2A104K + 2A473J)', 1, 1, 'condensador poliester 100nF + 47nF', 'ARMADO: soldar el 100n y el 47n entre los mismos dos puntos (nodo MA del MFB y GND), patas cortas. 147 nF: f0 +1 %'),
        ('Cm2', 'Condensador de realimentacion', '1n', '1n', 'ceramico C0G/NP0', 1, 1, 'condensador ceramico 1nF NP0', ''),
        ('XMF', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 10 OP-AMPS'),
    ]),
    ('6 LPF Sallen-Key 500 Hz (Q 1.31)', 3, [
        ('Rlb1, Rlb2', 'Resistencia del LPF B', '54.9k', '56k', 'pelicula metalica 1 %', 2, 2, 'resistencia 56k 1%', 'Con 56k: f0 = 495 Hz'),
        ('C21', 'Condensador de realimentacion = 2 condensadores EN PARALELO', '15n', '10n + 4.7n en paralelo', 'poliester 100 V (2A103J + 2A472K)', 1, 1, 'condensador poliester 10nF + 4.7nF', 'ARMADO: soldar el 10n y el 4.7n entre los mismos dos puntos (union de Rlb1-Rlb2 y la salida del op-amp del SK), patas cortas. 14.7 nF: f0 +1 %'),
        ('C22', 'Condensador a GND', '2.2n', '2.2n', 'poliester 5 % o C0G', 1, 1, 'condensador poliester 2.2nF', ''),
        ('XLB', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 10 OP-AMPS'),
    ]),
    ('7 BUCKET + SALIDA AL ADC', 3, [
        ('Rbk', 'Resistencia del bucket', '100', '100', 'pelicula metalica 1 %', 1, 1, 'resistencia 100 ohm 1%', ''),
        ('Cbk', 'Condensador del bucket', '1n', '1n', 'ceramico C0G/NP0', 1, 1, 'condensador ceramico 1nF NP0', ''),
        ('ADCk', 'Cable a Arduino A1..A3 del STM32N6570-DK', '-', 'jumper Dupont M-H', '-', 1, 2, 'cable dupont macho-hembra (tira de 40)', 'CH1-A1 (PA9), CH2-A2 (PA10), CH3-A3 (PA12). Mas 1 cable de GND. A0 no: comparte ADC con USB1 ISENSE (UM3300)'),
    ]),
    ('8 VREF 1.65 V (compartido)', 1, [
        ('RA1, RA2', 'Divisor de VREF', '100k', '100k', 'pelicula metalica 1 %', 2, 0, 'resistencia 100k 1%', ''),
        ('CA', 'Condensador del divisor', '10u', '10u', 'ceramico X7R o electrolitico', 1, 0, 'condensador 10uF', ''),
        ('XVR', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 10 OP-AMPS'),
    ]),
    ('9 RLD (compartido)', 1, [
        ('RSM1..RSM3', 'Sensado de modo comun (punto medio de RG)', '604k', '620k', 'pelicula metalica 1 %', 3, 1, 'resistencia 620k 1%', ''),
        ('CINT', 'Condensador del integrador', '1n', '1n', 'ceramico C0G/NP0', 1, 1, 'condensador ceramico 1nF NP0', 'Si oscila en banco: 2.2n'),
        ('RPAR', 'Resistencia en paralelo al integrador', '10M', '10M', 'pelicula 5 %', 1, 1, 'resistencia 10M', ''),
        ('RLIM', 'Resistencia de seguridad al electrodo RLD', '390k', '390k', 'pelicula metalica 1 %', 1, 1, 'resistencia 390k 1%', 'Limita la corriente al paciente'),
        ('XRLD', OPS, '-', '-', '-', None, None, '', 'Contada en el modulo 10 OP-AMPS'),
    ]),
    ('10 OP-AMPS (paquetes)', 1, [
        ('XHP, XMF, XLB x3, XRLD, XVR', 'Op-amp doble TS922AIYDT (Global 001-TS922)', 'TS922', 'TS922AIYDT', 'SOIC-8', 6, 0, 'TS922AIYDT', '11 secciones = 3 por canal x 3 + RLD + VREF (1 libre). Solo habia 6 en stock'),
        ('-', 'Adaptador SOIC-8 a DIP-8 (S08D8, Global; trae PCB y 2 headers de 4)', '-', 'S08D8', 'PCB adaptador', 6, 1, 'S08D8 adaptador SOIC 8 a DIP 8', 'Solo para los TS922 (SOIC-8, 1.27 mm). NO sirve para el TLV757 (SOT-23) ni para el INA333 (MSOP). Soldar con flux y probar antes de montar'),
        ('-', 'Zocalo DIP-8 (opcional)', '-', 'DIP-8', 'zocalo', None, None, 'zocalo DIP 8 pines', 'Opcional: soldar los pines del S08D8 directo a la perfboard, o usar tira hembra 2.54 como zocalo'),
        ('-', 'Desacople de cada op-amp', '100n', '100n', 'ceramico X7R', 6, 2, 'condensador ceramico 100nF', 'Pegado al pin de alimentacion'),
    ]),
    ('11 ALIMENTACION (5 V USB / powerbank -> 3.3 V)', 1, [
        ('XLDO', 'Regulador LDO 3.3 V TLV75733PDBVR (Global 014-75733)', 'TLV75733P', 'TLV75733PDBVR', 'SOT-23-5', 1, 1, 'TLV75733PDBVR', 'Entrada 5 V desde el pin +5V del STM32N6570-DK (Arduino CN8). EN unido a IN'),
        ('-', 'Montaje del TLV757 sin adaptador (dead bug)', '-', '-', '-', None, None, '', 'Pegado boca arriba en la perfboard, hilo fino a cada pata. Pines: 1 IN, 2 GND, 3 EN (a IN), 4 NC, 5 OUT. El SOT23S3 de Global es de 3 pines: no sirve'),
        ('CLDOI, CLDOO', 'Condensadores del LDO (entrada y salida)', '1u', '1u', 'ceramico X7R', 2, 1, 'condensador ceramico 1uF', 'Pegados a los pines del LDO'),
        ('CLDOO cer.', 'Condensador ceramico de salida del LDO (en paralelo con el electrolitico)', '1u', '1u X7R', 'MLCC X7R 16 V o mas', 1, 1, 'MLCC THD 1uF X7R', 'El TLV757 esta pensado para ceramico a la salida (>= 0.47 uF efectivos); un electrolitico solo puede oscilar'),
        ('CBULK', 'Condensador bulk del riel 3.3 V', '10u', '10u', 'ceramico o electrolitico', 1, 1, 'condensador 10uF', ''),
        ('-', 'Cable 5 V y GND desde el DK', '-', 'jumper Dupont M-H', '-', 2, 1, 'cable dupont macho-hembra', 'Usar powerbank o PC a bateria mientras haya electrodos puestos (ver Notas de seguridad)'),
    ]),
    ('12 ELECTRODOS Y CONECTORES (7)', 1, [
        ('XE1P..XE3N, XER', 'Electrodo Ag/AgCl con broche 4 mm', '-', 'Skintact FS-RG1/10 32x41', 'desechable', 7, 43, 'Skintact FS-RG1/10 / Kendall Arbo H124SG 24 mm', '7 por sesion (6 de senal + 1 RLD); caja de 50. Skintact para CH1, CH3 y RLD. CH2: Arbo H124SG (24 mm) o par sobre el menton. ISIMED 55x55 solo como RLD'),
        ('-', 'Cable de electrodo con broche (snap) 4 mm, idealmente apantallado', '-', 'broche 4 mm a pin', '-', 7, 1, 'cable electrodo snap 4 mm / cable ECG broche', 'Uno por electrodo; trenzar los dos de cada par. REVISAR EL TERMINAL antes de comprar: debe calzar en header hembra 2.54 mm. Si termina en DIN 1.5 mm touchproof (DIN 42802), cortar y crimpar terminal Dupont hembra o comprar bases touchproof. Alternativa: cable de 3 electrodos con jack 3.5 mm (el de los kits AD8232) + jack hembra 3.5 mm TRS en la placa'),
        ('-', 'Conector de la placa para los 7 electrodos', '-', 'hembra 2x8 2.54 THT', '-', 1, 1, '1105-8X2 conector hembra doble fila 16 vias', 'Una fila: CH1+ CH1- CH2+ CH2- CH3+ CH3- RLD GND(malla). Se enchufa el bus Dupont macho'),
        ('-', 'Bus de 8 cables Dupont macho (separado de una tira de 40)', '-', 'jumper Dupont M-M', '-', 8, 0, 'cable dupont macho-macho 20 cm tira 40', 'Lado macho al conector 2x8; el otro extremo se une a los cables de electrodo (soldado + termorretractil o enchufado)'),
        ('-', 'Alcohol isopropilico / gel', '-', '-', '-', 1, 0, 'alcohol isopropilico', 'Preparar la piel'),
    ]),
    ('13 MECANICA E INTERCONEXION', 1, [
        ('-', 'Perfboard', '-', '10 x 15 cm', 'fibra de vidrio', 1, 1, 'placa perforada 10x15', ''),
                        ('-', 'Tira de header macho 1x40 2.54 THT', '-', 'macho 1x40', '-', 1, 0, 'tira poste recto una fila 40 pines', 'Salidas A1-A3 + GND, 5 V/GND y microfono'),
        ('-', 'Tira de header hembra 1x40 2.54 THT', '-', 'hembra 1x40', '-', 1, 0, 'tira 40 pines header hembra 2.54', 'Zocalo de los 3 modulos INA333 (se cambian sin desoldar)'),
        ('-', 'Cable para puentes', '-', '24 AWG rigido', '-', 1, 0, 'cable UTP Cat6 24 AWG unifilar (por metro)', 'UTP: 8 hilos rigidos por metro. Rigido: no usarlo para los cables de electrodo (se corta al doblarse)'),
    ]),
    ('14 MICROFONO DE REFERENCIA (I2S)', 1, [
        ('-', 'Modulo microfono digital INMP441 (I2S)', '-', 'INMP441', 'modulo', 1, 0, 'modulo microfono INMP441', 'A SAI/I2S del STM32N6570-DK (pines por definir en CubeMX). Alternativa sin cableado: microfono MEMS PDM que trae el DK (U13)'),
        ('-', 'Cables Dupont para el microfono', '-', 'jumper Dupont M-H', '-', 6, 0, 'cable dupont macho-hembra', 'VDD 3.3V, GND, SCK, WS, SD, L/R (L/R a GND)'),
    ]),

]

G, M = 'Global Electronica', 'MechatronicStore'
X7R100N = 'K104K10X7RF53L2 MLCC X7R 100nF 50V'
X7R1N = 'RPE110X7R102K050V MLCC X7R 1nF 50V'
E10U = 'CE50103 electrolitico 10uF 50V'
R100K = 'R2W100K carbon 2 W 5 % 100k'
# Carritos del 4-oct-2026 (precios con IVA, sin despacho). clave = refs (o componente si refs es '-')
#   -> (tienda, parte, cantidad asignada a esta fila, precio unitario, nota de compra)
# Una linea del carrito que cubre varias filas se reparte entre ellas (la suma = lo comprado).
CART = {
    'Rsp, Rsn': (G, R100K, 8, 178, '2 W en vez de 1/4 W: funciona, pero es grande y caro (11 x $178). Si hay 100k 1/4 W, cambiarla'),
    'Dp1, Dp2, Dn1, Dn2': (G, '1N4148', 16, 20, ''),
    'Rfp, Rfn': (M, 'Resistencia carbon 1/4 W 1k (GK3-17)', 8, 100, ''),
    'Ccmp, Ccmn': (G, 'C470NPO04D disco NPO 47pF 50V', 8, 30, ''),
    'Cdif': (G, 'RPE110C0G101J050V MLCC C0G 100pF 50V', 4, 40, ''),
    'XINA': (M, 'Modulo MCU-333 INA333 (GM2-4)', 4, 6790, ''),
    'RGa, RGb': (G, '293-2.7K carbon 1/2 W 5 %', 10, 25, ''),
    'C desac. INA': (G, X7R100N, 4, 40, ''),
    'Chp1, Chp2': (G, X7R100N, 8, 40, 'X7R en vez de poliester: f0 del HPF +-10 %, aceptado para la demo'),
    'R1': (G, '293-56K carbon 1/2 W 5 %', 4, 25, ''),
    'Ra': (G, '291-110K carbon 1/4 W 5 %', 6, 20, ''),
    'Cm0': (G, E10U, 4, 50, 'Electrolitico polarizado: aceptable para la demo (DC ~0 V entre sus patas, senal de mV). Para produccion: X7R o bipolar'),
    'Rm1': (G, '291-2.4K carbon 1/4 W 5 %', 6, 20, ''),
    'Rm2': (G, '291-300K carbon 1/4 W 5 %', 6, 20, ''),
    'Rm3': (G, '293-2.2K carbon 1/2 W 5 %', 5, 25, ''),
    'Cm2': (G, X7R1N, 4, 60, 'X7R en vez de C0G: aceptado para la demo'),
    'Rlb1, Rlb2': (G, '293-56K carbon 1/2 W 5 %', 8, 25, ''),
    'C22': (G, 'C222NPO05D disco NPO 2.2nF 50V', 4, 30, ''),
    'Rbk': (G, 'R1W100 carbon 1 W 100 ohm', 6, 50, ''),
    'Cbk': (G, X7R1N, 4, 60, ''),
    'RA1, RA2': (G, R100K, 3, 178, ''),
    'CA': (G, E10U, 1, 50, ''),
    'RSM1..RSM3': (G, '291-620K carbon 1/4 W 5 %', 6, 20, ''),
    'CINT': (G, X7R1N, 2, 60, ''),
    'RPAR': (G, '291-10M carbon 1/4 W 5 %', 4, 20, ''),
    'RLIM': (G, '293-390K carbon 1/2 W 5 %', 4, 25, ''),
    'XHP, XMF, XLB x3, XRLD, XVR': (G, 'TS922AIYDT', 6, 2890, ''),
    'Adaptador SOIC-8 a DIP-8 (S08D8, Global; trae PCB y 2 headers de 4)': (G, 'S08D8', 12, 250, 'En el carrito hay 12; bastan 7 (sobran 5 = $1.250)'),
    'Desacople de cada op-amp': (G, X7R100N, 8, 40, ''),
    'XLDO': (G, 'TLV75733PDBVR', 2, 950, ''),
    'CLDOI, CLDOO': (G, 'CE50102 electrolitico 1uF 50V', 3, 90, 'Ver la fila CLDOO cer.: a la salida hace falta ademas un ceramico'),
    'CBULK': (G, E10U, 2, 50, ''),
    'Conector de la placa para los 7 electrodos': (G, '1105-8X2 hembra doble fila 16 vias 2.54', 2, 150, ''),
    'Cable para puentes': (G, '6UNI UTP Cat6 4 pares 24 AWG unifilar (m)', 3, 300, '3 m'),
    'Modulo microfono digital INMP441 (I2S)': (G, 'INMP441 sensor microfono omnidireccional (pagina 5044)', 1, 7790, ''),
    'Cm1': (G, '2A104K poliester 100nF 100V + 2A473J poliester 47nF 100V, en paralelo (par)', 4, 130,
            'No hay 150 nF en Global: 100n + 47n en paralelo = 147 nF (f0 +1 %, Q -1 %). Cantidad en pares; precio del par ($70 + $60)'),
    'CLDOO cer.': (G, 'CM105 MLCC THD 1uF 50V X7R', 2, 50, ''),
    'Tira de header macho 1x40 2.54 THT': (G, '1109-40L tira poste recto una fila 40 pines, pin largo', 1, 490, ''),
    'Tira de header hembra 1x40 2.54 THT': (M, 'Fila de 40 pines header hembra 2.54 (GD2-3)', 1, 490, ''),
    'C21': (G, '2A103J poliester 10nF 100V + 2A472K poliester 4.7nF 100V, en paralelo (par)', 4, 110,
            '15 nF agotado (2A153J en Global; tampoco en MechatronicStore): 10n + 4.7n en paralelo = 14.7 nF (f0 +1 %, Q -1 %). '
            'Cantidad en pares; precio del par ($50 + $60)'),
    'ADCk': (G, 'JPMH20 cable Dupont M-H 20 cm (1 unidad)', 2, 50, 'Son cables sueltos, no una tira de 40'),
    'Bus de 8 cables Dupont macho (separado de una tira de 40)': (G, 'JPMM20 cable Dupont M-M 20 cm (1 unidad)', 2, 50, 'Son cables sueltos, no una tira de 40'),
}
ORDERS = {G: 'Pedido BVGDHKTGU (4-oct-2026), retiro en tienda Global (Vina del Mar). Total $39.433',
          M: 'Pedido del 4-oct-2026, despacho Bluexpress (gratis). Total $28.450'}
# Ya los tiene el usuario (no se compran)
OWNED = {'Perfboard'}
# Por agregar al carrito de Global (encontrados en globalelectronica.cl el 4-oct-2026). Mismo formato que CART.
ADD = {}
# Lo que falta y no esta en ninguna fila de diseno (insumos de montaje)
INSUMOS_TENIDOS = [  # estano, flux, malla y termorretractil: ya los tiene el usuario (4-oct)
    (1, 'Estano 0.5-0.8 mm con nucleo de flux', 'soldadura estano 0.8 mm', 'Global (soldadura)', ''),
    (1, 'Flux (lapiz o pasta)', 'flux', 'Global (flux y mallas)', 'Imprescindible para soldar los TS922 en los S08D8'),
    (1, 'Malla desoldadora', 'malla desoldadora', 'Global (flux y mallas)', 'Para sacar los trimmers de los modulos INA333'),
    (1, 'Termorretractil 2-3 mm (surtido)', 'tubo termo retractil', 'Global', 'Uniones bus Dupont - cable de electrodo'),
]
INSUMOS = []
ARMADO = [
    'Cm1 (MFB, x3 canales) = 100 nF (2A104K) EN PARALELO con 47 nF (2A473J): los dos entre el nodo MA (union Rm1-Rm2-Rm3) y GND.',
    'C21 (Sallen-Key, x3 canales) = 10 nF (2A103J) EN PARALELO con 4.7 nF (2A472K): los dos entre la union Rlb1-Rlb2 y la salida del op-amp del SK.',
    'Cm0 (10 uF electrolitico): entre sus patas hay ~0 V DC; cualquier orientacion sirve. Por convencion: + hacia la salida del HPF.',
    'LDO: CM105 (1 uF ceramico) en paralelo con el CE50102 (1 uF electrolitico) a la salida, pegados a los pines OUT y GND.',
    'La simulacion ya usa los valores armados: CM1 = 147n y C21 = 14.7n.',
]
DONDE = {
    'Electrodo Ag/AgCl con broche 4 mm': 'Tiendas de insumos medicos / Mercado Libre',
    'Cable de electrodo con broche (snap) 4 mm, idealmente apantallado': 'MechatronicStore ("cable de electrodos AD8232") / tiendas medicas',
    'Alcohol isopropilico / gel': 'Farmacia / ferreteria',
    'Perfboard': 'Global (tarjetas para prototipos) / MechatronicStore',
    'Cable a Arduino A1..A3 del STM32N6570-DK': 'MechatronicStore / Global. 1 tira de 40 M-H cubre las 3 filas M-H (14 cables)',
    'Cable 5 V y GND desde el DK': 'MechatronicStore / Global (misma tira M-H)',
    'Cables Dupont para el microfono': 'MechatronicStore / Global (misma tira M-H)',
    'Bus de 8 cables Dupont macho (separado de una tira de 40)': 'MechatronicStore / Global. 1 tira de 40 M-M',
}
STATES = '"Pendiente,En carrito,Comprado,Parcial,Ya lo tengo,No hay,No aplica"'
# notas generales de la compra (hoja Resumen)
AVISOS = [
    'Pedidos hechos el 4-oct-2026: Global $39.433 (retiro en tienda) + MechatronicStore $28.450 (Bluexpress) = $67.883.',
    'Dupont: JPMH20/JPMM20 son cables SUELTOS. Tienes 2 M-H y 2 M-M; el diseno usa 14 M-H y 8 M-M (faltan 12 M-H y 6 M-M; Global tiene stock, $50 c/u).',
    'Falta: electrodos, cables de electrodo y alcohol (ver FALTA COMPRAR).',
    'Resistencias de carbon 5 % en vez de pelicula metalica 1 %: aceptado para la demo (ganancia por canal +-7 %, se normaliza en firmware). Para produccion: 1 %.',
    'Precios con IVA.',
]

COLS = ['Modulo', 'Ref. en esquematico', 'Componente', 'Valor de diseno', 'Valor a comprar', 'Tipo / tolerancia',
        'Cant. por canal', 'N canales', 'Cant. total', 'Repuesto', 'A comprar', 'Buscar como', 'Tienda',
        'Parte en el carrito', 'Cant. en carrito', 'Precio unit. (CLP)', 'Subtotal (CLP)', 'Estado', 'Notas']
WID = [26, 22, 38, 14, 22, 26, 9, 9, 9, 9, 10, 32, 18, 34, 10, 13, 14, 12, 70]


def key(refs, comp):
    return refs if refs != '-' else comp


def hdr(ws, row, cols):
    for j, c in enumerate(cols, 1):
        x = ws.cell(row, j, c)
        x.font = Font(name=F, bold=True, color='FFFFFF'); x.fill = HDR; x.border = BOX
        x.alignment = Alignment(wrap_text=True, vertical='center', horizontal='center')


def bom(wb):
    ws = wb.active; ws.title = 'BoM por modulo'
    ws['A1'] = 'BoM AFE sEMG AuraVox: 3 canales (submentoniano, labio inferior, laringe), 7 electrodos, RLD. Ordenada por modulo, igual que los recuadros del esquematico LTspice (sim/ltspice).'
    ws['A1'].font = Font(name=F, bold=True, size=12)
    ws['A2'] = ('Carritos del 4-oct-2026 (Global Electronica + MechatronicStore) ya cargados. Celdas amarillas = editables. '
                'SEGURIDAD: con electrodos puestos alimentar el DK con powerbank o PC a bateria, nunca con un cargador de pared.')
    ws['A2'].font = Font(name=F, italic=True, size=9)
    hdr(ws, 4, COLS)
    dv = DataValidation(type='list', formula1=STATES, allow_blank=True)
    ws.add_data_validation(dv)
    r = 5
    for name, nch, rows in MODULES:
        ws.cell(r, 1, name)
        for j in range(1, len(COLS) + 1):
            c = ws.cell(r, j); c.fill = MOD; c.font = Font(name=F, bold=True); c.border = BOX
        ws.cell(r, 3, 'por canal (x3)' if nch == 3 else 'compartido')
        r += 1
        for refs, comp, vd, vc, tipo, qch, rep, buscar, nota in rows:
            for j, v in enumerate([name, refs, comp, vd, vc, tipo], 1):
                ws.cell(r, j, v)
            k = key(refs, comp)
            cart = CART.get(k) or ADD.get(k)
            if qch is not None:
                ws.cell(r, 7, qch); ws.cell(r, 8, nch); ws.cell(r, 9, f'=G{r}*H{r}')
                ws.cell(r, 10, rep); ws.cell(r, 11, f'=I{r}+J{r}')
                ws.cell(r, 17, f'=IF(P{r}="","",IF(O{r}="",K{r},O{r})*P{r})')
                for j in (13, 14, 15, 16, 18):
                    ws.cell(r, j).fill = INP; ws.cell(r, j).font = Font(name=F, color='0000FF')
                if comp in OWNED:
                    ws.cell(r, 18, 'Ya lo tengo')
                elif cart:
                    tienda, parte, cant, precio, nc = cart
                    for j, v in ((13, tienda), (14, parte), (15, cant), (16, precio)):
                        ws.cell(r, j, v)
                    need = qch * nch + rep
                    st = ('Comprado' if tienda in ORDERS else 'En carrito') if k in CART else 'Pendiente'
                    if k in CART and cant is not None and cant < need:
                        st = 'Parcial'; nc = (nc + '. ' if nc else '') + f'FALTAN {need - cant}'
                    ws.cell(r, 18, st)
                    if k in ADD:
                        nc = 'AGREGAR AL CARRITO DE GLOBAL' + ('. ' + nc if nc else '')
                    if nc:
                        nota = (nc + '. ' + nota) if nota else nc
                else:
                    ws.cell(r, 18, 'Pendiente')
                    nota = ('FALTA EN EL CARRITO. ' + nota) if nota else 'FALTA EN EL CARRITO'
                dv.add(ws.cell(r, 18))
            else:
                ws.cell(r, 18, 'No aplica')
            ws.cell(r, 12, buscar); ws.cell(r, 19, nota)
            for j in range(1, len(COLS) + 1):
                c = ws.cell(r, j); c.border = BOX
                if c.font.name != F or c.font.color is None:
                    c.font = Font(name=F, color=c.font.color, bold=c.font.bold)
                c.alignment = Alignment(wrap_text=True, vertical='top')
            if ws.cell(r, 18).value in ('Pendiente', 'Parcial'):
                ws.cell(r, 18).font = Font(name=F, bold=True, color='C00000')
            ws.cell(r, 16).number_format = CLP; ws.cell(r, 17).number_format = CLP
            r += 1
    last = r - 1
    ws.cell(last + 2, 16, 'TOTAL').font = Font(name=F, bold=True)
    ws.cell(last + 2, 17, f'=SUM(Q5:Q{last})').font = Font(name=F, bold=True)
    ws.cell(last + 2, 17).number_format = CLP
    falta(ws, last + 4)
    for j, w in enumerate(WID, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = 'C5'
    ws.auto_filter.ref = f'A4:S{last}'
    return last


def falta_rows():
    """[(cant, que, buscar como, donde, nota)] de todo lo que no esta en los carritos."""
    out = []
    for _, nch, rows in MODULES:
        for refs, comp, vd, vc, tipo, qch, rep, buscar, nota in rows:
            k = key(refs, comp)
            if qch is None or comp in OWNED:
                continue
            q = qch * nch + rep
            if k in CART:
                if CART[k][2] is not None and CART[k][2] < q:
                    out.append((q - CART[k][2], f'{vc} {comp}', buscar, DONDE.get(comp, ''), f'Compraste {CART[k][2]} de {q}'))
                continue
            add = ADD.get(k)
            que = f'{vc} {comp}' if vc not in ('-',) else comp
            if add:
                out.append((q, que, add[1], 'Global (agregar al carrito)', add[4]))
            else:
                out.append((q, que, buscar, DONDE.get(comp, ''), nota))
    return out + [(q, que, b, d, n + ' (insumo, no esta en el esquematico)' if n else 'insumo, no esta en el esquematico')
                  for q, que, b, d, n in INSUMOS]


def falta(ws, r0):
    ws.cell(r0, 1, 'FALTA COMPRAR (no esta en los carritos del 4-oct-2026)').font = Font(name=F, bold=True, size=12, color='C00000')
    hdr(ws, r0 + 1, ['Cant.', 'Que', 'Buscar como', 'Donde', 'Notas'])
    for i, row in enumerate(falta_rows(), r0 + 2):
        for j, v in enumerate(row, 1):
            c = ws.cell(i, j, v); c.font = Font(name=F); c.border = BOX
            c.alignment = Alignment(wrap_text=True, vertical='top')


def resumen(wb, last):
    ws = wb.create_sheet('Resumen')
    ws['A1'] = 'Resumen por modulo'; ws['A1'].font = Font(name=F, bold=True, size=12)
    hdr(ws, 3, ['Modulo', 'Items', 'Pendientes', 'Subtotal (CLP)'])
    r = 4
    rng = lambda c: f"'BoM por modulo'!${c}$5:${c}${last}"
    for name, _, _ in MODULES:
        ws.cell(r, 1, name)
        ws.cell(r, 2, f'=COUNTIFS({rng("A")},A{r},{rng("R")},"<>No aplica",{rng("R")},"<>")')
        ws.cell(r, 3, f'=COUNTIFS({rng("A")},A{r},{rng("R")},"Pendiente")')
        ws.cell(r, 4, f'=SUMIF({rng("A")},A{r},{rng("Q")})'); ws.cell(r, 4).number_format = CLP
        for j in range(1, 5):
            ws.cell(r, j).font = Font(name=F); ws.cell(r, j).border = BOX
        r += 1
    ws.cell(r, 1, 'TOTAL').font = Font(name=F, bold=True)
    ws.cell(r, 2, f'=SUM(B4:B{r - 1})'); ws.cell(r, 3, f'=SUM(C4:C{r - 1})')
    ws.cell(r, 4, f'=SUM(D4:D{r - 1})'); ws.cell(r, 4).number_format = CLP
    for j in range(1, 5):
        ws.cell(r, j).font = Font(name=F, bold=True); ws.cell(r, j).border = BOX
    r += 2
    hdr(ws, r, ['Tienda', 'Comprado (CLP)', 'En carrito / por agregar (CLP)', ''])
    for t in (G, M):
        r += 1
        ws.cell(r, 1, t).font = Font(name=F)
        ws.cell(r, 2, f'=SUMIFS({rng("Q")},{rng("M")},A{r},{rng("R")},"Comprado")+SUMIFS({rng("Q")},{rng("M")},A{r},{rng("R")},"Parcial")').number_format = CLP
        ws.cell(r, 3, f'=SUMIFS({rng("Q")},{rng("M")},A{r},{rng("R")},"En carrito")+SUMIFS({rng("Q")},{rng("M")},A{r},{rng("R")},"Pendiente")').number_format = CLP
    r += 2
    ws.cell(r, 1, 'Faltan en los carritos').font = Font(name=F, bold=True, color='C00000')
    for _, nch, rows in MODULES:
        for refs, comp, vd, vc, tipo, qch, rep, buscar, nota in rows:
            if qch is not None and key(refs, comp) not in CART:
                r += 1
                add = ADD.get(key(refs, comp))
                ws.cell(r, 1, f'{qch * nch + rep} x {vc if vc != "-" else ""}  {comp}').font = Font(name=F)
                ws.cell(r, 2, f'Global: {add[1]}' if add else buscar).font = Font(name=F, color='595959')
    r += 2
    ws.cell(r, 1, 'Pedidos').font = Font(name=F, bold=True)
    for t, o in ORDERS.items():
        r += 1
        ws.cell(r, 1, f'{t}: {o}').font = Font(name=F)
    r += 2
    ws.cell(r, 1, 'ARMADO: condensadores en paralelo y polaridades').font = Font(name=F, bold=True, color='1F3A5F')
    for a in ARMADO:
        r += 1
        ws.cell(r, 1, a).font = Font(name=F)
    r += 2
    ws.cell(r, 1, 'Avisos de la compra').font = Font(name=F, bold=True)
    for a in AVISOS:
        r += 1
        ws.cell(r, 1, a).font = Font(name=F)
    for j, w in enumerate([70, 44, 12, 16], 1):
        ws.column_dimensions[get_column_letter(j)].width = w


REQ = [
    ('OP-AMP (reemplazo del MCP6004): 22 secciones = HPF, G2, LPF A, LPF B y buffer en cada canal + RLD + VREF', [
        ('Alimentacion unica', 'Funciona con 3.3 V: Vmin <= 3.0 V (ideal <= 2.7 V), Vmax >= 3.6 V', 'Todo el AFE vive en 3.3 V a bateria'),
        ('Salida rail-to-rail', 'Llega a <= 0.1 V de cada riel con 10 kohm', 'La salida va de 0 a 3.3 V centrada en 1.65 V. LM358/LM324 no suben de ~1.8 V con 3.3 V'),
        ('Rango de entrada en modo comun', 'Minimo 0.8-2.5 V (VREF +-0.85 V); ideal rail-to-rail', 'En los filtros y buffers la entrada sigue a la salida'),
        ('Producto ganancia-ancho de banda (GBW)', '>= 0.5 MHz (ideal >= 1 MHz)', 'G2 = 125 hasta 500 Hz (necesita >= 0.3 MHz; TS922 ~4 MHz) y LPF con Q = 1.3'),
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
    ('Global Electronica', 'Santiago', 'Web y tienda', 'TS922AIYDT, TLV75733PDBVR, S08D8, pasivos, conectores, INMP441 (carrito del 4-oct)', 'globalelectronica.cl'),
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


def _cat(comp, tipo):
    t = tipo.lower()
    for k, v in (('pelicula', 'resistencia'), ('poliester/mkt', 'cond. poliester (film)'), ('poliester', 'cond. poliester o C0G'),
                 ('c0g', 'cond. ceramico C0G'), ('x7r', 'cond. ceramico/electrolitico'), ('ceramico o', 'cond. ceramico/electrolitico'),
                 ('diodo', 'diodo')):
        if k in t:
            return v
    return comp


def compact_rows():
    """Agrupa por (categoria, valor): [(valor, cantidad total con repuesto, categoria)]."""
    agg = {}
    for _, nch, rows in MODULES:
        for refs, comp, vd, vc, tipo, qch, rep_, buscar, nota in rows:
            if not qch:
                continue
            cat = _cat(comp, tipo)
            val = vc if vc not in ('-',) else comp
            agg[(cat, val)] = agg.get((cat, val), 0) + qch * nch + rep_
    return [(v, q, c) for (c, v), q in agg.items()]


def compact_purchase():
    """Por (categoria, valor): tiendas, cantidad en carrito, precio unitario (si es unico) y estado."""
    agg = {}
    for _, nch, rows in MODULES:
        for refs, comp, vd, vc, tipo, qch, rep_, buscar, nota in rows:
            if not qch:
                continue
            k = (_cat(comp, tipo), vc if vc not in ('-',) else comp)
            a = agg.setdefault(k, {'tiendas': set(), 'cant': 0, 'precios': set(), 'pend': False})
            cart = CART.get(key(refs, comp))
            add = ADD.get(key(refs, comp))
            if comp in OWNED:
                a['tiendas'].add('ya lo tengo')
            elif cart:
                a['tiendas'].add(cart[0]); a['cant'] += cart[2]
                if cart[3] is not None:
                    a['precios'].add(cart[3])
            else:
                a['pend'] = True
                if add:
                    a['tiendas'].add(add[0] + ' (agregar: ' + add[1] + ')')
    return agg


def compacta():
    wb = Workbook(); ws = wb.active; ws.title = 'BoM compacta'
    ws['A1'] = 'BoM compacta AFE sEMG AuraVox (3 canales, incluye repuesto). Detalle por modulo en BoM_AFE_AuraVox.xlsx'
    ws['A1'].font = Font(name=F, bold=True, size=12)
    ws['A2'] = 'Carritos del 4-oct-2026 cargados. Precios con IVA, sin despacho. En rojo: falta en los carritos.'
    ws['A2'].font = Font(name=F, italic=True, size=9)
    hdr(ws, 3, ['Valor / parte', 'Cantidad', 'Componente', 'Tienda', 'En carrito', 'Precio unit. (CLP)', 'Subtotal (CLP)', 'Estado'])
    pur = compact_purchase()
    rows = sorted(compact_rows(), key=lambda r: (r[2], r[0]))
    for i, (v, q, t) in enumerate(rows, 4):
        a = pur[(t, v)]
        estado = ('Ya lo tengo' if a['tiendas'] == {'ya lo tengo'} else
                  'Pendiente' if a['pend'] and not a['cant'] else
                  'Parcial' if a['pend'] or (a['cant'] < q and not v.endswith('paralelo')) else 'Comprado')
        precio = next(iter(a['precios'])) if len(a['precios']) == 1 else None
        for j, x in enumerate((v, q, t, ', '.join(sorted(a['tiendas'])), a['cant'] or None, precio), 1):
            ws.cell(i, j, x).font = Font(name=F)
        ws.cell(i, 7, f'=IF(OR(E{i}="",F{i}=""),"",E{i}*F{i})').number_format = CLP
        roja = estado in ('Pendiente', 'Parcial')
        ws.cell(i, 8, estado).font = Font(name=F, bold=roja, color='C00000' if roja else '000000')
        for j in (4, 5, 6, 8):
            ws.cell(i, j).fill = INP
        ws.cell(i, 6).number_format = CLP
        for j in range(1, 9):
            ws.cell(i, j).border = BOX
    n = 3 + len(rows)
    ws.cell(n + 1, 6, 'TOTAL').font = Font(name=F, bold=True)
    ws.cell(n + 1, 7, f'=SUM(G4:G{n})').number_format = CLP
    falta(ws, n + 3)
    r = n + 6 + len(falta_rows())
    ws.cell(r, 1, 'ARMADO: condensadores en paralelo y polaridades').font = Font(name=F, bold=True, color='1F3A5F')
    for a in ARMADO:
        r += 1
        ws.cell(r, 1, a).font = Font(name=F)
    r += 2
    ws.cell(r, 1, 'Avisos de la compra').font = Font(name=F, bold=True)
    for a in AVISOS:
        r += 1
        ws.cell(r, 1, a).font = Font(name=F)
    for j, w in enumerate([30, 10, 34, 20, 10, 16, 16, 12], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = 'A4'
    out = OUT.replace('.xlsx', '_compacta.xlsx'); wb.save(out); print(out)


if __name__ == '__main__':
    wb = Workbook()
    last = bom(wb); resumen(wb, last); requisitos(wb); tiendas(wb)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    wb.save(OUT)
    print(OUT)
    compacta()
