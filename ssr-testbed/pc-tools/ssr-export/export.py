#!/usr/bin/env python3

"""
ssr-export: Convierte archivos .ssr a .npz para Colab.
Aplica CWT (Morlet) a los 4 canales sEMG y mel-spectrograma a audio.
Frame EMG (0x03): N muestras x 4 x int16 (CH1..CH4), ver docs/afe-emg/AFE_EMG_Diseno.md 5.1.
"""

import argparse
import struct
import json
import os
import sys
from pathlib import Path

import numpy as np

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

try:
    import scipy.signal as signal
    import scipy.fft as fft
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


HEADER_SIZE = 10
SYNC0 = 0xAA
SYNC1 = 0x55
TYPE_AUDIO = 0x02
TYPE_EMG = 0x03
EMG_CHANNELS = 4


class SSRFile:
    def __init__(self, path):
        self.path = Path(path)
        self.data = self.path.read_bytes()
        self.frames = []
        self._parse()

    def _parse(self):
        pos = 0
        while pos + HEADER_SIZE <= len(self.data):
            if self.data[pos] != SYNC0 or self.data[pos+1] != SYNC1:
                pos += 1
                continue

            frame_type = self.data[pos+2]
            flags = self.data[pos+3]
            timestamp = struct.unpack_from('<I', self.data, pos+4)[0]
            data_len = struct.unpack_from('<H', self.data, pos+8)[0]
            frame_size = HEADER_SIZE + data_len

            if pos + frame_size > len(self.data):
                break

            payload = self.data[pos+HEADER_SIZE:pos+frame_size]

            self.frames.append({
                'type': frame_type,
                'flags': flags,
                'timestamp': timestamp,
                'data': payload,
                'data_len': data_len,
            })
            pos += frame_size

    def split_channels(self):
        emg_frames = [f for f in self.frames if f['type'] == TYPE_EMG]
        audio_frames = [f for f in self.frames if f['type'] == TYPE_AUDIO]
        return emg_frames, audio_frames

    def summary(self):
        emg, audio = self.split_channels()
        if not self.frames:
            return "No frames found"
        ts_min = min(f['timestamp'] for f in self.frames)
        ts_max = max(f['timestamp'] for f in self.frames)
        duration = (ts_max - ts_min) / 1e6
        return (
            f"Frames: {len(self.frames)} "
            f"(EMG={len(emg)}, AUDIO={len(audio)}) | "
            f"Duration: {duration:.2f}s"
        )


def extract_emg_channels(emg_frames, fs):
    """Devuelve {'ch': (N, 4) int16, 'timestamps_us': (N,)} desde frames EMG 0x03."""
    blocks, timestamps = [], []
    for f in emg_frames:
        n = f['data_len'] // (2 * EMG_CHANNELS)
        blocks.append(np.frombuffer(f['data'][:n * 2 * EMG_CHANNELS], dtype='<i2').reshape(n, EMG_CHANNELS))
        timestamps.append(f['timestamp'] + np.arange(n, dtype=np.uint64) * int(1_000_000 // fs))
    return {
        'ch': np.concatenate(blocks).astype(np.int16),
        'timestamps_us': np.concatenate(timestamps).astype(np.uint64),
    }


def extract_audio_channel(audio_frames):
    samples = []
    timestamps = []

    for f in audio_frames:
        data = f['data']
        ts = f['timestamp']
        n_samples = f['data_len'] // 4

        for i in range(n_samples):
            offset = i * 4
            sample = struct.unpack_from('<i', data, offset)[0]
            sample = sample >> 8
            samples.append(sample)
            timestamps.append(ts + i * (1_000_000 // 16000))

    return {
        'samples': np.array(samples, dtype=np.int32),
        'timestamps_us': np.array(timestamps, dtype=np.uint64),
    }


def cwt_morlet(signal_data, fs, f_min=50, f_max=3000, n_scales=64):
    if not HAS_SCIPY:
        raise ImportError("scipy required for CWT")

    scales = np.geomspace(fs / f_max, fs / f_min, n_scales)
    frequencies = fs / scales

    widths = scales
    cwt_matrix = signal.cwt(signal_data, signal.morlet2, widths, w=5)

    return cwt_matrix, frequencies


def mel_spectrogram(audio, fs, n_mels=64, n_fft=1024, hop_length=256):
    if not HAS_SCIPY:
        raise ImportError("scipy required for mel spectrogram")

    freqs = np.fft.rfftfreq(n_fft, 1/fs)
    mel_basis = _mel_filterbank(freqs, n_mels, fs)

    _, _, stft = signal.stft(audio, fs, nperseg=n_fft, noverlap=n_fft - hop_length)
    mag = np.abs(stft)

    mel_spec = mel_basis @ mag

    return mel_spec


def _mel_filterbank(freqs, n_mels, fs):
    low_freq = 0
    high_freq = fs / 2
    mel_low = 2595 * np.log10(1 + low_freq / 700)
    mel_high = 2595 * np.log10(1 + high_freq / 700)
    mel_points = np.linspace(mel_low, mel_high, n_mels + 2)
    hz_points = 700 * (10 ** (mel_points / 2595) - 1)

    fbank = np.zeros((n_mels, len(freqs)))
    for i in range(1, n_mels + 1):
        left = hz_points[i-1]
        center = hz_points[i]
        right = hz_points[i+1]

        idx = np.where((freqs >= left) & (freqs <= right))[0]
        for j in idx:
            if freqs[j] <= center:
                fbank[i-1, j] = (freqs[j] - left) / (center - left)
            else:
                fbank[i-1, j] = (right - freqs[j]) / (right - center)

    return fbank


def align_channels(emg_data, audio_data):
    emg_ts = emg_data['timestamps_us']
    audio_ts = audio_data['timestamps_us']

    t_start = max(emg_ts[0], audio_ts[0])
    t_end = min(emg_ts[-1], audio_ts[-1])

    if t_end <= t_start:
        return None, None, 0

    duration_s = (t_end - t_start) / 1e6

    emg_mask = (emg_ts >= t_start) & (emg_ts <= t_end)
    audio_mask = (audio_ts >= t_start) & (audio_ts <= t_end)

    emg_aligned = {
        k: v[emg_mask] if isinstance(v, np.ndarray) else v
        for k, v in emg_data.items()
    }
    audio_aligned = {
        k: v[audio_mask] if isinstance(v, np.ndarray) else v
        for k, v in audio_data.items()
    }

    return emg_aligned, audio_aligned, duration_s


def main():
    parser = argparse.ArgumentParser(description='Export .ssr to .npz for Colab')
    parser.add_argument('input', help='Input .ssr file or session directory')
    parser.add_argument('--output', '-o', default=None, help='Output .npz file')
    parser.add_argument('--cwt', action='store_true', default=True,
                        help='Compute CWT features (default: True)')
    parser.add_argument('--mel', action='store_true', default=True,
                        help='Compute mel spectrogram (default: True)')
    parser.add_argument('--plot', action='store_true',
                        help='Save diagnostic plots')
    parser.add_argument('--n-scales', type=int, default=64,
                        help='Number of CWT scales')
    parser.add_argument('--fs-emg', type=float, default=2000,
                        help='Tasa de muestreo del ADC EMG por canal [Hz] (default 2000)')
    args = parser.parse_args()

    input_path = Path(args.input)
    if input_path.is_dir():
        ssr_path = input_path / 'data.ssr'
        if not ssr_path.exists():
            print(f"No data.ssr found in {input_path}")
            sys.exit(1)
        input_path = ssr_path

    if not input_path.exists():
        print(f"File not found: {input_path}")
        sys.exit(1)

    ssr = SSRFile(input_path)
    print(f"Loaded: {ssr.path.name} | {ssr.summary()}")

    emg_frames, audio_frames = ssr.split_channels()
    if not emg_frames:
        print("No EMG frames found")
        sys.exit(1)
    if not audio_frames:
        print("No AUDIO frames found")
        sys.exit(1)

    print(f"EMG frames: {len(emg_frames)}, AUDIO frames: {len(audio_frames)}")

    fs_emg = args.fs_emg
    fs_audio = 16000
    emg_data = extract_emg_channels(emg_frames, fs_emg)
    audio_data = extract_audio_channel(audio_frames)

    print(f"EMG samples: {len(emg_data['ch'])} x {EMG_CHANNELS} ch, AUDIO samples: {len(audio_data['samples'])}")

    emg_aligned, audio_aligned, duration = align_channels(emg_data, audio_data)
    if emg_aligned is None:
        print("No temporal overlap between channels")
        sys.exit(1)

    print(f"Aligned duration: {duration:.2f}s")
    print(f"Aligned EMG: {len(emg_aligned['ch'])} samples")
    print(f"Aligned AUDIO: {len(audio_aligned['samples'])} samples")

    export = {}

    export['emg'] = np.array(emg_aligned['ch'], dtype=np.int16)
    export['emg_timestamps_us'] = np.array(emg_aligned['timestamps_us'], dtype=np.uint64)
    export['audio'] = np.array(audio_aligned['samples'], dtype=np.int32)
    export['audio_timestamps_us'] = np.array(audio_aligned['timestamps_us'], dtype=np.uint64)
    export['sample_rate'] = fs_audio
    export['emg_fs'] = fs_emg

    if args.cwt and HAS_SCIPY:
        print("Computing CWT (Morlet) on the 4 EMG channels...")
        max_samples = 500000
        f_max = min(500.0, 0.45 * fs_emg)
        mags = []
        for k in range(EMG_CHANNELS):
            x = emg_aligned['ch'][:max_samples, k].astype(np.float64)
            x -= x.mean()
            x /= x.std() + 1e-10
            cwt_matrix, cwt_freqs = cwt_morlet(x, fs_emg, f_min=20, f_max=f_max, n_scales=args.n_scales)
            mags.append(np.abs(cwt_matrix).astype(np.float32))

        export['cwt_mag'] = np.stack(mags)          # (4, n_scales, N)
        export['cwt_frequencies'] = cwt_freqs.astype(np.float32)
        print(f"CWT shape: {export['cwt_mag'].shape}")

        if args.plot and HAS_MPL:
            fig, axes = plt.subplots(EMG_CHANNELS, 1, figsize=(12, 10), sharex=True)
            for k, ax in enumerate(axes):
                ax.imshow(mags[k], aspect='auto',
                          extent=[0, mags[k].shape[1] / fs_emg, cwt_freqs[-1], cwt_freqs[0]], cmap='viridis')
                ax.set_yscale('log')
                ax.set_ylabel(f'CH{k + 1} [Hz]')
            axes[-1].set_xlabel('Time (s)')
            axes[0].set_title('CWT (Morlet) de los 4 canales sEMG')
            plot_path = input_path.with_suffix('.cwt.png')
            fig.savefig(plot_path, dpi=150, bbox_inches='tight')
            plt.close(fig)
            print(f"CWT plot saved: {plot_path}")

    if args.mel and HAS_SCIPY:
        print("Computing mel spectrogram on audio...")

        audio_norm = audio_aligned['samples'].astype(np.float64)
        audio_norm /= 2**23

        max_samples = 500000
        if len(audio_norm) > max_samples:
            audio_norm = audio_norm[:max_samples]

        mel_spec = mel_spectrogram(audio_norm, fs_audio)
        export['mel_spec'] = mel_spec.astype(np.float32)
        print(f"Mel spectrogram shape: {export['mel_spec'].shape}")

        if args.plot and HAS_MPL:
            plt.figure(figsize=(12, 6))
            plt.imshow(
                mel_spec,
                aspect='auto',
                origin='lower',
                extent=[0, len(audio_norm)/fs_audio, 0, mel_spec.shape[0]],
                cmap='magma'
            )
            plt.ylabel('Mel band')
            plt.xlabel('Time (s)')
            plt.title('Mel spectrogram (AUDIO)')
            plt.colorbar(label='Magnitude')
            plot_path = input_path.with_suffix('.mel.png')
            plt.savefig(plot_path, dpi=150, bbox_inches='tight')
            plt.close()
            print(f"Mel plot saved: {plot_path}")

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_suffix('.npz')

    np.savez_compressed(output_path, **export)
    print(f"Exported: {output_path} ({os.path.getsize(output_path)/1e6:.1f} MB)")


if __name__ == '__main__':
    main()
