# Especificación de Acople Mecánico a la Piel

## Requerimientos

- Adhesión segura a la piel sobre la laringe durante sesiones de 30–60 min
- Hipoalergénico, apto para piel sensible
- Masa despreciable (< 10 mg sobre el sensor)
- Sin resonancias mecánicas en el rango DC – 6.3 kHz
- Extracción sin dolor ni residuos
- Reposicionable si es necesario (múltiples sesiones)

## Opción 1 (Recomendada): Adhesivo Médico 3M 1526L

| Propiedad              | Valor                  |
|------------------------|------------------------|
| Tipo                   | Acrílico medical grade |
| Espesor                | 0.18 mm               |
| Liner                  | Papel kraft siliconado |
| Adhesión al acero      | 3.9 N/10mm            |
| Temperatura            | -40 a +93°C           |
| Biocompatibilidad      | ISO 10993 (citotóxico, irritación, sensibilización) |
| Remoción               | Sin residuos, baja traumaticidad |

**Aplicación:** Corte de 8×12 mm aplicado en la cara inferior de la flex PCB,
con bordes reforzados con micropore tape (3M #1530).

## Opción 2: Hidrocoloide Delgado

- Comercial: Parche Compeed o similar, 0.5 mm
- Mayor grosor pero mejor amortiguación de sudor
- Se puede recortar al tamaño exacto de la flex

## Opción 3: Silicona Médica Biocompatible (para uso prolongado)

- Ej: Dow Corning MG 7-9900
- Curado in situ sobre la flex
- Reutilizable ~10 sesiones
- Mayor complejidad de aplicación

## Consideraciones Mecánicas

### Posicionamiento

La flex debe colocarse:
- Sobre la prominencia laríngea ("nuez de Adán")
- Eje X del acelerómetro alineado con el eje anteroposterior (perpendicular a piel)
- Eje Z alineado con el eje cráneo-caudal (vertical)
- La marca de alineación en la flex (muesca en esquina) debe apuntar hacia arriba

### Efecto de Masa

La masa total del flex + componentes es < 10 mg.
La piel y tejido subcutáneo sobre la laringe tiene una masa efectiva > 1 g
y un módulo elástico de ~100 kPa. Con estos valores, la frecuencia de
resonancia del conjunto piel-sensor supera los 10 kHz (muy por fuera del
ancho de banda de interés de 6.3 kHz).

### Cable

El cable FPC/ZIF debe tener un lazo de alivio de tensión (curva de 180°)
entre la flex y el cuello para evitar transmitir vibraciones del cable al
sensor. Fijar el cable a la piel con un parche de micropore 2 cm antes del
conector.

## Referencias

- 3M 1526L: https://www.3m.com/3M/en_US/p/d/b5005010860/
- 3M Micropore 1530: https://www.3m.com/3M/en_US/p/d/b5005010884/
- ISO 10993-5: Biocompatibilidad (citotoxicidad)
- Guía de aplicación: ver `docs/diagrams/mechanical-assembly.mermaid`
