"""Additive synthesis with the slow (0.1–8 Hz) amplitude pulse, mono or stereo."""

from __future__ import annotations

import numpy as np

from .chaos import Chaos
from .score import Piece

ADSR = (0.012, 0.09, 0.7, 0.18)        # attack s, decay s, sustain level, release s


def lfo_envelope(piece: Piece, sr: int, depth: float = 0.35, phase_offset: float = 0.0) -> np.ndarray:
    """Gain in [1 − depth, 1] following the piece's LFO rate. Envelopes at offsets 0 and π sum to 2 − depth."""
    n = int(piece.seconds * sr)
    t_cols = np.arange(len(piece.lfo_rate)) * piece.step
    rate = np.interp(np.arange(n) / sr, t_cols, piece.lfo_rate)
    phase = 2 * np.pi * np.cumsum(rate) / sr + phase_offset
    return 1.0 - depth * (0.5 - 0.5 * np.cos(phase))


def dry(piece: Piece, sr: int) -> np.ndarray:
    """The notes alone, before the pulse and the output stage."""
    n = int(piece.seconds * sr)
    out = np.zeros(n)
    ch = Chaos(piece.seed + "/timbre")
    partials = np.array([1.0, 0.5 * ch.scalar() + 0.25, 0.3 * ch.scalar() + 0.05, 0.15 * ch.scalar()])
    a, d, s_level, r = ADSR
    for note in piece.notes:
        f = 440.0 * 2 ** ((note.pitch - 69) / 12)
        i0 = int(note.start * sr)
        i1 = min(n, i0 + int((note.duration + r) * sr))
        t = np.arange(i1 - i0) / sr
        env = np.where(t < a, t / a, np.where(t < a + d, 1 - (1 - s_level) * (t - a) / d, s_level))
        env = np.where(t > note.duration, env * np.clip(1 - (t - note.duration) / r, 0, 1), env)
        tone = sum(w * np.sin(2 * np.pi * f * (k + 1) * t) for k, w in enumerate(partials) if (k + 1) * f < sr / 2)
        out[i0:i1] += (note.velocity / 127.0) * env * tone
    return out


def _output_stage(x: np.ndarray) -> np.ndarray:
    x = np.tanh(1.5 * x / (np.max(np.abs(x)) + 1e-12))
    return 0.89 * x / (np.max(np.abs(x)) + 1e-12)                        # ≈ −1 dBFS


def render(piece: Piece, sr: int = 22050, lfo: bool = True, stereo: bool = False, depth: float = 0.35) -> np.ndarray:
    """Mono: shape (n,). Stereo: shape (n, 2) with the pulse in antiphase between the channels, so the pulse
    becomes motion between the ears and a mono fold-down (L + R) carries no pulse at all."""
    if sr < 8000:
        raise ValueError(f"sample rate {sr} is below 8000 Hz")
    x = dry(piece, sr)
    if not stereo:
        return _output_stage(x * lfo_envelope(piece, sr, depth) if lfo else x)
    if not lfo:
        return _output_stage(np.stack([x, x], axis=1))
    return _output_stage(np.stack([x * lfo_envelope(piece, sr, depth, 0.0),
                                   x * lfo_envelope(piece, sr, depth, np.pi)], axis=1))
