"""Output processing: loudness, fades, padding, resampling, channels and encoding."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
import torchaudio.functional as AF

FORMATS = {
    # format: (soundfile format, extension, subtypes by bit depth)
    "wav": ("WAV", ".wav", {"16": "PCM_16", "24": "PCM_24", "32f": "FLOAT"}),
    "flac": ("FLAC", ".flac", {"16": "PCM_16", "24": "PCM_24"}),
    "ogg": ("OGG", ".ogg", {"vorbis": "VORBIS"}),
    "mp3": ("MP3", ".mp3", {"mp3": "MPEG_LAYER_III"}),
}


_SFC_SET_COMPRESSION_LEVEL = 0x1301


def _set_compression_level(f: sf.SoundFile, level: float) -> None:
    """soundfile 0.12 has no compression_level argument, so call libsndfile directly.
    level: 0.0 = best quality / largest file, 1.0 = smallest file."""
    try:
        value = sf._ffi.new("double*", min(max(level, 0.0), 1.0))
        sf._snd.sf_command(f._file, _SFC_SET_COMPRESSION_LEVEL, value, sf._ffi.sizeof("double"))
    except Exception:
        pass


def _db_to_gain(db: float) -> float:
    return 10.0 ** (db / 20.0)


def time_stretch(x: np.ndarray, rate: float, sr: int) -> np.ndarray:
    """WSOLA tempo change for speech. rate < 1 is slower, > 1 faster; pitch is unchanged.

    Overlap-adds 40 ms Hann frames at a fixed output hop. Each input frame is taken near
    its nominal position, shifted by up to ±10 ms to best match the natural continuation
    of the previous frame, which avoids the phasiness of a plain phase vocoder.
    """
    x = np.asarray(x, dtype=np.float32)
    frame = int(0.040 * sr) & ~1
    hop_out = frame // 2
    hop_in = hop_out * rate
    tol = int(0.010 * sr)
    if len(x) < frame * 2:
        return x
    win = np.hanning(frame).astype(np.float32)
    n_out = int(len(x) / rate) + frame
    y = np.zeros(n_out, dtype=np.float32)
    wsum = np.zeros(n_out, dtype=np.float32)
    dec = 4                                         # search on a decimated signal for speed
    xd = x[::dec]
    prev = 0
    k = 0
    while True:
        nominal = int(round(k * hop_in))
        if k == 0:
            start = 0
        else:
            target = prev + hop_out                 # where the previous frame naturally continues
            lo, hi = max(0, nominal - tol), min(len(x) - frame, nominal + tol)
            if hi <= lo or target + frame > len(x):
                start = min(max(nominal, 0), len(x) - frame)
            else:
                tmpl = xd[target // dec:(target + frame) // dec]
                region = xd[lo // dec:(hi + frame) // dec]
                if len(region) >= len(tmpl) > 0:
                    corr = np.correlate(region, tmpl, mode="valid")
                    start = lo + int(np.argmax(corr)) * dec
                else:
                    start = nominal
        out = k * hop_out
        if start + frame > len(x) or out + frame > n_out:
            break
        y[out:out + frame] += x[start:start + frame] * win
        wsum[out:out + frame] += win
        prev = start
        k += 1
    end = k * hop_out + hop_out
    y, wsum = y[:end], wsum[:end]
    return y / np.maximum(wsum, 1e-3)


def process(wave: torch.Tensor, sr: int, cfg: dict) -> tuple[np.ndarray, int]:
    """wave: (1, samples) float tensor at the model rate. Returns (samples, channels) float32."""
    x = wave.detach().float().cpu()
    if x.ndim == 1:
        x = x.unsqueeze(0)

    # Resample first so loudness is measured on the final signal.
    target_sr = int(cfg.get("sample_rate") or sr)
    if target_sr != sr:
        x = AF.resample(x, sr, target_sr, lowpass_filter_width=64, rolloff=0.9475,
                        resampling_method="sinc_interp_kaiser", beta=14.769656459379492)
        sr = target_sr

    # Speaking speed: change the tempo, keep the pitch.
    speed = float(cfg.get("speed") or 1.0)
    if abs(speed - 1.0) > 1e-3:
        x = torch.from_numpy(time_stretch(x[0].numpy(), speed, sr)).unsqueeze(0)

    # Optional gentle high-pass to remove rumble/DC.
    hp = float(cfg.get("highpass_hz") or 0)
    if hp > 0:
        x = AF.highpass_biquad(x, sr, hp)

    # Loudness / peak normalization.
    mode = cfg.get("normalize", "loudness")
    if mode == "loudness" and x.shape[-1] > sr * 0.5:
        try:
            current = float(AF.loudness(x, sr))
            if math.isfinite(current):
                x = x * _db_to_gain(float(cfg.get("target_lufs", -18.0)) - current)
        except Exception:
            pass
    elif mode == "peak":
        peak = float(x.abs().max())
        if peak > 0:
            x = x * (_db_to_gain(float(cfg.get("peak_db", -1.0))) / peak)

    # True-peak-ish safety limiter: never exceed the ceiling.
    ceiling = _db_to_gain(float(cfg.get("ceiling_db", -1.0)))
    peak = float(x.abs().max())
    if peak > ceiling:
        x = x * (ceiling / peak)

    # Fades.
    for key, at_start in (("fade_in_ms", True), ("fade_out_ms", False)):
        n = int(sr * float(cfg.get(key) or 0) / 1000)
        n = min(n, x.shape[-1] // 2)
        if n > 1:
            ramp = torch.linspace(0, 1, n) if at_start else torch.linspace(1, 0, n)
            if at_start:
                x[..., :n] *= ramp
            else:
                x[..., -n:] *= ramp

    # Padding.
    lead = int(sr * float(cfg.get("pad_start_ms") or 0) / 1000)
    tail = int(sr * float(cfg.get("pad_end_ms") or 0) / 1000)
    if lead or tail:
        x = torch.nn.functional.pad(x, (lead, tail))

    audio = x.squeeze(0).numpy().astype(np.float32)
    if cfg.get("channels", 1) == 2:
        audio = np.stack([audio, audio], axis=1)
    else:
        audio = audio[:, None]
    return audio, sr


def encode(audio: np.ndarray, sr: int, path: Path, cfg: dict) -> Path:
    fmt = cfg.get("format", "wav")
    sf_format, ext, subtypes = FORMATS[fmt]
    path = path.with_suffix(ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt in ("wav", "flac"):
        subtype = subtypes.get(str(cfg.get("bit_depth", "24")), list(subtypes.values())[0])
        sf.write(path, audio, sr, format=sf_format, subtype=subtype)
    else:
        subtype = list(subtypes.values())[0]
        # quality 0..1 (higher is better) -> libsndfile compression level (lower is better)
        q = float(cfg.get("quality", 0.9))
        with sf.SoundFile(path, "w", sr, audio.shape[1], format=sf_format, subtype=subtype) as f:
            _set_compression_level(f, 1.0 - q)
            f.write(audio)
    return path


def peaks(audio: np.ndarray, buckets: int = 1200) -> list[float]:
    """Max-abs envelope for the UI waveform (mono mix)."""
    mono = np.abs(audio.mean(axis=1) if audio.ndim == 2 else audio)
    if mono.size == 0:
        return []
    buckets = max(1, min(buckets, mono.size))
    edges = np.linspace(0, mono.size, buckets + 1, dtype=np.int64)
    out = np.maximum.reduceat(mono, edges[:-1])
    top = float(out.max()) or 1.0
    return [round(float(v) / top, 4) for v in out]
