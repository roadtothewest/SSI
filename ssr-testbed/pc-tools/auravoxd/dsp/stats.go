package dsp

import (
	"math"
	"sort"
)

// XCorr devuelve r(τ) para τ = -maxLag..maxLag (en muestras): la correlación de
// Pearson entre x[t] y y[t+τ] en la parte que se superpone.
// τ > 0 significa que y (la voz) viene después de x (el sEMG): el sEMG se adelanta.
func XCorr(x, y []float32, maxLag int) []float32 {
	r := make([]float32, 2*maxLag+1)
	n := len(x)
	for l := -maxLag; l <= maxLag; l++ {
		t0, t1 := max(0, -l), min(n, n-l)
		if t1-t0 < 10 {
			continue
		}
		var sx, sy, sxx, syy, sxy float64
		for t := t0; t < t1; t++ {
			a, b := float64(x[t]), float64(y[t+l])
			sx += a
			sy += b
			sxx += a * a
			syy += b * b
			sxy += a * b
		}
		m := float64(t1 - t0)
		cov := sxy - sx*sy/m
		den := math.Sqrt((sxx - sx*sx/m) * (syy - sy*sy/m))
		if den > 0 {
			r[l+maxLag] = float32(cov / den)
		}
	}
	return r
}

// Peak devuelve el índice y el valor del máximo de r.
func Peak(r []float32) (int, float32) {
	bi, bv := 0, float32(math.Inf(-1))
	for i, v := range r {
		if v > bv {
			bi, bv = i, v
		}
	}
	return bi, bv
}

// RMS sin la media.
func RMS(x []float32) float64 {
	if len(x) == 0 {
		return 0
	}
	var s, ss float64
	for _, v := range x {
		s += float64(v)
		ss += float64(v) * float64(v)
	}
	n := float64(len(x))
	return math.Sqrt(math.Max(ss/n-(s/n)*(s/n), 0))
}

// ToneAmp es la amplitud (pico) de la componente de frecuencia f, por DFT en un solo bin.
func ToneAmp(x []float32, fs, f float64) float64 {
	if len(x) == 0 {
		return 0
	}
	var mean float64
	for _, v := range x {
		mean += float64(v)
	}
	mean /= float64(len(x))
	var re, im float64
	w := 2 * math.Pi * f / fs
	for i, v := range x {
		a := float64(v) - mean
		re += a * math.Cos(w*float64(i))
		im -= a * math.Sin(w*float64(i))
	}
	return 2 * math.Hypot(re, im) / float64(len(x))
}

// F0 estima la frecuencia fundamental por autocorrelación normalizada en [fmin, fmax].
// Devuelve 0 si la señal no es sonora (correlación < 0.3).
func F0(x []float32, fs, fmin, fmax float64) float64 {
	l0, l1 := int(fs/fmax), int(fs/fmin)
	if len(x) < 2*l1 {
		return 0
	}
	best, bl := 0.0, 0
	for l := l0; l <= l1; l++ {
		var sxy, sxx, syy float64
		for i := 0; i+l < len(x); i++ {
			a, b := float64(x[i]), float64(x[i+l])
			sxy += a * b
			sxx += a * a
			syy += b * b
		}
		if sxx > 0 && syy > 0 {
			if r := sxy / math.Sqrt(sxx*syy); r > best {
				best, bl = r, l
			}
		}
	}
	if best < 0.3 || bl == 0 {
		return 0
	}
	return fs / float64(bl)
}

// Baseline estima el nivel de reposo de una envolvente: media y desviación del
// 20 % de muestras más bajas.
func Baseline(env []float32) (mean, sd float64) {
	if len(env) == 0 {
		return 0, 0
	}
	s := append([]float32(nil), env...)
	sort.Slice(s, func(i, j int) bool { return s[i] < s[j] })
	s = s[:max(1, len(s)/5)]
	for _, v := range s {
		mean += float64(v)
	}
	mean /= float64(len(s))
	for _, v := range s {
		sd += (float64(v) - mean) * (float64(v) - mean)
	}
	return mean, math.Sqrt(sd / float64(len(s)))
}

// Thresholds de onset/offset con histéresis (umbral tipo media + 3·DE, Stepp 2009).
// El término proporcional a la media evita umbrales absurdamente bajos cuando el ruido es muy pequeño.
func Thresholds(mean, sd float64) (on, off float64) {
	return mean + 3*sd + 0.5*mean, mean + 1.5*sd + 0.25*mean
}

// Onset devuelve el primer índice desde el que env supera on durante hold muestras, o -1.
func Onset(env []float32, on float64, hold int) int {
	run := 0
	for i, v := range env {
		if float64(v) > on {
			run++
			if run >= hold {
				return i - hold + 1
			}
		} else {
			run = 0
		}
	}
	return -1
}

// MedianIQR devuelve la mediana y el rango intercuartil.
func MedianIQR(v []float64) (med, iqr float64) {
	if len(v) == 0 {
		return math.NaN(), math.NaN()
	}
	s := append([]float64(nil), v...)
	sort.Float64s(s)
	q := func(p float64) float64 {
		x := p * float64(len(s)-1)
		i := int(x)
		if i+1 >= len(s) {
			return s[i]
		}
		return s[i] + (x-float64(i))*(s[i+1]-s[i])
	}
	return q(0.5), q(0.75) - q(0.25)
}
