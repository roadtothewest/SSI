package dsp

import (
	"math"
	"math/cmplx"
)

// Bank es un banco de wavelets Morlet complejas (ω0 = 6) en el dominio del tiempo.
//
// Se calcula columna por columna (un instante, todas las frecuencias). Así cada
// ventana de CWT cuesta solo lo que cubren los núcleos, y no hace falta una FFT:
//
//	W(f, c) = Σ_j x[c+j] · w_f[j] · e^{-i2πf j/fs}
//
// w_f es una gaussiana con σ = ω0/(2πf) segundos, truncada en ±3σ y normalizada
// a Σw = 2. Así, una senoide de amplitud A da |W| = A en su frecuencia, y la
// fase es la de la señal en el instante c.
type Bank struct {
	Fs    float64
	Freqs []float64
	k     [][]complex128 // núcleo j = -half..half
	half  []int
}

func NewBank(fs, fmin, fmax float64, nf int, w0 float64) *Bank {
	b := &Bank{Fs: fs}
	for i := 0; i < nf; i++ {
		f := fmin * math.Pow(fmax/fmin, float64(i)/float64(nf-1))
		sigma := w0 / (2 * math.Pi * f) * fs // en muestras
		half := int(math.Ceil(3 * sigma))
		k := make([]complex128, 2*half+1)
		sum := 0.0
		for j := -half; j <= half; j++ {
			sum += math.Exp(-float64(j*j) / (2 * sigma * sigma))
		}
		for j := -half; j <= half; j++ {
			w := 2 * math.Exp(-float64(j*j)/(2*sigma*sigma)) / sum
			k[j+half] = complex(w, 0) * cmplx.Exp(complex(0, -2*math.Pi*f*float64(j)/fs))
		}
		b.Freqs = append(b.Freqs, f)
		b.k = append(b.k, k)
		b.half = append(b.half, half)
	}
	return b
}

// MaxHalf es el semiancho del núcleo más largo (el de la frecuencia más baja), en muestras.
func (b *Bank) MaxHalf() int {
	m := 0
	for _, h := range b.half {
		m = max(m, h)
	}
	return m
}

// Column calcula W(f, c) para todas las frecuencias. Fuera de x se toma 0.
func (b *Bank) Column(x []float32, c int, out []complex128) {
	for fi, k := range b.k {
		h := b.half[fi]
		j0, j1 := max(-h, -c), min(h, len(x)-1-c)
		var acc complex128
		for j := j0; j <= j1; j++ {
			acc += complex(float64(x[c+j]), 0) * k[j+h]
		}
		out[fi] = acc
	}
}

// Half es el semiancho del núcleo de la frecuencia fi.
func (b *Bank) Half(fi int) int { return b.half[fi] }
