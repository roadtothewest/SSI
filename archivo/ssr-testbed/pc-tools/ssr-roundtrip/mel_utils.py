"""
mel_utils — Transformación bidireccional Audio ↔ Mel Spectrogram.

Forward:  audio → STFT → |magnitude| → Mel filterbank → Mel spectrogram
Inverse:  Mel → pseudo-inversa → magnitud lineal → Griffin-Lim → iSTFT → audio

Nota sobre Griffin-Lim:
    El algoritmo converge a una señal con la magnitud de STFT correcta
    pero fase estimada. El SNR en dominio temporal es inherentemente bajo
    (~-3 dB incluso con la implementación de librosa). Esto NO es un bug.
    Lo que importa es la calidad perceptual y la consistencia Mel→Mel.
"""

import numpy as np
import librosa


# ---------------------------------------------------------------------------
# Conversión Hz ↔ Mel
# ---------------------------------------------------------------------------

def hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + f / 700.0)


def mel_to_hz(m):
    return 700.0 * (10.0 ** (m / 2595.0) - 1.0)


# ---------------------------------------------------------------------------
# Filterbank Mel (manual, para MCU futuro)
# ---------------------------------------------------------------------------

def mel_filterbank(sr, n_fft, n_mels=64, f_min=0.0, f_max=None):
    """Construye filterbank triangular Mel.

    Retorna matriz E de shape (n_mels, n_fft//2 + 1).
    """
    if f_max is None:
        f_max = sr / 2.0

    n_freqs = n_fft // 2 + 1
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)

    mel_lo = hz_to_mel(f_min)
    mel_hi = hz_to_mel(f_max)
    mel_points = np.linspace(mel_lo, mel_hi, n_mels + 2)
    hz_points = mel_to_hz(mel_points)

    fbank = np.zeros((n_mels, n_freqs))
    for m in range(1, n_mels + 1):
        left = hz_points[m - 1]
        center = hz_points[m]
        right = hz_points[m + 1]

        for k in range(n_freqs):
            if left <= freqs[k] <= center:
                fbank[m - 1, k] = (freqs[k] - left) / (center - left)
            elif center < freqs[k] <= right:
                fbank[m - 1, k] = (right - freqs[k]) / (right - center)

    return fbank


# ---------------------------------------------------------------------------
# Forward: Audio → Mel
# ---------------------------------------------------------------------------

def audio_to_mel(audio, sr=16000, n_fft=1024, hop_length=256, n_mels=64):
    """Convierte waveform a espectrograma Mel.

    Retorna: mel_spec ndarray (n_mels, n_frames)
    """
    S = np.abs(librosa.stft(audio, n_fft=n_fft, hop_length=hop_length))
    E = mel_filterbank(sr, n_fft, n_mels)
    mel_spec = E @ S
    return mel_spec


# ---------------------------------------------------------------------------
# Inverse: Mel → Audio
# ---------------------------------------------------------------------------

def mel_to_audio(mel_spec, sr=16000, n_fft=1024, hop_length=256, n_iter=60):
    """Convierte espectrograma Mel a waveform via pseudo-inversa + Griffin-Lim.

    Args:
        mel_spec: ndarray (n_mels, n_frames) — spectrograma Mel (amplitude, no dB)
        sr: sample rate
        n_fft: tamaño FFT
        hop_length: salto entre frames STFT
        n_iter: iteraciones de Griffin-Lim

    Retorna: audio ndarray (n_samples,) — waveform reconstruido
    """
    n_freqs = n_fft // 2 + 1
    E = mel_filterbank(sr, n_fft, mel_spec.shape[0])
    E_pinv = np.linalg.pinv(E)  # (n_freqs, n_mels)

    # Pseudo-inversa → magnitud lineal estimada
    linear_mag = E_pinv @ mel_spec  # (n_freqs, n_frames)

    # Clip a no-negativo
    linear_mag = np.maximum(linear_mag, 0.0)

    # Griffin-Lim via librosa (implementación optimizada y probada)
    audio = librosa.griffinlim(
        linear_mag,
        n_iter=n_iter,
        hop_length=hop_length,
        n_fft=n_fft,
        momentum=0.99,
        random_state=42,
    )
    return audio


# ---------------------------------------------------------------------------
# Métricas de calidad (las que realmente importan)
# ---------------------------------------------------------------------------

def spectral_convergence(original, reconstructed, sr=16000, n_fft=1024, hop_length=256):
    """Convergencia espectral: qué tan parecidos son los espectros de magnitud.

    Valor más bajo = mejor (0 = perfecto).
    """
    S_orig = np.abs(librosa.stft(original, n_fft=n_fft, hop_length=hop_length))
    S_recon = np.abs(librosa.stft(reconstructed, n_fft=n_fft, hop_length=hop_length))
    nf = min(S_orig.shape[1], S_recon.shape[1])
    return np.linalg.norm(S_orig[:, :nf] - S_recon[:, :nf]) / np.linalg.norm(S_orig[:, :nf])


def mel_roundtrip_error(audio, sr=16000, n_fft=1024, hop_length=256, n_mels=64, n_iter=60):
    """Error de roundtrip Mel→Mel: audio → mel → audio → mel.

    Retorna el error relativo entre el Mel original y el Mel reconstruido.
    """
    mel_orig = audio_to_mel(audio, sr, n_fft, hop_length, n_mels)
    audio_recon = mel_to_audio(mel_orig, sr, n_fft, hop_length, n_iter)
    mel_recon = audio_to_mel(audio_recon, sr, n_fft, hop_length, n_mels)

    # Normalizar para comparar
    eps = 1e-10
    mel_orig_norm = mel_orig / (mel_orig.max() + eps)
    mel_recon_norm = mel_recon / (mel_recon.max() + eps)

    error = np.mean((mel_orig_norm - mel_recon_norm) ** 2)
    return error


# ---------------------------------------------------------------------------
# Utilidad
# ---------------------------------------------------------------------------

def normalize_audio(audio):
    """Normaliza audio float a [-1, 1]."""
    peak = np.max(np.abs(audio))
    if peak > 0:
        return audio / peak
    return audio
