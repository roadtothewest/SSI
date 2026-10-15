package ml

import (
	"archive/zip"
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"log"
	"math"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"auravoxd/stream"
)

// Carpeta de ML (Manager.Dir), dentro de la carpeta de datos:
//
//	modelo/    el modelo activo (contenido del .zip del cuaderno)
//	anterior/  el que había antes de la última subida
//	lib/       paquetes de Python para el evaluador (onnxruntime, numpy, ...)
//	runner.py  el evaluador (se escribe al arrancar)
const (
	dirModel = "modelo"
	dirPrev  = "anterior"
	dirLib   = "lib"
	maxZip   = 100 << 20
	smooth   = 3 // predicciones promediadas (100 ms cada una)
)

type Pred struct {
	Clase string    `json:"clase"`
	Probs []float64 `json:"probs"` // promedio de las últimas predicciones, en el orden de Spec.Clases
	MS    float64   `json:"ms"`    // tiempo de la última evaluación
	Stale bool      `json:"stale"` // no llegan muestras nuevas
}

type Status struct {
	State  string   `json:"state"` // sin-modelo | cargando | activo | error
	Err    string   `json:"err,omitempty"`
	Model  string   `json:"model,omitempty"`
	Fecha  string   `json:"fecha,omitempty"`
	Clases []string `json:"clases,omitempty"`
	Canal  []int    `json:"canal,omitempty"`
	WinMS  int      `json:"winMs,omitempty"`
	AccBal float64  `json:"accBal,omitempty"`
	Ort    string   `json:"ort,omitempty"`
	Pred   *Pred    `json:"pred,omitempty"`
}

type Manager struct {
	Dir    string
	Python string
	St     *stream.Store
	Period time.Duration

	mu     sync.Mutex
	status Status
	reload chan struct{}
	inst   sync.Mutex // una subida a la vez
}

func NewManager(dir, python string, st *stream.Store) *Manager {
	return &Manager{Dir: dir, Python: python, St: st, Period: 100 * time.Millisecond,
		reload: make(chan struct{}, 1), status: Status{State: "sin-modelo"}}
}

func (m *Manager) Status() Status {
	m.mu.Lock()
	defer m.mu.Unlock()
	s := m.status
	if s.Pred != nil {
		p := *s.Pred
		s.Pred = &p
	}
	return s
}

func (m *Manager) set(f func(*Status)) {
	m.mu.Lock()
	f(&m.status)
	m.mu.Unlock()
}

func (m *Manager) script() string { return filepath.Join(m.Dir, "runner.py") }

// Run mantiene el evaluador del modelo activo y predice cada Period. Si falla, reintenta
// cada 10 s; una subida nueva lo reinicia al tiro.
func (m *Manager) Run(ctx context.Context) {
	if err := os.MkdirAll(m.Dir, 0o755); err == nil {
		os.WriteFile(m.script(), runnerPy, 0o644)
	}
	for ctx.Err() == nil {
		err := m.serve(ctx)
		if ctx.Err() != nil {
			return
		}
		if err == nil {
			continue // se pidió recargar
		}
		wait := 10 * time.Second
		if errors.Is(err, errNoModel) {
			m.set(func(s *Status) { *s = Status{State: "sin-modelo"} })
			wait = time.Hour
		} else if err != nil {
			log.Printf("ml: %v", err)
			m.set(func(s *Status) { s.State, s.Err, s.Pred = "error", err.Error(), nil })
		}
		select {
		case <-ctx.Done():
		case <-m.reload:
		case <-time.After(wait):
		}
	}
}

var errNoModel = errors.New("sin modelo")

func (m *Manager) serve(ctx context.Context) error {
	dir := filepath.Join(m.Dir, dirModel)
	if _, err := os.Stat(dir); err != nil {
		return errNoModel
	}
	spec, err := Load(dir)
	if err != nil {
		return err
	}
	m.set(func(s *Status) {
		*s = Status{State: "cargando", Model: spec.Name, Fecha: spec.Fecha, Clases: spec.Clases,
			Canal: spec.Canales, WinMS: int(spec.Window() / time.Millisecond), AccBal: spec.AccBal}
	})
	pctx, cancel := context.WithCancel(ctx)
	defer cancel()
	p, err := startProc(pctx, m.Python, m.script(), filepath.Join(m.Dir, dirLib), spec.Onnx)
	if err != nil {
		return err
	}
	defer p.close()
	m.set(func(s *Status) { s.State, s.Ort = "activo", p.Ort })
	log.Printf("ml: modelo %s activo (onnxruntime %s)", spec.Name, p.Ort)

	feat := NewFeatures(spec)
	codes := make([][]uint16, len(spec.Canales))
	for i := range codes {
		codes[i] = make([]uint16, feat.Span())
	}
	var hist [][]float64
	last := int64(-1)
	t := time.NewTicker(m.Period)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-m.reload:
			return nil
		case <-t.C:
		}
		nE, _, _ := m.St.Counts()
		if nE == last {
			m.set(func(s *Status) {
				if s.Pred != nil {
					s.Pred.Stale = true
				}
			})
			continue
		}
		last = nE
		ok := true
		for i, ch := range spec.Canales {
			ok = ok && m.St.ReadCodes(ch, nE-int64(feat.Span()), codes[i])
		}
		if !ok {
			continue
		}
		t0 := time.Now()
		mag, fase := feat.Inputs(codes)
		y, err := p.eval(map[string][]float32{"cwt_mag": mag, "cwt_fase": fase})
		if err != nil {
			return err
		}
		if len(y) != len(spec.Clases) {
			return fmt.Errorf("el modelo da %d salidas y hay %d clases", len(y), len(spec.Clases))
		}
		hist = append(hist, softmax(y))
		if len(hist) > smooth {
			hist = hist[1:]
		}
		pr := &Pred{Probs: make([]float64, len(y)), MS: float64(time.Since(t0).Microseconds()) / 1000}
		for _, h := range hist {
			for i, v := range h {
				pr.Probs[i] += v / float64(len(hist))
			}
		}
		best := 0
		for i, v := range pr.Probs {
			if v > pr.Probs[best] {
				best = i
			}
		}
		pr.Clase = spec.Clases[best]
		m.set(func(s *Status) { s.Pred = pr })
	}
}

func softmax(y []float32) []float64 {
	mx := math.Inf(-1)
	for _, v := range y {
		mx = math.Max(mx, float64(v))
	}
	out := make([]float64, len(y))
	sum := 0.0
	for i, v := range y {
		out[i] = math.Exp(float64(v) - mx)
		sum += out[i]
	}
	for i := range out {
		out[i] /= sum
	}
	return out
}

// Install descomprime el .zip del cuaderno, comprueba que el modelo carga y evalúa una
// ventana, y recién entonces lo deja activo (el anterior queda en anterior/).
func (m *Manager) Install(ctx context.Context, zipData []byte) (*Spec, error) {
	m.inst.Lock()
	defer m.inst.Unlock()
	zr, err := zip.NewReader(bytes.NewReader(zipData), int64(len(zipData)))
	if err != nil {
		return nil, fmt.Errorf("no es un .zip: %w", err)
	}
	if err := os.MkdirAll(m.Dir, 0o755); err != nil {
		return nil, err
	}
	os.WriteFile(m.script(), runnerPy, 0o644)
	tmp, err := os.MkdirTemp(m.Dir, "nuevo-")
	if err != nil {
		return nil, err
	}
	defer os.RemoveAll(tmp)
	var total int64
	for _, f := range zr.File {
		name := filepath.Base(f.Name) // se aplana: nada sale de la carpeta
		if f.FileInfo().IsDir() || name == "." || strings.HasPrefix(name, ".") {
			continue
		}
		if total += int64(f.UncompressedSize64); total > maxZip {
			return nil, errors.New("el .zip descomprimido pasa de 100 MB")
		}
		if err := extract(f, filepath.Join(tmp, name)); err != nil {
			return nil, err
		}
	}
	spec, err := Load(tmp)
	if err != nil {
		return nil, err
	}
	// Prueba de humo: el evaluador carga el .onnx y responde con una salida por clase.
	pctx, cancel := context.WithCancel(ctx)
	defer cancel()
	p, err := startProc(pctx, m.Python, m.script(), filepath.Join(m.Dir, dirLib), spec.Onnx)
	if err != nil {
		return nil, err
	}
	feat := NewFeatures(spec)
	codes := make([][]uint16, len(spec.Canales))
	for i := range codes {
		codes[i] = make([]uint16, feat.Span())
		for j := range codes[i] {
			codes[i][j] = 2048
		}
	}
	mag, fase := feat.Inputs(codes)
	y, err := p.eval(map[string][]float32{"cwt_mag": mag, "cwt_fase": fase})
	p.close()
	if err != nil {
		return nil, err
	}
	if len(y) != len(spec.Clases) {
		return nil, fmt.Errorf("el modelo da %d salidas y la cabecera declara %d clases", len(y), len(spec.Clases))
	}
	cur, prev := filepath.Join(m.Dir, dirModel), filepath.Join(m.Dir, dirPrev)
	os.RemoveAll(prev)
	if _, err := os.Stat(cur); err == nil {
		if err := os.Rename(cur, prev); err != nil {
			return nil, err
		}
	}
	if err := os.Rename(tmp, cur); err != nil {
		os.Rename(prev, cur)
		return nil, err
	}
	spec, err = Load(cur) // rutas definitivas
	if err != nil {
		return nil, err
	}
	log.Printf("ml: modelo %s instalado", spec.Name)
	m.Reload()
	return spec, nil
}

// Reload hace que Run relea el modelo activo.
func (m *Manager) Reload() {
	select {
	case m.reload <- struct{}{}:
	default:
	}
}

func extract(f *zip.File, dst string) error {
	r, err := f.Open()
	if err != nil {
		return err
	}
	defer r.Close()
	w, err := os.Create(dst)
	if err != nil {
		return err
	}
	if _, err := io.Copy(w, io.LimitReader(r, maxZip)); err != nil {
		w.Close()
		return err
	}
	return w.Close()
}
