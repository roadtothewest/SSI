# Simulación LTspice del AFE sEMG AuraVox

## Abrir y correr
```bash
cd ~/SSI/sim/ltspice
wine "C:\Program Files\ADI\LTspice\LTspice.exe" AuraVox_AFE.asc
```
Run (~6 min). El Run hace 2 pasos: **paso 1 sin RLD** (referencia pasiva por 390k) y **paso 2 con RLD**.
- Resultados numéricos: *View > SPICE Error Log* (`CM_cuerpo_Vpp`, `ADCk_rafaga/reposo_mVrms`, `SNRk_salida_dB`, `PINk_min/max_V`, `sEMGk_uVrms`).
- Para ver las 8 etapas de un canal: doble clic en un bloque `CANAL`.

## Cómo se simula cada entrada diferencial (todo en LTspice)
La fuente `BINk` va entre el cuerpo (`BODY`) y el electrodo + del canal k. Su valor es la suma de:

| Componente | Fuentes | Detalle |
|---|---|---|
| sEMG útil | `BWk` → `EFk` → `BSEMk` | Ruido blanco `white()`, filtrado por un pasabanda Laplace centrado en 90 Hz y multiplicado por la envolvente de habla `VENV`: ráfagas de 170 ms cada 420 ms, 5 % de tono en reposo. Amplitud `AS1..AS4` = 50/30/40/25 µV RMS (submentoniano, platisma, labio inferior, laringe) |
| Movimiento | `white(3*time)` | 500 µV RMS, < 10 Hz |
| ECG | `VECG` | PQRST que se repite a 72 lpm, con pico `GE1..GE4` = 120/300/50/250 µV (más fuerte en el cuello) |
| Ruido blanco | `white(2e4*time)` | 20 µV RMS |

Además actúan, ya incluidos en el banco:
- la red de 311 V acoplada al cuerpo, con el circuito a tierra por USB (peor caso);
- la media celda DC de cada electrodo;
- el desbalance 51k‖47n (IEC 60601-2-27).

`KN=0` quita todo el ruido.

## Salidas al STM32N6570-DK (UM3300)
`ADCk` pasa por el modelo del amplificador de la placa (3,3 V → 1,8 V, ganancia `GDK`; verificar en el esquemático MB1939) y por el muestreo del ADC, y llega a `pink`.

| Canal | Pin Arduino | Pin del MCU | Canal ADC |
|---|---|---|---|
| CH1 | A1 | PA9 | ADC12_INP10 |
| CH2 | A2 | PA10 | ADC12_INP11 |
| CH3 | A3 | PA12 | ADC12_INP13 |
| CH4 | A4 | PF3 | ADC12_INP16 |

No usar A0 (comparte ADC con USB1 ISENSE) ni A5 (compartido con STMod+).

## Cambiar componentes
Recuadro **VALORES** de la hoja: un `.param` por componente, que usan las 4 copias del canal. La BoM está en el recuadro inferior y en `docs/afe-emg/BoM_AFE_AuraVox*.xlsx`; se regeneran con `python3 tools/make_bom_xlsx.py && python3 tools/make_asc.py && python3 tools/check_asc.py`. `check_asc.py` también falla si queda algún pin o cable abierto.
