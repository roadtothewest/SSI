# Ubicación de los 3 canales sEMG: qué dice la literatura

## Papers en esta carpeta (y en `papers/old`)

| Archivo | Referencia | Por qué sirve |
|---|---|---|
| `Hwang2026_EMG-to-Speech_fewer_channels.pdf` | Hwang, Lee, Lee. *EMG-to-Speech with Fewer Channels*. arXiv:2602.06460 (2026) | **El más directo.** Prueba las 70 combinaciones de 4 canales de 8, y mide qué canal es crítico para cada tipo de vocal (Tabla 3) |
| `Gaddy2020_Digital_voicing_silent_speech.pdf` | Gaddy, Klein. *Digital Voicing of Silent Speech*. EMNLP 2020, arXiv:2010.02960 | Define las 8 posiciones que usan Hwang y Lee; dataset abierto |
| `Le2026_sEMG_encoding_articulatory_features.pdf` | Le et al. *Comparison of sEMG Encoding Accuracy Across Speech Modes Using Articulatory and Phoneme Features*. arXiv:2604.18920 (2026) | Relación sitio del electrodo ↔ articulador, en habla en voz alta, mimada y subvocal |
| `Sensors2025.xml` (texto completo) | Salomons, del Blanco, Navas, Hernáez et al. *Electrode Setup for EMG-Based Silent Speech Interfaces: A Pilot Study*. Sensors 25(3):781 (2025). [PDF](https://www.mdpi.com/1424-8220/25/3/781) | **Hablantes de español.** Compara 14 músculos en clasificación de fonos; Tabla 1 resume las configuraciones de electrodos de ~20 estudios |
| `../old/2505.13814v1.pdf` | Lee et al. *Articulatory Feature Prediction from Surface EMG during Speech Production*. arXiv:2505.13814 (2025) | Qué electrodo predice cada articulador, el tono y el volumen |
| `../old/nihms387553.pdf` | Stepp, Heaton, Givens, Hillman. *Use of neck and face sEMG for controlling a prosthetic voice after total laryngectomy*. IEEE TNSRE (2009) | sEMG del cuello (músculos infrahioideos) para controlar volumen y F0 → respalda la recomendación del experto |
| `../old/Freeman_RLD.pdf` | Gonzalez-Lopez et al. *Silent Speech Interfaces for Speech Restoration: A Review*. IEEE Access (2020) | Revisión general |

No descargables (paywall), pero conviene citarlos: Meltzner et al. 2017 (IEEE/ACM TASLP 25(12)) y 2018 (J Neural Eng 15(4):046031), sobre selección de subconjuntos de sensores; Stepp 2012, *Surface electromyography for speech and swallowing systems*, JSLHR 55:1232, sobre colocación y crosstalk; Fridlund & Cacioppo 1986, *Guidelines for human electromyographic research*, Psychophysiology 23:567, la guía clásica de ubicación facial.

## Posiciones de Gaddy (las que usan Hwang y Lee)
1 mejilla izq. justo sobre la boca · 2 esquina izq. del mentón (depresor del ángulo de la boca) · **3 bajo el mentón, 3 cm hacia atrás (submentoniano)** · 4 garganta, 3 cm a la izquierda de la nuez · 5 mitad de la mandíbula der. · **6 mejilla der. justo bajo la boca (orbicular / labio inferior)** · 7 mejilla der., 2 cm de la nariz (cigomático mayor) · 8 mejilla der. posterior, 4 cm delante de la oreja (masetero)

## Resultados clave para las vocales A E I O U
- **Hwang 2026, Tabla 3** (canal cuya ausencia más empeora la tasa de error):
  - **vocales altas y anteriores (I, E) → canal 7 (cigomático)**: el error sube de 21,7 % a 28,8 %;
  - **vocales redondeadas y posteriores (O, U) → canal 6 (orbicular / labio inferior)**: de 17,8 % a 20,7 %;
  - **vocales bajas (A) → canal 3 (submentoniano)**.
- **Hwang 2026, Tabla 2:** el canal individual más valioso es el **3 (submentoniano)**, seguido del 2 y el 1.
- **Lee 2025:**
  - los electrodos 2 y 3 son los que más aportan al movimiento de la lengua;
  - el 2 y el 6, al labio inferior y la mandíbula;
  - **el 4 (cuello, junto a la laringe) es el mejor para volumen (r = 0,73) y tono (r = 0,32)**.
  - Su subconjunto recomendado de 4 es {2, 3, 4, 6}.
- **Stepp 2009:** el sEMG del cuello sirve para controlar el volumen y la F0 → coincide con lo que te dijo el experto.

## Recomendación con 3 canales (español: las 5 vocales)
Las 5 vocales del español se separan con 2 dimensiones: **altura** (A baja; E y O medias; I y U altas) y **redondeo** (O y U redondeadas; I y E no). En español, el redondeo coincide con anterior/posterior. Por eso basta con 2 canales en la cara + 1 en el cuello:

| Canal | Músculo | Posición exacta | Qué aporta |
|---|---|---|---|
| **CH1** | Submentoniano (vientre anterior del digástrico, milohioideo, base de la lengua) | Bajo el mentón, a 1 cm de la línea media. Electrodo 1 a ~1 cm detrás de la punta del mentón y electrodo 2 a 2–3 cm detrás (posición 3 de Gaddy), en línea antero-posterior | **Altura de la vocal / apertura** (A vs I, U). Es el canal más informativo en todos los estudios |
| **CH2** | Labio inferior (depresor del ángulo de la boca, depresor del labio inferior, orbicular inferior) | Un electrodo justo bajo la comisura del labio y el otro bajo él, hacia la esquina del mentón, siguiendo las fibras (posiciones 6 → 2 de Gaddy, del mismo lado) | **Redondeo** (O, U vs I, E) y apertura del labio |
| **CH3** | Cuello, junto a la laringe (infrahioideos: esternohioideo) | ~3 cm lateral a la nuez, del lado de CH2. Par vertical: uno a la altura del cartílago tiroides y otro 2–3 cm más abajo, en el pliegue del cuello. **Por dentro del esternocleidomastoideo**, no sobre la arteria carótida (para no captar el pulso) | **Volumen y F0** (lo que dijo el experto); es además el control del confusor laríngeo en el análisis de causalidad |
| RLD | — | Clavícula o apófisis mastoides (detrás de la oreja), lejos de los 3 pares | Referencia |

**Variante solo para vocales:** cambiar CH3 por el **cigomático** (posición 7 de Gaddy: mejilla, 2 cm al lado de la nariz, con el par en la dirección de la comisura al pómulo). Es el canal crítico para I y E según Hwang (Tabla 3). Se pierde la lectura de volumen y F0, y también el control laríngeo de la causalidad.

## Reglas de colocación (aplican a todas)
- Separación entre los centros del par: **~2 cm**, a lo largo de la fibra del músculo, y siempre los dos electrodos sobre el mismo músculo.
- Limpiar la piel con alcohol; marcar las posiciones con un lápiz dermográfico o fotografiarlas para repetirlas igual en cada sesión.
- Los Skintact de 32 × 41 mm dejan los centros a ≥32 mm. En CH2 cuesta: recortar la espuma o usar electrodos de 24 mm (Arbo H124SG).
