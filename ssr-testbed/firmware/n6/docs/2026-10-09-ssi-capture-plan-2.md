# Plan 2 — Enlace SPI con la RPi5, watchdog y arranque desde flash (`ssi_capture`)

> **Para agentes:** SUB-SKILL REQUERIDA: `superpowers:executing-plans` (ejecución nativa, tarea por tarea, TDD). Los pasos usan casillas (`- [ ]`).

**Goal:** que el DK entregue los bloques de `ssr-testbed/firmware/PROTOCOLO_SPI.md` a la RPi5 por SPI5 esclavo + DRDY, que se reinicie solo si un hilo se cuelga y que arranque desde la flash externa sin debugger.

**Architecture:** `link_logic` es la máquina de estados del §4 del protocolo, lógica pura probada en el PC; `link` es el driver (SPI5 esclavo solo TX con DMA, NSS por hardware cuyo flanco de subida llega por EXTI3, DRDY en PH5), que reemplaza al consumidor provisional `sink` del Plan 1. `mon` supervisa con el IWDG: lo refresca solo si `acq` y `link` siguen dando vueltas. La flash se graba con el flujo ya verificado en `n6_smoke` (firma con `STM32_SigningTool_CLI` y CubeProgrammer con el loader del DK).

**Tech stack:** el mismo del Plan 1 (STM32CubeN6 v1.4.1, ThreadX, GCC 14.3.1, CubeProgrammer 2.23).

**Spec:** `docs/2026-10-09-ssi-capture-spec.md` (v0.3), §5–§8; contrato del enlace: `../PROTOCOLO_SPI.md`.

**Alcance:** R5 y R6 hasta donde se puede sin la RPi5 ni mover switches. La transferencia real (reloj del maestro, `sent`, P5 de 10 min) y el arranque desde flash (BOOT0 = BOOT1 = L) quedan como pasos pendientes para Matías.

**Escrito el 2026-10-09 durante la ejecución:** las tareas 6 y 7 se hicieron con TDD antes de redactar este documento y su código se copió de los archivos. Las tareas 8–10 se planificaron aquí antes de ejecutarlas.

## Restricciones globales

Las del Plan 1, más:
- SPI5 en D10–D13 (PA3 NSS, PG2 MOSI, PH8 MISO, PE15 SCK, AF5), modo 0, 8 bits, MSB primero; DRDY en PH5 (D4). Bloques de 538 B (PROTOCOLO §2).
- Nunca se corta una transferencia en curso (CS bajo): el bloque nuevo se descarta y la Pi ve el salto de `seq`.
- El IWDG, una vez arrancado, no se puede detener: se arranca recién cuando `acq` y `link` ya están en su bucle.
- Prohibido tocar OTP, fusibles u option bytes. La flash externa (0x70000000) sí se puede reescribir.

## Review Focus

1. **La Pi lee tarde** (DRDY alto y llega un bloque nuevo): se re-arma con el nuevo y se emite un flanco nuevo, nunca un bloque mezclado. Prueba: banco sin Pi, `repl = arm − 1` y la muestra del enlace con CRC correcto (Task 7).
2. **La Pi lee mientras llega un bloque:** la transferencia sigue y el bloque nuevo se descarta. Prueba: NSS bajo por pull, `ldrop > 0` (Task 7).
3. **CS sube antes de 538 B:** se aborta y se re-arma desde el byte 0. Prueba: NSS alto por pull, `abrt = 1` (Task 7).
4. **Watchdog que reinicia en un arranque normal** (por ejemplo, durante la calibración del ADC): el IWDG se arranca recién con los dos hilos en su bucle. Prueba: 65 s sin reinicio (Task 8).
5. **Imagen de flash que no corresponde al ELF probado:** `tools/flash.sh` compila, firma, graba y verifica la misma imagen. Prueba: `-v` de CubeProgrammer (Task 9).

---

### Task 6: `link_logic`, la máquina de estados del enlace (hecha)

**Files:** Create `FSBL/App/Inc/link_logic.h`, `FSBL/App/Src/link_logic.c`, `tests/host/test_link_logic.c`; Modify `tests/host/CMakeLists.txt` (`test_link_logic`).

**Interfaces — Produce:** `link_logic_t`, `LINK_A_*`, `uint32_t link_on_block(link_logic_t *l, int nss_low)`, `uint32_t link_on_tx_done(link_logic_t *l)`, `uint32_t link_on_nss_rise(link_logic_t *l, int tx_complete)`.

- [x] **Step 1: Prueba (falló: `link_logic.c` no existía)** — `tests/host/test_link_logic.c`:

```c
#include "link_logic.h"
#include "test_util.h"

int main(void)
{
  link_logic_t l = {0};

  /* idle: a block is armed and DRDY rises (it was low since the last transfer) */
  CHECK_EQ(link_on_block(&l, 0), LINK_A_ARM_NEW | LINK_A_DRDY_HIGH);
  CHECK_EQ(l.state, LINK_ARMED);
  CHECK_EQ(l.armed, 1);

  /* the Pi reads all 538 bytes: block freed, DRDY falls, link idle */
  CHECK_EQ(link_on_tx_done(&l), LINK_A_RELEASE_CUR | LINK_A_DRDY_LOW);
  CHECK_EQ(l.state, LINK_IDLE);
  CHECK_EQ(l.sent, 1);
  CHECK_EQ(link_on_nss_rise(&l, 1), 0); /* CS release after a full transfer: nothing to do */
  CHECK_EQ(link_on_tx_done(&l), 0);     /* spurious completion while idle */

  /* unread block and a newer one ready, CS high: replace it with a fresh DRDY edge (§4) */
  CHECK_EQ(link_on_block(&l, 0), LINK_A_ARM_NEW | LINK_A_DRDY_HIGH);
  CHECK_EQ(link_on_block(&l, 0),
           LINK_A_DRDY_LOW | LINK_A_ABORT | LINK_A_RELEASE_CUR | LINK_A_ARM_NEW | LINK_A_DRDY_HIGH);
  CHECK_EQ(l.state, LINK_ARMED);
  CHECK_EQ(l.replaced, 1);
  CHECK_EQ(l.armed, 3);

  /* a newer block while the Pi is reading (CS low): finish the transfer, drop the new block */
  CHECK_EQ(link_on_block(&l, 1), LINK_A_RELEASE_NEW);
  CHECK_EQ(l.dropped, 1);
  CHECK_EQ(l.state, LINK_ARMED);

  /* CS rises before 538 bytes: abort and re-arm the same block from byte 0 */
  CHECK_EQ(link_on_nss_rise(&l, 0), LINK_A_DRDY_LOW | LINK_A_ABORT | LINK_A_ARM_CUR | LINK_A_DRDY_HIGH);
  CHECK_EQ(l.aborted, 1);
  CHECK_EQ(l.state, LINK_ARMED);
  CHECK_EQ(link_on_nss_rise(&l, 1), 0); /* completion already in hardware: tx_done will follow */

  /* idle CS edges are ignored */
  CHECK_EQ(link_on_tx_done(&l), LINK_A_RELEASE_CUR | LINK_A_DRDY_LOW);
  CHECK_EQ(link_on_nss_rise(&l, 0), 0);

  /* a Pi that reads every block: armed == sent, nothing replaced */
  link_logic_t r = {0};
  for (int i = 0; i < 100; i++) {
    link_on_block(&r, 0);
    link_on_tx_done(&r);
  }
  CHECK_EQ(r.armed, 100);
  CHECK_EQ(r.sent, 100);
  CHECK_EQ(r.replaced + r.dropped + r.aborted, 0);

  /* no Pi at all: every block replaces the previous one, the pool never fills */
  link_logic_t n = {0};
  for (int i = 0; i < 100; i++) {
    link_on_block(&n, 0);
  }
  CHECK_EQ(n.armed, 100);
  CHECK_EQ(n.replaced, 99);
  CHECK_EQ(n.sent, 0);
  TEST_END();
}
```

- [x] **Step 2: Implementación** — `FSBL/App/Inc/link_logic.h`:

```c
#ifndef LINK_LOGIC_H
#define LINK_LOGIC_H

#include <stdint.h>

/* SPI-slave link state machine of ssr-testbed/firmware/PROTOCOLO_SPI.md §4, without HAL.
   Each event returns a set of actions; the driver runs them in this order:
   DRDY_LOW, ABORT, RELEASE_CUR, RELEASE_NEW, ARM_NEW or ARM_CUR, DRDY_HIGH
   (keeping DRDY low >= 10 us when both DRDY_LOW and DRDY_HIGH are set). */
#define LINK_A_DRDY_LOW    0x01u /* DRDY down */
#define LINK_A_ABORT       0x02u /* stop the armed SPI/DMA transfer (CS is high) */
#define LINK_A_RELEASE_CUR 0x04u /* free the armed block */
#define LINK_A_RELEASE_NEW 0x08u /* free the offered block (discarded) */
#define LINK_A_ARM_NEW     0x10u /* arm the DMA with the offered block, which becomes current */
#define LINK_A_ARM_CUR     0x20u /* re-arm the current block from byte 0 */
#define LINK_A_DRDY_HIGH   0x40u /* DRDY up: the Pi reads on this rising edge */

typedef enum { LINK_IDLE = 0, LINK_ARMED } link_state_t;

typedef struct {
  link_state_t state;
  uint32_t armed;    /* blocks offered to the Pi (DRDY rising edges) */
  uint32_t sent;     /* complete 538-byte transfers */
  uint32_t replaced; /* armed blocks replaced by a newer one before the Pi read them */
  uint32_t dropped;  /* newer blocks discarded because a transfer was in progress */
  uint32_t aborted;  /* transfers cut short (CS rose early) and re-armed */
} link_logic_t;

/* A new block is ready (always the newest). nss_low: a transfer is in progress. */
uint32_t link_on_block(link_logic_t *l, int nss_low);
/* The SPI finished sending the armed block. */
uint32_t link_on_tx_done(link_logic_t *l);
/* CS rose. tx_complete: the hardware already sent every byte of the armed block. */
uint32_t link_on_nss_rise(link_logic_t *l, int tx_complete);

#endif
```

`FSBL/App/Src/link_logic.c`:

```c
#include "link_logic.h"

uint32_t link_on_block(link_logic_t *l, int nss_low)
{
  if (l->state == LINK_IDLE) {
    l->state = LINK_ARMED;
    l->armed++;
    return LINK_A_ARM_NEW | LINK_A_DRDY_HIGH;
  }
  if (nss_low) {
    l->dropped++; /* never cut a transfer: the Pi sees the seq jump instead */
    return LINK_A_RELEASE_NEW;
  }
  l->replaced++;
  l->armed++;
  return LINK_A_DRDY_LOW | LINK_A_ABORT | LINK_A_RELEASE_CUR | LINK_A_ARM_NEW | LINK_A_DRDY_HIGH;
}

uint32_t link_on_tx_done(link_logic_t *l)
{
  if (l->state != LINK_ARMED) {
    return 0u;
  }
  l->state = LINK_IDLE;
  l->sent++;
  return LINK_A_RELEASE_CUR | LINK_A_DRDY_LOW;
}

uint32_t link_on_nss_rise(link_logic_t *l, int tx_complete)
{
  if (l->state != LINK_ARMED || tx_complete) {
    return 0u;
  }
  l->aborted++; /* restart from byte 0 so the next read starts with AA 55 */
  return LINK_A_DRDY_LOW | LINK_A_ABORT | LINK_A_ARM_CUR | LINK_A_DRDY_HIGH;
}
```

- [x] **Step 3:** `ctest --test-dir ssi_capture/tests/host/build` → `100% tests passed, 0 tests failed out of 5`.

---

### Task 7: Driver `link` (SPI5 esclavo + DMA + DRDY + NSS por EXTI) en lugar de `sink` (hecha)

**Files:** Create `FSBL/App/Inc/link.h`, `FSBL/App/Src/link.c`; Delete `FSBL/App/{Inc/sink.h,Src/sink.c}`; Modify `acq.h`/`acq.c` (`out_flags`/`out_flag`: avisa al consumidor), `mon.h`/`mon.c` (estadísticas del enlace, comando 9), `app.c` (hilo `link`, prioridad 5), `tools/swd.py` (`s_link_sample`).

**Interfaces — Produce:** `LINK_EVT_*`, `link_stats_t`, `link_cfg_t {in, flags, stats}`, `void link_configure(const link_cfg_t *)`, `void link_thread_entry(ULONG)`, `uint32_t link_loops(void)`, `void link_debug_nss_pulse(void)`; símbolo `s_link_sample` (538 B).

**Verificado (2026-10-09):** ejemplo `SPI_FullDuplex_ComDMA_Slave` (init del SPI5 esclavo y DMA normal); HAL del N6: `SPI_NSS_HARD_INPUT`, `SPI_DIRECTION_2LINES_TXONLY`, `GPDMA1_REQUEST_SPI5_TX`, `HAL_EXTI_SetConfigLine` con `EXTI_GPIOA` y `HAL_EXTI_RISING_CB_ID` (el EXTI3 detecta el flanco aunque PA3 esté en su función alterna; verificado en el DK).

- [x] **Step 1: Prueba (falló: no había campos del enlace en `STAT`)**

```bash
cd ~/2026-2/SSI/SSI-repo/ssr-testbed/firmware/n6
SSI_SYNC_LPTIM=ON tools/fw.sh build && tools/run_test.sh 6 --expect 'INIT link=0' \
  --check 'STAT:lost==0 and drop==0 and err==0 and lerr==0 and abs(d_arm-100)<=1 and sent==0 and ldrop==0 and abrt==0'
```

- [x] **Step 2: Driver** — `FSBL/App/Inc/link.h`:

```c
#ifndef LINK_H
#define LINK_H

#include <stdint.h>

#include "tx_api.h"

/* Link to the RPi5, ssr-testbed/firmware/PROTOCOLO_SPI.md §4: SPI5 slave, TX only, mode 0,
   8 bits, MSB first, hardware NSS (D10..D13 = PA3 NSS, PG2 MOSI, PH8 MISO, PE15 SCK), one
   538-byte block per DMA transfer, DRDY on PH5 (D4). The state machine is link_logic. */
#define LINK_EVT_BLOCK   0x01u /* acq queued a block */
#define LINK_EVT_TX_DONE 0x02u /* ISR: the armed block was sent */
#define LINK_EVT_NSS     0x04u /* ISR: CS rose */
#define LINK_EVT_ERROR   0x08u /* ISR: SPI or DMA error */

typedef struct {
  uint32_t armed;    /* blocks offered (DRDY rising edges) */
  uint32_t sent;     /* complete transfers */
  uint32_t replaced; /* unread blocks replaced by a newer one */
  uint32_t dropped;  /* blocks discarded during a transfer */
  uint32_t aborted;  /* incomplete transfers or errors, re-armed from byte 0 */
  uint32_t errors;   /* SPI/DMA error callbacks and failed arms */
} link_stats_t;      /* sent as one TX_8_ULONG message */

typedef struct {
  TX_QUEUE *in;                /* block pointers from acq (TX_1_ULONG) */
  TX_EVENT_FLAGS_GROUP *flags; /* LINK_EVT_*: acq sets LINK_EVT_BLOCK after queueing */
  TX_QUEUE *stats;             /* link_stats_t every 100 blocks armed (TX_8_ULONG) */
} link_cfg_t;

void link_configure(const link_cfg_t *cfg); /* before the thread runs */
void link_thread_entry(ULONG arg);
uint32_t link_loops(void);       /* increments on every pass of the link thread (watchdog) */
void link_debug_nss_pulse(void); /* bench: pull the unwired NSS low ~20 ms, then high */

#endif
```

`FSBL/App/Src/link.c`:

```c
#include "link.h"

#include <string.h>

#include "avx_block.h"
#include "link_logic.h"
#include "log.h"
#include "stm32n6xx_hal.h"

_Static_assert(sizeof(link_stats_t) <= 8u * sizeof(ULONG), "link_stats_t must fit TX_8_ULONG");

#define STATS_EVERY    100u  /* blocks armed between stats messages (1 s) */
#define DRDY_LOW_SPINS 4000u /* >= 10 us of DRDY low before a new rising edge (PROTOCOLO §4) */

static link_cfg_t s_cfg;
static SPI_HandleTypeDef s_spi;
static DMA_HandleTypeDef s_dma;
static EXTI_HandleTypeDef s_exti;
static link_logic_t s_lk;
static uint8_t *s_cur;
static volatile uint32_t s_loops;
static volatile uint32_t s_errors;
/* Copy of every 100th armed block for tools/swd.py sample, cleaned to SRAM after the copy. */
static uint8_t s_link_sample[AVX_BLOCK_SIZE] __attribute__((aligned(32), used));

void link_configure(const link_cfg_t *cfg)
{
  s_cfg = *cfg;
}

uint32_t link_loops(void)
{
  return s_loops;
}

/* ISR context: notify only. */
static void notify(ULONG flag)
{
  (void)tx_event_flags_set(s_cfg.flags, flag, TX_OR);
}

static void nss_rise_cb(void)
{
  notify(LINK_EVT_NSS);
}

static void nss_pin(uint32_t pull)
{
  GPIO_InitTypeDef g = {0};
  g.Pin = GPIO_PIN_3; /* SPI5_NSS, D10 */
  g.Mode = GPIO_MODE_AF_PP;
  g.Pull = pull;
  g.Speed = GPIO_SPEED_FREQ_HIGH;
  g.Alternate = GPIO_AF5_SPI5;
  HAL_GPIO_Init(GPIOA, &g);
}

static void pins_init(void)
{
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_GPIOG_CLK_ENABLE();
  __HAL_RCC_GPIOH_CLK_ENABLE();
  nss_pin(GPIO_PULLUP); /* unwired CS reads "not selected" */
  g.Mode = GPIO_MODE_AF_PP;
  g.Speed = GPIO_SPEED_FREQ_HIGH;
  g.Alternate = GPIO_AF5_SPI5;
  g.Pull = GPIO_NOPULL;
  g.Pin = GPIO_PIN_2; /* MOSI, D11 (the Pi sends zeros, ignored) */
  HAL_GPIO_Init(GPIOG, &g);
  g.Pin = GPIO_PIN_15; /* SCK, D13 */
  HAL_GPIO_Init(GPIOE, &g);
  g.Pull = GPIO_PULLDOWN;
  g.Pin = GPIO_PIN_8; /* MISO, D12: reads 0x00 while the slave does not drive it */
  HAL_GPIO_Init(GPIOH, &g);
  HAL_GPIO_WritePin(GPIOH, GPIO_PIN_5, GPIO_PIN_RESET);
  g.Mode = GPIO_MODE_OUTPUT_PP;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_LOW;
  g.Alternate = 0;
  g.Pin = GPIO_PIN_5; /* DRDY, D4 */
  HAL_GPIO_Init(GPIOH, &g);
  HAL_GPIO_ConfigPinAttributes(GPIOA, GPIO_PIN_3, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOG, GPIO_PIN_2, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOE, GPIO_PIN_15, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
  HAL_GPIO_ConfigPinAttributes(GPIOH, GPIO_PIN_5 | GPIO_PIN_8, GPIO_PIN_SEC | GPIO_PIN_NPRIV);
}

static int spi_init(void)
{
  RCC_PeriphCLKInitTypeDef clk = {0};
  clk.PeriphClockSelection = RCC_PERIPHCLK_SPI5;
  clk.Spi5ClockSelection = RCC_SPI5CLKSOURCE_PCLK2;
  if (HAL_RCCEx_PeriphCLKConfig(&clk) != HAL_OK) {
    return -1;
  }
  __HAL_RCC_SPI5_CLK_ENABLE();
  s_spi.Instance = SPI5;
  s_spi.Init.Mode = SPI_MODE_SLAVE;
  s_spi.Init.Direction = SPI_DIRECTION_2LINES_TXONLY;
  s_spi.Init.DataSize = SPI_DATASIZE_8BIT;
  s_spi.Init.CLKPolarity = SPI_POLARITY_LOW; /* mode 0 */
  s_spi.Init.CLKPhase = SPI_PHASE_1EDGE;
  s_spi.Init.NSS = SPI_NSS_HARD_INPUT;
  s_spi.Init.FirstBit = SPI_FIRSTBIT_MSB;
  s_spi.Init.TIMode = SPI_TIMODE_DISABLE;
  s_spi.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  s_spi.Init.CRCPolynomial = 0x7;
  s_spi.Init.NSSPMode = SPI_NSS_PULSE_DISABLE;
  s_spi.Init.NSSPolarity = SPI_NSS_POLARITY_LOW;
  s_spi.Init.FifoThreshold = SPI_FIFO_THRESHOLD_01DATA;
  s_spi.Init.MasterSSIdleness = SPI_MASTER_SS_IDLENESS_00CYCLE;
  s_spi.Init.MasterInterDataIdleness = SPI_MASTER_INTERDATA_IDLENESS_00CYCLE;
  s_spi.Init.MasterReceiverAutoSusp = SPI_MASTER_RX_AUTOSUSP_DISABLE;
  s_spi.Init.MasterKeepIOState = SPI_MASTER_KEEP_IO_STATE_DISABLE;
  s_spi.Init.IOSwap = SPI_IO_SWAP_DISABLE;
  s_spi.Init.ReadyMasterManagement = SPI_RDY_MASTER_MANAGEMENT_INTERNALLY;
  s_spi.Init.ReadyPolarity = SPI_RDY_POLARITY_HIGH;
  return (HAL_SPI_Init(&s_spi) == HAL_OK) ? 0 : -2;
}

static int dma_init(void)
{
  __HAL_RCC_GPDMA1_CLK_ENABLE();
  s_dma.Instance = GPDMA1_Channel2;
  s_dma.Init.Request = GPDMA1_REQUEST_SPI5_TX;
  s_dma.Init.BlkHWRequest = DMA_BREQ_SINGLE_BURST;
  s_dma.Init.Direction = DMA_MEMORY_TO_PERIPH;
  s_dma.Init.SrcInc = DMA_SINC_INCREMENTED;
  s_dma.Init.DestInc = DMA_DINC_FIXED;
  s_dma.Init.SrcDataWidth = DMA_SRC_DATAWIDTH_BYTE;
  s_dma.Init.DestDataWidth = DMA_DEST_DATAWIDTH_BYTE;
  s_dma.Init.Priority = DMA_LOW_PRIORITY_HIGH_WEIGHT;
  s_dma.Init.SrcBurstLength = 1;
  s_dma.Init.DestBurstLength = 1;
  s_dma.Init.TransferAllocatedPort = DMA_SRC_ALLOCATED_PORT0 | DMA_DEST_ALLOCATED_PORT0;
  s_dma.Init.TransferEventMode = DMA_TCEM_BLOCK_TRANSFER;
  s_dma.Init.Mode = DMA_NORMAL;
  if (HAL_DMA_Init(&s_dma) != HAL_OK) {
    return -3;
  }
  __HAL_LINKDMA(&s_spi, hdmatx, s_dma);
  if (HAL_DMA_ConfigChannelAttributes(&s_dma, DMA_CHANNEL_SEC | DMA_CHANNEL_PRIV |
                                                  DMA_CHANNEL_SRC_SEC | DMA_CHANNEL_DEST_SEC) != HAL_OK) {
    return -4;
  }
  HAL_NVIC_SetPriority(GPDMA1_Channel2_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(GPDMA1_Channel2_IRQn);
  HAL_NVIC_SetPriority(SPI5_IRQn, 5, 0);
  HAL_NVIC_EnableIRQ(SPI5_IRQn);
  return 0;
}

static int nss_irq_init(void)
{
  EXTI_ConfigTypeDef e = {0};
  e.Line = EXTI_LINE_3;
  e.Mode = EXTI_MODE_INTERRUPT;
  e.Trigger = EXTI_TRIGGER_RISING;
  e.GPIOSel = EXTI_GPIOA; /* PA3 stays in its SPI5_NSS alternate function */
  if (HAL_EXTI_SetConfigLine(&s_exti, &e) != HAL_OK ||
      HAL_EXTI_RegisterCallback(&s_exti, HAL_EXTI_RISING_CB_ID, nss_rise_cb) != HAL_OK) {
    return -5;
  }
  /* Lower priority than SPI5: a complete transfer's EOT is handled before its CS edge. */
  HAL_NVIC_SetPriority(EXTI3_IRQn, 7, 0);
  HAL_NVIC_EnableIRQ(EXTI3_IRQn);
  return 0;
}

static int nss_low(void)
{
  return HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_3) == GPIO_PIN_RESET;
}

static int tx_complete(void)
{
  return __HAL_SPI_GET_FLAG(&s_spi, SPI_FLAG_EOT) != 0u;
}

static void drdy(int high)
{
  HAL_GPIO_WritePin(GPIOH, GPIO_PIN_5, high ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

static void arm(uint8_t *blk)
{
  if (HAL_SPI_Transmit_DMA(&s_spi, blk, (uint16_t)AVX_BLOCK_SIZE) != HAL_OK) {
    s_errors++;
  }
}

/* Runs link_logic actions in the order link_logic.h documents. */
static void run(uint32_t a, uint8_t *blk)
{
  if ((a & LINK_A_DRDY_LOW) != 0u) {
    drdy(0);
  }
  if ((a & LINK_A_ABORT) != 0u) {
    (void)HAL_SPI_Abort(&s_spi);
  }
  if ((a & LINK_A_RELEASE_CUR) != 0u && s_cur != NULL) {
    (void)tx_block_release(s_cur);
    s_cur = NULL;
  }
  if ((a & LINK_A_RELEASE_NEW) != 0u) {
    (void)tx_block_release(blk);
  }
  if ((a & LINK_A_ARM_NEW) != 0u) {
    s_cur = blk;
    arm(s_cur);
  }
  if ((a & LINK_A_ARM_CUR) != 0u && s_cur != NULL) {
    arm(s_cur);
  }
  if ((a & LINK_A_DRDY_HIGH) != 0u) {
    if ((a & LINK_A_DRDY_LOW) != 0u) {
      for (volatile uint32_t n = DRDY_LOW_SPINS; n != 0u; n--) {
      }
    }
    drdy(1);
  }
}

static void stats_push(void)
{
  union {
    link_stats_t s;
    ULONG raw[8];
  } m;
  memset(&m, 0, sizeof m);
  m.s.armed = s_lk.armed;
  m.s.sent = s_lk.sent;
  m.s.replaced = s_lk.replaced;
  m.s.dropped = s_lk.dropped;
  m.s.aborted = s_lk.aborted;
  m.s.errors = s_errors;
  (void)tx_queue_send(s_cfg.stats, m.raw, TX_NO_WAIT);
  if (s_cur != NULL) {
    memcpy(s_link_sample, s_cur, AVX_BLOCK_SIZE);
    SCB_CleanDCache_by_Addr(s_link_sample, (int32_t)AVX_BLOCK_SIZE);
  }
}

void link_debug_nss_pulse(void)
{
  nss_pin(GPIO_PULLDOWN); /* unwired CS follows the pull: "transfer in progress" */
  tx_thread_sleep(2u);    /* ~20 ms: new blocks find CS low and are dropped */
  nss_pin(GPIO_PULLUP);   /* rising edge without a single clock: incomplete transfer */
}

void SPI5_IRQHandler(void)
{
  HAL_SPI_IRQHandler(&s_spi);
}

void GPDMA1_Channel2_IRQHandler(void)
{
  HAL_DMA_IRQHandler(&s_dma);
}

void EXTI3_IRQHandler(void)
{
  HAL_EXTI_IRQHandler(&s_exti);
}

void HAL_SPI_TxCpltCallback(SPI_HandleTypeDef *hspi)
{
  if (hspi == &s_spi) {
    notify(LINK_EVT_TX_DONE);
  }
}

void HAL_SPI_ErrorCallback(SPI_HandleTypeDef *hspi)
{
  if (hspi == &s_spi) {
    s_errors++;
    notify(LINK_EVT_ERROR);
  }
}

void link_thread_entry(ULONG arg)
{
  (void)arg;
  int rc;
  pins_init();
  if ((rc = spi_init()) == 0 && (rc = dma_init()) == 0) {
    rc = nss_irq_init();
  }
  log_printf("INIT link=%d", rc);
  if (rc != 0) {
    (void)tx_thread_suspend(tx_thread_identify());
  }
  for (;;) {
    ULONG got = 0u;
    (void)tx_event_flags_get(s_cfg.flags,
                             LINK_EVT_BLOCK | LINK_EVT_TX_DONE | LINK_EVT_NSS | LINK_EVT_ERROR,
                             TX_OR_CLEAR, &got, TX_TIMER_TICKS_PER_SECOND / 10u);
    s_loops++;
    /* Completion first: a full transfer's CS edge must not look like an early one. */
    if ((got & LINK_EVT_TX_DONE) != 0u) {
      run(link_on_tx_done(&s_lk), NULL);
    }
    if ((got & (LINK_EVT_NSS | LINK_EVT_ERROR)) != 0u) {
      const int complete = ((got & LINK_EVT_ERROR) == 0u) && tx_complete();
      run(link_on_nss_rise(&s_lk, complete), NULL);
    }
    ULONG msg;
    while (tx_queue_receive(s_cfg.in, &msg, TX_NO_WAIT) == TX_SUCCESS) {
      const uint32_t armed = s_lk.armed;
      run(link_on_block(&s_lk, nss_low()), (uint8_t *)(uintptr_t)msg);
      if (s_lk.armed != armed && s_lk.armed % STATS_EVERY == 0u) {
        stats_push();
      }
    }
  }
}
```

- [x] **Step 3: Integración**
  - `acq_cfg_t` gana `out_flags` y `out_flag`: después de encolar un bloque, `acq` hace `tx_event_flags_set(out_flags, out_flag, TX_OR)`.
  - `app.c` crea el grupo `link` y la cola de estadísticas `link_st` (TX_8_ULONG), y el hilo `link` con prioridad 5 en lugar de `sink`.
  - `mon` imprime `arm sent repl ldrop abrt lerr` en `STAT` y agrega `CMD_NSS_PULSE = 9`.
  - `swd.py sample` lee `s_link_sample`.

- [x] **Step 4: Pruebas de banco (medidas el 2026-10-09)**
  1. El Step 1 da `RESULT: PASS`: `INIT link=0`, 100 bloques armados por segundo, `repl = arm − 1` (sin Pi), sin errores ni descartes en `acq`.
  2. `tools/inject_test.sh 'cmd 9' --skip 0 --expect 'ldrop=[1-9][0-9]* abrt=1 lerr=0' --check 'STAT:lost==0 and drop==0 and err==0 and lerr==0'` da `RESULT: PASS` (`ldrop=2`, `abrt=1`).
  3. DRDY (GPIOH ODR bit 5) = 1 con un bloque armado; `swd.py sample` + `avx_block.py check --ts-check` da `RESULT: PASS`.

- [ ] **Step 5 (pendiente: Raspberry Pi):** cablear SPI y DRDY según la spec §3 (GND común; isla sin tierra de protección) y correr `auravoxd` (Vicente). Aceptación (P5): 100 bloques/s, 0 errores de CRC, 0 saltos de `seq` en 10 min y `sent` ≈ `arm` en `STAT`.

---

### Task 8: Watchdog (IWDG) supervisado por `mon` (hecha)

**Files:** Modify `FSBL/CMakeLists.txt` (`HAL_IWDG_MODULE_ENABLED`, `stm32n6xx_hal_iwdg.c`), `acq.h`/`acq.c` (`acq_loops()`, `ACQ_EVT_HANG`, `acq_request_hang()`), `mon.c` (IWDG, `CMD_HANG = 8`), `app.c` (línea `RST rsr=… iwdg=…` al arrancar; después limpia los flags con `RMVF`), `tools/swd.py` (`read32`).

**Diseño:** IWDG con LSI ≈ 32 kHz, prescaler 64 y recarga 500 → ≈ 1 s. `mon` lo arranca cuando `acq_loops()` y `link_loops()` avanzaron al menos una vez. Después lo refresca, como mucho cada 100 ms, solo si los dos contadores avanzaron desde la última vez. Los dos hilos dan una vuelta al menos cada 100 ms (timeout de sus event flags). Si `mon` se cuelga, tampoco refresca. En modo desarrollo, un reset deja el firmware en la ROM (no se recarga solo); la prueba lo detecta por `RCC->RSR.IWDGRSTF` (0x56028034, bit 26).

- [x] **Step 1: Prueba de reinicio (falló: `FORBIDDEN: STAT t=8`)**: `tools/inject_test.sh 'cmd 8' --skip 0 --expect 'CMD n=8' --expect 'WDG on=1' --reject 'STAT t=8 '` y después `python3 tools/swd.py read32 0x56028034` debe tener el bit 26 en 1.
- [x] **Step 2:** `acq_loops()` cuenta las vueltas del bucle de `acq`; `ACQ_EVT_HANG` lo bloquea 2 s. En `mon`, `watchdog()` corre en cada vuelta, como mucho cada 100 ms:

```c
static void watchdog(void)
{
  const uint32_t a = acq_loops();
  const uint32_t l = link_loops();
  if (a == s_acq_seen || l == s_link_seen) {
    return; /* a thread has not looped since the last check */
  }
  s_acq_seen = a;
  s_link_seen = l;
  if (s_wdg_on) {
    (void)HAL_IWDG_Refresh(&s_iwdg);
    return;
  }
  s_iwdg.Instance = IWDG;
  s_iwdg.Init.Prescaler = IWDG_PRESCALER_64;
  s_iwdg.Init.Reload = 500u;
  s_iwdg.Init.Window = IWDG_WINDOW_DISABLE;
  s_iwdg.Init.EWI = 0u;
  s_wdg_on = (HAL_IWDG_Init(&s_iwdg) == HAL_OK);
  log_printf("WDG on=%d", s_wdg_on);
}
```

En `app_early_init`:

```c
  /* Reset cause of this boot (RM0486 RCC_RSR), then clear the flags for the next one. */
  const uint32_t rsr = RCC->RSR;
  log_printf("RST rsr=%lu iwdg=%lu", (unsigned long)rsr, (unsigned long)((rsr & RCC_RSR_IWDGRSTF) != 0u));
  RCC->RSR = RCC_RSR_RMVF;
```

- [x] **Step 3 (medido el 2026-10-09):**
  - El Step 1 da `RESULT: PASS`: después de `CMD n=8` no aparece ninguna `STAT` más, y `RSR` = `0x04400000` (bit 26 = IWDGRSTF).
  - 65 s con el watchdog: 64 `STAT` sin reinicios y sin pérdidas.
  - El siguiente arranque informa `RST … iwdg=0`. El arranque inmediatamente posterior al cuelgue informa `iwdg=1`: el flag queda puesto mientras la placa espera en la ROM y lo limpia el firmware al arrancar.
- [x] **Step 4:** `MEMORY.md` y commit `feat(n6): IWDG supervised by mon (acq and link liveness)`.

---

### Task 9: Grabación en la flash externa (`tools/flash.sh`) y LED de IDLE (hecha, falta el arranque)

**Files:** Create `tools/flash.sh`; Modify `FSBL/App/Src/mon.c` (verde fijo en IDLE, spec §5: sin esto, el build ETR sin puente arranca desde flash sin ninguna señal visible).

- [x] **Step 1: Prueba del LED en IDLE (falló: GPIOO ODR = 0)** — build ETR sin puente, `run_test.sh 4 --expect 'IDLE ms='`, y luego tres lecturas de GPIOO ODR (`python3 tools/swd.py read32 0x56023814`) separadas 0,4 s: el bit 1 tiene que estar siempre en 1.
- [x] **Step 2:** en la rama `IDLE` de `mon`: `led_set(LED_GREEN, 1); /* steady green = idle: no data, e.g. no D6->D2 bridge (spec §5) */`. La prueba pasa (ODR = 0x2 en las tres lecturas).
- [x] **Step 3: `tools/flash.sh`**

```bash
#!/usr/bin/env bash
# Builds the firmware (default: ETR sync, the demo build), signs it as an FSBL and writes it to
# the DK's external flash at 0x70000000, then verifies it. The DK must be in development mode
# (BOOT1 = H). To boot from flash: BOOT0 = L, BOOT1 = L, reset; back to development: BOOT1 = H.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ENV_SH="${STM32_ENV:-$HOME/2026-2/SSI/tools/stm32-env.sh}"
# shellcheck disable=SC1090
if [ -f "$ENV_SH" ]; then source "$ENV_SH" >/dev/null; fi
: "${STM32_DK_EXTLOADER:?set STM32_DK_EXTLOADER to MX66UW1G45G_STM32N6570-DK.stldr}"

SSI_SYNC_LPTIM="${SSI_SYNC_LPTIM:-OFF}" "$HERE/fw.sh" build >/dev/null
ELF="$HERE/../ssi_capture/FSBL/build/Debug/ssi_capture_FSBL.elf"
OUT="$HERE/../out/flash"
mkdir -p "$OUT"
BIN="$OUT/ssi_capture_FSBL.bin"
SIGNED="$OUT/ssi_capture_FSBL-trusted.bin"
arm-none-eabi-objcopy -O binary "$ELF" "$BIN"
# Same commands as the n6_smoke flash test (2026-10-08); -align is required with CubeProgrammer >= 2.21.
STM32_SigningTool_CLI -s -bin "$BIN" -nk -of 0x80000000 -t fsbl -o "$SIGNED" -hv 2.3 -align \
  -dump "$SIGNED" >/dev/null
echo "image: $(stat -c %s "$BIN") B, signed: $(stat -c %s "$SIGNED") B"
STM32_Programmer_CLI -c port=swd -hardRst -el "$STM32_DK_EXTLOADER" -d "$SIGNED" 0x70000000 -v \
  | sed 's/\x1b\[[0-9;]*m//g' | grep -E 'Erasing|Download|verified|Error|error' || true
```

- [x] **Step 4 (2026-10-09):** `tools/flash.sh` → `image: 115332 B, signed: 116384 B`, `Erasing external memory sectors [0 1]`, `Download verified successfully`.
- [ ] **Step 5 (pendiente: Matías mueve los switches):** BOOT0 = L, BOOT1 = L y reset.
  - Sin cables: LED verde fijo y, por el VCP, `SSI capture fw 0.1.0 …`, `INIT … sync=0`, `INIT link=0` e `IDLE …` cada 2 s.
  - Con el puente D6 → D2: verde parpadeando y `STAT` cada segundo.
  - Para volver a desarrollar: BOOT1 = H y reset.

---

### Task 10: Documentación para Vicente y estado (hecha)

**Files:** Create `README.md` (en `ssr-testbed/firmware/n6/`); Modify `docs/2026-10-09-ssi-capture-spec.md` (§5: `link` en lugar de `sink`, estado), `~/2026-2/SSI/.claude/MEMORY.md`.

- [x] **Step 1:** el README cubre:
  - qué hace el firmware;
  - pines (diferencia A1/A4/A5 con PROTOCOLO_SPI.md);
  - convenciones de `seq`, `ts` y `flags`;
  - latencias fijas;
  - cómo compilar, cargar, probar y grabar;
  - build de banco;
  - estado y pendientes.
- [x] **Step 2:** spec §5 actualizada (`link_logic`, `link`, watchdog en `mon`, LED de IDLE) y commit `docs(n6): README for the capture firmware and protocol notes for the RPi side`.

---

### Task 11: Bloque retenido con el enlace libre y CS bajo (hecha; hallazgo de la autorrevisión)

**Motivo:** PROTOCOLO §4 define un modo de puesta en marcha sin DRDY (`auravoxd -drdy -1`), en el que la Pi lee cada 10 ms. Si una de esas lecturas encuentra el enlace libre (MISO en ceros) y en ese momento llega un bloque, armarlo a mitad de la transferencia corrompe esa lectura: ≈ 11 % de las lecturas a 4 MHz.

**Cambio:** `link_logic` gana el estado `LINK_HELD` y la acción `LINK_A_HOLD_NEW`. Con el enlace libre y CS bajo, el bloque se retiene sin armarlo. Al subir CS se arma (`ARM_CUR` + `DRDY_HIGH`). Un bloque más nuevo reemplaza al retenido, que se cuenta en `dropped`. Si CS ya está alto cuando llega el siguiente bloque, se arma el más nuevo.

- [x] **Step 1 (RED):** casos nuevos en `test_link_logic.c`. No compilaba: `LINK_A_HOLD_NEW` no existía.
- [x] **Step 2 (GREEN):** `link_logic` + `link.c` (`HOLD_NEW`: `s_cur = blk` sin armar). Host 5/5; `inject_test.sh 'cmd 9'` sigue en PASS.
- [ ] **Pendiente con la RPi5:** `auravoxd -src spi -drdy -1` durante 1 min sin errores de CRC.
