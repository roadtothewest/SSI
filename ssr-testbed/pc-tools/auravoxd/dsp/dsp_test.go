package dsp

import (
	"math"
	"math/cmplx"
	"math/rand"
	"testing"
)

func TestCWTPeakAtTone(t *testing.T) {
	const fs = 2000.0
	b := NewBank(fs, 20, 500, 32, 6)
	x := make([]float32, 2000)
	for i := range x {
		x[i] = float32(3 * math.Cos(2*math.Pi*100*float64(i)/fs))
	}
	out := make([]complex128, len(b.Freqs))
	b.Column(x, 1000, out)
	bi := 0
	for i := range out {
		if cmplx.Abs(out[i]) > cmplx.Abs(out[bi]) {
			bi = i
		}
	}
	if f := b.Freqs[bi]; math.Abs(f-100) > 10 {
		t.Fatalf("máximo en %.1f Hz, se esperaba ~100 Hz", f)
	}
	if a := cmplx.Abs(out[bi]); math.Abs(a-3) > 0.3 {
		t.Fatalf("|W| = %.2f, se esperaba ~3", a)
	}
}

// Envolvente sintética: pulsos aleatorios; la "voz" es la misma envolvente retrasada 60 ms.
func delayedPair(fs float64, n, delay int) (x, y []float32) {
	rng := rand.New(rand.NewSource(1))
	src := make([]float64, n+delay)
	for i := 0; i < len(src); i += 30 + rng.Intn(40) {
		for j := 0; j < 30 && i+j < len(src); j++ {
			src[i+j] += math.Sin(math.Pi * float64(j) / 30)
		}
	}
	x, y = make([]float32, n), make([]float32, n)
	for i := 0; i < n; i++ {
		x[i] = float32(src[i+delay])
		y[i] = float32(src[i])
	}
	return
}

func TestXCorrLag(t *testing.T) {
	const fs = 200.0
	x, y := delayedPair(fs, 800, 12) // 12 muestras = 60 ms
	r := XCorr(x, y, 60)
	i, _ := Peak(r)
	if lagMS := float64(i-60) * 1000 / fs; math.Abs(lagMS-60) > 10 {
		t.Fatalf("τ* = %.0f ms, se esperaba +60 ms", lagMS)
	}
}

func TestCrossWaveletPhaseLag(t *testing.T) {
	const fs = 200.0
	x, y := delayedPair(fs, 1600, 12)
	b := NewBank(fs, 1.5, 6, 6, 6)
	wx, wy := make([]complex128, 6), make([]complex128, 6)
	sum := make([]complex128, 6)
	for c := 500; c < 1100; c += 5 {
		b.Column(x, c, wx)
		b.Column(y, c, wy)
		for i := range sum {
			sum[i] += wx[i] * cmplx.Conj(wy[i])
		}
	}
	for i, f := range b.Freqs {
		lag := cmplx.Phase(sum[i]) / (2 * math.Pi * f) * 1000
		if math.Abs(lag-60) > 15 {
			t.Fatalf("f = %.1f Hz: lag por fase %.0f ms, se esperaba 60 ms", f, lag)
		}
	}
}

// Costo de una columna de CWT de la voz (16 kHz), la más cara del hop.
func BenchmarkColumnVoice(b *testing.B) {
	bank := NewBank(16000, 20, 500, 32, 6)
	h := bank.MaxHalf()
	x := make([]float32, 2*h+1)
	out := make([]complex128, 32)
	for i := 0; i < b.N; i++ {
		bank.Column(x, h, out)
	}
}
