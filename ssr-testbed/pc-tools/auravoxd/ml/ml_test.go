package ml

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"testing"
	"time"

	"auravoxd/frame"
	"auravoxd/stream"
)

func TestTheNotebookHeaderGivesTheModelSpec(t *testing.T) {
	src, err := os.ReadFile("testdata/auravox_vocales.h")
	if err != nil {
		t.Fatal(err)
	}
	s, err := parseHeader(string(src))
	if err != nil {
		t.Fatal(err)
	}
	if s.Fs != 2000 || s.Hop != 20 || s.T != 32 || s.NF != 32 || s.W0 != 6 || s.DBMin != -20 || s.Gain != 2500 || !s.UsaFase {
		t.Fatalf("constantes: %+v", s)
	}
	if len(s.Canales) != 1 || s.Canales[0] != 2 {
		t.Fatalf("canales = %v, want [2] (CH3)", s.Canales)
	}
	if want := []string{"reposo", "a", "e", "i", "o", "u"}; fmt.Sprint(s.Clases) != fmt.Sprint(want) {
		t.Fatalf("clases = %v", s.Clases)
	}
	if len(s.Mu[0]) != 32 || s.Mu[0][0] != -11.855948 || s.InvSD[0][31] != 0.16980134 {
		t.Fatalf("mu/inv_sd mal leídos: %v … %v", s.Mu[0][0], s.InvSD[0][31])
	}
}

// Una senoide de 100 Hz y 200 µV: el dB de la columna está en la frecuencia más cercana a
// 100 Hz, la fase sale en el círculo unitario y la ventana cubre T columnas.
func TestFeaturesFollowTheHeaderFormulas(t *testing.T) {
	src, _ := os.ReadFile("testdata/auravox_vocales.h")
	s, _ := parseHeader(string(src))
	f := NewFeatures(s)
	if f.Span() != 31*20+2*287+1 {
		t.Fatalf("span = %d", f.Span())
	}
	codes := make([]uint16, f.Span())
	for i := range codes {
		uv := 200 * math.Sin(2*math.Pi*100*float64(i)/2000)
		v := (s.VMid + uv*1e-6*s.Gain) * s.GDK / s.VrefADC * 4095
		codes[i] = uint16(math.Round(v))
	}
	mag, fase := f.Inputs([][]uint16{codes})
	if len(mag) != 32*32 || len(fase) != 2*32*32 {
		t.Fatalf("tamaños %d y %d", len(mag), len(fase))
	}
	// Se deshace el z-score para comparar dB entre frecuencias.
	best, bdb := 0, math.Inf(-1)
	for fi := 0; fi < 32; fi++ {
		db := float64(mag[(0*32+31)*32+fi])/s.InvSD[0][fi] + s.Mu[0][fi]
		if db > bdb {
			best, bdb = fi, db
		}
	}
	if fr := f.bank.Freqs[best]; fr < 90 || fr > 110 {
		t.Errorf("pico en %.0f Hz, want ~100", fr)
	}
	if math.Abs(bdb-20*math.Log10(200)) > 1 {
		t.Errorf("pico de %.1f dB, want ~%.1f (200 µV)", bdb, 20*math.Log10(200))
	}
	for i := 0; i < 32*32; i++ {
		c, sn := float64(fase[i]), float64(fase[32*32+i])
		if math.Abs(c*c+sn*sn-1) > 1e-3 {
			t.Fatalf("cos²+sin² = %v en %d", c*c+sn*sn, i)
		}
	}
}

// --- evaluador falso: hace de runner.py, con las mismas entradas que el modelo real.

func TestMain(m *testing.M) {
	if os.Getenv("AURAVOX_FAKE_RUNNER") == "1" {
		fakeRunner()
		os.Exit(0)
	}
	os.Exit(m.Run())
}

// fakeRunner responde logits que eligen la clase 2 ("e") si llegan valores finitos.
func fakeRunner() {
	head, _ := json.Marshal(map[string]any{"inputs": []ioDesc{
		{"cwt_mag", []int{1, 1, 32, 32}}, {"cwt_fase", []int{1, 2, 32, 32}}}, "ort": "falso"})
	os.Stdout.Write(append(head, '\n'))
	for {
		var h [4]byte
		if _, err := io.ReadFull(os.Stdin, h[:]); err != nil {
			return
		}
		body := make([]byte, binary.LittleEndian.Uint32(h[:]))
		if _, err := io.ReadFull(os.Stdin, body); err != nil {
			return
		}
		y := []float32{0, 0, 5, 0, 0, 0}
		for i := 0; i < len(body); i += 4 {
			if v := math.Float32frombits(binary.LittleEndian.Uint32(body[i:])); math.IsNaN(float64(v)) {
				y[2] = -5
			}
		}
		out := make([]byte, 4+4*len(y))
		binary.LittleEndian.PutUint32(out, uint32(4*len(y)))
		for i, v := range y {
			binary.LittleEndian.PutUint32(out[4+4*i:], math.Float32bits(v))
		}
		os.Stdout.Write(out)
	}
}

// fakePython es un "python" que lanza este mismo binario de prueba como evaluador.
func fakePython(t *testing.T) string {
	exe, _ := os.Executable()
	p := filepath.Join(t.TempDir(), "python")
	os.WriteFile(p, []byte("#!/bin/sh\nAURAVOX_FAKE_RUNNER=1 exec "+exe+"\n"), 0o755)
	return p
}

func modelZip(t *testing.T, files map[string]string) []byte {
	var b bytes.Buffer
	z := zip.NewWriter(&b)
	for name, src := range files {
		w, _ := z.Create(name)
		if src != "" {
			data, err := os.ReadFile(src)
			if err != nil {
				t.Fatal(err)
			}
			w.Write(data)
		}
	}
	z.Close()
	return b.Bytes()
}

func TestUploadingAModelMakesItPredictLive(t *testing.T) {
	st := stream.NewStore(stream.Conv{VrefADC: 1.8, GDK: 0.5437, VMid: 1.65, Gain: 2500})
	m := NewManager(t.TempDir(), fakePython(t), st)
	m.Period = 10 * time.Millisecond
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go m.Run(ctx)

	if _, err := m.Install(ctx, []byte("no es un zip")); err == nil {
		t.Fatal("aceptó algo que no es un .zip")
	}
	if _, err := m.Install(ctx, modelZip(t, map[string]string{"informe.json": "testdata/informe.json"})); err == nil {
		t.Fatal("aceptó un paquete sin .onnx ni cabecera")
	}
	zipData := modelZip(t, map[string]string{
		"export/auravox_vocales.h": "testdata/auravox_vocales.h", "export/informe.json": "testdata/informe.json",
		"export/auravox_vocales_int8.onnx": "", "../fuera.txt": ""})
	spec, err := m.Install(ctx, zipData)
	if err != nil {
		t.Fatal(err)
	}
	if spec.Name != "auravox_vocales_int8" || spec.AccBal < 0.28 || spec.AccBal > 0.29 {
		t.Fatalf("spec = %s, accBal %.3f", spec.Name, spec.AccBal)
	}
	if _, err := os.Stat(filepath.Join(m.Dir, "..", "fuera.txt")); err == nil {
		t.Fatal("un nombre con .. salió de la carpeta")
	}

	// 1 s de bloques: alcanza para una ventana (931 muestras).
	b := frame.Block{}
	raw := make([]byte, frame.BlockSize)
	for seq := uint32(0); seq < 100; seq++ {
		b.Seq = seq
		for i := range b.Tuples {
			b.Tuples[i].ADC = [3]uint16{2048, 2048, uint16(2048 + 50*math.Sin(float64(seq*20+uint32(i))))}
		}
		frame.Encode(&b, raw)
		st.Ingest(raw)
	}
	for end := time.Now().Add(5 * time.Second); ; time.Sleep(10 * time.Millisecond) {
		s := m.Status()
		if s.State == "activo" && s.Pred != nil {
			if s.Pred.Clase != "e" || s.Ort != "falso" {
				t.Fatalf("predicción %+v, ort %q", s.Pred, s.Ort)
			}
			break
		}
		if time.Now().After(end) {
			t.Fatalf("sin predicción: %+v", s)
		}
	}
	// Sin muestras nuevas, la predicción queda marcada como vieja.
	for end := time.Now().Add(time.Second); !m.Status().Pred.Stale; time.Sleep(10 * time.Millisecond) {
		if time.Now().After(end) {
			t.Fatal("la predicción no se marcó como vieja")
		}
	}
}
