package source

import (
	"bytes"
	"context"
	"errors"
	"testing"
	"time"

	"auravoxd/frame"
)

// tagSource stands in for the live SPI source: a block filled with its tag every millisecond.
type tagSource byte

func (s tagSource) Run(ctx context.Context, out chan<- []byte) {
	for {
		b := bytes.Repeat([]byte{byte(s)}, frame.BlockSize)
		select {
		case <-ctx.Done():
			return
		case out <- b:
		}
		time.Sleep(time.Millisecond)
	}
}

func nextTag(t *testing.T, out <-chan []byte) byte {
	t.Helper()
	select {
	case b := <-out:
		return b[0]
	case <-time.After(time.Second):
		t.Fatal("no block in 1 s")
		return 0
	}
}

// expectSource allows one block of the previous source still in flight, then wants n blocks of tag.
func expectSource(t *testing.T, out <-chan []byte, tag byte, n int) {
	t.Helper()
	got := nextTag(t, out)
	if got != tag {
		got = nextTag(t, out)
	}
	for i := 0; ; i++ {
		if got != tag {
			t.Fatalf("block %d after the switch is %q, want %q", i, got, tag)
		}
		if i == n-1 {
			return
		}
		got = nextTag(t, out)
	}
}

func startMux(t *testing.T) (*Mux, <-chan []byte) {
	t.Helper()
	dir := t.TempDir()
	writeSession(t, dir, "s.avx", 'F', 'F', 'F')
	writeSession(t, dir, "s.json", 'J')
	m := NewMux(tagSource('L'), dir)
	out := make(chan []byte) // unbuffered: no forwarded block hides in a buffer across a switch
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	go m.Run(ctx, out)
	return m, out
}

func TestMuxSwitchesBetweenLiveAndARecordedSession(t *testing.T) {
	m, out := startMux(t)
	expectSource(t, out, 'L', 5)

	if err := m.Play("s.avx", nil); err != nil {
		t.Fatal(err)
	}
	if st := m.State(); st != (State{Mode: ModeFile, File: "s.avx"}) {
		t.Fatalf("state = %+v while playing", st)
	}
	expectSource(t, out, 'F', 5) // longer than the file: the session loops

	m.Live()
	if st := m.State(); st != (State{Mode: ModeLive}) {
		t.Fatalf("state = %+v after Live", st)
	}
	expectSource(t, out, 'L', 5)
}

func TestMuxOnlyPlaysSessionsInsideTheDataDir(t *testing.T) {
	m, out := startMux(t)
	for _, c := range []struct {
		name string
		want error
	}{
		{"", ErrBadSession},
		{"../s.avx", ErrBadSession},
		{"sub/s.avx", ErrBadSession},
		{"s.json", ErrBadSession},
		{"missing.avx", ErrNoSession},
	} {
		if err := m.Play(c.name, nil); !errors.Is(err, c.want) {
			t.Errorf("Play(%q) = %v, want %v", c.name, err, c.want)
		}
	}
	if st := m.State(); st != (State{Mode: ModeLive}) {
		t.Fatalf("state = %+v after rejected sessions, want live", st)
	}
	expectSource(t, out, 'L', 3)
}

func TestMuxPassesTheBlockIndexToThePlayHook(t *testing.T) {
	m, out := startMux(t)
	idx := make(chan uint64, 64)
	if err := m.Play("s.avx", func(i uint64) { idx <- i }); err != nil {
		t.Fatal(err)
	}
	expectSource(t, out, 'F', 4)
	for n, want := range []uint64{0, 1, 2, 0} {
		if got := <-idx; got != want {
			t.Fatalf("index %d = %d, want %d", n, got, want)
		}
	}
}
