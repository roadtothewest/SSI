package ml

import (
	"context"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"auravoxd/frame"
)

// Prueba de punta a punta con el modelo real y las grabaciones con que se entrenó:
//
//	AURAVOX_ML_PY=<python con onnxruntime> AURAVOX_ML_MODEL=<carpeta del .zip>
//	AURAVOX_ML_AVX=<carpeta con los .avx> go test ./ml -run Recordings -v
//
// Las ventanas con voz de cada vocal y las de los silencios deben salir, en su mayoría,
// con la clase del archivo (el modelo las vio al entrenar: exactitud ~0,8 en el cuaderno).
func TestRecordingsEndToEnd(t *testing.T) {
	py, mdir, adir := os.Getenv("AURAVOX_ML_PY"), os.Getenv("AURAVOX_ML_MODEL"), os.Getenv("AURAVOX_ML_AVX")
	if py == "" || mdir == "" || adir == "" {
		t.Skip("sin AURAVOX_ML_PY / AURAVOX_ML_MODEL / AURAVOX_ML_AVX")
	}
	spec, err := Load(mdir)
	if err != nil {
		t.Fatal(err)
	}
	script := filepath.Join(t.TempDir(), "runner.py")
	os.WriteFile(script, runnerPy, 0o644)
	p, err := startProc(context.Background(), py, script, "", spec.Onnx)
	if err != nil {
		t.Fatal(err)
	}
	defer p.close()
	feat := NewFeatures(spec)
	files, _ := filepath.Glob(filepath.Join(adir, "*.avx"))
	sort.Strings(files)
	hit, tot := 0, 0
	for _, f := range files {
		label := strings.SplitN(filepath.Base(f), "-", 2)[0]
		if strings.HasPrefix(label, "silencio") {
			label = "reposo"
		}
		if !contains(spec.Clases, label) {
			continue
		}
		emg, vdb := readAvx(t, f, spec.Canales)
		count := map[string]int{}
		n := 0
		// Una predicción cada 100 ms, como en vivo; en las vocales, solo con voz.
		for end := feat.Span(); end <= len(emg[0]); end += 200 {
			col := end - 1 - feat.Delay() // última columna de la ventana
			if label != "reposo" && vdb[col/frame.NTuples] < -45 {
				continue
			}
			codes := make([][]uint16, len(emg))
			for c := range emg {
				codes[c] = emg[c][end-feat.Span() : end]
			}
			mag, fase := feat.Inputs(codes)
			y, err := p.eval(map[string][]float32{"cwt_mag": mag, "cwt_fase": fase})
			if err != nil {
				t.Fatal(err)
			}
			count[spec.Clases[argmax(y)]]++
			n++
		}
		if n == 0 {
			continue
		}
		hit += count[label]
		tot += n
		t.Logf("%-20s %-6s %3.0f %% de %3d  %v", filepath.Base(f), label, 100*float64(count[label])/float64(n), n, count)
	}
	acc := float64(hit) / float64(tot)
	t.Logf("total: %.0f %% de %d ventanas con la clase del archivo", 100*acc, tot)
	if acc < 0.5 {
		t.Errorf("exactitud %.2f: el preproceso de Go no reproduce el del entrenamiento", acc)
	}
}

// readAvx devuelve los códigos de los canales pedidos y la energía de la voz por bloque (dBFS).
func readAvx(t *testing.T, path string, chans []int) ([][]uint16, []float64) {
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	emg := make([][]uint16, len(chans))
	var vdb []float64
	var b frame.Block
	for o := 0; o+frame.BlockSize <= len(raw); o += frame.BlockSize {
		if frame.Decode(raw[o:o+frame.BlockSize], &b) != nil {
			continue
		}
		e := 0.0
		for _, tu := range b.Tuples {
			for i, ch := range chans {
				emg[i] = append(emg[i], tu.ADC[ch])
			}
			for _, v := range tu.Voice {
				e += float64(v) * float64(v) / (32768 * 32768)
			}
		}
		vdb = append(vdb, 10*math.Log10(e/float64(frame.NTuples*frame.NVoice)+1e-12))
	}
	return emg, vdb
}

func argmax(y []float32) int {
	b := 0
	for i, v := range y {
		if v > y[b] {
			b = i
		}
	}
	return b
}

func contains(xs []string, s string) bool {
	for _, x := range xs {
		if x == s {
			return true
		}
	}
	return false
}
