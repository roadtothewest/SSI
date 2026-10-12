package analysis

import (
	"math"
	"testing"

	"auravoxd/source"
	"auravoxd/stream"
)

// De punta a punta, sin esperar en tiempo real: bloques simulados (sEMG 60 ms
// antes que la voz) → Store → análisis con la misma cadencia que RunStats.
func TestPipelineDetectsLead(t *testing.T) {
	conv := stream.Conv{VrefADC: 1.8, GDK: 0.545, VMid: 1.65, Gain: 2500}
	st := stream.NewStore(conv)
	a := New(st, 10)
	g := source.NewGen(conv, 60, 1)
	s := &stats{conds: map[string]*condAcc{}, f0: nan, conf: [3]F{nan, nan, nan}}
	var r *Result
	for blk := 1; blk <= 2000; blk++ { // 20 s
		if !st.Ingest(g.Next()) {
			t.Fatal("bloque simulado rechazado")
		}
		if blk%20 == 0 && blk >= 200 { // cada 200 ms, desde los 2 s
			nE, _, nEnv := st.Counts()
			if blk%100 == 0 {
				a.slowStats(s, nE, nEnv)
			}
			a.detectUtterances(s, nEnv)
			r = a.fastStats(s, nE, nEnv)
		}
	}
	if len(s.utter) < 5 {
		t.Fatalf("enunciados detectados: %d, se esperaban ~7", len(s.utter))
	}
	for ch, sm := range r.Sum {
		if math.Abs(float64(sm.Tau)-60) > 15 {
			t.Errorf("CH%d: τ* mediana = %v ms, se esperaba ~+60", ch+1, sm.Tau)
		}
		if !(sm.Lead > 0) {
			t.Errorf("CH%d: adelanto del onset = %v ms, se esperaba > 0", ch+1, sm.Lead)
		}
		t.Logf("CH%d: τ* %v ms (IQR %v), onset %v ms, r %v, n %d, lag(f) %v",
			ch+1, sm.Tau, sm.TauIQR, sm.Lead, sm.R, sm.N, r.XWT[ch].Lag[:4])
	}
	if f0 := float64(r.F0); f0 != 0 && !math.IsNaN(f0) && (f0 < 110 || f0 > 150) {
		t.Errorf("F0 = %.0f Hz, se esperaba ~130", f0)
	}
	if n := len(r.Lanes); n != 3 || r.Lanes[0].RMS <= 0 {
		t.Errorf("RMS por canal no calculado: %+v", r.Lanes)
	}
}
