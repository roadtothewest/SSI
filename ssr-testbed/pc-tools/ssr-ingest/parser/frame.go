package parser

import (
	"encoding/binary"
	"fmt"
	"sync/atomic"
	"time"

	"ssr-ingest/buffer"
	"ssr-ingest/storage"
)

const (
	Sync0      = 0xAA
	Sync1      = 0x55
	TypeAudio  = 0x02
	TypeEMG    = 0x03 // EMG 4 canales (pendiente en firmware)
	HeaderSize = 10
)

type FrameHeader struct {
	Sync0     byte
	Sync1     byte
	FrameType byte
	Flags     byte
	Timestamp uint32
	DataLen   uint16
}

type Frame struct {
	Header    FrameHeader
	Data      []byte
	Timestamp time.Time
}

type FrameParser struct {
	buf      []byte
	ring     *buffer.Ring
	writer   *storage.Writer
	frames   atomic.Uint64
	drops    atomic.Uint64
}

func NewFrameParser(ring *buffer.Ring, writer *storage.Writer) *FrameParser {
	return &FrameParser{
		buf:    make([]byte, 0, 65536),
		ring:   ring,
		writer: writer,
	}
}

func (p *FrameParser) Feed(data []byte) {
	p.buf = append(p.buf, data...)
	p.parse()
}

func (p *FrameParser) parse() {
	for len(p.buf) >= HeaderSize {
		syncIdx := -1
		for i := 0; i < len(p.buf)-1; i++ {
			if p.buf[i] == Sync0 && p.buf[i+1] == Sync1 {
				syncIdx = i
				break
			}
		}
		if syncIdx < 0 {
			p.buf = p.buf[len(p.buf)-1:]
			return
		}

		if syncIdx > 0 {
			p.buf = p.buf[syncIdx:]
		}

		if len(p.buf) < HeaderSize {
			return
		}

		if p.buf[0] != Sync0 || p.buf[1] != Sync1 {
			p.buf = p.buf[1:]
			continue
		}

		dataLen := binary.LittleEndian.Uint16(p.buf[8:10])
		frameSize := HeaderSize + int(dataLen)

		if len(p.buf) < frameSize {
			return
		}

		frame := &Frame{
			Header: FrameHeader{
				Sync0:     p.buf[0],
				Sync1:     p.buf[1],
				FrameType: p.buf[2],
				Flags:     p.buf[3],
				Timestamp: binary.LittleEndian.Uint32(p.buf[4:8]),
				DataLen:   dataLen,
			},
			Data:      make([]byte, dataLen),
			Timestamp: time.Now(),
		}
		copy(frame.Data, p.buf[HeaderSize:frameSize])

		p.processFrame(frame)
		p.buf = p.buf[frameSize:]
	}
}

func (p *FrameParser) processFrame(frame *Frame) {
	p.frames.Add(1)

	if !p.ring.Push(frame) {
		p.drops.Add(1)
	}

	p.writer.WriteFrame(frame)
}

func (p *FrameParser) FrameCount() uint64 {
	return p.frames.Load()
}

func (p *FrameParser) DropCount() uint64 {
	return p.drops.Load()
}

func (h *FrameHeader) TypeName() string {
	switch h.FrameType {
	case TypeAudio:
		return "AUDIO"
	case TypeEMG:
		return "EMG"
	default:
		return fmt.Sprintf("UNKNOWN(0x%02X)", h.FrameType)
	}
}

func (h *FrameHeader) String() string {
	return fmt.Sprintf("[%s ts=%d len=%d]",
		h.TypeName(), h.Timestamp, h.DataLen)
}
