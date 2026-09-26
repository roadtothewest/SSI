"""
audio_io — Grabación de micrófono y E/S de archivos WAV.
"""

import numpy as np
import scipy.io.wavfile as wavfile


def record_audio(duration=5.0, sr=16000, channels=1):
    """Graba audio del micrófono.

    Args:
        duration: duración en segundos
        sr: sample rate (default 16kHz, coincidente con INMP441)
        channels: número de canales (1=mono)

    Retorna:
        audio: ndarray float32, shape (n_samples,) si channels=1
    """
    try:
        import sounddevice as sd
    except ImportError:
        raise ImportError(
            "sounddevice no instalado. Ejecuta: pip install sounddevice"
        )

    print(f"Grabando {duration}s a {sr} Hz ...")
    audio = sd.rec(
        int(duration * sr),
        samplerate=sr,
        channels=channels,
        dtype='float32'
    )
    sd.wait()
    print("Grabación completada.")

    if channels == 1 and audio.ndim > 1:
        audio = audio[:, 0]

    return audio


def play_audio(audio, sr=16000):
    """Reproduce audio por los speakers."""
    try:
        import sounddevice as sd
    except ImportError:
        raise ImportError("sounddevice no instalado.")

    sd.play(audio, sr)
    sd.wait()


def save_wav(path, audio, sr=16000):
    """Guarda audio como WAV int16."""
    audio_int16 = (audio * 32767).clip(-32768, 32767).astype(np.int16)
    wavfile.write(path, sr, audio_int16)


def load_wav(path):
    """Carga WAV y retorna (audio_float32, sample_rate)."""
    sr, data = wavfile.read(path)
    if data.dtype == np.int16:
        audio = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        audio = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.float64:
        audio = data.astype(np.float32)
    else:
        audio = data.astype(np.float32)
    return audio, sr
