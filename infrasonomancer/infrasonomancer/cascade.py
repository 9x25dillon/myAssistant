"""Recoherence cascade: voices that beat, lock, and by locking set off the next, higher generation.

    generators g_1 … g_G (default 2 and 3) ─▶ lattice of voices f = f0 · Π g_k^e_k with Σ e_k ≤ depth
    each voice is coupled to one parent (the voice one generator below it whose coincident partials have the lowest
    order) through those partials; its other parents are measured, not forced: forcing two at once frustrates the
    loop (each parent locks at its own phase offset, and the two pulls can cancel), whereas a spanning tree of locks
    makes every frequency ratio exact, so the other relations stop beating by themselves
    coupling adapts: a coupled pair still beating after its ramp strengthens (×e per ramp_s, up to a stability cap),
    so when a newborn branch pulls an older voice off its lock through back-reaction, that lock recovers
    a voice is born detuned, so one of its partials beats against one of its parent's at Δ/2π Hz
    the coupling ramps up; once (1 + ε)K > |Δ| the beat slows as √(Δ² − (1 + ε)²K²)/2π and stops: recoherence
    a voice is born once every voice it grows from has stayed locked for `dwell_s`: the cascade climbs and branches,
    and branches that meet (2·3 = 3·2) merge into one voice that must agree with both

Why 2 and 3 by default: every voice is then a harmonic of f0 (1, 2, 3, 4, 6, 8, 9, 12 …), so the cascade grows the
root's own overtone series, wide in the bass and closing up higher, and once locked the voices' partials coincide
instead of crowding each other. Measured over four seeds, its end-state sensory dissonance is 0.034–0.046 against
0.123–0.149 for 2 and 3/2 (the same pitch classes, stacked as fifths, whose low voices share critical bands).

Exact phase bookkeeping. With g = p/q in lowest terms, q·f_child = p·f_parent exactly, so the child's q-th partial and
the parent's p-th partial coincide. Write each phase as θ_i = 2π f_i t + φ_i: the fast parts of ψ = q θ_c − p θ_p
cancel identically, and only the slow deviations are integrated (RK4 at a control rate),

    dφ_c/dt = 2π δ_c − (K/q) sin ψ,    dφ_p/dt = 2π δ_p + (ε K/p) sin ψ,    so    dψ/dt = Δ − (1 + ε) K sin ψ

with δ the voice's detuning in Hz and Δ = 2π (q δ_c − p δ_p): Adler's equation, as in cardioresp. Audio is synthesised
from θ, so what is measured below is the phase the sound is made of, not a description of it.

Measured on every run (cascade_timeline, cascade_report): voices sounding; phase coherence of the coupled pairs; the
beat rate of every pair; a beat index weighted like fluctuation strength (peak near 4 Hz, zero when still); sensory
dissonance of the whole spectrum (Plomp & Levelt 1965, Sethares 1993 parametrisation); spectral centroid. Whether
any of it relaxes or focuses a listener is a hypothesis, stated as one in the report.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import asdict, dataclass, field, replace
from fractions import Fraction

import numpy as np

from .chaos import Chaos

TWO_PI = 2.0 * math.pi
_PRIMES = (2, 3, 5, 7, 11, 13)
_K_FLOOR_HZ = 0.05                       # a pair detuned by less than this is still held, at this strength


@dataclass(frozen=True)
class CascadeConfig:
    seed: str = "recoherence"
    generators: tuple[str, ...] = ("2", "3")
    depth: int = 6
    f0: float | None = None              # Hz; None: drawn from the seed in A1–E2 (55–82.4 Hz)
    f_max: float = 4000.0                # highest fundamental kept
    min_cents: float = 150.0             # consonance guard: skip a voice this close to one already there (0: off)
    beat_hz: float = 0.6                 # |detuning| bound per voice; a p/q pair starts beating at ≤ (p + q)·beat_hz
    coupling: float = 1.8                # (1 + ε)·K / |Δ| per pair at birth: > 1 locks; it then adapts (see adapt)
    adapt: bool = True                   # strengthen a coupled pair that still beats after its ramp
    backreaction: float = 0.25           # ε: how hard a child pulls its parent back
    ramp_s: float = 8.0                  # time constant of a pair's coupling ramp after the child is born
    dwell_s: float = 3.0                 # locked to every parent this long → coherent → children are born
    lock_hz: float = 0.02                # a pair beating slower than this counts as locked
    stagger_s: float = 3.0               # sibling births spread over up to this long
    attack_s: float = 8.0                # raised-cosine fade-in of a newborn voice
    harmonics: int = 6
    rolloff: float = 1.5                 # partial k has amplitude k^−rolloff
    tilt_db_oct: float = -4.0            # voice level per octave above f0
    breath_hz: float = 0.1               # slow swell to breathe with; 0 turns it off
    breath_depth: float = 0.12
    tail_s: float = 45.0                 # held after the last voice is coherent …
    fade_s: float = 15.0                 # … then faded out
    max_seconds: float = 300.0
    control_hz: float = 100.0

    def validate(self) -> "CascadeConfig":
        gens = parse_generators(self.generators)
        problems = []
        if not 1 <= self.depth <= 8:
            problems.append(f"depth must be in [1, 8], got {self.depth}")
        if self.f0 is not None and not 20.0 <= self.f0 <= 1000.0:
            problems.append(f"f0 must be in [20, 1000] Hz, got {self.f0}")
        need = max(max(g.numerator, g.denominator) for g in gens)
        if not need <= self.harmonics <= 32:
            problems.append(f"harmonics must be in [{need}, 32]: coupling acts through partial {need} of "
                            f"{'/'.join(map(str, gens))}, got {self.harmonics}")
        for name, lo, hi in (("beat_hz", 0.0, 5.0), ("coupling", 0.0, 10.0), ("backreaction", 0.0, 1.0),
                             ("lock_hz", 1e-4, 1.0), ("breath_depth", 0.0, 0.5), ("rolloff", 0.0, 4.0)):
            v = getattr(self, name)
            if not lo <= v <= hi:
                problems.append(f"{name} must be in [{lo}, {hi}], got {v}")
        for name in ("ramp_s", "attack_s", "control_hz", "max_seconds", "f_max"):
            if not getattr(self, name) > 0:
                problems.append(f"{name} must be > 0, got {getattr(self, name)}")
        for name in ("dwell_s", "stagger_s", "tail_s", "fade_s", "breath_hz", "min_cents"):
            if not getattr(self, name) >= 0:
                problems.append(f"{name} must be ≥ 0, got {getattr(self, name)}")
        fastest = max(g.numerator + g.denominator for g in gens) * self.beat_hz
        if fastest > self.control_hz / 10:
            problems.append(f"beats up to {fastest:g} Hz need control_hz ≥ {10 * fastest:g}")
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CascadeConfig":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        if "generators" in known:
            known["generators"] = tuple(str(g) for g in known["generators"])
        return cls(**known).validate()


def parse_generators(gens) -> list[Fraction]:
    """Ratios > 1 with numerator and denominator ≤ 16, multiplicatively independent (else voices would coincide)."""
    out = []
    for g in gens:
        try:
            r = Fraction(str(g).strip())
        except (ValueError, ZeroDivisionError):
            raise ValueError(f"generator {g!r} is not a ratio such as 3/2") from None
        if r <= 1 or r.numerator > 16 or r.denominator > 16:
            raise ValueError(f"generator {r} must be > 1 with numerator and denominator ≤ 16")
        out.append(r)
    if not 1 <= len(out) <= 4:
        raise ValueError(f"give 1 to 4 generators, got {len(out)}")

    def exponents(k: int) -> list[int]:
        e = []
        for pr in _PRIMES:
            c = 0
            while k % pr == 0:
                k //= pr
                c += 1
            e.append(c)
        if k != 1:
            raise ValueError("generator terms must factor over primes ≤ 13")
        return e

    m = np.array([np.subtract(exponents(r.numerator), exponents(r.denominator)) for r in out], dtype=float)
    if np.linalg.matrix_rank(m) < len(out):
        raise ValueError(f"generators {', '.join(map(str, out))} are not independent: two paths would reach one pitch")
    return out


@dataclass(frozen=True)
class Voice:
    index: int
    exponents: tuple[int, ...]
    ratio: Fraction                     # to f0
    freq: float                         # nominal, Hz
    depth: int
    pan: float                          # −1 left … +1 right
    amp: float
    detune_hz: float
    parents: tuple[int, ...]


@dataclass(frozen=True)
class Pair:
    child: int
    parent: int
    p: int                              # the parent's coincident partial
    q: int                              # the child's coincident partial
    delta: float                        # Δ, rad/s: against the parent's frequency when the child is born
    k_max: float                        # K, rad/s, sized from that Δ (0: not coupled, or the child was never born)
    coupled: bool = True                # False: a second parent, checked for beating but not pulled toward


@dataclass
class Cascade:
    config: CascadeConfig
    f0: float
    generators: list[Fraction]
    voices: list[Voice]
    pairs: list[Pair]
    t: np.ndarray                       # control times, s
    phi: np.ndarray                     # (steps, voices) slow phase deviations, rad
    dphi: np.ndarray                    # (steps, voices) their derivatives, rad/s
    born: np.ndarray                    # birth time per voice (inf: never)
    coherent: np.ndarray                # first time locked to every parent for dwell_s (inf: never)
    complete_s: float | None            # every voice coherent
    seconds: float
    meta: dict = field(default_factory=dict)

    def psi(self, k: int) -> np.ndarray:
        e = self.pairs[k]
        return e.q * self.phi[:, e.child] - e.p * self.phi[:, e.parent]

    def dpsi(self, k: int) -> np.ndarray:
        e = self.pairs[k]
        return e.q * self.dphi[:, e.child] - e.p * self.dphi[:, e.parent]


def _lattice(gens: list[Fraction], cfg: CascadeConfig, f0: float, ch: Chaos) -> tuple[list[Voice], list[Pair]]:
    g = len(gens)
    exps = [e for e in itertools.product(range(cfg.depth + 1), repeat=g) if sum(e) <= cfg.depth]
    ratio = {e: math.prod((r ** k for r, k in zip(gens, e)), start=Fraction(1)) for e in exps}
    kept: list[tuple[int, ...]] = []
    for e in sorted((e for e in exps if f0 * ratio[e] <= cfg.f_max), key=lambda e: (sum(e), ratio[e])):
        if any(e[k] and tuple(x - (j == k) for j, x in enumerate(e)) not in kept for k in range(g)):
            continue                                                     # a parent was skipped: no way to be born
        cents = [abs(1200 * math.log2(ratio[e] / ratio[o])) for o in kept]
        if cents and min(cents) < cfg.min_cents:
            continue                                                     # e.g. 243/32 against 8: a 90-cent limma
        kept.append(e)
    exps = kept
    index = {e: i for i, e in enumerate(exps)}
    per_depth = {d: sum(1 for e in exps if sum(e) == d) for d in range(cfg.depth + 1)}
    detune = (2.0 * ch.uniform(len(exps)) - 1.0) * cfg.beat_hz
    detune[0] = 0.0                                                      # the root is the reference
    direction = np.linspace(-1.0, 1.0, g) if g > 1 else np.zeros(1)      # each generator leans one way
    voices = []
    for i, e in enumerate(exps):
        d = sum(e)
        f = f0 * float(ratio[e])
        pan = 0.0 if d == 0 else 0.8 * float(np.dot(direction, e)) / d
        amp = 10 ** (cfg.tilt_db_oct * math.log2(f / f0) / 20) / math.sqrt(per_depth[d])
        parents = tuple(index[tuple(x - (j == k) for j, x in enumerate(e))] for k in range(g) if e[k] > 0)
        voices.append(Voice(i, e, ratio[e], f, d, pan, amp, float(detune[i]), parents))
    pairs = []
    for v in voices:
        ks = [k for k in range(g) if v.exponents[k] > 0]
        primary = min(ks, key=lambda k: (gens[k].numerator + gens[k].denominator, k)) if ks else None
        for k in ks:
            par = index[tuple(x - (j == k) for j, x in enumerate(v.exponents))]
            p, q = gens[k].numerator, gens[k].denominator
            delta = TWO_PI * (q * v.detune_hz - p * voices[par].detune_hz)
            pairs.append(Pair(v.index, par, p, q, delta, 0.0, k == primary))   # nominal Δ; recohere re-measures it
    return voices, pairs


def recohere(cfg: CascadeConfig = CascadeConfig()) -> Cascade:
    """Integrate the cascade until every voice is coherent (then tail_s + fade_s more), or until max_seconds."""
    cfg = cfg.validate()
    gens = parse_generators(cfg.generators)
    ch = Chaos(cfg.seed + "/cascade")
    f0 = cfg.f0 if cfg.f0 is not None else 55.0 * 2 ** (7 / 12 * ch.scalar())
    voices, pairs = _lattice(gens, cfg, f0, ch)
    n = len(voices)
    stagger = cfg.stagger_s * ch.uniform(n)
    c = np.array([e.child for e in pairs], dtype=np.int64)
    par = np.array([e.parent for e in pairs], dtype=np.int64)
    p = np.array([e.p for e in pairs], dtype=float)
    q = np.array([e.q for e in pairs], dtype=float)
    kmax = np.zeros(len(pairs))                                          # sized when the child is born
    delta = np.array([e.delta for e in pairs])
    armed = np.zeros(len(pairs), dtype=bool)
    coupled = np.array([e.coupled for e in pairs], dtype=bool)
    w0 = TWO_PI * np.array([v.detune_hz for v in voices])
    eps, ramp = cfg.backreaction, cfg.ramp_s
    k_cap = 0.5 * cfg.control_hz / (1.0 + eps)                           # (1 + ε)·K·dt ≤ 0.5: RK4 stays accurate
    parents = [np.array(v.parents, dtype=np.int64) for v in voices]

    born = np.full(n, np.inf)
    coherent = np.full(n, np.inf)
    born[0] = coherent[0] = 0.0
    locked_since = np.full(n, np.inf)
    on = np.full(len(pairs), np.inf)                                     # pair coupling starts at the child's birth

    def deriv(phi: np.ndarray, t: float) -> np.ndarray:
        d = w0.copy()
        if len(pairs):
            k = kmax * (1.0 - np.exp(-np.maximum(t - on, 0.0) / ramp))   # 0 until the pair is on
            s = k * np.sin(q * phi[c] - p * phi[par])
            d -= np.bincount(c, weights=s / q, minlength=n)
            d += np.bincount(par, weights=eps * s / p, minlength=n)
        return d

    dt = 1.0 / cfg.control_hz
    limit = int(round(cfg.max_seconds * cfg.control_hz))
    phi = np.zeros(n)
    hist_phi = np.empty((limit + 1, n))
    hist_dphi = np.empty((limit + 1, n))
    end = limit
    complete = None
    changed = True
    s = 0
    while True:
        t = s * dt
        if changed:                                                      # every parent coherent → schedule the birth
            for i in np.flatnonzero(np.isinf(born)):
                if np.all(np.isfinite(coherent[parents[i]])):
                    born[i] = float(coherent[parents[i]].max()) + stagger[i]
            on = born[c]
            changed = False
        todo = ~armed & (on <= t)
        if todo.any():
            # A parent that has locked no longer runs at its own detuning, so the child's Δ is measured against the
            # parent's frequency now; K sized from the nominal detunings can fall short of it and never lock.
            rate = hist_dphi[s - 1] if s else w0
            delta[todo] = q[todo] * rate[c[todo]] - p[todo] * rate[par[todo]]
            kmax[todo] = coupled[todo] * np.minimum(
                cfg.coupling * np.maximum(np.abs(delta[todo]), TWO_PI * _K_FLOOR_HZ) / (1 + eps), k_cap)
            armed |= todo
        k1 = deriv(phi, t)
        hist_phi[s], hist_dphi[s] = phi, k1
        if len(pairs):
            active = on <= t
            beat = np.abs(q * k1[c] - p * k1[par]) / TWO_PI
            unlocked = np.bincount(c, weights=(~(active & (beat < cfg.lock_hz))).astype(float), minlength=n)
            ok = (born <= t) & (unlocked == 0)
            ok[0] = True
            locked_since[ok & np.isinf(locked_since)] = t
            locked_since[~ok] = np.inf
            newly = np.isinf(coherent) & (t - locked_since >= cfg.dwell_s - 1e-9)
            coherent[newly] = t
            changed = bool(newly.any())
            if cfg.adapt:
                grow = coupled & armed & (t - on > ramp) & (beat >= cfg.lock_hz)
                kmax[grow] = np.minimum(kmax[grow] * math.exp(dt / ramp), k_cap)
        if complete is None and np.all(np.isfinite(coherent)):
            complete = t
            end = min(limit, s + int(round((cfg.tail_s + cfg.fade_s) * cfg.control_hz)))
        if s >= end:
            break
        k2 = deriv(phi + 0.5 * dt * k1, t + 0.5 * dt)
        k3 = deriv(phi + 0.5 * dt * k2, t + 0.5 * dt)
        k4 = deriv(phi + dt * k3, t + dt)
        phi = phi + dt / 6.0 * (k1 + 2 * k2 + 2 * k3 + k4)
        s += 1
    steps = s + 1
    pairs = [replace(e, delta=float(delta[k]), k_max=float(kmax[k])) for k, e in enumerate(pairs)]
    return Cascade(cfg, f0, gens, voices, pairs, np.arange(steps) * dt, hist_phi[:steps].copy(),
                   hist_dphi[:steps].copy(), born, coherent, complete, steps * dt,
                   {"stagger_s": stagger.tolist()})


def _partials(cfg: CascadeConfig) -> np.ndarray:
    w = np.arange(1, cfg.harmonics + 1, dtype=float) ** -cfg.rolloff
    return w / math.sqrt(float(np.sum(w ** 2)))


def _attack(t: np.ndarray, born: float, attack: float) -> np.ndarray:
    x = np.clip((t - born) / attack, 0.0, 1.0)
    return 0.5 - 0.5 * np.cos(np.pi * x)


def master_gain(cfg: CascadeConfig, seconds: float, t: np.ndarray) -> np.ndarray:
    """The slow breathing swell times the closing fade."""
    g = 1.0 - cfg.breath_depth * (0.5 - 0.5 * np.cos(TWO_PI * cfg.breath_hz * t)) if cfg.breath_hz > 0 else \
        np.ones_like(t)
    if cfg.fade_s > 0:
        x = np.clip((seconds - t) / cfg.fade_s, 0.0, 1.0)
        g = g * (0.5 - 0.5 * np.cos(np.pi * x))
    return g


def render_cascade(c: Cascade, sr: int = 22050, stereo: bool = True, block: int = 1 << 17) -> np.ndarray:
    """Mono (n,) or stereo (n, 2), peak −1 dBFS, no saturation. Each voice is Σ_k w_k sin(k θ) with
    θ = 2π f t + φ(t); partials at or above 0.45·sr are left out. Equal-power panning."""
    if sr < 8000:
        raise ValueError(f"sample rate {sr} is below 8000 Hz")
    cfg = c.config
    n = int(c.seconds * sr)
    out = np.zeros((n, 2)) if stereo else np.zeros(n)
    weights = _partials(cfg)
    for v in c.voices:
        if not c.born[v.index] < c.seconds:
            continue
        i0 = int(math.ceil(c.born[v.index] * sr))
        kmax = int(min(cfg.harmonics, math.ceil(0.45 * sr / v.freq) - 1))
        if kmax < 1:
            continue
        gl, gr = math.cos((v.pan + 1) * math.pi / 4), math.sin((v.pan + 1) * math.pi / 4)
        for a in range(i0, n, block):
            t = np.arange(a, min(n, a + block)) / sr
            theta = TWO_PI * v.freq * t + np.interp(t, c.t, c.phi[:, v.index])
            s1, c2 = np.sin(theta), 2.0 * np.cos(theta)
            prev, cur = np.zeros_like(s1), s1
            tone = weights[0] * s1
            for k in range(2, kmax + 1):                                  # sin kθ = 2cos θ · sin (k−1)θ − sin (k−2)θ
                prev, cur = cur, c2 * cur - prev
                tone += weights[k - 1] * cur
            sig = v.amp * _attack(t, c.born[v.index], cfg.attack_s) * tone
            if stereo:
                out[a:a + len(t), 0] += gl * sig
                out[a:a + len(t), 1] += gr * sig
            else:
                out[a:a + len(t)] += sig
    g = master_gain(cfg, c.seconds, np.arange(n) / sr)
    out *= g[:, None] if stereo else g
    peak = float(np.max(np.abs(out))) if n else 0.0
    return 0.89 * out / peak if peak > 0 else out


def fluctuation_weight(f_hz) -> np.ndarray:
    """1 at 4 Hz, → 0 at 0 Hz and at fast rates: the band-pass shape of fluctuation strength (Zwicker & Fastl)."""
    f = np.abs(np.asarray(f_hz, dtype=float))
    with np.errstate(divide="ignore"):
        return np.where(f > 0, 2.0 / (f / 4.0 + 4.0 / np.where(f > 0, f, 1.0)), 0.0)


def sethares_dissonance(freqs, amps) -> float:
    """Sensory dissonance of a spectrum: Plomp & Levelt's curve as parametrised by Sethares (1993, 2005)."""
    f = np.asarray(freqs, dtype=float)
    a = np.asarray(amps, dtype=float)
    if len(f) < 2:
        return 0.0
    i, j = np.triu_indices(len(f), 1)
    s = 0.24 / (0.0207 * np.minimum(f[i], f[j]) + 18.96)
    d = np.abs(f[i] - f[j])
    return float(np.sum(np.minimum(a[i], a[j]) * (np.exp(-3.51 * s * d) - np.exp(-5.75 * s * d))))


def cascade_timeline(c: Cascade, sr: int = 22050, hop: float = 0.25, window: float = 2.0) -> dict[str, np.ndarray]:
    """Per frame: voices sounding; coherence (amplitude-weighted phase-locking value of the coupled pairs over the
    last `window` s); beat index (amplitude-weighted fluctuation weight of each pair's beat rate); the fastest beat;
    sensory dissonance per unit amplitude (Sethares sum ÷ Σa, so a fuller chord does not count as rougher merely for
    having more partials); and the power-weighted spectral centroid of the partials actually synthesised at `sr`.
    Partials at one exact frequency ratio (child partial q = parent partial p, and every other coincidence) are one
    partial: their amplitudes add as phasors, as they do in the sound, so a locked chord is not scored as crowded."""
    cfg = c.config
    ctrl = cfg.control_hz
    frames = np.arange(0.0, c.seconds, hop)
    w_partial = _partials(cfg)
    env = _attack(frames[:, None], c.born[None, :], cfg.attack_s)
    amps = np.array([v.amp for v in c.voices])
    psi = np.stack([c.psi(k) for k in range(len(c.pairs))], axis=1) if c.pairs else np.zeros((len(c.t), 0))
    dpsi = np.stack([c.dpsi(k) for k in range(len(c.pairs))], axis=1) if c.pairs else np.zeros((len(c.t), 0))
    on = np.array([c.born[e.child] for e in c.pairs])
    pc = np.array([e.child for e in c.pairs], dtype=np.int64)
    pp = np.array([e.parent for e in c.pairs], dtype=np.int64)
    wq = np.array([w_partial[e.q - 1] for e in c.pairs])
    wp = np.array([w_partial[e.p - 1] for e in c.pairs])
    W, H = max(1, int(round(window * ctrl))), max(1, int(round(hop * ctrl)))
    k = np.arange(1, cfg.harmonics + 1, dtype=float)
    keys: dict[Fraction, int] = {}
    group = np.array([[keys.setdefault(v.ratio * h, len(keys)) for h in range(1, cfg.harmonics + 1)]
                      for v in c.voices], dtype=np.int64)
    cols = {name: np.full(len(frames), np.nan) for name in
            ("voices", "coherence", "beat_index", "max_beat_hz", "dissonance", "centroid_hz")}
    for fi, t in enumerate(frames):
        j = min(len(c.t) - 1, int(round(t * ctrl)))
        sounding = env[fi] > 0
        cols["voices"][fi] = int(np.sum(c.born <= t))
        if len(c.pairs):
            act = on <= t
            w = env[fi, pc] * amps[pc] * wq * env[fi, pp] * amps[pp] * wp * act
            if w.sum() > 0:
                seg = psi[max(0, j - W):j + 1]
                plv = np.abs(np.mean(np.exp(1j * seg), axis=0))
                beat = np.mean(np.abs(dpsi[max(0, j - H):j + 1]), axis=0) / TWO_PI
                cols["coherence"][fi] = float(np.sum(w * plv) / w.sum())
                cols["beat_index"][fi] = float(np.sum(w * fluctuation_weight(beat)) / w.sum())
                cols["max_beat_hz"][fi] = float(beat[w > 1e-6 * w.max()].max())
        if sounding.any():
            f_inst = np.array([v.freq for v in c.voices])[sounding] + c.dphi[j, sounding] / TWO_PI
            fk = np.outer(f_inst, k).ravel()
            ak = np.outer(env[fi, sounding] * amps[sounding], w_partial).ravel()
            ph = np.outer(c.phi[j, sounding], k).ravel()                    # the common 2π·k·f·t cancels in a group
            gk = group[sounding].ravel()
            keep = fk < 0.45 * sr
            gk, fk, ak, ph = gk[keep], fk[keep], ak[keep], ph[keep]
            m = len(keys)
            asum = np.bincount(gk, weights=ak, minlength=m)
            amp = np.hypot(np.bincount(gk, weights=ak * np.cos(ph), minlength=m),
                           np.bincount(gk, weights=ak * np.sin(ph), minlength=m))
            live = asum > 0
            fg = np.bincount(gk, weights=ak * fk, minlength=m)[live] / asum[live]
            ag = amp[live]
            cols["dissonance"][fi] = sethares_dissonance(fg, ag) / float(np.sum(ag))
            cols["centroid_hz"][fi] = float(np.sum(ag ** 2 * fg) / np.sum(ag ** 2))
    return {"t_s": frames, **cols}


def held_at_end(c: Cascade, seconds: float = 10.0) -> list[bool]:
    """Per pair: over the last `seconds` of the run, but never before the cascade completed, ψ moved less than π
    (no phase slip)."""
    j = max(0, len(c.t) - int(round(seconds * c.config.control_hz)))
    if c.complete_s is not None:
        j = max(j, int(round(c.complete_s * c.config.control_hz)))
    return [bool(np.ptp(c.psi(k)[j:]) < math.pi) for k in range(len(c.pairs))]


def _ratio(r: Fraction) -> str:
    return f"{r.numerator}/{r.denominator}"


def cascade_report(c: Cascade, tl: dict[str, np.ndarray]) -> dict:
    cfg = c.config
    held = held_at_end(c, c.seconds)                                     # everything after the cascade completed
    finite = np.isfinite(c.born)
    generations = []
    for d in sorted({v.depth for v in c.voices}):
        idx = [v.index for v in c.voices if v.depth == d]
        generations.append({"depth": d, "voices": len(idx),
                            "first_birth_s": float(np.min(c.born[idx])), "last_coherent_s": float(np.max(c.coherent[idx])),
                            "pitches": [_ratio(c.voices[i].ratio) for i in idx]})

    def at(name: str, which: str) -> float | None:
        x = tl[name][np.isfinite(tl[name])]
        if not len(x):
            return None
        return float({"first": x[0], "last": x[-1], "max": x.max(), "min": x.min()}[which])

    pairs = []
    for k, e in enumerate(c.pairs):
        b = np.abs(c.dpsi(k)) / TWO_PI
        on = c.born[e.child]
        locked = np.flatnonzero((c.t >= on) & (b < cfg.lock_hz))
        pairs.append({"child": e.child, "parent": e.parent, "ratio": _ratio(Fraction(e.p, e.q)),
                      "coincident_partials": f"child {e.q} = parent {e.p}", "coupled": e.coupled,
                      "start_beat_hz": abs(e.delta) / TWO_PI,
                      "k_max_rad_s": e.k_max, "first_locked_s": float(c.t[locked[0]]) if len(locked) else None,
                      "held_at_end": held[k]})
    return {
        "seed": cfg.seed, "config": cfg.to_dict(), "f0_hz": c.f0, "generators": [_ratio(g) for g in c.generators],
        "voices": len(c.voices), "pairs": len(c.pairs), "seconds": c.seconds,
        "cascade_complete_s": c.complete_s, "all_coherent": bool(np.all(np.isfinite(c.coherent))),
        "all_held_at_end": bool(all(held)), "voices_born": int(finite.sum()),
        "generations": generations,
        "timeline": {"coherence_min": at("coherence", "min"), "coherence_end": at("coherence", "last"),
                     "beat_index_peak": at("beat_index", "max"), "beat_index_end": at("beat_index", "last"),
                     "max_beat_hz_peak": at("max_beat_hz", "max"), "max_beat_hz_end": at("max_beat_hz", "last"),
                     "dissonance_start": at("dissonance", "first"), "dissonance_end": at("dissonance", "last"),
                     "centroid_hz_start": at("centroid_hz", "first"), "centroid_hz_end": at("centroid_hz", "last")},
        "voice_table": [{"index": v.index, "ratio": _ratio(v.ratio), "freq_hz": v.freq, "depth": v.depth,
                         "pan": v.pan, "detune_hz": v.detune_hz, "born_s": float(c.born[v.index]),
                         "coherent_s": float(c.coherent[v.index])} for v in c.voices],
        "pair_table": pairs,
        "evidence": {
            "measured (L0)": "lock times, beat rates, coherence and the end-of-run hold test are computed from the "
                             "phases the audio is synthesised from; the lock condition and slip rate are Adler's.",
            "perceptual models (L1)": "sensory dissonance (Plomp & Levelt 1965; Sethares 1993) and the fluctuation "
                                      "weighting (Zwicker & Fastl: strongest near 4 Hz) are models of perception, used "
                                      "as proxies; neither was fitted to a listener here.",
            "breathing (L1)": "slow breathing near 0.1 Hz raises heart-rate variability when the listener actually "
                              "breathes at that rate (resonance-frequency breathing; Lehrer & Gevirtz 2014). The "
                              "swell offers a pace; it does not make anyone breathe.",
            "relaxation and focus (L2, untested)": "that hearing beats slow to stillness, or a cascade climbing, "
                                                   "relaxes or focuses a listener has not been measured. Test it: "
                                                   "record ECG and respiration during silence and during playback, "
                                                   "then compare `beats` (HRV) and `coherence` (RSA) between them.",
        },
    }
