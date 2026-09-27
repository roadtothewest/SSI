# Pinout de Conexiones

## Conexiones STM32 (NUCLEO-H723ZG Reference)

### AFE sEMG — ADC (4 canales)

Las 4 salidas ADC1..ADC4 del AFE (docs/afe-emg/) van a 4 entradas analógicas
del ADC con disparo por timer y DMA (2 kHz por canal propuesto). Los pines
quedan pendientes de la decisión de MCU (ver docs/refactor-emg-software.md).

### INMP441 — I2S3 (vía SAI1 mapeado a I2S)

| INMP441 Pin | STM32 Pin | Función       | Notas                   |
|-------------|-----------|---------------|-------------------------|
| L/R         | GND       | Left channel  | 0 = left, 1 = right    |
| DOUT        | PC7       | SPI2_MOSI / I2S3_SD | SDO serial data    |
| WS          | PA15      | I2S3_WS       | Word select (LR clock)  |
| BCK         | PC10      | I2S3_CK       | Bit clock               |
| VDD         | 3.3V      | TPS7A output  | LDO limpio              |
| GND         | GND       | AGND          | Plano separado          |

### TPS7A4700 (LDO)

| TPS7A Pin | Conexión          | Notas                      |
|-----------|-------------------|----------------------------|
| VIN       | 5V (NUCLEO/VBUS)  | Desde USB o powerbank      |
| VOUT      | 3.3V sensores     | VDD INMP441                |
| GND       | AGND              | Plano de tierra analógico  |
| SHDN      | 5V (pull-up)      | Enable siempre activo      |
| NR/SS     | 4.7µF → GND       | Noise reduction / soft-start|
| FB/GND    | GND (fijo)        | Si es versión fija 3.3V    |

### USB (CDC)

| Señal      | STM32 Pin | Notas                    |
|------------|-----------|--------------------------|
| USB_DP     | PA12      | D+ (con resistencia pull-up 1.5kΩ a 3.3V para FS) |
| USB_DM     | PA11      | D-                        |
| VBUS       | PA9       | Detección de 5V en VBUS   |
| GND        | GND       |                          |

## Opciones Alternativas de Pines (por PDM)

Si se usa PDM directo en vez de I2S (STM32 con periférico PDM nativo):

| Señal          | STM32 Pin    | Periférico    |
|----------------|--------------|---------------|
| PDM_CLK        | PB10         | SAI1_SCK_B   |
| PDM_DATA       | PC3          | SAI1_SD_B    |

Para el INMP441 en modo PDM se requiere un decimator filter por SW o usar
el periférico DFSDM del STM32 (si está disponible).
