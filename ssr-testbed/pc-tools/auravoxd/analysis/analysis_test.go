package analysis

import (
	"math"
	"math/rand"
	"testing"

	"auravoxd/frame"
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
		t.Logf("CH%d: τ* %v ms (IQR %v), onset %v ms, r %v, n %d",
			ch+1, sm.Tau, sm.TauIQR, sm.Lead, sm.R, sm.N)
	}
	if f0 := float64(r.F0); f0 != 0 && !math.IsNaN(f0) && (f0 < 110 || f0 > 150) {
		t.Errorf("F0 = %.0f Hz, se esperaba ~130", f0)
	}
	if n := len(r.Lanes); n != 3 || r.Lanes[0].RMS <= 0 {
		t.Errorf("RMS por canal no calculado: %+v", r.Lanes)
	}
}

// Un canal sin relación con la voz (CH2 al aire) no debe dar τ* significativos,
// aunque su correlación cruzada siempre tenga algún máximo.
func TestUnrelatedChannelIsNotSignificant(t *testing.T) {
	conv := stream.Conv{VrefADC: 1.8, GDK: 0.545, VMid: 1.65, Gain: 2500}
	st := stream.NewStore(conv)
	a := New(st, 10)
	g := source.NewGen(conv, 60, 2)
	rng := rand.New(rand.NewSource(3))
	s := &stats{conds: map[string]*condAcc{}, f0: nan, conf: [3]F{nan, nan, nan}}
	var blk frame.Block
	raw := make([]byte, frame.BlockSize)
	var r *Result
	for n := 1; n <= 3000; n++ { // 30 s
		if err := frame.Decode(g.Next(), &blk); err != nil {
			t.Fatal(err)
		}
		for i := range blk.Tuples {
			blk.Tuples[i].ADC[1] = conv.Code(10 * rng.NormFloat64())
		}
		frame.Encode(&blk, raw)
		st.Ingest(raw)
		if n%20 == 0 && n >= 200 {
			nE, _, nEnv := st.Counts()
			if n%100 == 0 {
				a.slowStats(s, nE, nEnv)
			}
			a.detectUtterances(s, nEnv)
			r = a.fastStats(s, nE, nEnv)
		}
	}
	if r.Sum[0].N < 5 || r.Sum[2].N < 5 {
		t.Fatalf("canales con señal: %d y %d enunciados significativos, se esperaban ≥ 5", r.Sum[0].N, r.Sum[2].N)
	}
	if sm := r.Sum[1]; sm.NAll < 5 || sm.N > 1 {
		t.Errorf("canal de ruido: %d de %d enunciados significativos, se esperaba ≤ 1", sm.N, sm.NAll)
	}
}
