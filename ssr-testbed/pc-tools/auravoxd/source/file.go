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
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
		b := make([]byte, frame.BlockSize)
		if _, err := io.ReadFull(f, b); err != nil {
			f.Seek(0, io.SeekStart) // fin del archivo: vuelve al inicio
			continue
		}
		select {
		case out <- b:
		default:
		}
	}
}
