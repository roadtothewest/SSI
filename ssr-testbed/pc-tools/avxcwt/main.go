// avxcwt: análisis offline de una sesión .avx con el mismo banco Morlet de la HMI.
//
//	go run . sesion.avx
//
// Por canal: nivel DC a la salida del AFE, espectro Morlet medio (µV RTI) y, por ventanas
// de 0,5 s, la energía sEMG (20–500 Hz sin armónicos de 50 Hz), el 50 Hz y el nivel de la voz.
package main

import (
	"fmt"
	"math"
	"math/cmplx"
	"os"
	"sort"

	"auravoxd/dsp"
	"auravoxd/frame"
)

const (
	fsEMG = 2000.0
	gdk   = 0.5437 // divisor del DK (MB1939)
	gain  = 2500.0 // ganancia del AFE
	win   = 1000   // 0,5 s
	step  = 4      // una columna de CWT cada 4 muestras
)

func vAFE(code uint16) float64 { return float64(code) / 4095 * 1.8 / gdk }

func near50(f float64) bool {
	for h := 50.0; h <= 500; h += 50 {
		if math.Abs(f-h) < 6 {
			return true
		}
	}
	return false
}

func main() {
	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	var emg [3][]float64
	var voice []float64
	var blk frame.Block
	bad := 0
	for o := 0; o+frame.BlockSize <= len(raw); o += frame.BlockSize {
		if frame.Decode(raw[o:o+frame.BlockSize], &blk) != nil {
			bad++
			continue
		}
		for _, t := range blk.Tuples {
			for c := 0; c < 3; c++ {
				emg[c] = append(emg[c], vAFE(t.ADC[c]))
			}
			for _, v := range t.Voice {
				voice = append(voice, float64(v)/32768)
			}
		}
	}
	n := len(emg[0])
	fmt.Printf("%s: %d muestras por canal (%.1f s), %d bloques inválidos\n\n", os.Args[1], n, float64(n)/fsEMG, bad)

	// DC y µV RTI
	var uv [3][]float32
	fmt.Println("Nivel DC a la salida del AFE (esperado 1,65 V = VREF):")
	for c := 0; c < 3; c++ {
		mean, lo, hi := 0.0, math.Inf(1), math.Inf(-1)
		for _, v := range emg[c] {
			mean += v
			lo, hi = math.Min(lo, v), math.Max(hi, v)
		}
		mean /= float64(n)
		uv[c] = make([]float32, n)
		for i, v := range emg[c] {
			uv[c][i] = float32((v - mean) / gain * 1e6)
		}
		fmt.Printf("  CH%d: media %.3f V, mín %.3f, máx %.3f (p-p %.1f mV = %.1f µV RTI)\n",
			c+1, mean, lo, hi, (hi-lo)*1e3, (hi-lo)/gain*1e6)
	}

	bank := dsp.NewBank(fsEMG, 20, 500, 32, 6)
	nf := len(bank.Freqs)
	nw := n / win
	col := make([]complex128, nf)
	// mag[c][w][f] = |W| medio de la ventana w
	mag := make([][][]float64, 3)
	for c := 0; c < 3; c++ {
		mag[c] = make([][]float64, nw)
		for w := 0; w < nw; w++ {
			acc := make([]float64, nf)
			cnt := 0
			for i := w * win; i < (w+1)*win; i += step {
				bank.Column(uv[c], i, col)
				for f := range col {
					acc[f] += cmplx.Abs(col[f])
				}
				cnt++
			}
			for f := range acc {
				acc[f] /= float64(cnt)
			}
			mag[c][w] = acc
		}
	}

	// Espectro medio (mediana por frecuencia sobre las ventanas)
	fmt.Println("\nEspectro Morlet (mediana de las ventanas), amplitud en µV RTI:")
	fmt.Println("   f [Hz]    CH1     CH2     CH3")
	for f := 0; f < nf; f++ {
		fmt.Printf("  %6.1f", bank.Freqs[f])
		for c := 0; c < 3; c++ {
			v := make([]float64, nw)
			for w := 0; w < nw; w++ {
				v[w] = mag[c][w][f]
			}
			sort.Float64s(v)
			fmt.Printf("  %6.2f", v[nw/2])
		}
		mark := ""
		if near50(bank.Freqs[f]) {
			mark = "  ← armónico de 50 Hz"
		}
		fmt.Println(mark)
	}

	// Serie temporal por ventana
	fmt.Println("\nPor ventana de 0,5 s: voz [dBFS] | por canal: sEMG 20–500 Hz sin 50 Hz [µV] y 50 Hz [µV]")
	fmt.Println("    t [s]   voz    | CH1 sEMG  50Hz | CH2 sEMG  50Hz | CH3 sEMG  50Hz")
	vozW := make([]float64, nw)
	emgW := make([][]float64, 3)
	for c := range emgW {
		emgW[c] = make([]float64, nw)
	}
	for w := 0; w < nw; w++ {
		s := 0.0
		for _, v := range voice[w*win*8 : (w+1)*win*8] {
			s += v * v
		}
		vozW[w] = 10 * math.Log10(s/float64(win*8)+1e-12)
		fmt.Printf("  %6.1f  %6.1f   |", float64(w)*0.5, vozW[w])
		for c := 0; c < 3; c++ {
			e, k := 0.0, 0
			for f := 0; f < nf; f++ {
				if !near50(bank.Freqs[f]) {
					e += mag[c][w][f]
					k++
				}
			}
			emgW[c][w] = e / float64(k)
			a50 := dsp.ToneAmp(uv[c][w*win:(w+1)*win], fsEMG, 50) * 1
			fmt.Printf(" %7.2f %6.2f |", emgW[c][w], a50)
		}
		fmt.Println()
	}

	// Correlación sEMG ↔ voz
	fmt.Println("\nCorrelación (Pearson) entre la energía sEMG por ventana y el nivel de la voz:")
	for c := 0; c < 3; c++ {
		fmt.Printf("  CH%d: r = %+.2f\n", c+1, pearson(emgW[c], vozW))
	}
}

func pearson(x, y []float64) float64 {
	n := float64(len(x))
	var mx, my float64
	for i := range x {
		mx += x[i]
		my += y[i]
	}
	mx /= n
	my /= n
	var sxy, sxx, syy float64
	for i := range x {
		sxy += (x[i] - mx) * (y[i] - my)
		sxx += (x[i] - mx) * (x[i] - mx)
		syy += (y[i] - my) * (y[i] - my)
	}
	return sxy / math.Sqrt(sxx*syy+1e-30)
}
