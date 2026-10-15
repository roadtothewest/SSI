package stream

import (
	"testing"

	"auravoxd/frame"
)

func block(seq uint32) []byte {
	b := make([]byte, frame.BlockSize)
	frame.Encode(&frame.Block{Seq: seq, T0: 10000 * seq}, b)
	return b
}

func TestResetLinkStartsTheCountersOverForTheNewSource(t *testing.T) {
	s := NewStore(Conv{VrefADC: 1.8, GDK: 0.5437, VMid: 1.65, Gain: 2500})
	for _, seq := range []uint32{1000, 1001, 1005} { // 3 gaps
		s.Ingest(block(seq))
	}
	if l := s.Link(); l.Blocks != 3 || l.Gaps != 3 {
		t.Fatalf("before reset: blocks %d gaps %d, want 3 and 3", l.Blocks, l.Gaps)
	}
	s.ResetLink()
	// A recorded session restarts its own seq: the jump back is a new source, not a lost block.
	s.Ingest(block(7))
	if l := s.Link(); l.Blocks != 1 || l.Gaps != 0 || l.CRCErr != 0 || l.Dups != 0 {
		t.Fatalf("after reset: %+v, want 1 block and no gaps, CRC errors or duplicates", l)
	}
}

func TestRawCodesFollowTheSamples(t *testing.T) {
	s := NewStore(Conv{VrefADC: 1.8, GDK: 0.5437, VMid: 1.65, Gain: 2500})
	b := frame.Block{Seq: 1}
	for i := range b.Tuples {
		b.Tuples[i].ADC = [3]uint16{uint16(100 + i), 2000, uint16(4000 - i)}
	}
	raw := make([]byte, frame.BlockSize)
	frame.Encode(&b, raw)
	s.Ingest(raw)
	got := make([]uint16, frame.NTuples)
	if !s.ReadCodes(2, 0, got) || got[0] != 4000 || got[19] != 3981 {
		t.Fatalf("CH3 codes = %v", got)
	}
	if s.ReadCodes(0, 1, got) {
		t.Fatal("read past the last sample")
	}
}
