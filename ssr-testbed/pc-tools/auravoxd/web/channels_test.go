package web

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"auravoxd/frame"
	"auravoxd/stream"
)

func TestChannelSetupIsSavedAndApplied(t *testing.T) {
	r := newRig(t)
	cs := [3]stream.Channel{{Name: "Masetero", Gain: 200, On: true}, {Name: "Libre", Gain: 2500, On: false}, {Name: " Omohioideo ", Gain: 1, On: true}}
	if code := r.post(t, "/api/channels", cs); code != http.StatusOK {
		t.Fatalf("channels: %d", code)
	}
	for _, bad := range [][3]stream.Channel{
		{{Name: "", Gain: 1, On: true}, {Name: "b", Gain: 1, On: true}, {Name: "c", Gain: 1, On: true}},
		{{Name: "a", Gain: 0, On: true}, {Name: "b", Gain: 1, On: true}, {Name: "c", Gain: 1, On: true}},
	} {
		if code := r.post(t, "/api/channels", bad); code != http.StatusBadRequest {
			t.Errorf("channels %+v: %d, want 400", bad, code)
		}
	}
	if !exists(r.s.DataDir, chanFile) {
		t.Fatal("the setup was not saved")
	}
	if ss := r.sessions(t); len(ss) != 1 {
		t.Fatalf("the setup file shows up as a session: %+v", ss)
	}

	// The gain applies to the next block: a code of 1 V above VMid at the pin reads
	// 1e6/200 µV on CH1 and 1e6 µV on CH3.
	conv := r.s.Conv
	b := frame.Block{Seq: 900}
	for i := range b.Tuples {
		code := uint16((conv.VMid + 1) * conv.GDK / conv.VrefADC * 4095)
		b.Tuples[i].ADC = [3]uint16{code, code, code}
	}
	raw := make([]byte, frame.BlockSize)
	frame.Encode(&b, raw)
	r.s.St.Ingest(raw)
	nE, _, _ := r.s.St.Counts()
	x := make([]float32, 1)
	for ch, want := range []float32{5000, 1e6} {
		r.s.St.ReadEMG(2*ch, nE-1, x)
		if d := x[0]/want - 1; d > 0.01 || d < -0.01 {
			t.Errorf("CH%d = %.0f µV, want ≈ %.0f", 2*ch+1, x[0], want)
		}
	}

	// A new server on the same folder starts with the saved setup.
	s2 := &Server{St: stream.NewStore(conv), An: r.s.An, Rec: r.s.Rec, Src: r.s.Src, Conv: conv, DataDir: r.s.DataDir}
	srv := httptest.NewServer(s2.Handler())
	defer srv.Close()
	resp, err := http.Get(srv.URL + "/api/channels")
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	var got [3]stream.Channel
	json.NewDecoder(resp.Body).Decode(&got)
	cs[2].Name = "Omohioideo"
	if got != cs {
		t.Fatalf("after restart: %+v, want %+v", got, cs)
	}
}
