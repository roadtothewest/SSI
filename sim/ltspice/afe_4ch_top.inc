* AuraVox AFE - banco de 4 canales con modelo de cuerpo, red y RLD
* Parametros esperados (definir con .param/.step en el archivo de prueba):
*   SENSE  0 = punto medio de RG (propuesta) | 1 = 100k desde cada electrodo (pizarra)
*   RLDON  1 = RLD activo | 0 = electrodo de referencia pasivo a VREF
*   CINT   capacitor del integrador RLD
*   RLIM   resistencia de seguridad del RLD
*   RPASV  R serie de la referencia pasiva cuando RLDON=0 (1 = directa, 390k = con R de seguridad)
*   CGE    capacidad tierra-circuito <-> tierra de red (20p bateria, 1 = alimentado de red)
*   VSEMG  amplitud (pico) del sEMG diferencial (tono de 100 Hz) en CH1 para .tran
*   VMAINS_AC, VDIFF_AC  amplitudes AC de la red y de la senal diferencial de CH1 para .ac
*   CCM, CD, RS  filtro RFI / proteccion
.include afe_channel.lib
VCC VCC 0 3.3
XVREF VCC VREF VREFGEN

* --- Red electrica y cuerpo (valores tipicos, [MEMORIA]) ---
VM MAINS EARTH SINE(0 {VMAINS_TRAN} 50) AC {VMAINS_AC}
CMB MAINS BODY 3p
CBE BODY EARTH 200p
CGE 0 EARTH {CGE}
RGE 0 EARTH 1G

* --- Electrodos: 20k || 47n por electrodo; desbalance 51k || 47n en EN (estilo IEC 60601-2-27) ---
* Offsets de media celda distintos por electrodo
VS1 BODY S1 SINE(0 {VSEMG} 100) AC {VDIFF_AC}
XE1P S1 EP1 ELECTRODE Vhc=5m
XE1N BODY E1x ELECTRODE Vhc=-5m
RI1 E1x EN1 51k
CI1 E1x EN1 47n
XE2P BODY EP2 ELECTRODE Vhc=12m
XE2N BODY E2x ELECTRODE Vhc=0
RI2 E2x EN2 51k
CI2 E2x EN2 47n
XE3P BODY EP3 ELECTRODE Vhc=-8m
XE3N BODY E3x ELECTRODE Vhc=10m
RI3 E3x EN3 51k
CI3 E3x EN3 47n
XE4P BODY EP4 ELECTRODE Vhc=3m
XE4N BODY E4x ELECTRODE Vhc=-15m
RI4 E4x EN4 51k
CI4 E4x EN4 47n

* --- 4 canales ---
XCH1 EP1 EN1 VCC VREF ADC1 RGM1 INA1 AFE_CH Rs={RS} Ccm={CCM} Cd={CD}
XCH2 EP2 EN2 VCC VREF ADC2 RGM2 INA2 AFE_CH Rs={RS} Ccm={CCM} Cd={CD}
XCH3 EP3 EN3 VCC VREF ADC3 RGM3 INA3 AFE_CH Rs={RS} Ccm={CCM} Cd={CD}
XCH4 EP4 EN4 VCC VREF ADC4 RGM4 INA4 AFE_CH Rs={RS} Ccm={CCM} Cd={CD}

* --- RLD: integrador inversor ---
XRLD VREF RLDN VCC 0 RLDO OPA
CINT RLDN RLDO {CINT}
RPAR RLDN RLDO 10Meg
* Sensado (a) punto medio de RG
RSM1 RGM1 RLDN {if(SENSE==0,604k,1T)}
RSM2 RGM2 RLDN {if(SENSE==0,604k,1T)}
RSM3 RGM3 RLDN {if(SENSE==0,604k,1T)}
RSM4 RGM4 RLDN {if(SENSE==0,604k,1T)}
* Sensado (b) 100k desde cada electrodo (nodos A/B de la pizarra)
RSE1P EP1 RLDN {if(SENSE==1,100k,1T)}
RSE1N EN1 RLDN {if(SENSE==1,100k,1T)}
RSE2P EP2 RLDN {if(SENSE==1,100k,1T)}
RSE2N EN2 RLDN {if(SENSE==1,100k,1T)}
RSE3P EP3 RLDN {if(SENSE==1,100k,1T)}
RSE3N EN3 RLDN {if(SENSE==1,100k,1T)}
RSE4P EP4 RLDN {if(SENSE==1,100k,1T)}
RSE4N EN4 RLDN {if(SENSE==1,100k,1T)}
* Salida a electrodo (clavicula) o referencia pasiva
RLIM RLDO RLDE {if(RLDON,RLIM,1T)}
RPAS VREF RLDE {if(RLDON,1T,RPASV)}
XER BODY RLDE ELECTRODE Vhc=0
