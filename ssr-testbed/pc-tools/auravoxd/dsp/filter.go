// Package dsp tiene el procesamiento de señal: filtros para la envolvente,
// CWT Morlet, correlación cruzada y estadísticas simples.
package dsp

import "math"

// Biquad es un filtro IIR de 2º orden (forma directa II transpuesta).
type Biquad struct {
	b0, b1, b2, a1, a2 float64
	z1, z2             float64
}

// LowPass2 es un pasa-bajos Butterworth de 2º orden (RBJ, Q = 1/√2).
func LowPass2(fs, fc float64) Biquad {
	w := 2 * math.Pi * fc / fs
	alpha := math.Sin(w) / math.Sqrt2
	cw := math.Cos(w)
	a0 := 1 + alpha
	return Biquad{
		b0: (1 - cw) / 2 / a0,
		b1: (1 - cw) / a0,
		b2: (1 - cw) / 2 / a0,
		a1: -2 * cw / a0,
		a2: (1 - alpha) / a0,
	}
}

func (f *Biquad) Step(x float64) float64 {
	y := f.b0*x + f.z1
	f.z1 = f.b1*x - f.a1*y + f.z2
	f.z2 = f.b2*x - f.a2*y
	return y
}

// DCBlock es un pasa-altos de 1er orden: quita el offset antes de rectificar.
type DCBlock struct {
	a, x1, y1 float64
}

func NewDCBlock(fs, fc float64) DCBlock {
	return DCBlock{a: math.Exp(-2 * math.Pi * fc / fs)}
}

func (f *DCBlock) Step(x float64) float64 {
	y := x - f.x1 + f.a*f.y1
	f.x1, f.y1 = x, y
	return y
}

// Envelope = pasa-altos 5 Hz -> |x| -> pasa-bajos 10 Hz x2 (4º orden) -> decimación.
// Se aplica igual a sEMG y voz, así el retardo de grupo se cancela al compararlas.
type Envelope struct {
	dc     DCBlock
	lp1    Biquad
	lp2    Biquad
	dec, i int
}

func NewEnvelope(fs float64, dec int) *Envelope {
	return &Envelope{
		dc:  NewDCBlock(fs, 5),
		lp1: LowPass2(fs, 10),
		lp2: LowPass2(fs, 10),
		dec: dec,
	}
}

// Step procesa una muestra y devuelve (envolvente, true) cada dec muestras.
func (e *Envelope) Step(x float64) (float64, bool) {
	y := e.lp2.Step(e.lp1.Step(math.Abs(e.dc.Step(x))))
	e.i++
	if e.i < e.dec {
		return 0, false
	}
	e.i = 0
	return y, true
}
