#!/usr/bin/env python3

"""
roundtrip — Valida la transformación bidireccional Audio ↔ Mel Spectrogram.

Flujo:
  1. Graba voz del micrófono (o carga WAV)
  2. Audio → Mel (forward)
  3. Mel → Audio (inverse via Griffin-Lim)
  4. Calcula métricas: spectral convergence, mel roundtrip error, PESQ, STOI
  5. Genera WAVs + gráficos comparativos

Nota sobre SNR:
    El SNR en dominio temporal es inherentemente bajo con Griffin-Lim (~-3 dB).
    Esto NO indica mala calidad — es una propiedad del algoritmo que estima
    la fase. Las métricas que importan son: spectral convergence y mel roundtrip error.
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np

from mel_utils import (
    audio_to_mel,
    mel_to_audio,
    normalize_audio,
    spectral_convergence,
    mel_roundtrip_error,
)
from audio_io import record_audio, save_wav, load_wav


# ---------------------------------------------------------------------------
# Métricas adicionales
# ---------------------------------------------------------------------------

def compute_pesq(original, reconstructed, sr=16000):
    """PESQ (Perceptual Evaluation of Speech Quality). Range: -0.5 to 4.5"""
    try:
        from pesq import pesq
        min_len = min(len(original), len(reconstructed))
        return pesq(sr, original[:min_len], reconstructed[:min_len], 'wb')
    except ImportError:
        return None
    except Exception:
        return None


def compute_stoi(original, reconstructed, sr=16000):
    """STOI (Short-Time Objective Intelligibility). Range: 0 to 1"""
    try:
        from pystoi import stoi
        min_len = min(len(original), len(reconstructed))
        return stoi(original[:min_len], reconstructed[:min_len], sr, extended=False)
    except ImportError:
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Gráficos
# ---------------------------------------------------------------------------

def plot_comparison(original, reconstructed, mel_orig, mel_recon, sr, output_dir):
    """Genera gráficos comparativos lado a lado."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib no instalado, omitiendo gráficos.")
        return

    try:
        import librosa
        import librosa.display
    except ImportError:
        print("librosa no instalado para display, omitiendo gráficos.")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 8))

    # Waveforms
    t_orig = np.arange(len(original)) / sr
    t_recon = np.arange(len(reconstructed)) / sr

    axes[0, 0].plot(t_orig, original, linewidth=0.3, color='#2196F3')
    axes[0, 0].set_title('Original')
    axes[0, 0].set_xlabel('Tiempo (s)')
    axes[0, 0].set_ylabel('Amplitud')
    axes[0, 0].set_ylim(-1, 1)
    axes[0, 0].grid(True, alpha=0.3)

    axes[0, 1].plot(t_recon, reconstructed, linewidth=0.3, color='#F44336')
    axes[0, 1].set_title('Reconstruido (Griffin-Lim)')
    axes[0, 1].set_xlabel('Tiempo (s)')
    axes[0, 1].set_ylabel('Amplitud')
    axes[0, 1].set_ylim(-1, 1)
    axes[0, 1].grid(True, alpha=0.3)

    # Espectrogramas Mel
    im1 = axes[1, 0].imshow(
        mel_orig, aspect='auto', origin='lower',
        extent=[0, len(original) / sr, 0, mel_orig.shape[0]],
        cmap='magma'
    )
    axes[1, 0].set_title('Mel Original')
    axes[1, 0].set_xlabel('Tiempo (s)')
    axes[1, 0].set_ylabel('Mel band')
    fig.colorbar(im1, ax=axes[1, 0], fraction=0.046)

    im2 = axes[1, 1].imshow(
        mel_recon, aspect='auto', origin='lower',
        extent=[0, len(reconstructed) / sr, 0, mel_recon.shape[0]],
        cmap='magma'
    )
    axes[1, 1].set_title('Mel Reconstruido')
    axes[1, 1].set_xlabel('Tiempo (s)')
    axes[1, 1].set_ylabel('Mel band')
    fig.colorbar(im2, ax=axes[1, 1], fraction=0.046)

    plt.tight_layout()
    plot_path = output_dir / 'comparison.png'
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Gráfico: {plot_path}")


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def run_roundtrip(audio, sr, output_dir, n_mels=64, n_fft=1024, hop=256, n_iter=60):
    """Ejecuta el pipeline completo de roundtrip."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    audio = normalize_audio(audio)

    # 1. Guardar original
    save_wav(output_dir / 'original.wav', audio, sr)
    duracion = len(audio) / sr
    print(f"  Original: {len(audio)} samples, {duracion:.2f}s")

    # 2. Forward: Audio → Mel
    mel_orig = audio_to_mel(audio, sr, n_fft, hop, n_mels)
    print(f"  Mel: {mel_orig.shape} (mels={mel_orig.shape[0]}, frames={mel_orig.shape[1]})")

    # 3. Inverse: Mel → Audio
    reconstructed = mel_to_audio(mel_orig, sr, n_fft, hop, n_iter)
    reconstructed = normalize_audio(reconstructed)
    print(f"  Reconstruido: {len(reconstructed)} samples, {len(reconstructed)/sr:.2f}s")

    # 4. Guardar reconstruido
    save_wav(output_dir / 'reconstructed.wav', reconstructed, sr)

    # 5. Forward del reconstruido (para métricas mel→mel)
    mel_recon = audio_to_mel(reconstructed, sr, n_fft, hop, n_mels)

    # 6. Calcular métricas
    sc = spectral_convergence(audio, reconstructed, sr, n_fft, hop)
    mre = mel_roundtrip_error(audio, sr, n_fft, hop, n_mels, n_iter)
    pesq_score = compute_pesq(audio, reconstructed, sr)
    stoi_score = compute_stoi(audio, reconstructed, sr)

    print("\n  --- Métricas de Calidad ---")
    print(f"  Spectral Convergence:  {sc:.4f}  (menor = mejor, 0 = perfecto)")
    print(f"  Mel Roundtrip Error:   {mre:.6f}  (menor = mejor, 0 = perfecto)")
    if pesq_score is not None:
        print(f"  PESQ:                  {pesq_score:.2f}  (-0.5 a 4.5, >3 = bueno)")
    else:
        print("  PESQ:                  (instalar: pip install pesq)")
    if stoi_score is not None:
        print(f"  STOI:                  {stoi_score:.3f}  (0 a 1, >0.9 = excelente)")
    else:
        print("  STOI:                  (instalar: pip install pystoi)")

    # 7. Gráficos
    plot_comparison(audio, reconstructed, mel_orig, mel_recon, sr, output_dir)

    # 8. Guardar métricas
    metrics = {
        'spectral_convergence': float(sc),
        'mel_roundtrip_error': float(mre),
        'duration_s': float(duracion),
        'n_mels': n_mels,
        'n_fft': n_fft,
        'hop_length': hop,
        'n_iter': n_iter,
    }
    if pesq_score is not None:
        metrics['pesq'] = float(pesq_score)
    if stoi_score is not None:
        metrics['stoi'] = float(stoi_score)

    with open(output_dir / 'metrics.json', 'w') as f:
        json.dump(metrics, f, indent=2)

    return metrics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Valida roundtrip Audio → Mel → Audio'
    )
    parser.add_argument(
        '--input', '-i', type=str, default=None,
        help='Archivo WAV de entrada (si no se usa micrófono)'
    )
    parser.add_argument(
        '--output', '-o', type=str, default='dataset/roundtrip',
        help='Directorio de salida (default: dataset/roundtrip)'
    )
    parser.add_argument(
        '--duration', '-d', type=float, default=5.0,
        help='Duración de grabación en segundos (default: 5)'
    )
    parser.add_argument('--sr', type=int, default=16000, help='Sample rate')
    parser.add_argument('--n-mels', type=int, default=64, help='Número de mels')
    parser.add_argument('--n-fft', type=int, default=1024, help='Tamaño FFT')
    parser.add_argument('--hop', type=int, default=256, help='Hop length')
    parser.add_argument('--n-iter', type=int, default=60, help='Iteraciones Griffin-Lim')
    args = parser.parse_args()

    if args.input:
        print(f"Cargando: {args.input}")
        audio, sr = load_wav(args.input)
        if sr != args.sr:
            print(f"Advertencia: WAV tiene sr={sr}, usando sr={args.sr}")
    else:
        audio = record_audio(duration=args.duration, sr=args.sr)
        sr = args.sr

    print("\n=== Roundtrip Audio → Mel → Audio ===\n")
    metrics = run_roundtrip(
        audio, sr, args.output,
        n_mels=args.n_mels, n_fft=args.n_fft,
        hop=args.hop, n_iter=args.n_iter
    )

    print(f"\nListo. Archivos en: {args.output}/")


if __name__ == '__main__':
    main()
