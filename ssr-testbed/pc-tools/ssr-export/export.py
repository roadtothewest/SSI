#!/usr/bin/env python3

"""
ssr-export: Convierte archivos .ssr a .npz para Colab.
Aplica CWT (Morlet) a aceleración y mel-spectrograma a audio.
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
TYPE_ACC = 0x01
TYPE_AUDIO = 0x02


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
        acc_frames = [f for f in self.frames if f['type'] == TYPE_ACC]
        audio_frames = [f for f in self.frames if f['type'] == TYPE_AUDIO]
        return acc_frames, audio_frames

    def summary(self):
        acc, audio = self.split_channels()
        if not self.frames:
            return "No frames found"
        ts_min = min(f['timestamp'] for f in self.frames)
        ts_max = max(f['timestamp'] for f in self.frames)
        duration = (ts_max - ts_min) / 1e6
        return (
            f"Frames: {len(self.frames)} "
            f"(ACC={len(acc)}, AUDIO={len(audio)}) | "
            f"Duration: {duration:.2f}s"
        )


def extract_acc_channel(acc_frames):
    samples_x, samples_y, samples_z = [], [], []
    timestamps = []

    for f in acc_frames:
        data = f['data']
        ts = f['timestamp']
        n_samples = f['data_len'] // 6

        for i in range(n_samples):
            offset = i * 6
            x = struct.unpack_from('<h', data, offset)[0]
            y = struct.unpack_from('<h', data, offset+2)[0]
            z = struct.unpack_from('<h', data, offset+4)[0]
            samples_x.append(x)
            samples_y.append(y)
            samples_z.append(z)
            timestamps.append(ts + i * (1_000_000 // 26700))

    return {
        'x': np.array(samples_x, dtype=np.int16),
        'y': np.array(samples_y, dtype=np.int16),
        'z': np.array(samples_z, dtype=np.int16),
        'timestamps_us': np.array(timestamps, dtype=np.uint64),
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


def align_channels(acc_data, audio_data):
    acc_ts = acc_data['timestamps_us']
    audio_ts = audio_data['timestamps_us']

    t_start = max(acc_ts[0], audio_ts[0])
    t_end = min(acc_ts[-1], audio_ts[-1])

    if t_end <= t_start:
        return None, None, 0

    duration_s = (t_end - t_start) / 1e6

    acc_mask = (acc_ts >= t_start) & (acc_ts <= t_end)
    audio_mask = (audio_ts >= t_start) & (audio_ts <= t_end)

    acc_aligned = {
        k: v[acc_mask] if isinstance(v, np.ndarray) else v
        for k, v in acc_data.items()
    }
    audio_aligned = {
        k: v[audio_mask] if isinstance(v, np.ndarray) else v
        for k, v in audio_data.items()
    }

    return acc_aligned, audio_aligned, duration_s


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

    acc_frames, audio_frames = ssr.split_channels()
    if not acc_frames:
        print("No ACC frames found")
        sys.exit(1)
    if not audio_frames:
        print("No AUDIO frames found")
        sys.exit(1)

    print(f"ACC frames: {len(acc_frames)}, AUDIO frames: {len(audio_frames)}")

    acc_data = extract_acc_channel(acc_frames)
    audio_data = extract_audio_channel(audio_frames)

    print(f"ACC samples: {len(acc_data['x'])}, AUDIO samples: {len(audio_data['samples'])}")

    acc_aligned, audio_aligned, duration = align_channels(acc_data, audio_data)
    if acc_aligned is None:
        print("No temporal overlap between channels")
        sys.exit(1)

    print(f"Aligned duration: {duration:.2f}s")
    print(f"Aligned ACC: {len(acc_aligned['x'])} samples")
    print(f"Aligned AUDIO: {len(audio_aligned['samples'])} samples")

    export = {}

    export['acc_x'] = np.array(acc_aligned['x'], dtype=np.int16)
    export['acc_y'] = np.array(acc_aligned['y'], dtype=np.int16)
    export['acc_z'] = np.array(acc_aligned['z'], dtype=np.int16)
    export['acc_timestamps_us'] = np.array(acc_aligned['timestamps_us'], dtype=np.uint64)
    export['audio'] = np.array(audio_aligned['samples'], dtype=np.int32)
    export['audio_timestamps_us'] = np.array(audio_aligned['timestamps_us'], dtype=np.uint64)
    export['sample_rate'] = 16000
    export['acc_odr'] = 26700

    fs_acc = 26700
    fs_audio = 16000

    if args.cwt and HAS_SCIPY:
        print("Computing CWT (Morlet) on ACC-X...")

        acc_norm = acc_aligned['x'].astype(np.float64)
        acc_norm -= acc_norm.mean()
        acc_norm /= acc_norm.std() + 1e-10

        max_samples = 500000
        if len(acc_norm) > max_samples:
            acc_norm = acc_norm[:max_samples]

        cwt_matrix, cwt_freqs = cwt_morlet(
            acc_norm, fs_acc,
            f_min=50, f_max=3000,
            n_scales=args.n_scales
        )

        export['cwt_mag'] = np.abs(cwt_matrix).astype(np.float32)
        export['cwt_frequencies'] = cwt_freqs.astype(np.float32)
        print(f"CWT shape: {export['cwt_mag'].shape}")

        if args.plot and HAS_MPL:
            plt.figure(figsize=(12, 6))
            plt.imshow(
                np.abs(cwt_matrix),
                aspect='auto',
                extent=[0, len(acc_norm)/fs_acc, cwt_freqs[0], cwt_freqs[-1]],
                cmap='viridis'
            )
            plt.yscale('log')
            plt.ylabel('Frequency (Hz)')
            plt.xlabel('Time (s)')
            plt.title('CWT of ACC-X (Morlet)')
            plt.colorbar(label='Magnitude')
            plot_path = input_path.with_suffix('.cwt.png')
            plt.savefig(plot_path, dpi=150, bbox_inches='tight')
            plt.close()
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
