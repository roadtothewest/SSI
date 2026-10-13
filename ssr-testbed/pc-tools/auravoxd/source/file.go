package source

import (
	"context"
	"io"
	"log"
	"os"
	"time"

	"auravoxd/frame"
)

// File reproduce una sesión grabada (.avx = bloques crudos seguidos) a tiempo
// real, en bucle.
type File struct {
	Path string
	// OnBlock, si no es nil, recibe el índice en el archivo de cada bloque antes de
	// entregarlo (vuelve a 0 en cada vuelta): sirve para reproducir las marcas de condición.
	OnBlock func(i uint64)
}

func (s *File) Run(ctx context.Context, out chan<- []byte) {
	f, err := os.Open(s.Path)
	if err != nil {
		log.Printf("file: %v", err)
		<-ctx.Done()
		return
	}
	defer f.Close()
	t := time.NewTicker(10 * time.Millisecond)
	defer t.Stop()
	var i uint64
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
		b := make([]byte, frame.BlockSize)
		if _, err := io.ReadFull(f, b); err != nil {
			f.Seek(0, io.SeekStart) // fin del archivo: vuelve al inicio
			i = 0
			continue
		}
		if s.OnBlock != nil {
			s.OnBlock(i)
		}
		i++
		select {
		case out <- b:
		default:
		}
	}
}
