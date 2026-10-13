// Package web sirve la HMI (archivos embebidos, sin internet) y un stream SSE
// por cliente con las formas de onda, las columnas de CWT y los resultados.
package web

import (
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"sync"
	"time"

	"auravoxd/analysis"
	"auravoxd/record"
	"auravoxd/source"
	"auravoxd/stream"
)

//go:embed static
var static embed.FS

const (
	bucketEMG = 4             // 2 kHz → 500 pares min/max por segundo
	bucketV   = bucketEMG * 8 // la voz con los mismos baldes de tiempo
	showSecs  = 5
)

type Server struct {
	St      *stream.Store
	An      *analysis.Analyzer
	Rec     *record.Recorder
	Src     *source.Mux // en vivo ↔ sesión grabada
	Conv    stream.Conv
	Source  string // fuente en vivo del arranque (-src)
	DataDir string

	srcMu    sync.Mutex
	liveCond string // condición en vivo, para restaurarla al volver de una sesión
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	sub, _ := fs.Sub(static, "static")
	mux.Handle("GET /", http.FileServerFS(sub))
	mux.Handle("GET /files/", http.StripPrefix("/files/", http.FileServer(http.Dir(s.DataDir))))
	mux.HandleFunc("GET /api/stream", s.stream)
	mux.HandleFunc("GET /api/files", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, s.Rec.Files())
	})
	mux.HandleFunc("POST /api/condition", func(w http.ResponseWriter, r *http.Request) {
		var req struct{ Cond string }
		if json.NewDecoder(r.Body).Decode(&req) != nil || !s.An.SetCondition(req.Cond) {
			http.Error(w, "condición inválida", http.StatusBadRequest)
			return
		}
		s.Rec.Mark(req.Cond)
		writeJSON(w, req)
	})
	mux.HandleFunc("POST /api/hop", func(w http.ResponseWriter, r *http.Request) {
		var req struct{ MS int }
		if json.NewDecoder(r.Body).Decode(&req) != nil || !s.An.SetHop(req.MS) {
			http.Error(w, "hop válido: 5, 10 o 20 ms", http.StatusBadRequest)
			return
		}
		writeJSON(w, req)
	})
	mux.HandleFunc("POST /api/record", func(w http.ResponseWriter, r *http.Request) {
		var req struct{ On bool }
		if json.NewDecoder(r.Body).Decode(&req) != nil {
			http.Error(w, "json inválido", http.StatusBadRequest)
			return
		}
		if req.On && s.Src.State().Mode == source.ModeFile {
			http.Error(w, "no se graba mientras se reproduce una sesión", http.StatusConflict)
			return
		}
		var err error
		if req.On {
			_, err = s.Rec.Start(s.Conv, s.An.Hop(), s.An.Condition())
		} else {
			err = s.Rec.Stop()
		}
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		writeJSON(w, s.Rec.Status())
	})
	mux.HandleFunc("POST /api/reset", func(w http.ResponseWriter, r *http.Request) {
		s.An.ResetStats()
		writeJSON(w, true)
	})
	mux.HandleFunc("GET /api/source", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, s.Src.State())
	})
	mux.HandleFunc("POST /api/source", func(w http.ResponseWriter, r *http.Request) {
		var req struct{ File string } // "" = volver a en vivo
		if json.NewDecoder(r.Body).Decode(&req) != nil {
			http.Error(w, "json inválido", http.StatusBadRequest)
			return
		}
		switch err := s.setSource(req.File); {
		case errors.Is(err, source.ErrBadSession):
			http.Error(w, err.Error(), http.StatusBadRequest)
		case errors.Is(err, source.ErrNoSession):
			http.Error(w, err.Error(), http.StatusNotFound)
		case err != nil:
			http.Error(w, err.Error(), http.StatusInternalServerError)
		default:
			writeJSON(w, s.Src.State())
		}
	})
	return mux
}

// setSource cambia a la sesión file ("" = en vivo). Al reproducir no se graba, las marcas
// de la sesión fijan la condición en su bloque, y al volver se restaura la condición en vivo.
// Cada cambio reinicia los contadores del enlace y las estadísticas: no se mezclan fuentes.
func (s *Server) setSource(file string) error {
	s.srcMu.Lock()
	defer s.srcMu.Unlock()
	fromLive := s.Src.State().Mode == source.ModeLive
	if file == "" {
		if fromLive {
			return nil
		}
		s.Src.Live()
		s.An.SetCondition(s.liveCond)
	} else {
		if err := s.Src.Check(file); err != nil {
			return err
		}
		marks, err := record.LoadMarks(s.DataDir, file)
		if err != nil {
			log.Printf("source: %s sin marcas de condición: %v", file, err)
		}
		if fromLive {
			s.liveCond = s.An.Condition()
			if err := s.Rec.Stop(); err != nil {
				log.Printf("source: cerrar la grabación: %v", err)
			}
		}
		err = s.Src.Play(file, func(i uint64) {
			if i == 0 {
				s.St.ResetSeq() // cada vuelta del bucle
			}
			if c, ok := record.CondAt(marks, i); ok {
				s.An.SetCondition(c)
			}
		})
		if err != nil {
			return err
		}
	}
	s.St.ResetLink()
	s.An.ResetStats()
	return nil
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}

type initMsg struct {
	FsEMG    int         `json:"fsEmg"`
	Bucket   int         `json:"bucket"`
	ShowSecs int         `json:"showSecs"`
	Freqs    []float64   `json:"freqs"`
	NF       int         `json:"nf"`
	MagRange [2][2]int   `json:"magRange"`
	Conds    []string    `json:"conds"`
	Source   string      `json:"source"`
	Conv     stream.Conv `json:"conv"`
	MaxLagMS int         `json:"maxLagMs"`
}

type msg struct {
	E    [3][]float32     `json:"e"` // pares min/max por balde, por canal [µV]
	V    []float32        `json:"v"` // pares min/max de la voz
	C    [][]byte         `json:"c"` // columnas CWT nuevas
	R    *analysis.Result `json:"r,omitempty"`
	Link *stream.Link     `json:"link,omitempty"`
	Rec  *record.Status   `json:"rec,omitempty"`
	Src  *source.State    `json:"src,omitempty"`
}

func minmax(x []float32, n int) []float32 {
	out := make([]float32, 0, 2*len(x)/n)
	for i := 0; i+n <= len(x); i += n {
		lo, hi := x[i], x[i]
		for _, v := range x[i : i+n] {
			lo, hi = min(lo, v), max(hi, v)
		}
		out = append(out, lo, hi)
	}
	return out
}

// stream manda un evento cada 40 ms con lo nuevo desde el último envío, y los
// resultados del análisis cada 200 ms.
func (s *Server) stream(w http.ResponseWriter, r *http.Request) {
	fl, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "sin streaming", http.StatusInternalServerError)
		return
	}
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	send := func(v any) bool {
		js, err := json.Marshal(v)
		if err != nil {
			return false
		}
		_, err = fmt.Fprintf(w, "data: %s\n\n", js)
		fl.Flush()
		return err == nil
	}
	if !send(initMsg{
		FsEMG: stream.FsEMG, Bucket: bucketEMG, ShowSecs: showSecs,
		Freqs: s.An.Freqs(), NF: analysis.NF,
		MagRange: [2][2]int{{-10, 40}, {-80, -10}},
		Conds:    analysis.Conditions, Source: s.Source, Conv: s.Conv, MaxLagMS: 300,
	}) {
		return
	}

	nE, _, _ := s.St.Counts()
	cur := max(0, (nE-showSecs*stream.FsEMG)/bucketEMG*bucketEMG)
	colCur := max(0, s.An.ColumnCount()-int64(showSecs*1000/s.An.Hop()))
	t := time.NewTicker(40 * time.Millisecond)
	defer t.Stop()
	for i := 0; ; i++ {
		select {
		case <-r.Context().Done():
			return
		case <-t.C:
		}
		var m msg
		nE, _, _ = s.St.Counts()
		if nE < cur || nE-cur > 10*stream.FsEMG { // se reinició o se atrasó
			cur = max(0, (nE-showSecs*stream.FsEMG)/bucketEMG*bucketEMG)
		}
		if nb := (nE - cur) / bucketEMG; nb > 0 {
			buf := make([]float32, nb*bucketEMG)
			vbuf := make([]float32, nb*bucketV)
			ok := s.St.ReadVoice(cur*8, vbuf)
			for ch := 0; ch < stream.NCh && ok; ch++ {
				if ok = s.St.ReadEMG(ch, cur, buf); ok {
					m.E[ch] = minmax(buf, bucketEMG)
				}
			}
			if ok {
				m.V = minmax(vbuf, bucketV)
				cur += nb * bucketEMG
			} else {
				m.E = [3][]float32{}
				cur = nE / bucketEMG * bucketEMG
			}
		}
		var cols []analysis.Column
		cols, colCur = s.An.ColumnsSince(colCur)
		for _, c := range cols {
			m.C = append(m.C, c.Data)
		}
		if i%5 == 0 {
			l, st, src := s.St.Link(), s.Rec.Status(), s.Src.State()
			m.R, m.Link, m.Rec, m.Src = s.An.Result(), &l, &st, &src
		}
		if !send(m) {
			return
		}
	}
}
