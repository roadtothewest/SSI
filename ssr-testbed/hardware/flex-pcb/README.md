# Flex PCB — Sensor de Vibración Laríngeo

## Objetivo

Montar el acelerómetro IIS3DWB en una PCB flexible de masa despreciable
que pueda adherirse a la piel sobre la laringe, minimizando el efecto de
carga mecánica (mass loading) y artefactos por movimiento relativo.

## Especificaciones de la Flex

| Parámetro               | Valor                |
|-------------------------|----------------------|
| Material base           | Poliimida (Kapton)   |
| Espesor base            | 0.1 mm (4 mil)      |
| Cobre                   | 1/2 oz (18 µm)      |
| Coverlay                | 0.025 mm             |
| **Total estimado**      | **~0.2 mm**          |
| Capas                   | 1 (simple faz)       |
| Acabado                 | ENIG (Au sobre Ni)   |
| Masa total (sin cable)  | < 10 mg              |
| Conector                | ZIF 0.5mm pitch, 6 pins o JST SH 1.0mm 4-pin |
| Longitud cable          | 10–15 cm             |
| Ancho aproximado        | 8 × 12 mm (área activa) |

## Componentes en Flex

| Componente | Encapsulado | Masa  |
|------------|-------------|-------|
| IIS3DWB    | LGA-14L (2.5×3mm) | ~2 mg |
| Capacitor desacople 100nF | 0402 | ~0.6 mg |
| Capacitor bypass Vdd_IO | 0402 | ~0.6 mg |
| Pull-up CS (si necesario) | 0402 | ~0.6 mg |
| Conector ZIF (remoto) | — | en extremo del cable |

## Masa Total vs. Piel

La masa total del conjunto flex + componentes es < 10 mg.
La piel sobre la laringe tiene una masa efectiva >> 1 g y una impedancia
mecánica mucho mayor, por lo que el efecto de carga es < 1%.

Esto garantiza que la respuesta medida es la vibración real de la laringe,
no la resonancia del sensor.

## Stackup

```
Capa superior:  Coverlay 0.025mm
               Cobre 0.018mm (1/2 oz)
               Poliimida 0.1mm
Capa inferior: Coverlay 0.025mm (adhesivo 3M 1526L aplicado después)
```

## Archivos de Diseño (rev01)

Los archivos de diseño en KiCad se encuentran en `hardware/flex-pcb/rev01/`.
Incluyen:

- `iis3dwb-flex.sch` — Esquemático
- `iis3dwb-flex.pcb` — Layout
- `iis3dwb-flex.kicad_pro` — Proyecto KiCad 8
- `gerber/` — Archivos de fabricación
