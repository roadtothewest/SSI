# Diseño del AFE sEMG — transcripción técnica por tema (documento 2 de 2)

Complementa `gemini_1_contexto_y_decisiones.md` (contexto, decisiones, leyenda de confianza: [VERIFICADO-DS], [REPO], [WEB], [MEMORIA], [USUARIO]). Aquí está el diseño del circuito tal como quedó en la conversación, incluyendo los debates, las correcciones y los puntos abiertos.

## 1. Requisitos de partida

- 4 canales bipolares (2 electrodos c/u) + 1 electrodo de RLD. Alimentación única de 3,3 V, referencia analógica VREF = 1,65 V [REPO].
- Banda útil sEMG 20–500 Hz; fs 1–2 kHz por canal; ADC interno del STM32 (12 bits + sobremuestreo hasta ≈ 14 bits efectivos) [REPO].
- sEMG típico 0,1–5 mV pico [REPO]. El usuario planteó un rango de entrada de **100 µV a 100 mV** y preguntó qué pasa al saturar (ver §5).
- CMRR suficiente para la red de 50 Hz. RLD verdadero (no la tierra virtual del BioAmp Pill).
- Modelo mental del usuario: "el RLD en paralelo claro, y para cada canal un primer op amp que filtra ruido y tiene ganancia, y luego el pasa-banda (también con ganancia, puede ser), y luego viene el bus de adc-dma, generando CWT-windows en paralelo".

## 2. Cadena por canal (cajas negras) — versión acordada

```
Electrodos IN+ / IN-
   │
   ▼
[Protección ESD/AC]      por línea: R serie + diodos clamp a los rieles (sin ferrita)
   │
   ▼
[Filtro RFI diferencial] 2×R 1 kΩ + 2×C a GND + Cdiff   (corte ≈ 340 kHz por línea)
   │
   ▼
[INA — 1 solo IC]        AD8226 o INA333, ganancia G1 con una RG, REF = 1,65 V
   │
   ▼
[HPF 2º orden, 20 Hz]    Sallen-Key (Butterworth/Bessel)  — 1 op-amp
   │
   ▼
[G2 — ganancia]          no inversor, Rg a VREF           — 1 op-amp
   │
   ▼
[LPF 4º orden, 500 Hz]   2× Sallen-Key en cascada, Bessel — 2 op-amps
   │
   ▼
[Buffer de salida]       ganancia unitaria                — 1 op-amp
   │
   ▼
Pin del ADC (+ RC pasivo opcional pegado al pin)
```

Compartido entre los 4 canales: **RLD** (lazo lateral, en paralelo), **referencia VREF = 1,65 V** (divisor + seguidor rail-to-rail + capacitor de 10 µF) y **un solo ADC** del STM en modo scan+DMA.

**Orden original del repo (superado):** INA (G1=100) → post-amp G2 (5–10) → HPF 20 Hz → LPF 500 Hz, con G_total ≈ 500 (hasta ≈ 1000) [REPO §3.2/§3.3]. Se cambió el orden por el problema de offset descrito en §6.

## 3. Protección ESD/AC y filtro RFI

### 3.1 Protección ESD/AC (primer bloque tras el conector de electrodos)

- Es circuitería **por línea** (IN+ e IN− por separado, no diferencial): un resistor en serie (10–100 kΩ en el repo) y, después de él, diodos de sujeción a los rieles que recortan transientes y ESD.
- El resistor serie cumple dos funciones: limitar corriente de falla hacia el paciente y hacia el amplificador.
- **Sin ferrita** (decisión del usuario; solo añadía atenuación de RF extra, no es la protección real).
- Diodos de baja fuga: el datasheet del AD8232 menciona BAV199 o FJH1100 para sobrecargas extremas [VERIFICADO-DS, p. 19]. Ese datasheet también recomienda un resistor entre el pin y el electrodo tal que la corriente nunca supere **10 µA**: R = V_alimentación / 10 µA (≈ 330 kΩ a 3,3 V) [VERIFICADO-DS, p. 19]. Esto **contradice** el rango de 10–100 kΩ del repo; ver §12 punto 2.

### 3.2 Filtro RFI diferencial

Filtro pasivo de guardia, **no** filtra 50 Hz. Evita que la RF (radios, conmutación de fuentes, celulares) se rectifique en el par de entrada de la INA y aparezca como artefacto de baja frecuencia. El corte es deliberadamente ancho: f = 1 / (2π · 1 kΩ · 470 pF) ≈ 338 kHz.

Netlist (aclarado a pedido del usuario, porque un ASCII previo era confuso):

| Elemento | Conecta | Valor |
|---|---|---|
| R_rfi1 | salida de la protección de IN+ → nodo **C** | 1 kΩ |
| R_rfi2 | salida de la protección de IN− → nodo **D** | 1 kΩ |
| Ccm1 | nodo C → GND | 470 pF |
| Ccm2 | nodo D → GND | 470 pF |
| Cdiff | nodo C ↔ nodo D (entre las patas de salida de las dos R de 1 kΩ) | **no se dimensionó** |
| Salida | nodo C → INA pin 3 (+IN); nodo D → INA pin 2 (−IN) | — |

- Cdiff va entre los dos nodos posteriores a las R de 1 kΩ (lado de la INA), no entre los electrodos crudos.
- Regla habitual: Cdiff ≈ 10× Ccm para limitar la conversión de modo común a diferencial por tolerancias [MEMORIA — verificar].
- Referencia real: el AD8232 forma su RFI con 15 pF de capacidad de compuerta y 10 kΩ por entrada, admite resistores externos adicionales en serie "lo más cerca posible" de las entradas de la INA, que pueden ser los mismos de protección [VERIFICADO-DS, p. 20]. También pide trazas de entrada simétricas y de igual longitud, resistores de protección/bias en la misma posición relativa en cada entrada, y plano de tierra [VERIFICADO-DS, p. 20].

## 4. INA: conexiones, ganancia y elección de chip

El "inicial" es **un solo IC** (AD8226 o INA333), aunque por dentro sea un amplificador de instrumentación de 3 op-amps. Antes de él no hay nada más que la protección y el RFI.

### 4.1 Conexiones (8 pines; ambos chips comparten el layout) — [MEMORIA, no verificado contra datasheet en esta sesión]

| Pin | Nombre | Va a |
|---|---|---|
| 1 y 8 | RG | una resistencia entre ambos pines fija G1 |
| 2 | −IN | nodo D (post-RFI) |
| 3 | +IN | nodo C (post-RFI) |
| 4 | −VS | GND (alimentación única) |
| 5 | REF | VREF = 1,65 V (compartida por las 4 INAs) |
| 6 | OUT | entrada del HPF |
| 7 | +VS | 3,3 V con 100 nF de bypass pegado al pin |

Ecuación de salida: Vout = REF + G1·(IN+ − IN−) [MEMORIA].

### 4.2 Ganancia [REPO]

- AD8226: G = 1 + 49,4 kΩ / RG → para G1 = 100, RG ≈ 499 Ω.
- INA333: G = 1 + 100 kΩ / RG → para G1 = 100, RG ≈ 1,01 kΩ.
- RG al 0,1 % para mantener CMRR y ganancia entre canales (escalogramas comparables).

### 4.3 CMRR: dónde importa

CMRR ≥ 100 dB importa casi exclusivamente en la INA, único punto con dos señales independientes que se restan. Desde su salida todo es single-ended sobre 1,65 V, así que en post-amp, HPF, LPF y buffer no hay modo común que rechazar; ahí importan ancho de banda, offset, rail-to-rail y recuperación de sobrecarga.

- INA333: CMRR ≈ 100 dB con G ≥ 10, zero-drift, ruido ≈ 55 nV/√Hz [REPO].
- AD8226: CMRR ≈ 90 dB con G = 100 [REPO]. **Estas cifras no se verificaron contra datasheet**; el usuario preguntó explícitamente por > 100 dB, así que hay que confirmarlas.

### 4.4 Abastecimiento y falsificación

Cotización en `es.aliexpress.com` (precios en CLP, leídos por un resumen automático [WEB], poco fiable):

- INA333: listados de ≈ CLP 2.900–4.800 por 5 unidades (centavos de dólar cada una), implausible para un chip de precisión genuino → alto riesgo de falsificación o re-marcado.
- AD8226ARMZ: desde ≈ CLP 1.088 la unidad en lote chico hasta CLP 56.200 en otros listados. El precio más bajo también es sospechoso.
- Postura acordada: preferir AD8226, comprar a vendedor con historial largo, y **validar en banco** la ganancia real de cada unidad contra la calculada (síntoma típico de chip falso). Alternativa: INA333 de un distribuidor confiable, más caro y lento.
- Búsqueda usada: https://es.aliexpress.com/w/wholesale-AD8226ARMZ.html

## 5. Ganancia, rango dinámico y saturación

Números [REPO §3.3 y cálculos de la conversación]:

- Configuración del repo: G1 = 100 y G2 = 5 → **G_total = 500** (margen para 5 mV; subir a ≈ 1000 ajustando G2).
- Rango del ADC: 3,3 V; 12 bits ⇒ ≈ 0,8 mV/LSB en el pin.
- Con G1 = 100 y unos ±1,5 V de excursión útil de la INA alrededor de 1,65 V, **la INA satura a ≈ 15 mV diferenciales** (DC + señal). O sea, satura antes de los 100 mV del rango mencionado. La excursión de ±1,5 V es un supuesto; falta verificar el swing real de salida a 3,3 V.
- No se puede cubrir 100 µV–100 mV (60 dB) con ganancia fija: bajar G_total a ≈ 15 para no saturar con 100 mV deja 100 µV como ≈ 1,5 mV en el ADC, menos de 2 LSB. Por eso el diseño se calibró para 0,1–5 mV.
- Postura acordada: 100 mV en un electrodo de superficie es artefacto (movimiento, "pop" de contacto, offset), no señal EMG. Se deja saturar y se **detecta por software** (marcar y descartar ventanas con el ADC cerca de fondo de escala, ya en el checklist del repo).
- Recuperación: elegir op-amps con buen tiempo de recuperación de sobrecarga.
- El protocolo de captura debe distinguir EMG desconectado / sin habla / con habla por canal (ver documento 1 §6).

**Corrección sobre la recuperación rápida:** Claude sugirió "diodos de sujeción en paralelo con el capacitor del HPF" y dijo que el Fast Restore del AD8232 era el equivalente. **Falso**: el Fast Restore usa un comparador de ventana que detecta cuando la salida de la IA se acerca a 50 mV de cualquiera de los rieles y, al dispararse, cierra dos switches (S1/S2) que ponen resistores internos de 10 kΩ **en paralelo** con los resistores externos del HPF, subiendo temporalmente el corte para descargar rápido los capacitores; luego vuelve al corte normal [VERIFICADO-DS, pp. 17–18, 21]. Son dos mecanismos distintos. Los diodos son una idea de Claude no respaldada por ese datasheet.

## 6. Offset piel-electrodo y orden de las etapas (el debate)

### 6.1 El pin REF de la INA no rechaza offset

Objeción del usuario: "para qué [el capacitor] si el INA ya recibe la referencia?". Aclaración: REF solo fija dónde cae la salida cuando la entrada diferencial es cero (Vout = REF + G1·ΔV). El offset de media-celda entre los dos electrodos es una diferencia real entre IN+ e IN−: para la INA es indistinguible de señal, se multiplica por G1 y llega montada sobre el 1,65 V. Con 5 mV de offset y G1 = 100 son 500 mV en la salida de la INA; con G2 = 5 antes del HPF serían 2,5 V, cerca del riel.

### 6.2 Propuesta del capacitor de acople (retirada) y la técnica que se conserva

Claude propuso primero un capacitor de acople en serie tras la INA (≈ 1–4,7 µF) con R ≈ 100 kΩ a VREF, y G2 como no inversor con Rg a VREF. El usuario desconfió ("siento que te vas a pitear las señales de los sEMG"). Se retiró esa propuesta a favor del reorden de §6.3. Aclaraciones que sí quedan:

- Con un capacitor de 2,2 µF y 100 kΩ el corte sería ≈ 0,72 Hz, muy por debajo de 20 Hz, así que no atenuaba la banda sEMG; aun así se descartó por innecesario.
- No es un "sumador" (término de la configuración inversora con varias entradas). Lo que recentra en 1,65 V es un **amplificador no inversor con Rg a VREF** en vez de a GND:

```
V+ (centrada en VREF, más la señal v_ac) ──► op-amp
V- ◄── nodo N;  Rf: N ↔ salida;  Rg: N ↔ VREF
Vout = V+·(1 + Rf/Rg) − VREF·Rf/Rg  =  VREF + (1 + Rf/Rg)·v_ac
```

  El 1,65 V aparece solo, sin etapa extra. Sirve para G2 y para cualquier etapa de una sola alimentación (`G2 = 1 + Rf/Rg`).
- Malentendido resuelto: Rf/Rg son nombres genéricos de la realimentación local de ese op-amp; **no tienen relación con el RLD**, que es un tercer circuito independiente.

### 6.3 Resolución acordada: reordenar, sin capacitor nuevo

INA → **HPF** → **G2** → LPF. El HPF Sallen-Key ya tiene capacitores en la trayectoria de señal y bloquea DC por topología; al ponerlo antes de G2, el offset se elimina antes de aplicarle el grueso de la ganancia. Mismos bloques, mismo número de op-amps. En un sistema lineal el orden de filtro y ganancia no cambia la respuesta en frecuencia mientras nada sature, así que el corte de 20 Hz no daña la señal; de hecho evita la saturación, que sí la distorsiona. El usuario lo aceptó: "En segundo lugar, vendría el HPF, luego G2, luego LPF."

**Limitación que quedó sin decir en la conversación (nota al transcribir):** con este orden el offset aún se multiplica por G1 antes del HPF, así que con G1 = 100 la INA tolera solo ≈ ±15 mV de offset+señal. Ver §12 punto 1.

### 6.4 Hallazgos verificados en el datasheet del AD8232 (Rev. A)

Ese chip **no es** el que se va a usar: es un front-end de ECG integrado. Se usó como precedente de arquitectura.

- Bloques: amplificador de instrumentación (IA), op-amp de propósito general A1, amplificador de RLD A2 y buffer de referencia de mitad de alimentación A3, más detección de electrodo suelto y "fast restore" [VERIFICADO-DS, p. 16].
- Su IA rechaza offsets de electrodo de hasta **±300 mV** dentro de la propia etapa mediante un lazo de realimentación indirecta con un amplificador de bloqueo DC (HPA/integrador), con ganancia 100 [VERIFICADO-DS, pp. 16, 21]. **AD8226 e INA333 no tienen ese lazo interno**; por eso en este diseño el HPF externo justo tras la INA no es opcional.
- Rechazo de offset con una red RC entre la salida de la IA, HPSENSE y HPDRIVE: f_dB ≈ 100 / (2π·R·C), es decir, el corte es **100 veces más alto** que el de un polo simple, porque la realimentación de la IA lo modifica por su ganancia de 100 [VERIFICADO-DS, p. 21]. Ante un cambio brusco de offset que sature la IA, S1 pone 10 kΩ en paralelo con R y sube el corte (Fast Restore, §5).
- Para un HPF de 2 polos añade "un simple RC de acople AC a la salida de la IA" (Fig. 55); tablas de 1, 2 y 3 polos en p. 22 (Tabla 4). Este RC pasivo es esencialmente la misma técnica (capacitor + resistor a REFOUT tras la salida de la IA) que Claude había propuesto en §6.2, y **el datasheet la respalda como técnica documentada** [VERIFICADO-DS, pp. 21–22]. Lo que la conversación acordó en cambio fue usar un Sallen-Key activo; ambas opciones son válidas y es decisión de diseño.
- Si esa red de acople pasiva no está bufereada tiene impedancia de salida alta; al conectarla a un Sallen-Key pasabajos hay que hacer R1 del LPF **al menos 10 veces** el resistor de acople (R2 de la Fig. 55) [VERIFICADO-DS, p. 23]. Regla útil si se elige HPF pasivo.
- Sallen-Key de 2 polos: f_c = 1/(2π√(R1·C1·R2·C2)); con R1=R2 y C1=C2, f_c = 1/(2πRC) y Q se controla con la ganancia (G < 3 para ese esquema; con C2 ≥ 4·C1 se permiten ganancias mayores). Las ecuaciones asumen impedancia de salida de la etapa previa mucho menor que la de entrada del filtro [VERIFICADO-DS, p. 23].

## 7. Op-amps: recomendación, características y conteo

**Para la INA:** ver §4.3–4.4 (INA333 si se prioriza CMRR; AD8226 si se prioriza abastecimiento seguro).

**Para post-amp, HPF, LPF y buffer** (4 op-amps genéricos por canal, todos iguales): **OPA4313** (recomendado) o **MCP6004** (más barato y disponible) [MEMORIA/REPO]. Evitar el TL074 clásico a 3,3 V (no opera bien); el TL074H figura en el repo como opción rail-to-rail.

Características exigibles a estos op-amps:

- rail-to-rail de entrada y salida con alimentación única de 3,3 V;
- ancho de banda de ganancia (GBW) ≥ 1 MHz (sobra para señales < 1 kHz con ganancias modestas);
- offset bajo (importa en el HPF y para la deriva de línea base);
- buen tiempo de recuperación de sobrecarga (relacionado con la saturación por artefactos);
- ruido bajo es deseable pero pesa menos que en la INA (queda dividido por la ganancia previa).

**Conteo corregido** (Claude cometió un error de aritmética en la conversación, ver §11):

| Concepto | Cantidad |
|---|---|
| Op-amps genéricos por canal: G2 (1) + HPF (1) + LPF de 4º orden (2) + buffer (1) | 5 |
| 4 canales | 20 |
| RLD (1) + seguidor de VREF (1) | 2 |
| **Total de op-amps genéricos** | **22** |
| Chips cuádruples (4 op-amps c/u) | **6** (24 slots, 2 de sobra) |
| INAs (chips aparte) | 4 |
| **Total de chips** | **10** |

Si se fusiona G2 con una etapa de filtro (Sallen-Key con ganancia), bajaría a 4 por canal → 18 op-amps → 5 cuádruples. Es una optimización posible, no acordada.

## 8. RLD (Right Leg Drive)

Diseño del repo [REPO §3.4]: promedio resistivo del modo común de las entradas con resistores de 100 kΩ → op-amp inversor de ganancia −A (A ≈ 10–20) con polo dominante (C ≈ 10–100 pF en la realimentación) → resistor serie de seguridad R_s (≈ 100 kΩ) → electrodo dedicado en la muñeca (zona de baja actividad muscular). El sistema debía operar "flotante a batería" (ver alerta de seguridad, documento 1 §7).

Puntos discutidos:

- **Va en paralelo**, como lazo lateral: no está en serie con ninguna de las 4 cadenas de canal, y maneja un electrodo distinto del resto.
- **Dónde se toma el nodo de promedio:** *después* de la protección ESD/AC (tras la R serie), idealmente después del RFI, en el mismo nodo que entra a la INA; nunca directo del electrodo crudo. Motivo: si se sensa antes de esa R, un transiente en el cable le pega al nodo sumador del op-amp del RLD sin el recorte de los diodos, y tomando después se promedia una señal ya libre de RF, que es la que interesa cancelar.
- **¿Solo IN+?** El diseño del repo dibuja solo los IN+ (4 resistores). Es una simplificación válida y común, porque IN+ e IN− de un mismo canal están a 2–3 cm sobre el mismo músculo y ven casi el mismo modo común. Claude **recomendó usar los 8** (IN+ e IN−: 4 resistores más, costo ≈ cero) por dar una estimación de Vcm algo más fiel; es la forma "de libro" (Winter–Webster, ADS1299). **No hay decisión final del usuario.**
- El pin "DRL" del BioAmp Pill no es un RLD; ver documento 1 §4.

Datos verificados del RLD del AD8232 (referencia de diseño) [VERIFICADO-DS, pp. 17 y 23]:

- Invierte el modo común presente en las entradas de la IA y lo inyecta al sujeto. El modo común se extrae de GM1 y entra al inversor de A2 por un resistor interno de 150 kΩ.
- Integrador con capacitor externo entre RLDFB y RLD: 1 nF da cruce en ≈ 1 kHz y ≈ 26 dB de ganancia de lazo a 50–60 Hz. Capacitores mayores bajan el cruce y reducen el rechazo (más ruido de línea); menores suben la ganancia pero pueden inestabilizar y saturar la salida del RLD.
- Para estabilidad, la ganancia del integrador debe ser menor que 1 en la frecuencia de cualquier otro polo del lazo (capacidad del paciente, resistores de seguridad).
- Resistor serie al electrodo: corriente < 10 µA incluso en falla; con 3,0 V debe ser > 330 kΩ (el repo dice ≈ 100 kΩ; ver §12 punto 3).
- Si el RLD no se usa, se recomienda configurar A2 como seguidor.

Referencias sugeridas para "copiar" el RLD: sección "Right Leg Drive" de los datasheets ADS1298/ADS1299 (TI); esquemático público de **OpenBCI Cyton** en GitHub (placa real basada en ADS1299) [MEMORIA, no se abrió]; Winter y Webster, "Driven-right-leg circuit design", IEEE Trans. Biomed. Eng., 1983 [MEMORIA].

## 9. Salida: buffer y ADC

- **Buffer de salida: sí**. Aunque el último Sallen-Key ya tenga salida de baja impedancia, el buffer aísla la red de realimentación del filtro de la carga capacitiva conmutada del sample-and-hold del ADC y da un punto limpio para un polo RC final (p. ej. 1 kΩ + 100 pF) pegado al pin del ADC.
- El AD8232 confirma que, según la arquitectura del ADC, puede hacer falta una red RC simple para desacoplar los transitorios del capacitor conmutado, y que además filtra ruido y aliasing; seguir la guía del datasheet del ADC [VERIFICADO-DS, p. 23].
- **No son 4 ADCs:** es **un** periférico ADC (ADC12 del STM32N6) con 4 canales analógicos en modo scan + DMA, con timestamp común por timer y desfase de µs entre canales [REPO].
- Protección de entrada del ADC (spec original): R serie 10 kΩ y sujeción a 3,3 V [REPO].
- Plan B del spec original si el ADC interno no alcanza en ruido/resolución: ADS131M04 (4 canales, 24 bits, muestreo simultáneo, SPI); cambia solo la tarea de adquisición, no el frente analógico [REPO]. La resolución efectiva del ADC del STM32N657 y el mapeo de pines aún no están verificados.

## 10. Alimentación y referencia

- 3,3 V limpia (LDO de bajo ruido; el testbed cita un TPS7A4700). El LDO ya comprado es de **3,0 V**, no sirve como riel de 3,3 V (ver documento 1 §7).
- VREF = 1,65 V: divisor + seguidor rail-to-rail + capacitor de 10 µF, compartida por las 4 INAs y por las etapas de una alimentación. Además es la referencia de retorno de los resistores Rg de los no inversores.
- Bypass: 100 nF cerámicos pegados a cada pin de alimentación (ya hay 2 de 100 nF y 2 de 1 µF en stock); el AD8232 recomienda 0,1 µF cerca del pin y 1 µF más lejos [VERIFICADO-DS, p. 20].

## 11. Errores y correcciones ocurridos en la conversación (para no repetirlos)

1. "El Fast Restore del AD8232 es equivalente a diodos de sujeción" — falso; usa comparador de ventana y switches (§5).
2. "G2 como sumador" — término incorrecto; es un no inversor con Rg a VREF (§6.2).
3. Confusión Rf/Rg con el RLD — eran nombres genéricos de otro circuito (§6.2).
4. Propuesta de capacitor de acople tras la INA — retirada por innecesaria en favor del reorden (§6), aunque el datasheet AD8232 documenta una técnica parecida.
5. **Aritmética del conteo de op-amps:** en la conversación se dijo que con buffer bastaban 5 chips cuádruples ("20 slots, 1 usado por RLD, 3 de sobra"). Incorrecto: los 4 canales solos usan los 20 slots, y faltaban el RLD y el seguidor de VREF. Correcto: 22 op-amps, 6 chips (§7).
6. "El LDO comprado sirve para 3,3 V" — es de 3,0 V.
7. Publicaciones previas del repo afirmaban "INMP441 comprado y validado" — error; no está comprado (corregido en el repo).
8. Se citaron de memoria (sin verificar) el pinout de la INA, las cifras de CMRR, el número SLOA058 de TI y el esquemático de OpenBCI.

## 12. Puntos abiertos para el diseño con Gemini

Anotados al transcribir; no todos se discutieron en la conversación.

1. **Valor de G1 vs. tolerancia al offset de electrodo.** Con G1 = 100 la INA tolera ≈ ±15 mV (offset+señal). Con G1 más bajo (p. ej. 10–20) tolera ≈ ±75–150 mV y el grueso de la ganancia pasa a G2 después del HPF, manteniendo G_total ≈ 500. Decidir teniendo en cuenta ruido y CMRR (INA333 declara CMRR alto desde G ≥ 10).
2. **Valor del resistor serie de protección de entradas:** repo 10–100 kΩ vs. criterio de 10 µA del AD8232 (≈ 330 kΩ a 3,3 V). Evaluar ruido térmico, desbalance de fuente/CMRR y sobrevoltajes.
3. **Resistor serie del RLD:** repo ≈ 100 kΩ vs. AD8232 > 330 kΩ a 3,0 V.
4. **Seguridad con alimentación de red** (documento 1 §7): definir aislamiento galvánico antes de conectar electrodos.
5. **Camino de retorno de corriente de bias y comportamiento con electrodo desconectado:** no se discutió. El usuario quiere ver en la HMI "EMG desconectado". Sin retorno de bias las entradas flotan a un riel de forma impredecible; el AD8232 usa resistores de 10 MΩ a REFOUT o RLD [VERIFICADO-DS, p. 19]. El diseño del repo (§3.4 punto 5) habla de retornar los pines de bias/referencia de las INAs al nodo RLD.
6. **Dimensionar Cdiff** y verificar la regla Cdiff ≈ 10×Ccm (§3.2).
7. **Encapsulados:** AD8226ARMZ es MSOP-8 y los cuádruples propuestos son SOIC-14/TSSOP-14 (SMD), mientras la "Ruta B" se describió como perfboard through-hole. Hace falta adaptadores SMD→DIP o variantes DIP, o soldadura fina. El BOM del repo no lo resuelve.
8. **BOM del repo desactualizado:** dice 4 cuádruples (ahora 6), asume 3,0 V como riel de 3,3 V y no incluye el buffer. Impacto de costo: +2 chips (≈ USD 2–4) sobre un estimado que ya rozaba el tope de USD 60.
9. **Verificar contra datasheet de AD8226 e INA333:** pinout, rango de alimentación mínimo, rango de modo común de entrada y swing de salida a 3,3 V con alimentación única y G alto, CMRR y ruido reales.
10. **Diseño de filtros con valores:** HPF Sallen-Key 2º orden a 20 Hz; LPF 4º orden a 500 Hz en dos secciones Sallen-Key (Bessel para fase lineal, Butterworth aceptable; evitar respuestas elípticas por ringing) [REPO]; ganancias, Q y valores de R/C; con Sallen-Key de ganancia unitaria o baja si se quiere fusionar G2.
11. **Recuperación de sobrecarga:** sin decidir el método (ninguno está validado): clamp pasivo, conmutación de resistores como el Fast Restore, o solo elegir op-amps de recuperación rápida y detectar en software.
12. **Interfaz al ADC:** RC final (valores), sujeción a 3,3 V, y confirmar resolución y pines del ADC del MCU elegido (H723ZG vs. N6).
13. **RLD:** cuántos resistores de promedio (4 vs. 8), valor del integrador/polo dominante y verificación de estabilidad con la impedancia real del cuerpo y el resistor de seguridad.
14. **Notch:** el usuario mencionó un notch "post conversión ac/dc" sin especificar dónde ni cómo (¿sobre el riel de alimentación o digital sobre los datos?). Aclarar.
15. **Validación en banco (propuesta acordada):** armar y validar **1 canal completo** antes de replicar los otros tres; medir ganancia real y CMRR; correr el protocolo de diagnóstico por canal (desconectado / sin habla / con habla).

## 13. Referencias

- **AD8232 Data Sheet, Rev. A (Analog Devices)** — leído localmente en `/home/ludicolo/Descargas/AD8232.PDF`, págs. 16–23 (Theory of Operation y Applications Information). Secciones útiles: Architecture Overview, Right Leg Drive Amplifier, Fast Restore Circuit, Input Protection, RFI, Eliminating Electrode Offsets, High-Pass Filtering, Low-Pass Filtering and Gain, Driving ADCs.
- TI, "Single-Supply Op Amp Circuit Collection" (**SLOA058**) — técnica de atar la resistencia de ganancia a VREF en etapas de una alimentación [MEMORIA: el número de documento se citó de memoria; buscar por título].
- Datasheets ADS1298/ADS1299 (TI), sección Right Leg Drive; y ADS129x SBAS459K referido en el repo [REPO].
- OpenBCI Cyton, esquemático público en GitHub [MEMORIA, no se abrió].
- Winter y Webster, "Driven-right-leg circuit design", IEEE Trans. Biomed. Eng., 1983 [MEMORIA].
- En el repo: `docs/afe-emg/AFE_EMG_Diseno.md` (§2 análisis netlist del BioAmp Pill; §3 arquitectura; §5 interfaz), `docs/refactor-emg-software.md`, `bom.csv`, `README.md`.
- https://www.crowdsupply.com/upside-down-labs/bioamp-exg-pill · https://www.crowdsupply.com/starcat/hackeeg · https://www.youtube.com/watch?v=3g7l5bm7fZ8 · https://www.atomic14.com/videos/posts/VVGln_-XEgI
