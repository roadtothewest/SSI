// Package record graba las sesiones: los bloques crudos válidos en <nombre>.avx
// y los metadatos (condiciones, enunciados con su lag) en <nombre>.json.
// Con los bloques crudos se puede recalcular todo después (refactor §4).
package record

import (
	"bufio"
	"context"
	"encoding/json"
	"log"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"sync/atomic"
	"time"

	"auravoxd/analysis"
	"auravoxd/frame"
	"auravoxd/stream"
)

type Mark struct {
	Block uint64 `json:"block"` // índice del bloque en el .avx (10 ms cada uno)
	Cond  string `json:"cond"`
}

type Meta struct {
	Start     time.Time            `json:"start"`
	Stop      time.Time            `json:"stop"`
	BlockSize int                  `json:"blockSize"`
	Conv      stream.Conv          `json:"conv"`
	HopMS     int                  `json:"hopMs"`
	Blocks    uint64               `json:"blocks"`
	Dropped   uint64               `json:"dropped"`
	Marks     []Mark               `json:"marks"`
	Utter     []analysis.Utterance `json:"utterances"`
}

type Status struct {
	Active  bool    `json:"active"`
	Name    string  `json:"name"`
	Secs    float64 `json:"secs"`
	Dropped uint64  `json:"dropped"`
}

type Recorder struct {
	dir     string
	in      chan []byte
	active  atomic.Bool
	dropped atomic.Uint64

	mu   sync.Mutex
	f    *os.File
	w    *bufio.Writer
	name string
	meta Meta
}

func New(dir string) *Recorder {
	return &Recorder{dir: dir, in: make(chan []byte, 512)}
}

// Feed no bloquea: si el disco se atrasa, el bloque se cuenta como descartado.
func (r *Recorder) Feed(raw []byte) {
	if !r.active.Load() {
		return
	}
	select {
	case r.in <- raw:
	default:
		r.dropped.Add(1)
	}
}

func (r *Recorder) Run(ctx context.Context) {
	for {
		select {
		case <-ctx.Done():
			r.Stop()
			return
		case b := <-r.in:
			r.mu.Lock()
			if r.w != nil {
				if _, err := r.w.Write(b); err != nil {
					log.Printf("record: %v", err)
				}
				r.meta.Blocks++
			}
			r.mu.Unlock()
		}
	}
}

func (r *Recorder) Start(conv stream.Conv, hopMS int, cond string) (string, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.f != nil {
		return r.name, nil
	}
	if err := os.MkdirAll(r.dir, 0o755); err != nil {
		return "", err
	}
	now := time.Now()
	name := now.Format("20060102-150405")
	f, err := os.Create(filepath.Join(r.dir, name+".avx"))
	if err != nil {
		return "", err
	}
	r.f, r.w, r.name = f, bufio.NewWriterSize(f, 64<<10), name
	r.meta = Meta{Start: now, BlockSize: frame.BlockSize, Conv: conv, HopMS: hopMS,
		Marks: []Mark{{0, cond}}}
	r.dropped.Store(0)
	r.active.Store(true)
	log.Printf("record: grabando %s", name)
	return name, nil
}

func (r *Recorder) Stop() error {
	r.active.Store(false)
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.f == nil {
		return nil
	}
	r.w.Flush()
	err := r.f.Close()
	r.meta.Stop = time.Now()
	r.meta.Dropped = r.dropped.Load()
	js, _ := json.MarshalIndent(r.meta, "", "  ")
	if e := os.WriteFile(filepath.Join(r.dir, r.name+".json"), js, 0o644); e != nil && err == nil {
		err = e
	}
	log.Printf("record: %s cerrado (%d bloques)", r.name, r.meta.Blocks)
	r.f, r.w = nil, nil
	return err
}

// Mark anota un cambio de condición en la sesión en curso.
func (r *Recorder) Mark(cond string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.f != nil {
		r.meta.Marks = append(r.meta.Marks, Mark{r.meta.Blocks, cond})
	}
}

func (r *Recorder) AddUtterance(u analysis.Utterance) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.f != nil {
		r.meta.Utter = append(r.meta.Utter, u)
	}
}

func (r *Recorder) Status() Status {
	r.mu.Lock()
	defer r.mu.Unlock()
	return Status{
		Active:  r.f != nil,
		Name:    r.name,
		Secs:    float64(r.meta.Blocks) * frame.NTuples / stream.FsEMG,
		Dropped: r.dropped.Load(),
	}
}

type FileInfo struct {
	Name string `json:"name"`
	Size int64  `json:"size"`
}

func (r *Recorder) Files() []FileInfo {
	ents, _ := os.ReadDir(r.dir)
	var out []FileInfo
	for _, e := range ents {
		if info, err := e.Info(); err == nil && !e.IsDir() {
			out = append(out, FileInfo{e.Name(), info.Size()})
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name > out[j].Name })
	return out
}
