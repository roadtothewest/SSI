# Simulación LTspice del AFE sEMG AuraVox (3 canales, TS922 + INA333)

## Abrir y correr
```bash
cd ~/SSI/sim/ltspice
wine "C:\Program Files\ADI\LTspice\LTspice.exe" AuraVox_AFE.asc
```
Run: una sola simulación de 1,2 s, con el RLD conectado (salida del integrador → RLIM 390k → electrodo RLD). Tarda unos 5 min con el macromodelo oficial del TS922.
- **Para probar sin RLD:** en el recuadro RLD, borra el cable marcado entre RLIM y el electrodo RLD y vuelve a dar Run. Compara `CM_cuerpo_Vpp`, `V(body)` y `V(adc1..3)` con la corrida anterior. Con ese cable abierto el cuerpo queda sin camino de DC (igual que en la placa real) y el integrador del RLD se va al riel.
- Resultados numéricos: *View > SPICE Error Log* (`VCC_V`, `VREF_V`, `CM_cuerpo_Vpp`, `ADCk_DC_V`, `ADCk_pk_V` (pico de la salida respecto a VREF), `ADCk_rafaga/reposo_mVrms`, `SNRk_salida_dB`, `PINk_min/max_V`, `sEMGk_uVrms`).
- Para ver las 7 etapas de un canal (ESD → RFI → INA333 ×20 → HPF 20 Hz → G2 + LPF etapa A: MFB ×125 → LPF etapa B + buffer: Sallen-Key ×1 → RC): doble clic en un bloque `CANAL`.

## Cómo se simula cada entrada diferencial (todo en LTspice)
La fuente `BINk` va entre el cuerpo (`BODY`) y el electrodo + del canal k. Su valor es la suma de:

| Componente | Fuentes | Detalle |
|---|---|---|
| sEMG útil | `BWk` → `LSEMk`-`CSEMk`-`RSEMk` → `BSEMk` | Ruido blanco `white()`, filtrado por un pasabanda RLC serie (f0 = 90 Hz, Q = 0,7; antes era una fuente Laplace, que trababa la transitoria con el TS922 real) y multiplicado por la envolvente de habla `VENV`: ráfagas de 170 ms cada 420 ms, 5 % de tono en reposo. Amplitud `AS1..AS3` = 50/40/25 µV RMS (submentoniano, labio inferior, laringe) |
| Movimiento | `white(3*time)` | 500 µV RMS, < 10 Hz |
| ECG | `VECG` | PQRST que se repite a 72 lpm, con pico `GE1..GE3` = 120/50/250 µV (más fuerte en el cuello) |
| Ruido blanco | `white(2e4*time)` | 20 µV RMS |

Además actúan, ya incluidos en el banco:
- la red de 311 V acoplada al cuerpo, con el circuito a tierra por USB (peor caso);
- la media celda DC de cada electrodo;
- el desbalance 51k‖47n (IEC 60601-2-27).

`KN=0` quita todo el ruido.

### Qué es cada nodo y en qué unidades
Los generadores son adimensionales (escala 1 V) y **no son señales del cuerpo**. Se escalan dentro de `BINk`.

| Nodo | Qué es | Valor típico |
|---|---|---|
| `w1..w3` | ruido blanco unitario `white()` | ±0,5 V, 0,24 V RMS |
| `f1..f3` | ese ruido pasado por el RLC de 90 Hz | ~0,04 V RMS (`KSEM=25` lo normaliza a 1) |
| `env` | envolvente del habla | 0,05 (reposo) a 1 (ráfaga) |
| `ecg` | latido PQRST de 72 lpm, normalizado | pico 1 V |
| `semg1..3` | **sEMG real** en el electrodo | 50/40/25 µV RMS en ráfaga |
| `V(n1)-V(BODY)` | **entrada diferencial total** del canal | ~540 µV RMS (domina el movimiento, < 10 Hz) |
| `MAINS` | red de 220 Vrms (311 Vpk, 50 Hz) en el cableado del recinto | se acopla al cuerpo solo por `CMB` = 3 pF |
| `BODY` | modo común del cuerpo | algunos mV sin RLD, mucho menos con RLD |
| `adc1..3` | salida del AFE | DC ≈ VREF = 1,65 V; sEMG ≈ ±0,5 V en ráfaga |
| `pin1..3` | lo que ve el ADC del DK (dominio 1,8 V) | ≈ 0,90 V ± varios cientos de mV en ráfaga |

La red de 311 V no está aplicada al paciente: representa el cableado cercano, que acopla capacitivamente unos pocos mV de 50 Hz al cuerpo. Ese modo común es lo que el RLD debe cancelar.

Las mediciones `ADCk_rafaga/reposo_mVrms` son solo la parte AC, porque restan el promedio. `ADCk_DC_V` es el nivel DC.

## Salidas al STM32N6570-DK (UM3300)
`ADCk` (k = 1..3) pasa por el modelo del amplificador de la placa (3,3 V → 1,8 V, ganancia `GDK`; verificar en el esquemático MB1939) y por el muestreo del ADC, y llega a `pink`.

| Canal | Pin Arduino | Pin del MCU | Canal ADC |
|---|---|---|---|
| CH1 | A1 | PA9 | ADC12_INP10 |
| CH2 | A2 | PA10 | ADC12_INP11 |
| CH3 | A3 | PA12 | ADC12_INP13 |

No usar A0 (comparte ADC con USB1 ISENSE) ni A5 (compartido con STMod+). A4 (PF3) queda libre.

## Cambiar componentes
Recuadro **VALORES** de la hoja: un `.param` por componente, que usan las 3 copias del canal. La BoM está en el recuadro inferior y en `docs/afe-emg/BoM_AFE_AuraVox*.xlsx`; se regeneran con `python3 tools/make_bom_xlsx.py && python3 tools/make_asc.py && python3 tools/check_asc.py`. `check_asc.py` también falla si queda algún pin o cable abierto.

## Componentes activos
- INA: módulo INA333 MCU-333 ×3 (+1), con RG = 2 × 2,7k y el punto medio al RLD.
- Op-amp: TS922AIYDT ×6 (11 de las 12 secciones: 3 por canal + RLD + VREF), en adaptador SOIC-8 → DIP-8.
- El LPF es de 4º orden: MFB + Sallen-Key. `Cm0` = 10 µF (electrolítico o cerámico) en serie a la entrada del MFB bloquea el DC. Sin él, la corriente de polarización del TS922 en Ra (110k) × G2 desplazaba la salida. La ganancia total es **2500** (G1 20 × G2 125): la escala completa es ±1,4 V en la salida del TS922, o sea 0,14–1,66 V en el pin del DK, para ±560 µV pico de entrada.
- Mapeo al pipeline original (ESD, RFI, INA, HPF, G2, LPF, buffer): el **MFB** hace G2 + LPF etapa A, y el **Sallen-Key de ganancia 1** hace LPF etapa B + buffer. Son 3 op-amps por canal, porque solo hay 6 TS922 (12 secciones = 3 × 3 + RLD + VREF).

## Armado: condensadores en paralelo
No había 150 nF ni 15 nF en las tiendas, así que cada uno se arma con dos de poliéster **en paralelo**, en cada uno de los 3 canales. La simulación ya usa los valores armados (`CM1=147n`, `C21=14.7n`).

| Posición | Se arma con | Entre |
|---|---|---|
| **Cm1** (MFB) | 100 nF (2A104K) ∥ 47 nF (2A473J) = 147 nF | nodo MA (unión Rm1-Rm2-Rm3) y GND |
| **C21** (Sallen-Key) | 10 nF (2A103J) ∥ 4,7 nF (2A472K) = 14,7 nF | unión Rlb1-Rlb2 y salida del op-amp del SK |
| **Salida del LDO** | 1 µF cerámico (CM105) ∥ 1 µF electrolítico (CE50102) | OUT y GND, pegados al TLV757 |

Cm0 (10 µF electrolítico) tiene ~0 V DC entre sus patas, así que cualquier orientación sirve. Por convención, + hacia la salida del HPF.

## Alimentación y seguridad
- El AFE toma 5 V del pin +5V del STM32N6570-DK (Arduino CN8) → TLV75733P → 3,3 V (`VCC`). La GND es común con el DK.
- Con electrodos puestos, el DK debe ir a **powerbank o a un PC funcionando a batería**. No uses un cargador de pared, porque el paciente queda referido a la red. La simulación ya usa ese peor caso (`CGE=1`).

## Modelos y símbolos
- Símbolos propios en esta carpeta: `INA333.asy` (módulo MCU-333), `TLV75733P.asy`, `ELECTRODO.asy` y `CANAL.asy`. Los op-amps usan `opamp2` de LTspice con Value `TS922`; los diodos, el `1N4148` de la librería de LTspice.
- Modelos: el INA333 es de TI (`models/INA333.LIB` en AC; el equivalente `models/ina_behav.lib` en transitorio). El **TS922 usa el macromodelo oficial de ST** (`models/ts92x.lib`, envuelto en `models/opa_ts922.lib`); el conductual anterior quedó en `models/opa_ts922_behav.lib`. El TLV75733P es conductual (`models/tlv757_behav.lib`). Con el modelo de ST, el punto de operación se resuelve por pseudo-transitorio (`.options gminsteps=0 srcsteps=0`).
