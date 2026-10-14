// Package frame define el bloque SPI que manda el STM32N6570-DK a la Raspberry.
// El mismo formato está en ssr-testbed/firmware/auravox_frame.h.
//
// Bloque fijo de 538 B cada 10 ms, little-endian:
//
//	0-1   sync 0xAA 0x55
//	2     tipo 0x04
//	3     versión 1
//	4-7   seq (u32, +1 por bloque)
//	8-11  t0_us (u32, timestamp de la primera tupla)
//	12-13 n (u16, = 20)
//	14-15 flags (bit0 overrun ADC, bit1 overrun SAI)
//	16+   20 tuplas de 26 B: ts_us u32, adc[3] u16, voz[8] i16
//	536   CRC16-CCITT (u16) de los bytes 0..535
package frame

import (
	"encoding/binary"
	"errors"
)

const (
	Sync0      = 0xAA
	Sync1      = 0x55
	Type       = 0x04
	Version    = 1
	NTuples    = 20 // 20 tuplas x 500 us = 10 ms por bloque
	NVoice     = 8  // 16 kHz / 2 kHz
	NADC       = 3
	HeaderSize = 16
	TupleSize  = 4 + 2*NADC + 2*NVoice
	BlockSize  = HeaderSize + NTuples*TupleSize + 2

	FlagADCOverrun = 1 << 0
	FlagSAIOverrun = 1 << 1
)

var (
	ErrSize   = errors.New("frame: tamaño incorrecto")
	ErrSync   = errors.New("frame: sin sync")
	ErrHeader = errors.New("frame: cabecera inválida")
	ErrCRC    = errors.New("frame: CRC incorrecto")
)

// Tuple es una muestra de los 3 ADC (2 kHz) con sus 8 muestras de voz (16 kHz).
type Tuple struct {
	TS    uint32
	ADC   [NADC]uint16
	Voice [NVoice]int16
}

type Block struct {
	Seq    uint32
	T0     uint32
	Flags  uint16
	Tuples [NTuples]Tuple
}

// CRC16 es CRC-16/CCITT-FALSE: polinomio 0x1021, inicial 0xFFFF.
func CRC16(b []byte) uint16 {
	crc := uint16(0xFFFF)
	for _, v := range b {
		crc ^= uint16(v) << 8
		for i := 0; i < 8; i++ {
			if crc&0x8000 != 0 {
				crc = crc<<1 ^ 0x1021
			} else {
				crc <<= 1
			}
		}
	}
	return crc
}

func Decode(b []byte, blk *Block) error {
	if len(b) != BlockSize {
		return ErrSize
	}
	if b[0] != Sync0 || b[1] != Sync1 {
		return ErrSync
	}
	le := binary.LittleEndian
	if le.Uint16(b[BlockSize-2:]) != CRC16(b[:BlockSize-2]) {
		return ErrCRC
	}
	if b[2] != Type || b[3] != Version || le.Uint16(b[12:]) != NTuples {
		return ErrHeader
	}
	blk.Seq = le.Uint32(b[4:])
	blk.T0 = le.Uint32(b[8:])
	blk.Flags = le.Uint16(b[14:])
	p := b[HeaderSize:]
	for i := range blk.Tuples {
		t := &blk.Tuples[i]
		t.TS = le.Uint32(p)
		for c := 0; c < NADC; c++ {
			t.ADC[c] = le.Uint16(p[4+2*c:])
		}
		for k := 0; k < NVoice; k++ {
			t.Voice[k] = int16(le.Uint16(p[4+2*NADC+2*k:]))
		}
		p = p[TupleSize:]
	}
	return nil
}

// Encode escribe blk en b (len BlockSize). Lo usan la fuente simulada y los tests.
func Encode(blk *Block, b []byte) {
	le := binary.LittleEndian
	b[0], b[1], b[2], b[3] = Sync0, Sync1, Type, Version
	le.PutUint32(b[4:], blk.Seq)
	le.PutUint32(b[8:], blk.T0)
	le.PutUint16(b[12:], NTuples)
	le.PutUint16(b[14:], blk.Flags)
	p := b[HeaderSize:]
	for i := range blk.Tuples {
		t := &blk.Tuples[i]
		le.PutUint32(p, t.TS)
		for c := 0; c < NADC; c++ {
			le.PutUint16(p[4+2*c:], t.ADC[c])
		}
		for k := 0; k < NVoice; k++ {
			le.PutUint16(p[4+2*NADC+2*k:], uint16(t.Voice[k]))
		}
		p = p[TupleSize:]
	}
	le.PutUint16(b[BlockSize-2:], CRC16(b[:BlockSize-2]))
}
