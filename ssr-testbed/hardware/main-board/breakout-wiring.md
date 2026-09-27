# Conexionado Breakout — Prototipo

## Configuración Base

Para el prototipo inicial (sin PCB), todo se conecta con cables dupont
sobre la NUCLEO-H723ZG.

### Alimentación

```
Powerbank 5V ──USB──▶ NUCLEO-H723ZG ──5V pin──▶ TPS7A4700 VIN
                                                     │
                                                     ├── 3.3V ──▶ INMP441 VDD
                                                     │
                                                    GND ──▶ AGND común
```

⚠️ **Importante:** El TPS7A solo alimenta los sensores. La NUCLEO se
alimenta por USB directo.

### AFE sEMG (4 canales)

Las salidas ADC1..ADC4 del AFE van a 4 entradas analógicas del MCU, con la
tierra del AFE unida a AGND. Pines pendientes de la decisión de MCU (ver
docs/refactor-emg-software.md). Esquemático y simulación: sim/ltspice/.

### INMP441 (Breakout Board)

| Breakout Pin | Cable Color  | NUCLEO Pin  |
|-------------|-------------|-------------|
| VDD         | Rojo        | TPS7A VOUT (3.3V) |
| GND         | Negro       | AGND         |
| L/R         | Negro       | GND (left channel) |
| DOUT        | Blanco      | PC7 (I2S3_SD) |
| WS          | Gris        | PA15 (I2S3_WS) |
| BCK         | Morado      | PC10 (I2S3_CK) |

## Lista de Cables Dupont

| Tipo           | Cant. | Uso |
|----------------|-------|-----|
| Macho-Hembra   | 12    | Sensores → NUCLEO |
| Macho-Macho    | 4     | Puentes en NUCLEO |
| Hembra-Hembra  | 2     | TPS7A → sensores  |

## Diagrama de Conexión (ASCII)

```
                    ┌──────────────────────┐
                    │     NUCLEO-H723ZG    │
                    │                      │
                    │ ADCx ◄───────── ADC1..ADC4 (AFE) │
                    │                      │
                    │ PC7  ◄───────── DOUT │
                    │ PA15 ◄───────── WS   │
                    │ PC10 ◄───────── BCK  │
                    │                      │
                    │ 5V ──► TPS7A VIN     │
                    └──────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   TPS7A LDO       │
                    │   VIN  VOUT       │
                    │   GND             │
                    └─────────┬─────────┘
                              │ 3.3V
                    ┌─────────┴─────────┐
                    │      INMP441      │
                    │  VDD      VDD     │
                    │  GND      GND     │
                    └───────────────────┘
```

## Verificación Rápida

1. Medir 3.3V en salida del TPS7A con multímetro
2. Medir VREF = 1.65 V y las 4 salidas del AFE en reposo (≈ 1.65 V)
3. Verificar BCK del INMP441 con osciloscopio / analizador lógico
4. Enviar 0x55 por UART y verificar eco (loopback test)
