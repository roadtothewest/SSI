// avxcwt: análisis offline de una sesión .avx con el mismo banco Morlet de la HMI.
//
//	go run . [-gain 2500 | -gains g1,g2,g3] [-settle 1] sesion.avx
//
// Por canal: nivel DC en la entrada del DK, espectro Morlet medio (µV RTI) y, por ventanas
// de 0,5 s, la energía sEMG (20–500 Hz sin armónicos de 50 Hz), el 50 Hz y el nivel de la voz.
// Si existe sesion.json, cada ventana lleva su condición y se resume por condición
// (descartando las ventanas que empiezan antes de -settle s tras un cambio).
// -gain: 2500 para el AFE AuraVox, 200 para la salida RAW de un MyoWare 2.0.
// -gains: una ganancia por canal (p. ej. 200,1,1: RAW en CH1 y una envolvente en CH2 vista en V).
package main

import (
	"flag"
	"fmt"
	"math"
	"math/cmplx"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"auravoxd/dsp"
	"auravoxd/frame"
	"auravoxd/record"
)

const (
	fsEMG = 2000.0
	gdk   = 0.5437 // divisor del DK (MB1939)
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

var gain [3]float64 // ganancia desde el electrodo hasta el pin Arduino, por canal

func main() {
	g := flag.Float64("gain", 2500, "ganancia hasta el pin Arduino: 2500 = AFE AuraVox, 200 = MyoWare 2.0 RAW")
	gs := flag.String("gains", "", "ganancia por canal separada por comas (reemplaza a -gain)")
	settle := flag.Float64("settle", 1, "segundos descartados tras cada cambio de condición en el resumen")
	flag.Parse()
	if flag.NArg() != 1 {
		fmt.Fprintln(os.Stderr, "uso: avxcwt [-gain G | -gains g1,g2,g3] [-settle s] sesion.avx")
		os.Exit(2)
	}
	gain = [3]float64{*g, *g, *g}
	if *gs != "" {
		parts := strings.Split(*gs, ",")
		for c := 0; c < 3 && c < len(parts); c++ {
			v, err := strconv.ParseFloat(strings.TrimSpace(parts[c]), 64)
			if err != nil || v <= 0 {
				fmt.Fprintln(os.Stderr, "-gains inválido:", *gs)
				os.Exit(2)
			}
			gain[c] = v
		}
	}
	path := flag.Arg(0)
	raw, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	var emg [3][]float64
	var voice []float64
	var blkOf []uint64 // índice del bloque en el .avx de cada muestra EMG
	var sat [3]int
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
				if t.ADC[c] <= 8 || t.ADC[c] >= 4087 {
					sat[c]++
				}
			}
			blkOf = append(blkOf, uint64(o/frame.BlockSize))
			for _, v := range t.Voice {
				voice = append(voice, float64(v)/32768)
			}
		}
	}
	n := len(emg[0])
	fmt.Printf("%s: %d muestras por canal (%.1f s), %d bloques inválidos, ganancias %v\n\n", path, n, float64(n)/fsEMG, bad, gain)
	marks, err := record.LoadMarks(filepath.Dir(path), filepath.Base(path))
	if err != nil {
		fmt.Fprintln(os.Stderr, "marcas:", err)
	}

	// DC y µV RTI
	var uv [3][]float32
	fmt.Println("Nivel DC en la entrada del DK (esperado 1,65 V = mitad del riel de 3,3 V):")
	for c := 0; c < 3; c++ {
		mean, lo, hi := 0.0, math.Inf(1), math.Inf(-1)
		for _, v := range emg[c] {
			mean += v
			lo, hi = math.Min(lo, v), math.Max(hi, v)
		}
		mean /= float64(n)
		uv[c] = make([]float32, n)
		for i, v := range emg[c] {
			uv[c][i] = float32((v - mean) / gain[c] * 1e6)
		}
		fmt.Printf("  CH%d: media %.3f V, mín %.3f, máx %.3f (p-p %.1f mV = %.1f µV RTI), %d muestras saturadas\n",
			c+1, mean, lo, hi, (hi-lo)*1e3, (hi-lo)/gain[c]*1e6, sat[c])
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
	fmt.Println("    t [s]  condición     voz    | CH1 sEMG  50Hz | CH2 sEMG  50Hz | CH3 sEMG  50Hz")
	condW := make([]string, nw)
	sinceW := make([]float64, nw) // segundos desde el último cambio de condición al inicio de la ventana
	a50W := make([][]float64, 3)
	for c := range a50W {
		a50W[c] = make([]float64, nw)
	}
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
		condW[w], sinceW[w] = condAt(marks, blkOf[w*win], blkOf[(w+1)*win-1])
		fmt.Printf("  %6.1f  %-12s %6.1f   |", float64(w)*0.5, condW[w], vozW[w])
		for c := 0; c < 3; c++ {
			e, k := 0.0, 0
			for f := 0; f < nf; f++ {
				if !near50(bank.Freqs[f]) {
					e += mag[c][w][f]
					k++
				}
			}
			emgW[c][w] = e / float64(k)
			a50W[c][w] = dsp.ToneAmp(uv[c][w*win:(w+1)*win], fsEMG, 50)
			fmt.Printf(" %7.2f %6.2f |", emgW[c][w], a50W[c][w])
		}
		fmt.Println()
	}

	if len(marks) > 0 {
		summary(uv, mag, emgW, a50W, condW, sinceW, *settle, bank.Freqs)
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

// condAt devuelve la condición vigente en el bloque b0 y los segundos desde la marca que la
// inició; si la condición cambia dentro de la ventana [b0, b1], la ventana es de transición.
func condAt(marks []record.Mark, b0, b1 uint64) (string, float64) {
	cond, since := "—", math.Inf(1)
	for _, m := range marks {
		if m.Block <= b0 {
			cond, since = m.Cond, float64(b0-m.Block)*0.01
		} else if m.Block <= b1 {
			return "transición", 0
		}
	}
	return cond, since
}

// summary resume por condición: RMS en el tiempo, nivel sEMG Morlet, 50 Hz y frecuencia
// mediana de CH1..CH3, más el contraste respecto de "reposo".
func summary(uv [3][]float32, mag [][][]float64, emgW, a50W [][]float64, condW []string, sinceW []float64, settle float64, freqs []float64) {
	type acc struct {
		n          int
		rms, e, hu [3]float64
		spec       [3][]float64
	}
	byCond := map[string]*acc{}
	var order []string
	for w, c := range condW {
		if c == "—" || c == "transición" || sinceW[w] < settle {
			continue
		}
		a := byCond[c]
		if a == nil {
			a = &acc{}
			for ch := 0; ch < 3; ch++ {
				a.spec[ch] = make([]float64, len(freqs))
			}
			byCond[c] = a
			order = append(order, c)
		}
		a.n++
		for ch := 0; ch < 3; ch++ {
			seg := uv[ch][w*win : (w+1)*win]
			m, s2 := 0.0, 0.0
			for _, v := range seg {
				m += float64(v)
			}
			m /= float64(len(seg))
			for _, v := range seg {
				s2 += (float64(v) - m) * (float64(v) - m)
			}
			a.rms[ch] += s2 / float64(len(seg)) // se promedia la potencia
			a.e[ch] += emgW[ch][w]
			a.hu[ch] += a50W[ch][w]
			for f := range freqs {
				a.spec[ch][f] += mag[ch][w][f] * mag[ch][w][f]
			}
		}
	}
	fmt.Printf("\nResumen por condición (ventanas de 0,5 s, sin las de transición ni las primeras %.1f s tras cada cambio):\n", settle)
	fmt.Println("  condición    ventanas | canal  RMS [µV RTI]  sEMG Morlet [µV]  50 Hz [µV]  f mediana [Hz]  vs reposo")
	ref := byCond["reposo"]
	for _, c := range order {
		a := byCond[c]
		for ch := 0; ch < 3; ch++ {
			rms := math.Sqrt(a.rms[ch] / float64(a.n))
			vs := "—"
			if ref != nil && c != "reposo" {
				r0 := math.Sqrt(ref.rms[ch] / float64(ref.n))
				vs = fmt.Sprintf("%+.1f dB", 20*math.Log10(rms/r0))
			}
			label, nwin := "", ""
			if ch == 0 {
				label, nwin = c, fmt.Sprint(a.n)
			}
			fmt.Printf("  %-12s %8s | CH%d   %12.2f  %16.2f  %10.2f  %14.0f  %s\n", label, nwin, ch+1,
				rms, a.e[ch]/float64(a.n), a.hu[ch]/float64(a.n), medianFreq(a.spec[ch], freqs), vs)
		}
	}
}

// medianFreq: frecuencia que deja la mitad de la potencia a cada lado, sin los armónicos de 50 Hz.
// Con el banco log-espaciado de Q constante, |W|² por bin ya es proporcional a la potencia del bin.
func medianFreq(p, freqs []float64) float64 {
	tot := 0.0
	for f := range p {
		if !near50(freqs[f]) {
			tot += p[f]
		}
	}
	cum := 0.0
	for f := range p {
		if near50(freqs[f]) {
			continue
		}
		cum += p[f]
		if cum >= tot/2 {
			return freqs[f]
		}
	}
	return math.NaN()
}
