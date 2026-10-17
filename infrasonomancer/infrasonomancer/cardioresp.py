"""Breath and heartbeat as two coupled phase oscillators, rendered as raw sensor signals with known ground truth.

    dφr = ωr dt + σr dW                                       breathing, autonomous
    dφh = (ωh + ε·sin(n·φr − m·φh)) dt + σh dW                heart, driven by breathing

ψ = n·φr − m·φh obeys Adler's equation dψ/dt = Δ − m·ε·sin ψ with Δ = n·ωr − m·ωh, so without noise the two lock
n:m exactly when |Δ| < m·ε: the Arnold tongue. Scenarios are parametrised by δ = Δ/(m·ε), the position across the
tongue (|δ| < 1 locked), which makes ground truth analytic. This is the phase-oscillator model of cardiorespiratory
interaction (Rosenblum et al. 1998; Kralemann et al. 2013), not a claim that real hearts follow it.

From the phases the recording is synthesised as a sensor would see it, unprocessed: a belt signal (non-sinusoidal
breath, drift, noise), an ECG (P-QRS-T at each heart cycle, baseline wander, mains hum, noise) and a PPG.
`assess` then runs the package's own chain on the raw signals (beats detected, Hilbert phase estimated) and the same
statistics on the true phases, and scores both against what the true phases did. Outside the tongue the phases
slip but stay non-uniform, with mean resultant |δ| − √(δ² − 1): coupled is not the same as locked.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from .chaos import Chaos
from .coherence import PhaseStream, stream_from_events, stream_from_signal, synchronize
from .physio import detect_beats

MODEL_DT = 0.01                                            # s, phase integration step


@dataclass(frozen=True)
class Scenario:
    n: int = 4                       # heart cycles ...
    m: int = 1                       # ... per m breaths
    breath_hz: float = 0.25
    detuning: float = 0.0            # δ: |δ| < 1 is inside the Arnold tongue
    coupling: float = 0.3            # ε, rad/s
    phase_noise: float = 0.05        # σh, rad/√s
    breath_noise: float = 0.02       # σr, rad/√s
    sensor_noise: float = 0.05       # white noise amplitude, relative to the R wave / breath / pulse
    seconds: float = 300.0
    fs: float = 250.0

    @property
    def heart_hz(self) -> float:
        """Free-running heart rate: m·ωh = n·ωr − δ·m·ε."""
        return (self.n / self.m) * self.breath_hz - self.detuning * self.coupling / (2 * math.pi)

    @property
    def locked_without_noise(self) -> bool:
        return abs(self.detuning) < 1.0

    def validate(self) -> "Scenario":
        problems = []
        if self.n < 1 or self.m < 1 or math.gcd(self.n, self.m) != 1:
            problems.append(f"n:m = {self.n}:{self.m} must be coprime positive integers")
        if not 0.05 <= self.breath_hz <= 1.0:
            problems.append(f"breath_hz {self.breath_hz} must be in [0.05, 1]")
        if not self.coupling > 0:
            problems.append("coupling must be > 0")
        if min(self.phase_noise, self.breath_noise, self.sensor_noise) < 0:
            problems.append("noise levels must be ≥ 0")
        if self.seconds < 90:
            problems.append(f"seconds {self.seconds} must be ≥ 90 (two 30 s windows plus filter edges)")
        if self.fs < 200:
            problems.append(f"fs {self.fs} must be ≥ 200 Hz for the ECG waveform")
        if not 0.5 <= self.heart_hz <= 3.5:
            problems.append(f"heart rate {60 * self.heart_hz:.0f} bpm is outside 30–210 bpm")
        if problems:
            raise ValueError("invalid scenario: " + "; ".join(problems))
        return self

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Scenario":
        return cls(**{k: type(getattr(cls(), k))(v) for k, v in d.items() if k in cls.__dataclass_fields__}).validate()


@dataclass
class Recording:
    scenario: Scenario
    t: np.ndarray                    # sensor sample times, s
    resp: np.ndarray
    ecg: np.ndarray
    ppg: np.ndarray
    beats: np.ndarray                # true heart-cycle times, s
    t_model: np.ndarray
    phi_r: np.ndarray                # true unwrapped phases on t_model
    phi_h: np.ndarray
    truth: dict = field(default_factory=dict)


def integrate(sc: Scenario, ch: Chaos) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Euler–Maruyama on MODEL_DT; returns (t, φr, φh)."""
    steps = int(round(sc.seconds / MODEL_DT)) + 1
    z = ch.normal(2 * steps).reshape(2, steps)
    u = ch.uniform(2)
    wr, wh = 2 * math.pi * sc.breath_hz, 2 * math.pi * sc.heart_hz
    sr, sh = sc.breath_noise * math.sqrt(MODEL_DT), sc.phase_noise * math.sqrt(MODEL_DT)
    pr, ph = np.empty(steps), np.empty(steps)
    pr[0], ph[0] = 2 * math.pi * u[0], 2 * math.pi * u[1]
    n, m, eps, dt = sc.n, sc.m, sc.coupling, MODEL_DT
    a, b = float(pr[0]), float(ph[0])
    zr, zh = z[0].tolist(), z[1].tolist()
    for k in range(1, steps):
        a_next = a + wr * dt + sr * zr[k]
        b = b + (wh + eps * math.sin(n * a - m * b)) * dt + sh * zh[k]
        a = a_next
        pr[k], ph[k] = a, b
    return np.arange(steps) * MODEL_DT, pr, ph


def cycle_times(t: np.ndarray, phase: np.ndarray) -> np.ndarray:
    """Times at which an unwrapped phase crosses 2πk (first crossing when noise makes it wobble)."""
    mono = np.maximum.accumulate(phase)
    k = np.arange(math.floor(mono[0] / (2 * math.pi)) + 1, math.floor(mono[-1] / (2 * math.pi)) + 1)
    idx = np.searchsorted(mono, 2 * math.pi * k)
    lo = np.clip(idx - 1, 0, len(t) - 1)
    hi = np.clip(idx, 0, len(t) - 1)
    span = np.where(mono[hi] > mono[lo], mono[hi] - mono[lo], 1.0)
    return t[lo] + (2 * math.pi * k - mono[lo]) / span * (t[hi] - t[lo])


def ecg_waveform(beats: np.ndarray, fs: float, seconds: float, noise: float, ch: Chaos) -> np.ndarray:
    """P-QRS-T as Gaussians at each beat (McSharry et al. 2003, simplified), slow amplitude change, baseline wander,
    50 Hz mains and white noise."""
    n = int(seconds * fs)
    t = np.arange(n) / fs
    x = np.zeros(n)
    waves = ((-0.20, 0.025, 0.12), (-0.035, 0.010, -0.12), (0.0, 0.009, 1.0), (0.035, 0.010, -0.25),
             (0.25, 0.045, 0.30))
    for tk in beats:
        amp = 1 + 0.2 * math.sin(2 * math.pi * 0.07 * tk)
        i0, i1 = max(0, int((tk - 0.5) * fs)), min(n, int((tk + 0.6) * fs))
        tt = t[i0:i1] - tk
        for off, sd, a in waves:
            x[i0:i1] += amp * a * np.exp(-((tt - off) ** 2) / (2 * sd * sd))
    x += 0.3 * np.sin(2 * np.pi * 0.21 * t + 0.4) + 0.15 * np.sin(2 * np.pi * 0.04 * t) \
        + 0.04 * np.sin(2 * np.pi * 50.0 * t)
    return x + 2 * noise * (ch.uniform(n) - 0.5)


def ppg_waveform(beats: np.ndarray, fs: float, seconds: float, noise: float, ch: Chaos, transit: float = 0.25) -> np.ndarray:
    n = int(seconds * fs)
    t = np.arange(n) / fs
    x = np.zeros(n)
    for tk in beats:
        i0, i1 = max(0, int((tk + transit - 0.3) * fs)), min(n, int((tk + transit + 0.9) * fs))
        tt = t[i0:i1] - tk - transit
        x[i0:i1] += np.exp(-((tt - 0.12) ** 2) / 0.0072) + 0.35 * np.exp(-((tt - 0.38) ** 2) / 0.0098)
    x += 0.3 * np.sin(2 * np.pi * 0.07 * t)
    return x + 2 * noise * (ch.uniform(n) - 0.5)


def resp_waveform(t: np.ndarray, phi_r: np.ndarray, t_model: np.ndarray, noise: float, ch: Chaos) -> np.ndarray:
    """Belt signal: a non-sinusoidal breath (second harmonic), slow drift and white noise."""
    p = np.interp(t, t_model, phi_r)
    x = np.cos(p) + 0.3 * np.cos(2 * p + 0.6) + 0.3 * np.sin(2 * np.pi * 0.013 * t + 1.0)
    return x + 2 * noise * (ch.uniform(len(t)) - 0.5)


def simulate(sc: Scenario, seed: str = "cardioresp") -> Recording:
    sc.validate()
    ch = Chaos(f"{seed}/{sorted(sc.to_dict().items())}")
    t_model, pr, ph = integrate(sc, ch)
    beats = cycle_times(t_model, ph)
    beats = beats[(beats > 0.6) & (beats < sc.seconds - 0.7)]
    t = np.arange(int(sc.seconds * sc.fs)) / sc.fs
    psi = sc.n * pr - sc.m * ph
    tail = slice(len(psi) // 10, None)
    true_index = float(abs(np.mean(np.exp(1j * psi[tail]))))
    slips = float(abs(psi[-1] - psi[len(psi) // 10]) / (2 * math.pi))
    truth = {"heart_hz": sc.heart_hz, "locked_without_noise": sc.locked_without_noise, "true_index": true_index,
             "phase_slips": slips, "beats": len(beats),
             "fixed_point_psi": math.asin(sc.detuning) if sc.locked_without_noise else None}
    return Recording(sc, t, resp_waveform(t, pr, t_model, sc.sensor_noise, ch),
                     ecg_waveform(beats, sc.fs, sc.seconds, sc.sensor_noise, ch),
                     ppg_waveform(beats, sc.fs, sc.seconds, sc.sensor_noise, ch), beats, t_model, pr, ph, truth)


def true_breath_stream(rec: Recording) -> PhaseStream:
    t, p = rec.t_model, rec.phi_r
    rate = (p[-1] - p[0]) / (2 * math.pi * (t[-1] - t[0]))
    return PhaseStream("signal", float(t[0]), float(t[-1]), float(rate), lambda q: np.interp(q, t, p), None,
                       {"source": "true phase"})


def assess(rec: Recording, surrogates: int = 99, alpha: float = 0.05, seed: str = "assess") -> dict:
    """The same synchronization analysis on the true phases (oracle) and on the raw signals (pipeline), each
    compared with what happened: the true phase difference ψ = n·φr − m·φh slipped fewer than one net cycle over
    the analysed span (locked in fact) or not. Coupling is always present in this model (ε > 0), so "interaction"
    is true by construction; locking is the question with a non-trivial answer."""
    sc = rec.scenario
    kw = dict(max_n=max(12, sc.n), max_m=max(3, sc.m), surrogates=surrogates, alpha=alpha, seed=seed)
    oracle = synchronize(true_breath_stream(rec), stream_from_events(rec.beats), **kw)
    t0, t1 = oracle["overlap_s"]
    psi = np.interp([t0, t1], rec.t_model, sc.n * rec.phi_r - sc.m * rec.phi_h)
    slips = float((psi[1] - psi[0]) / (2 * math.pi))
    out = {"truth": {"net_slips": slips, "locked": abs(slips) < 1, "span_s": [t0, t1]},
           "oracle": _brief(oracle), "pipeline": None, "pipeline_error": None}
    try:
        beats = detect_beats(rec.ecg, sc.fs, "ecg")
        breath = stream_from_signal(rec.resp, sc.fs)
        pipe = synchronize(breath, stream_from_events(beats), **kw)
        out["pipeline"] = _brief(pipe)
        out["pipeline"]["beats_detected"] = len(beats)
        out["pipeline"]["breath_band_hz"] = breath.info["band_hz"]
        j = np.clip(np.searchsorted(beats, rec.beats), 1, max(1, len(beats) - 1))
        err = np.minimum(np.abs(beats[j] - rec.beats), np.abs(beats[j - 1] - rec.beats)) if len(beats) > 1 else []
        out["pipeline"]["beat_error_ms_median"] = 1e3 * float(np.median(err)) if len(err) else None
    except ValueError as e:
        out["pipeline_error"] = str(e)
    o, p, truth = out["oracle"], out["pipeline"], out["truth"]["locked"]
    out["oracle_locked"] = o["verdict"] == "locked"
    out["pipeline_locked"] = (p["verdict"] == "locked") if p else None

    def call(decided):
        return ("failed" if decided is None else "right" if decided == truth
                else "missed lock" if truth else "false lock")

    out["oracle_call"], out["pipeline_call"] = call(out["oracle_locked"]), call(out["pipeline_locked"])
    return out


def _brief(res: dict) -> dict:
    w = res["whole_record"]
    return {"ratio": w["ratio"], "index": w["index"], "p": w["p"], "net_slips": w["net_slips"], "verdict": w["verdict"],
            "x_rate_hz": res["x_rate_hz"], "y_rate_hz": res["y_rate_hz"],
            "locked_fraction": res["windows"]["locked_fraction"], "windows_p": res["windows"]["p"]}
