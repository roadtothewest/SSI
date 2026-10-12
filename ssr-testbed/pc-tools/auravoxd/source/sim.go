package source

import (
	"context"
	"math"
	"math/rand"
	"time"

	"auravoxd/frame"
	"auravoxd/stream"
)

// Sim genera bloques sintéticos para probar la HMI sin el DK:
// un enunciado cada 2,5 s con 5 sílabas; el sEMG se activa LagMS antes que la voz.
// Piso de ruido de 1,5 µV RTI y 1 µV de 50 Hz en los 3 canales.
type Sim struct {
	Conv  stream.Conv
	LagMS float64
}

// Amplitud del sEMG por canal [µV RTI]: submentoniano, labio inferior, cuello.
var simAmp = [3]float64{40, 30, 20}

// envAt es la envolvente articulatoria en el instante t [s]: 0 en silencio, ~1 en una sílaba.
func envAt(t float64) float64 {
	const period, start, syl, width = 2.5, 0.6, 0.18, 0.16
	p := math.Floor(t / period)
	tl := t - p*period - start
	e := 0.0
	for j := 0.0; j < 5; j++ {
		d := tl - j*syl
		if d >= 0 && d < width {
			s := math.Sin(p*12.9898+j*78.233) * 43758.5453
			a := 0.6 + 0.4*(s-math.Floor(s))
			e += a * math.Sin(math.Pi*d/width)
		}
	}
	return e
}

// Gen genera los bloques simulados uno por uno, sin esperar (lo usan Run y los tests).
type Gen struct {
	conv stream.Conv
	lag  float64
	rng  *rand.Rand
	k    int64 // muestra del ADC
	seq  uint32
	ph   float64 // fase de la voz
	blk  frame.Block
}

func NewGen(c stream.Conv, lagMS float64, seed int64) *Gen {
	return &Gen{conv: c, lag: lagMS / 1000, rng: rand.New(rand.NewSource(seed))}
}

func (g *Gen) Next() []byte {
	for i := range g.blk.Tuples {
		tu := &g.blk.Tuples[i]
		te := float64(g.k) / stream.FsEMG
		tu.TS = uint32(g.k * 500)
		e := envAt(te)
		for c := 0; c < 3; c++ {
			uv := simAmp[c]*e*g.rng.NormFloat64() + 1.5*g.rng.NormFloat64() +
				math.Sin(2*math.Pi*50*te+float64(c))
			tu.ADC[c] = g.conv.Code(uv)
		}
		for j := range tu.Voice {
			tv := te + float64(j)/stream.FsVoice
			f0 := 130 + 10*math.Sin(2*math.Pi*0.5*tv)
			g.ph += 2 * math.Pi * f0 / stream.FsVoice
			v := 0.0
			for h := 1.0; h <= 5; h++ {
				v += math.Sin(h*g.ph) / h
			}
			x := 0.25*envAt(tv-g.lag)*v + 0.003*g.rng.NormFloat64()
			tu.Voice[j] = int16(math.Max(-32768, math.Min(32767, x*32767)))
		}
		g.k++
	}
	g.blk.Seq, g.blk.T0 = g.seq, g.blk.Tuples[0].TS
	g.seq++
	b := make([]byte, frame.BlockSize)
	frame.Encode(&g.blk, b)
	return b
}

func (s *Sim) Run(ctx context.Context, out chan<- []byte) {
	g := NewGen(s.Conv, s.LagMS, time.Now().UnixNano())
	t := time.NewTicker(10 * time.Millisecond)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
		select {
		case out <- g.Next():
		default:
		}
	}
}
