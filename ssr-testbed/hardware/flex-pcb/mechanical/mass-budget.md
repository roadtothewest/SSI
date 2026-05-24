# Budget de Masa del Conjunto Flex

## Objetivo

Demostrar que la masa del conjunto sensor + flex es despreciable frente a
la masa efectiva de la piel y tejido laríngeo, asegurando que no hay
efecto de carga mecánica (mass loading) que modifique la vibración medida.

## Cálculo de Masas

### Componentes Electrónicos

| Componente    | Cant. | Masa Unit. | Masa Total |
|---------------|-------|-----------|------------|
| IIS3DWB (LGA-14L) | 1 | 2.0 mg | 2.0 mg |
| Capacitor 0402 (100nF) | 2 | 0.6 mg | 1.2 mg |
| Resistor 0402 (si necesario) | 1 | 0.6 mg | 0.6 mg |
| **Subtotal componentes** | | | **3.8 mg** |

### Flex PCB

| Elemento      | Área    | Espesor | Densidad | Masa |
|---------------|---------|---------|----------|------|
| Poliimida     | 96 mm²  | 0.1 mm  | 1.42 g/cm³ | 1.36 mg |
| Cobre (1/2 oz)| 40 mm²  | 18 µm   | 8.96 g/cm³ | 0.65 mg |
| Coverlay      | 96 mm²  | 25 µm   | 1.42 g/cm³ | 0.34 mg |
| Soldadura ENIG| —       | —       | —         | ~0.1 mg |
| **Subtotal flex** | | | | **2.45 mg** |

### Adhesivo

| Elemento      | Área    | Espesor | Densidad | Masa |
|---------------|---------|---------|----------|------|
| 3M 1526L      | 96 mm²  | 0.18 mm | 1.0 g/cm³ | 1.73 mg |

### Total Conjunto

| Componente    | Masa    |
|---------------|---------|
| Componentes   | 3.8 mg  |
| Flex PCB      | 2.5 mg  |
| Adhesivo      | 1.7 mg  |
| **Total**     | **8.0 mg** |

## Masa Efectiva de la Piel Laríngea

La piel sobre el cartílago tiroides tiene:
- Área de acople típica: 2 × 2 cm = 4 cm²
- Espesor piel + tejido subcutáneo: ~2–3 mm
- Masa efectiva: ~1–2 g
- Impedancia mecánica: ~100–200 kg/s (mucho mayor que la flex)

## Relación de Masas

```
Masa flex / Masa piel = 8 mg / 1500 mg = 0.0053 (0.53%)
```

El efecto de carga mecánica es despreciable (< 1%). La flex PCB actúa como
un "testigo" que sigue fielmente el movimiento de la piel sin modificarlo.

## Frecuencia de Resonancia del Conjunto

Considerando la flex como una masa m = 8 mg sobre un resorte
k = E·A/h (donde E ≈ 100 kPa para piel, A = 96 mm², h = 2 mm):

- k = 100 kPa · 96 mm² / 2 mm = 4800 N/m
- f_res = (1/2π) · √(k/m) = (1/2π) · √(4800 / 8e-6) ≈ 3.9 kHz

La resonancia está por debajo del BW del IIS3DWB (6.3 kHz), pero:
1. La piel no es un resorte ideal — tiene amortiguamiento viscoso alto
2. La resonancia es de la interface, no del sensor
3. En la práctica, para CWT la banda útil es < 3 kHz, donde el acople es plano

Esto se verificará experimentalmente comparando con un sensor de referencia
montado rígidamente.
