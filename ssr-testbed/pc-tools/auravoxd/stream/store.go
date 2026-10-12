// Package stream ordena las tuplas que llegan en buffers circulares, uno por
// señal, indexados por número de muestra. Así el sEMG y la voz quedan alineados:
// la muestra k del ADC corresponde a las muestras 8k..8k+7 de la voz y a la
// muestra k/10 de las envolventes.
package stream

import (
	"math"
	"sync"
	"time"

	"auravoxd/dsp"
	"auravoxd/frame"
)

const (
	FsEMG    = 2000
	FsVoice  = 16000
	FsEnv    = 200
	DecEMG   = FsEMG / FsEnv   // 10
	DecVoice = FsVoice / FsEnv // 80
	NCh      = frame.NADC
)

// Conv pasa el código del ADC a µV referidos a la entrada del AFE.
type Conv struct {
	VrefADC float64 // tensión de referencia del ADC del DK [V]
	GDK     float64 // ganancia del pin Arduino al ADC (supuesto 0.545)
	VMid    float64 // VREF del AFE [V]
	Gain    float64 // ganancia total del AFE (2500)
}

func (c Conv) MicroVolts(code uint16) float32 {
	v := float64(code) * c.VrefADC / 4095 / c.GDK
	return float32((v - c.VMid) / c.Gain * 1e6)
}

// Code es la inversa: la usa la fuente simulada.
func (c Conv) Code(uv float64) uint16 {
	v := (c.VMid + uv*1e-6*c.Gain) * c.GDK / c.VrefADC * 4095
	return uint16(math.Max(0, math.Min(4095, math.Round(v))))
}

// Ring es un buffer circular; n es el total de muestras escritas.
type Ring struct {
	buf []float32
	n   int64
}

func newRing(size int) *Ring { return &Ring{buf: make([]float32, size)} }

func (r *Ring) push(x float32) {
	r.buf[r.n%int64(len(r.buf))] = x
	r.n++
}

func (r *Ring) read(from int64, dst []float32) bool {
	if from < 0 || from < r.n-int64(len(r.buf)) || from+int64(len(dst)) > r.n {
		return false
	}
	size := int64(len(r.buf))
	for i := range dst {
		dst[i] = r.buf[(from+int64(i))%size]
	}
	return true
}

// Link resume el estado del enlace SPI.
type Link struct {
	Blocks  uint64  `json:"blocks"`
	Rate    float64 `json:"rate"` // bloques/s (100 esperado)
	CRCErr  uint64  `json:"crc"`
	BadHdr  uint64  `json:"hdr"`
	Gaps    uint64  `json:"gaps"` // bloques perdidos según seq
	Dups    uint64  `json:"dups"`
	Overrun uint64  `json:"overrun"` // bloques con flag de overrun del DK
	LastTS  uint32  `json:"ts"`
	NoData  bool    `json:"nodata"`
}

type Store struct {
	mu    sync.RWMutex
	conv  Conv
	emg   [NCh]*Ring // µV RTI, 2 kHz
	voice *Ring      // [-1, 1], 16 kHz
	env   [NCh + 1]*Ring
	envF  [NCh + 1]*dsp.Envelope

	link    Link
	lastSeq uint32
	haveSeq bool
	lastRx  time.Time
	rateT0  time.Time
	rateN   uint64
	blk     frame.Block
}

func NewStore(c Conv) *Store {
	s := &Store{conv: c, voice: newRing(10 * FsVoice)}
	for i := 0; i < NCh; i++ {
		s.emg[i] = newRing(30 * FsEMG)
		s.envF[i] = dsp.NewEnvelope(FsEMG, DecEMG)
	}
	s.envF[NCh] = dsp.NewEnvelope(FsVoice, DecVoice)
	for i := range s.env {
		s.env[i] = newRing(30 * FsEnv)
	}
	return s
}

// Ingest decodifica un bloque crudo y lo agrega. Devuelve true si el bloque es
// nuevo y válido (el que hay que grabar).
func (s *Store) Ingest(raw []byte) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := time.Now()
	if err := frame.Decode(raw, &s.blk); err != nil {
		switch err {
		case frame.ErrCRC:
			s.link.CRCErr++
		case frame.ErrHeader:
			s.link.BadHdr++
		}
		// ErrSync: el DK no tenía bloque (bus en 0x00/0xFF); no es un error.
		return false
	}
	b := &s.blk
	if s.haveSeq {
		switch d := b.Seq - s.lastSeq; {
		case d == 0:
			s.link.Dups++ // lectura repetida (modo sin DRDY)
			return false
		case d > 1 && d < 1<<31:
			s.link.Gaps += uint64(d - 1)
		case d >= 1<<31:
			s.link.Gaps++ // el DK se reinició
		}
	}
	s.lastSeq, s.haveSeq = b.Seq, true
	if b.Flags != 0 {
		s.link.Overrun++
	}
	for i := range b.Tuples {
		t := &b.Tuples[i]
		for c := 0; c < NCh; c++ {
			uv := s.conv.MicroVolts(t.ADC[c])
			s.emg[c].push(uv)
			if e, ok := s.envF[c].Step(float64(uv)); ok {
				s.env[c].push(float32(e))
			}
		}
		for _, v := range t.Voice {
			x := float32(v) / 32768
			s.voice.push(x)
			if e, ok := s.envF[NCh].Step(float64(x)); ok {
				s.env[NCh].push(float32(e))
			}
		}
	}
	s.link.Blocks++
	s.link.LastTS = b.Tuples[frame.NTuples-1].TS
	s.lastRx = now
	s.rateN++
	if dt := now.Sub(s.rateT0); dt >= time.Second {
		s.link.Rate = float64(s.rateN) / dt.Seconds()
		s.rateT0, s.rateN = now, 0
	}
	return true
}

func (s *Store) Link() Link {
	s.mu.RLock()
	defer s.mu.RUnlock()
	l := s.link
	l.NoData = time.Since(s.lastRx) > time.Second
	if l.NoData {
		l.Rate = 0
	}
	return l
}

// Counts devuelve el total de muestras escritas de sEMG (por canal), voz y envolventes.
func (s *Store) Counts() (nEMG, nVoice, nEnv int64) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.emg[0].n, s.voice.n, s.env[0].n
}

// ReadEMG copia las muestras [from, from+len(dst)) del canal ch. false si ya no están o aún no llegan.
func (s *Store) ReadEMG(ch int, from int64, dst []float32) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.emg[ch].read(from, dst)
}

func (s *Store) ReadVoice(from int64, dst []float32) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.voice.read(from, dst)
}

// ReadEnv lee la envolvente i (0..2 = CH1..CH3, 3 = voz), a 200 Hz.
func (s *Store) ReadEnv(i int, from int64, dst []float32) bool {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.env[i].read(from, dst)
}
