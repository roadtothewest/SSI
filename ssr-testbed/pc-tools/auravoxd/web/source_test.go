package web

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"

	"auravoxd/analysis"
	"auravoxd/frame"
	"auravoxd/record"
	"auravoxd/source"
	"auravoxd/stream"
)

// quietLive stands in for the DK: it never delivers a block.
type quietLive struct{}

func (quietLive) Run(ctx context.Context, out chan<- []byte) { <-ctx.Done() }

type rig struct {
	srv *httptest.Server
	s   *Server
}

func newRig(t *testing.T) *rig {
	t.Helper()
	dir := t.TempDir()
	// Session of 4 valid blocks (seq 50..53) recorded in "reposo", switched to "vocal" at block 2.
	avx := make([]byte, 0, 4*frame.BlockSize)
	for seq := uint32(50); seq < 54; seq++ {
		b := make([]byte, frame.BlockSize)
		frame.Encode(&frame.Block{Seq: seq, T0: 10000 * seq}, b)
		avx = append(avx, b...)
	}
	if err := os.WriteFile(filepath.Join(dir, "s.avx"), avx, 0o644); err != nil {
		t.Fatal(err)
	}
	meta := `{"blocks": 4, "marks": [{"block": 0, "cond": "reposo"}, {"block": 2, "cond": "vocal"}]}`
	if err := os.WriteFile(filepath.Join(dir, "s.json"), []byte(meta), 0o644); err != nil {
		t.Fatal(err)
	}
	conv := stream.Conv{VrefADC: 1.8, GDK: 0.5437, VMid: 1.65, Gain: 2500}
	st := stream.NewStore(conv)
	mux := source.NewMux(quietLive{}, dir)
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	out := make(chan []byte, 64)
	go mux.Run(ctx, out)
	go func() {
		for {
			select {
			case <-ctx.Done():
				return
			case b := <-out:
				st.Ingest(b) // the decoder of main.go
			}
		}
	}()
	s := &Server{St: st, An: analysis.New(st, 10), Rec: record.New(dir), Src: mux, Conv: conv,
		Source: "spi", DataDir: dir}
	srv := httptest.NewServer(s.Handler())
	t.Cleanup(srv.Close)
	return &rig{srv, s}
}

func (r *rig) post(t *testing.T, path string, body any) int {
	t.Helper()
	js, _ := json.Marshal(body)
	resp, err := http.Post(r.srv.URL+path, "application/json", bytes.NewReader(js))
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	return resp.StatusCode
}

func (r *rig) state(t *testing.T) source.State {
	t.Helper()
	resp, err := http.Get(r.srv.URL + "/api/source")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var st source.State
	if err := json.NewDecoder(resp.Body).Decode(&st); err != nil {
		t.Fatal(err)
	}
	return st
}

func waitCond(t *testing.T, an *analysis.Analyzer, want string) {
	t.Helper()
	for end := time.Now().Add(time.Second); time.Now().Before(end); time.Sleep(5 * time.Millisecond) {
		if an.Condition() == want {
			return
		}
	}
	t.Fatalf("condition = %q, want %q", an.Condition(), want)
}

func TestPlayingASessionFromTheHMIAndBackToLive(t *testing.T) {
	r := newRig(t)
	if code := r.post(t, "/api/condition", map[string]string{"cond": "habla"}); code != http.StatusOK {
		t.Fatalf("condition: %d", code)
	}
	if code := r.post(t, "/api/record", map[string]bool{"on": true}); code != http.StatusOK {
		t.Fatalf("record: %d", code)
	}
	for seq := uint32(100); seq < 103; seq++ {
		b := make([]byte, frame.BlockSize)
		frame.Encode(&frame.Block{Seq: seq}, b)
		r.s.St.Ingest(b)
	}

	if code := r.post(t, "/api/source", map[string]string{"file": "s.avx"}); code != http.StatusOK {
		t.Fatalf("play: %d", code)
	}
	if st := r.state(t); st != (source.State{Mode: source.ModeFile, File: "s.avx"}) {
		t.Fatalf("state = %+v", st)
	}
	if r.s.Rec.Status().Active {
		t.Fatal("the live recording kept running while a session plays")
	}
	if l := r.s.St.Link(); l.Blocks != 0 {
		t.Fatalf("link still counts %d live blocks after the switch", l.Blocks)
	}
	if code := r.post(t, "/api/record", map[string]bool{"on": true}); code != http.StatusConflict {
		t.Fatalf("record during playback: %d, want 409", code)
	}
	waitCond(t, r.s.An, "vocal") // the session's own mark at block 2

	if code := r.post(t, "/api/source", map[string]string{"file": ""}); code != http.StatusOK {
		t.Fatalf("live: %d", code)
	}
	if st := r.state(t); st != (source.State{Mode: source.ModeLive}) {
		t.Fatalf("state = %+v after going back live", st)
	}
	waitCond(t, r.s.An, "habla") // the condition the operator had before the playback
}

func TestSessionNamesAreChecked(t *testing.T) {
	r := newRig(t)
	for _, c := range []struct {
		file string
		want int
	}{{"../s.avx", http.StatusBadRequest}, {"s.json", http.StatusBadRequest}, {"otra.avx", http.StatusNotFound}} {
		if code := r.post(t, "/api/source", map[string]string{"file": c.file}); code != c.want {
			t.Errorf("play %q: %d, want %d", c.file, code, c.want)
		}
	}
	if st := r.state(t); st != (source.State{Mode: source.ModeLive}) {
		t.Fatalf("state = %+v after rejected sessions", st)
	}
}

func TestALoopingSessionDoesNotLookLikeLostBlocks(t *testing.T) {
	r := newRig(t)
	if code := r.post(t, "/api/source", map[string]string{"file": "s.avx"}); code != http.StatusOK {
		t.Fatalf("play: %d", code)
	}
	// 4 blocks every 10 ms plus the restart tick: 3 full loops in 200 ms.
	for end := time.Now().Add(time.Second); r.s.St.Link().Blocks < 12; time.Sleep(10 * time.Millisecond) {
		if time.Now().After(end) {
			t.Fatalf("only %d blocks played", r.s.St.Link().Blocks)
		}
	}
	if l := r.s.St.Link(); l.Gaps != 0 {
		t.Fatalf("link counts %d gaps over %d blocks of a looping session, want 0", l.Gaps, l.Blocks)
	}
}
