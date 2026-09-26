Para establecer un enlace inalámbrico directo de 20 km entre un microcontrolador STM32 (a bordo del dron) y un SBC terrestre (Single Board Computer, como Raspberry Pi, Jetson Nano, etc.), necesitamos transceptores de alta potencia con interfaces nativas compatibles con ambos sistemas. [1] 
A continuación, se presentan las mejores alternativas inalámbricas a LoRa, detallando sus periféricos y protocolos recomendados para esta arquitectura.
------------------------------
## Sistemas Alternativos Recomendados

| Sistema / Módulo | Interfaz STM32 (Dron) | Interfaz SBC (Tierra) | Ventaja Principal a 20 km | Enlace de Referencia |
|---|---|---|---|---|
| RFDesign RFD900x / RFD900ux | UART (Serial) | UART / USB-UART | Máxima penetración, salto de frecuencia y robustez. | RFDesign RFD900x[](https://store.rfdesign.com.au/) |
| Microhard pDDL900 / pMDDL2450 | Ethernet / UART | Ethernet / USB-Ethernet | IP nativo encapsulado, video HD + datos simultáneos. | Microhard Systems[](https://www.microhardcorp.com/) |
| Módems 4G LTE (Simcom / Quectel) | UART / USB (vía comandos AT) | USB (Modem Manager / Linux) | Alcance virtual ilimitado independiente de la línea de vista. | Quectel Wireless[](https://www.quectel.com/) |

------------------------------
## 1. Sistema de Telemetría Industrial: RFDesign RFD900x
Es la evolución natural y profesional de los módulos SiK de telemetría. Trabaja en la banda de 900 MHz, lo que ofrece un excelente equilibrio entre alcance y tamaño de antena.

* Periféricos requeridos en el Dron (STM32):
* Puerto UART: Conexión directa desde los pines TX/RX del STM32 a los pines RX/TX del módulo RFD900x.
   * Alimentación Externa: El módulo consume hasta 1A a 5V en picos de transmisión de 1W. Nunca lo alimentes desde el regulador interno del STM32; requiere un BEC/regulador de 5V dedicado.
   * Antenas: Dos antenas monopolo o dipolo ligeras a bordo para aprovechar su tecnología de diversidad espacial (Antenna Diversity).
* Periféricos requeridos en el SBC Terrestre:
* Módulo RFD900x gemelo.
   * Conversor USB a UART (FTDI): Para conectar el módulo a un puerto USB del SBC, o bien conectarlo directamente a los pines GPIO UART del SBC (ej. ttyAMA0 en Raspberry Pi).
   * Antena Direccional: Una antena tipo Yagi o Patch de alta ganancia conectada al nodo de tierra para asegurar el umbral de recepción a 20 km.

## 2. Enlace de Datos IP Militar/Industrial: Microhard pDDL o pMDDL
Estos módulos crean una red de área local inalámbrica (LAN) privada de largo alcance entre el dron y tierra, operando como un puente Ethernet/Serial inalámbrico transparente.

* Periféricos requeridos en el Dron (STM32):
* Periférico Ethernet (MAC) del STM32 + PHY Externo: Si usas un STM32 con soporte Ethernet (como las series STM32F4/F7/H7), necesitas un chip PHY (como el LAN8720) para conectar el STM32 al puerto Ethernet del módulo Microhard.
   * Alternativa UART: Si tu STM32 no tiene Ethernet, puedes usar un puerto UART, pero perderás la capacidad de transmitir flujos de datos masivos.
   * Regulador de Voltaje de Alta Potencia: Operan comúnmente entre 7V y 30V; requieren una línea directa de la batería del dron con filtrado de ruido.
* Periféricos requeridos en el SBC Terrestre:
* Módulo Microhard base.
   * Puerto Ethernet Nativo: Conexión directa por cable de red RJ45 al SBC. El SBC verá al dron simplemente como otro dispositivo dentro de su propia subred IP.

## 3. Enlace Celular Celda a Celda (4G LTE / 5G)
Elimina la necesidad de antenas direccionales terrestres utilizando la infraestructura de telecomunicaciones existente.

* Periféricos requeridos en el Dron (STM32):
* Módulo Celular (ej. Quectel BG95 o SIM7600): Conectado al STM32 mediante un puerto UART de alta velocidad.
   * Tarjeta NanoSIM: Con plan de datos activo y cobertura en la zona de vuelo.
   * Antena LTE: Antena de parche flexible pegada al chasis del dron.
* Periféricos requeridos en el SBC Terrestre:
* Conexión a Internet: El SBC terrestre solo necesita acceso a internet estable (un módem USB 4G, WiFi o Ethernet convencional).

------------------------------
## Protocolos Recomendados
Para garantizar que los datos viajen empaquetados, sin errores y de forma eficiente sobre estas tecnologías, debes implementar las siguientes capas de software:
## Para Telemetría y Comandos de Control: MAVLink (v2)

* Por qué: Diseñado específicamente para canales de radio con pérdidas. MAVLink incluye suma de comprobación (CRC) para descartar paquetes corruptos y maneja retransmisiones automáticas para comandos críticos. [2] 
* Implementación: El STM32 genera los paquetes MAVLink usando la librería generada (mavlink.h) y los escupe secuencialmente por el buffer de la UART. En el SBC, puedes usar [Mavsdk-Python](https://mavsdk.mavlink.io/main/en/python/) o [PyMAVLink](https://github.com/ArduPilot/pymavlink) para leer el puerto serie o socket UDP y desempaquetar la telemetría automáticamente.

## Para Arquitecturas basadas en Redes IP (Microhard o LTE): UDP / TCP encapsulado

* Si usas Microhard/LTE: Configura un socket UDP en el STM32 (usando una pila de red como LWIP).
* Por qué UDP: A 20 km la latencia fluctúa. UDP no se detiene a esperar paquetes perdidos, garantizando que el SBC siempre reciba la telemetría más reciente en tiempo real. TCP solo debe usarse para comandos de configuración críticos donde no se pueda tolerar la pérdida de un solo byte.

## Para el Control del Módulo Celular: Comandos AT y Protocolo PPP / MQTT

* Implementación: El STM32 debe enviar Comandos AT iniciales al módem para conectarse a la red celular de la telefónica (configuración de APN). Posteriormente, se puede abrir un socket directo o utilizar un cliente ligero de MQTT (con un broker en la nube o en el propio SBC con IP pública) para intercambiar mensajes cortos de telemetría de manera asíncrona.

------------------------------
Para ayudarte a elegir los componentes exactos, dime:

* ¿El modelo de STM32 que estás usando cuenta con periférico Ethernet nativo (como el STM32F407 o STM32H7) o solo dispone de UARTS?
* ¿Vas a escribir el firmware del STM32 utilizando bare-metal/HAL o estás utilizando un sistema operativo en tiempo real como FreeRTOS o Zephyr?


[1] [https://www.youtube.com](https://www.youtube.com/watch?v=GCvDmYvfHs0)
[2] [https://es.wikipedia.org](https://es.wikipedia.org/wiki/MAVLink)

