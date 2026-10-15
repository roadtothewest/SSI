// Package ml corre en la Pi un clasificador exportado por el cuaderno de Colab
// (auravox_vocales_npu.ipynb): auravoxd calcula las entradas con la misma CWT con que
// se entrenó (dsp.Bank) y un proceso Python con onnxruntime evalúa el .onnx.
//
// Un modelo es la carpeta que sale del .zip del cuaderno: el .onnx, informe.json y la
// cabecera C (auravox_vocales.h), que define el preproceso igual que para la N6.
package ml

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

// Spec es lo que hace falta para armar las entradas del modelo y leer su salida.
type Spec struct {
	Name     string   `json:"name"`    // nombre del .onnx, sin extensión
	Onnx     string   `json:"onnx"`    // ruta del .onnx elegido
	Fecha    string   `json:"fecha"`   // de informe.json
	Clases   []string `json:"clases"`  // en el orden de los logits
	Canales  []int    `json:"canales"` // índices en adc[] del bloque (CH3 = 2)
	Entradas []string `json:"entradas"`

	Fs, Hop, T, NF int
	W0, FMin, FMax float64
	DBMin, DBMax   float64
	ZClip          float64
	VrefADC, GDK   float64
	VMid, Gain     float64
	Mu, InvSD      [][]float64 // [canal][frecuencia]
	UsaFase        bool

	AccBal float64 `json:"accBal"` // exactitud balanceada media de la validación cruzada (fp32)
}

var (
	defineRE = regexp.MustCompile(`(?m)^#define\s+AVX_VOC_(\w+)\s+\(?\s*([-+0-9.eE]+)f?\s*\)?`)
	arrayRE  = regexp.MustCompile(`(?s)avx_voc_(\w+)\s*\[[^=]*=\s*\{(.*?)\};`)
	numRE    = regexp.MustCompile(`[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?`)
	strRE    = regexp.MustCompile(`"([^"]*)"`)
)

// Load lee el modelo de la carpeta dir. Prefiere el .onnx int8 (el mismo que iría a la
// NPU de la N6) y si no hay, el de float.
func Load(dir string) (*Spec, error) {
	onnx, err := pickOnnx(dir)
	if err != nil {
		return nil, err
	}
	hdr, err := findOne(dir, ".h")
	if err != nil {
		return nil, err
	}
	src, err := os.ReadFile(hdr)
	if err != nil {
		return nil, err
	}
	s, err := parseHeader(string(src))
	if err != nil {
		return nil, fmt.Errorf("%s: %w", filepath.Base(hdr), err)
	}
	s.Onnx = onnx
	s.Name = strings.TrimSuffix(filepath.Base(onnx), ".onnx")
	if js, err := os.ReadFile(filepath.Join(dir, "informe.json")); err == nil {
		s.readInforme(js)
	}
	if len(s.Entradas) == 0 {
		s.Entradas = []string{"cwt_mag"}
		if s.UsaFase {
			s.Entradas = append(s.Entradas, "cwt_fase")
		}
	}
	return s, s.check()
}

func pickOnnx(dir string) (string, error) {
	all, _ := filepath.Glob(filepath.Join(dir, "*.onnx"))
	if len(all) == 0 {
		return "", errors.New("el paquete no trae un .onnx")
	}
	sort.Strings(all)
	for _, f := range all {
		if strings.Contains(filepath.Base(f), "int8") {
			return f, nil
		}
	}
	return all[0], nil
}

func findOne(dir, ext string) (string, error) {
	all, _ := filepath.Glob(filepath.Join(dir, "*"+ext))
	var keep []string
	for _, f := range all {
		if !strings.Contains(filepath.Base(f), "prueba") { // auravox_vocales_prueba.h = datos de prueba para la N6
			keep = append(keep, f)
		}
	}
	if len(keep) != 1 {
		return "", fmt.Errorf("se esperaba una cabecera %s con el preproceso, hay %d", ext, len(keep))
	}
	return keep[0], nil
}

func parseHeader(src string) (*Spec, error) {
	d := map[string]float64{}
	for _, m := range defineRE.FindAllStringSubmatch(src, -1) {
		if v, err := strconv.ParseFloat(m[2], 64); err == nil {
			d[m[1]] = v
		}
	}
	arr := map[string]string{}
	for _, m := range arrayRE.FindAllStringSubmatch(src, -1) {
		arr[m[1]] = m[2]
	}
	need := []string{"FS", "HOP", "T", "NF", "NCH", "NCLASES", "W0", "FMIN", "FMAX", "DB_MIN", "DB_MAX",
		"Z_CLIP", "VREF_ADC", "GDK", "VMID", "GAIN"}
	for _, k := range need {
		if _, ok := d[k]; !ok {
			return nil, fmt.Errorf("falta AVX_VOC_%s", k)
		}
	}
	if d["FASE_RELATIVA"] != 0 {
		return nil, errors.New("fase relativa: auravoxd todavía no la calcula")
	}
	s := &Spec{
		Fs: int(d["FS"]), Hop: int(d["HOP"]), T: int(d["T"]), NF: int(d["NF"]),
		W0: d["W0"], FMin: d["FMIN"], FMax: d["FMAX"], DBMin: d["DB_MIN"], DBMax: d["DB_MAX"],
		ZClip: d["Z_CLIP"], VrefADC: d["VREF_ADC"], GDK: d["GDK"], VMid: d["VMID"], Gain: d["GAIN"],
		UsaFase: d["USA_FASE"] != 0,
	}
	nch := int(d["NCH"])
	for _, v := range nums(arr["canal"]) {
		s.Canales = append(s.Canales, int(v))
	}
	mu, sd := nums(arr["mu"]), nums(arr["inv_sd"])
	if len(s.Canales) != nch || len(mu) != nch*s.NF || len(sd) != nch*s.NF {
		return nil, fmt.Errorf("canales/mu/inv_sd no calzan con NCH = %d y NF = %d", nch, s.NF)
	}
	for c := 0; c < nch; c++ {
		s.Mu = append(s.Mu, mu[c*s.NF:(c+1)*s.NF])
		s.InvSD = append(s.InvSD, sd[c*s.NF:(c+1)*s.NF])
	}
	for _, m := range strRE.FindAllStringSubmatch(arr["clases"], -1) {
		s.Clases = append(s.Clases, m[1])
	}
	if len(s.Clases) != int(d["NCLASES"]) {
		return nil, fmt.Errorf("hay %d clases y NCLASES = %v", len(s.Clases), d["NCLASES"])
	}
	return s, nil
}

func nums(body string) []float64 {
	var out []float64
	for _, t := range numRE.FindAllString(body, -1) {
		if v, err := strconv.ParseFloat(t, 64); err == nil {
			out = append(out, v)
		}
	}
	return out
}

func (s *Spec) readInforme(js []byte) {
	var inf struct {
		Fecha    string   `json:"fecha"`
		Entradas []string `json:"entradas"`
		Val      []struct {
			AccBal float64 `json:"acc_bal"`
		} `json:"validacion_cruzada"`
	}
	if json.Unmarshal(js, &inf) != nil {
		return
	}
	s.Fecha, s.Entradas = inf.Fecha, inf.Entradas
	for _, v := range inf.Val {
		s.AccBal += v.AccBal / float64(len(inf.Val))
	}
}

func (s *Spec) check() error {
	switch {
	case s.Fs != 2000:
		return fmt.Errorf("el modelo espera fs = %d Hz y el sEMG llega a 2000 Hz", s.Fs)
	case s.Hop <= 0 || s.T <= 0 || s.NF <= 1:
		return errors.New("HOP, T y NF deben ser positivos")
	case s.Gain <= 0 || s.GDK <= 0:
		return errors.New("ganancia o GDK no válidos")
	}
	for _, c := range s.Canales {
		if c < 0 || c > 2 {
			return fmt.Errorf("canal %d fuera de adc[0..2]", c)
		}
	}
	for _, e := range s.Entradas {
		if e != "cwt_mag" && e != "cwt_fase" {
			return fmt.Errorf("entrada %q: auravoxd solo arma cwt_mag y cwt_fase", e)
		}
	}
	return nil
}

// Window es lo que cubre una predicción: T columnas cada Hop muestras.
func (s *Spec) Window() time.Duration {
	return time.Duration(s.T*s.Hop) * time.Second / time.Duration(s.Fs)
}
