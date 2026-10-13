package source

import (
	"bytes"
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"auravoxd/frame"
)

// writeSession writes one block per tag, each block filled with its tag byte.
func writeSession(t *testing.T, dir, name string, tags ...byte) {
	t.Helper()
	var buf bytes.Buffer
	for _, tag := range tags {
		buf.Write(bytes.Repeat([]byte{tag}, frame.BlockSize))
	}
	if err := os.WriteFile(filepath.Join(dir, name), buf.Bytes(), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestFileReportsTheIndexOfEachBlockAndRestartsItOnEveryLoop(t *testing.T) {
	dir := t.TempDir()
	writeSession(t, dir, "s.avx", 'a', 'b', 'c')
	type got struct {
		idx uint64
		tag byte
	}
	idx := make(chan uint64, 32)
	out := make(chan []byte, 32)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	f := &File{Path: filepath.Join(dir, "s.avx"), OnBlock: func(i uint64) { idx <- i }}
	go f.Run(ctx, out)

	want := []got{{0, 'a'}, {1, 'b'}, {2, 'c'}, {0, 'a'}, {1, 'b'}, {2, 'c'}, {0, 'a'}}
	for n, w := range want {
		var g got
		select {
		case g.idx = <-idx:
		case <-time.After(time.Second):
			t.Fatalf("block %d: no index reported", n)
		}
		g.tag = (<-out)[0]
		if g != w {
			t.Fatalf("block %d: index %d tag %q, want index %d tag %q", n, g.idx, g.tag, w.idx, w.tag)
		}
	}
}
