package web

import (
	"io"
	"net/http"
	"strings"

	"auravoxd/ml"
)

func (s *Server) mlStatus() ml.Status {
	if s.ML == nil {
		return ml.Status{State: "apagado"}
	}
	return s.ML.Status()
}

// postModel recibe el .zip que exporta el cuaderno (cuerpo crudo o campo "modelo" de un
// formulario), lo prueba y lo deja activo.
func (s *Server) postModel(w http.ResponseWriter, r *http.Request) {
	if s.ML == nil {
		http.Error(w, "auravoxd corre con -ml=false", http.StatusConflict)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 100<<20)
	var src io.Reader = r.Body
	if strings.HasPrefix(r.Header.Get("Content-Type"), "multipart/form-data") {
		f, _, err := r.FormFile("modelo")
		if err != nil {
			http.Error(w, "falta el campo modelo: "+err.Error(), http.StatusBadRequest)
			return
		}
		defer f.Close()
		src = f
	}
	data, err := io.ReadAll(src)
	if err != nil {
		http.Error(w, "no se pudo leer el archivo: "+err.Error(), http.StatusBadRequest)
		return
	}
	spec, err := s.ML.Install(r.Context(), data)
	if err != nil {
		http.Error(w, err.Error(), http.StatusUnprocessableEntity)
		return
	}
	writeJSON(w, map[string]any{"model": spec.Name, "clases": spec.Clases})
}
