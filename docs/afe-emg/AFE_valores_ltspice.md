# AFE sEMG: valores de componentes y BoM para simular en LTspice

**Fecha:** 26 sep 2026. **Base:** esquemático de pizarra "AuraVox – AFE" (26 sep) + `CONTEXTO_CLAUDE.md` §4–6.
**Arquitectura:** 4 × (1 INA333 + 5 op-amps) + 2 op-amps compartidos (VREF, RLD) = 4 INA333 + 22 op-amps → **6 × MCP6004** (2 op-amps libres).

Leyenda: **[DS]** verificado en datasheet del repo (`datasheets/INA333.pdf` SBOS445C, `datasheets/MCP6004.pdf` DS20001733L, `datasheets/AD8232.PDF`) · **[CÁLCULO]** calculado aquí, las fórmulas están en §5 · **[MEMORIA]** sin verificar · **[SIM]** lo decide la simulación.

Alimentación: 3,3 V única, VREF = 1,65 V.

---

## 1. Elección de circuitos integrados

### 1.1 INA: INA333 (decisión del usuario)

Datos [DS] relevantes para este diseño:

| Parámetro | Valor | Consecuencia |
|---|---|---|
| Alimentación | 1,8–5,5 V | OK a 3,3 V |
| Ganancia | G = 1 + 100 kΩ/RG; internamente, 2 × 50 kΩ en la primera etapa y 4 × 150 kΩ en el amplificador diferencial | RG entre los pines 1 y 8, que están en las entradas inversoras de A1 y A2 → **el punto medio de RG partido en dos es Vcm** (ver §3) |
| CMRR (DC–60 Hz) | 100 dB mín. para G ≥ 10 | G1 = 10 no pierde CMRR respecto de G1 = 20 |
| Ruido | 50 nV/√Hz (G = 100), sin 1/f (chopper) | Ruido 20–500 Hz ≈ 1,1 µVrms |
| Ib | ±200 pA máx. | Con 101 kΩ en serie: ≈ 20 µV, despreciable |
| Rango de entrada | V– + 0,1 a V+ – 0,1 V | |
| Salida | a 50 mV de los rieles | ±1,6 V útiles alrededor de VREF |
| **REF** | R_IN = 300 kΩ; "debe excitarse con baja impedancia"; **≤ 15 Ω de resistencia parásita** para mantener el CMRR | REF va directo a la salida del seguidor de VREF, sin R serie ni RC |
| Pines RG | "evitar más de unos pocos pF parásitos; igualar parásitos en ambos pines" | Condiciona cómo cablear el punto medio (ver §3) |
| Chopper | 350 kHz, auto-cero cada 8 µs; 100 µs para alcanzar el Vos especificado al encender | Revisar el rizado en el osciloscopio (ver T12) |
| Encapsulado | Solo VSSOP-8 / WSON-8 | **Perfboard: adaptador MSOP-8 → DIP-8** |
| SPICE | Nota del datasheet: "el modelo no converge sin un resistor entre los pines RG" | En LTspice poner siempre RG |

### 1.2 Op-amp: **MCP6004-I/P** (PDIP-14)

| Parámetro | MCP6004 [DS] | Requisito del diseño |
|---|---|---|
| Alimentación | 1,8–6,0 V | 3,3 V |
| Entrada/salida | Rail-to-rail; entrada V_SS–0,3 a V_DD+0,3 V; salida a 25 mV de los rieles | Seguidores y SK con señal centrada en 1,65 V ± 1,6 V |
| GBW / margen de fase | 1 MHz / 90°; 45° con 500 pF de carga | SK pasa-bajos a 500 Hz y Q = 1,31: con GBW ≳ 100·f0·Q ≈ 65 kHz [MEMORIA, regla práctica] sobra |
| Vos | ±4,5 mV máx. | Todas las etapas posteriores al HPF tienen **ganancia DC 1** (G2 lleva C en serie) ⇒ peor caso ≈ 5 × 4,5 = 22 mV de corrimiento a la salida (1,4 % del rango). Tolerable |
| Ib | 1 pA | Con resistores de hasta 240 kΩ, despreciable |
| Ruido | 28 nV/√Hz @ 1 kHz | Referido a la entrada del INA se divide por G1 = 20 ⇒ 1,4 nV/√Hz, despreciable frente a los 50 nV/√Hz del INA333 |
| Encapsulado | **PDIP-14**, SOIC, TSSOP | Soldable directo en perfboard, sin adaptador |
| Modelo | Microchip publica macromodelo SPICE | Importable en LTspice [MEMORIA: formato compatible] |

**Por qué basta un op-amp de propósito general:** el ruido y el CMRR los fija el INA333. Después de G1 = 20, el ruido del op-amp no aporta, y como G2 está acoplada en AC, el offset tampoco se amplifica. Lo que importa es rail-to-rail a 3,3 V, Ib en pA (resistores de 50–240 kΩ), DIP y precio.

**Alternativa en DIP, si hiciera falta:** MCP6024-I/P (misma patilla, 10 MHz, menor ruido y offset) [MEMORIA, verificar el datasheet antes de comprar]. Solo se justifica si la simulación o el banco muestran pasa-banda del chopper del INA333 por el SK (T12). **No usar TL074/TL074H** (no es rail-to-rail y el TL074H exige ≥ 4,5 V) ni LM324 (la salida no llega al riel superior).

### 1.3 Asignación de op-amps (6 × MCP6004)

| IC | A | B | C | D |
|---|---|---|---|---|
| U1 (CH1) | HPF | G2 | LPF A | LPF B |
| U2 (CH2) | HPF | G2 | LPF A | LPF B |
| U3 (CH3) | HPF | G2 | LPF A | LPF B |
| U4 (CH4) | HPF | G2 | LPF A | LPF B |
| U5 | Buffer CH1 | Buffer CH2 | Buffer CH3 | Buffer CH4 |
| U6 | Seguidor VREF | Integrador RLD | libre | libre |

Op-amps libres: + a VREF y salida a – (seguidor), para que no oscilen ni consuman de más. Uno puede usarse como segundo seguidor de VREF si los 4 REF + 4 Ra + 4 Cg cargan demasiado al primero (T1).

---

## 2. Valores por bloque (nombres de la pizarra)

### 2.1 Protección ESD + filtro RFI

| Componente | Pizarra | **Propuesta** | Motivo |
|---|---|---|---|
| R serie (IN±) | 100 k | **100 kΩ 1 %** (se mantiene) | Falla con la entrada del INA a riel: 3,3 V/100 k = 33 µA. Cumple el límite de condición de falla simple de IEC 60601-1 (50 µA) [MEMORIA], pero no la guía del AD8232 de < 10 µA [DS p.19], que pediría 330 kΩ. 330 kΩ sube el ruido a 2,3 µVrms y obliga a bajar los condensadores RFI → **[SIM] T9** |
| Diodos clamp | 4 por canal a VCC/GND | **1N4148** (THT) o BAV199 (SOT-23, adaptador) | La fuga de 1N4148 a ~1,6 V de polarización inversa es de nA [MEMORIA] ⇒ < 0,5 mV sobre 100 k, y el HPF la elimina. Su capacitancia (~2–4 pF [MEMORIA]) se suma a Ccm |
| R 1 k (post clamp) | 1 k | **1 kΩ 1 %** | Aísla el clamp del INA; se suma a la R del filtro |
| **Ccm** (470p a GND) | 470 p | **47 pF C0G 5 %** | Ver H1: con 470 p el polo de modo común queda en 3,35 kHz y la conversión MC→MD a 50 Hz (10 %) es −56,5 dB. Con 47 p/5 %: 33,5 kHz y −82,5 dB [CÁLCULO]. Además 3,35 kHz metería un polo en el lazo del RLD, cerca de su cruce de 1 kHz (§2.8) |
| **Cd** (diferencial) | sin valor | **100 pF C0G** | f_diff = 1/(2π·101k·(2Cd+Ccm)) = **6,4 kHz**; −0,03 dB a 500 Hz. Con el Cd = 4,7 nF del repo quedaba en **160 Hz**, dentro de la banda sEMG |

### 2.2 INA333 (G1)

| Componente | Valor | Resultado |
|---|---|---|
| RG | **2 × 2,61 kΩ 0,1 %** en serie (punto medio → RLD, §3) | G1 = 1 + 100k/5,22k = **20,16** |
| REF | Directo a la salida del seguidor de VREF | — |
| Desacople | 100 nF X7R en V+ pegado al pin | [DS] §10 |

Rango DC diferencial admisible (offset de electrodos): ±1,6 V/20,16 = **±79 mV** [CÁLCULO]. Si T3 muestra offsets mayores: **G1 = 10** (RG = 2 × 5,49 kΩ ⇒ 10,1) y G2 = 50 (§2.4), sin pérdida de CMRR (100 dB mín. a G ≥ 10 [DS]).

### 2.3 HPF Sallen-Key 2º orden, ganancia 1, Q = 0,707

Topología de la pizarra: C–C en serie, **R1** del nodo central a la salida y **Ra** de la entrada + a VREF.

| Componente | Valor |
|---|---|
| C, C | **100 nF film (PET/MKT) 5 %**, no X7R (no lineal, deriva) |
| R1 (nodo central → salida) | **56,2 kΩ 1 %** |
| Ra (entrada + → VREF) | **113 kΩ 1 %** |

f0 = 1/(2πC√(R1·Ra)) = **19,97 Hz**; Q = ½√(Ra/R1) = **0,709** [CÁLCULO]. Ra a VREF fija la salida en 1,65 V DC.

### 2.4 G2 no inversor, G_AC = 25 y G_DC = 1

| Componente | Valor |
|---|---|
| Rf | **240 kΩ 1 %** |
| Rg | **10 kΩ 1 %** |
| Cg | **10 µF X7R** (o film si hay) |

G_AC = 1 + 240k/10k = **25**. El polo del bloqueo DC está en 1/(2π·Rg·Cg) = **1,6 Hz**, que resta 0,03 dB a 20 Hz [CÁLCULO].

**Cambio respecto de la pizarra: retornar Cg a VREF, no a GND.** Tres razones:
1. Con Cg a GND, el condensador queda con 1,65 V DC. Si es electrolítico, su fuga (µA [MEMORIA]) circula por Rf: 1 µA × 240 kΩ = **0,24 V** de corrimiento a la salida. A VREF queda con ~0 V y la fuga es despreciable, así que sirve un X7R o film sin polaridad.
2. Con Cg a GND, el ruido y el rizado de VREF salen amplificados × 25. A VREF salen × 1.
3. Al encender, la constante de tiempo es la misma (Rg·Cg = 0,1 s).

Si G1 = 10: Rf = 499 kΩ ⇒ G_AC = 50,9 (Cg igual).

### 2.5 LPF A: Sallen-Key, ganancia 1, Q = 0,541 (Butterworth 4º orden, sección 1)

| Componente | Valor |
|---|---|
| R, R | **88,7 kΩ 1 %** |
| C11 (realimentación, a la salida) | **3,9 nF C0G/film 5 %** |
| C12 (a GND) | **3,3 nF C0G/film 5 %** |

Q = ½√(C11/C12) = **0,5436** (+0,4 %); f0 = 1/(2πR√(C11·C12)) = **500,2 Hz** [CÁLCULO].
Alternativa si no hay 3,9/3,3 nF: 12 nF/10 nF con R = 29,4 kΩ (Q 0,548, f0 494 Hz).

### 2.6 LPF B: Sallen-Key, ganancia 1, Q = 1,306 (sección 2)

| Componente | Valor |
|---|---|
| R, R | **54,9 kΩ 1 %** |
| C21 (realimentación) | **15 nF C0G/film 5 %** |
| C22 (a GND) | **2,2 nF C0G 5 %** |

Q = ½√(15/2,2) = **1,3056** (−0,08 %); f0 = **504,6 Hz** [CÁLCULO].
Alternativa: C21 = 6,8 nF, C22 = 1 nF, R = 121 kΩ (Q 1,304, f0 504 Hz). Es más sensible a la capacitancia de entrada del op-amp (6 pF [DS] frente a 1 nF).

Las secciones A y B deben ir en ese orden: primero Q bajo y después Q alto [MEMORIA, práctica estándar para reducir el sobreimpulso interno]. El error de f0 entre ambas (0,9 %) es menor que la tolerancia de los condensadores.

### 2.7 Buffer + "bucket" al ADC

| Componente | Valor |
|---|---|
| Buffer | Seguidor MCP6004 |
| R serie | **100 Ω 1 %** (aísla el op-amp de la C: el MCP6004 conserva 45° de margen con 500 pF [DS], y la R lo desacopla del todo) |
| C bucket | **1 nF C0G**, pegado al pin del ADC |

τ = 100 ns. **TODO:** Csh y tiempo de muestreo mínimo del ADC del STM32N657, para fijar el sample time. La regla es que el bucket entregue la carga al instante y el buffer la reponga antes de la próxima conversión del mismo canal (125 µs a 8 kHz), lo que sobra.

### 2.8 VREF (con bypass)

| Componente | Valor |
|---|---|
| RA, RA | **100 kΩ 1 %** |
| C (en el nodo del divisor, entrada del seguidor) | **10 µF** |
| Seguidor | U6A |

Filtro del divisor: 1/(2π·50k·10µ) = **0,32 Hz**. **Sin condensador ni R serie en la salida del seguidor**: el REF del INA333 exige ≤ 15 Ω [DS], y una C grande directa en la salida del MCP6004 compromete la estabilidad (45° con 500 pF [DS]). Cablear en estrella desde la salida hacia los 4 REF.

Pendiente H6: si el ADC usa 3,3 V del DK y el AFE otro regulador, VREF no queda centrado en el rango del ADC. Lo ideal es derivar el divisor de la misma referencia que el ADC.

### 2.9 RLD (integrador), **cambio de sensado**

| Componente | Pizarra | **Propuesta** |
|---|---|---|
| Sensado | 100 k desde cada uno de los 8 electrodos (nodos A/B) | **R_avg = 604 kΩ** (E96) desde el **punto medio de RG** de cada uno de los 4 INA |
| C_int | sin valor | **1 nF C0G** (barrer 1–4,7 nF en T5) |
| R en paralelo con C_int | sin valor | **10 MΩ** (limita la ganancia DC a ~36 dB, para que el integrador no se vaya al riel por offsets) [SIM] |
| Entrada + | VREF | VREF |
| Rlimit | sin valor | **390 kΩ** ⇒ 3,3 V/390k = 8,5 µA |

R efectiva de entrada: 604k/4 = 151 kΩ. Con 1 nF: cruce a 1,05 kHz y ganancia de lazo ≈ **26,4 dB a 50 Hz**, igual que el estilo AD8232 [DS p.17] [CÁLCULO].

Rlimit se dimensiona para condición **normal**: con un electrodo suelto, el integrador se va al riel en operación normal, así que debe quedar bajo 10 µA. Ojo: C_cuerpo–tierra (~200 pF [MEMORIA]) con 390 kΩ pone un polo en ~2 kHz, cerca del cruce. Por eso hay que barrer C_int en T5.

---

## 3. Por qué cambiar el sensado del RLD (hallazgo H2)

En la pizarra hay un resistor de 100 kΩ desde cada electrodo (nodos A/B, antes de la R serie) hasta la entrada inversora del integrador, que es tierra virtual en VREF. Cada electrodo queda cargado con 100 kΩ a tierra AC:

- **Conversión de modo común a diferencial:** V_A = Vcm·100k/(100k + Ze_A). Con un desbalance de impedancia de electrodo ΔZe, la diferencial resultante ≈ Vcm·ΔZe/100k. Con ΔZe = 10 kΩ, **CMRR efectivo ≈ 20 dB**, sin importar los 100 dB del INA333 [CÁLCULO].
- **Atenuación de señal:** Ze/(Ze + 100k). Con electrodos de 50–100 kΩ a baja frecuencia se pierden entre 3,5 y 6 dB.

**Punto medio de RG:** los pines RG están en las entradas inversoras de A1 y A2, que por realimentación siguen a VIN− y VIN+ [DS, diagrama de bloques]. Partiendo RG en dos mitades iguales, el punto medio vale (VIN+ + VIN−)/2 = Vcm, **ya buffereado por A1/A2**, así que no carga los electrodos. Es el circuito ECG clásico de INA128/AD620 [MEMORIA]. Con 4 canales hay 4 puntos medios, cuyo promedio es el mismo Vcm que daría promediar los 8 electrodos.

Efectos secundarios [CÁLCULO]:
- La corriente que sale del punto medio (ΔVcm/604k) se reparte por igual entre las dos mitades de RG y las 50 kΩ internas. Es modo común y A3 la rechaza, así que la ganancia diferencial no cambia.
- Cablear el R_avg de 604 kΩ **pegado al punto medio** y llevar el cable largo del lado del integrador (tierra virtual, baja impedancia). El datasheet pide pocos pF y simétricos en los pines RG [DS].
- No verificado: si el punto medio lleva rizado del chopper de 350 kHz. El integrador lo filtra, pero hay que mirarlo (T12).

Esto **contradice la sección 4.6 de la spec nueva** ("promedio de los 8 electrodos mediante red resistiva"). La simulación T4 debe comparar ambas opciones con electrodos desbalanceados antes de decidir.

---

## 4. Resumen del BoM del AFE (4 canales)

| Ítem | Cant. | Valor / parte | Tipo |
|---|---|---|---|
| INA333AIDGKR | 4 | VSSOP-8 | + 4 adaptadores MSOP-8→DIP-8 |
| MCP6004-I/P | 6 | PDIP-14 | + 6 zócalos DIP-14 (opcional) |
| R 100 kΩ | 8 + 2 | serie IN± ; divisor VREF | Película metálica 1 % |
| R 1 kΩ | 8 | post-clamp | 1 % |
| R 2,61 kΩ | 8 | RG partido | **0,1 %** (o 1 % pareados en banco) |
| R 113 kΩ | 4 | Ra HPF | 1 % |
| R 56,2 kΩ | 4 | R1 HPF | 1 % |
| R 240 kΩ | 4 | Rf G2 | 1 % |
| R 10 kΩ | 4 | Rg G2 | 1 % |
| R 88,7 kΩ | 8 | LPF A | 1 % |
| R 54,9 kΩ | 8 | LPF B | 1 % |
| R 100 Ω | 4 | bucket | 1 % |
| R 604 kΩ | 4 | R_avg RLD | 1 % |
| R 10 MΩ | 1 | paralelo C_int | 5 % |
| R 390 kΩ | 1 | Rlimit RLD | 1 % |
| C 47 pF | 8 | Ccm | C0G 5 % |
| C 100 pF | 4 | Cd | C0G 5 % |
| C 100 nF | 8 | HPF | **Film** 5 % |
| C 10 µF | 4 + 1 | Cg G2; VREF | X7R (o film) |
| C 3,9 nF / 3,3 nF | 4 / 4 | LPF A | C0G o film 5 % |
| C 15 nF / 2,2 nF | 4 / 4 | LPF B | C0G o film 5 % |
| C 1 nF | 4 + 1 | bucket; C_int | C0G |
| C 100 nF | 10 | desacople (1 por IC) | X7R |
| C 10 µF | 1–2 | bulk riel AFE | X7R/tántalo |
| Diodos | 16 | 1N4148 (o 8 × BAV199) | |

Total: ~74 resistencias y ~60 condensadores. Comprar ~20 % extra de cada valor para parear canales.

---

## 5. Fórmulas usadas (para revisar)

- RFI diferencial: f_d = 1/(2π·R·(2Cd + Ccm)), con R = Rs + 1k = 101 kΩ por línea.
- RFI modo común: f_cm = 1/(2π·R·Ccm). Conversión MC→MD a baja frecuencia ≈ 2π·f·R·ΔCcm.
- HPF SK con C iguales y ganancia 1: ω0 = 1/(C√(R1·Ra)), Q = ½√(Ra/R1).
- LPF SK con R iguales y ganancia 1: ω0 = 1/(R√(C11·C12)), Q = ½√(C11/C12) (C11 = realimentación).
- G2 con C: G(s) = 1 + Rf/(Rg + 1/(sCg)).
- Ruido referido a la entrada, 20–500 Hz: Rs → √(4kT·202k) = 57,8 nV/√Hz ⇒ 1,27 µVrms; INA333 50 nV/√Hz ⇒ 1,10 µVrms; **total ≈ 1,7 µVrms**.
- G_total = 20,16 × 25 = **504**. LSB del ADC de 12 bit referido a la entrada = 0,806 mV/504 = **1,6 µV**. Recorte a ±1,6 V/504 = **±3,2 mV pico** en la entrada.
- Atenuación 4º orden Butterworth (f0 ≈ 502 Hz): −24 dB a 1 kHz, −48 dB a 2 kHz, **−72 dB a 4 kHz** (Nyquist con fs = 8 kHz, igual al rango de 12 bit; H5).
- HPF a 50 Hz: −0,11 dB; a 10 Hz: −12,3 dB.

Los números se confirmaron con un script Python y con LTspice (§7).

---

## 5b. Verificación del diseño propuesto por Gemini (26 sep)

| Punto | Gemini | Veredicto |
|---|---|---|
| G1 ≈ 20, tolera ±75 mV | RG 5,23 kΩ ⇒ 20,12 | **Correcto** [DS, tabla 1]: rango ±80 mV. Pero Gemini también dice que el offset de electrodos puede llegar a ±300 mV (dato de diseño del AD8232 [DS p.16]); con ±300 mV haría falta G1 ≤ 5,3. Lo decide T3 |
| AD8226, RG 2,61 k | G = 19,93 | Ecuación OK [MEMORIA]. El pinout "1,8 RG / 2 −IN / 3 +IN" es el del INA333 [DS]; el AD8226 tiene otro orden [MEMORIA]. Verificar en su datasheet si se usa |
| Pinout INA333 | 1,8 RG · 2 −IN · 3 +IN · 4 V− · 5 REF · 6 OUT · 7 V+ | **Correcto** [DS] |
| **Rs 330 kΩ + Ccm 470 pF + Cdiff 4,7 nF** | "Cdiff ≈ 10·Ccm" | **Incorrecto en conjunto (H1).** La regla vale si la R del filtro es de pocos kΩ, pero Rs está en serie: f_diff = **49 Hz**, con **−20 dB a 500 Hz**. Con Rs 100k: 160 Hz (−10 dB a 500 Hz) |
| Corrección | — | Rs 100k: Ccm 47 pF + Cd 100 pF ⇒ 6,2 kHz. **Rs 330k: sin Ccm discreto, Cd 47 pF ⇒ 4,7 kHz** (el INA333 ya trae filtro RFI de 8 MHz [DS]); ruido de 1,7 a 2,5 µVrms |
| Clamps BAV199/FJH1100 | | Correcto [DS AD8232 p.19] |
| HPF | 100n, R1 56,2k (nodo→salida), R2 113k (V+→VREF) | **Correcto** (tras su propia corrección) |
| **G2 = 1 + 24k/1k acoplada en DC** | | **Peor que la pizarra**: multiplica ×25 los offsets del HPF y de G2, hasta ±225 mV con MCP6004. Se mantiene G_DC = 1 con Cg (§2.4) |
| LPF 28,7k 12n/10n; 25,5k 33n/4,7n | | OK: 506 Hz Q 0,548; 501 Hz Q 1,325. Difiere de §2.5–2.6 en < 0,25 dB. Cualquiera de los dos juegos sirve |
| Bucket 1 kΩ + 100 pF | | Mismo τ que 100 Ω + 1 nF, pero la patada del S/H es 10× mayor (5 % vs 0,5 %). Se prefiere 100 Ω + 1 nF |
| Aislamiento galvánico con red | | **Correcto** (H7) |
| RLD sumando electrodos con R de cientos de kΩ "sin degradar la impedancia" | | **Incorrecto** (§3). El AD8232 sensa detrás de la etapa de entrada: "the common-mode signal ... is derived from the transconductance amplifier, GM1. It is then connected to the inverting input of A2 through a 150 kΩ resistor" [DS p.17] |
| Integrador con R alta en paralelo, R de seguridad 390k–1M | | Correcto; coincide con §2.9 |

---

## 6. Plan de simulación LTspice (adaptado de `CONTEXTO_CLAUDE.md` §6.2)

Modelos: INA333 (PSpice de TI; si LTspice no lo importa, INA de 3 op-amps ideales con 2 × 50 kΩ y 4 × 150 kΩ, la topología [DS], y desajuste de 0,01–0,1 % en los 150 kΩ para un CMRR de 80–100 dB). MCP6004: macromodelo de Microchip. Electrodo: R ∥ C + fuente DC de media celda. Cuerpo: fuente de 50 Hz de modo común (0,1–10 V), C cuerpo–tierra ~200 pF [MEMORIA].

| # | Prueba | Criterio |
|---|---|---|
| T1 | `.op` | Todos los nodos de señal ≈ 1,65 V. VREF estable con las 12 cargas |
| T2 | `.ac` 0,1 Hz–100 kHz | Banda 20–500 Hz, G ≈ 504 (54 dB), −72 dB a 4 kHz |
| T3 | Offset DC de electrodo 5/15/50/80/150 mV | INA sin saturar; decide G1 = 20 vs 10 |
| T4 | 50 Hz MC + desbalance 51 kΩ ∥ 47 nF | **Sensado 8 × 100k sobre electrodos vs punto medio de RG**; Ccm 470p vs 47p |
| T5 | Estabilidad del lazo RLD | Barrer C_int 1–4,7 nF y Rlimit 330k–1M con modelo de cuerpo. Sobreimpulso < 30 % |
| T6 | Ráfaga de 100 mV | Tiempo de recuperación (G2 AC-coupled: τ = 0,1 s) |
| T7 | 50 µV y 3 mV a 100 Hz | Sin recorte |
| T8 | Tonos 3,5–4,5 kHz, fs 8 kHz | Alias < 1 LSB |
| T9 | Falla: IN del INA a 3,3 V | Corriente al electrodo (100k: 33 µA; 330k: 10 µA) |
| T10 | Electrodo suelto | Salida al riel ⇒ umbral por software |
| T11 | Monte Carlo (C 5 %, R 1 %, RG 0,1 %) | Dispersión de f0/Q/ganancia entre canales |
| T12 | Tono de 350 kHz en la salida del INA (chopper) | Cuánto atraviesa el SK (feedthrough) hasta el ADC |

Decisiones que cierra la simulación: G1 (20/10) · Rs (100k/330k) · sensado del RLD · C_int y Rlimit · bucket.

---

## 7. Resultados LTspice (26–27 sep, `sim/ltspice/`)

Modelos: INA333 = macromodelo TI (SBOM382, Final 1.3). Op-amp = MCP6004 **conductual** (`models/opa_behav.lib`: GBW 1 MHz, Aol 112 dB, SR 0,6 V/µs, salida a 25 mV de rieles; validado en `dbg/opa.cir` y `dbg/sr.cir`). El macromodelo de Microchip (`models/opa_mcp.lib`) y el UniversalOpAmp2 (`models/opa_level2.lib`) no convergían con 4 canales. Correr: `wine LTspice.exe -b <archivo>.cir` y leer el `.log`.

**T2 (`t2_ac.cir`), un canal:** ganancia 54,04 dB (503) · −3 dB en **19,97 Hz** y **501,3 Hz** · −73,8 dB a 4 kHz respecto de la banda · G1 = 20,16. Cumple.

**T4 (`t4_cm.cir`), 4 canales, 50 Hz de red 311 Vpk, desbalance 51k ∥ 47n, RFI propuesta.** Valores referidos a la entrada (RTI):

| Caso | A batería (CGE 20 pF) | Alimentado de red |
|---|---|---|
| 0 Ref. pasiva directa a VREF (sin R de seguridad) | 0,37 µVpk | 4,1 µVpk |
| 4 Ref. pasiva por 390 kΩ (segura) | 7,9 µVpk | 87 µVpk |
| **1 RLD, sensado en punto medio de RG** | **0,39 µVpk** | **4,3 µVpk** |
| 2 RLD, sensado 100k × 8 sobre electrodos (pizarra) | 79 µVpk | 870 µVpk |
| 3 Solo los 100k × 8, sin RLD | 53 µVpk | 582 µVpk |

- Sensar sobre los electrodos es **~200× (46 dB) peor** que el punto medio de RG. H2 queda confirmado.
- El RLD mejora **~26 dB** frente a una referencia pasiva igual de segura (390 kΩ). Frente a una referencia directa sin resistencia queda igual, pero esa referencia no cumple el límite de corriente.

**T4b (`t4b_rfi.cir`), filtro RFI con RLD en punto medio de RG:**

| RFI | Ganancia 100 Hz | Ganancia 500 Hz | 50 Hz RTI a batería | 50 Hz RTI con red |
|---|---|---|---|---|
| Pizarra: 100k, 470p, 4,7n | 51,4 dB (−2,6) | 40,3 dB (**−10,7**) | 2,9 µV | 32 µV |
| Gemini: 330k, 470p, 4,7n | 46,2 dB (−7,8) | 30,8 dB (**−20,3**) | 2,2 µV | 24 µV |
| Propuesta: 100k, 47p, 100p | 54,0 dB | 51,0 dB | 0,39 µV | 4,3 µV |
| Propuesta: 330k, sin Ccm, 47p | 54,0 dB | 51,0 dB | **0,07 µV** | **0,8 µV** |

(Las pérdidas entre paréntesis son respecto de la cadena ideal: 54,0 dB a 100 Hz y 51,0 dB a 500 Hz.) Las dos variantes con 470 pF/4,7 nF se comen la banda. **330k sin Ccm + Cd 47 pF** da el mejor rechazo, 10 µA en falla y +0,8 µVrms de ruido: candidata a quedar como opción final (decisión del usuario).

**Pendiente:** T5, la estabilidad del lazo RLD. `t5_rld.cir` está armado, pero su `.meas` mide |Vcm| absoluto, no la razón con y sin RLD. Hay que exportar con `-ascii` y calcular S(f) = Vcm_RLD/Vcm_sinRLD. También quedan pendientes T3 (offset de electrodo, transitorio), T6–T12 y el Monte Carlo.
