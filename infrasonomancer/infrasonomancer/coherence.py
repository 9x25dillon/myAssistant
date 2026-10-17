"""Phase synchronization between two rhythms (breathing and heartbeat, say), with a null hypothesis.

A stream is a phase that grows by 2π per cycle: from a signal, the Hilbert phase of its band-passed dominant
rhythm; from events (heartbeats), 2π per event, linear in between (Rosenblum et al. 2001). The n:m index
|⟨exp(i(n·φx − m·φy))⟩| (Tass et al., PRL 81, 3291, 1998) is 1 for perfect locking and small for unrelated
phases, but its value under "no relation" depends on record length and spectra, so every index here comes with
a p-value from time-shift surrogates: y is cut at a random lag and its halves swapped (its own dynamics kept,
its relation to x destroyed), and the same statistic is recomputed on each surrogate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .analysis import dominant_frequency, msc, welch
from .chaos import Chaos
from .physio import bandpass, clean_intervals


def analytic(x: np.ndarray) -> np.ndarray:
    """Analytic signal by FFT (the Hilbert transform's discrete form)."""
    n = len(x)
    spec = np.fft.fft(x)
    h = np.zeros(n)
    h[0] = 1
    if n % 2 == 0:
        h[n // 2] = 1
        h[1:n // 2] = 2
    else:
        h[1:(n + 1) // 2] = 2
    return np.fft.ifft(spec * h)


# ============================================================================================ two-signal shortcuts

def _bandpass_rel(x: np.ndarray, fs: float, f0: float, rel: float = 0.3) -> np.ndarray:
    spec = np.fft.rfft(x - np.mean(x))
    f = np.fft.rfftfreq(len(x), 1 / fs)
    spec[(f < f0 * (1 - rel)) | (f > f0 * (1 + rel))] = 0
    return np.fft.irfft(spec, len(x))


def nm_phase_locking(x: np.ndarray, y: np.ndarray, fs: float, n: int, m: int,
                     fx: float | None = None, fy: float | None = None) -> float:
    """n:m index of two equally sampled signals; n·fx ≈ m·fy when they lock (breath x, heart y at 4 beats per
    breath: n = 4, m = 1). No null distribution: use `synchronize` for a p-value."""
    fx = fx or dominant_frequency(x, fs)
    fy = fy or dominant_frequency(y, fs)
    px = np.angle(analytic(_bandpass_rel(x, fs, fx)))
    py = np.angle(analytic(_bandpass_rel(y, fs, fy)))
    trim = slice(len(x) // 10, -len(x) // 10 or None)                    # drop filter edge effects
    return float(np.abs(np.mean(np.exp(1j * (n * px[trim] - m * py[trim])))))


def nearest_ratio(fx: float, fy: float, max_n: int = 12, max_m: int = 3) -> tuple[int, int, float]:
    """Coprime (n, m), n ≤ max_n, m ≤ max_m, minimising the relative detuning |n·fx − m·fy| / (m·fy);
    ties go to the smaller n + m."""
    best = min(((n, m) for n in range(1, max_n + 1) for m in range(1, max_m + 1) if math.gcd(n, m) == 1),
               key=lambda nm: (round(abs(nm[0] * fx - nm[1] * fy) / (nm[1] * fy), 12), nm[0] + nm[1]))
    return best[0], best[1], abs(best[0] * fx - best[1] * fy) / (best[1] * fy)


def coherence_report(x: np.ndarray, y: np.ndarray, fs: float, max_ratio: int = 8) -> dict:
    """Dominant rates of two signals, the nearest small n:m ratio, and the locking index at that ratio."""
    fx, fy = dominant_frequency(x, fs), dominant_frequency(y, fs)
    n, m, _ = nearest_ratio(fx, fy, max_ratio, max_ratio)
    return {"fx_hz": fx, "fy_hz": fy, "ratio": f"{n}:{m}", "locking_index": nm_phase_locking(x, y, fs, n, m, fx, fy)}


# ============================================================================================ streams

@dataclass
class PhaseStream:
    kind: str                                   # "signal" or "events"
    t0: float                                   # valid from (s)
    t1: float                                   # valid to (s)
    rate_hz: float
    phase_at: Callable[[np.ndarray], np.ndarray]
    events: np.ndarray | None = None
    info: dict = field(default_factory=dict)
    samples: tuple[np.ndarray, float] | None = None    # the raw signal and its rate, for kind "signal"


def stream_from_signal(x: np.ndarray, fs: float, band: tuple[float, float] | None = None, fmin: float = 0.05,
                       fmax: float | None = None, rel: float = 0.35) -> PhaseStream:
    """Hilbert phase of the band around the dominant rhythm (or of `band`). The signal is mirrored at both ends
    before the zero-phase filter, and one period of the lowest band edge is still dropped at each end.

    The phase means something only when the band holds the rhythm: `band_power_fraction` (band variance / total
    variance) is reported, with a warning below 0.3. A drifting baseline can out-power the rhythm in the whole-record
    spectrum; pass `band` explicitly then (breathing: 0.15–0.5 Hz)."""
    x = np.asarray(x, dtype=float)
    if band is None:
        f0 = dominant_frequency(x, fs, fmin, fmax)
        band = (f0 * (1 - rel), f0 * (1 + rel))
    lo, hi = band
    if not 0 < lo < hi <= fs / 2:
        raise ValueError(f"band {band} must satisfy 0 < lo < hi ≤ fs/2 = {fs / 2}")
    n = len(x)
    edge = 1.0 / lo
    if n / fs <= 2 * edge + 10:
        raise ValueError(f"{n / fs:.1f} s of signal is too short for a {lo:.3g} Hz band edge "
                         f"(needs > {2 * edge + 10:.0f} s)")
    pad = min(n - 1, int(3 * edge * fs))
    mirrored = np.concatenate([x[pad:0:-1], x, x[-2:-pad - 2:-1]])
    filtered = bandpass(mirrored, fs, lo, hi)[pad:pad + n]
    phase = np.unwrap(np.angle(analytic(filtered)))
    t = np.arange(n) / fs
    valid = (t >= edge) & (t <= t[-1] - edge)
    rate = (phase[valid][-1] - phase[valid][0]) / (2 * np.pi * (t[valid][-1] - t[valid][0]))
    fraction = float(np.var(filtered[valid]) / (np.var(x[valid]) + 1e-300))
    info = {"band_hz": [float(lo), float(hi)], "band_power_fraction": fraction}
    if fraction < 0.3:
        info["warning"] = (f"only {100 * fraction:.0f} % of the variance lies in {lo:.3g}–{hi:.3g} Hz: the phase may "
                           "not follow the rhythm; choose the band explicitly")
    return PhaseStream("signal", float(edge), float(t[-1] - edge), float(rate),
                       lambda q: np.interp(q, t, phase), None, info, (x, float(fs)))


def stream_from_events(times: np.ndarray) -> PhaseStream:
    """2π per event, linear between events."""
    ev = np.asarray(times, dtype=float)
    if len(ev) < 3 or np.any(np.diff(ev) <= 0):
        raise ValueError("need at least 3 strictly increasing event times")
    k = np.arange(len(ev), dtype=float)
    rate = (len(ev) - 1) / (ev[-1] - ev[0])
    return PhaseStream("events", float(ev[0]), float(ev[-1]), float(rate),
                       lambda q: 2 * np.pi * np.interp(q, ev, k), ev, {"events": len(ev)})


# ============================================================================================ synchronization

def _shifted(phase: np.ndarray, lag: int) -> np.ndarray:
    """The same phase increments, circularly delayed by `lag` samples: a continuous surrogate phase."""
    d = np.diff(phase)
    return np.concatenate([[phase[0]], phase[0] + np.cumsum(np.roll(d, lag))])


def _window_stats(px: np.ndarray, py: np.ndarray, starts: np.ndarray, width: int, max_n: int, max_m: int,
                  rate: float) -> tuple[np.ndarray, list[tuple[int, int]]]:
    ends = starts + width
    fx = (px[ends - 1] - px[starts]) / (2 * np.pi * (width - 1) / rate)
    fy = (py[ends - 1] - py[starts]) / (2 * np.pi * (width - 1) / rate)
    ratios = [nearest_ratio(a, b, max_n, max_m)[:2] if a > 0 and b > 0 else (1, 1) for a, b in zip(fx, fy)]
    index = np.empty(len(starts))
    for nm in set(ratios):
        z = np.concatenate([[0j], np.cumsum(np.exp(1j * (nm[0] * px - nm[1] * py)))])
        sel = np.array([r == nm for r in ratios])
        index[sel] = np.abs(z[ends[sel]] - z[starts[sel]]) / width
    return index, ratios


def candidate_ratios(fx: float, fy: float, max_n: int = 12, max_m: int = 3, spread: float = 0.35) -> list[tuple[int, int]]:
    """Coprime (n, m) within `spread` relative detuning of the mean rates, nearest first."""
    out = [(n, m) for n in range(1, max_n + 1) for m in range(1, max_m + 1)
           if math.gcd(n, m) == 1 and abs(n * fx - m * fy) / (m * fy) <= spread]
    return sorted(out, key=lambda nm: (abs(nm[0] * fx - nm[1] * fy) / (nm[1] * fy), nm[0] + nm[1]))


def synchronize(x: PhaseStream, y: PhaseStream, rate: float = 10.0, window: float = 30.0, step: float = 5.0,
                max_n: int = 12, max_m: int = 3, surrogates: int = 199, min_shift: float | None = None,
                alpha: float = 0.05, seed: str = "synchronize", spread: float = 0.35) -> dict:
    """Whole-record and windowed n:m synchronization of x and y on their common time range, sampled at `rate` Hz.

    Whole record: every coprime ratio within `spread` relative detuning of the mean rates is tested and the largest
    index is the statistic, with p = (1 + #{surrogate max ≥ observed max}) / (1 + K): the surrogates take the same
    maximum, so scanning ratios costs no false positives. The scan matters because coupled pairs that drift do not
    run at their coupling ratio (a 4:1-coupled pair can average 3.5 beats per breath).
    Windows: each window takes the ratio nearest its own rates. A window counts as locked when its index exceeds
    the (1 − alpha) quantile of all surrogate windows' indices; the fraction of locked windows is then tested
    against the same fraction on each surrogate, which keeps the test valid although windows overlap.

    A small p shows phase *interaction*, not locking. Two coupled oscillators outside their Arnold tongue slip
    continuously, yet linger near the ghost of the fixed point, so their phase difference stays non-uniform: for
    Adler dynamics its mean resultant is |δ| − √(δ² − 1) (0.27 at δ = 2), which a long record detects. Locking is
    the absence of slips, so the verdict also counts net cycles of ψ = n·φx − m·φy over the record:
        locked                       p ≤ alpha and fewer than one net slip
        interacting, not locked      p ≤ alpha, one or more net slips
        no evidence of interaction   p > alpha
    """
    t0, t1 = max(x.t0, y.t0), min(x.t1, y.t1)
    if t1 - t0 < 2 * window:
        raise ValueError(f"the streams overlap for {max(0.0, t1 - t0):.1f} s; need at least 2 windows "
                         f"({2 * window:.0f} s)")
    t = np.arange(t0, t1, 1 / rate)
    px, py = x.phase_at(t), y.phase_at(t)
    n_samples = len(t)
    width = int(round(window * rate))
    starts = np.arange(0, n_samples - width + 1, max(1, int(round(step * rate))))
    min_shift = window if min_shift is None else min_shift
    lo, hi = int(min_shift * rate), n_samples - int(min_shift * rate)
    if hi <= lo:
        raise ValueError(f"record of {t1 - t0:.1f} s is too short for surrogate shifts of at least {min_shift} s")
    lags = lo + (Chaos(seed).uniform(surrogates) * (hi - lo)).astype(int)

    fx_all = (px[-1] - px[0]) / (2 * np.pi * (t[-1] - t[0]))
    fy_all = (py[-1] - py[0]) / (2 * np.pi * (t[-1] - t[0]))
    near = nearest_ratio(fx_all, fy_all, max_n, max_m)
    cands = candidate_ratios(fx_all, fy_all, max_n, max_m, spread) or [near[:2]]
    cx = np.exp(1j * np.outer([c[0] for c in cands], px))                # phasors of n·φx, one row per candidate

    def scan(q: np.ndarray) -> np.ndarray:
        return np.abs(np.mean(cx * np.exp(-1j * np.outer([c[1] for c in cands], q)), axis=1))

    obs_scan = scan(py)
    best = int(np.argmax(obs_scan))
    n, m = cands[best]
    detune = abs(n * fx_all - m * fy_all) / (m * fy_all)
    net_slips = float(((n * px[-1] - m * py[-1]) - (n * px[0] - m * py[0])) / (2 * np.pi))

    obs_index, obs_ratios = _window_stats(px, py, starts, width, max_n, max_m, rate)
    obs_whole = float(obs_scan[best])
    sur_whole, sur_index = np.empty(surrogates), []
    for k, lag in enumerate(lags):
        q = _shifted(py, int(lag))
        sur_whole[k] = float(scan(q).max())
        sur_index.append(_window_stats(px, q, starts, width, max_n, max_m, rate)[0])
    p_whole = float((1 + np.sum(sur_whole >= obs_whole)) / (1 + surrogates))
    verdict = ("no evidence of interaction" if p_whole > alpha else
               "locked" if abs(net_slips) < 1 else "interacting, not locked")
    ends = starts + width - 1
    win_slips = np.array([((a * px[e] - b * py[e]) - (a * px[s0] - b * py[s0])) / (2 * np.pi)
                          for (a, b), s0, e in zip(obs_ratios, starts, ends)])
    pooled = np.concatenate(sur_index)
    thresh = float(np.quantile(pooled, 1 - alpha))
    locked = obs_index > thresh
    frac_obs = float(locked.mean())
    frac_sur = np.array([float((s > thresh).mean()) for s in sur_index])

    runs, run = [], 0
    for flag in locked:
        run = run + 1 if flag else 0
        runs.append(run)
    longest = max(runs, default=0)
    counts: dict[str, int] = {}
    for r in obs_ratios:
        counts[f"{r[0]}:{r[1]}"] = counts.get(f"{r[0]}:{r[1]}", 0) + 1
    return {
        "overlap_s": [float(t0), float(t1)], "rate_hz": rate,
        "x_rate_hz": float(fx_all), "y_rate_hz": float(fy_all),
        "whole_record": {"ratio": f"{n}:{m}", "relative_detuning": float(detune), "index": obs_whole,
                         "nearest_ratio": f"{near[0]}:{near[1]}", "ratios_scanned": len(cands),
                         "surrogate_mean": float(sur_whole.mean()), "surrogate_q95": float(np.quantile(sur_whole, 0.95)),
                         "p": p_whole, "net_slips": net_slips, "slips_per_min": 60 * net_slips / (t[-1] - t[0]),
                         "verdict": verdict},
        "windows": {"seconds": window, "step_s": step, "count": len(starts), "ratios": counts,
                    "index_threshold": thresh, "locked_fraction": frac_obs,
                    "slip_free_fraction": float(np.mean(np.abs(win_slips) < 0.5)),
                    "locked_fraction_expected": float(frac_sur.mean()),
                    "p": float((1 + np.sum(frac_sur >= frac_obs)) / (1 + surrogates)),
                    "longest_locked_s": float(0 if longest == 0 else window + (longest - 1) * step),
                    "mean_index": float(obs_index.mean())},
        "surrogates": surrogates, "min_shift_s": min_shift, "alpha": alpha,
        "_table": {"t_start": t[starts], "t_end": t[starts] + window, "ratio": [f"{a}:{b}" for a, b in obs_ratios],
                   "index": obs_index, "locked": locked.astype(int), "slips": win_slips},
    }


def synchrogram(events: np.ndarray, other: PhaseStream, m: int) -> tuple[np.ndarray, np.ndarray]:
    """Stroboscopic view (Schäfer et al., Nature 392, 239, 1998): the other stream's phase, wrapped over m of its
    cycles, read at each event. n horizontal bands of points mean n events per m cycles, phase-locked."""
    ev = np.asarray(events, dtype=float)
    ev = ev[(ev >= other.t0) & (ev <= other.t1)]
    psi = np.mod(other.phase_at(ev), 2 * np.pi * m) / (2 * np.pi)
    return ev, psi


def rate_coupling(x: np.ndarray, fs: float, events: np.ndarray, band: tuple[float, float] = (0.1, 0.5),
                  seconds: float = 60.0, rate: float = 4.0, surrogates: int = 199, min_shift: float | None = None,
                  seed: str = "rate-coupling") -> dict:
    """Spectral coupling of a signal (breathing) with the instantaneous rate of an event train (heartbeats).

    Magnitude-squared coherence between the signal and 60/RR, both resampled at `rate` Hz over the events' span
    (the signal is low-passed below rate/2 first, so nothing aliases). The statistic is the largest coherence in
    `band`; its p-value comes from circular time shifts of the rate series, which also pays for having searched
    over frequencies. Coherence is also reported at the signal's own spectral peak (the breathing fundamental), with
    its own surrogate p: a non-sinusoidal rhythm makes harmonics coherent too, so the in-band maximum can sit on a
    harmonic where neither spectrum has power. Respiratory sinus arrhythmia is coherence at the breathing
    fundamental (Saul et al., Am J Physiol 1991): amplitude/frequency coupling, a different question from phase
    locking.
    """
    t, rr = clean_intervals(np.asarray(events, dtype=float))
    if len(rr) < 10:
        raise ValueError("need at least 10 clean intervals")
    t0, t1 = max(float(t[0]), 0.0), min(float(t[-1]), (len(x) - 1) / fs)
    grid = np.arange(t0, t1, 1 / rate)
    if len(grid) < 2 * seconds * rate:
        raise ValueError(f"{t1 - t0:.0f} s of overlap is too short for {seconds:g} s segments (needs {2 * seconds:g} s)")
    smooth = bandpass(np.asarray(x, dtype=float), fs, band[0] / 4, 0.4 * rate)
    sig = np.interp(grid, np.arange(len(x)) / fs, smooth)
    hr = np.interp(grid, t, 60.0 / rr)
    f, c = msc(sig, hr, rate, seconds)
    sel = (f >= band[0]) & (f <= band[1])
    if not sel.any():
        raise ValueError(f"no frequency bins in {band} Hz at {seconds:g} s segments")
    k = int(np.argmax(c[sel]))
    fp, pp = welch(sig, rate, seconds=seconds)
    ks = int(np.argmax(pp[sel]))
    min_shift = seconds if min_shift is None else min_shift
    lo, hi = int(min_shift * rate), len(grid) - int(min_shift * rate)
    if hi <= lo:
        raise ValueError(f"overlap of {t1 - t0:.0f} s is too short for surrogate shifts of {min_shift:g} s")
    lags = lo + (Chaos(seed).uniform(surrogates) * (hi - lo)).astype(int)
    null = np.array([msc(sig, np.roll(hr, int(lag)), rate, seconds)[1][sel] for lag in lags])
    peak_null, at_null = null.max(axis=1), null[:, ks]
    nper = int(round(seconds * rate))
    return {"band_hz": list(band), "segment_s": seconds, "segments": 1 + (len(grid) - nper) // max(1, nper // 2),
            "span_s": [t0, t1], "peak_hz": float(f[sel][k]), "peak_msc": float(c[sel][k]),
            "surrogate_q95": float(np.quantile(peak_null, 0.95)),
            "p": float((1 + np.sum(peak_null >= c[sel][k])) / (1 + surrogates)),
            "signal_peak_hz": float(fp[sel][ks]), "msc_at_signal_peak": float(c[sel][ks]),
            "surrogate_q95_at_signal_peak": float(np.quantile(at_null, 0.95)),
            "p_at_signal_peak": float((1 + np.sum(at_null >= c[sel][ks])) / (1 + surrogates)), "surrogates": surrogates}


# ============================================================================================ PLL

@dataclass
class PLLResult:
    frequency: np.ndarray
    locked: np.ndarray
    lock_fraction: float
    final_frequency: float


def pll_track(x: np.ndarray, fs: float, f0: float, bandwidth_hz: float = 2.0, zeta: float = 0.707,
              lock_threshold: float = 0.6) -> PLLResult:
    """Second-order type-II PLL. The phase detector is x·(−sin θ), whose mean is (A/2)·sin(φ − θ) for an input
    A·cos φ, so the gains are normalised by the input amplitude A. Locked means the low-passed in-phase product
    x·cos θ exceeds `lock_threshold` × A/2. Lock fraction and final frequency are taken over the second half."""
    x = np.asarray(x, dtype=float)
    if not 0 < f0 < fs / 2:
        raise ValueError(f"f0 = {f0} must be in (0, fs/2 = {fs / 2})")
    if not 0 < bandwidth_hz < fs / 4:
        raise ValueError(f"bandwidth {bandwidth_hz} Hz must be in (0, fs/4)")
    amp = np.sqrt(2) * np.std(x) + 1e-12
    kd = amp / 2
    wn = 2 * np.pi * bandwidth_hz
    kp, ki = 2 * zeta * wn / kd, wn ** 2 / kd
    dt = 1 / fs
    theta, integ, i_lp = 0.0, 0.0, 0.0
    alpha = 1 - math.exp(-2 * math.pi * bandwidth_hz / 4 * dt)
    freq = np.empty(len(x))
    locked = np.empty(len(x), dtype=bool)
    for k, v in enumerate(x):
        err = -v * math.sin(theta)
        integ += ki * err * dt
        w = 2 * math.pi * f0 + kp * err + integ
        i_lp += alpha * (v * math.cos(theta) - i_lp)
        locked[k] = i_lp > lock_threshold * kd
        freq[k] = w / (2 * math.pi)
        theta = (theta + w * dt) % (2 * math.pi)
    tail = slice(len(x) // 2, None)
    return PLLResult(freq, locked, float(locked[tail].mean()), float(np.mean(freq[tail])))
