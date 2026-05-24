#include "iis3dwb.h"
#include "frame.h"
#include "usb_cdc.h"

volatile uint8_t  iis3dwb_acc_ready = 0;
volatile uint16_t iis3dwb_frame_count = 0;
int16_t iis3dwb_acc_buf[ACC_SAMPLES_PER_FRAME * 3];
int16_t iis3dwb_acc_buf2[ACC_SAMPLES_PER_FRAME * 3];

static int16_t *active_buf = NULL;
static bool use_buf2 = false;

static void iis3dwb_cs_low(void)
{
    HAL_GPIO_WritePin(IIS3DWB_CS_PORT, IIS3DWB_CS_PIN, GPIO_PIN_RESET);
}

static void iis3dwb_cs_high(void)
{
    HAL_GPIO_WritePin(IIS3DWB_CS_PORT, IIS3DWB_CS_PIN, GPIO_PIN_SET);
}

bool iis3dwb_read_reg(uint8_t reg, uint8_t *val)
{
    uint8_t tx[2] = { reg | 0x80, 0x00 };
    uint8_t rx[2] = { 0 };

    iis3dwb_cs_low();
    HAL_StatusTypeDef ret = HAL_SPI_TransmitReceive(&IIS3DWB_SPI, tx, rx, 2, IIS3DWB_SPI_TIMEOUT);
    iis3dwb_cs_high();

    if (ret != HAL_OK) return false;
    *val = rx[1];
    return true;
}

bool iis3dwb_write_reg(uint8_t reg, uint8_t val)
{
    uint8_t tx[2] = { reg & 0x7F, val };

    iis3dwb_cs_low();
    HAL_StatusTypeDef ret = HAL_SPI_Transmit(&IIS3DWB_SPI, tx, 2, IIS3DWB_SPI_TIMEOUT);
    iis3dwb_cs_high();

    return (ret == HAL_OK);
}

bool iis3dwb_init(void)
{
    uint8_t whoami = 0;
    if (!iis3dwb_read_reg(IIS3DWB_WHO_AM_I, &whoami))
        return false;
    if (whoami != IIS3DWB_WHO_AM_I_VAL)
        return false;

    iis3dwb_write_reg(IIS3DWB_CTRL3_C, 0x01);
    HAL_Delay(10);

    iis3dwb_write_reg(IIS3DWB_CTRL1_XL, 0x60);
    HAL_Delay(1);

    iis3dwb_write_reg(IIS3DWB_CTRL4_C, 0x04);
    HAL_Delay(1);

    iis3dwb_write_reg(IIS3DWB_CTRL6_C, 0x00);
    HAL_Delay(1);

    iis3dwb_write_reg(IIS3DWB_FIFO_CTRL1, 0x00);
    iis3dwb_write_reg(IIS3DWB_FIFO_CTRL2, 0x00);
    iis3dwb_write_reg(IIS3DWB_FIFO_CTRL3, 0x00);
    iis3dwb_write_reg(IIS3DWB_FIFO_CTRL4, 0x00);
    iis3dwb_write_reg(IIS3DWB_FIFO_CTRL5, 0x00);

    iis3dwb_write_reg(IIS3DWB_CTRL5_C, 0x00);
    iis3dwb_write_reg(IIS3DWB_MD1_CFG, 0x00);

    return true;
}

bool iis3dwb_start_dma(void)
{
    use_buf2 = false;
    active_buf = iis3dwb_acc_buf;
    iis3dwb_acc_ready = 0;
    iis3dwb_frame_count = 0;

    return (iis3dwb_dma_transfer((uint16_t*)active_buf,
            ACC_SAMPLES_PER_FRAME * 3) == HAL_OK);
}

HAL_StatusTypeDef iis3dwb_dma_transfer(uint16_t *buf, uint16_t len)
{
    iis3dwb_cs_low();
    uint8_t cmd = IIS3DWB_OUT_X_L_XL | 0x80 | 0x40;

    HAL_StatusTypeDef ret = HAL_SPI_Transmit_DMA(&IIS3DWB_SPI, &cmd, 1);
    if (ret != HAL_OK) {
        iis3dwb_cs_high();
        return ret;
    }

    while (IIS3DWB_SPI.Instance->SR & SPI_SR_BSY);

    ret = HAL_SPI_Receive_DMA(&IIS3DWB_SPI, (uint8_t*)buf, len * 2);
    if (ret != HAL_OK) {
        iis3dwb_cs_high();
        return ret;
    }

    return HAL_OK;
}

void HAL_SPI_TxHalfCpltCallback(SPI_HandleTypeDef *hspi)
{
    if (hspi->Instance == IIS3DWB_SPI.Instance) {
        iis3dwb_frame_count++;
        if (use_buf2) {
            active_buf = iis3dwb_acc_buf;
        } else {
            active_buf = iis3dwb_acc_buf2;
        }
        use_buf2 = !use_buf2;
        iis3dwb_acc_ready = 1;
        iis3dwb_dma_transfer((uint16_t*)active_buf,
            ACC_SAMPLES_PER_FRAME * 3);
    }
}

void HAL_SPI_TxCpltCallback(SPI_HandleTypeDef *hspi)
{
    if (hspi->Instance == IIS3DWB_SPI.Instance) {
        iis3dwb_cs_high();
    }
}

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
    if (GPIO_Pin == IIS3DWB_INT_PIN) {
    }
}
