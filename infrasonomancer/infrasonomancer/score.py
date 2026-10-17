"""Genome → Julia lattice → score. A genome is the complete, serializable recipe of a piece."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

from .chaos import Chaos
from .fractal import cardioid_c, julia

MODES = {
    "ionian": (0, 2, 4, 5, 7, 9, 11), "dorian": (0, 2, 3, 5, 7, 9, 10), "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "lydian": (0, 2, 4, 6, 7, 9, 11), "mixolydian": (0, 2, 4, 5, 7, 9, 10), "aeolian": (0, 2, 3, 5, 7, 8, 10),
}
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
DEGREES = 21                                      # three octaves of a 7-note mode
TOP_OFFSET = 12 * ((DEGREES - 1) // 7) + 11       # highest possible pitch above the root

# ranges a mutation stays inside; any genome loaded from JSON only has to satisfy validate()
RADIUS = (0.985, 0.997)
ZOOM = (1.0, 1.6)
DENSITY = (0.04, 0.16)


@dataclass(frozen=True)
class Genome:
    theta: float        # angle of λ, radians: which part of the cardioid edge, hence which fractal
    radius: float       # |λ| < 1: closeness to the edge, hence intricacy
    zoom: float         # lattice magnification
    density: float      # fraction of lattice cells that sound
    mode: str
    root: int           # MIDI note of the lowest degree

    @classmethod
    def from_seed(cls, seed: str, density: float = 0.08) -> "Genome":
        ch = Chaos(seed)
        theta = 2 * math.pi * int.from_bytes(ch.digest[16:24], "big") / 2 ** 64   # the hash itself picks the fractal
        radius = RADIUS[0] + 0.012 * ch.scalar()
        zoom = ZOOM[0] + 0.6 * ch.scalar()
        mode = list(MODES)[int(ch.scalar() * len(MODES))]
        root = 36 + int(ch.scalar() * 12)                                         # C2 … B2
        return cls(theta, radius, zoom, density, mode, root).validate()

    @classmethod
    def from_dict(cls, d: dict) -> "Genome":
        missing = {"theta", "radius", "zoom", "density", "mode", "root"} - set(d)
        if missing:
            raise ValueError(f"genome is missing {sorted(missing)}")
        return cls(float(d["theta"]), float(d["radius"]), float(d["zoom"]), float(d["density"]),
                   str(d["mode"]), int(d["root"])).validate()

    def to_dict(self) -> dict:
        return asdict(self)

    def validate(self) -> "Genome":
        problems = []
        if not (math.isfinite(self.theta)):
            problems.append("theta must be finite")
        if not (0.0 < self.radius < 1.0):
            problems.append(f"radius {self.radius} must be in (0, 1) for a connected Julia set")
        if not (self.zoom > 0.0):
            problems.append(f"zoom {self.zoom} must be > 0")
        if not (0.0 < self.density < 1.0):
            problems.append(f"density {self.density} must be in (0, 1)")
        if self.mode not in MODES:
            problems.append(f"mode {self.mode!r} must be one of {sorted(MODES)}")
        if not (0 <= self.root <= 127 - TOP_OFFSET):
            problems.append(f"root {self.root} must be in [0, {127 - TOP_OFFSET}] so every degree is a MIDI note")
        if problems:
            raise ValueError("invalid genome: " + "; ".join(problems))
        return self

    @property
    def c(self) -> complex:
        return cardioid_c(self.theta, self.radius)

    def mutate(self, ch: Chaos, scale: float = 1.0) -> "Genome":
        """A small step: nearby θ gives a nearby Julia set, so search has locality. Always draws the same count
        of variates, so the stream stays aligned whichever branches are taken."""
        z, u = ch.normal(4), ch.uniform(4)
        modes = list(MODES)
        return Genome(
            theta=(self.theta + 0.06 * scale * z[0]) % (2 * math.pi),
            radius=float(np.clip(self.radius + 0.002 * scale * z[1], *RADIUS)),
            zoom=float(np.clip(self.zoom + 0.08 * scale * z[2], *ZOOM)),
            density=float(np.clip(self.density + 0.012 * scale * z[3], *DENSITY)),
            mode=modes[int(u[1] * len(modes))] if u[0] < 0.1 else self.mode,
            root=36 + int(u[3] * 12) if u[2] < 0.1 else self.root,
        ).validate()


@dataclass(frozen=True)
class Note:
    pitch: int          # MIDI
    start: float        # seconds
    duration: float     # seconds
    velocity: int       # 1-127


@dataclass
class Piece:
    seed: str                      # the piece's name; also seeds its timbre
    genome: Genome
    lattice: np.ndarray
    filled: np.ndarray
    notes: list[Note]
    lfo_rate: np.ndarray           # Hz per time step, 0.1–8
    step: float                    # seconds per lattice column
    seconds: float
    meta: dict = field(default_factory=dict)

    @property
    def c(self) -> complex:
        return self.genome.c

    @property
    def mode(self) -> str:
        return self.genome.mode

    @property
    def root(self) -> int:
        return self.genome.root


def compose_genome(genome: Genome, name: str, seconds: float = 32.0, voices: int = 4,
                   width: int = 128, height: int = 64) -> Piece:
    if not seconds > 0:
        raise ValueError(f"seconds must be > 0, got {seconds}")
    if not 1 <= voices <= 16:
        raise ValueError(f"voices must be in [1, 16], got {voices}")
    if width < 16 or height < 8:
        raise ValueError(f"lattice must be at least 16 × 8, got {width} × {height}")
    lattice, filled = julia(genome.c, width, height, zoom=genome.zoom)
    lattice = np.where(filled, 0.0, lattice)          # the interior is silence; slow escape near the edge sings
    scale = MODES[genome.mode]
    step = seconds / width
    thresh = float(np.quantile(lattice, 1.0 - genome.density))

    def pitch(row: int) -> int:
        d = (height - 1 - row) * DEGREES // height                       # top of the lattice = high
        return genome.root + 12 * (d // 7) + scale[d % 7]

    active: dict[int, tuple[float, float]] = {}                          # pitch -> (start, peak value)
    notes: list[Note] = []
    for col in range(width):
        values = lattice[:, col]
        rows = [r for r in np.argsort(-values) if values[r] >= thresh]
        chosen: dict[int, float] = {}
        for r in rows:
            p = pitch(int(r))
            if p not in chosen:
                chosen[p] = float(values[r])
            if len(chosen) == voices:
                break
        t = col * step
        for p in list(active):                                           # end notes that stopped sounding
            if p not in chosen:
                start, peak = active.pop(p)
                notes.append(Note(p, start, t - start, int(40 + 80 * peak)))
        for p, v in chosen.items():                                      # start or sustain
            start, peak = active.get(p, (t, 0.0))
            active[p] = (start, max(peak, v))
    for p, (start, peak) in active.items():
        notes.append(Note(p, start, seconds - start, int(40 + 80 * peak)))
    notes.sort(key=lambda n: (n.start, n.pitch))

    col_mean = lattice.mean(axis=0)
    span = col_mean.max() - col_mean.min()
    m = (col_mean - col_mean.min()) / span if span > 0 else np.zeros_like(col_mean)
    lfo_rate = 0.1 * 80.0 ** m                                           # 0.1 Hz … 8 Hz, log-spaced
    return Piece(name, genome, lattice, filled, notes, lfo_rate, step, seconds,
                 {"voices": voices, "width": width, "height": height})


def compose(seed: str, seconds: float = 32.0, density: float = 0.08, voices: int = 4,
            width: int = 128, height: int = 64, genome: Genome | None = None) -> Piece:
    """The piece named `seed`. Without a genome, the seed's hash chooses one."""
    return compose_genome(genome or Genome.from_seed(seed, density), seed, seconds, voices, width, height)
