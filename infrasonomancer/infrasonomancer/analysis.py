"""Measurements on series and on pieces. Every estimator here has a known-answer test."""

from __future__ import annotations

import hashlib
import math

import numpy as np

from .fractal import edge_dimension
from .score import NOTE_NAMES, Piece


def hurst_rs(x: np.ndarray, min_scale: int = 8) -> float:
    """Rescaled-range Hurst exponent over dyadic scales (white noise ≈ 0.5). On an integrated series (a random
    walk, any smooth curve) R/S reads ≈ 1 whatever the dynamics, so estimate H of such series from increments."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    scales, rs = [], []
    s = min_scale
    while s <= n // 2:
        segs = x[:(n // s) * s].reshape(-1, s)
        dev = np.cumsum(segs - segs.mean(axis=1, keepdims=True), axis=1)
        sd = segs.std(axis=1)
        ok = sd > 0
        if ok.any():
            scales.append(s)
            rs.append(np.mean((dev.max(axis=1) - dev.min(axis=1))[ok] / sd[ok]))
        s *= 2
    if len(scales) < 2:
        return float("nan")
    return float(np.polyfit(np.log(scales), np.log(rs), 1)[0])


def dfa(x: np.ndarray, min_scale: int = 8, max_scale: int | None = None, order: int = 1) -> float:
    """Detrended fluctuation analysis exponent α (Peng et al. 1994): white noise 0.5, 1/f noise 1, random walk 1.5.
    Windows run from both ends so no samples are discarded; scales are log-spaced from min_scale to n/4."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    max_scale = max_scale or n // 4
    if max_scale < 2 * min_scale:
        return float("nan")
    y = np.cumsum(x - x.mean())
    scales = np.unique(np.round(np.geomspace(min_scale, max_scale, 16)).astype(int))
    fluct = []
    for s in scales:
        t = np.arange(s, dtype=float)
        a = np.vander(t / s, order + 1)                                   # scaled: well conditioned at any s
        k = n // s
        segs = np.concatenate([y[:k * s].reshape(k, s), y[n - k * s:].reshape(k, s)])
        resid = segs - (a @ (np.linalg.pinv(a) @ segs.T)).T              # least-squares polynomial trend per window
        fluct.append(math.sqrt(float(np.mean(resid ** 2))))
    return float(np.polyfit(np.log(scales), np.log(fluct), 1)[0])


def persistence(points: np.ndarray) -> dict[int, list[tuple[float, float]]]:
    """Vietoris–Rips persistent homology in dimensions 0 and 1 (2-skeleton, exact Z/2 column reduction).

    Simplices are ordered by (filtration value, dimension); columns are Python ints used as bit sets, so a
    column addition is one XOR. Returns {0: [(birth, death), ...], 1: [...]}; the one infinite H0 bar has
    death = inf. Cost grows as n³ in the number of points: keep n ≤ 80.
    """
    p = np.asarray(points, dtype=float)
    n = len(p)
    if n > 80:
        raise ValueError(f"persistence on {n} points builds {n * (n - 1) * (n - 2) // 6} triangles; subsample to ≤ 80")
    d = np.sqrt(((p[:, None, :] - p[None, :, :]) ** 2).sum(-1))
    simplices: list[tuple[float, int, tuple]] = [(0.0, 0, (i,)) for i in range(n)]
    simplices += [(float(d[i, j]), 1, (i, j)) for i in range(n) for j in range(i + 1, n)]
    simplices += [(float(max(d[i, j], d[i, k], d[j, k])), 2, (i, j, k))
                  for i in range(n) for j in range(i + 1, n) for k in range(j + 1, n)]
    simplices.sort(key=lambda s: (s[0], s[1], s[2]))
    index = {s[2]: idx for idx, s in enumerate(simplices)}
    low_of: dict[int, tuple[int, int]] = {}
    pairs: dict[int, list[tuple[float, float]]] = {0: [], 1: []}
    paired: set[int] = set()
    for j, (fval, dim, verts) in enumerate(simplices):
        if dim == 0:
            continue
        col = 0
        for drop in range(len(verts)):
            col ^= 1 << index[verts[:drop] + verts[drop + 1:]]
        while col:
            low = col.bit_length() - 1
            if low not in low_of:
                break
            col ^= low_of[low][1]
        if col:
            low = col.bit_length() - 1
            low_of[low] = (j, col)
            birth = simplices[low][0]
            paired.update((low, j))
            if fval > birth:
                pairs[dim - 1].append((birth, fval))
    for idx, (fval, dim, _) in enumerate(simplices):
        if idx not in paired and dim == 0:
            pairs[0].append((fval, math.inf))
    return pairs


def autocorrelation(x: np.ndarray) -> np.ndarray:
    """Biased autocorrelation at lags 0..n−1 by FFT (O(n log n)), normalised to 1 at lag 0."""
    x = np.asarray(x, dtype=float) - np.mean(x)
    n = len(x)
    f = np.fft.rfft(x, 2 * n)
    ac = np.fft.irfft(f * np.conj(f), 2 * n)[:n]
    return ac / (ac[0] + 1e-300)


def embedding_delay(x: np.ndarray) -> int:
    """First zero crossing of the autocorrelation (1 when it never crosses)."""
    zero = np.flatnonzero(autocorrelation(x) <= 0)
    return int(zero[0]) if len(zero) else 1


def delay_embed(x: np.ndarray, dim: int = 3, tau: int | None = None, max_points: int = 48) -> np.ndarray:
    """Takens delay embedding of the standardised series, thinned evenly to at most max_points points."""
    x = np.asarray(x, dtype=float)
    x = (x - x.mean()) / (x.std() + 1e-12)
    tau = tau or embedding_delay(x)
    m = len(x) - (dim - 1) * tau
    if m < 2:
        raise ValueError(f"series of {len(x)} samples is too short for dim {dim} at delay {tau}")
    emb = np.stack([x[i * tau:i * tau + m] for i in range(dim)], axis=1)
    if len(emb) > max_points:
        emb = emb[np.linspace(0, len(emb) - 1, max_points).astype(int)]
    return emb


def recurrence(x: np.ndarray, dim: int = 3, points: int = 48) -> dict:
    """H1 persistence of the delay-embedded series: loops in state space are recurring cycles."""
    tau = embedding_delay(x)
    emb = delay_embed(x, dim, tau, points)
    bars = persistence(emb)
    diameter = float(np.max(np.sqrt(((emb[:, None] - emb[None]) ** 2).sum(-1))))
    h1 = sorted(bars[1], key=lambda bd: bd[0] - bd[1])
    return {"tau_samples": tau, "points": len(emb), "h1_bars": len(h1),
            "longest_h1_over_diameter": ((h1[0][1] - h1[0][0]) / diameter) if h1 and diameter > 0 else 0.0,
            "top_h1": [[round(b, 6), round(d, 6)] for b, d in h1[:5]]}


def welch(x: np.ndarray, fs: float, seconds: float | None = None, overlap: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """One-sided power spectral density by Welch's method: Hann segments, mean removed per segment,
    density scaling (units²/Hz), matching scipy.signal.welch's defaults for the same segment length."""
    x = np.asarray(x, dtype=float)
    nper = min(len(x), int(round((seconds or 256 / fs) * fs)))
    step = max(1, int(nper * (1 - overlap)))
    w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(nper) / nper)          # periodic Hann
    starts = range(0, len(x) - nper + 1, step)
    segs = np.stack([x[s:s + nper] for s in starts])
    segs = (segs - segs.mean(axis=1, keepdims=True)) * w
    p = np.mean(np.abs(np.fft.rfft(segs, axis=1)) ** 2, axis=0) / (fs * (w ** 2).sum())
    p[1:-1 if nper % 2 == 0 else None] *= 2
    return np.fft.rfftfreq(nper, 1 / fs), p


def msc(x: np.ndarray, y: np.ndarray, fs: float, seconds: float, overlap: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """Magnitude-squared coherence |Sxy|² / (Sxx·Syy) by Welch averaging (Hann segments, mean removed per segment),
    matching scipy.signal.coherence for the same segment length. 1 at frequencies where y is a linear filter of x."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(x) != len(y):
        raise ValueError(f"msc needs equal lengths, got {len(x)} and {len(y)}")
    nper = min(len(x), int(round(seconds * fs)))
    step = max(1, int(nper * (1 - overlap)))
    w = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(nper) / nper)
    starts = range(0, len(x) - nper + 1, step)

    def spec(v: np.ndarray) -> np.ndarray:
        segs = np.stack([v[s:s + nper] for s in starts])
        return np.fft.rfft((segs - segs.mean(axis=1, keepdims=True)) * w, axis=1)

    fx, fy = spec(x), spec(y)
    sxy = np.mean(fx * np.conj(fy), axis=0)
    sxx, syy = np.mean(np.abs(fx) ** 2, axis=0), np.mean(np.abs(fy) ** 2, axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.where(sxx * syy > 0, np.abs(sxy) ** 2 / (sxx * syy), 0.0)
    return np.fft.rfftfreq(nper, 1 / fs), c


def dominant_frequency(x: np.ndarray, fs: float, fmin: float = 0.01, fmax: float | None = None) -> float:
    """Peak of the Hann-windowed periodogram within [fmin, fmax], refined by parabolic interpolation of the
    log power over the three bins around the peak."""
    x = np.asarray(x, dtype=float)
    p = np.abs(np.fft.rfft((x - x.mean()) * np.hanning(len(x)))) ** 2
    f = np.fft.rfftfreq(len(x), 1 / fs)
    band = (f >= fmin) & (f <= (fmax if fmax is not None else fs / 2))
    if not band.any():
        raise ValueError(f"no frequency bins in [{fmin}, {fmax}] Hz at {len(x)} samples, {fs} Hz")
    k = int(np.flatnonzero(band)[np.argmax(p[band])])
    if 0 < k < len(p) - 1 and min(p[k - 1], p[k], p[k + 1]) > 0:
        a, b, c = np.log(p[k - 1:k + 2])
        shift = 0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c != 0 else 0.0
        return float(f[k] + np.clip(shift, -0.5, 0.5) * (f[1] - f[0]))
    return float(f[k])


def describe_series(x: np.ndarray, fs: float, points: int = 48, fmin: float = 0.01,
                    fmax: float | None = None) -> dict:
    x = np.asarray(x, dtype=float)
    return {
        "samples": len(x), "fs": fs, "seconds": len(x) / fs, "mean": float(x.mean()), "std": float(x.std()),
        "dominant_hz": dominant_frequency(x, fs, fmin, fmax),
        "hurst_rs_levels": hurst_rs(x),
        "hurst_rs_increments": hurst_rs(np.diff(x)),
        "dfa_alpha": dfa(x),
        "recurrence": recurrence(x, points=points),
    }


def analyse(piece: Piece, audio: np.ndarray, sr: int) -> dict:
    """Numbers measured on what was produced: the score, the fractal, the texture and the audio."""
    notes = piece.notes
    pcs = np.zeros(12)
    for nt in notes:
        pcs[nt.pitch % 12] += nt.duration
    p = pcs[pcs > 0] / pcs.sum() if pcs.sum() > 0 else np.zeros(0)
    texture = piece.lattice.std(axis=0)
    rec = recurrence(texture)
    onsets = np.zeros(len(piece.lfo_rate))
    for nt in notes:
        onsets[min(len(onsets) - 1, int(nt.start / piece.step))] += 1
    a = np.asarray(audio)
    channels = a.reshape(len(a), -1)
    pcm = np.clip(np.round(a * 32767), -32768, 32767).astype("<i2")
    return {
        "seed": piece.seed, "sha256": hashlib.sha256(piece.seed.encode()).hexdigest()[:16],
        "genome": piece.genome.to_dict(),
        "julia_c": [round(piece.c.real, 6), round(piece.c.imag, 6)],
        "mode": f"{NOTE_NAMES[piece.root % 12]} {piece.mode}",
        "notes": len(notes), "seconds": piece.seconds,
        "polyphony_max": int(max((sum(1 for o in notes if o.start <= t < o.start + o.duration)
                                  for t in np.arange(0, piece.seconds, piece.step)), default=0)),
        "pitch_range": [min(n.pitch for n in notes), max(n.pitch for n in notes)] if notes else None,
        "pitch_class_entropy_bits": float(-(p * np.log2(p)).sum()) if len(p) else 0.0,
        "fractal_boundary_dimension": edge_dimension(piece.c),
        # R/S reads ≈ 1 on any integrated (fBm-like) series, so H is estimated from the increments (fGn)
        "hurst_of_texture_increments": hurst_rs(np.diff(texture)),
        "texture_recurrence": {"h1_bars": rec["h1_bars"], "longest_h1_over_diameter": rec["longest_h1_over_diameter"]},
        "lfo_hz": [float(piece.lfo_rate.min()), float(piece.lfo_rate.max())],
        "onset_rate_vs_lfo_corr": float(np.corrcoef(onsets, piece.lfo_rate)[0, 1]) if onsets.std() > 0 else 0.0,
        "audio": {"sample_rate": sr, "channels": channels.shape[1],
                  "peak_dbfs": float(20 * np.log10(np.max(np.abs(a)) + 1e-12)),
                  "rms_dbfs": float(20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-12)),
                  "pcm_sha256": hashlib.sha256(pcm.tobytes()).hexdigest()[:16]},
    }
