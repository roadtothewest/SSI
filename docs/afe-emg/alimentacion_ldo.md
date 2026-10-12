# Alimentación del AFE sEMG AuraVox: LDO TLV75733P y módulos INA333

Documento autocontenido para revisión. Reúne la alimentación del AFE: el regulador, sus condensadores, cómo se alimentan los módulos INA333 y el presupuesto de corriente. Al final lista lo que todavía no está verificado.

## 1. Contexto
- **AFE:** 3 canales sEMG diferenciales:
  - CH1 submentoniano;
  - CH2 labio inferior;
  - CH3 cuello/laringe.

  Son 7 electrodos en total, incluido el RLD.
- **Cadena por canal:** módulo INA333 (MCU-333 / CJMCU-333, G1 ≈ 19,2) → HPF → MFB (G2 = 125 + LPF) → Sallen-Key (LPF + buffer) → ADC del STM32N6570-DK. La ganancia total es ≈ 2500.
- **Op-amps:** 6 × TS922AIYDT (SOIC-8 en adaptador a DIP-8). Se usan 11 de las 12 secciones: 3 por canal, más el RLD y el buffer de VREF.
- **VREF:** 1,65 V. Sale de un divisor de 2 × 100k con 10 µF, seguido por un TS922 como buffer.
- **Alimentación:** se toma del pin **+5V del STM32N6570-DK** (Arduino CN8) → TLV75733P → riel **VCC = 3,3 V** del AFE. GND es común con el DK.
- **Seguridad:** con electrodos puestos, el DK va a un powerbank o a un PC funcionando a batería, nunca a un cargador de pared.
- **Fuentes del proyecto:**
  - esquemático LTspice: `sim/ltspice/AuraVox_AFE.asc` (lo genera `sim/ltspice/tools/make_asc.py`);
  - BoM: `sim/ltspice/tools/make_bom_xlsx.py` → `docs/afe-emg/BoM_AFE_AuraVox*.xlsx`;
  - notas: `sim/ltspice/README.md`.

## 2. Hay dos LDO distintos (fuente de confusión)
```
DK +5V ──► [TLV75733P, LDO del AFE] ──► 3,3 V (VCC) ──┬──► 6 × TS922
           IN = 5 V      OUT = 3,3 V                  │
                                                      └──► pin "3.3V" de cada módulo INA333
                                                            │
                     módulo INA333:  VCC ──► [LDO pequeño del módulo] ──► "3.3V" ──► INA333
                                     (sin conectar)  (no se usa)
```
- **TLV75733P:** es el LDO que se suelda en el perfboard. Recibe 5 V del DK y entrega 3,3 V a todo el AFE.
- **LDO del módulo INA333:** cada módulo trae uno pequeño en SOT-23, con entrada en el pin VCC y salida en el pin "3.3V". **No se usa.** El riel de 3,3 V del AFE entra directo por el pin "3.3V".

## 3. TLV75733P (TI), el LDO del AFE
- LDO de **3,3 V fijos** y hasta 1 A, en encapsulado SOT-23-5 (DBV), código de pedido `TLV75733PDBVR` (Global Electrónica, 014-75733).
- **No se ajusta:** no lleva resistencias para fijar la tensión de salida.
- Pines DBV según TI (**verificar con el datasheet antes de soldar**):

| Pin | Nombre | Conexión |
|---|---|---|
| 1 | IN | +5 V del DK |
| 2 | GND | GND |
| 3 | EN | **Unido a IN.** No puede quedar flotando, porque el LDO podría no encender. |
| 4 | NC | Sin conectar |
| 5 | OUT | Riel VCC de 3,3 V |

### Condensadores
| Dónde | Componente | Notas |
|---|---|---|
| IN ↔ GND | 1 µF electrolítico CE50102 (`CLDOI`) | Cerca del pin 1. El + va a IN. |
| OUT ↔ GND | **1 µF cerámico X7R CM105** | **Obligatorio**, pegado a los pines 5 y 2 (< 5 mm). El TLV757 está pensado para cerámico a la salida (≥ 0,47 µF efectivos); con un electrolítico solo puede oscilar. |
| OUT ↔ GND | 1 µF electrolítico CE50102 (`CLDOO`) | Opcional, en paralelo con el cerámico. El + va a OUT. |
| VCC ↔ GND | 10 µF CE50103 (`CBULK`) | Bulk del riel, donde se reparte a los INA y TS922 |

**Discrepancia conocida:** el `.asc` de LTspice tiene un solo condensador de 1 µF en OUT (`CLDOO`). El cerámico CM105 en paralelo figura en la BoM (fila "CLDOO cer.") y en el README, pero no en el esquemático.
- En la simulación no influye: el modelo del LDO (`models/tlv757_behav.lib`) es conductual y no reproduce la estabilidad del lazo.
- Pendiente: agregar `CLDOO2` = 1 µF en paralelo en `make_asc.py`, para que el esquemático coincida con lo que se suelda.

### Montaje en perfboard (sin adaptador SOT-23 → DIP)
1. Pegar el chip en el centro de un cuadro de 3×3 agujeros, con una gota mínima de cianoacrilato y las patas hacia arriba, sin tocar pads.
2. Estañar las 5 patas con flux y punta fina.
3. Soldar a cada pata un alambre corto (una pata cortada de resistencia, o cable de 24–30 AWG) hacia agujeros vecinos.
4. Hacer el puente EN–IN por el lado del perfboard, nunca por encima de la pata de GND.
5. Soldar el CM105 directo de la pata OUT a la pata GND, con patas mínimas. Después los electrolíticos.
6. Revisar con lupa que no haya puentes entre patas.

**Ojo:** si el chip queda boca abajo ("dead bug"), el orden de los pines se invierte en espejo. Guiarse por la marca del pin 1.

### Prueba antes de conectar el resto
Sin INA, sin op-amps y sin electrodos:
1. **Sin alimentar:** IN–GND y OUT–GND no deben estar en cortocircuito. Es normal que la lectura suba lentamente mientras se cargan los condensadores.
2. **Con los 5 V del DK:** IN ≈ 5 V, EN ≈ 5 V y **OUT = 3,25–3,35 V**.
3. **Temperatura:** no debe calentarse.
4. **Diagnóstico:** si OUT ≈ 0 V, revisar el puente EN–IN; si OUT ≈ 5 V o da un valor raro, revisar la orientación del chip.

## 4. Alimentación de los módulos INA333 (MCU-333)
| Pin del módulo | Conexión |
|---|---|
| 3.3V | Riel VCC de 3,3 V (salida del TLV75733P) |
| GND | GND |
| **VCC** | **Sin conectar** (o al mismo riel de 3,3 V). **Nunca a GND.** |
| VREF | VREF con buffer (seguidor TS922) |
| VIN+, VIN− | Electrodos (a través de las protecciones y el filtro RFI) |

- **Por qué VCC nunca va a GND:** VCC es la entrada del LDO del módulo, y el riel de 3,3 V llega a su salida. Con VCC a GND, el riel se descarga a tierra a través de ese LDO: baja el riel y puede dañar el regulador.
- **Con VCC flotando**, ese pin queda en ~2,7 V y no circula corriente.
- **Con VCC a 3,3 V**, el LDO del módulo queda con la misma tensión a la entrada y a la salida, y no conduce. Las dos opciones son seguras.
- **Modificación ya definida para el módulo** (fuera del alcance de este documento):
  - trimmer de RG reemplazado por 2,7k + 2,7k en serie, manteniendo la de 100 Ω de fábrica → RG ≈ 5,5k, G1 ≈ 19,2;
  - resistencia de sensado del modo común (RSM) de 620k desde el punto medio de RG hacia el sumador del RLD.

## 5. Presupuesto de corriente del riel de 3,3 V
| Carga | Típico | Máximo |
|---|---|---|
| 6 × TS922 (datasheet ST: ICC total 2 mA típ. / 3 mA máx. por chip, sin carga, con Vout = VCC/2) | 12 mA | 18 mA (19,2 en todo el rango de temperatura) |
| 3 × INA333 (50 µA típ. / 75 µA máx.) | 0,15 mA | 0,23 mA |
| Divisores de REF de 10k + 10k en los 3 módulos | 0,5 mA | 0,5 mA |
| Divisor de VREF del AFE (2 × 100k) | 0,02 mA | 0,02 mA |
| Cargas de las salidas de los op-amps y del RLD (resistencias de ≥ 1k) | < 1 mA | ~1 mA |
| **Total** | **~14 mA** | **~20 mA** |

- **Capacidad:** el TLV75733P entrega 1 A, así que se usa menos del 2 %.
- **Disipación:** (5 − 3,3) V × 20 mA ≈ 35 mW. Con θJA ≈ 200 °C/W, sube ≈ +7 °C.
- **Dropout:** el TLV757 cae ~425 mV a 1 A; a 20 mA, menos de 20 mV. Mantiene los 3,3 V aunque los 5 V del USB bajen a ~4,5 V.
- **El INMP441 no va en este riel:** se alimenta desde los 3,3 V del DK, junto a sus pines I2S/SAI, para que su ruido digital no entre al riel analógico.
- **LED del módulo INA333:** si trae uno encendido, suma 1–3 mA por módulo. No se verificó si existe. Se puede desoldar.
- **Prueba en banco:** amperímetro en serie en el +5 V del DK, con todo montado y sin electrodos.
  - Se espera **~15–25 mA**.
  - Más de ~50 mA indica un cortocircuito o un op-amp oscilando.

## 6. Pendientes y supuestos por verificar
1. **Pinout del TLV75733P DBV:** 1 IN, 2 GND, 3 EN, 4 NC, 5 OUT. Confirmarlo con el datasheet de TI (SBVS320) antes de soldar.
2. **LDO del módulo INA333:** se supone que es SOT-23 con entrada en VCC y salida en "3.3V". Medir la continuidad con el multímetro, y que el pin 7 (V+) del INA333 llegue al pin "3.3V".
3. **LED en el módulo INA333:** ver si existe y de qué riel cuelga.
4. **Esquemático LTspice:** agregar `CLDOO2` (1 µF cerámico) en paralelo con `CLDOO`.
5. **Corriente real:** medirla con el amperímetro (sección 5).
6. **Capacidad del pin +5V del DK:** no se consultó en el manual del DK. Con ~20 mA no se espera problema.
