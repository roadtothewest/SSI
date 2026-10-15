package analysis

import (
	"math"
	"strconv"
)

// Condiciones del protocolo de captura (archivo/docs/refactor-emg-software.md §3.3 y §3.4).
var Conditions = []string{"desconectado", "reposo", "habla", "silenciosa", "vocal"}

// F es un float que en JSON sale como null si es NaN o infinito.
type F float64

func (f F) MarshalJSON() ([]byte, error) {
	v := float64(f)
	if math.IsNaN(v) || math.IsInf(v, 0) {
		return []byte("null"), nil
	}
	return strconv.AppendFloat(nil, v, 'g', 5, 64), nil
}

var nan = F(math.NaN())

// Column es una columna de CWT: un instante, todas las frecuencias, para las
// 4 señales (CH1, CH2, CH3, voz). Data = 4·NF magnitudes y luego 4·NF fases, en uint8.
type Column struct {
	N    int64 // muestra del ADC (2 kHz) en el centro de la ventana
	Data []byte
}

// Utterance es un enunciado detectado en la envolvente de la voz.
type Utterance struct {
	T    F       `json:"t"`   // inicio de la voz [s]
	Dur  F       `json:"dur"` // duración [s]
	Cond string  `json:"cond"`
	Tau  [3]F    `json:"tau"`  // lag de la correlación cruzada [ms]; > 0 = sEMG adelantado
	R    [3]F    `json:"r"`    // r(τ*)
	R0   [3]F    `json:"r0"`   // r(0)
	Lead [3]F    `json:"lead"` // onset de voz − onset de sEMG [ms]; > 0 = sEMG primero
	RMin F       `json:"rMin"` // r que se alcanza por azar en la ventana del enunciado (dsp.ChanceR)
	Sig  [3]bool `json:"sig"`  // r(τ*) sobre el azar y τ* lejos del borde de ±300 ms
}

type Lane struct {
	RMS    F    `json:"rms"` // µV RTI, último segundo
	Hum    F    `json:"hum"` // amplitud de 50 Hz [µV]
	Active bool `json:"act"`
}

// Summary resume los enunciados recientes con τ* significativo (Utterance.Sig).
type Summary struct {
	N       int `json:"n"`    // enunciados significativos
	NAll    int `json:"nAll"` // enunciados analizados
	Tau     F   `json:"tau"`  // mediana de τ* [ms]
	TauIQR  F   `json:"tauIqr"`
	PctLead F   `json:"pctLead"` // % de enunciados con τ* > 0
	Lead    F   `json:"lead"`    // mediana del adelanto del onset [ms]
	LeadIQR F   `json:"leadIqr"`
	R       F   `json:"r"`
	R0      F   `json:"r0"`
}

type CondStat struct {
	Secs int  `json:"secs"`
	RMS  [3]F `json:"rms"`
	Hum  [3]F `json:"hum"`
}

type Result struct {
	T        F                    `json:"t"`
	Hop      int                  `json:"hop"`
	Cond     string               `json:"cond"`
	Lanes    [3]Lane              `json:"lanes"`
	VoiceRMS F                    `json:"vrms"`
	Voiced   bool                 `json:"voiced"`
	XC       [3][]float32         `json:"xc"`      // r(τ), τ = -300..300 ms cada 5 ms
	TauLive  [3]F                 `json:"tauLive"` // solo si es significativo
	RLive    [3]F                 `json:"rLive"`
	RMinLive F                    `json:"rMinLive"` // r por azar en la ventana en vivo
	Utter    []Utterance          `json:"utter"`
	Sum      [3]Summary           `json:"sum"`
	Conds    map[string]*CondStat `json:"conds"`
	SNR      [3]F                 `json:"snr"` // habla vs reposo [dB]
	F0       F                    `json:"f0"`
	Confound [3]F                 `json:"confound"` // pico en F0 sobre la mediana [dB]; null si F0 cae en un armónico de 50 Hz
}
