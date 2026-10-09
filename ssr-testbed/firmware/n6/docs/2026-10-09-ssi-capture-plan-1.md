# Plan 1 — Firmware de captura `ssi_capture` (adquisición en la N6)

> **Para agentes:** SUB-SKILL REQUERIDA: `superpowers:executing-plans` (ejecución nativa, tarea por tarea; Matías pidió "cada módulo de forma procedural, con pruebas"). Los pasos usan casillas (`- [ ]`).

**Goal:** firmware FSBL + ThreadX que adquiere 3 canales EMG a 4 kHz y audio del INMP441 a 16 kHz en un solo dominio de reloj y arma paquetes DATA de 1024 B verificados, probado módulo a módulo en el DK, sin la RPi5.

**Architecture:** CubeMX genera solo la base: relojes, MPU y caché, ThreadX, TIM6 como tick de la HAL y USART1. Cada periférico de la captura vive en un módulo propio en `FSBL/App/`, con su handle HAL `static`, sus pines, su reloj, su DMA y su configuración RIF; así la regeneración de CubeMX no lo toca. La lógica pura (CRC, paquetes, decodificación del audio, emparejamiento de ventanas) se prueba en el PC con gcc; los drivers, en el DK con logs por el VCP y volcados de memoria por SWD.

**Tech stack:** STM32CubeN6 v1.4.1 (HAL), ThreadX (API nativa), CubeMX 6.18.1 (CLI), GCC `arm-none-eabi` 14.3.1 + CMake/Ninja, CubeProgrammer 2.23 (SWD en modo HOTPLUG), Python 3.12 solo con biblioteca estándar, gcc 13 del host.

**Spec:** `docs/2026-10-09-ssi-capture-spec.md` (v0.2).

**Alcance:** este plan cubre R1–R4 y R7 (pruebas P1 parcial, P2, P3, P4 y P7). El Plan 2 se escribe al terminar este y cubre el enlace SPI con la RPi5, `ctrl` con comandos e INFO/STATUS, la recuperación ante errores de la spec §7 (detener, estado ERROR, nuevo `epoch`), el watchdog y el arranque desde flash (R5, R6, P5, P6). En este plan un error de DMA, ADC o SAI se cuenta, marca b3 en el siguiente paquete y se ve en `STAT`.

**Desvíos de la spec v0.2 (se corrigen en la spec junto con este plan):** el CRC-32 es por software, porque así lo prueba el mismo código en el PC y el costo es despreciable. El SAI captura las dos ranuras: la derecha debe quedar en cero, lo que permite detectar un pin L/R mal cableado.

**Ya hecho (prueba de viabilidad, 2026-10-09):** `ssi_capture/ssi_capture.ioc` derivado de `NUCLEO-N657X0-Q/Applications/ThreadX/Tx_Thread_Creation.ioc` (misma MCU) sin los LED de la Nucleo (PG8, PG10), con toolchain CMake, librerías copiadas y `TX_APP_CREATION=0`. El script `scripts/mx_generate_ssi_capture.txt` lo genera y la base compila: 56,7 KB de código y 6,5 KB de RAM.

## Restricciones globales

- Placa STM32N6570-DK (MB1939C) con la N657X0H3Q en modo desarrollo (BOOT1 = H). Proyecto único FSBL en AXISRAM2: código desde `0x34180400` (255 KB).
- Regla del proyecto: un módulo por responsabilidad, `.h` público y `.c` con estado `static`. Sin variables globales compartidas. Entre hilos, solo primitivas de ThreadX. ISR y callbacks de la HAL solo incrementan contadores propios y llaman a `tx_event_flags_set`.
- Código propio solo en `ssi_capture/FSBL/App/`, `ssi_capture/tests/`, `tools/` o en bloques `USER CODE`.
- Pines (spec v0.2 §3): EMG en A1 = PA9 (ADC1_INP10), A4 = PF3 (ADC1_INP16) y A5 = PB10 (ADC1_INP8). SAI2 bloque B: SCK PE12 (A2), FS PE13 (D6), SD PE7 (D8), AF10. TIM1_ETR en PD0 (D2), AF1. Puente D6 → D2. PC10, PC12 y PH2 (gemelos digitales de A1, A4 y A5) se quedan en analógico.
- Audio a 16 kHz exactos: HSE 48 MHz → PLL4 1179,648 MHz → IC7 /24 = 49,152 MHz → MCKDIV 12. I²S estándar, 24 bits en ranuras de 32. EMG = FS/4 vía TIM1 (ETR, ARR = 3, TRGO = update). Muestreo del ADC de 246,5 ciclos, reloj del ADC ≤ 50 MHz.
- Paquete DATA de 1024 B según la spec §6. CRC-32 compatible con `zlib.crc32`, guardado en el offset 1020.
- Búferes DMA y nodos GPDMA en `.noncacheable`: región NC `0x341F8000–0x341FFFFF`, región 0 de la MPU, sección NOLOAD.
- Prohibido programar OTP, fusibles u option bytes.
- Sin `git commit` salvo pedido explícito de Matías.
- Seguridad: en estas pruebas el DK está unido al PC por el ST-LINK, así que nada de electrodos en una persona.

## Review Focus

1. **`acq` atrasado más de 10 ms:** la DMA sobrescribe la mitad del búfer antes de copiarla. Se espera que la ventana se cuente como `lost` y marque b2, nunca datos mezclados. Pruebas: casos de salto en `test_acq_logic` (Task 2) y 60 s con `lost == 0` (Task 5).
2. **Orden de arranque roto** (el SAI arranca antes de armar ADC y TIM1): `c` cambiaría entre reinicios. Se espera `c` constante. Prueba: pulso común con 10 reinicios (Task 5).
3. **Micrófono mal cableado** (L/R a 3,3 V o SD suelto): el audio cae en la ranura derecha o queda en cero. Se espera verlo en `rslot` y `peak`. Prueba: criterios `rslot == 0` y `peak > 0` (Task 3).
4. **Salida del AFE fuera de rango:** códigos pegados en 0 o 4095. Se espera la bandera b1. Prueba: saturación alta y baja en `test_packet` (Task 2).
5. **Sección no cacheable fuera de la región de la MPU:** el CPU vería datos viejos de la DMA. Se espera un fallo visible al arrancar. Prueba: línea `NC ... OK` del arranque (Task 1).

## Mapa de archivos

Rutas relativas a `SSI-repo/ssr-testbed/firmware/n6/`.

| Archivo | Responsabilidad |
|---|---|
| `ssi_capture/ssi_capture.ioc` | Base de CubeMX: relojes, MPU (región NC), caché, ThreadX, TIM6, USART1 |
| `ssi_capture/FSBL/ssi_capture_fsbl.ld` | Linker propio: RAM de 224 KB + región NC de 32 KB (NOLOAD) |
| `ssi_capture/FSBL/CMakeLists.txt` | (generado una vez, editable) módulos HAL extra, `App/`, linker propio |
| `FSBL/App/Inc/ssi_config.h` | Constantes de adquisición compartidas |
| `FSBL/App/Inc/nc_mem.h` | Atributo `NC_MEM` para búferes DMA |
| `FSBL/App/{Inc,Src}/log.*` | Log por línea en el VCP (USART1), con mutex |
| `FSBL/App/{Inc,Src}/led.*` | LD1 verde (PO1) y LD2 rojo (PG10) |
| `FSBL/App/{Inc,Src}/crc32.*` | CRC-32 (zlib), lógica pura |
| `FSBL/App/{Inc,Src}/packet.*` | Formato de paquetes de la spec §6, lógica pura |
| `FSBL/App/{Inc,Src}/audio_decode.*` | Palabras del SAI → muestras de 24 bits con signo, lógica pura |
| `FSBL/App/{Inc,Src}/acq_logic.*` | Qué ventana de 10 ms empaquetar o descartar, lógica pura |
| `FSBL/App/{Inc,Src}/mic_sai.*` | Driver del INMP441: reloj de audio, SAI2-B, DMA circular |
| `FSBL/App/{Inc,Src}/sync.*` | TIM1 contando FS por ETR → TRGO al ADC |
| `FSBL/App/{Inc,Src}/emg_adc.*` | ADC1 de 3 canales con disparo por TIM1, DMA circular |
| `FSBL/App/{Inc,Src}/capture.*` | Orden de arranque y parada, `epoch` |
| `FSBL/App/{Inc,Src}/acq.*` | Hilo `acq`: empareja ventanas y arma paquetes DATA |
| `FSBL/App/{Inc,Src}/diag.*` | Captura de 1 s para volcarla por SWD (solo depuración) |
| `FSBL/App/{Inc,Src}/testpulse.*` | Pulsos en D7 para la prueba de sincronización |
| `FSBL/App/{Inc,Src}/sink.*` | Consumidor provisional de paquetes (lo reemplaza `link` en el Plan 2) |
| `FSBL/App/{Inc,Src}/mon.*` | Hilo de monitoreo: STAT por segundo, LED, comandos de depuración por SWD |
| `FSBL/App/{Inc,Src}/app.*` | Objetos RTOS e hilos; enganche con `main.c` y `app_threadx.c` |
| `ssi_capture/tests/host/` | Pruebas en el PC (gcc + CTest) de la lógica pura |
| `tools/fw.sh` | Compilar y cargar en RAM |
| `tools/run_test.sh` | Cargar y verificar el log del VCP en una sola orden |
| `tools/uart_log.py` | Lector del VCP con expectativas (regex y expresiones sobre líneas `TAG k=v`) |
| `tools/ssi_packet.py` | Parser y validador de paquetes; el mismo que usará la RPi5 |
| `tools/swd.py` | Leer y escribir variables por SWD sin detener la MCU |
| `tools/diag.py` | Captura de 1 s: WAV, CSV, tono dominante, ruido y alineamiento de pulsos |

## Cableado por tarea

Numeración de pines según el UM3300, tabla 16.

| Tarea | Conexiones |
|---|---|
| 1–2 | Solo USB del ST-LINK (CN6) |
| 3 | INMP441: VDD → CN8-4 (+3V3), GND → CN8-6, SCK → A2 (CN7-3), WS → D6 (CN11-7), SD → D8 (CN12-1), L/R → GND |
| 4 | Además, puente D6 (CN11-7) → D2 (CN11-3). Prueba de niveles: A4 (CN7-5) → +3V3; A1 y A5 al aire |
| 5a (flujo, P3 y P7) | Igual que la tarea 4, sin el puente de A4 a +3V3. A1, A4 y A5 al punto medio de un divisor de 10k/10k entre +3V3 y GND (≈ 1,65 V), con 100 nF a GND |
| 5b (pulso, P4) | SD del micrófono desconectado de D8. D7 (CN11-8) → D8 (CN12-1) y D7 → A1 (CN7-2), con A1 fuera del divisor |

---

### Task 1: Base del proyecto, log, LED y herramientas de prueba

**Files:**
- Modify: `ssi_capture/ssi_capture.ioc` (dirección de la región 0 de la MPU) y regenerar
- Create: `ssi_capture/FSBL/ssi_capture_fsbl.ld`
- Modify: `ssi_capture/FSBL/CMakeLists.txt`
- Modify: `ssi_capture/FSBL/Src/main.c` (USER CODE Includes y 2) y `ssi_capture/FSBL/Src/app_threadx.c` (USER CODE Includes y App_ThreadX_Init)
- Create: `FSBL/App/Inc/{ssi_config.h,nc_mem.h,log.h,led.h,mon.h,app.h}`, `FSBL/App/Src/{log.c,led.c,mon.c,app.c}`
- Create: `tools/fw.sh`, `tools/run_test.sh`, `tools/uart_log.py`

**Interfaces:**
- Produce: `log_init(UART_HandleTypeDef*)`, `log_rtos_init(void)`, `log_printf(const char*, ...)`, `led_init(void)`, `led_set(led_t,int)`, `led_toggle(led_t)`, `app_early_init(UART_HandleTypeDef*)`, `app_start(void)`, `mon_thread_entry(ULONG)`, `NC_MEM`, constantes `SSI_*`.
- Herramientas: `tools/fw.sh build|ram`; `tools/run_test.sh SECS [args de uart_log.py]`; `uart_log.py --expect REGEX --check 'TAG:expr' --skip N`.

- [ ] **Step 1: Mover la región no cacheable de la MPU a 0x341F8000 (32 KB) y regenerar**

```bash
cd ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6
sed -i 's/^CORTEX_M55_FSBL.BaseAddress-Cortex_Memory_Protection_Unit_Region0_Settings=.*/CORTEX_M55_FSBL.BaseAddress-Cortex_Memory_Protection_Unit_Region0_Settings=0x341F8000/' ssi_capture/ssi_capture.ioc
(cd ~/STM32CubeMX && ./STM32CubeMX -q ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6/scripts/mx_generate_ssi_capture.txt | tail -3)
grep -n 'BaseAddress\|LimitAddress' ssi_capture/FSBL/Src/main.c
```
Expected: `MPU_InitStruct.BaseAddress = 0x341F8000;` y `MPU_InitStruct.LimitAddress = 0x341FFFFF;`.

- [ ] **Step 2: Crear el linker propio con la región NC (NOLOAD)**

Transformación del `.ld` generado (se repite si CubeMX cambia el original):

```bash
cd ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6/ssi_capture/FSBL
python3 -I - STM32N657XX_AXISRAM2_fsbl.ld ssi_capture_fsbl.ld <<'EOF'
import re, sys
src, dst = sys.argv[1], sys.argv[2]
t = open(src).read()
t = t.replace("RAM    (xrw)    : ORIGIN = 0x341C0000,   LENGTH = 256K",
              "RAM    (xrw)    : ORIGIN = 0x341C0000,   LENGTH = 224K\n"
              "  NC     (rw)     : ORIGIN = 0x341F8000,   LENGTH = 32K   /* MPU region 0: non-cacheable */")
block = re.compile(r"\.noncacheable :\s*\{.*?\}\s*> RAM", re.S)
new = (".noncacheable (NOLOAD) :\n  {\n    . = ALIGN(32);\n    __snoncacheable = .;\n"
       "    KEEP(*(.noncacheable))\n    . = ALIGN(32);\n    __enoncacheable = .;\n  } > NC")
t, n = block.subn(new, t)
assert n == 1 and "LENGTH = 224K" in t, "unexpected generated linker script"
open(dst, "w").write("/* ssi_capture: generated FSBL script + NC region (see Plan 1, Task 1). */\n" + t)
EOF
grep -n 'NC \|224K\|noncacheable (NOLOAD)\|> NC' ssi_capture_fsbl.ld
```
Expected: las 4 líneas presentes.

- [ ] **Step 3: Editar `FSBL/CMakeLists.txt`**

Cambiar `set(STM32_LINKER_SCRIPT STM32N657XX_AXISRAM2_fsbl.ld)` por:

```cmake
set(STM32_LINKER_SCRIPT ssi_capture_fsbl.ld)
```

Inmediatamente después de `include("mx-generated.cmake")`, agregar:

```cmake
# --- ssi_capture: HAL modules used by App/ but not configured in CubeMX ---
target_compile_definitions(stm32cubemx INTERFACE
    HAL_ADC_MODULE_ENABLED
    HAL_SAI_MODULE_ENABLED
    HAL_SPI_MODULE_ENABLED
)
target_sources(STM32_Drivers PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_adc.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_adc_ex.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_sai.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_sai_ex.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_spi.c
    ${CMAKE_CURRENT_SOURCE_DIR}/../Drivers/STM32N6xx_HAL_Driver/Src/stm32n6xx_hal_spi_ex.c
)
file(GLOB APP_SRC CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/App/Src/*.c)
set_source_files_properties(${APP_SRC} PROPERTIES COMPILE_OPTIONS "-Wall;-Wextra")
```

En `target_include_directories(... # Add user defined include paths)` agregar `${CMAKE_CURRENT_SOURCE_DIR}/App/Inc`, y en `target_sources(... # Add user sources here)` agregar `${APP_SRC}`.

- [ ] **Step 4: Herramientas: `tools/fw.sh`**

```bash
#!/usr/bin/env bash
# Build ssi_capture and load it to RAM on the DK (development mode, BOOT1 = H).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
FSBL="$HERE/../ssi_capture/FSBL"
ELF="$FSBL/build/Debug/ssi_capture_FSBL.elf"
# Toolchain on PATH: Matías's env script if present (override with STM32_ENV).
ENV_SH="${STM32_ENV:-$HOME/2026-2/SSI/tools/stm32-env.sh}"
# shellcheck disable=SC1090
if [ -f "$ENV_SH" ]; then source "$ENV_SH" >/dev/null; fi

case "${1:-}" in
  build)
    cd "$FSBL"
    cmake --preset Debug >/dev/null
    cmake --build --preset Debug
    ;;
  ram)
    STM32_Programmer_CLI -c port=SWD mode=UR -hardRst >/dev/null 2>&1 || true
    sleep 0.5
    GDBLOG="$(mktemp)"
    # Without -e the server exits after the first detach: one load per call.
    ST-LINK_gdbserver -p 61234 -l 1 -d -cp "$STM32_PROG_ROOT" -m 1 -g >"$GDBLOG" 2>&1 &
    GDBS=$!
    sleep 2
    arm-none-eabi-gdb -batch -ex 'target extended-remote :61234' -ex load -ex detach "$ELF" \
      | grep -E '^(Loading|Start address|Transfer rate)' || { cat "$GDBLOG"; exit 1; }
    wait "$GDBS" || true
    ;;
  *)
    echo "usage: fw.sh build|ram" >&2
    exit 2
    ;;
esac
```

- [ ] **Step 5: Herramientas: `tools/uart_log.py`**

```python
#!/usr/bin/env python3
"""Capture the ST-LINK VCP and check it (standard library only).

--start REGEX        drop everything before the first line matching REGEX (the boot banner),
                     then capture --secs seconds; the ST-LINK VCP replays stale bytes on open
--drain SECS         discard input for SECS first (run_test.sh drains before the reset)
--expect REGEX       must appear in the log
--reject REGEX       must not appear
--check 'TAG[/N]:EXPR'
                     evaluated on every 'TAG k=v k=v' line after the first N lines of that TAG
                     (N defaults to --skip; use /0 for one-shot lines such as INIT);
                     EXPR sees the fields as ints, plus d_<field> = change since the previous line.
"""
import argparse
import os
import re
import select
import sys
import termios
import time

KV_LINE = re.compile(r"^([A-Z]+)((?:\s+[a-z_0-9]+=-?\d+)+)\s*$")
KV = re.compile(r"([a-z_0-9]+)=(-?\d+)")


def open_tty(path, baud):
    fd = os.open(path, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    speed = getattr(termios, f"B{baud}")
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = attrs[5] = speed
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIFLUSH)
    return fd


def capture(dev, baud, secs, start=None, wait=20.0, drain=0.0):
    """Return the text read in secs seconds; with start, timing begins at that line.
    drain: seconds of input discarded first (bytes the VCP bridge buffered earlier)."""
    fd = open_tty(dev, baud)
    t_drain = time.time() + drain
    while time.time() < t_drain:
        if select.select([fd], [], [], 0.05)[0]:
            try:
                os.read(fd, 4096)
            except BlockingIOError:
                pass
    end = time.time() + (wait + secs if start else secs)
    data = b""
    started = start is None
    try:
        while time.time() < end:
            ready, _, _ = select.select([fd], [], [], 0.1)
            if ready:
                try:
                    data += os.read(fd, 4096)
                except BlockingIOError:
                    pass
            if not started:
                text = data.decode("ascii", "replace")
                m = re.search(r"^.*" + start, text, re.M)
                if m:
                    data = data[m.start():]
                    started = True
                    end = time.time() + secs
    finally:
        os.close(fd)
    if not started:
        return None
    return data.decode("ascii", "replace").replace("\r", "")


def kv_lines(text):
    for raw in text.splitlines():
        m = KV_LINE.match(raw.strip())
        if m:
            yield m.group(1), {k: int(v) for k, v in KV.findall(m.group(2))}, raw.strip()


def run_checks(text, checks, skip):
    ok = True
    for spec in checks:
        tag, expr = spec.split(":", 1)
        n_skip = skip
        if "/" in tag:
            tag, n = tag.split("/", 1)
            n_skip = int(n)
        prev, seen, evaluated = None, 0, 0
        for t, fields, raw in kv_lines(text):
            if t != tag:
                continue
            seen += 1
            env = dict(fields)
            if prev is not None:
                env.update({f"d_{k}": v - prev.get(k, 0) for k, v in fields.items()})
            prev = fields
            if seen <= n_skip:
                continue
            evaluated += 1
            try:
                passed = bool(eval(expr, {"__builtins__": {}, "abs": abs, "min": min, "max": max}, env))
            except NameError as e:
                passed = False
                print(f"CHECK ERROR {spec}: {e}")
            if not passed:
                print(f"CHECK FAILED {spec}\n  line: {raw}")
                ok = False
        if evaluated == 0:
            print(f"CHECK FAILED {spec}: no {tag} lines after skip={n_skip}")
            ok = False
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", default="/dev/ttyACM0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--secs", type=float, default=5.0)
    ap.add_argument("--skip", type=int, default=1)
    ap.add_argument("--start")
    ap.add_argument("--wait", type=float, default=20.0)
    ap.add_argument("--drain", type=float, default=0.0)
    ap.add_argument("--expect", action="append", default=[])
    ap.add_argument("--reject", action="append", default=[])
    ap.add_argument("--check", action="append", default=[])
    ap.add_argument("--out")
    a = ap.parse_args()
    text = capture(a.dev, a.baud, a.secs, a.start, a.wait, a.drain)
    if text is None:
        print(f"MISSING START: {a.start} (waited {a.wait} s)")
        print("RESULT: FAIL")
        return 1
    sys.stdout.write(text)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text)
    ok = True
    for rx in a.expect:
        if not re.search(rx, text, re.M):
            print(f"MISSING: {rx}")
            ok = False
    for rx in a.reject:
        if re.search(rx, text, re.M):
            print(f"FORBIDDEN: {rx}")
            ok = False
    ok = run_checks(text, a.check, a.skip) and ok
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Herramientas: `tools/run_test.sh`**

```bash
#!/usr/bin/env bash
# Usage: run_test.sh SECS [uart_log.py args...]
# Starts the VCP reader, loads the current build to RAM (reset + load) and returns the check result.
# SECS counts from the boot banner, so the ~4 s load and stale VCP bytes are excluded.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SECS="$1"
shift
python3 -I "$HERE/uart_log.py" --drain 1 --start "SSI capture fw" --secs "$SECS" "$@" &
READER=$!
sleep 1.5 # let the reader drain stale VCP bytes before the reset
"$HERE/fw.sh" ram >/dev/null
wait "$READER"
```

```bash
chmod +x ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6/tools/{fw.sh,run_test.sh,uart_log.py}
```

- [ ] **Step 7: Escribir la prueba y verificar que falla**

La prueba de esta tarea (P1, parte RAM):

```bash
cd ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6
tools/fw.sh build && tools/run_test.sh 5 \
  --expect 'SSI capture fw 0\.1\.0' \
  --expect 'CLK cpu=600000000' \
  --expect 'NC 0x341f8000\.\.0x341f[89a-f][0-9a-f]{3} OK' \
  --check 'TICK:abs(d_tx_ms-d_hal_ms)<=10' \
  --check 'TICK:abs(d_hal_ms-1000)<=30'
```
Expected ahora: `RESULT: FAIL` (la base no imprime nada; incluso puede fallar el build porque `App/` no existe todavía).

- [ ] **Step 8: Constantes y atributos (`ssi_config.h`, `nc_mem.h`)**

`FSBL/App/Inc/ssi_config.h`:

```c
#ifndef SSI_CONFIG_H
#define SSI_CONFIG_H

/* Acquisition constants shared by drivers, pure logic and packet format (spec v0.2). */
#define SSI_AUDIO_FS_HZ    16000u
#define SSI_EMG_DIV        8u                               /* EMG fs = audio fs / 8 = 2 kHz */
#define SSI_EMG_CH         3u
#define SSI_WIN_AUDIO      160u                             /* frames per 10 ms window */
#define SSI_WIN_EMG        (SSI_WIN_AUDIO / SSI_EMG_DIV)    /* 20 = tuples per SPI block */
#define SSI_AUDIO_STARTUP  4800u                            /* INMP441 start-up (~300 ms): diag skips it */
#define SSI_SYNC_C         0                                /* audio frame of EMG sample 0 (spec §4) */

#define SSI_FW_VERSION     0x000100u                        /* 0.1.0 */

#endif
```

`FSBL/App/Inc/nc_mem.h`:

```c
#ifndef NC_MEM_H
#define NC_MEM_H

/* DMA buffers and GPDMA linked-list nodes. ssi_capture_fsbl.ld places .noncacheable in
   NC (0x341F8000-0x341FFFFF), which MPU region 0 marks non-cacheable, so CPU and DMA
   stay coherent without cache maintenance. NOLOAD: contents start undefined. */
#define NC_MEM __attribute__((section(".noncacheable"), aligned(32)))

#endif
```

- [ ] **Step 9: Módulo `log`**

`FSBL/App/Inc/log.h`:

```c
#ifndef LOG_H
#define LOG_H

#include "stm32n6xx_hal.h"

/* Line logger on the ST-LINK VCP (USART1, handle created by CubeMX code in main.c).
   Thread-safe after log_rtos_init(). Never call from an ISR: it blocks on the UART. */
void log_init(UART_HandleTypeDef *huart);
void log_rtos_init(void);
void log_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));

#endif
```

`FSBL/App/Src/log.c`:

```c
#include "log.h"

#include <stdarg.h>
#include <stdio.h>

#include "tx_api.h"

static UART_HandleTypeDef *s_uart;
static TX_MUTEX s_mutex;
static int s_rtos;
static char s_line[192];

void log_init(UART_HandleTypeDef *huart)
{
  s_uart = huart;
}

void log_rtos_init(void)
{
  if (tx_mutex_create(&s_mutex, "log", TX_INHERIT) == TX_SUCCESS) {
    s_rtos = 1;
  }
}

void log_printf(const char *fmt, ...)
{
  if (s_uart == NULL) {
    return;
  }
  /* Before the scheduler runs there is a single context: no lock needed. */
  const int locked = s_rtos && (tx_thread_identify() != TX_NULL);
  if (locked) {
    tx_mutex_get(&s_mutex, TX_WAIT_FOREVER);
  }
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(s_line, sizeof s_line - 2u, fmt, ap);
  va_end(ap);
  if (n < 0) {
    n = 0;
  } else if (n > (int)sizeof s_line - 3) {
    n = (int)sizeof s_line - 3;
  }
  s_line[n++] = '\r';
  s_line[n++] = '\n';
  (void)HAL_UART_Transmit(s_uart, (uint8_t *)s_line, (uint16_t)n, 100);
  if (locked) {
    tx_mutex_put(&s_mutex);
  }
}
```

- [ ] **Step 10: Módulo `led`**

`FSBL/App/Inc/led.h`:

```c
#ifndef LED_H
#define LED_H

typedef enum { LED_GREEN = 0, LED_RED = 1 } led_t;

void led_init(void);
void led_set(led_t led, int on);
void led_toggle(led_t led);

#endif
```

`FSBL/App/Src/led.c`:

```c
#include "led.h"

#include "stm32n6xx_hal.h"

/* MB1939: LD1 green on PO1 (active high, VDDIO2 bank), LD2 red on PG10 (active low). */
void led_init(void)
{
  GPIO_InitTypeDef g = {0};
  HAL_PWREx_EnableVddIO2();
  __HAL_RCC_GPIOO_CLK_ENABLE();
  __HAL_RCC_GPIOG_CLK_ENABLE();
  g.Mode = GPIO_MODE_OUTPUT_PP;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_LOW;
  g.Pin = GPIO_PIN_1;
  HAL_GPIO_Init(GPIOO, &g);
  g.Pin = GPIO_PIN_10;
  HAL_GPIO_Init(GPIOG, &g);
  led_set(LED_GREEN, 0);
  led_set(LED_RED, 0);
}

void led_set(led_t led, int on)
{
  if (led == LED_GREEN) {
    HAL_GPIO_WritePin(GPIOO, GPIO_PIN_1, on ? GPIO_PIN_SET : GPIO_PIN_RESET);
  } else {
    HAL_GPIO_WritePin(GPIOG, GPIO_PIN_10, on ? GPIO_PIN_RESET : GPIO_PIN_SET);
  }
}

void led_toggle(led_t led)
{
  if (led == LED_GREEN) {
    HAL_GPIO_TogglePin(GPIOO, GPIO_PIN_1);
  } else {
    HAL_GPIO_TogglePin(GPIOG, GPIO_PIN_10);
  }
}
```

- [ ] **Step 11: `mon` (versión 1: tick y LED) y `app` (versión 1)**

`FSBL/App/Inc/mon.h`:

```c
#ifndef MON_H
#define MON_H

#include "tx_api.h"

void mon_thread_entry(ULONG arg);

#endif
```

`FSBL/App/Src/mon.c` (v1):

```c
#include "mon.h"

#include "led.h"
#include "log.h"
#include "stm32n6xx_hal.h"

#define MS_PER_TICK (1000u / TX_TIMER_TICKS_PER_SECOND)

void mon_thread_entry(ULONG arg)
{
  (void)arg;
  for (uint32_t i = 1u;; i++) {
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 10u);
    if (i % 5u == 0u) {
      led_toggle(LED_GREEN);
    }
    if (i % 10u == 0u) {
      log_printf("TICK t=%lu tx_ms=%lu hal_ms=%lu", (unsigned long)(i / 10u),
                 (unsigned long)(tx_time_get() * MS_PER_TICK), (unsigned long)HAL_GetTick());
    }
  }
}
```

`FSBL/App/Inc/app.h`:

```c
#ifndef APP_H
#define APP_H

#include "stm32n6xx_hal.h"

/* main(), USER CODE 2, before the kernel starts: logger, LEDs, boot report. */
void app_early_init(UART_HandleTypeDef *huart);
/* App_ThreadX_Init(): creates every RTOS object and thread (no HAL waits here:
   interrupts are still masked during tx_application_define). */
void app_start(void);

#endif
```

`FSBL/App/Src/app.c` (v1):

```c
#include "app.h"

#include "led.h"
#include "log.h"
#include "mon.h"
#include "ssi_config.h"
#include "tx_api.h"

extern uint32_t __snoncacheable;  /* ssi_capture_fsbl.ld */
extern uint32_t __enoncacheable;

#define NC_BASE 0x341F8000u
#define NC_END  0x34200000u

static TX_THREAD s_mon;
static ULONG s_mon_stack[1024]; /* 4 KB: vsnprintf */

void app_early_init(UART_HandleTypeDef *huart)
{
  const uint32_t s = (uint32_t)&__snoncacheable;
  const uint32_t e = (uint32_t)&__enoncacheable;
  log_init(huart);
  led_init();
  log_printf("SSI capture fw %lu.%lu.%lu (%s %s)", (unsigned long)((SSI_FW_VERSION >> 16) & 0xFFu),
             (unsigned long)((SSI_FW_VERSION >> 8) & 0xFFu), (unsigned long)(SSI_FW_VERSION & 0xFFu),
             __DATE__, __TIME__);
  log_printf("CLK cpu=%lu", (unsigned long)SystemCoreClock);
  log_printf("NC 0x%08lx..0x%08lx %s", (unsigned long)s, (unsigned long)e,
             (s >= NC_BASE && e <= NC_END) ? "OK" : "FAIL");
}

void app_start(void)
{
  log_rtos_init();
  tx_thread_create(&s_mon, "mon", mon_thread_entry, 0, s_mon_stack, sizeof s_mon_stack, 10, 10,
                   TX_NO_TIME_SLICE, TX_AUTO_START);
}
```

- [ ] **Step 12: Enganches en el código generado (solo bloques USER CODE)**

`FSBL/Src/main.c`:
- En `/* USER CODE BEGIN Includes */` agregar `#include "app.h"`.
- En `/* USER CODE BEGIN 2 */` agregar `app_early_init(&huart1);`.

`FSBL/Src/app_threadx.c`:
- En `/* USER CODE BEGIN Includes */` agregar `#include "app.h"`.
- En `/* USER CODE BEGIN App_ThreadX_Init */` agregar `app_start();`.

- [ ] **Step 13: Compilar y correr la prueba**

Run: el comando del Step 7.
Expected: `RESULT: PASS`, con líneas `TICK t=1 ...` a `TICK t=4 ...` y el LED verde alternando cada 0,5 s.

- [ ] **Step 14: Registrar en `MEMORY.md`** el resultado (comando y salida) y, solo si Matías lo autoriza, hacer commit: `feat: ssi_capture base project with logger, LEDs and test tools`.

---

### Task 2: Lógica pura con pruebas en el PC (CRC, paquetes, audio, emparejamiento)

**Files:**
- Create: `FSBL/App/Inc/{crc32.h,packet.h,audio_decode.h,acq_logic.h}`, `FSBL/App/Src/{crc32.c,packet.c,audio_decode.c,acq_logic.c}`
- Create: `ssi_capture/tests/host/{CMakeLists.txt,test_util.h,test_crc32.c,test_packet.c,test_audio_decode.c,test_acq_logic.c}`
- Create: `tools/ssi_packet.py`

**Interfaces:**
- Produce: `uint32_t crc32_update(uint32_t crc, const void *data, size_t len)`;
  `pkt_header_t`, `void pkt_build_data(uint8_t *buf, pkt_header_t *h, const uint16_t *emg, const int32_t *audio)`, `void pkt_write_header(...)`, `void pkt_finalize(uint8_t *buf, size_t used)`, constantes `PKT_*`;
  `int32_t audio_sign_extend24(uint32_t)`, `void audio_extract_left(const uint32_t *stereo, int32_t *out, size_t frames)`, `uint32_t audio_right_activity(const uint32_t *stereo, size_t frames)`;
  `acq_step_t acq_select(uint32_t *next, uint32_t emg_done, uint32_t aud_done, uint32_t *lost, uint32_t *k)`;
  `tools/ssi_packet.py`: `parse(bytes) -> dict` y la orden `check FILE --expect k=v ...`.

- [ ] **Step 1: Infraestructura de pruebas en el host**

`tests/host/test_util.h`:

```c
#ifndef TEST_UTIL_H
#define TEST_UTIL_H

#include <stdio.h>

static int g_fail;

#define CHECK(c)                                                          \
  do {                                                                    \
    if (!(c)) {                                                           \
      fprintf(stderr, "%s:%d: CHECK(%s)\n", __FILE__, __LINE__, #c);      \
      g_fail++;                                                           \
    }                                                                     \
  } while (0)

#define CHECK_EQ(a, b)                                                                  \
  do {                                                                                  \
    long long _a = (long long)(a), _b = (long long)(b);                                 \
    if (_a != _b) {                                                                     \
      fprintf(stderr, "%s:%d: %s == %lld, expected %lld\n", __FILE__, __LINE__, #a, _a, \
              _b);                                                                      \
      g_fail++;                                                                         \
    }                                                                                   \
  } while (0)

#define TEST_END()                                                    \
  do {                                                                \
    if (g_fail) fprintf(stderr, "%d check(s) failed\n", g_fail);     \
    return g_fail ? 1 : 0;                                            \
  } while (0)

#endif
```

`tests/host/CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.22)
project(ssi_host_tests C)
set(CMAKE_C_STANDARD 11)
enable_testing()

set(APP ${CMAKE_CURRENT_SOURCE_DIR}/../../FSBL/App)
set(TOOLS ${CMAKE_CURRENT_SOURCE_DIR}/../../../tools)
add_compile_options(-Wall -Wextra -Werror -O1 -g -fsanitize=address,undefined)
add_link_options(-fsanitize=address,undefined)
include_directories(${APP}/Inc)

add_executable(test_crc32 test_crc32.c ${APP}/Src/crc32.c)
add_executable(test_packet test_packet.c ${APP}/Src/packet.c ${APP}/Src/crc32.c)
add_executable(test_audio_decode test_audio_decode.c ${APP}/Src/audio_decode.c)
add_executable(test_acq_logic test_acq_logic.c ${APP}/Src/acq_logic.c)

add_test(NAME crc32 COMMAND test_crc32)
add_test(NAME packet COMMAND test_packet ${CMAKE_CURRENT_BINARY_DIR}/pkt_sample.bin)
add_test(NAME packet_py COMMAND python3 -I ${TOOLS}/ssi_packet.py check
         ${CMAKE_CURRENT_BINARY_DIR}/pkt_sample.bin --expect type=1 seq=7 emg_index=280
         audio_index=1120 n_emg=40 n_audio=160 n_ch=3 epoch=2 flags=1 dropped=0
         payload_len=880 emg0=100 emg119=2480 audio0=-8388608 audio159=8388607)
set_tests_properties(packet_py PROPERTIES DEPENDS packet)
add_test(NAME audio_decode COMMAND test_audio_decode)
add_test(NAME acq_logic COMMAND test_acq_logic)
```

- [ ] **Step 2: Escribir las pruebas (fallan: los módulos no existen)**

`tests/host/test_crc32.c`:

```c
#include <string.h>

#include "crc32.h"
#include "test_util.h"

int main(void)
{
  const char *v = "123456789";
  CHECK_EQ(crc32_update(0, v, strlen(v)), 0xCBF43926u); /* CRC-32/ISO-HDLC check value */
  CHECK_EQ(crc32_update(0, "", 0), 0u);
  uint32_t c = crc32_update(0, v, 4);
  c = crc32_update(c, v + 4, 5);
  CHECK_EQ(c, 0xCBF43926u); /* incremental == one-shot */
  TEST_END();
}
```

`tests/host/test_packet.c`:

```c
#include <stdio.h>
#include <string.h>

#include "crc32.h"
#include "packet.h"
#include "test_util.h"

static uint32_t rd32(const uint8_t *p)
{
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }

static pkt_header_t base_header(void)
{
  pkt_header_t h = {0};
  h.flags = PKT_F_AUDIO_VALID;
  h.seq = 7;
  h.emg_index = 280;
  h.audio_index = 1120;
  h.n_emg = 40;
  h.n_audio = 160;
  h.n_ch = 3;
  h.epoch = 2;
  return h;
}

static int sat_flag(uint16_t code)
{
  uint8_t pkt[PKT_SIZE];
  uint16_t emg[120];
  int32_t audio[160] = {0};
  for (int i = 0; i < 120; i++) emg[i] = 2048;
  emg[57] = code;
  pkt_header_t h = base_header();
  pkt_build_data(pkt, &h, emg, audio);
  return (h.flags & PKT_F_EMG_SAT) != 0 && (rd16(pkt + 6) & PKT_F_EMG_SAT) != 0;
}

int main(int argc, char **argv)
{
  uint8_t pkt[PKT_SIZE];
  uint16_t emg[120];
  int32_t audio[160];
  memset(pkt, 0xEE, sizeof pkt);
  for (int i = 0; i < 120; i++) emg[i] = (uint16_t)(100 + 20 * i);
  for (int i = 0; i < 160; i++) audio[i] = (i - 80) * 1000;
  audio[0] = -8388608;
  audio[159] = 8388607;

  pkt_header_t h = base_header();
  pkt_build_data(pkt, &h, emg, audio);

  CHECK(memcmp(pkt, "SSI1", 4) == 0);
  CHECK_EQ(pkt[4], PKT_VERSION);
  CHECK_EQ(pkt[5], PKT_DATA);
  CHECK_EQ(rd16(pkt + 6), PKT_F_AUDIO_VALID);
  CHECK_EQ(rd32(pkt + 8), 7);
  CHECK_EQ(rd32(pkt + 12), 280);
  CHECK_EQ(rd32(pkt + 16), 1120);
  CHECK_EQ(rd16(pkt + 20), 40);
  CHECK_EQ(rd16(pkt + 22), 160);
  CHECK_EQ(rd32(pkt + 24), 0);
  CHECK_EQ(rd16(pkt + 28), 880);
  CHECK_EQ(pkt[30], 3);
  CHECK_EQ(pkt[31], 2);
  CHECK_EQ(rd16(pkt + PKT_EMG_OFFSET), 100);
  CHECK_EQ(rd16(pkt + PKT_EMG_OFFSET + 2 * 119), 2480);
  CHECK_EQ((int32_t)rd32(pkt + PKT_AUDIO_OFFSET), -8388608);
  CHECK_EQ((int32_t)rd32(pkt + PKT_AUDIO_OFFSET + 4 * 159), 8388607);
  for (int i = 912; i < 1020; i++) CHECK_EQ(pkt[i], 0);
  CHECK_EQ(rd32(pkt + PKT_CRC_OFFSET), crc32_update(0, pkt, PKT_CRC_OFFSET));

  if (argc > 1) { /* sample for the Python cross-check (CTest packet_py) */
    FILE *f = fopen(argv[1], "wb");
    CHECK(f != NULL);
    if (f) {
      CHECK_EQ(fwrite(pkt, 1, PKT_SIZE, f), PKT_SIZE);
      fclose(f);
    }
  }

  CHECK(sat_flag(4095));
  CHECK(sat_flag(PKT_EMG_SAT_HI));
  CHECK(sat_flag(PKT_EMG_SAT_LO));
  CHECK(sat_flag(0));
  CHECK(!sat_flag(PKT_EMG_SAT_HI - 1));
  CHECK(!sat_flag(PKT_EMG_SAT_LO + 1));
  TEST_END();
}
```

`tests/host/test_audio_decode.c`:

```c
#include "audio_decode.h"
#include "test_util.h"

int main(void)
{
  CHECK_EQ(audio_sign_extend24(0x000000u), 0);
  CHECK_EQ(audio_sign_extend24(0x7FFFFFu), 8388607);
  CHECK_EQ(audio_sign_extend24(0x800000u), -8388608);
  CHECK_EQ(audio_sign_extend24(0xFFFFFFu), -1);
  CHECK_EQ(audio_sign_extend24(0xFF000001u), 1);  /* bits 31..24 ignored */
  CHECK_EQ(audio_sign_extend24(0xFFFFFFFEu), -2); /* already sign-extended input */

  const uint32_t st[8] = {0x000001u, 0u, 0xFFFFFFu, 0u, 0x800000u, 5u, 0x7FFFFFu, 0u};
  int32_t out[4];
  audio_extract_left(st, out, 4);
  CHECK_EQ(out[0], 1);
  CHECK_EQ(out[1], -1);
  CHECK_EQ(out[2], -8388608);
  CHECK_EQ(out[3], 8388607);
  CHECK_EQ(audio_right_activity(st, 4), 1);
  TEST_END();
}
```

`tests/host/test_acq_logic.c`:

```c
#include "acq_logic.h"
#include "test_util.h"

static acq_step_t step(uint32_t *next, uint32_t e, uint32_t a, uint32_t *lost, uint32_t *k)
{
  *k = 0xFFFFFFFFu;
  return acq_select(next, e, a, lost, k);
}

int main(void)
{
  uint32_t next, lost, k;

  /* nothing completed yet */
  next = 0; lost = 0;
  CHECK_EQ(step(&next, 0, 0, &lost, &k), ACQ_NONE);
  CHECK_EQ(step(&next, 1, 0, &lost, &k), ACQ_NONE); /* audio window 0 pending */

  /* steady state: both streams finished window 0 */
  CHECK_EQ(step(&next, 1, 1, &lost, &k), ACQ_BUILD);
  CHECK_EQ(k, 0);
  CHECK_EQ(next, 1);
  CHECK_EQ(lost, 0);
  CHECK_EQ(step(&next, 1, 1, &lost, &k), ACQ_NONE); /* already built */

  /* audio one window ahead of EMG is normal while the EMG half is in flight */
  CHECK_EQ(step(&next, 1, 2, &lost, &k), ACQ_NONE);
  CHECK_EQ(step(&next, 2, 2, &lost, &k), ACQ_BUILD);
  CHECK_EQ(k, 1);

  /* consumer starved: window 2 overwritten in audio (a = 4 means window 3 done, 4 in flight
     in half 0 = window 2's half) */
  next = 2; lost = 0;
  CHECK_EQ(step(&next, 3, 4, &lost, &k), ACQ_SKIP);
  CHECK_EQ(lost, 1);
  CHECK_EQ(next, 3);
  CHECK_EQ(step(&next, 3, 4, &lost, &k), ACQ_NONE); /* EMG window 3 not complete yet */
  CHECK_EQ(step(&next, 4, 4, &lost, &k), ACQ_BUILD);
  CHECK_EQ(k, 3);

  /* long starvation: jump to the newest window still intact in both streams */
  next = 0; lost = 0;
  CHECK_EQ(step(&next, 5, 5, &lost, &k), ACQ_SKIP);
  CHECK_EQ(lost, 4);
  CHECK_EQ(next, 4);
  CHECK_EQ(step(&next, 5, 5, &lost, &k), ACQ_BUILD);
  CHECK_EQ(k, 4);

  /* EMG two windows ahead of audio: window overwritten in EMG */
  next = 0; lost = 0;
  CHECK_EQ(step(&next, 2, 1, &lost, &k), ACQ_SKIP);
  CHECK_EQ(lost, 1);
  CHECK_EQ(next, 1);
  TEST_END();
}
```

- [ ] **Step 3: Escribir `tools/ssi_packet.py`**

```python
#!/usr/bin/env python3
"""SSI packet format (spec v0.2 §6): parse and validate 1024-byte packets.

Shared by the host tests, the SWD checks and (Plan 2) the RPi5 reader.
"""
import argparse
import struct
import sys
import zlib
from array import array

PKT_SIZE = 1024
CRC_OFFSET = 1020
MAGIC = b"SSI1"
HEADER = struct.Struct("<4sBBHIIIHHIHBB")  # 32 bytes, spec §6
FIELDS = ("magic", "version", "type", "flags", "seq", "emg_index", "audio_index", "n_emg",
          "n_audio", "dropped", "payload_len", "n_ch", "epoch")
EMG_OFFSET = 32
AUDIO_OFFSET = 272
TYPES = {1: "DATA", 2: "INFO", 3: "STATUS"}


def parse(buf: bytes) -> dict:
    if len(buf) != PKT_SIZE:
        raise ValueError(f"packet size {len(buf)} != {PKT_SIZE}")
    p = dict(zip(FIELDS, HEADER.unpack_from(buf, 0)))
    p["magic_ok"] = p["magic"] == MAGIC
    p["crc_ok"] = zlib.crc32(buf[:CRC_OFFSET]) == struct.unpack_from("<I", buf, CRC_OFFSET)[0]
    if p["type"] == 1:
        emg = array("H", buf[EMG_OFFSET:EMG_OFFSET + 2 * p["n_emg"] * p["n_ch"]])
        audio = array("i", buf[AUDIO_OFFSET:AUDIO_OFFSET + 4 * p["n_audio"]])
        if sys.byteorder != "little":
            emg.byteswap()
            audio.byteswap()
        p["emg"] = emg
        p["audio"] = audio
    return p


def value(p, key):
    for name in ("emg", "audio"):
        if key.startswith(name) and key[len(name):].isdigit():
            return p[name][int(key[len(name):])]
    return p[key]


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="validate a packet file")
    c.add_argument("file")
    c.add_argument("--expect", nargs="*", default=[], help="key=value (int, 0x.. allowed)")
    a = ap.parse_args()
    with open(a.file, "rb") as f:
        p = parse(f.read())
    ok = p["magic_ok"] and p["crc_ok"]
    print(" ".join(f"{k}={p[k]}" for k in FIELDS if k != "magic"),
          f"magic_ok={p['magic_ok']} crc_ok={p['crc_ok']}")
    for item in a.expect:
        key, want = item.split("=", 1)
        got = value(p, key)
        if got != int(want, 0):
            print(f"MISMATCH {key}: got {got}, expected {want}")
            ok = False
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Compilar las pruebas y verificar que fallan**

Run:
```bash
cd ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6/ssi_capture/tests/host
cmake -S . -B build -G Ninja >/dev/null && cmake --build build 2>&1 | tail -3
```
Expected: error de compilación (`crc32.h: No such file or directory`).

- [ ] **Step 5: Implementar `crc32`**

`FSBL/App/Inc/crc32.h`:

```c
#ifndef CRC32_H
#define CRC32_H

#include <stddef.h>
#include <stdint.h>

/* CRC-32/ISO-HDLC, identical to zlib.crc32: crc = crc32_update(0, buf, len).
   Software (not the CRC peripheral): ~100 kB/s needs no hardware and the same code
   runs in the host tests. */
uint32_t crc32_update(uint32_t crc, const void *data, size_t len);

#endif
```

`FSBL/App/Src/crc32.c`:

```c
#include "crc32.h"

/* Reflected polynomial 0xEDB88320, one nibble per step. */
static const uint32_t k_nibble[16] = {
    0x00000000u, 0x1DB71064u, 0x3B6E20C8u, 0x26D930ACu, 0x76DC4190u, 0x6B6B51F4u,
    0x4DB26158u, 0x5005713Cu, 0xEDB88320u, 0xF00F9344u, 0xD6D6A3E8u, 0xCB61B38Cu,
    0x9B64C2B0u, 0x86D3D2D4u, 0xA00AE278u, 0xBDBDF21Cu,
};

uint32_t crc32_update(uint32_t crc, const void *data, size_t len)
{
  const uint8_t *p = (const uint8_t *)data;
  crc = ~crc;
  while (len--) {
    crc ^= *p++;
    crc = (crc >> 4) ^ k_nibble[crc & 0x0Fu];
    crc = (crc >> 4) ^ k_nibble[crc & 0x0Fu];
  }
  return ~crc;
}
```

- [ ] **Step 6: Implementar `packet`**

`FSBL/App/Inc/packet.h`:

```c
#ifndef PACKET_H
#define PACKET_H

#include <stddef.h>
#include <stdint.h>

/* Wire format of spec v0.2 §6 (little-endian, 1024-byte packets). */
#define PKT_SIZE          1024u
#define PKT_HDR_SIZE      32u
#define PKT_CRC_OFFSET    1020u
#define PKT_MAGIC         0x31495353u /* bytes "SSI1" */
#define PKT_VERSION       1u
#define PKT_EMG_OFFSET    32u
#define PKT_AUDIO_OFFSET  272u

enum { PKT_DATA = 1, PKT_INFO = 2, PKT_STATUS = 3 };

#define PKT_F_AUDIO_VALID 0x0001u
#define PKT_F_EMG_SAT     0x0002u
#define PKT_F_DROPPED     0x0004u
#define PKT_F_DMA_ERR     0x0008u

/* EMG codes at or beyond these limits flag saturation (b1). */
#define PKT_EMG_SAT_LO    5u
#define PKT_EMG_SAT_HI    4090u

typedef struct {
  uint8_t type;
  uint16_t flags;
  uint32_t seq;
  uint32_t emg_index;
  uint32_t audio_index;
  uint16_t n_emg;
  uint16_t n_audio;
  uint32_t dropped;
  uint16_t payload_len;
  uint8_t n_ch;
  uint8_t epoch;
} pkt_header_t;

void pkt_write_header(uint8_t *buf, const pkt_header_t *h);
/* Zero-fills [used, 1020) and stores the CRC-32 of bytes 0..1019 at 1020. */
void pkt_finalize(uint8_t *buf, size_t used);
/* DATA: emg = u16[n_emg][n_ch] interleaved, audio = i32[n_audio]. Fills h->type and
   h->payload_len and ORs PKT_F_EMG_SAT into h->flags when a code is saturated. */
void pkt_build_data(uint8_t *buf, pkt_header_t *h, const uint16_t *emg, const int32_t *audio);

#endif
```

`FSBL/App/Src/packet.c`:

```c
#include "packet.h"

#include <string.h>

#include "crc32.h"

static void put_u16(uint8_t *p, uint16_t v)
{
  p[0] = (uint8_t)v;
  p[1] = (uint8_t)(v >> 8);
}

static void put_u32(uint8_t *p, uint32_t v)
{
  p[0] = (uint8_t)v;
  p[1] = (uint8_t)(v >> 8);
  p[2] = (uint8_t)(v >> 16);
  p[3] = (uint8_t)(v >> 24);
}

void pkt_write_header(uint8_t *buf, const pkt_header_t *h)
{
  put_u32(buf + 0, PKT_MAGIC);
  buf[4] = PKT_VERSION;
  buf[5] = h->type;
  put_u16(buf + 6, h->flags);
  put_u32(buf + 8, h->seq);
  put_u32(buf + 12, h->emg_index);
  put_u32(buf + 16, h->audio_index);
  put_u16(buf + 20, h->n_emg);
  put_u16(buf + 22, h->n_audio);
  put_u32(buf + 24, h->dropped);
  put_u16(buf + 28, h->payload_len);
  buf[30] = h->n_ch;
  buf[31] = h->epoch;
}

void pkt_finalize(uint8_t *buf, size_t used)
{
  if (used < PKT_CRC_OFFSET) {
    memset(buf + used, 0, PKT_CRC_OFFSET - used);
  }
  put_u32(buf + PKT_CRC_OFFSET, crc32_update(0, buf, PKT_CRC_OFFSET));
}

void pkt_build_data(uint8_t *buf, pkt_header_t *h, const uint16_t *emg, const int32_t *audio)
{
  const size_t n_codes = (size_t)h->n_emg * h->n_ch;
  uint8_t *p = buf + PKT_EMG_OFFSET;
  for (size_t i = 0; i < n_codes; i++, p += 2) {
    if (emg[i] <= PKT_EMG_SAT_LO || emg[i] >= PKT_EMG_SAT_HI) {
      h->flags |= PKT_F_EMG_SAT;
    }
    put_u16(p, emg[i]);
  }
  p = buf + PKT_AUDIO_OFFSET;
  for (size_t i = 0; i < h->n_audio; i++, p += 4) {
    put_u32(p, (uint32_t)audio[i]);
  }
  h->type = PKT_DATA;
  h->payload_len = (uint16_t)(n_codes * 2u + (size_t)h->n_audio * 4u);
  pkt_write_header(buf, h);
  pkt_finalize(buf, PKT_AUDIO_OFFSET + (size_t)h->n_audio * 4u);
}
```

- [ ] **Step 7: Implementar `audio_decode`**

`FSBL/App/Inc/audio_decode.h`:

```c
#ifndef AUDIO_DECODE_H
#define AUDIO_DECODE_H

#include <stddef.h>
#include <stdint.h>

/* SAI RX words carry the INMP441's 24-bit two's complement sample right-aligned;
   bits 31..24 are ignored (zero-padded or sign-extended both decode correctly). */
static inline int32_t audio_sign_extend24(uint32_t raw)
{
  return (int32_t)((raw & 0x00FFFFFFu) ^ 0x00800000u) - 0x00800000;
}

/* stereo = [L0, R0, L1, R1, ...]; writes the left slot (L/R pin tied to GND). */
void audio_extract_left(const uint32_t *stereo, int32_t *out, size_t frames);
/* Frames whose right slot is non-zero: should stay 0 (SD is Hi-Z there, pulled down). */
uint32_t audio_right_activity(const uint32_t *stereo, size_t frames);

#endif
```

`FSBL/App/Src/audio_decode.c`:

```c
#include "audio_decode.h"

void audio_extract_left(const uint32_t *stereo, int32_t *out, size_t frames)
{
  for (size_t i = 0; i < frames; i++) {
    out[i] = audio_sign_extend24(stereo[2u * i]);
  }
}

uint32_t audio_right_activity(const uint32_t *stereo, size_t frames)
{
  uint32_t n = 0;
  for (size_t i = 0; i < frames; i++) {
    if ((stereo[2u * i + 1u] & 0x00FFFFFFu) != 0u) {
      n++;
    }
  }
  return n;
}
```

- [ ] **Step 8: Implementar `acq_logic`**

`FSBL/App/Inc/acq_logic.h`:

```c
#ifndef ACQ_LOGIC_H
#define ACQ_LOGIC_H

#include <stdint.h>

typedef enum { ACQ_NONE = 0, ACQ_BUILD, ACQ_SKIP } acq_step_t;

/* Both DMA streams are double-buffered: window k lives in half k % 2 and stays intact
   while the stream's completed-window count is exactly k + 1.
   ACQ_BUILD: window *k is complete and intact in both streams; *next = *k + 1.
   ACQ_SKIP:  windows were overwritten before packaging; *lost grows, *next advances.
   ACQ_NONE:  window *next is not complete in both streams yet. */
acq_step_t acq_select(uint32_t *next, uint32_t emg_done, uint32_t aud_done, uint32_t *lost,
                      uint32_t *k);

#endif
```

`FSBL/App/Src/acq_logic.c`:

```c
#include "acq_logic.h"

acq_step_t acq_select(uint32_t *next, uint32_t emg_done, uint32_t aud_done, uint32_t *lost,
                      uint32_t *k)
{
  const uint32_t lo = (emg_done < aud_done) ? emg_done : aud_done;
  const uint32_t hi = (emg_done < aud_done) ? aud_done : emg_done;
  if (lo == 0u || lo - 1u < *next) {
    return ACQ_NONE;
  }
  const uint32_t newest = lo - 1u; /* newest window complete in both streams */
  if (newest > *next || hi > newest + 1u) {
    /* Older windows are gone; 'newest' too if the faster stream is writing over it. */
    const uint32_t first_intact = (hi > newest + 1u) ? newest + 1u : newest;
    *lost += first_intact - *next;
    *next = first_intact;
    return ACQ_SKIP;
  }
  *k = newest;
  *next = newest + 1u;
  return ACQ_BUILD;
}
```

- [ ] **Step 9: Correr las pruebas del host**

Run:
```bash
cd ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6/ssi_capture/tests/host
cmake --build build && ctest --test-dir build --output-on-failure
```
Expected: `100% tests passed, 0 tests failed out of 6`. La prueba `packet_py` imprime `RESULT: PASS` (CRC de Python = CRC del firmware).

- [ ] **Step 10: Compilar el firmware con los módulos nuevos**

Run: `~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6/tools/fw.sh build 2>&1 | tail -4`
Expected: compila sin warnings en `App/` (los módulos puros aún no se llaman).

- [ ] **Step 11: `MEMORY.md` y commit (si Matías lo autoriza):** `feat: pure packet, CRC, audio and window-pairing logic with host tests`.

---

### Task 3: Driver del micrófono (`mic_sai`): reloj de audio, SAI2-B y DMA circular

**Files:**
- Create: `FSBL/App/Inc/mic_sai.h`, `FSBL/App/Src/mic_sai.c`
- Modify: `FSBL/App/Src/mon.c` (v2: arranca el micrófono y reporta `AUD` cada segundo)

**Interfaces:**
- Consume: `NC_MEM`, `SSI_WIN_AUDIO`, `log_printf`, `led_toggle` (Task 1); `audio_sign_extend24`, `audio_right_activity` (Task 2).
- Produce:
  - `int mic_sai_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error)`: en contexto de hilo; `flags` puede ser `TX_NULL`. Devuelve 0 o el paso que falló: −1 HSE, −2 PLL4, −3 reloj del SAI2, −4 SAI, −5 y −6 lista DMA, −7 atributos de la DMA.
  - `int mic_sai_start(void)`, `void mic_sai_stop(void)`.
  - `uint32_t mic_sai_blocks_done(void)`: ventanas de 10 ms completas desde el último start.
  - `const uint32_t *mic_sai_window(uint32_t k)`: `2*SSI_WIN_AUDIO` palabras `[L0, R0, L1, R1, ...]` de la ventana `k`, que vive en la mitad `k % 2`.
  - `uint32_t mic_sai_errors(void)`, `uint32_t mic_sai_clock_hz(void)`, `uint32_t mic_sai_hse_mode(void)` (1 = cristal, 2 = bypass digital), `void mic_sai_sck_output(int on)` (prueba P7).

**Verificado en el paquete N6 v1.4.1 (2026-10-09):**
- `NUCLEO-N657X0-Q/Examples/SAI/SAI_TDM_I2S_LoopbackDMA`: PLL4 = HSE · (24 + 9663677/2²⁴), IC7 desde PLL4, nodo GPDMA y `HAL_DMA_ConfigChannelAttributes(SEC|PRIV|SRC_SEC|DEST_SEC)`.
- `stm32n6xx_hal_sai.c`: con `AudioFrequency = SAI_AUDIO_FREQUENCY_MCKDIV`, `Mckdiv` se usa tal cual. `HAL_SAI_Receive_DMA` toma el tamaño en palabras del SAI y reescribe el nodo de la lista. `SAI_DMARxCplt` no detiene la DMA en modo `DMA_LINKEDLIST_CIRCULAR`.
- `stm32n6xx_hal_rcc.c`: `RCC_PLL_NONE` deja PLL1 (CPU) intacto.
- HSE: la configuración de placa de CubeMX (`M13_Discovery_STM32N6570-DK_..._AllConfig.ioc`) declara un cristal (`HSE-External-Oscillator`, `RCC_HSE_ON`), pero 8 ejemplos USBX del DK usan `RCC_HSE_BYPASS_DIGITAL` con PLL1 desde el HSE. El driver prueba los dos en ese orden y reporta cuál arrancó (`hse=`). Probar el modo equivocado no daña nada: el HSE simplemente no llega a listo.

- [ ] **Step 1: Cablear el micrófono (DK sin alimentación)**

INMP441: VDD → CN8-4 (+3V3), GND → CN8-6, SCK → A2 (CN7-3), WS → D6 (CN11-7), SD → D8 (CN12-1), L/R → GND.

- [ ] **Step 2: Escribir la prueba y verificar que falla**

```bash
cd ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6
tools/fw.sh build && tools/run_test.sh 6 \
  --expect 'INIT mic=0 start=0 hse=[12]' \
  --check 'INIT/0:abs(sai_ck-49152000)<=100' \
  --check 'AUD:abs(d_blk-100)<=2' \
  --check 'AUD:err==0 and rslot==0 and peak>0'
```
Expected: `RESULT: FAIL` (`MISSING: INIT ...` y ninguna línea `AUD`).

La tolerancia de `d_blk` es de ±2 % porque el log mide el tiempo con el HSI (PLL1 de la CPU), mientras que el audio sale del HSE. La relación exacta entre EMG y audio se prueba en la Task 4.

- [ ] **Step 3: `mic_sai.h`**

```c
#ifndef MIC_SAI_H
#define MIC_SAI_H

#include <stdint.h>

#include "tx_api.h"

/* INMP441 on SAI2 block B: master RX, Philips I2S, 24-bit data in 32-bit slots, both slots
   captured (left = mic with L/R to GND; right must stay silent). Audio clock: HSE 48 MHz ->
   PLL4 1179.648 MHz -> IC7 /24 = 49.152 MHz -> MCKDIV 12 -> FS = 16 kHz exactly.
   Circular DMA over two windows of SSI_WIN_AUDIO frames: window k lives in half k % 2.
   The DMA callbacks set flag_block (flag_error on SAI/DMA errors) when flags != TX_NULL. */
int mic_sai_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error);
int mic_sai_start(void);                     /* resets the window count; FS edges start here */
void mic_sai_stop(void);
uint32_t mic_sai_blocks_done(void);          /* windows completed since the last start */
const uint32_t *mic_sai_window(uint32_t k);  /* 2 * SSI_WIN_AUDIO words: L0, R0, L1, R1, ... */
uint32_t mic_sai_errors(void);
uint32_t mic_sai_clock_hz(void);             /* SAI2 kernel clock, expected 49152000 */
uint32_t mic_sai_hse_mode(void);             /* 1 crystal, 2 digital bypass, 0 not started */
void mic_sai_sck_output(int on);             /* P7: 0 = SCK pin (PE12/A2) analog, 1 = AF10 */

#endif
```

- [ ] **Step 4: `mic_sai.c`**

```c
#include "mic_sai.h"

#include "nc_mem.h"
#include "ssi_config.h"
#include "stm32n6xx_hal.h"

#define MIC_WORDS (2u * 2u * SSI_WIN_AUDIO) /* two windows x two slots per frame */

static SAI_HandleTypeDef s_sai;
static DMA_HandleTypeDef s_dma;
static DMA_QListTypeDef s_list;
static DMA_NodeTypeDef s_node NC_MEM; /* the DMA reloads it after every block */
static uint32_t s_buf[MIC_WORDS] NC_MEM;

static TX_EVENT_FLAGS_GROUP *s_flags;
static ULONG s_flag_block;
static ULONG s_flag_error;
static volatile uint32_t s_blocks;
static volatile uint32_t s_errors;
static uint32_t s_hse_mode;

/* MB1939 board config says crystal; several DK examples use the digital bypass. Keep the
   mode that reaches HSERDY (a wrong mode only times out). */
static int hse_start(void)
{
  static const uint32_t k_modes[2] = {RCC_HSE_ON, RCC_HSE_BYPASS_DIGITAL};
  RCC_OscInitTypeDef osc = {0};
  osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  osc.PLL1.PLLState = RCC_PLL_NONE;
  osc.PLL2.PLLState = RCC_PLL_NONE;
  osc.PLL3.PLLState = RCC_PLL_NONE;
  osc.PLL4.PLLState = RCC_PLL_NONE;
  for (uint32_t i = 0; i < 2u; i++) {
    osc.HSEState = k_modes[i];
    if (HAL_RCC_OscConfig(&osc) == HAL_OK) {
      s_hse_mode = i + 1u;
      return 0;
    }
    osc.HSEState = RCC_HSE_OFF;
    (void)HAL_RCC_OscConfig(&osc);
  }
  return -1;
}

/* HSE 48 MHz -> PLL4 1179.648 MHz -> IC7 /24 = 49.152 MHz. PLL1 (CPU) stays as CubeMX set it. */
static int audio_clock_init(void)
{
  RCC_OscInitTypeDef osc = {0};
  RCC_PeriphCLKInitTypeDef clk = {0};
  if (hse_start() != 0) {
    return -1;
  }
  osc.OscillatorType = RCC_OSCILLATORTYPE_NONE;
  osc.PLL1.PLLState = RCC_PLL_NONE;
  osc.PLL2.PLLState = RCC_PLL_NONE;
  osc.PLL3.PLLState = RCC_PLL_NONE;
  osc.PLL4.PLLState = RCC_PLL_ON;
  osc.PLL4.PLLSource = RCC_PLLSOURCE_HSE;
  osc.PLL4.PLLM = 1;
  osc.PLL4.PLLN = 24;
  osc.PLL4.PLLFractional = 9663677; /* 48 MHz * (24 + 9663677 / 2^24) = 1179.648 MHz */
  osc.PLL4.PLLP1 = 1;
  osc.PLL4.PLLP2 = 1;
  if (HAL_RCC_OscConfig(&osc) != HAL_OK) {
    return -2;
  }
  clk.PeriphClockSelection = RCC_PERIPHCLK_SAI2;
  clk.Sai2ClockSelection = RCC_SAI2CLKSOURCE_IC7;
  clk.ICSelection[RCC_IC7].ClockSelection = RCC_ICCLKSOURCE_PLL4;
  clk.ICSelection[RCC_IC7].ClockDivider = 24;
  if (HAL_RCCEx_PeriphCLKConfig(&clk) != HAL_OK) {
    return -3;
  }
  __HAL_RCC_SAI2_CLK_ENABLE();
  return 0;
}

static void pins_init(void)
{
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_GPIOE_CLK_ENABLE();
  g.Mode = GPIO_MODE_AF_PP;
  g.Speed = GPIO_SPEED_FREQ_LOW; /* slow edges: less SCK coupling into the A2 buffer (P7) */
  g.Alternate = GPIO_AF10_SAI2;
  g.Pull = GPIO_NOPULL;
  g.Pin = GPIO_PIN_12 | GPIO_PIN_13; /* SCK_B (A2), FS_B (D6) */
  HAL_GPIO_Init(GPIOE, &g);
  g.Pull = GPIO_PULLDOWN; /* SD is Hi-Z outside the mic's slot (INMP441 datasheet) */
  g.Pin = GPIO_PIN_7;     /* SD_B (D8) */
  HAL_GPIO_Init(GPIOE, &g);
  HAL_GPIO_ConfigPinAttributes(GPIOE, GPIO_PIN_7 | GPIO_PIN_12 | GPIO_PIN_13,
                               GPIO_PIN_SEC | GPIO_PIN_NPRIV);
}

static int sai_init(void)
{
  s_sai.Instance = SAI2_Block_B;
  s_sai.Init.AudioMode = SAI_MODEMASTER_RX;
  s_sai.Init.Synchro = SAI_ASYNCHRONOUS;
  s_sai.Init.OutputDrive = SAI_OUTPUTDRIVE_DISABLE;
  s_sai.Init.NoDivider = SAI_MASTERDIVIDER_ENABLE;
  s_sai.Init.FIFOThreshold = SAI_FIFOTHRESHOLD_EMPTY;
  s_sai.Init.AudioFrequency = SAI_AUDIO_FREQUENCY_MCKDIV;
  s_sai.Init.Mckdiv = 12; /* 49.152 MHz / 12 = 4.096 MHz = 256 x 16 kHz */
  s_sai.Init.MckOverSampling = SAI_MCK_OVERSAMPLING_DISABLE;
  s_sai.Init.SynchroExt = SAI_SYNCEXT_DISABLE;
  s_sai.Init.MckOutput = SAI_MCK_OUTPUT_DISABLE;
  s_sai.Init.MonoStereoMode = SAI_STEREOMODE;
  s_sai.Init.CompandingMode = SAI_NOCOMPANDING;
  s_sai.Init.TriState = SAI_OUTPUT_NOTRELEASED;
  s_sai.Init.PdmInit.Activation = DISABLE;
  s_sai.Init.PdmInit.MicPairsNbr = 1;
  s_sai.Init.PdmInit.ClockEnable = SAI_PDM_CLOCK1_ENABLE;
  /* Philips I2S: FS low = left slot, 24-bit data MSB first in 32-bit slots, 64 SCK per frame. */
  if (HAL_SAI_InitProtocol(&s_sai, SAI_I2S_STANDARD, SAI_PROTOCOL_DATASIZE_24BIT, 2) != HAL_OK) {
    return -4;
  }
  return 0;
}

static int dma_init(void)
{
  DMA_NodeConfTypeDef n = {0};
  __HAL_RCC_GPDMA1_CLK_ENABLE();
  n.NodeType = DMA_GPDMA_LINEAR_NODE;
  n.Init.Request = GPDMA1_REQUEST_SAI2_B;
  n.Init.BlkHWRequest = DMA_BREQ_SINGLE_BURST;
  n.Init.Direction = DMA_PERIPH_TO_MEMORY;
  n.Init.SrcInc = DMA_SINC_FIXED;
  n.Init.DestInc = DMA_DINC_INCREMENTED;
  n.Init.SrcDataWidth = DMA_SRC_DATAWIDTH_WORD;
  n.Init.DestDataWidth = DMA_DEST_DATAWIDTH_WORD;
  n.Init.SrcBurstLength = 1;
  n.Init.DestBurstLength = 1;
  n.Init.TransferAllocatedPort = DMA_SRC_ALLOCATED_PORT0 | DMA_DEST_ALLOCATED_PORT0;
  n.Init.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  n.Init.Mode = DMA_NORMAL;
  n.TriggerConfig.TriggerPolarity = DMA_TRIG_POLARITY_MASKED;
  n.TriggerConfig.TriggerSelection = GPDMA1_TRIGGER_GPDMA1_CH0_TCF;
  n.DataHandlingConfig.DataExchange = DMA_EXCHANGE_NONE;
  n.DataHandlingConfig.DataAlignment = DMA_DATA_RIGHTALIGN_ZEROPADDED;
  n.SrcSecure = DMA_CHANNEL_SRC_SEC;
  n.DestSecure = DMA_CHANNEL_DEST_SEC;
  if (HAL_DMAEx_List_BuildNode(&n, &s_node) != HAL_OK ||
      HAL_DMAEx_List_InsertNode(&s_list, NULL, &s_node) != HAL_OK ||
      HAL_DMAEx_List_SetCircularMode(&s_list) != HAL_OK) {
    return -5;
  }
  s_dma.Instance = GPDMA1_Channel0;
  s_dma.InitLinkedList.Priority = DMA_LOW_PRIORITY_HIGH_WEIGHT;
  s_dma.InitLinkedList.LinkStepMode = DMA_LSM_FULL_EXECUTION;
  s_dma.InitLinkedList.LinkAllocatedPort = DMA_LINK_ALLOCATED_PORT0;
  s_dma.InitLinkedList.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  s_dma.InitLinkedList.LinkedListMode = DMA_LINKEDLIST_CIRCULAR;
  if (HAL_DMAEx_List_Init(&s_dma) != HAL_OK || HAL_DMAEx_List_LinkQ(&s_dma, &s_list) != HAL_OK) {
    return -6;
  }
  __HAL_LINKDMA(&s_sai, hdmarx, s_dma);
  /* The FSBL runs secure: channel, source and destination secure, as in ST's example. */
  if (HAL_DMA_ConfigChannelAttributes(&s_dma, DMA_CHANNEL_SEC | DMA_CHANNEL_PRIV |
                                                  DMA_CHANNEL_SRC_SEC | DMA_CHANNEL_DEST_SEC) != HAL_OK) {
    return -7;
  }
  HAL_NVIC_SetPriority(GPDMA1_Channel0_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(GPDMA1_Channel0_IRQn);
  HAL_NVIC_SetPriority(SAI2_B_IRQn, 6, 0);
  HAL_NVIC_EnableIRQ(SAI2_B_IRQn);
  return 0;
}

int mic_sai_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error)
{
  int rc;
  s_flags = flags;
  s_flag_block = flag_block;
  s_flag_error = flag_error;
  if ((rc = audio_clock_init()) != 0) {
    return rc;
  }
  pins_init();
  if ((rc = sai_init()) != 0) {
    return rc;
  }
  return dma_init();
}

int mic_sai_start(void)
{
  s_blocks = 0u;
  return (HAL_SAI_Receive_DMA(&s_sai, (uint8_t *)s_buf, (uint16_t)MIC_WORDS) == HAL_OK) ? 0 : -1;
}

void mic_sai_stop(void)
{
  (void)HAL_SAI_DMAStop(&s_sai);
}

uint32_t mic_sai_blocks_done(void)
{
  return s_blocks;
}

const uint32_t *mic_sai_window(uint32_t k)
{
  return &s_buf[(k & 1u) * (MIC_WORDS / 2u)];
}

uint32_t mic_sai_errors(void)
{
  return s_errors;
}

uint32_t mic_sai_clock_hz(void)
{
  return HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_SAI2);
}

uint32_t mic_sai_hse_mode(void)
{
  return s_hse_mode;
}

void mic_sai_sck_output(int on)
{
  GPIO_InitTypeDef g = {0};
  g.Pin = GPIO_PIN_12;
  g.Mode = on ? GPIO_MODE_AF_PP : GPIO_MODE_ANALOG;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_LOW;
  g.Alternate = GPIO_AF10_SAI2;
  HAL_GPIO_Init(GPIOE, &g);
}

/* ISR context: count and notify, nothing else. */
static void notify(ULONG flag)
{
  if (s_flags != TX_NULL) {
    (void)tx_event_flags_set(s_flags, flag, TX_OR);
  }
}

void HAL_SAI_RxHalfCpltCallback(SAI_HandleTypeDef *hsai)
{
  if (hsai == &s_sai) {
    s_blocks++;
    notify(s_flag_block);
  }
}

void HAL_SAI_RxCpltCallback(SAI_HandleTypeDef *hsai)
{
  if (hsai == &s_sai) {
    s_blocks++;
    notify(s_flag_block);
  }
}

void HAL_SAI_ErrorCallback(SAI_HandleTypeDef *hsai)
{
  if (hsai == &s_sai) {
    s_errors++;
    notify(s_flag_error);
  }
}

void GPDMA1_Channel0_IRQHandler(void)
{
  HAL_DMA_IRQHandler(&s_dma);
}

void SAI2_B_IRQHandler(void)
{
  HAL_SAI_IRQHandler(&s_sai);
}
```

- [ ] **Step 5: `mon.c` v2 (sonda de audio)**

Reemplaza la versión 1 completa:

```c
#include "mon.h"

#include "audio_decode.h"
#include "led.h"
#include "log.h"
#include "mic_sai.h"
#include "ssi_config.h"
#include "stm32n6xx_hal.h"

#define MS_PER_TICK (1000u / TX_TIMER_TICKS_PER_SECOND)

/* Task 3 probe: last complete audio window, read straight from the DMA buffer. Good enough
   once per second; acq (Task 5) copies and validates windows properly. */
static void audio_probe(uint32_t t)
{
  const uint32_t blk = mic_sai_blocks_done();
  uint32_t peak = 0u;
  uint32_t rslot = 0u;
  uint32_t raw0 = 0u;
  if (blk > 0u) {
    const uint32_t *w = mic_sai_window(blk - 1u);
    raw0 = w[0];
    for (uint32_t i = 0; i < SSI_WIN_AUDIO; i++) {
      const int32_t s = audio_sign_extend24(w[2u * i]);
      const uint32_t a = (uint32_t)(s < 0 ? -s : s);
      if (a > peak) {
        peak = a;
      }
    }
    rslot = audio_right_activity(w, SSI_WIN_AUDIO);
  }
  log_printf("AUD t=%lu blk=%lu err=%lu peak=%lu rslot=%lu raw0=%lu", (unsigned long)t,
             (unsigned long)blk, (unsigned long)mic_sai_errors(), (unsigned long)peak,
             (unsigned long)rslot, (unsigned long)raw0);
}

void mon_thread_entry(ULONG arg)
{
  (void)arg;
  const int init = mic_sai_init(TX_NULL, 0u, 0u);
  const int start = (init == 0) ? mic_sai_start() : -99;
  log_printf("INIT mic=%d start=%d hse=%lu sai_ck=%lu", init, start,
             (unsigned long)mic_sai_hse_mode(), (unsigned long)mic_sai_clock_hz());
  for (uint32_t i = 1u;; i++) {
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 10u);
    if (i % 5u == 0u) {
      led_toggle(LED_GREEN);
    }
    if (i % 10u == 0u) {
      log_printf("TICK t=%lu tx_ms=%lu hal_ms=%lu", (unsigned long)(i / 10u),
                 (unsigned long)(tx_time_get() * MS_PER_TICK), (unsigned long)HAL_GetTick());
      audio_probe(i / 10u);
    }
  }
}
```

- [ ] **Step 6: Correr la prueba**

Run: el comando del Step 2.
Expected: `RESULT: PASS`, con `INIT mic=0 start=0 hse=1 sai_ck=49152000` (o `hse=2`) y líneas como `AUD t=3 blk=300 err=0 peak=1234 rslot=0 raw0=...`. `raw0` debe ser menor que 16777216: el dato llega alineado a la derecha en 24 bits.

- [ ] **Step 7: Silbido (parte de P3)**

```bash
python3 tools/uart_log.py --secs 8 --skip 0 --check 'AUD:err==0'
```
Silbar a unos 10 cm del micrófono durante la captura. Expected: `peak` sube de ~10³ (sala en silencio; el ruido propio del INMP441 es de ≈ −87 dBFS) a más de 5·10⁴. Opcional, con osciloscopio: A2 es una cuadrada de 1,024 MHz y D6, de 16,000 kHz al 50 %.

- [ ] **Step 8: Si falla**

| Síntoma | Qué revisar |
|---|---|
| `INIT mic=-1` | El HSE no arrancó en ningún modo. Revisar el reloj HSE en el esquemático MB1939 |
| `mic=-2` o `-3` | Configuración de PLL4 o IC7 (comparar con `SAI_TDM_I2S_LoopbackDMA`) |
| `mic=-4` | `HAL_SAI_InitProtocol` rechazó la configuración |
| `blk` no avanza y `err=0` | La DMA no recibe pedidos: `GPDMA1_REQUEST_SAI2_B`, y que `s_node` y `s_buf` estén en NC (`arm-none-eabi-nm -S` del ELF: direcciones `0x341f8...`) |
| `err>0` desde el arranque | Error de transferencia de la DMA por seguridad: agregar `HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_SAI2, RIF_ATTRIBUTE_SEC \| RIF_ATTRIBUTE_NPRIV)` al comienzo de `sai_init()` |
| `peak=0` | SD sin conectar, micrófono sin 3,3 V, o L/R a 3,3 V (en ese caso, además, `rslot>0`) |
| `rslot>0` | L/R no está a GND |

- [ ] **Step 9: Registrar en `MEMORY.md`** el modo de HSE que arrancó, `sai_ck` y el `peak` en silencio. Commit solo si Matías lo autoriza: `feat: INMP441 capture on SAI2-B with an exact 16 kHz audio clock`.

---

### Task 4: Sincronización por la FS (`sync`), ADC de 3 canales (`emg_adc`) y orden de arranque (`capture`)

**Files:**
- Create: `FSBL/App/Inc/{sync.h,emg_adc.h,capture.h}`, `FSBL/App/Src/{sync.c,emg_adc.c,capture.c}`
- Modify: `FSBL/App/Src/mon.c` (v3: arranca la captura completa y reporta `CAP` cada segundo)

**Interfaces:**
- Consume: todo `mic_sai` (Task 3), `NC_MEM`, `SSI_*`, `log_printf`, `led_toggle`.
- Produce:
  - `int sync_init(void)`, `void sync_start(void)`, `void sync_stop(void)`.
  - `int emg_adc_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error)`: devuelve 0 o el paso que falló: −1 reloj, −2 init, −3 multimodo, −4 canal, −5 calibración, −6 y −7 lista DMA, −8 atributos de la DMA.
  - `int emg_adc_start(void)`, `void emg_adc_stop(void)`, `uint32_t emg_adc_blocks_done(void)`, `uint32_t emg_adc_errors(void)`, `uint32_t emg_adc_clock_hz(void)`.
  - `const uint32_t *emg_adc_window(uint32_t k)`: `SSI_WIN_EMG*SSI_EMG_CH` palabras `[s0c0, s0c1, s0c2, s1c0, ...]`, con el código de 12 bits en los bits 11..0.
  - `capture.h`: `CAP_EVT_EMG 0x01`, `CAP_EVT_AUD 0x02`, `CAP_EVT_ERR 0x04`; `int capture_init(TX_EVENT_FLAGS_GROUP *flags)` (escribe la línea `INIT cap=…`), `int capture_start(void)`, `void capture_stop(void)`, `uint8_t capture_epoch(void)`.

**Verificado en el paquete N6 v1.4.1 (2026-10-09):**
- `NUCLEO-N657X0-Q/Examples/ADC/ADC_SingleConversion_TriggerTimer_DMA`: reloj `RCC_ADCCLKSOURCE_TIMG` con `AdcDivider`, `HAL_ADCEx_Calibration_Start(&hadc, ADC_SINGLE_ENDED)`, ADC12 en `SEC|NPRIV` en el RIF, y DMA con anchos de **palabra** desde `DR`. Por eso el búfer es `uint32_t`: así no se arriesga un acceso de media palabra a un registro del ADC.
- `stm32n6xx_hal_adc.c`: `HAL_ADC_Start_DMA` pasa `Length` a bytes según el ancho del nodo y habilita la interrupción de overrun; `ADC_DMAConvCplt` sigue llamando a los callbacks en modo circular.
- `stm32n6xx_hal_rcc_ex.c`: `HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_ADC)` devuelve la frecuencia ya dividida por `AdcDivider`. `stm32n6xx_hal_tim_ex.h`: `TIM_TIM1_ETR_GPIO = 0` (valor de reset), así que el ETR del TIM1 viene del pin.
- Reloj del ADC ≤ 50 MHz, por prudencia (el ejemplo de ST usa TIMG/6). Con 246,5 ciclos, la secuencia de 3 canales dura ≈ 15,5 µs, muy por debajo de los 250 µs entre disparos.

**Por qué `c = 3` en teoría (spec §4):** en el I²S estándar, la FS baja al comienzo de la trama (ranura izquierda) y sube a mitad de trama. El TIM1 cuenta flancos de subida desde 0 y emite el TRGO en el 4.º flanco, a mitad de la trama 3; la muestra EMG *i* se toma entonces en el flanco de subida de la trama 4*i* + 3. Si al habilitarse el SAI la FS arrancara en alto, se contaría un flanco extra y `c` valdría 2, pero seguiría siendo constante. La prueba de pulsos de la Task 5 mide el valor real.

- [ ] **Step 1: Cablear (además de lo de la Task 3)**

Puente D6 (CN11-7) → D2 (CN11-3). A4 (CN7-5) → +3V3 (CN8-4). A1 y A5 al aire: el divisor 470k/560k de la placa las lleva a 0 V.

- [ ] **Step 2: Escribir la prueba y verificar que falla**

```bash
cd ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6
tools/fw.sh build && tools/run_test.sh 6 \
  --expect 'INIT cap=0 step=0' --expect 'START rc=0 epoch=1' \
  --check 'INIT/0:abs(sai_ck-49152000)<=100 and adc_ck<=50000000' \
  --check 'CAP:abs(emgblk-audblk)<=1 and abs(d_emgblk-100)<=2' \
  --check 'CAP:eerr==0 and aerr==0' \
  --check 'CAP:e1>4000 and e0<50 and e2<50'
```
Expected: `RESULT: FAIL` (aún no existen `INIT cap` ni `CAP`).

Valores esperados: A4 a 3,3 V da 3,3 · 560/1030 = 1,794 V en el ADC, es decir, un código ≈ 4082. `emgblk` puede ir una ventana adelante de `audblk`, porque la última muestra EMG de una ventana se convierte a mitad de su última trama de audio.

- [ ] **Step 3: `sync.h` y `sync.c`**

`FSBL/App/Inc/sync.h`:

```c
#ifndef SYNC_H
#define SYNC_H

/* TIM1 counts SAI FS rising edges on ETR (PD0/D2, bridged from D6) and fires TRGO on every
   SSI_EMG_DIV-th edge: the ADC trigger is phase-locked to the audio frames (spec §4). */
int sync_init(void);
void sync_start(void); /* counter := 0, then enable: call before the SAI starts */
void sync_stop(void);

#endif
```

`FSBL/App/Src/sync.c`:

```c
#include "sync.h"

#include "ssi_config.h"
#include "stm32n6xx_hal.h"

static TIM_HandleTypeDef s_tim;

int sync_init(void)
{
  GPIO_InitTypeDef g = {0};
  TIM_ClockConfigTypeDef clk = {0};
  TIM_MasterConfigTypeDef master = {0};

  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_TIM1_CLK_ENABLE();
  g.Pin = GPIO_PIN_0; /* TIM1_ETR, D2 */
  g.Mode = GPIO_MODE_AF_PP;
  g.Pull = GPIO_PULLDOWN; /* no edges while the bridge is open or the SAI is off */
  g.Speed = GPIO_SPEED_FREQ_LOW;
  g.Alternate = GPIO_AF1_TIM1;
  HAL_GPIO_Init(GPIOD, &g);
  HAL_GPIO_ConfigPinAttributes(GPIOD, GPIO_PIN_0, GPIO_PIN_SEC | GPIO_PIN_NPRIV);

  s_tim.Instance = TIM1;
  s_tim.Init.Prescaler = 0;
  s_tim.Init.CounterMode = TIM_COUNTERMODE_UP;
  s_tim.Init.Period = SSI_EMG_DIV - 1u; /* update = TRGO on every 4th FS edge */
  s_tim.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  s_tim.Init.RepetitionCounter = 0;
  s_tim.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&s_tim) != HAL_OK) {
    return -1;
  }
  clk.ClockSource = TIM_CLOCKSOURCE_ETRMODE2; /* count ETR rising edges */
  clk.ClockPolarity = TIM_CLOCKPOLARITY_NONINVERTED;
  clk.ClockPrescaler = TIM_CLOCKPRESCALER_DIV1;
  clk.ClockFilter = 0;
  if (HAL_TIM_ConfigClockSource(&s_tim, &clk) != HAL_OK) {
    return -2;
  }
  master.MasterOutputTrigger = TIM_TRGO_UPDATE;
  master.MasterOutputTrigger2 = TIM_TRGO2_RESET;
  master.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&s_tim, &master) != HAL_OK) {
    return -3;
  }
  return 0;
}

void sync_start(void)
{
  __HAL_TIM_SET_COUNTER(&s_tim, 0u);
  (void)HAL_TIM_Base_Start(&s_tim);
}

void sync_stop(void)
{
  (void)HAL_TIM_Base_Stop(&s_tim);
}
```

- [ ] **Step 4: `emg_adc.h` y `emg_adc.c`**

`FSBL/App/Inc/emg_adc.h`:

```c
#ifndef EMG_ADC_H
#define EMG_ADC_H

#include <stdint.h>

#include "tx_api.h"

/* ADC1 regular scan, ranks 1..3 = INP10 (PA9, A1), INP16 (PF3, A4), INP8 (PB10, A5); 12 bits,
   246.5-cycle sampling, one sequence per TIM1 TRGO (4 kHz). Circular DMA over two windows of
   SSI_WIN_EMG sequences: window k lives in half k % 2. The callbacks set flag_block
   (flag_error on ADC overrun or DMA error) when flags != TX_NULL. */
int emg_adc_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error);
int emg_adc_start(void);                     /* arms the ADC: conversions start at the next TRGO */
void emg_adc_stop(void);
uint32_t emg_adc_blocks_done(void);          /* windows completed since the last start */
const uint32_t *emg_adc_window(uint32_t k);  /* SSI_WIN_EMG * SSI_EMG_CH words: s0c0, s0c1, ... */
uint32_t emg_adc_errors(void);
uint32_t emg_adc_clock_hz(void);             /* ADC kernel clock after the divider */

#endif
```

`FSBL/App/Src/emg_adc.c`:

```c
#include "emg_adc.h"

#include "nc_mem.h"
#include "ssi_config.h"
#include "stm32n6xx_hal.h"

#define EMG_WORDS  (2u * SSI_WIN_EMG * SSI_EMG_CH) /* two windows, one word per conversion */
#define ADC_MAX_HZ 50000000u                       /* conservative; ST's example runs TIMG/6 */

static ADC_HandleTypeDef s_adc;
static DMA_HandleTypeDef s_dma;
static DMA_QListTypeDef s_list;
static DMA_NodeTypeDef s_node NC_MEM;
static uint32_t s_buf[EMG_WORDS] NC_MEM;

static TX_EVENT_FLAGS_GROUP *s_flags;
static ULONG s_flag_block;
static ULONG s_flag_error;
static volatile uint32_t s_blocks;
static volatile uint32_t s_errors;

static int clock_init(void)
{
  RCC_PeriphCLKInitTypeDef clk = {0};
  clk.PeriphClockSelection = RCC_PERIPHCLK_ADC;
  clk.AdcClockSelection = RCC_ADCCLKSOURCE_TIMG;
  clk.AdcDivider = (HAL_RCCEx_GetTIMGFreq() + ADC_MAX_HZ - 1u) / ADC_MAX_HZ;
  if (HAL_RCCEx_PeriphCLKConfig(&clk) != HAL_OK || emg_adc_clock_hz() > ADC_MAX_HZ) {
    return -1;
  }
  __HAL_RCC_ADC12_CLK_ENABLE();
  /* Same RIF setting as ST's ADC example: ADC12 secure, unprivileged access allowed. */
  HAL_RIF_RISC_SetSlaveSecureAttributes(RIF_RISC_PERIPH_INDEX_ADC12,
                                        RIF_ATTRIBUTE_SEC | RIF_ATTRIBUTE_NPRIV);
  return 0;
}

static void pins_init(void)
{
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOF_CLK_ENABLE();
  g.Mode = GPIO_MODE_ANALOG;
  g.Pull = GPIO_NOPULL;
  g.Pin = GPIO_PIN_9; /* PA9 = ADC1_INP10, A1 */
  HAL_GPIO_Init(GPIOA, &g);
  g.Pin = GPIO_PIN_3; /* PF3 = ADC1_INP16, A4 */
  HAL_GPIO_Init(GPIOF, &g);
  g.Pin = GPIO_PIN_10; /* PB10 = ADC1_INP8, A5 */
  HAL_GPIO_Init(GPIOB, &g);
  HAL_GPIO_ConfigPinAttributes(GPIOA, GPIO_PIN_9, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOF, GPIO_PIN_3, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOB, GPIO_PIN_10, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
}

static int adc_init(void)
{
  static const uint32_t k_channel[SSI_EMG_CH] = {ADC_CHANNEL_10, ADC_CHANNEL_16, ADC_CHANNEL_8};
  static const uint32_t k_rank[SSI_EMG_CH] = {ADC_REGULAR_RANK_1, ADC_REGULAR_RANK_2,
                                              ADC_REGULAR_RANK_3};
  ADC_MultiModeTypeDef mm = {0};
  ADC_ChannelConfTypeDef ch = {0};

  s_adc.Instance = ADC1;
  s_adc.Init.Resolution = ADC_RESOLUTION_12B;
  s_adc.Init.GainCompensation = 0;
  s_adc.Init.ScanConvMode = ADC_SCAN_ENABLE;
  s_adc.Init.EOCSelection = ADC_EOC_SEQ_CONV;
  s_adc.Init.LowPowerAutoWait = DISABLE;
  s_adc.Init.ContinuousConvMode = DISABLE;
  s_adc.Init.NbrOfConversion = SSI_EMG_CH;
  s_adc.Init.DiscontinuousConvMode = DISABLE;
  s_adc.Init.ExternalTrigConv = ADC_EXTERNALTRIG_T1_TRGO;
  s_adc.Init.ExternalTrigConvEdge = ADC_EXTERNALTRIGCONVEDGE_RISING;
  s_adc.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DMA_CIRCULAR;
  s_adc.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
  s_adc.Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;
  s_adc.Init.OversamplingMode = DISABLE;
  if (HAL_ADC_Init(&s_adc) != HAL_OK) {
    return -2;
  }
  mm.Mode = ADC_MODE_INDEPENDENT;
  if (HAL_ADCEx_MultiModeConfigChannel(&s_adc, &mm) != HAL_OK) {
    return -3;
  }
  ch.SamplingTime = ADC_SAMPLETIME_246CYCLES_5; /* source: TSZ122 buffer of the DK */
  ch.SingleDiff = ADC_SINGLE_ENDED;
  ch.OffsetNumber = ADC_OFFSET_NONE;
  ch.Offset = 0;
  for (uint32_t i = 0; i < SSI_EMG_CH; i++) {
    ch.Channel = k_channel[i];
    ch.Rank = k_rank[i];
    if (HAL_ADC_ConfigChannel(&s_adc, &ch) != HAL_OK) {
      return -4;
    }
  }
  if (HAL_ADCEx_Calibration_Start(&s_adc, ADC_SINGLE_ENDED) != HAL_OK) {
    return -5;
  }
  return 0;
}

static int dma_init(void)
{
  DMA_NodeConfTypeDef n = {0};
  __HAL_RCC_GPDMA1_CLK_ENABLE();
  n.NodeType = DMA_GPDMA_LINEAR_NODE;
  n.Init.Request = GPDMA1_REQUEST_ADC1;
  n.Init.BlkHWRequest = DMA_BREQ_SINGLE_BURST;
  n.Init.Direction = DMA_PERIPH_TO_MEMORY;
  n.Init.SrcInc = DMA_SINC_FIXED;
  n.Init.DestInc = DMA_DINC_INCREMENTED;
  n.Init.SrcDataWidth = DMA_SRC_DATAWIDTH_WORD;
  n.Init.DestDataWidth = DMA_DEST_DATAWIDTH_WORD;
  n.Init.SrcBurstLength = 1;
  n.Init.DestBurstLength = 1;
  n.Init.TransferAllocatedPort = DMA_SRC_ALLOCATED_PORT0 | DMA_DEST_ALLOCATED_PORT0;
  n.Init.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  n.Init.Mode = DMA_NORMAL;
  n.TriggerConfig.TriggerPolarity = DMA_TRIG_POLARITY_MASKED;
  n.TriggerConfig.TriggerSelection = GPDMA1_TRIGGER_GPDMA1_CH0_TCF;
  n.DataHandlingConfig.DataExchange = DMA_EXCHANGE_NONE;
  n.DataHandlingConfig.DataAlignment = DMA_DATA_RIGHTALIGN_ZEROPADDED;
  n.SrcSecure = DMA_CHANNEL_SRC_SEC;
  n.DestSecure = DMA_CHANNEL_DEST_SEC;
  if (HAL_DMAEx_List_BuildNode(&n, &s_node) != HAL_OK ||
      HAL_DMAEx_List_InsertNode(&s_list, NULL, &s_node) != HAL_OK ||
      HAL_DMAEx_List_SetCircularMode(&s_list) != HAL_OK) {
    return -6;
  }
  s_dma.Instance = GPDMA1_Channel1;
  s_dma.InitLinkedList.Priority = DMA_LOW_PRIORITY_HIGH_WEIGHT;
  s_dma.InitLinkedList.LinkStepMode = DMA_LSM_FULL_EXECUTION;
  s_dma.InitLinkedList.LinkAllocatedPort = DMA_LINK_ALLOCATED_PORT0;
  s_dma.InitLinkedList.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  s_dma.InitLinkedList.LinkedListMode = DMA_LINKEDLIST_CIRCULAR;
  if (HAL_DMAEx_List_Init(&s_dma) != HAL_OK || HAL_DMAEx_List_LinkQ(&s_dma, &s_list) != HAL_OK) {
    return -7;
  }
  __HAL_LINKDMA(&s_adc, DMA_Handle, s_dma);
  if (HAL_DMA_ConfigChannelAttributes(&s_dma, DMA_CHANNEL_SEC | DMA_CHANNEL_PRIV |
                                                  DMA_CHANNEL_SRC_SEC | DMA_CHANNEL_DEST_SEC) != HAL_OK) {
    return -8;
  }
  HAL_NVIC_SetPriority(GPDMA1_Channel1_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(GPDMA1_Channel1_IRQn);
  HAL_NVIC_SetPriority(ADC1_2_IRQn, 6, 0); /* overrun only: HAL_ADC_Start_DMA enables just OVR */
  HAL_NVIC_EnableIRQ(ADC1_2_IRQn);
  return 0;
}

int emg_adc_init(TX_EVENT_FLAGS_GROUP *flags, ULONG flag_block, ULONG flag_error)
{
  int rc;
  s_flags = flags;
  s_flag_block = flag_block;
  s_flag_error = flag_error;
  if ((rc = clock_init()) != 0) {
    return rc;
  }
  pins_init();
  if ((rc = adc_init()) != 0) {
    return rc;
  }
  return dma_init();
}

int emg_adc_start(void)
{
  s_blocks = 0u;
  return (HAL_ADC_Start_DMA(&s_adc, s_buf, EMG_WORDS) == HAL_OK) ? 0 : -1;
}

void emg_adc_stop(void)
{
  (void)HAL_ADC_Stop_DMA(&s_adc);
}

uint32_t emg_adc_blocks_done(void)
{
  return s_blocks;
}

const uint32_t *emg_adc_window(uint32_t k)
{
  return &s_buf[(k & 1u) * (EMG_WORDS / 2u)];
}

uint32_t emg_adc_errors(void)
{
  return s_errors;
}

uint32_t emg_adc_clock_hz(void)
{
  return HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_ADC);
}

/* ISR context: count and notify, nothing else. */
static void notify(ULONG flag)
{
  if (s_flags != TX_NULL) {
    (void)tx_event_flags_set(s_flags, flag, TX_OR);
  }
}

void HAL_ADC_ConvHalfCpltCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc == &s_adc) {
    s_blocks++;
    notify(s_flag_block);
  }
}

void HAL_ADC_ConvCpltCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc == &s_adc) {
    s_blocks++;
    notify(s_flag_block);
  }
}

void HAL_ADC_ErrorCallback(ADC_HandleTypeDef *hadc)
{
  if (hadc == &s_adc) {
    s_errors++;
    notify(s_flag_error);
  }
}

void GPDMA1_Channel1_IRQHandler(void)
{
  HAL_DMA_IRQHandler(&s_dma);
}

void ADC1_2_IRQHandler(void)
{
  HAL_ADC_IRQHandler(&s_adc);
}
```

- [ ] **Step 5: `capture.h` y `capture.c`**

`FSBL/App/Inc/capture.h`:

```c
#ifndef CAPTURE_H
#define CAPTURE_H

#include <stdint.h>

#include "tx_api.h"

/* Driver events, set from the DMA callbacks into the group given to capture_init(). */
#define CAP_EVT_EMG 0x01u /* emg_adc finished a window */
#define CAP_EVT_AUD 0x02u /* mic_sai finished a window */
#define CAP_EVT_ERR 0x04u /* SAI, ADC or DMA error */

/* Owns the start order that fixes c (spec §4). Single caller: acq (Task 5) or mon (Task 4). */
int capture_init(TX_EVENT_FLAGS_GROUP *flags); /* thread context; logs "INIT cap=..." */
int capture_start(void);                       /* restarts if running; epoch++ */
void capture_stop(void);
uint8_t capture_epoch(void);

#endif
```

`FSBL/App/Src/capture.c`:

```c
#include "capture.h"

#include "emg_adc.h"
#include "log.h"
#include "mic_sai.h"
#include "sync.h"

static uint8_t s_epoch;
static int s_running;

int capture_init(TX_EVENT_FLAGS_GROUP *flags)
{
  int step = 1;
  int rc = mic_sai_init(flags, CAP_EVT_AUD, CAP_EVT_ERR);
  if (rc == 0) {
    step = 2;
    rc = emg_adc_init(flags, CAP_EVT_EMG, CAP_EVT_ERR);
  }
  if (rc == 0) {
    step = 3;
    rc = sync_init();
  }
  log_printf("INIT cap=%d step=%d hse=%lu sai_ck=%lu adc_ck=%lu", rc, (rc == 0) ? 0 : step,
             (unsigned long)mic_sai_hse_mode(), (unsigned long)mic_sai_clock_hz(),
             (unsigned long)emg_adc_clock_hz());
  return rc;
}

int capture_start(void)
{
  if (s_running) {
    capture_stop();
  }
  s_epoch++;
  /* Fixed order, fixed c: the ADC waits for TRGO, TIM1 counts FS edges from 0, and only then
     the SAI produces its first FS edge. */
  if (emg_adc_start() != 0) {
    return -1;
  }
  sync_start();
  if (mic_sai_start() != 0) {
    sync_stop();
    emg_adc_stop();
    return -2;
  }
  s_running = 1;
  return 0;
}

void capture_stop(void)
{
  mic_sai_stop(); /* no FS edges after this: no partial EMG sequence */
  sync_stop();
  emg_adc_stop();
  s_running = 0;
}

uint8_t capture_epoch(void)
{
  return s_epoch;
}
```

- [ ] **Step 6: `mon.c` v3**

Reemplaza la versión 2 completa:

```c
#include "mon.h"

#include "capture.h"
#include "emg_adc.h"
#include "led.h"
#include "log.h"
#include "mic_sai.h"

void mon_thread_entry(ULONG arg)
{
  (void)arg;
  const int init = capture_init(TX_NULL); /* nobody waits on the flags yet */
  const int start = (init == 0) ? capture_start() : -99;
  log_printf("START rc=%d epoch=%u", start, (unsigned)capture_epoch());
  for (uint32_t i = 1u;; i++) {
    tx_thread_sleep(TX_TIMER_TICKS_PER_SECOND / 10u);
    if (i % 5u == 0u) {
      led_toggle(LED_GREEN);
    }
    if (i % 10u == 0u) {
      const uint32_t eb = emg_adc_blocks_done();
      const uint32_t *w = (eb > 0u) ? emg_adc_window(eb - 1u) : TX_NULL;
      log_printf("CAP t=%lu emgblk=%lu audblk=%lu eerr=%lu aerr=%lu e0=%lu e1=%lu e2=%lu",
                 (unsigned long)(i / 10u), (unsigned long)eb, (unsigned long)mic_sai_blocks_done(),
                 (unsigned long)emg_adc_errors(), (unsigned long)mic_sai_errors(),
                 (unsigned long)(w ? w[0] : 0u), (unsigned long)(w ? w[1] : 0u),
                 (unsigned long)(w ? w[2] : 0u));
    }
  }
}
```

- [ ] **Step 7: Correr la prueba**

Run: el comando del Step 2.
Expected: `RESULT: PASS`. Ejemplo: `INIT cap=0 step=0 hse=1 sai_ck=49152000 adc_ck=50000000`, `START rc=0 epoch=1` y `CAP t=3 emgblk=300 audblk=300 eerr=0 aerr=0 e0=2 e1=4081 e2=1`. Esto cubre R1 (4000 muestras/s por índices) y la primera parte de R3: EMG y audio avanzan juntos porque los cuenta el mismo reloj.

- [ ] **Step 8: Prueba negativa del puente**

Sacar el puente D6 → D2 y correr:

```bash
tools/run_test.sh 4 --check 'CAP:emgblk==0 and audblk>0'
```
Expected: `RESULT: PASS`. Sin FS en el ETR no hay disparos del ADC, y el audio sigue corriendo. Esto muestra que el EMG depende solo de la FS. Volver a poner el puente.

- [ ] **Step 9: Si falla**

| Síntoma | Qué revisar |
|---|---|
| `INIT cap=<n> step=2` | `emg_adc_init` devolvió `n` (ver la lista de códigos en Interfaces) |
| `INIT cap=<n> step=3` | `sync_init`: TIM1, ETR o TRGO |
| `emgblk=0` con el puente puesto | FS en D2 con el osciloscopio; AF1 de PD0; `TIM_CLOCKSOURCE_ETRMODE2` |
| `emgblk` avanza, pero `e1` ≈ 0 | A4 sin conectar a +3V3, o el orden de los rangos no corresponde a 10/16/8 |
| `eerr>0` | Overrun del ADC: la DMA no está leyendo (revisar que `s_buf` y `s_node` estén en NC) |
| `abs(emgblk-audblk)` crece | El ADC no se dispara en cada TRGO: ¿la secuencia dura más de 250 µs? (`adc_ck` muy bajo) |

- [ ] **Step 10: Registrar en `MEMORY.md`** (`adc_ck`, códigos de A4 a 3,3 V y al aire). Commit solo si Matías lo autoriza: `feat: FS-locked 4 kHz EMG acquisition (TIM1 ETR, ADC1 scan, DMA)`.

---

### Task 5: Hilo `acq`, paquetes DATA, consumidor provisional y pruebas P3, P4 y P7

**Files:**
- Modify: `FSBL/App/Inc/acq_logic.h`, `FSBL/App/Src/acq_logic.c`, `tests/host/test_acq_logic.c` (raíz cuadrada entera para el RMS)
- Create: `FSBL/App/Inc/{acq.h,diag.h,testpulse.h,sink.h}`, `FSBL/App/Src/{acq.c,diag.c,testpulse.c,sink.c}`
- Modify: `FSBL/App/Inc/mon.h`, `FSBL/App/Src/mon.c` (final), `FSBL/App/Src/app.c` (final)
- Create: `tools/swd.py`, `tools/diag.py`

**Interfaces:**
- Consume: Tasks 1–4 (`acq_select`, `pkt_build_data`, `pkt_header_t`, `PKT_*`, `audio_extract_left`, `audio_right_activity`, `crc32_update`, `capture_*`, `CAP_EVT_*`, `mic_sai_*`, `emg_adc_*`); `tools/ssi_packet.py` (`parse`, `PKT_SIZE`).
- Produce:
  - `uint32_t acq_isqrt64(uint64_t v)`: lógica pura, probada en el PC.
  - `acq.h`: `ACQ_EVT_RESTART 0x10`, `ACQ_EVT_DIAG 0x20`, `acq_stats_t`, `acq_cfg_t {flags, pool, out, stats}`, `void acq_configure(const acq_cfg_t *cfg)`, `void acq_thread_entry(ULONG arg)`, `void acq_request_restart(void)`, `void acq_request_diag(void)`.
  - `diag.h`: `DIAG_WINDOWS 100`, `diag_hdr_t`, `void diag_arm(uint32_t min_window)`, `void diag_feed(uint32_t k, uint8_t epoch, const uint32_t *raw, const int32_t *audio, const uint16_t *emg)`. Solo los llama `acq`.
  - `testpulse.h`: `void testpulse_init(void)`, `void testpulse_thread_entry(ULONG arg)`, `void testpulse_set(int on)`.
  - `sink.h`: `sink_stats_t {rx, crc_err, gap, ainv}`, `sink_cfg_t {in, stats}`, `void sink_configure(const sink_cfg_t *cfg)`, `void sink_thread_entry(ULONG arg)`.
  - `mon.h`: `mon_cfg_t {acq_stats, sink_stats}`, `void mon_configure(const mon_cfg_t *cfg)`, `void mon_thread_entry(ULONG arg)`.
  - Símbolos que las herramientas leen o escriben por SWD: `s_mon_dbg_cmd` (buzón de comandos, en NC), `s_diag` (89 312 B) y `s_sink_sample` (1024 B).
  - `tools/swd.py sym|cmd|sample`; `tools/diag.py audio|emg|noise|pulse`.

**Hilos y objetos (spec §5):** `acq` con prioridad 2, `sink` 8, `testpulse` 9 y `mon` 10. Un grupo de event flags `acq` recibe los eventos de las DMA y los pedidos de `mon`. Hay un block pool de 16 × 1024 B en NC, una cola de 16 punteros a paquetes y dos colas de estadísticas: `acq` → `mon` (TX_16_ULONG) y `sink` → `mon` (TX_4_ULONG). No se comparte nada fuera de esas primitivas: `diag` lo toca solo `acq`, y el buzón `s_mon_dbg_cmd` solo `mon` y el depurador.

**Regla de copia de `acq`:** primero se copia la ventana *k* de los dos búferes DMA y después se vuelve a leer `blocks_done`. Si alguna corriente ya pasó de *k* + 1, su DMA pudo empezar a reescribir esa mitad durante la copia: la ventana se descarta y se cuenta en `lost`. El contador sube en la ISR antes de que la DMA escriba la primera palabra nueva (31 µs después en el audio, 250 µs en el EMG), así que la verificación es segura.

**Por qué `c = min(d) + 3` (prueba de pulsos, P4):** el mismo pulso de D7 entra al ADC por A1 y al SAI por SD. Sea *j* la primera trama de audio no nula y *m* la primera muestra EMG del canal 0 sobre 2048; entonces `d = j − 4m`. Si la muestra EMG *i* se toma en la trama 4*i* + *c*, `d` cae en {*c* − 3, …, *c* + 1}, y vale *c* − 3 cada vez que el pulso sube justo después de una muestra EMG (≈ 20 % de los pulsos, si la fase de los flancos es uniforme). `testpulse` da unos 45 pulsos por segundo con fase casi uniforme (retardo aleatorio de 0–2 ms). Verificado en el PC con un modelo de tiempos de la trama I²S y del ADC (2026-10-09): 0 estimaciones erradas en 900 capturas sintéticas con *c* = 2, 3 y 4, incluso sin deriva entre el HSI y el HSE. Con el retardo anterior, de 0–0,4 ms (6,4 tramas, que no es múltiplo de 4), fallaba el 0,44 % de las capturas.

- [ ] **Step 1: Prueba de `acq_isqrt64` (falla)**

Agregar al final de `tests/host/test_acq_logic.c`, antes de `TEST_END();`:

```c
  /* integer square root for the audio RMS */
  CHECK_EQ(acq_isqrt64(0u), 0);
  CHECK_EQ(acq_isqrt64(15u), 3);
  CHECK_EQ(acq_isqrt64(16u), 4);
  CHECK_EQ(acq_isqrt64(8388607ull * 8388607ull), 8388607);
  CHECK_EQ(acq_isqrt64(UINT64_MAX), 4294967295ll);
```

Run: `cd ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6/ssi_capture/tests/host && cmake --build build 2>&1 | tail -3`
Expected: error de compilación (`implicit declaration of function 'acq_isqrt64'`, que `-Werror` vuelve fatal).

- [ ] **Step 2: Implementar `acq_isqrt64`**

En `FSBL/App/Inc/acq_logic.h`, antes de `#endif`:

```c
/* floor(sqrt(v)): audio RMS in acq's statistics. */
uint32_t acq_isqrt64(uint64_t v);
```

Al final de `FSBL/App/Src/acq_logic.c`:

```c
uint32_t acq_isqrt64(uint64_t v)
{
  uint64_t r = 0u;
  uint64_t bit = 1ull << 62;
  while (bit > v) {
    bit >>= 2;
  }
  while (bit != 0u) {
    if (v >= r + bit) {
      v -= r + bit;
      r = (r >> 1) + bit;
    } else {
      r >>= 1;
    }
    bit >>= 2;
  }
  return (uint32_t)r;
}
```

Run: `cmake --build build && ctest --test-dir build --output-on-failure`
Expected: `100% tests passed, 0 tests failed out of 6`.

- [ ] **Step 3: Escribir la prueba en el DK y verificar que falla**

Cableado 5a (ver la tabla del comienzo): micrófono como en la Task 3, puente D6 → D2, y A1, A4 y A5 al punto medio del divisor 10k/10k con 100 nF (≈ 1,65 V, código ≈ 2041).

```bash
cd ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6
tools/fw.sh build && tools/run_test.sh 65 --skip 2 \
  --expect 'INIT cap=0 step=0' --reject 'ERR ' \
  --check 'STAT:lost==0 and drop==0 and err==0 and crc==0 and gap==0' \
  --check 'STAT:d_win==100 and abs(emgblk-audblk)<=1 and abs(d_ms-1000)<=30' \
  --check 'STAT:ainv==30' \
  --check 'SIG:rslot==0 and peak>0' \
  --check 'SIG:e0lo>1700 and e0hi<2400 and e1lo>1700 and e1hi<2400 and e2lo>1700 and e2hi<2400'
```
Expected: `RESULT: FAIL` (no hay líneas `STAT` ni `SIG`).

Qué mide cada chequeo: `lost`, `drop`, `crc` y `gap` en cero durante 60 s (Review Focus 1); exactamente 100 paquetes por mensaje de estadísticas; 1 s de datos por segundo según el HSI (±3 %, R1); `ainv == 30`, o sea, los primeros 300 ms de cada `epoch` marcados como audio inválido (P3); la ranura derecha en silencio; y los tres canales en el nivel medio, sin saturar.

- [ ] **Step 4: Módulo `diag`**

`FSBL/App/Inc/diag.h`:

```c
#ifndef DIAG_H
#define DIAG_H

#include <stdint.h>

#include "ssi_config.h"

/* One-second capture of acq's decoded windows, read over SWD by tools/diag.py. The layout of
   s_diag (diag.c) is that tool's contract. Only acq calls these functions. */
#define DIAG_WINDOWS 100u

typedef struct {
  uint32_t state;        /* 0 idle, 1 filling, 2 done (D-cache cleaned) */
  uint32_t first_window; /* k of the first captured window */
  uint32_t n;            /* windows captured */
  uint32_t gaps;         /* discontinuities inside the capture (missing window or new epoch) */
  uint32_t epoch;
  uint32_t reserved[3];
} diag_hdr_t;

void diag_arm(uint32_t min_window);
void diag_feed(uint32_t k, uint8_t epoch, const uint32_t *raw, const int32_t *audio,
               const uint16_t *emg);

#endif
```

`FSBL/App/Src/diag.c`:

```c
#include "diag.h"

#include <stddef.h>
#include <string.h>

#include "stm32n6xx_hal.h"

typedef struct {
  diag_hdr_t hdr;
  uint32_t raw[2u * SSI_WIN_AUDIO];                      /* first window, stereo, as received */
  int32_t audio[DIAG_WINDOWS * SSI_WIN_AUDIO];           /* left slot, sign-extended */
  uint16_t emg[DIAG_WINDOWS * SSI_WIN_EMG * SSI_EMG_CH]; /* interleaved ch0, ch1, ch2 */
} diag_buf_t;

_Static_assert(offsetof(diag_buf_t, raw) == 32u, "tools/diag.py layout");
_Static_assert(offsetof(diag_buf_t, audio) == 1312u, "tools/diag.py layout");
_Static_assert(offsetof(diag_buf_t, emg) == 65312u, "tools/diag.py layout");
_Static_assert(sizeof(diag_buf_t) == 89312u, "tools/diag.py layout");

/* Cacheable RAM (too big for NC): cleaned to SRAM before the debugger may read it. */
static diag_buf_t s_diag __attribute__((aligned(32), used));
static uint32_t s_min;
static uint32_t s_last;

void diag_arm(uint32_t min_window)
{
  s_diag.hdr.state = 1u;
  s_diag.hdr.n = 0u;
  s_diag.hdr.gaps = 0u;
  s_min = min_window;
  SCB_CleanDCache_by_Addr(&s_diag.hdr, (int32_t)sizeof s_diag.hdr); /* no stale "2" over SWD */
}

void diag_feed(uint32_t k, uint8_t epoch, const uint32_t *raw, const int32_t *audio,
               const uint16_t *emg)
{
  diag_hdr_t *h = &s_diag.hdr;
  if (h->state != 1u || k < s_min) {
    return;
  }
  if (h->n == 0u) {
    h->first_window = k;
    h->epoch = epoch;
    memcpy(s_diag.raw, raw, sizeof s_diag.raw);
  } else if (k != s_last + 1u || epoch != h->epoch) {
    h->gaps++;
  }
  s_last = k;
  memcpy(&s_diag.audio[h->n * SSI_WIN_AUDIO], audio, SSI_WIN_AUDIO * sizeof(int32_t));
  memcpy(&s_diag.emg[h->n * SSI_WIN_EMG * SSI_EMG_CH], emg,
         SSI_WIN_EMG * SSI_EMG_CH * sizeof(uint16_t));
  if (++h->n == DIAG_WINDOWS) {
    h->state = 2u;
    SCB_CleanDCache_by_Addr(&s_diag, (int32_t)sizeof s_diag);
  }
}
```

- [ ] **Step 5: Módulo `testpulse`**

`FSBL/App/Inc/testpulse.h`:

```c
#ifndef TESTPULSE_H
#define TESTPULSE_H

#include "tx_api.h"

/* Sync test (P4): ~10 ms pulses on PD6 (D7), about 45 per second. Each rising edge is delayed
   by a random 0-2 ms busy-wait: that spans many 4-frame EMG periods (250 us each), so the
   edges land at a nearly uniform phase of that period. */
void testpulse_init(void); /* app_start: pin low, flags created */
void testpulse_thread_entry(ULONG arg);
void testpulse_set(int on); /* any thread */

#endif
```

`FSBL/App/Src/testpulse.c`:

```c
#include "testpulse.h"

#include "stm32n6xx_hal.h"

#define TP_ON 0x1u

static TX_EVENT_FLAGS_GROUP s_evt;
static uint32_t s_lcg = 12345u;

static uint32_t rnd(void)
{
  s_lcg = s_lcg * 1664525u + 1013904223u;
  return s_lcg >> 8;
}

void testpulse_init(void)
{
  GPIO_InitTypeDef g = {0};
  (void)tx_event_flags_create(&s_evt, "tp");
  __HAL_RCC_GPIOD_CLK_ENABLE();
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_6, GPIO_PIN_RESET);
  g.Pin = GPIO_PIN_6;
  g.Mode = GPIO_MODE_OUTPUT_PP;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOD, &g);
}

void testpulse_set(int on)
{
  if (on) {
    (void)tx_event_flags_set(&s_evt, TP_ON, TX_OR);
  } else {
    (void)tx_event_flags_set(&s_evt, ~(ULONG)TP_ON, TX_AND);
  }
}

void testpulse_thread_entry(ULONG arg)
{
  (void)arg;
  for (;;) {
    ULONG got;
    (void)tx_event_flags_get(&s_evt, TP_ON, TX_OR, &got, TX_WAIT_FOREVER); /* blocks while off */
    tx_thread_sleep(1u); /* low: ~10 ms */
    /* 0 to ~2 ms (depends on CPU speed and -O level; it only has to span >> 250 us). */
    for (volatile uint32_t n = rnd() % 120000u; n != 0u; n--) {
    }
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_6, GPIO_PIN_SET);
    tx_thread_sleep(1u); /* high until the next 10 ms tick */
    HAL_GPIO_WritePin(GPIOD, GPIO_PIN_6, GPIO_PIN_RESET);
  }
}
```

- [ ] **Step 6: Módulo `sink`**

`FSBL/App/Inc/sink.h`:

```c
#ifndef SINK_H
#define SINK_H

#include <stdint.h>

#include "tx_api.h"

/* Provisional packet consumer (Plan 2 replaces it with the SPI link): checks every packet as
   the RPi5 will, then releases its block. */
typedef struct {
  uint32_t rx;      /* packets received since boot */
  uint32_t crc_err; /* bad magic or CRC */
  uint32_t gap;     /* seq discontinuities (a numbered packet was dropped) */
  uint32_t ainv;    /* packets without b0 (audio valid) in the current epoch */
} sink_stats_t;     /* one TX_4_ULONG message */

typedef struct {
  TX_QUEUE *in;    /* packet pointers from acq */
  TX_QUEUE *stats; /* sink_stats_t every 100 packets */
} sink_cfg_t;

void sink_configure(const sink_cfg_t *cfg);
void sink_thread_entry(ULONG arg);

#endif
```

`FSBL/App/Src/sink.c`:

```c
#include "sink.h"

#include <string.h>

#include "crc32.h"
#include "packet.h"
#include "stm32n6xx_hal.h"

_Static_assert(sizeof(sink_stats_t) == 4u * sizeof(ULONG), "sink_stats_t is a TX_4_ULONG message");

#define SAMPLE_EVERY 100u

static sink_cfg_t s_cfg;
static sink_stats_t s_st;
static uint32_t s_last_seq;
static int s_have_seq;
static uint8_t s_epoch;
/* Copy of every 100th packet for tools/swd.py sample, cleaned to SRAM after the copy. */
static uint8_t s_sink_sample[PKT_SIZE] __attribute__((aligned(32), used));

static uint32_t rd32(const uint8_t *p)
{
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

void sink_configure(const sink_cfg_t *cfg)
{
  s_cfg = *cfg;
}

static void check(const uint8_t *pkt)
{
  const uint32_t seq = rd32(pkt + 8);
  const uint16_t flags = (uint16_t)(pkt[6] | (pkt[7] << 8));
  if (rd32(pkt) != PKT_MAGIC || rd32(pkt + PKT_CRC_OFFSET) != crc32_update(0u, pkt, PKT_CRC_OFFSET)) {
    s_st.crc_err++;
  }
  if (s_have_seq && seq != s_last_seq + 1u) {
    s_st.gap++;
  }
  s_last_seq = seq;
  s_have_seq = 1;
  if (pkt[31] != s_epoch) {
    s_epoch = pkt[31];
    s_st.ainv = 0u;
  }
  if ((flags & PKT_F_AUDIO_VALID) == 0u) {
    s_st.ainv++;
  }
}

void sink_thread_entry(ULONG arg)
{
  (void)arg;
  for (;;) {
    ULONG msg;
    if (tx_queue_receive(s_cfg.in, &msg, TX_WAIT_FOREVER) != TX_SUCCESS) {
      continue;
    }
    uint8_t *pkt = (uint8_t *)(uintptr_t)msg;
    check(pkt);
    if (++s_st.rx % SAMPLE_EVERY == 0u) {
      memcpy(s_sink_sample, pkt, PKT_SIZE);
      SCB_CleanDCache_by_Addr(s_sink_sample, (int32_t)PKT_SIZE);
      (void)tx_queue_send(s_cfg.stats, &s_st, TX_NO_WAIT);
    }
    (void)tx_block_release(pkt);
  }
}
```

- [ ] **Step 7: Módulo `acq`**

`FSBL/App/Inc/acq.h`:

```c
#ifndef ACQ_H
#define ACQ_H

#include <stdint.h>

#include "ssi_config.h"
#include "tx_api.h"

/* Requests to acq (any thread), on the same flags group as the CAP_EVT_* driver events. */
#define ACQ_EVT_RESTART 0x10u /* stop and restart the capture: new epoch, indices from 0 */
#define ACQ_EVT_DIAG    0x20u /* arm a 1 s diag capture from the first valid-audio window */

typedef struct {
  uint32_t windows;    /* packets queued since boot */
  uint32_t emg_blocks; /* windows completed in the current epoch */
  uint32_t aud_blocks;
  uint32_t lost;       /* windows overwritten before packaging, since boot */
  uint32_t drop;       /* packets dropped (pool or queue full), since boot */
  uint32_t err;        /* SAI + ADC/DMA error callbacks, since boot */
  uint32_t peak;       /* last 100 windows: max |audio| */
  uint32_t rms;        /* last 100 windows: audio rms */
  uint32_t rslot;      /* last 100 windows: frames with right-slot data (must be 0) */
  uint16_t emg_min[SSI_EMG_CH];
  uint16_t emg_max[SSI_EMG_CH];
  uint32_t epoch;
} acq_stats_t;         /* one TX_16_ULONG message (64 bytes max) */

typedef struct {
  TX_EVENT_FLAGS_GROUP *flags; /* CAP_EVT_* from the drivers + ACQ_EVT_* requests */
  TX_BLOCK_POOL *pool;         /* PKT_SIZE blocks */
  TX_QUEUE *out;               /* packet pointers, TX_1_ULONG */
  TX_QUEUE *stats;             /* acq_stats_t every 100 windows, TX_16_ULONG */
} acq_cfg_t;

void acq_configure(const acq_cfg_t *cfg); /* before the thread runs */
void acq_thread_entry(ULONG arg);
void acq_request_restart(void);
void acq_request_diag(void);

#endif
```

`FSBL/App/Src/acq.c`:

```c
#include "acq.h"

#include <string.h>

#include "acq_logic.h"
#include "audio_decode.h"
#include "capture.h"
#include "diag.h"
#include "emg_adc.h"
#include "log.h"
#include "mic_sai.h"
#include "packet.h"

_Static_assert(sizeof(acq_stats_t) <= 16u * sizeof(ULONG), "acq_stats_t must fit TX_16_ULONG");

#define STATS_WINDOWS   100u                                /* one stats message per second */
#define DIAG_MIN_WINDOW (SSI_AUDIO_STARTUP / SSI_WIN_AUDIO) /* 30: first valid-audio window */

static acq_cfg_t s_cfg;
static uint32_t s_raw[2u * SSI_WIN_AUDIO];
static int32_t s_audio[SSI_WIN_AUDIO];
static uint16_t s_emg[SSI_WIN_EMG * SSI_EMG_CH];

static uint32_t s_next;    /* next window to package (current epoch) */
static uint32_t s_seq;     /* packets numbered since boot, sent or not */
static uint32_t s_dropped; /* windows lost + packets dropped since boot (header field) */
static uint16_t s_pending; /* b2/b3 events not yet reported in a packet */
static uint8_t s_epoch;
static acq_stats_t s_st;
static uint64_t s_sq;   /* audio sum of squares in the stats period */
static uint32_t s_nwin; /* windows in the stats period */

void acq_configure(const acq_cfg_t *cfg)
{
  s_cfg = *cfg;
}

void acq_request_restart(void)
{
  (void)tx_event_flags_set(s_cfg.flags, ACQ_EVT_RESTART, TX_OR);
}

void acq_request_diag(void)
{
  (void)tx_event_flags_set(s_cfg.flags, ACQ_EVT_DIAG, TX_OR);
}

static void period_reset(void)
{
  s_st.peak = 0u;
  s_st.rslot = 0u;
  s_sq = 0u;
  s_nwin = 0u;
  for (uint32_t c = 0; c < SSI_EMG_CH; c++) {
    s_st.emg_min[c] = 0xFFFFu;
    s_st.emg_max[c] = 0u;
  }
}

static void start_capture(void)
{
  const int rc = capture_start();
  if (rc != 0) {
    log_printf("ERR capture_start=%d", rc); /* streams stopped: logging costs no data */
  }
  s_epoch = capture_epoch();
  s_next = 0u;
  period_reset();
}

static void note_loss(uint32_t n, uint32_t *counter)
{
  *counter += n;
  s_dropped += n;
  s_pending |= PKT_F_DROPPED;
}

static void update_stats(void)
{
  for (uint32_t i = 0; i < SSI_WIN_AUDIO; i++) {
    const int64_t s = s_audio[i];
    const uint32_t a = (uint32_t)(s < 0 ? -s : s);
    if (a > s_st.peak) {
      s_st.peak = a;
    }
    s_sq += (uint64_t)(s * s);
  }
  s_st.rslot += audio_right_activity(s_raw, SSI_WIN_AUDIO);
  for (uint32_t i = 0; i < SSI_WIN_EMG * SSI_EMG_CH; i++) {
    const uint32_t c = i % SSI_EMG_CH;
    if (s_emg[i] < s_st.emg_min[c]) {
      s_st.emg_min[c] = s_emg[i];
    }
    if (s_emg[i] > s_st.emg_max[c]) {
      s_st.emg_max[c] = s_emg[i];
    }
  }
}

static void build_window(uint32_t k)
{
  const uint32_t *ew = emg_adc_window(k);
  memcpy(s_raw, mic_sai_window(k), sizeof s_raw);
  for (uint32_t i = 0; i < SSI_WIN_EMG * SSI_EMG_CH; i++) {
    s_emg[i] = (uint16_t)ew[i];
  }
  /* Copy first, then check: a stream past k + 1 may have started rewriting window k's half
     during the copy. */
  if (mic_sai_blocks_done() > k + 1u || emg_adc_blocks_done() > k + 1u) {
    note_loss(1u, &s_st.lost);
    return;
  }
  audio_extract_left(s_raw, s_audio, SSI_WIN_AUDIO);
  update_stats();
  diag_feed(k, s_epoch, s_raw, s_audio, s_emg);

  pkt_header_t h = {0};
  h.flags = (uint16_t)(s_pending |
                       ((k * SSI_WIN_AUDIO >= SSI_AUDIO_STARTUP) ? PKT_F_AUDIO_VALID : 0u));
  h.seq = s_seq++;
  h.emg_index = k * SSI_WIN_EMG;
  h.audio_index = k * SSI_WIN_AUDIO;
  h.n_emg = SSI_WIN_EMG;
  h.n_audio = SSI_WIN_AUDIO;
  h.dropped = s_dropped;
  h.n_ch = SSI_EMG_CH;
  h.epoch = s_epoch;

  VOID *blk;
  if (tx_block_allocate(s_cfg.pool, &blk, TX_NO_WAIT) != TX_SUCCESS) {
    note_loss(1u, &s_st.drop); /* s_pending kept: reported on the next packet */
    return;
  }
  s_pending = 0u;
  pkt_build_data((uint8_t *)blk, &h, s_emg, s_audio);
  ULONG msg = (ULONG)(uintptr_t)blk;
  if (tx_queue_send(s_cfg.out, &msg, TX_NO_WAIT) != TX_SUCCESS) {
    (void)tx_block_release(blk);
    s_pending = (uint16_t)(h.flags & PKT_F_DMA_ERR);
    note_loss(1u, &s_st.drop);
    return;
  }
  s_st.windows++;
}

static void stats_push(void)
{
  union {
    acq_stats_t s;
    ULONG raw[16];
  } m;
  memset(&m, 0, sizeof m);
  s_st.emg_blocks = emg_adc_blocks_done();
  s_st.aud_blocks = mic_sai_blocks_done();
  s_st.err = emg_adc_errors() + mic_sai_errors();
  s_st.rms = acq_isqrt64(s_sq / ((uint64_t)s_nwin * SSI_WIN_AUDIO));
  s_st.epoch = s_epoch;
  m.s = s_st;
  (void)tx_queue_send(s_cfg.stats, m.raw, TX_NO_WAIT); /* if mon lags, skip: never block acq */
  period_reset();
}

void acq_thread_entry(ULONG arg)
{
  (void)arg;
  if (capture_init(s_cfg.flags) != 0) {
    (void)tx_thread_suspend(tx_thread_identify()); /* the INIT line names the failing step */
  }
  start_capture();
  for (;;) {
    ULONG got = 0u;
    (void)tx_event_flags_get(s_cfg.flags,
                             CAP_EVT_EMG | CAP_EVT_AUD | CAP_EVT_ERR | ACQ_EVT_RESTART | ACQ_EVT_DIAG,
                             TX_OR_CLEAR, &got, TX_TIMER_TICKS_PER_SECOND / 10u);
    if ((got & ACQ_EVT_RESTART) != 0u) {
      start_capture();
    }
    if ((got & ACQ_EVT_DIAG) != 0u) {
      diag_arm(DIAG_MIN_WINDOW);
    }
    if ((got & CAP_EVT_ERR) != 0u) {
      s_pending |= PKT_F_DMA_ERR; /* stop, ERROR state and new epoch (spec §7): ctrl, Plan 2 */
    }
    for (;;) {
      uint32_t k = 0u;
      uint32_t lost = 0u;
      const acq_step_t step =
          acq_select(&s_next, emg_adc_blocks_done(), mic_sai_blocks_done(), &lost, &k);
      if (lost != 0u) {
        note_loss(lost, &s_st.lost);
      }
      if (step == ACQ_NONE) {
        break;
      }
      if (step == ACQ_BUILD) {
        build_window(k);
        if (++s_nwin == STATS_WINDOWS) {
          stats_push();
        }
      }
    }
  }
}
```

`acq` no escribe en el log mientras captura: `log_printf` puede esperar el mutex mientras `mon` imprime una línea (~11 ms a 115 200 baud), más que una ventana de 10 ms.

- [ ] **Step 8: `mon` final**

`FSBL/App/Inc/mon.h` (reemplaza la versión 1):

```c
#ifndef MON_H
#define MON_H

#include "tx_api.h"

typedef struct {
  TX_QUEUE *acq_stats;  /* acq_stats_t, TX_16_ULONG */
  TX_QUEUE *sink_stats; /* sink_stats_t, TX_4_ULONG */
} mon_cfg_t;

void mon_configure(const mon_cfg_t *cfg); /* before the thread runs */
void mon_thread_entry(ULONG arg);

#endif
```

`FSBL/App/Src/mon.c` (reemplaza la versión 3):

```c
#include "mon.h"

#include <string.h>

#include "acq.h"
#include "led.h"
#include "log.h"
#include "mic_sai.h"
#include "nc_mem.h"
#include "sink.h"
#include "stm32n6xx_hal.h"
#include "testpulse.h"

/* Debug mailbox: tools/swd.py writes a command over SWD, mon runs it and writes 0 back.
   NC memory, so debugger and CPU see the same value; NOLOAD, so cleared at thread start. */
enum {
  CMD_NONE = 0,
  CMD_RESTART = 1,   /* new epoch */
  CMD_DIAG = 2,      /* 1 s capture from window 30 (tools/diag.py) */
  CMD_PULSE_ON = 3,  /* D7 test pulses (P4) */
  CMD_PULSE_OFF = 4,
  CMD_SCK_OFF = 5,   /* P7: SCK pin (A2) to analog; the SAI and its FS keep running */
  CMD_SCK_ON = 6,
};
static volatile uint32_t s_mon_dbg_cmd NC_MEM __attribute__((used));

static mon_cfg_t s_cfg;

void mon_configure(const mon_cfg_t *cfg)
{
  s_cfg = *cfg;
}

static void run_cmd(uint32_t cmd)
{
  switch (cmd) {
    case CMD_RESTART:
      acq_request_restart();
      break;
    case CMD_DIAG:
      acq_request_diag();
      break;
    case CMD_PULSE_ON:
      testpulse_set(1);
      break;
    case CMD_PULSE_OFF:
      testpulse_set(0);
      break;
    case CMD_SCK_OFF:
      mic_sai_sck_output(0);
      break;
    case CMD_SCK_ON:
      mic_sai_sck_output(1);
      break;
    default:
      break;
  }
  log_printf("CMD n=%lu", (unsigned long)cmd);
}

static void print_stats(uint32_t t, const acq_stats_t *a, const sink_stats_t *k)
{
  log_printf("STAT t=%lu ms=%lu ep=%lu win=%lu emgblk=%lu audblk=%lu lost=%lu drop=%lu err=%lu "
             "rx=%lu crc=%lu gap=%lu ainv=%lu",
             (unsigned long)t, (unsigned long)HAL_GetTick(), (unsigned long)a->epoch,
             (unsigned long)a->windows, (unsigned long)a->emg_blocks,
             (unsigned long)a->aud_blocks, (unsigned long)a->lost, (unsigned long)a->drop,
             (unsigned long)a->err, (unsigned long)k->rx, (unsigned long)k->crc_err,
             (unsigned long)k->gap, (unsigned long)k->ainv);
  log_printf("SIG t=%lu peak=%lu rms=%lu rslot=%lu e0lo=%u e0hi=%u e1lo=%u e1hi=%u e2lo=%u e2hi=%u",
             (unsigned long)t, (unsigned long)a->peak, (unsigned long)a->rms,
             (unsigned long)a->rslot, (unsigned)a->emg_min[0], (unsigned)a->emg_max[0],
             (unsigned)a->emg_min[1], (unsigned)a->emg_max[1], (unsigned)a->emg_min[2],
             (unsigned)a->emg_max[2]);
}

void mon_thread_entry(ULONG arg)
{
  union {
    acq_stats_t s;
    ULONG raw[16];
  } a;
  union {
    sink_stats_t s;
    ULONG raw[4];
  } k;
  uint32_t t = 0u;
  uint32_t idle = 0u;
  (void)arg;
  memset(&k, 0, sizeof k);
  s_mon_dbg_cmd = CMD_NONE;
  for (;;) {
    if (tx_queue_receive(s_cfg.acq_stats, a.raw, TX_TIMER_TICKS_PER_SECOND / 10u) == TX_SUCCESS) {
      while (tx_queue_receive(s_cfg.sink_stats, k.raw, TX_NO_WAIT) == TX_SUCCESS) {
        /* keep the newest */
      }
      print_stats(++t, &a.s, &k.s);
      led_toggle(LED_GREEN); /* blinking green = capturing (spec §5) */
      led_set(LED_RED, (a.s.err != 0u) || (k.s.crc_err != 0u));
      idle = 0u;
    } else if (++idle == 20u) { /* 2 s without data */
      log_printf("IDLE ms=%lu", (unsigned long)HAL_GetTick());
      idle = 0u;
    }
    const uint32_t cmd = s_mon_dbg_cmd;
    if (cmd != CMD_NONE) {
      run_cmd(cmd);
      s_mon_dbg_cmd = CMD_NONE;
    }
  }
}
```

- [ ] **Step 9: `app.c` final**

Reemplaza la versión 1 completa (`app_early_init` no cambia):

```c
#include "app.h"

#include "acq.h"
#include "led.h"
#include "log.h"
#include "mon.h"
#include "nc_mem.h"
#include "packet.h"
#include "sink.h"
#include "ssi_config.h"
#include "testpulse.h"
#include "tx_api.h"

extern uint32_t __snoncacheable; /* ssi_capture_fsbl.ld */
extern uint32_t __enoncacheable;

#define NC_BASE 0x341F8000u
#define NC_END  0x34200000u

#define POOL_BLOCKS 16u /* spec §5: 16 packets x 1024 B = 160 ms of data */

static TX_EVENT_FLAGS_GROUP s_acq_flags;
static TX_BLOCK_POOL s_pool;
static UCHAR s_pool_mem[POOL_BLOCKS * (PKT_SIZE + sizeof(void *))] NC_MEM; /* + block header */
static TX_QUEUE s_pkt_q;
static ULONG s_pkt_q_mem[POOL_BLOCKS];
static TX_QUEUE s_acq_stats_q;
static ULONG s_acq_stats_mem[4u * 16u];
static TX_QUEUE s_sink_stats_q;
static ULONG s_sink_stats_mem[4u * 4u];

static TX_THREAD s_acq;
static TX_THREAD s_sink;
static TX_THREAD s_tp;
static TX_THREAD s_mon;
static ULONG s_acq_stack[1024]; /* 4 KB */
static ULONG s_sink_stack[512];
static ULONG s_tp_stack[256];
static ULONG s_mon_stack[1024]; /* vsnprintf */

void app_early_init(UART_HandleTypeDef *huart)
{
  const uint32_t s = (uint32_t)&__snoncacheable;
  const uint32_t e = (uint32_t)&__enoncacheable;
  log_init(huart);
  led_init();
  log_printf("SSI capture fw %lu.%lu.%lu (%s %s)", (unsigned long)((SSI_FW_VERSION >> 16) & 0xFFu),
             (unsigned long)((SSI_FW_VERSION >> 8) & 0xFFu), (unsigned long)(SSI_FW_VERSION & 0xFFu),
             __DATE__, __TIME__);
  log_printf("CLK cpu=%lu", (unsigned long)SystemCoreClock);
  log_printf("NC 0x%08lx..0x%08lx %s", (unsigned long)s, (unsigned long)e,
             (s >= NC_BASE && e <= NC_END) ? "OK" : "FAIL");
}

void app_start(void)
{
  UINT rc = TX_SUCCESS;
  log_rtos_init();
  rc |= tx_event_flags_create(&s_acq_flags, "acq");
  rc |= tx_block_pool_create(&s_pool, "pkt_pool", PKT_SIZE, s_pool_mem, sizeof s_pool_mem);
  rc |= tx_queue_create(&s_pkt_q, "pkt_q", TX_1_ULONG, s_pkt_q_mem, sizeof s_pkt_q_mem);
  rc |= tx_queue_create(&s_acq_stats_q, "acq_st", TX_16_ULONG, s_acq_stats_mem,
                        sizeof s_acq_stats_mem);
  rc |= tx_queue_create(&s_sink_stats_q, "sink_st", TX_4_ULONG, s_sink_stats_mem,
                        sizeof s_sink_stats_mem);

  const acq_cfg_t acq = {&s_acq_flags, &s_pool, &s_pkt_q, &s_acq_stats_q};
  const sink_cfg_t sink = {&s_pkt_q, &s_sink_stats_q};
  const mon_cfg_t mon = {&s_acq_stats_q, &s_sink_stats_q};
  acq_configure(&acq);
  sink_configure(&sink);
  mon_configure(&mon);
  testpulse_init();

  /* Preemption threshold = priority: tx_user.h defines TX_DISABLE_PREEMPTION_THRESHOLD. */
  rc |= tx_thread_create(&s_acq, "acq", acq_thread_entry, 0, s_acq_stack, sizeof s_acq_stack, 2, 2,
                         TX_NO_TIME_SLICE, TX_AUTO_START);
  rc |= tx_thread_create(&s_sink, "sink", sink_thread_entry, 0, s_sink_stack, sizeof s_sink_stack,
                         8, 8, TX_NO_TIME_SLICE, TX_AUTO_START);
  rc |= tx_thread_create(&s_tp, "testpulse", testpulse_thread_entry, 0, s_tp_stack,
                         sizeof s_tp_stack, 9, 9, TX_NO_TIME_SLICE, TX_AUTO_START);
  rc |= tx_thread_create(&s_mon, "mon", mon_thread_entry, 0, s_mon_stack, sizeof s_mon_stack, 10,
                         10, TX_NO_TIME_SLICE, TX_AUTO_START);
  if (rc != TX_SUCCESS) {
    log_printf("ERR app_start rc=%u", (unsigned)rc);
  }
}
```

Uso de NC: 2560 B (audio) + 960 B (EMG) + 16 448 B (pool) + nodos y buzón ≈ 20 KB de 32 KB.

- [ ] **Step 10: Compilar y correr la prueba del Step 3**

Run: el comando del Step 3.
Expected: `RESULT: PASS` en unas 63 líneas `STAT`/`SIG`, por ejemplo `STAT t=12 ms=13077 ep=1 win=1200 emgblk=1201 audblk=1200 lost=0 drop=0 err=0 rx=1200 crc=0 gap=0 ainv=30` y `SIG t=12 peak=2311 rms=402 rslot=0 e0lo=2035 e0hi=2046 ...`. El LED verde parpadea a 0,5 Hz y el rojo queda apagado.

- [ ] **Step 11: `tools/swd.py` y verificación de un paquete real**

```python
#!/usr/bin/env python3
"""Read and write ssi_capture variables over SWD while the firmware runs.

STM32_Programmer_CLI in HOTPLUG mode (no halt, no reset) plus the ELF symbol table
(arm-none-eabi-nm). Source ~/2026-2/SSI/tools/stm32-env.sh first.

  swd.py sym NAME        address and size of a symbol
  swd.py cmd N           write the mon debug mailbox and wait until mon has run it
  swd.py sample OUT.bin  last packet sampled by sink, CRC-checked
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ssi_packet  # noqa: E402

ELF = os.path.join(HERE, "..", "ssi_capture", "FSBL", "build", "Debug", "ssi_capture_FSBL.elf")
CLI = "STM32_Programmer_CLI"
CONNECT = ["-c", "port=SWD", "mode=HOTPLUG"]


def symbol(name, elf=ELF):
    out = subprocess.run(["arm-none-eabi-nm", "-S", elf], check=True, capture_output=True,
                         text=True).stdout
    hits = [f for f in (line.split() for line in out.splitlines()) if len(f) == 4 and f[3] == name]
    if len(hits) != 1:
        raise KeyError(f"{name}: {len(hits)} matches in {elf}")
    return int(hits[0][0], 16), int(hits[0][1], 16)


def _cli(*args):
    r = subprocess.run([CLI, *CONNECT, *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{CLI} {' '.join(args)} failed:\n{r.stdout[-600:]}")
    return r.stdout


def read(addr, size):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "dump.bin")
        _cli("-u", hex(addr), str(size), path)
        with open(path, "rb") as f:
            data = f.read()
    if len(data) != size:
        raise RuntimeError(f"read {len(data)} of {size} bytes at {addr:#x}")
    return data


def read32(addr):
    return struct.unpack("<I", read(addr, 4))[0]


def write32(addr, value):
    _cli("-w32", hex(addr), hex(value))


def cmd(n, timeout=6.0):
    addr, _ = symbol("s_mon_dbg_cmd")
    write32(addr, n)
    end = time.time() + timeout
    while time.time() < end:
        if read32(addr) == 0:
            return
        time.sleep(0.2)
    raise TimeoutError(f"mon did not take command {n} (is the firmware running?)")


def sample(retries=3):
    addr, _ = symbol("s_sink_sample")
    for _ in range(retries):
        buf = read(addr, ssi_packet.PKT_SIZE)
        p = ssi_packet.parse(buf)
        if p["magic_ok"] and p["crc_ok"]:
            return buf
        time.sleep(0.3)  # torn read while sink was copying: read again
    raise RuntimeError("no valid packet in s_sink_sample")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="op", required=True)
    sub.add_parser("sym").add_argument("name")
    sub.add_parser("cmd").add_argument("n", type=int)
    sub.add_parser("sample").add_argument("out")
    a = ap.parse_args()
    if a.op == "sym":
        addr, size = symbol(a.name)
        print(f"{a.name} addr={addr:#010x} size={size}")
    elif a.op == "cmd":
        cmd(a.n)
        print(f"CMD {a.n} OK")
    else:
        with open(a.out, "wb") as f:
            f.write(sample())
        print(f"sample -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run (con el firmware corriendo después del Step 10):

```bash
cd ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6 && source ~/2026-2/SSI/tools/stm32-env.sh >/dev/null && mkdir -p out
python3 tools/swd.py sym s_mon_dbg_cmd
python3 tools/swd.py sample out/pkt.bin
python3 tools/ssi_packet.py check out/pkt.bin --expect version=1 type=1 flags=1 n_emg=40 \
  n_audio=160 n_ch=3 payload_len=880 dropped=0
```
Expected: `s_mon_dbg_cmd addr=0x341f8...` (dentro de NC) y `RESULT: PASS`. El parser que usará la RPi5 valida un paquete armado por el firmware (offsets, CRC y banderas).

- [ ] **Step 12: `tools/diag.py`**

```python
#!/usr/bin/env python3
"""1-second diagnostic captures over SWD (firmware module diag) and their analysis.

s_diag layout (diag.c): u32 header[8] = {state, first_window, n, gaps, epoch, 0, 0, 0},
u32 raw[320] at 32, i32 audio[16000] at 1312, u16 emg[4000][3] at 65312; 89312 bytes.

  diag.py audio [--tone HZ] [--out DIR]          P3: dominant tone, rms, peak, WAV
  diag.py emg [--ch N --tone HZ] [--out DIR]     P2: EMG statistics, CSV, generator tone
  diag.py noise                                  P7: EMG noise with the SCK pin on vs off
  diag.py pulse [--restarts N]                   P4: c from the D7 pulse seen on A1 and SD
"""
import argparse
import cmath
import math
import os
import struct
import sys
import time
import wave
from array import array

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import swd  # noqa: E402

FS_AUDIO, FS_EMG, CH = 16000, 4000, 3
SIZE, OFF_RAW, OFF_AUDIO, OFF_EMG = 89312, 32, 1312, 65312
CMD_RESTART, CMD_DIAG, CMD_PULSE_ON, CMD_PULSE_OFF, CMD_SCK_OFF, CMD_SCK_ON = 1, 2, 3, 4, 5, 6
SSI_SYNC_C = 3       # keep equal to ssi_config.h
EMG_THRESHOLD = 2048  # pulse test: A1 driven to 0 / 3.3 V


def capture(timeout=8.0):
    addr, size = swd.symbol("s_diag")
    if size != SIZE:
        raise RuntimeError(f"s_diag is {size} bytes, this tool expects {SIZE}")
    swd.cmd(CMD_DIAG)
    end = time.time() + timeout
    while swd.read32(addr) != 2:
        if time.time() > end:
            raise TimeoutError("diag capture did not finish")
        time.sleep(0.3)
    buf = swd.read(addr, SIZE)
    _, first, n, gaps, epoch = struct.unpack_from("<5I", buf, 0)
    raw = array("I", buf[OFF_RAW:OFF_AUDIO])
    audio = array("i", buf[OFF_AUDIO:OFF_EMG])
    emg = array("H", buf[OFF_EMG:SIZE])
    if sys.byteorder != "little":
        for x in (raw, audio, emg):
            x.byteswap()
    if n != 100 or gaps != 0:
        raise RuntimeError(f"incomplete capture: n={n} gaps={gaps}")
    return {"first": first, "epoch": epoch, "raw": raw, "audio": audio, "emg": emg}


def fft(x):
    """Iterative radix-2 FFT; len(x) must be a power of two."""
    a = [complex(v) for v in x]
    n = len(a)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    size = 2
    while size <= n:
        w = cmath.exp(-2j * math.pi / size)
        half = size // 2
        for start in range(0, n, size):
            wk = 1 + 0j
            for k in range(start, start + half):
                t = wk * a[k + half]
                a[k + half] = a[k] - t
                a[k] += t
                wk *= w
        size *= 2
    return a


def dominant(x, fs):
    """Strongest tone in Hz: Hann window, FFT, parabolic interpolation on the log magnitude."""
    m = len(x)
    n = 1 << (m - 1).bit_length()
    mean = sum(x) / m
    win = [(v - mean) * (0.5 - 0.5 * math.cos(2 * math.pi * i / (m - 1))) for i, v in enumerate(x)]
    mag = [abs(c) for c in fft(win + [0.0] * (n - m))[: n // 2]]
    k = max(range(2, n // 2 - 1), key=mag.__getitem__)
    a, b, c = (math.log(mag[k + d] + 1e-12) for d in (-1, 0, 1))
    den = a - 2 * b + c
    return (k + (0.5 * (a - c) / den if den else 0.0)) * fs / n


def stats(v):
    n = len(v)
    mean = sum(v) / n
    return mean, math.sqrt(sum((x - mean) ** 2 for x in v) / n), min(v), max(v)


def write_wav(path, audio):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(3)
        w.setframerate(FS_AUDIO)
        w.writeframes(b"".join(struct.pack("<i", s)[:3] for s in audio))


def cmd_audio(a):
    d = capture()
    au = d["audio"]
    f0 = dominant(au, FS_AUDIO)
    rms = math.sqrt(sum(s * s for s in au) / len(au))
    peak = max(abs(s) for s in au)
    print(f"AUDIO epoch={d['epoch']} first={d['first']} f0={f0:.2f} rms={rms:.0f} peak={peak} "
          f"raw0={d['raw'][0]:#010x}")
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        write_wav(os.path.join(a.out, "audio.wav"), au)
        print(f"wav -> {os.path.join(a.out, 'audio.wav')}")
    return a.tone is None or (abs(f0 - a.tone) <= 2.0 and peak > 10000)


def cmd_emg(a):
    d = capture()
    e = d["emg"]
    for c in range(CH):
        mean, std, lo, hi = stats(e[c::CH])
        print(f"EMG ch{c} mean={mean:.1f} std={std:.2f} min={lo} max={hi}")
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        path = os.path.join(a.out, "emg.csv")
        with open(path, "w") as f:
            f.write("i,ch0,ch1,ch2\n")
            for i in range(len(e) // CH):
                f.write(f"{i},{e[CH * i]},{e[CH * i + 1]},{e[CH * i + 2]}\n")
        print(f"csv -> {path}")
    if a.tone is None:
        return True
    f0 = dominant(e[a.ch::CH], FS_EMG)
    print(f"EMG ch{a.ch} f0={f0:.2f}")
    return abs(f0 - a.tone) <= 1.0


def cmd_noise(a):
    swd.cmd(CMD_SCK_ON)
    on = capture()
    swd.cmd(CMD_SCK_OFF)
    try:
        off = capture()
    finally:
        swd.cmd(CMD_SCK_ON)
    ok = True
    for c in range(CH):
        m1, s1, _, _ = stats(on["emg"][c::CH])
        m0, s0, _, _ = stats(off["emg"][c::CH])
        print(f"NOISE ch{c} std_on={s1:.3f} std_off={s0:.3f} dstd={s1 - s0:+.3f} dmean={m1 - m0:+.2f}")
        ok = ok and abs(s1 - s0) < 1.0
    return ok


def pulse_offsets(d):
    """d = j - 4m per pulse: j = first non-zero audio frame, m = first EMG ch0 sample over the
    threshold. With EMG sample i taken at frame 4i + c, d spans {c-3 .. c+1}; c = min(d) + 3."""
    au, ch0 = d["audio"], d["emg"][0::CH]
    out = []
    for j in range(1, len(au)):
        if au[j] == 0 or au[j - 1] != 0:
            continue
        for m in range(max(1, j // 4 - 4), min(len(ch0), j // 4 + 4)):
            if ch0[m] > EMG_THRESHOLD >= ch0[m - 1]:
                out.append(j - 4 * m)
                break
    return out


def cmd_pulse(a):
    swd.cmd(CMD_PULSE_ON)
    cs = []
    ok = True
    try:
        for r in range(1, a.restarts + 1):
            swd.cmd(CMD_RESTART)
            d = capture()
            ds = pulse_offsets(d)
            if len(ds) < 30:
                print(f"PULSE r={r} epoch={d['epoch']} n={len(ds)}: too few pulses (D7 -> A1 and D8?)")
                return False
            c = min(ds) + 3
            cs.append(c)
            ok = ok and max(ds) - min(ds) <= 4
            print(f"PULSE r={r} epoch={d['epoch']} n={len(ds)} dmin={min(ds)} dmax={max(ds)} c={c}")
    finally:
        swd.cmd(CMD_PULSE_OFF)
    ok = ok and len(set(cs)) == 1 and abs(cs[0]) < 16  # constant (R3); |c| * 62.5 us < 1 ms (R4)
    print(f"SYNC c={cs[0]} frames = {cs[0] * 62.5:.1f} us; SSI_SYNC_C={SSI_SYNC_C}")
    if cs[0] != SSI_SYNC_C:
        print("NOTE: set SSI_SYNC_C to the measured c in ssi_config.h and in this tool")
    return ok


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="op", required=True)
    p = sub.add_parser("audio")
    p.add_argument("--tone", type=float)
    p.add_argument("--out")
    p = sub.add_parser("emg")
    p.add_argument("--ch", type=int, default=0)
    p.add_argument("--tone", type=float)
    p.add_argument("--out")
    sub.add_parser("noise")
    p = sub.add_parser("pulse")
    p.add_argument("--restarts", type=int, default=10)
    a = ap.parse_args()
    ok = {"audio": cmd_audio, "emg": cmd_emg, "noise": cmd_noise, "pulse": cmd_pulse}[a.op](a)
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 13: P3, tono de referencia**

Con el cableado 5a, poner un celular con un generador de tonos de 1 kHz a 10–20 cm del micrófono:

```bash
python3 tools/diag.py audio --tone 1000 --out out/p3
```
Expected: `AUDIO ... f0=1000.0x ...` y `RESULT: PASS`. Escuchar `out/p3/audio.wav` (1 s): el tono debe sonar limpio, sin clics. El error de f0 refleja el reloj del celular y el HSE de la N6, y debe quedar muy por debajo de 2 Hz.

- [ ] **Step 14: P2, señal de generador (opcional, si hay generador)**

Sacar A1 del divisor y aplicar un seno de 100 Hz entre ~0,5 y 2,8 V (siempre dentro de 0–3,3 V):

```bash
python3 tools/diag.py emg --ch 0 --tone 100 --out out/p2
```
Expected: `EMG ch0 f0=100.0x` y `RESULT: PASS`; `out/p2/emg.csv` muestra el seno. Sin generador, P2 queda cubierta por los niveles de la Task 4 y por las cuentas por segundo; anotarlo en `MEMORY.md`. Devolver A1 al divisor.

- [ ] **Step 15: P7, interferencia del SCK**

```bash
python3 tools/diag.py noise
```
Expected: tres líneas `NOISE chN std_on=… std_off=… dstd=… dmean=…` y `RESULT: PASS` (|Δstd| < 1 LSB rms). Anotar `dmean` en `MEMORY.md`: la spec (§9) espera que el SCK aparezca como un offset fijo, no como ruido.

- [ ] **Step 16: P4, sincronización con 10 reinicios**

Cableado 5b: SD del micrófono fuera de D8; D7 → D8 y D7 → A1 (A1 fuera del divisor).

```bash
python3 tools/diag.py pulse --restarts 10
```
Expected: 10 líneas `PULSE r=… epoch=… n≈45 dmin=… dmax=… c=…` con el mismo `c`, seguidas de `SYNC c=…` y `RESULT: PASS`. Esto cierra R3 (`c` constante entre sesiones) y R4 (`|c|` · 62,5 µs < 1 ms; con `c` conocido, la RPi5 lo compensa).

Después, con el firmware todavía corriendo:

```bash
python3 tools/uart_log.py --secs 4 --check 'STAT:ep>=11 and lost==0 and drop==0 and err==0 and crc==0 and gap==0'
```
Expected: `RESULT: PASS`. Los reinicios no pierden ventanas ni dejan huecos en `seq`.

- [ ] **Step 17: Si `c` medido ≠ `SSI_SYNC_C`**

Poner el valor medido en `SSI_SYNC_C` (`FSBL/App/Inc/ssi_config.h`) y en `tools/diag.py`, recompilar y repetir el Step 16. Registrar la causa en `MEMORY.md` (lo más probable es el nivel inicial de la FS al habilitar el SAI).

- [ ] **Step 18: Si falla**

| Síntoma | Qué revisar |
|---|---|
| No aparecen `STAT` sino `IDLE` | La línea `INIT cap=…` dice qué paso falló; `acq` queda suspendido |
| `lost>0` | Algo bloquea a `acq` más de 10 ms: ¿un `log_printf` dentro del ciclo de `acq`? ¿Una ISR larga? |
| `drop>0` | `sink` no libera bloques: revisar `tx_block_release` y su prioridad |
| `crc>0` | El pool de paquetes debe estar en NC: `python3 tools/swd.py sym s_pool_mem` tiene que dar una dirección entre `0x341f8000` y `0x341fffff` (`nm` también lista los `static`) |
| `gap>0` con `drop=0` | `seq` se numera mal: revisar `build_window` |
| `ainv` ≠ 30 | Se perdieron ventanas al arrancar, o `SSI_AUDIO_STARTUP` cambió |
| `pulse` con `n` bajo | Cableado 5b, o `testpulse` sin habilitar (buscar `CMD n=3` en el log) |
| `c` distinto entre reinicios | El orden de `capture_start` o un flanco espurio en la FS al arrancar: medir D6 con el osciloscopio durante un reinicio |
| `swd.py` falla al conectar | Modo desarrollo (BOOT1 = H) y que nada más use el ST-LINK (cerrar el gdbserver) |

- [ ] **Step 19: Registrar en `MEMORY.md`** los resultados de P3 (f0), P7 (Δstd y Δmean por canal), P4 (`c`) y la corrida de 60 s. Commit solo si Matías lo autoriza: `feat: acq pipeline with DATA packets, SWD diagnostics and sync tests`.

---

## Cierre del Plan 1

| Requisito o prueba | Dónde se verifica |
|---|---|
| R1: EMG a 4 kHz | Task 4 Step 7 (`d_emgblk`), Task 5 Step 10 (`d_win`, `d_ms`), P2 opcional en el Step 14 |
| R2: audio de 24 bits | Task 2 (decodificación), Task 3 (`AUD`), Task 5 Step 13 (P3) |
| R3: un solo reloj, `c` constante | Task 4 Steps 7 y 8, Task 5 Step 16 (P4) |
| R4: alineamiento < 1 ms | Task 5 Step 16 (`c` medido) |
| R7: modular sobre ThreadX | Estructura de `App/`; comunicación solo por primitivas de ThreadX |
| P1 (RAM), P3, P4, P7 | Tasks 1, 5 (Steps 13, 16 y 15) |

Al terminar se escribe el Plan 2: `link` (SPI5 esclavo + DRDY en PH5) en lugar de `sink`, `ctrl` (comandos START/STOP/INFO, estados, recuperación de la §7, INFO con `c`), watchdog, arranque desde flash (R5, R6, P5, P6) y el lector de la RPi5 basado en `tools/ssi_packet.py`.
