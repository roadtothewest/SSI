// Package source entrega bloques crudos de frame.BlockSize bytes: desde el SPI
// del DK, desde una simulación o desde una sesión grabada.
package source

import (
	"context"
	"fmt"
	"log"
	"os"
	"runtime"
	"syscall"
	"time"
	"unsafe"

	"auravoxd/frame"

	"github.com/warthog618/go-gpiocdev"
)

// SPI lee el DK como maestro por spidev. Si DRDY >= 0, espera el flanco de subida
// de esa línea GPIO antes de cada lectura; si no, lee cada 10 ms y el decoder
// descarta los bloques repetidos por seq.
type SPI struct {
	Dev  string // /dev/spidev0.0
	Hz   uint32
	Chip string // gpiochip0
	DRDY int    // offset de la línea (GPIO25), -1 = sin DRDY
}

// Run no termina por errores del hardware: reintenta cada 2 s hasta que ctx se cancela.
func (s *SPI) Run(ctx context.Context, out chan<- []byte) {
	for ctx.Err() == nil {
		if err := s.session(ctx, out); err != nil {
			log.Printf("spi: %v (reintento en 2 s)", err)
		}
		select {
		case <-ctx.Done():
		case <-time.After(2 * time.Second):
		}
	}
}

func (s *SPI) session(ctx context.Context, out chan<- []byte) error {
	f, err := os.OpenFile(s.Dev, os.O_RDWR, 0)
	if err != nil {
		return err
	}
	defer f.Close()
	fd := f.Fd()
	mode, bits, hz := uint8(0), uint8(8), s.Hz
	if err := ioctl(fd, spiIocWrMode, unsafe.Pointer(&mode)); err != nil {
		return fmt.Errorf("modo SPI: %w", err)
	}
	if err := ioctl(fd, spiIocWrBits, unsafe.Pointer(&bits)); err != nil {
		return fmt.Errorf("bits SPI: %w", err)
	}
	if err := ioctl(fd, spiIocWrSpeed, unsafe.Pointer(&hz)); err != nil {
		return fmt.Errorf("velocidad SPI: %w", err)
	}

	var line *gpiocdev.Line
	ready := make(chan struct{}, 1)
	if s.DRDY >= 0 {
		line, err = gpiocdev.RequestLine(s.Chip, s.DRDY, gpiocdev.AsInput, gpiocdev.WithRisingEdge,
			gpiocdev.WithEventHandler(func(gpiocdev.LineEvent) {
				select {
				case ready <- struct{}{}:
				default:
				}
			}))
		if err != nil {
			return fmt.Errorf("DRDY %s/%d: %w", s.Chip, s.DRDY, err)
		}
		defer line.Close()
	}
	log.Printf("spi: %s a %d Hz, DRDY %s/%d", s.Dev, s.Hz, s.Chip, s.DRDY)

	tx := make([]byte, frame.BlockSize)
	poll := time.NewTicker(10 * time.Millisecond)
	defer poll.Stop()
	for {
		if line != nil {
			select {
			case <-ctx.Done():
				return nil
			case <-ready:
			case <-time.After(100 * time.Millisecond):
				// Por si se perdió el flanco: si DRDY ya está arriba, se lee igual.
				if v, err := line.Value(); err != nil || v == 0 {
					continue
				}
			}
		} else {
			select {
			case <-ctx.Done():
				return nil
			case <-poll.C:
			}
		}
		rx := make([]byte, frame.BlockSize)
		if err := transfer(fd, tx, rx, hz); err != nil {
			return err
		}
		select {
		case out <- rx:
		default: // el decoder va atrasado: se descarta y el hueco de seq lo delata
		}
	}
}

// Constantes de linux/spi/spidev.h para arquitecturas con _IOC estándar (arm64, amd64).
const (
	spiIocWrMode   = 0x40016B01
	spiIocWrBits   = 0x40016B03
	spiIocWrSpeed  = 0x40046B04
	spiIocMessage1 = 0x40206B00
)

type spiIocTransfer struct {
	txBuf, rxBuf   uint64
	length, speed  uint32
	delayUsecs     uint16
	bitsPerWord    uint8
	csChange       uint8
	txNbits        uint8
	rxNbits        uint8
	wordDelayUsecs uint8
	pad            uint8
}

func transfer(fd uintptr, tx, rx []byte, hz uint32) error {
	t := spiIocTransfer{
		txBuf:       uint64(uintptr(unsafe.Pointer(&tx[0]))),
		rxBuf:       uint64(uintptr(unsafe.Pointer(&rx[0]))),
		length:      uint32(len(rx)),
		speed:       hz,
		bitsPerWord: 8,
	}
	err := ioctl(fd, spiIocMessage1, unsafe.Pointer(&t))
	runtime.KeepAlive(tx)
	runtime.KeepAlive(rx)
	return err
}

func ioctl(fd, req uintptr, arg unsafe.Pointer) error {
	if _, _, e := syscall.Syscall(syscall.SYS_IOCTL, fd, req, uintptr(arg)); e != 0 {
		return e
	}
	return nil
}
