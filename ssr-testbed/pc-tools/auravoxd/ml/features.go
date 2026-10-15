package ml

import (
	"math"
	"math/cmplx"

	"auravoxd/dsp"
)

// Features arma las entradas del modelo a partir de los códigos crudos del ADC.
type Features struct {
	s    *Spec
	bank *dsp.Bank
	half int
	x    []float32
	w    []complex128
}

func NewFeatures(s *Spec) *Features {
	b := dsp.NewBank(float64(s.Fs), s.FMin, s.FMax, s.NF, s.W0)
	return &Features{s: s, bank: b, half: b.MaxHalf(), w: make([]complex128, s.NF)}
}

// Span es cuántas muestras hacen falta para una ventana: T columnas cada Hop más el
// semiancho del núcleo más largo a cada lado.
func (f *Features) Span() int { return (f.s.T-1)*f.s.Hop + 2*f.half + 1 }

// Delay es cuánto atrasa la última columna respecto de la última muestra (semiancho).
func (f *Features) Delay() int { return f.half }

// Inputs calcula cwt_mag [nch][T][NF] y cwt_fase [2·nch][T][NF] (cos y sin por canal),
// en float32 y en el orden NCHW del .onnx. codes[c] son Span() muestras del canal c
// (en el orden de Spec.Canales); la columna t = T-1 es la más reciente.
func (f *Features) Inputs(codes [][]uint16) (mag, fase []float32) {
	s, T, NF := f.s, f.s.T, f.s.NF
	mag = make([]float32, len(codes)*T*NF)
	fase = make([]float32, 2*len(codes)*T*NF)
	if len(f.x) != f.Span() {
		f.x = make([]float32, f.Span())
	}
	k := s.VrefADC / 4095 / s.GDK
	for c, cc := range codes {
		for i, v := range cc[:len(f.x)] {
			f.x[i] = float32((float64(v)*k - s.VMid) / s.Gain * 1e6)
		}
		for t := 0; t < T; t++ {
			f.bank.Column(f.x, f.half+t*s.Hop, f.w)
			for fi, w := range f.w {
				a := cmplx.Abs(w)
				db := math.Min(math.Max(20*math.Log10(a+1e-12), s.DBMin), s.DBMax)
				z := math.Min(math.Max((db-s.Mu[c][fi])*s.InvSD[c][fi], -s.ZClip), s.ZClip)
				mag[(c*T+t)*NF+fi] = float32(z)
				fase[((2*c)*T+t)*NF+fi] = float32(real(w) / (a + 1e-12))
				fase[((2*c+1)*T+t)*NF+fi] = float32(imag(w) / (a + 1e-12))
			}
		}
	}
	return mag, fase
}
