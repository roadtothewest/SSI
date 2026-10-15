package ml

import (
	"bufio"
	"context"
	_ "embed"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"os/exec"
	"strings"
	"sync"
	"time"
)

//go:embed runner.py
var runnerPy []byte

// proc es el proceso Python que evalúa el .onnx (runner.py).
type proc struct {
	cmd    *exec.Cmd
	in     io.WriteCloser
	out    *bufio.Reader
	inputs []ioDesc
	Ort    string
	errs   *tail
}

type ioDesc struct {
	Name  string `json:"name"`
	Shape []int  `json:"shape"`
}

func (d ioDesc) size() int {
	n := 1
	for _, v := range d.Shape {
		n *= v
	}
	return n
}

// tail guarda las últimas líneas de stderr para mostrarlas si el proceso falla.
type tail struct {
	mu    sync.Mutex
	lines []string
}

func (t *tail) Write(p []byte) (int, error) {
	t.mu.Lock()
	defer t.mu.Unlock()
	for _, l := range strings.Split(strings.TrimRight(string(p), "\n"), "\n") {
		if l = strings.TrimSpace(l); l != "" {
			t.lines = append(t.lines, l)
		}
	}
	if len(t.lines) > 8 {
		t.lines = t.lines[len(t.lines)-8:]
	}
	return len(p), nil
}

func (t *tail) String() string {
	t.mu.Lock()
	defer t.mu.Unlock()
	return strings.Join(t.lines, " | ")
}

// startProc lanza python3 runner.py model.onnx con libDir en PYTHONPATH y espera su cabecera.
func startProc(ctx context.Context, python, script, libDir, onnx string) (*proc, error) {
	cmd := exec.CommandContext(ctx, python, script, onnx)
	cmd.Env = append(os.Environ(), "PYTHONPATH="+libDir, "OMP_NUM_THREADS=1")
	p := &proc{cmd: cmd, errs: &tail{}}
	cmd.Stderr = p.errs
	var err error
	if p.in, err = cmd.StdinPipe(); err != nil {
		return nil, err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	p.out = bufio.NewReader(stdout)
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("no se pudo lanzar %s: %w", python, err)
	}
	type head struct {
		Inputs []ioDesc `json:"inputs"`
		Ort    string   `json:"ort"`
	}
	got := make(chan error, 1)
	var h head
	go func() {
		line, err := p.out.ReadString('\n')
		if err == nil {
			err = json.Unmarshal([]byte(line), &h)
		}
		got <- err
	}()
	select {
	case err = <-got:
	case <-time.After(90 * time.Second): // importar onnxruntime en la Pi tarda unos segundos
		err = errors.New("el evaluador no respondió en 90 s")
	}
	if err != nil {
		p.close()
		if e := p.errs.String(); e != "" {
			return nil, fmt.Errorf("evaluador: %s", e)
		}
		return nil, fmt.Errorf("evaluador: %w", err)
	}
	p.inputs, p.Ort = h.Inputs, h.Ort
	return p, nil
}

// eval manda las entradas por nombre y devuelve la primera salida.
func (p *proc) eval(in map[string][]float32) ([]float32, error) {
	n := 0
	for _, d := range p.inputs {
		x, ok := in[d.Name]
		if !ok {
			return nil, fmt.Errorf("el modelo pide la entrada %q", d.Name)
		}
		if len(x) != d.size() {
			return nil, fmt.Errorf("%s: %d valores, el modelo espera %v", d.Name, len(x), d.Shape)
		}
		n += len(x)
	}
	buf := make([]byte, 4+4*n)
	binary.LittleEndian.PutUint32(buf, uint32(4*n))
	o := 4
	for _, d := range p.inputs {
		for _, v := range in[d.Name] {
			binary.LittleEndian.PutUint32(buf[o:], math.Float32bits(v))
			o += 4
		}
	}
	if _, err := p.in.Write(buf); err != nil {
		return nil, p.died(err)
	}
	var hdr [4]byte
	if _, err := io.ReadFull(p.out, hdr[:]); err != nil {
		return nil, p.died(err)
	}
	body := make([]byte, binary.LittleEndian.Uint32(hdr[:]))
	if _, err := io.ReadFull(p.out, body); err != nil {
		return nil, p.died(err)
	}
	y := make([]float32, len(body)/4)
	for i := range y {
		y[i] = math.Float32frombits(binary.LittleEndian.Uint32(body[4*i:]))
	}
	return y, nil
}

func (p *proc) died(err error) error {
	if e := p.errs.String(); e != "" {
		return fmt.Errorf("evaluador: %s", e)
	}
	return fmt.Errorf("evaluador: %w", err)
}

func (p *proc) close() {
	if p.in != nil {
		p.in.Close()
	}
	if p.cmd.Process != nil {
		p.cmd.Process.Kill()
	}
	p.cmd.Wait()
}
