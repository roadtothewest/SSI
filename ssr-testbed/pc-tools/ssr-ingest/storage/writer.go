package storage

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sync"
	"time"
)

type Writer struct {
	dir     string
	file    *os.File
	mu      sync.Mutex
	started time.Time
	hash    sha256.Sum256
	hashW   *os.File
	meta    SessionMeta
	closed  bool
}

type SessionMeta struct {
	SessionID    string            `json:"session_id"`
	Device       string            `json:"device"`
	Sensors      map[string]Sensor `json:"sensors"`
	DurationS    int               `json:"duration_s"`
	TotalFrames  map[string]int    `json:"total_frames"`
	Notes        string            `json:"notes"`
}

type Sensor struct {
	Model          string `json:"model"`
	OdrHz          int    `json:"odr_hz,omitempty"`
	RangeG         int    `json:"range_g,omitempty"`
	SamplesPerFrame int   `json:"samples_per_frame"`
	SampleRateHz   int    `json:"sample_rate_hz,omitempty"`
	Bits           int    `json:"bits,omitempty"`
}

func NewWriter(baseDir string) *Writer {
	now := time.Now()
	sessionID := now.Format("2006-01-02_150405")
	dir := filepath.Join(baseDir, sessionID)
	if err := os.MkdirAll(dir, 0755); err != nil {
		log.Fatalf("Failed to create session dir: %v", err)
	}

	f, err := os.Create(filepath.Join(dir, "data.ssr"))
	if err != nil {
		log.Fatalf("Failed to create data.ssr: %v", err)
	}

	w := &Writer{
		dir:     dir,
		file:    f,
		started: now,
		meta: SessionMeta{
			SessionID: sessionID,
			Device:    "NUCLEO-H723ZG",
			Sensors: map[string]Sensor{
				"acc": {
					Model:           "IIS3DWB",
					OdrHz:           26700,
					RangeG:          2,
					SamplesPerFrame: 256,
				},
				"audio": {
					Model:           "INMP441",
					SampleRateHz:    16000,
					Bits:            24,
					SamplesPerFrame: 128,
				},
			},
			TotalFrames: map[string]int{
				"acc":   0,
				"audio": 0,
			},
		},
	}

	return w
}

func (w *Writer) WriteFrame(frameData []byte) {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.closed {
		return
	}

	n, err := w.file.Write(frameData)
	if err != nil {
		log.Printf("Write error: %v", err)
		return
	}
	_ = n
}

func (w *Writer) WriteFrame(frame interface{}) {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.closed {
		return
	}
}

func (w *Writer) Close() {
	w.mu.Lock()
	defer w.mu.Unlock()

	if w.closed {
		return
	}
	w.closed = true

	w.file.Close()

	duration := int(time.Since(w.started).Seconds())
	w.meta.DurationS = duration

	metaFile := filepath.Join(w.dir, "metadata.json")
	data, _ := json.MarshalIndent(w.meta, "", "  ")
	os.WriteFile(metaFile, data, 0644)

	info := fmt.Sprintf(`# Session %s

Device:  NUCLEO-H723ZG
Started: %s
Duration: %d seconds

Sensors:
  ACC:  IIS3DWB @ 26700 Hz, ±2g
  AUDIO: INMP441 @ 16000 Hz, 24-bit
`, w.meta.SessionID, w.started.Format(time.RFC3339), duration)

	os.WriteFile(filepath.Join(w.dir, "info.md"), []byte(info), 0644)

	log.Printf("Session saved: %s (%ds, %d acc + %d audio frames)",
		w.dir, duration, w.meta.TotalFrames["acc"], w.meta.TotalFrames["audio"])
}
