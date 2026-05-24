# Conexionado Breakout — Prototipo

## Configuración Base

Para el prototipo inicial (sin PCB), todo se conecta con cables dupont
sobre la NUCLEO-H723ZG.

### Alimentación

```
Powerbank 5V ──USB──▶ NUCLEO-H723ZG ──5V pin──▶ TPS7A4700 VIN
                                                     │
                                                     ├── 3.3V ──▶ IIS3DWB VDD
                                                     ├── 3.3V ──▶ INMP441 VDD
                                                     │
                                                    GND ──▶ AGND común
```

⚠️ **Importante:** El TPS7A solo alimenta los sensores. La NUCLEO se
alimenta por USB directo.

### IIS3DWB (Breakout Board)

| Breakout Pin | Cable Color  | NUCLEO Pin  |
|-------------|-------------|-------------|
| VDD         | Rojo        | TPS7A VOUT (3.3V) |
| GND         | Negro       | AGND         |
| CS          | Naranja     | PA4          |
| SCK         | Amarillo    | PA5          |
| MOSI        | Verde       | PA7          |
| MISO        | Azul        | PA6          |
| INT1        | Violeta     | PC0          |

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
                    │ PA4  ◄───────── CS   │
                    │ PA5  ◄───────── SCK  │
                    │ PA7  ◄───────── MOSI │
                    │ PA6  ──────────► MISO│
                    │ PC0  ◄───────── INT1 │
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
                    │  IIS3DWB  INMP441 │
                    │  VDD      VDD     │
                    │  GND      GND     │
                    └───────────────────┘
```

## Verificación Rápida

1. Medir 3.3V en salida del TPS7A con multímetro
2. Leer WHO_AM_I del IIS3DWB (registro 0x0F = 0x71) vía SPI
3. Verificar BCK del INMP441 con osciloscopio / analizador lógico
4. Enviar 0x55 por UART y verificar eco (loopback test)
