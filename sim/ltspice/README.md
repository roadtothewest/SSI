# Simulación LTspice del AFE sEMG AuraVox (3 canales, TS922 + INA333)

## Abrir y correr
```bash
cd ~/SSI/sim/ltspice
wine "C:\Program Files\ADI\LTspice\LTspice.exe" AuraVox_AFE.asc
```
Run (~3 min). El Run hace 2 pasos: **paso 1 sin RLD** (referencia pasiva por 390k) y **paso 2 con RLD**.
- Resultados numéricos: *View > SPICE Error Log* (`CM_cuerpo_Vpp`, `ADCk_rafaga/reposo_mVrms`, `SNRk_salida_dB`, `PINk_min/max_V`, `sEMGk_uVrms`).
- Para ver las 7 etapas de un canal (ESD → RFI → INA333 ×20 → HPF 20 Hz → LPF MFB ×25 → LPF Sallen-Key → bucket): doble clic en un bloque `CANAL`.

## Cómo se simula cada entrada diferencial (todo en LTspice)
La fuente `BINk` va entre el cuerpo (`BODY`) y el electrodo + del canal k. Su valor es la suma de:

| Componente | Fuentes | Detalle |
|---|---|---|
| sEMG útil | `BWk` → `EFk` → `BSEMk` | Ruido blanco `white()`, filtrado por un pasabanda Laplace centrado en 90 Hz y multiplicado por la envolvente de habla `VENV`: ráfagas de 170 ms cada 420 ms, 5 % de tono en reposo. Amplitud `AS1..AS3` = 50/40/25 µV RMS (submentoniano, labio inferior, laringe) |
| Movimiento | `white(3*time)` | 500 µV RMS, < 10 Hz |
| ECG | `VECG` | PQRST que se repite a 72 lpm, con pico `GE1..GE3` = 120/50/250 µV (más fuerte en el cuello) |
| Ruido blanco | `white(2e4*time)` | 20 µV RMS |

Además actúan, ya incluidos en el banco:
- la red de 311 V acoplada al cuerpo, con el circuito a tierra por USB (peor caso);
- la media celda DC de cada electrodo;
- el desbalance 51k‖47n (IEC 60601-2-27).

`KN=0` quita todo el ruido.

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
- El LPF es de 4º orden: MFB + Sallen-Key. La ganancia es fija (G1 20 × G2 25 = ~500); el ajuste por sitio se hace en el firmware.

## Alimentación y seguridad
- El AFE toma 5 V del pin +5V del STM32N6570-DK (Arduino CN8) → TLV75733P → 3,3 V (`VCC`). La GND es común con el DK.
- Con electrodos puestos, el DK debe ir a **powerbank o a un PC funcionando a batería**. No uses un cargador de pared, porque el paciente queda referido a la red. La simulación ya usa ese peor caso (`CGE=1`).

## Modelos y símbolos
- Símbolos propios en esta carpeta: `INA333.asy` (módulo MCU-333), `TLV75733P.asy`, `ELECTRODO.asy` y `CANAL.asy`. Los op-amps usan `opamp2` de LTspice con Value `TS922`; los diodos, el `1N4148` de la librería de LTspice.
- Modelos: el INA333 es de TI (`models/INA333.LIB` en AC; el equivalente `models/ina_behav.lib` en transitorio). El TS922 y el TLV75733P son conductuales (`models/opa_ts922.lib`, `models/tlv757_behav.lib`) con los datos de sus datasheets. Si se descargan los modelos oficiales de ST y TI, se cambia el `.include`.
