"""The source texts' "dual-wavelength schema casting", reproduced exactly and measured, and the same counter-pair
structure driven by a breath–heart rhythm at a frequency that can actually be made.

The source (QuaternaryHyperspatialEngine.simulate_transceiver) builds, on t = linspace(0, 1, 10000):

    λ1 = chirp(t, fc − d → fc + d),  λ2 = chirp(t, fc + d → fc − d),  fc = 8.5 THz, d = 432 kHz
    combined = (λ1 + λ2) / 2                                  the unprocessed signal
    transmitted = fftconvolve(combined, exp(−t / 0.5 ns), 'same') · 20

Exactly, combined = cos(2π fc t) · cos(2π d (t²/T − t)) over a record of T seconds: the two counter-chirps
interfere destructively wherever d (t²/T − t) = −(1/4 + k/2). But the grid samples at 9999 Hz, so nothing above 4999.5 Hz exists in these arrays: every
"THz" value in them is an alias in the audio band, computed here exactly. The counter-pair structure itself is sound,
and `counter_pair` renders it at a real carrier, with a rhythm (the heart) setting the split instead of 432 kHz.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from fractions import Fraction

import numpy as np

from .analysis import dominant_frequency
from .coherence import analytic


@dataclass(frozen=True)
class DualCast:
    carrier: float = 8.5e12          # Hz, the source's "sazer carrier"
    deviation: float = 432e3         # Hz
    samples: int = 10000
    duration: float = 1.0            # s
    data_rate: float = 20e9          # the source multiplies by data_rate / 1e9
    rc_tau: float = 5e-10            # s

    @property
    def fs(self) -> float:
        return (self.samples - 1) / self.duration

    def validate(self) -> "DualCast":
        if self.samples < 16 or not self.duration > 0 or self.deviation < 0 or self.carrier <= self.deviation:
            raise ValueError("need samples ≥ 16, duration > 0, 0 ≤ deviation < carrier")
        return self


def chirp_linear(t: np.ndarray, f0: float, f1: float, t1: float) -> np.ndarray:
    """cos(2π(f0·t + (f1 − f0)·t² / (2·t1))): scipy.signal.chirp(method='linear', phi=0), evaluated in float64."""
    return np.cos(2 * np.pi * (f0 * t + (f1 - f0) / (2 * t1) * t * t))


def chirp_cycles_exact(f0: float, f1: float, t1: float, duration: float, samples: int) -> np.ndarray:
    """Fractional cycles of the same chirp at t_k = duration·k/(samples − 1), in exact rational arithmetic, so the
    phase of an 8.5 THz chirp is not lost to float rounding (2π·8.5e12·t has an ulp of ~0.008 rad)."""
    a, b = Fraction(f0), (Fraction(f1) - Fraction(f0)) / (2 * Fraction(t1))
    step = Fraction(duration) / (samples - 1)
    out = np.empty(samples)
    for k in range(samples):
        t = step * k
        c = a * t + b * t * t
        out[k] = float(c - math.floor(c))
    return out


def cast(dc: DualCast = DualCast()) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(t, λ1, λ2, combined) computed as the source computes them (float64 on linspace)."""
    dc.validate()
    t = np.linspace(0, dc.duration, dc.samples)
    l1 = chirp_linear(t, dc.carrier - dc.deviation, dc.carrier + dc.deviation, dc.duration)
    l2 = chirp_linear(t, dc.carrier + dc.deviation, dc.carrier - dc.deviation, dc.duration)
    return t, l1, l2, (l1 + l2) / 2


def cast_exact(dc: DualCast = DualCast()) -> tuple[np.ndarray, np.ndarray]:
    """(λ1, λ2) with exact phases."""
    dc.validate()
    c1 = chirp_cycles_exact(dc.carrier - dc.deviation, dc.carrier + dc.deviation, dc.duration, dc.duration, dc.samples)
    c2 = chirp_cycles_exact(dc.carrier + dc.deviation, dc.carrier - dc.deviation, dc.duration, dc.duration, dc.samples)
    return np.cos(2 * np.pi * c1), np.cos(2 * np.pi * c2)


def convolve_same(a: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Linear convolution by FFT, central part of a's length: scipy.signal.fftconvolve(a, v, mode='same')."""
    n = len(a) + len(v) - 1
    size = 1 << (n - 1).bit_length()
    full = np.fft.irfft(np.fft.rfft(a, size) * np.fft.rfft(v, size), size)[:n]
    start = (len(v) - 1) // 2
    return full[start:start + len(a)]


def transmit(dc: DualCast, combined: np.ndarray) -> np.ndarray:
    t = np.linspace(0, dc.duration, dc.samples)
    return convolve_same(combined, np.exp(-t / dc.rc_tau)) * (dc.data_rate / 1e9)


def alias_frequency(f: float, fs: float) -> float:
    """The frequency in [0, fs/2] that a sampled tone at f is indistinguishable from (exact for float inputs)."""
    r = math.fmod(abs(f), fs)
    return min(r, fs - r)


def analyse(dc: DualCast = DualCast()) -> dict:
    """What the source's arrays actually contain."""
    t, l1, l2, combined = cast(dc)
    e1, e2 = cast_exact(dc)
    fs, d, T = dc.fs, dc.deviation, dc.duration
    exact_combined = (e1 + e2) / 2
    identity = np.cos(2 * np.pi * chirp_cycles_exact(dc.carrier, dc.carrier, T, T, dc.samples)) \
        * np.cos(2 * np.pi * d * (t ** 2 / T - t))
    rc = np.exp(-t / dc.rc_tau)
    shift = (len(rc) - 1) // 2
    tx = transmit(dc, combined)
    gain = dc.data_rate / 1e9
    nonzero = int(np.sum(rc > 0))
    p = np.abs(np.fft.rfft(combined * np.hanning(len(combined)))) ** 2
    flatness = float(np.exp(np.mean(np.log(p[1:] + 1e-300))) / np.mean(p[1:]))
    half_window = min(T / 2, fs * T / (4 * d)) if d > 0 else T / 2       # where the beat d·|2t/T − 1| < fs/2
    return {
        "source": asdict(dc), "sample_rate_hz": fs, "nyquist_hz": fs / 2,
        "carrier_alias_hz": alias_frequency(dc.carrier, fs),
        "band_edge_aliases_hz": [alias_frequency(dc.carrier - d, fs), alias_frequency(dc.carrier + d, fs)],
        "nyquist_folds_per_chirp": 2 * d / (fs / 2),
        "envelope_identity_max_error": float(np.max(np.abs(exact_combined - identity))),
        "float_vs_exact_max_sample_error": float(max(np.abs(l1 - e1).max(), np.abs(l2 - e2).max())),
        "destructive_nulls_in_record": int(2 * math.floor(d * T / 2 + 0.5)),
        "resolved_window_s": [T / 2 - half_window, T / 2 + half_window],
        "resolved_samples": int(2 * half_window * fs),
        "spectral_flatness": flatness,
        "dominant_hz": dominant_frequency(combined, fs, 1.0),
        "rc_filter": {"nonzero_kernel_samples": nonzero, "acts_as": "a unit impulse" if nonzero == 1 else "a filter",
                      "same_mode_shift_samples": shift, "gain": gain,
                      "transmitted_equals_shifted_combined": bool(nonzero == 1 and np.allclose(
                          tx[:len(tx) - shift], gain * combined[shift:], atol=1e-9 * max(1.0, gain))),
                      "samples_lost": shift},
    }


# ============================================================================================ counter-pair render

def counter_pair(t_phase: np.ndarray, phi_slow: np.ndarray, phi_fast: np.ndarray, carrier_hz: float, sr: int,
                 depth: float = 0.35) -> np.ndarray:
    """The dual cast at a real carrier: L = gL·cos(Φ − φ_fast/2), R = gR·cos(Φ + φ_fast/2), Φ = 2π·carrier·t.

    L and R sit at carrier ∓ f_fast/2 (the counter-chirp pair, its split now set by the fast rhythm), and their sum
    is 2·cos Φ·cos(φ_fast/2): it cancels destructively once per fast cycle, at φ_fast = π (mod 2π). The slow
    rhythm is the antiphase stereo pulse gL = 1 − D(1 − cos φ_slow)/2, gR = 1 − D(1 + cos φ_slow)/2, which leaves
    a residual D·|cos φ_slow|/2 in each null: null depth spells out the slow phase at every fast cycle, a
    synchrogram you can hear. Linear output stage (one gain for both channels), so the identities hold exactly.
    """
    if not 0 < carrier_hz < sr / 2:
        raise ValueError(f"carrier {carrier_hz} Hz must lie in (0, {sr / 2}) at {sr} Hz")
    if not 0 <= depth < 1:
        raise ValueError(f"depth must be in [0, 1), got {depth}")
    n = int(round((t_phase[-1] - t_phase[0]) * sr))
    t = t_phase[0] + np.arange(n) / sr
    slow, fast = np.interp(t, t_phase, phi_slow), np.interp(t, t_phase, phi_fast)
    carrier = 2 * np.pi * carrier_hz * (t - t_phase[0])
    g_left, g_right = 1 - depth * (0.5 - 0.5 * np.cos(slow)), 1 - depth * (0.5 + 0.5 * np.cos(slow))
    stereo = np.stack([g_left * np.cos(carrier - fast / 2), g_right * np.cos(carrier + fast / 2)], axis=1)
    return 0.89 * stereo / np.max(np.abs(stereo))


def mono_envelope(slow: np.ndarray, fast: np.ndarray, depth: float) -> np.ndarray:
    """Closed-form envelope of (L + R)/2 before the output gain: ½·√((2 − D)² cos²(φf/2) + D² cos²(φs) sin²(φf/2))."""
    return 0.5 * np.sqrt((2 - depth) ** 2 * np.cos(fast / 2) ** 2 + depth ** 2 * np.cos(slow) ** 2 * np.sin(fast / 2) ** 2)


def null_analysis(stereo: np.ndarray, sr: int, t_phase: np.ndarray, phi_slow: np.ndarray, phi_fast: np.ndarray,
                  n: int, depth: float = 0.35) -> dict:
    """Measured mono nulls (Hilbert envelope of (L + R)/2) against the closed form `mono_envelope`.

    Nulls sit at the fast rhythm's mid-cycle, φf = π + 2πk, with depth D·|cos φs| / (2 − D) relative to the crest;
    the changing slow phase moves each null off mid-cycle by up to D²·|cos φs·dφs/dt| / ((dφf/dt / 2)·((2 − D)² −
    D²)), a few ms at breathing rates (reported as the closed form's own offset, not as error). Depth errors are scored
    where the prediction is above −40 dB; deeper nulls reach the analytic envelope's numerical floor.
    stroboscopic_lock_index = |⟨exp(i·n·φs)⟩| over the nulls: 1 when the slow phase repeats every n fast cycles.
    """
    mono = stereo.mean(axis=1)
    env = np.abs(analytic(mono))
    t = t_phase[0] + np.arange(len(mono)) / sr
    slow, fast = np.interp(t, t_phase, phi_slow), np.interp(t, t_phase, phi_fast)
    pred = mono_envelope(slow, fast, depth)
    crest_pred, crest = (2 - depth) / 2, np.percentile(env, 99.5)
    k = np.arange(np.ceil((fast[0] - np.pi) / (2 * np.pi)), np.floor((fast[-1] - np.pi) / (2 * np.pi)) + 1)
    t_mid = np.interp(np.pi + 2 * np.pi * k, phi_fast, t_phase)
    t_mid = t_mid[(t_mid > t[0] + 0.5) & (t_mid < t[-1] - 0.5)]
    half = int(0.15 * sr)
    measured, predicted, timing, offset, slow_at = [], [], [], [], []
    for tm in t_mid:
        c = int(round((tm - t[0]) * sr))
        w = slice(c - half, c + half)
        jm, jp = c - half + int(np.argmin(env[w])), c - half + int(np.argmin(pred[w]))
        measured.append(env[jm] / crest)
        predicted.append(pred[jp] / crest_pred)
        timing.append((jm - jp) / sr)
        offset.append(t[jp] - tm)
        slow_at.append(slow[jp])
    measured, predicted = np.array(measured), np.array(predicted)
    db = lambda v: 20 * np.log10(np.maximum(v, 1e-6))                   # noqa: E731
    scored = predicted > 0.01
    return {
        "nulls": len(t_mid), "rate_hz": float((len(t_mid) - 1) / (t_mid[-1] - t_mid[0])) if len(t_mid) > 1 else 0.0,
        "timing_error_ms": {"median_abs": 1e3 * float(np.median(np.abs(timing))),
                            "max_abs": 1e3 * float(np.max(np.abs(timing)))},
        "null_offset_from_mid_cycle_ms": {"max_abs": 1e3 * float(np.max(np.abs(offset)))},
        "depth_db": {"predicted_mean": float(np.mean(db(predicted))), "measured_mean": float(np.mean(db(measured))),
                     "max_abs_error_db": float(np.max(np.abs(db(measured) - db(predicted))[scored], initial=0.0)),
                     "scored_nulls": int(scored.sum())},
        "stroboscopic_lock_index": float(abs(np.mean(np.exp(1j * n * np.array(slow_at))))),
        "mono_to_stereo_energy_db": float(10 * np.log10(np.mean(mono ** 2) / np.mean(stereo ** 2))),
        "_depths": {"t_s": t_mid, "predicted": predicted, "measured": measured},
    }


def null_offset_for_path(path_difference_m: float, carrier_hz: float, speed_of_sound: float = 343.0) -> float:
    """In a room the two channels reach a listener with a path difference; the beat still nulls once per fast cycle,
    but shifted by this fraction of a cycle (π·fc·τ mod π, as a fraction of π). Over headphones the channels never
    sum; above ~1.5 kHz no binaural beat is heard either."""
    return math.fmod(math.pi * carrier_hz * path_difference_m / speed_of_sound, math.pi) / math.pi
