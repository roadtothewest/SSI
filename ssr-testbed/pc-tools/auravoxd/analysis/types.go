package analysis

import (
	"math"
	"strconv"
)

// Condiciones del protocolo de captura (refactor-emg-software.md §3.3 y §3.4).
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
	T    F      `json:"t"`   // inicio de la voz [s]
	Dur  F      `json:"dur"` // duración [s]
	Cond string `json:"cond"`
	Tau  [3]F   `json:"tau"`  // lag de la correlación cruzada [ms]; > 0 = sEMG adelantado
	R    [3]F   `json:"r"`    // r(τ*)
	R0   [3]F   `json:"r0"`   // r(0)
	Lead [3]F   `json:"lead"` // onset de voz − onset de sEMG [ms]; > 0 = sEMG primero
}

type Lane struct {
	RMS    F    `json:"rms"` // µV RTI, último segundo
	Hum    F    `json:"hum"` // amplitud de 50 Hz [µV]
	Active bool `json:"act"`
}

// XWT es la cross-wavelet sEMG × voz sobre las envolventes (últimos 5 s).
type XWT struct {
	Mag   []byte `json:"mag"`   // |Wxy| normalizado, [freq][col]
	Phase []byte `json:"phase"` // arg(Wxy), 0..255 = -π..π
	Coh   []F    `json:"coh"`   // coherencia por frecuencia (0..1)
	Lag   []F    `json:"lag"`   // lag por frecuencia = φ/(2πf) [ms], desenrollado cerca de τ*
}

type Summary struct {
	N       int `json:"n"`
	Tau     F   `json:"tau"` // mediana de τ* [ms]
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
	XC       [3][]float32         `json:"xc"` // r(τ), τ = -300..300 ms cada 5 ms
	TauLive  [3]F                 `json:"tauLive"`
	RLive    [3]F                 `json:"rLive"`
	XWTFreqs []float64            `json:"xwtFreqs"`
	XWTCols  int                  `json:"xwtCols"`
	XWT      [3]XWT               `json:"xwt"`
	Utter    []Utterance          `json:"utter"`
	Sum      [3]Summary           `json:"sum"`
	Conds    map[string]*CondStat `json:"conds"`
	SNR      [3]F                 `json:"snr"` // habla vs reposo [dB]
	F0       F                    `json:"f0"`
	Confound [3]F                 `json:"confound"` // pico en F0 sobre la mediana [dB]
}
