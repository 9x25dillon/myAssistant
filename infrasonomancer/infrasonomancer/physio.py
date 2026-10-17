"""Heartbeats from ECG or PPG, and heart-rate variability. Offline, zero-phase, O(n log n).

ECG follows Pan & Tompkins (1985): band-pass 5–20 Hz, squared slope, 120 ms moving integration, refractory 250 ms,
adaptive threshold, search-back for missed beats; the fiducial is the R wave's extreme (either polarity) on a
0.5–40 Hz trace, refined to sub-sample time. PPG uses the slope-sum function (Zong et al. 2003) with the steepest
upstroke as fiducial. HRV follows the Task Force of the ESC/NASPE (1996) definitions.
"""

from __future__ import annotations

import math

import numpy as np

from .analysis import welch

_KINDS = {
    #       energy band, integration s, refractory s, fiducial band, fiducial search ± s
    "ecg": ((5.0, 20.0), 0.12, 0.25, (0.5, 40.0), 0.08),
    "ppg": ((0.5, 8.0), 0.128, 0.30, (0.5, 8.0), 0.15),
}


def bandpass(x: np.ndarray, fs: float, lo: float, hi: float) -> np.ndarray:
    """Zero-phase FFT band-pass with raised-cosine edges 20 % of each corner wide (less ringing than a brick wall)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    f = np.fft.rfftfreq(n, 1 / fs)
    hi = min(hi, fs / 2)

    def ramp(v: np.ndarray, edge: float) -> np.ndarray:
        w = 0.2 * edge
        return np.clip((v - (edge - w / 2)) / w, 0.0, 1.0) if w > 0 else (v >= edge).astype(float)

    gain = ramp(f, lo) * (1.0 - ramp(f, hi))
    gain = 0.5 - 0.5 * np.cos(np.pi * gain)                               # smooth the linear ramps
    return np.fft.irfft(np.fft.rfft(x - x.mean()) * gain, n)


def rolling_max(x: np.ndarray, width: int) -> np.ndarray:
    """Centred running maximum over `width` samples (odd), O(n) by van Herk / Gil-Werman."""
    w = max(1, int(width) | 1)
    h = w // 2
    n = len(x)
    pad = np.concatenate([np.full(h, -np.inf), np.asarray(x, dtype=float), np.full(h + w, -np.inf)])
    blocks = len(pad) // w
    b = pad[:blocks * w].reshape(blocks, w)
    prefix = np.maximum.accumulate(b, axis=1).ravel()
    suffix = np.maximum.accumulate(b[:, ::-1], axis=1)[:, ::-1].ravel()
    i = np.arange(n)
    return np.maximum(suffix[i], prefix[i + w - 1])


def _local_level(e: np.ndarray, fs: float) -> np.ndarray:
    """Typical beat height near each sample: running max over 2 s, then a running median over ~10 s."""
    peak = rolling_max(e, int(2 * fs))
    hop = max(1, int(fs))
    coarse = peak[::hop]
    k = 5
    padded = np.concatenate([np.full(k, coarse[0]), coarse, np.full(k, coarse[-1])])
    med = np.median(np.lib.stride_tricks.sliding_window_view(padded, 2 * k + 1), axis=1)
    return np.interp(np.arange(len(e)), np.arange(len(coarse)) * hop, med)


def _pick_peaks(e: np.ndarray, threshold: np.ndarray, refractory: int) -> np.ndarray:
    is_max = (e >= rolling_max(e, 2 * refractory + 1)) & (e > threshold)
    idx = np.flatnonzero(is_max)
    keep: list[int] = []
    for i in idx:                                                        # plateaus: keep the first sample
        if not keep or i - keep[-1] > refractory:
            keep.append(int(i))
    return np.array(keep, dtype=np.int64)


def detect_beats(x: np.ndarray, fs: float, kind: str = "ecg") -> np.ndarray:
    """Beat times in seconds from an ECG (R waves) or a PPG/BVP trace (steepest systolic upstrokes)."""
    if kind not in _KINDS:
        raise ValueError(f"kind must be one of {sorted(_KINDS)}, got {kind!r}")
    x = np.asarray(x, dtype=float)
    if len(x) < 4 * fs:
        raise ValueError(f"need at least 4 s of signal, got {len(x) / fs:.2f} s")
    (lo, hi), integ, refr_s, (flo, fhi), search_s = _KINDS[kind]
    if fs < 2.5 * hi:
        raise ValueError(f"{kind} beat detection needs fs ≥ {2.5 * hi:g} Hz, got {fs:g}")
    band = bandpass(x, fs, lo, hi)
    slope = np.gradient(band) * fs
    raw = slope ** 2 if kind == "ecg" else np.maximum(slope, 0.0)
    k = max(1, int(round(integ * fs)))
    e = np.convolve(raw, np.ones(k) / k, mode="same")
    level = _local_level(e, fs)
    floor = 0.1 * float(np.median(level))
    thr = np.maximum(0.3 * level, floor)
    refr = int(round(refr_s * fs))
    peaks = _pick_peaks(e, thr, refr)
    # search-back: an interval longer than 1.6 × the local median hides a beat that fell under the threshold. The
    # energy is a squared slope, so a beat at a third of the usual amplitude has a ninth of the energy: inside such
    # a gap the bar drops to 0.15 × threshold (T waves sit two orders of magnitude lower still).
    for _ in range(2):
        if len(peaks) < 4:
            break
        rr = np.diff(peaks)
        med = np.array([np.median(rr[max(0, i - 4):i + 5]) for i in range(len(rr))])
        extra = []
        for i in np.flatnonzero(rr > 1.6 * med):
            a, b = peaks[i] + refr, peaks[i + 1] - refr
            if b > a:
                seg = e[a:b]
                j = int(np.argmax(seg))
                if seg[j] > 0.15 * thr[a + j]:
                    extra.append(a + j)
        if not extra:
            break
        peaks = np.unique(np.concatenate([peaks, extra]))
    if len(peaks) == 0:
        return np.zeros(0)
    fid = bandpass(x, fs, flo, fhi) if kind == "ecg" else np.gradient(bandpass(x, fs, flo, fhi))
    s = int(round(search_s * fs))
    if kind == "ecg":                                                    # R polarity: the sign of the larger extreme
        ext = [fid[max(0, p - s):p + s + 1] for p in peaks]
        sign = 1.0 if np.median([w.max() + w.min() for w in ext]) >= 0 else -1.0
        fid = sign * fid
    times = []
    for p in peaks:
        a, b = max(1, p - s), min(len(fid) - 1, p + s + 1)
        j = a + int(np.argmax(fid[a:b]))
        y0, y1, y2 = fid[j - 1], fid[j], fid[min(j + 1, len(fid) - 1)]
        den = y0 - 2 * y1 + y2
        times.append((j + (0.5 * (y0 - y2) / den if den < 0 else 0.0)) / fs)
    t = np.array(times)
    keep = np.concatenate([[True], np.diff(t) > 0.5 * refr_s])             # refinement can merge two candidates
    return t[keep]


def clean_intervals(beats: np.ndarray, lo: float = 0.3, hi: float = 2.0, tolerance: float = 0.2) -> tuple[
        np.ndarray, np.ndarray]:
    """(interval end times, intervals) keeping intervals in [lo, hi] s within ±tolerance of the 11-beat running
    median: ectopic beats and detection errors are excluded rather than corrected."""
    rr = np.diff(beats)
    if len(rr) == 0:
        return np.zeros(0), np.zeros(0)
    pad = np.concatenate([np.full(5, rr[0]), rr, np.full(5, rr[-1])])
    med = np.median(np.lib.stride_tricks.sliding_window_view(pad, 11), axis=1)
    ok = (rr >= lo) & (rr <= hi) & (np.abs(rr - med) <= tolerance * med)
    return beats[1:][ok], rr[ok]


def hrv(beats: np.ndarray, resample_hz: float = 4.0) -> dict:
    """Time-domain and spectral HRV. LF (0.04–0.15 Hz) is reported only for records ≥ 120 s, HF (0.15–0.40 Hz)
    for ≥ 60 s; the HF peak frequency is the respiratory sinus arrhythmia rate, i.e. the breathing rate."""
    beats = np.asarray(beats, dtype=float)
    if len(beats) < 3:
        raise ValueError("need at least 3 beats")
    t, rr = clean_intervals(beats)
    total = len(beats) - 1
    out: dict = {"beats": len(beats), "seconds": float(beats[-1] - beats[0]), "intervals_used": len(rr),
                 "intervals_excluded": total - len(rr)}
    if len(rr) < 2:
        return out
    d = np.diff(rr)
    adjacent = np.diff(t) <= rr[1:] * 1.0001                              # successive differences only across neighbours
    d = d[adjacent]
    out.update(mean_rr_ms=1e3 * float(rr.mean()), mean_hr_bpm=60.0 / float(rr.mean()),
               sdnn_ms=1e3 * float(rr.std(ddof=1)), rmssd_ms=1e3 * float(np.sqrt(np.mean(d ** 2))) if len(d) else None,
               pnn50=float(np.mean(np.abs(d) > 0.05)) if len(d) else None)
    duration = float(t[-1] - t[0])
    if duration < 60:
        return out
    grid = np.arange(t[0], t[-1], 1 / resample_hz)
    tach = np.interp(grid, t, rr) * 1e3
    tach = tach - np.polyval(np.polyfit(grid, tach, 1), grid)              # remove the linear trend
    f, p = welch(tach, resample_hz, seconds=min(duration, 120.0))
    df = f[1] - f[0]

    def band(lo: float, hi: float) -> tuple[float, float]:
        sel = (f >= lo) & (f < hi)
        return float(p[sel].sum() * df), float(f[sel][np.argmax(p[sel])])

    hf, hf_peak = band(0.15, 0.40)
    out.update(hf_ms2=hf, hf_peak_hz=hf_peak)
    if duration >= 120:
        lf, lf_peak = band(0.04, 0.15)
        out.update(lf_ms2=lf, lf_peak_hz=lf_peak, lf_hf=lf / hf if hf > 0 else math.inf)
    return out
