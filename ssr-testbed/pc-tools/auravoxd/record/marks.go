package record

import (
	"encoding/json"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

// LoadMarks lee las marcas de condición de la sesión <nombre>.avx desde su <nombre>.json.
// Una sesión sin .json no tiene marcas: la reproducción deja la condición como está.
func LoadMarks(dir, avx string) ([]Mark, error) {
	js, err := os.ReadFile(filepath.Join(dir, strings.TrimSuffix(avx, ".avx")+".json"))
	if errors.Is(err, fs.ErrNotExist) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var m Meta
	if err := json.Unmarshal(js, &m); err != nil {
		return nil, err
	}
	return m.Marks, nil
}

// CondAt devuelve la condición que empieza en el bloque block, si alguna marca cae ahí.
func CondAt(marks []Mark, block uint64) (string, bool) {
	for _, m := range marks {
		if m.Block == block {
			return m.Cond, true
		}
	}
	return "", false
}
