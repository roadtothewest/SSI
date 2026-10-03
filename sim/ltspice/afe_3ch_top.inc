* AuraVox AFE sEMG - banco completo: 4 canales diferenciales, 9 electrodos
* (4 pares + 1 RLD), 4 salidas ADC1..ADC4, RLD compartido, modelo de cuerpo y red.
*
* El archivo de prueba define:
*   - el estimulo diferencial de cada canal, entre BODY y S1..S4
*     (p. ej. "VIN1 S1 BODY 0" si el canal no lleva senal);
*   - los parametros:
*   RLDMODE 0 = referencia pasiva directa a VREF (1 ohm, sin R de seguridad)
*           1 = referencia pasiva a VREF por RLIM (misma R de seguridad que el RLD)
*           2 = RLD activo (integrador)
*   SENSE   0 = sensado del RLD en el punto medio de RG (propuesta)
*           1 = 100k desde cada electrodo (pizarra)      -1 = sin R de sensado
*   CINT    capacitor del integrador RLD
*   RLIM    resistencia de seguridad entre RLD y su electrodo
*   CGE     capacidad tierra del circuito <-> tierra de red (20p = a bateria,
*           1 = circuito unido a tierra, p. ej. USB a un PC enchufado)
*   VMAINS_TRAN, VMAINS_AC  amplitud de la red de 50 Hz para .tran y para .ac
*   RS, CCM, CD  proteccion y filtro RFI de entrada
* Parametros con valor por defecto (se pueden barrer con .step):
*   CMB   acople red-cuerpo (3p tipico; 30p = cerca de un cable de red)
*   RIMB  desbalance extra en serie con el electrodo - de cada par (51k = IEC 60601-2-27)
*   RER   resistencia del electrodo RLD (20k gel; 200k piel poco preparada)
.param CMB=3p RIMB=51k RER=20k
.include afe_channel.lib
VCC VCC 0 3.3
XVREF VCC VREF VREFGEN

* --- Red electrica y cuerpo (valores tipicos) ---
VM MAINS EARTH SINE(0 {VMAINS_TRAN} 50) AC {VMAINS_AC}
CMB MAINS BODY {CMB}
CBE BODY EARTH 200p
CGE 0 EARTH {CGE}
RGE 0 EARTH 1G

* --- 8 electrodos de senal: 20k || 47n cada uno; el negativo de cada par lleva
* un desbalance extra de 51k || 47n (IEC 60601-2-27). Media celda distinta en cada uno.
XE1P S1 EP1 ELECTRODE Vhc=5m
XE1N BODY E1x ELECTRODE Vhc=-5m
RI1 E1x EN1 {RIMB}
CI1 E1x EN1 47n
XE2P S2 EP2 ELECTRODE Vhc=12m
XE2N BODY E2x ELECTRODE Vhc=0
RI2 E2x EN2 {RIMB}
CI2 E2x EN2 47n
XE3P S3 EP3 ELECTRODE Vhc=-8m
XE3N BODY E3x ELECTRODE Vhc=10m
RI3 E3x EN3 {RIMB}
CI3 E3x EN3 47n

* --- 4 canales ---
XCH1 EP1 EN1 VCC VREF ADC1 RGM1 INA1 AFE_CH Rs={RS} Ccm={CCM} Cd={CD}
XCH2 EP2 EN2 VCC VREF ADC2 RGM2 INA2 AFE_CH Rs={RS} Ccm={CCM} Cd={CD}
XCH3 EP3 EN3 VCC VREF ADC3 RGM3 INA3 AFE_CH Rs={RS} Ccm={CCM} Cd={CD}

* --- RLD: integrador inversor ---
XRLD VREF RLDN VCC 0 RLDO OPA
CINT RLDN RLDO {CINT}
RPAR RLDN RLDO 10Meg
* Sensado (a) punto medio de RG
RSM1 RGM1 RLDN {if(SENSE==0,604k,1T)}
RSM2 RGM2 RLDN {if(SENSE==0,604k,1T)}
RSM3 RGM3 RLDN {if(SENSE==0,604k,1T)}
* Sensado (b) 100k desde cada electrodo (nodos A/B de la pizarra)
RSE1P EP1 RLDN {if(SENSE==1,100k,1T)}
RSE1N EN1 RLDN {if(SENSE==1,100k,1T)}
RSE2P EP2 RLDN {if(SENSE==1,100k,1T)}
RSE2N EN2 RLDN {if(SENSE==1,100k,1T)}
RSE3P EP3 RLDN {if(SENSE==1,100k,1T)}
RSE3N EN3 RLDN {if(SENSE==1,100k,1T)}
* --- 9o electrodo (clavicula): RLD o referencia pasiva ---
RLIM RLDO RLDE {if(RLDMODE==2,RLIM,1T)}
RPAS VREF RLDE {if(RLDMODE==2,1T,if(RLDMODE==1,RLIM,1))}
XER BODY RLDE ELECTRODE Vhc=0 Re={RER}
