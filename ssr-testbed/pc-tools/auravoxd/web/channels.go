package web

import (
	"encoding/json"
	"errors"
	"log"
	"math"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"

	"auravoxd/stream"
)

// chanFile guarda la configuración de canales en la carpeta de datos. No es .json,
// así no aparece como sesión en la lista de grabaciones.
const chanFile = "canales.cfg"

var defaultNames = [stream.NCh]string{"Submentoniano", "Labio inferior", "Cuello"}

// loadChannels lee canales.cfg o arma los valores por defecto (-gain, todos activos)
// y aplica las ganancias al Store.
func (s *Server) loadChannels() {
	for i := range s.chans {
		s.chans[i] = stream.Channel{Name: defaultNames[i], Gain: s.Conv.Gain, On: true}
	}
	js, err := os.ReadFile(filepath.Join(s.DataDir, chanFile))
	if err == nil {
		var cs [stream.NCh]stream.Channel
		if err = json.Unmarshal(js, &cs); err == nil {
			err = checkChannels(&cs)
		}
		if err == nil {
			s.chans = cs
		}
	}
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		log.Printf("canales: %s ignorado: %v", chanFile, err)
	}
	s.applyChannels()
}

// applyChannels pasa las ganancias al Store y a la conversión que se graba. Requiere chMu
// (o que nadie más use el servidor todavía).
func (s *Server) applyChannels() {
	var g [stream.NCh]float64
	for i, c := range s.chans {
		g[i] = c.Gain
	}
	s.St.SetGains(g)
}

func checkChannels(cs *[stream.NCh]stream.Channel) error {
	for i := range cs {
		c := &cs[i]
		c.Name = strings.Join(strings.Fields(c.Name), " ")
		if c.Name == "" || utf8.RuneCountInString(c.Name) > 32 {
			return errors.New("cada canal necesita un nombre de hasta 32 caracteres")
		}
		if !(c.Gain > 0 && c.Gain <= 1e6) || math.IsInf(c.Gain, 0) {
			return errors.New("la ganancia debe estar entre 0 y 1 000 000")
		}
	}
	return nil
}

func (s *Server) channels() [stream.NCh]stream.Channel {
	s.chMu.Lock()
	defer s.chMu.Unlock()
	return s.chans
}

func (s *Server) postChannels(w http.ResponseWriter, r *http.Request) {
	var cs [stream.NCh]stream.Channel
	if json.NewDecoder(r.Body).Decode(&cs) != nil {
		http.Error(w, "json inválido: se esperan 3 canales", http.StatusBadRequest)
		return
	}
	if err := checkChannels(&cs); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}
	s.chMu.Lock()
	defer s.chMu.Unlock()
	js, _ := json.MarshalIndent(cs, "", "  ")
	if err := os.MkdirAll(s.DataDir, 0o755); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	if err := os.WriteFile(filepath.Join(s.DataDir, chanFile), js, 0o644); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	s.chans = cs
	s.applyChannels()
	log.Printf("canales: %+v", cs)
	writeJSON(w, cs)
}
