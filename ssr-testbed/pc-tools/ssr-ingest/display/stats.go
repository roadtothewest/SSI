package display

import (
	"fmt"
	"strings"
	"sync/atomic"
	"time"
)

type Stats struct {
	running   atomic.Bool
	lastFrames atomic.Uint64
	lastDrops  atomic.Uint64
	peakFPS   uint64
	totalFPS  uint64
	samples   int
}

func NewStats() *Stats {
	return &Stats{}
}

func (s *Stats) Start() {
	s.running.Store(true)
	go s.loop()
}

func (s *Stats) Stop() {
	s.running.Store(false)
}

func (s *Stats) Update(frames, drops uint64) {
	s.lastFrames.Store(frames)
	s.lastDrops.Store(drops)
}

func (s *Stats) loop() {
	var prevFrames, prevDrops uint64

	for s.running.Load() {
		time.Sleep(1 * time.Second)

		currFrames := s.lastFrames.Load()
		currDrops := s.lastDrops.Load()

		fps := currFrames - prevFrames
		dps := currDrops - prevDrops

		if fps > s.peakFPS {
			s.peakFPS = fps
		}
		s.totalFPS += fps
		s.samples++

		avgFPS := s.totalFPS / uint64(s.samples)

		var bar string
		if fps > 2000 {
			bar = strings.Repeat("█", 40)
		} else {
			bar = strings.Repeat("█", int(fps)/50)
		}

		fmt.Printf("\033[2K\rFPS: %-5d | AVG: %-5d | DROPS: %-3d | %s",
			fps, avgFPS, dps, bar)

		prevFrames = currFrames
		prevDrops = currDrops
	}
}

func (s *Stats) Report() string {
	return fmt.Sprintf("\nPeak FPS: %d | Avg FPS: %d | Samples: %d",
		s.peakFPS, s.totalFPS/uint64(max(s.samples, 1)), s.samples)
}
