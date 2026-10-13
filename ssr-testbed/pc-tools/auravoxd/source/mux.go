package source

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// Source entrega bloques crudos de frame.BlockSize: el DK por SPI, la simulación o una sesión.
type Source interface {
	Run(ctx context.Context, out chan<- []byte)
}

const (
	ModeLive = "live" // la fuente del arranque (-src): el DK por SPI en la Pi
	ModeFile = "file" // una sesión .avx grabada, en bucle
)

var (
	ErrBadSession = errors.New("sesión inválida: se espera <nombre>.avx dentro de la carpeta de datos")
	ErrNoSession  = errors.New("la sesión no existe")
)

// State es lo que la HMI muestra de la fuente activa.
type State struct {
	Mode string `json:"mode"`
	File string `json:"file,omitempty"`
}

// Mux cambia en caliente entre la fuente en vivo y una sesión grabada. La fuente en vivo
// corre siempre (el SPI y la línea DRDY no se cierran ni se reabren); el reproductor arranca
// y se detiene a pedido; al consumidor solo llegan los bloques de la fuente activa.
type Mux struct {
	live Source
	dir  string
	wake chan struct{}

	mu     sync.Mutex
	state  State
	gen    uint64 // cambia en cada cambio de fuente: descarta bloques de la fuente anterior
	file   chan []byte
	cancel context.CancelFunc
}

func NewMux(live Source, dir string) *Mux {
	return &Mux{live: live, dir: dir, wake: make(chan struct{}, 1), state: State{Mode: ModeLive}}
}

func (m *Mux) Run(ctx context.Context, out chan<- []byte) {
	defer func() {
		m.mu.Lock()
		m.stopPlayer()
		m.mu.Unlock()
	}()
	live := make(chan []byte, 16)
	go m.live.Run(ctx, live)
	for {
		m.mu.Lock()
		gen, mode, file := m.gen, m.state.Mode, m.file
		m.mu.Unlock()
		var b []byte
		fromLive := false
		select {
		case <-ctx.Done():
			return
		case <-m.wake:
			continue
		case b = <-live: // en modo sesión se drena y se descarta
			fromLive = true
		case b = <-file: // nil en vivo: nunca listo
		}
		if fromLive != (mode == ModeLive) {
			continue
		}
		m.mu.Lock()
		stale := m.gen != gen
		m.mu.Unlock()
		if stale {
			continue
		}
		select {
		case <-ctx.Done():
			return
		case out <- b:
		}
	}
}

// Check dice si name es una sesión que se puede reproducir: <nombre>.avx dentro de la carpeta.
func (m *Mux) Check(name string) error {
	if name == "" || filepath.Base(name) != name || filepath.Ext(name) != ".avx" {
		return ErrBadSession
	}
	if fi, err := os.Stat(filepath.Join(m.dir, name)); err != nil || !fi.Mode().IsRegular() {
		return fmt.Errorf("%w: %s", ErrNoSession, name)
	}
	return nil
}

// Play reproduce dir/name en bucle. onBlock (opcional) recibe el índice de cada bloque.
func (m *Mux) Play(name string, onBlock func(i uint64)) error {
	if err := m.Check(name); err != nil {
		return err
	}
	path := filepath.Join(m.dir, name)
	m.mu.Lock()
	defer m.mu.Unlock()
	m.stopPlayer()
	ctx, cancel := context.WithCancel(context.Background()) // Run lo detiene al terminar
	ch := make(chan []byte, 16)
	go (&File{Path: path, OnBlock: onBlock}).Run(ctx, ch)
	m.file, m.cancel = ch, cancel
	m.gen++
	m.state = State{Mode: ModeFile, File: name}
	m.poke()
	return nil
}

// Live vuelve a la fuente del arranque.
func (m *Mux) Live() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.stopPlayer()
	m.gen++
	m.state = State{Mode: ModeLive}
	m.poke()
}

func (m *Mux) State() State {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.state
}

func (m *Mux) stopPlayer() {
	if m.cancel != nil {
		m.cancel()
		m.file, m.cancel = nil, nil
	}
}

// poke despierta a Run para que relea el estado.
func (m *Mux) poke() {
	select {
	case m.wake <- struct{}{}:
	default:
	}
}
