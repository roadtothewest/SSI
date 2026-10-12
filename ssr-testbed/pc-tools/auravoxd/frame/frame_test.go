package frame

import "testing"

func TestRoundTrip(t *testing.T) {
	if BlockSize != 538 {
		t.Fatalf("BlockSize = %d, se esperaba 538", BlockSize)
	}
	var in, out Block
	in.Seq, in.T0, in.Flags = 7, 123456, FlagSAIOverrun
	for i := range in.Tuples {
		in.Tuples[i].TS = in.T0 + uint32(500*i)
		in.Tuples[i].ADC = [3]uint16{uint16(i), 2048, 4095}
		for k := range in.Tuples[i].Voice {
			in.Tuples[i].Voice[k] = int16(-1000 * k)
		}
	}
	b := make([]byte, BlockSize)
	Encode(&in, b)
	if err := Decode(b, &out); err != nil {
		t.Fatal(err)
	}
	if in != out {
		t.Fatal("el bloque decodificado no coincide")
	}
	b[100] ^= 1
	if err := Decode(b, &out); err != ErrCRC {
		t.Fatalf("CRC malo: err = %v", err)
	}
}

func TestCRC16(t *testing.T) {
	// Valor de verificación estándar de CRC-16/CCITT-FALSE.
	if got := CRC16([]byte("123456789")); got != 0x29B1 {
		t.Fatalf("CRC16 = %04X", got)
	}
}
