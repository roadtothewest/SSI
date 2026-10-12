// Package analysis calcula, en goroutines propias, lo que muestra la HMI:
//   - RunCWT: escalogramas CWT (magnitud y fase) de los 3 sEMG y la voz, una columna por hop;
//   - RunStats: correlación cruzada sEMG→voz, cross-wavelet, enunciados y estadísticas.
package analysis

import (
	"context"
	"math"
	"math/cmplx"
	"slices"
	"sync"
	"sync/atomic"
	"time"

	"auravoxd/dsp"
	"auravoxd/stream"
)

const (
	NF        = 32  // frecuencias de la CWT
	FMin      = 20  // Hz
	FMax      = 500 // Hz
	maxCols   = 4096
	maxLag    = 60 // 60 muestras de envolvente = ±300 ms (Le 2026)
	envMS     = 1000 / stream.FsEnv
	xcWin     = 3 * stream.FsEnv // correlación en vivo: últimos 3 s
	xwtWin    = 5 * stream.FsEnv // cross-wavelet: últimos 5 s
	xwtStep   = 10               // una columna cada 50 ms → 100 columnas
	maxUtter  = 500
	showUtter = 20
)

type Analyzer struct {
	st          *stream.Store
	hop         atomic.Int32 // ms
	OnUtterance func(Utterance)

	bankE, bankV, bankX *dsp.Bank

	colMu sync.RWMutex
	cols  []Column
	colN  int64

	mu    sync.Mutex
	cond  string
	reset atomic.Bool

	res atomic.Pointer[Result]
}

func New(st *stream.Store, hopMS int) *Analyzer {
	a := &Analyzer{
		st:    st,
		bankE: dsp.NewBank(stream.FsEMG, FMin, FMax, NF, 6),
		bankV: dsp.NewBank(stream.FsVoice, FMin, FMax, NF, 6),
		bankX: dsp.NewBank(stream.FsEnv, 1.5, 16, 12, 6),
		cols:  make([]Column, maxCols),
		cond:  "reposo",
	}
	a.SetHop(hopMS)
	a.res.Store(&Result{Hop: hopMS, Cond: a.cond})
	return a
}

func (a *Analyzer) Freqs() []float64 { return a.bankE.Freqs }
func (a *Analyzer) Hop() int         { return int(a.hop.Load()) }
func (a *Analyzer) Result() *Result  { return a.res.Load() }

// SetHop acepta 5, 10 o 20 ms (refactor §5: lo que se barre es el hop, no la ventana).
func (a *Analyzer) SetHop(ms int) bool {
	if ms != 5 && ms != 10 && ms != 20 {
		return false
	}
	a.hop.Store(int32(ms))
	return true
}

func (a *Analyzer) SetCondition(c string) bool {
	if !slices.Contains(Conditions, c) {
		return false
	}
	a.mu.Lock()
	a.cond = c
	a.mu.Unlock()
	return true
}

func (a *Analyzer) Condition() string {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.cond
}

// ResetStats borra enunciados y estadísticas por condición.
func (a *Analyzer) ResetStats() { a.reset.Store(true) }

// ColumnsSince devuelve las columnas de CWT nuevas desde cursor y el cursor nuevo.
func (a *Analyzer) ColumnsSince(cursor int64) ([]Column, int64) {
	a.colMu.RLock()
	defer a.colMu.RUnlock()
	from := max(cursor, a.colN-int64(len(a.cols)))
	out := make([]Column, 0, a.colN-from)
	for i := from; i < a.colN; i++ {
		out = append(out, a.cols[i%int64(len(a.cols))])
	}
	return out, a.colN
}

func (a *Analyzer) ColumnCount() int64 {
	a.colMu.RLock()
	defer a.colMu.RUnlock()
	return a.colN
}

// ---------------------------------------------------------------- CWT

// Escala de colores: dB µV para sEMG y dBFS para la voz.
var magRange = [4][2]float64{{-10, 40}, {-10, 40}, {-10, 40}, {-80, -10}}

func encode(data []byte, s int, w []complex128) {
	lo, hi := magRange[s][0], magRange[s][1]
	for f, c := range w {
		db := 20 * math.Log10(cmplx.Abs(c)+1e-12)
		data[s*NF+f] = byte(math.Max(0, math.Min(255, (db-lo)/(hi-lo)*255)))
		data[4*NF+s*NF+f] = byte((cmplx.Phase(c) + math.Pi) / (2 * math.Pi) * 255)
	}
}

// RunCWT calcula una columna de CWT cada hop. La columna del instante c necesita
// datos hasta c + semiancho del núcleo más largo (≈143 ms a 20 Hz): ese es el
// retraso de la pantalla.
func (a *Analyzer) RunCWT(ctx context.Context) {
	hE, hV := int64(a.bankE.MaxHalf()), int64(a.bankV.MaxHalf())
	bufE := make([]float32, 2*hE+1)
	bufV := make([]float32, 2*hV+1)
	w := make([]complex128, NF)
	next := int64(-1)
	t := time.NewTicker(5 * time.Millisecond)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
		nE, nV, _ := a.st.Counts()
		hop := int64(a.hop.Load()) * stream.FsEMG / 1000
		if next < 0 || next < nE-stream.FsEMG { // inicio, o se quedó atrás más de 1 s
			next = max(nE-hE-1, hE)
		}
		for next+hE < nE && next*8+hV < nV {
			data := make([]byte, 8*NF)
			ok := true
			for ch := 0; ch < stream.NCh && ok; ch++ {
				if ok = a.st.ReadEMG(ch, next-hE, bufE); ok {
					a.bankE.Column(bufE, int(hE), w)
					encode(data, ch, w)
				}
			}
			if ok && a.st.ReadVoice(next*8-hV, bufV) {
				a.bankV.Column(bufV, int(hV), w)
				encode(data, 3, w)
				a.colMu.Lock()
				a.cols[a.colN%int64(len(a.cols))] = Column{N: next, Data: data}
				a.colN++
				a.colMu.Unlock()
			}
			next += hop
		}
	}
}

// ---------------------------------------------------------------- estadísticas

type condAcc struct {
	secs int
	rms2 [3]float64
	hum2 [3]float64
}

type pending struct{ start, end int64 }

// stats es el estado de RunStats; solo lo toca esa goroutine.
type stats struct {
	utter  []Utterance
	conds  map[string]*condAcc
	pos    int64 // próxima muestra de envolvente a revisar
	inU    bool
	runOn  int
	runOff int
	uStart int64
	pend   []pending
	vOn    float64
	vOff   float64
	eOn    [3]float64
	f0     F
	conf   [3]F
	lanes  [3]Lane
	vrms   F
}

func (a *Analyzer) RunStats(ctx context.Context) {
	s := &stats{conds: map[string]*condAcc{}, f0: nan, conf: [3]F{nan, nan, nan}}
	t := time.NewTicker(200 * time.Millisecond)
	defer t.Stop()
	for tick := 0; ; tick++ {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
		}
		if a.reset.Swap(false) {
			s.utter, s.conds = nil, map[string]*condAcc{}
		}
		nE, _, nEnv := a.st.Counts()
		if nEnv < 2*stream.FsEnv {
			r := &Result{Hop: a.Hop(), Cond: a.Condition()}
			a.res.Store(r)
			continue
		}
		if tick%5 == 0 {
			a.slowStats(s, nE, nEnv)
		}
		a.detectUtterances(s, nEnv)
		a.res.Store(a.fastStats(s, nE, nEnv))
	}
}

// slowStats corre cada 1 s: umbrales, RMS, 50 Hz, condición, F0 y confusor.
func (a *Analyzer) slowStats(s *stats, nE, nEnv int64) {
	// Umbrales de onset con la línea base de los últimos 10 s.
	n := min(nEnv, 10*stream.FsEnv)
	env := make([]float32, n)
	if a.st.ReadEnv(stream.NCh, nEnv-n, env) {
		s.vOn, s.vOff = dsp.Thresholds(dsp.Baseline(env))
	}
	for ch := 0; ch < stream.NCh; ch++ {
		if a.st.ReadEnv(ch, nEnv-n, env) {
			s.eOn[ch], _ = dsp.Thresholds(dsp.Baseline(env))
		}
	}
	// RMS y 50 Hz del último segundo, por canal.
	cond := a.Condition()
	acc := s.conds[cond]
	if acc == nil {
		acc = &condAcc{}
		s.conds[cond] = acc
	}
	acc.secs++
	x := make([]float32, stream.FsEMG)
	last := make([]float32, 1)
	for ch := 0; ch < stream.NCh; ch++ {
		if !a.st.ReadEMG(ch, nE-stream.FsEMG, x) {
			continue
		}
		rms, hum := dsp.RMS(x), dsp.ToneAmp(x, stream.FsEMG, 50)
		acc.rms2[ch] += rms * rms
		acc.hum2[ch] += hum * hum
		act := a.st.ReadEnv(ch, nEnv-1, last) && float64(last[0]) > s.eOn[ch]
		s.lanes[ch] = Lane{RMS: F(rms), Hum: F(hum), Active: act}
	}
	// F0 de la voz y control del confusor laríngeo (refactor §3.3):
	// si un canal sEMG tiene un pico en F0, la voz se está acoplando mecánicamente.
	s.f0, s.conf = nan, [3]F{nan, nan, nan}
	v := make([]float32, 2048)
	_, nV, _ := a.st.Counts()
	if !a.st.ReadVoice(nV-int64(len(v)), v) {
		return
	}
	s.vrms = F(dsp.RMS(v))
	vEnv := make([]float32, stream.FsEnv)
	if !a.st.ReadEnv(stream.NCh, nEnv-stream.FsEnv, vEnv) || float64(slices.Max(vEnv)) < s.vOn {
		return
	}
	f0 := dsp.F0(v, stream.FsVoice, 70, 400)
	if f0 == 0 {
		return
	}
	s.f0 = F(f0)
	for ch := 0; ch < stream.NCh; ch++ {
		if !a.st.ReadEMG(ch, nE-stream.FsEMG, x) {
			continue
		}
		var ref []float64
		for f := 20.0; f <= 500; f += 10 {
			hum := math.Abs(math.Mod(f+25, 50) - 25)
			if math.Abs(f-f0) < 15 || hum < 3 {
				continue
			}
			ref = append(ref, dsp.ToneAmp(x, stream.FsEMG, f))
		}
		med, _ := dsp.MedianIQR(ref)
		s.conf[ch] = F(20 * math.Log10(dsp.ToneAmp(x, stream.FsEMG, f0)/med))
	}
}

// detectUtterances recorre la envolvente de la voz con histéresis: inicio si supera
// el umbral 30 ms seguidos, fin si queda bajo el umbral 150 ms seguidos.
func (a *Analyzer) detectUtterances(s *stats, nEnv int64) {
	const holdOn, holdOff, minLen, maxLen = 6, 30, 30, 10 * stream.FsEnv
	if s.vOn == 0 {
		return
	}
	if s.pos < nEnv-10*stream.FsEnv {
		s.pos, s.inU, s.runOn, s.runOff = nEnv-stream.FsEnv, false, 0, 0
	}
	if n := nEnv - s.pos; n > 0 {
		v := make([]float32, n)
		if a.st.ReadEnv(stream.NCh, s.pos, v) {
			for i, x := range v {
				idx := s.pos + int64(i)
				val := float64(x)
				if !s.inU {
					if val > s.vOn {
						if s.runOn++; s.runOn >= holdOn {
							s.inU, s.uStart, s.runOff = true, idx-holdOn+1, 0
						}
					} else {
						s.runOn = 0
					}
					continue
				}
				if val < s.vOff {
					s.runOff++
				} else {
					s.runOff = 0
				}
				if s.runOff >= holdOff || idx-s.uStart > maxLen {
					end := idx - int64(s.runOff) + 1
					if end-s.uStart >= minLen {
						s.pend = append(s.pend, pending{s.uStart, end})
					}
					s.inU, s.runOn = false, 0
				}
			}
		}
		s.pos = nEnv
	}
	// Se analiza cada enunciado cuando ya hay 300 ms después de su fin.
	keep := s.pend[:0]
	for _, p := range s.pend {
		if p.end+maxLag > nEnv {
			keep = append(keep, p)
			continue
		}
		if u, ok := a.analyzeUtterance(s, p); ok {
			s.utter = append(s.utter, u)
			if len(s.utter) > maxUtter {
				s.utter = s.utter[1:]
			}
			if a.OnUtterance != nil {
				a.OnUtterance(u)
			}
		}
	}
	s.pend = keep
}

// analyzeUtterance mide, por canal, el lag de la correlación cruzada en
// [inicio − 500 ms, fin + 300 ms] y el adelanto del onset del sEMG.
func (a *Analyzer) analyzeUtterance(s *stats, p pending) (Utterance, bool) {
	from, to := p.start-100, p.end+maxLag
	y := make([]float32, to-from)
	if !a.st.ReadEnv(stream.NCh, from, y) {
		return Utterance{}, false
	}
	u := Utterance{
		T:    F(float64(p.start) / stream.FsEnv),
		Dur:  F(float64(p.end-p.start) / stream.FsEnv),
		Cond: a.Condition(),
	}
	x := make([]float32, len(y))
	for ch := 0; ch < stream.NCh; ch++ {
		u.Tau[ch], u.R[ch], u.R0[ch], u.Lead[ch] = nan, nan, nan, nan
		if !a.st.ReadEnv(ch, from, x) {
			continue
		}
		r := dsp.XCorr(x, y, maxLag)
		i, rv := dsp.Peak(r)
		u.Tau[ch], u.R[ch], u.R0[ch] = F((i-maxLag)*envMS), F(rv), F(r[maxLag])
		// Onset del sEMG entre −500 ms y +200 ms del onset de la voz (índice 100 de x).
		// Se exige que el sEMG parta bajo el umbral, si no el onset no es medible.
		win := x[:min(len(x), 140)]
		k := 0
		for k < len(win) && float64(win[k]) > s.eOn[ch] {
			k++
		}
		if s.eOn[ch] == 0 || k == len(win) {
			continue
		}
		if o := dsp.Onset(win[k:], s.eOn[ch], 6); o >= 0 {
			u.Lead[ch] = F((100 - (k + o)) * envMS)
		}
	}
	return u, true
}

// fastStats corre cada 200 ms: correlación cruzada en vivo y cross-wavelet.
func (a *Analyzer) fastStats(s *stats, nE, nEnv int64) *Result {
	r := &Result{
		T:        F(float64(nE) / stream.FsEMG),
		Hop:      a.Hop(),
		Cond:     a.Condition(),
		Lanes:    s.lanes,
		VoiceRMS: s.vrms,
		F0:       s.f0,
		Confound: s.conf,
		XWTFreqs: a.bankX.Freqs,
		XWTCols:  xwtWin / xwtStep,
		Conds:    map[string]*CondStat{},
	}
	// Correlación cruzada en vivo, últimos 3 s.
	y := make([]float32, xcWin)
	x := make([]float32, xcWin)
	voiceOK := a.st.ReadEnv(stream.NCh, nEnv-xcWin, y)
	r.Voiced = voiceOK && s.vOn > 0 && float64(slices.Max(y)) > s.vOn
	for ch := 0; ch < stream.NCh; ch++ {
		r.TauLive[ch], r.RLive[ch] = nan, nan
		if voiceOK && a.st.ReadEnv(ch, nEnv-xcWin, x) {
			r.XC[ch] = dsp.XCorr(x, y, maxLag)
			if r.Voiced {
				i, v := dsp.Peak(r.XC[ch])
				r.TauLive[ch], r.RLive[ch] = F((i-maxLag)*envMS), F(v)
			}
		}
	}
	// Resumen de los enunciados (últimos 30).
	recent := s.utter[max(0, len(s.utter)-30):]
	for ch := 0; ch < stream.NCh; ch++ {
		var tau, lead, rr, r0 []float64
		pos := 0
		for _, u := range recent {
			if !math.IsNaN(float64(u.Tau[ch])) {
				tau = append(tau, float64(u.Tau[ch]))
				rr = append(rr, float64(u.R[ch]))
				r0 = append(r0, float64(u.R0[ch]))
				if u.Tau[ch] > 0 {
					pos++
				}
			}
			if !math.IsNaN(float64(u.Lead[ch])) {
				lead = append(lead, float64(u.Lead[ch]))
			}
		}
		sm := Summary{N: len(tau), Tau: nan, TauIQR: nan, PctLead: nan, Lead: nan, LeadIQR: nan, R: nan, R0: nan}
		if len(tau) > 0 {
			m, q := dsp.MedianIQR(tau)
			sm.Tau, sm.TauIQR, sm.PctLead = F(m), F(q), F(100*float64(pos)/float64(len(tau)))
			m, _ = dsp.MedianIQR(rr)
			sm.R = F(m)
			m, _ = dsp.MedianIQR(r0)
			sm.R0 = F(m)
		}
		if len(lead) > 0 {
			m, q := dsp.MedianIQR(lead)
			sm.Lead, sm.LeadIQR = F(m), F(q)
		}
		r.Sum[ch] = sm
	}
	r.Utter = slices.Clone(s.utter[max(0, len(s.utter)-showUtter):])
	// Estadísticas por condición y SNR habla/reposo.
	for name, c := range s.conds {
		cs := &CondStat{Secs: c.secs}
		for ch := 0; ch < 3; ch++ {
			cs.RMS[ch] = F(math.Sqrt(c.rms2[ch] / float64(c.secs)))
			cs.Hum[ch] = F(math.Sqrt(c.hum2[ch] / float64(c.secs)))
		}
		r.Conds[name] = cs
	}
	for ch := 0; ch < 3; ch++ {
		r.SNR[ch] = nan
		if h, ok := r.Conds["habla"]; ok {
			if q, ok := r.Conds["reposo"]; ok && q.RMS[ch] > 0 {
				r.SNR[ch] = F(20 * math.Log10(float64(h.RMS[ch]/q.RMS[ch])))
			}
		}
	}
	a.crossWavelet(r, s, nEnv)
	return r
}

// crossWavelet calcula Wxy = Wx·conj(Wy) entre la envolvente de cada sEMG (x) y la
// de la voz (y) en 1,5–16 Hz, la banda de modulación articulatoria (sílabas).
// Si el sEMG se adelanta Δ, la fase es φ = 2πfΔ, entonces Δ(f) = φ/(2πf).
func (a *Analyzer) crossWavelet(r *Result, s *stats, nEnv int64) {
	b := a.bankX
	nf, cols := len(b.Freqs), xwtWin/xwtStep
	y := make([]float32, xwtWin)
	if !a.st.ReadEnv(stream.NCh, nEnv-xwtWin, y) {
		return
	}
	center(y)
	wy := make([][]complex128, cols)
	for c := range wy {
		wy[c] = make([]complex128, nf)
		b.Column(y, c*xwtStep+xwtStep/2, wy[c])
	}
	x := make([]float32, xwtWin)
	wx := make([]complex128, nf)
	for ch := 0; ch < stream.NCh; ch++ {
		if !a.st.ReadEnv(ch, nEnv-xwtWin, x) {
			continue
		}
		center(x)
		ref := float64(r.Sum[ch].Tau)
		if math.IsNaN(ref) {
			ref = float64(r.TauLive[ch])
		}
		if math.IsNaN(ref) {
			ref = 0
		}
		xw := XWT{Mag: make([]byte, nf*cols), Phase: make([]byte, nf*cols), Coh: make([]F, nf), Lag: make([]F, nf)}
		mag := make([]float64, nf*cols)
		sxy := make([]complex128, nf)
		sxx, syy := make([]float64, nf), make([]float64, nf)
		peak := 0.0
		for c := 0; c < cols; c++ {
			cc := c*xwtStep + xwtStep/2
			b.Column(x, cc, wx)
			for f := 0; f < nf; f++ {
				p := wx[f] * cmplx.Conj(wy[c][f])
				m := cmplx.Abs(p)
				mag[f*cols+c] = m
				peak = math.Max(peak, m)
				xw.Phase[f*cols+c] = byte((cmplx.Phase(p) + math.Pi) / (2 * math.Pi) * 255)
				if h := b.Half(f); cc >= h && cc+h < xwtWin { // fuera del cono de influencia
					sxy[f] += p
					sxx[f] += real(wx[f] * cmplx.Conj(wx[f]))
					syy[f] += real(wy[c][f] * cmplx.Conj(wy[c][f]))
				}
			}
		}
		for i, m := range mag {
			if peak > 0 {
				xw.Mag[i] = byte(255 * math.Sqrt(m/peak))
			}
		}
		for f, fr := range b.Freqs {
			xw.Coh[f], xw.Lag[f] = nan, nan
			if sxx[f] > 0 && syy[f] > 0 {
				am := cmplx.Abs(sxy[f])
				xw.Coh[f] = F(am * am / (sxx[f] * syy[f]))
				cyc := cmplx.Phase(sxy[f]) / (2 * math.Pi)
				k := math.Round(ref/1000*fr - cyc) // desenrollar cerca de τ*
				xw.Lag[f] = F((cyc + k) / fr * 1000)
			}
		}
		r.XWT[ch] = xw
	}
}

func center(x []float32) {
	var m float64
	for _, v := range x {
		m += float64(v)
	}
	m /= float64(len(x))
	for i := range x {
		x[i] -= float32(m)
	}
}
