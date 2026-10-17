"""MAP-Elites over genomes (Mouret & Clune 2015): keep the best piece in every cell of a behaviour grid.

Behaviour = (edge dimension of the Julia set, pitch-class entropy of the score): how intricate the fractal is and
how evenly the mode is used. Objective, one of
    recurrence   longest H1 bar of the delay-embedded texture curve / its diameter (the texture returns on itself),
                 the median over embedding dimensions 2, 3 and 4 at 48 points
    coupling     Pearson correlation of note-onset counts with the slow-pulse rate: the notes ride the pulse
A genome is valid when its score has at least 16 notes and reaches 2 voices. The seed's own genome is evaluated
first, so the gain over the unevolved piece is measured, not assumed. Deterministic: all variation comes from Chaos.

Selecting the best of hundreds of noisy measurements overstates the winner (the winner's curse). So the result also
re-measures baseline and champion with an estimator the search never saw (recurrence at 32 and 64 points;
coupling as a Spearman rank correlation) and reports that held-out gain beside the in-search one.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from .analysis import recurrence
from .chaos import Chaos
from .fractal import edge_dimension
from .score import DENSITY, MODES, RADIUS, ZOOM, Genome, Piece, compose_genome

OBJECTIVES = ("recurrence", "coupling")
SEARCH_DIMS, SEARCH_POINTS, HELD_OUT_POINTS = (2, 3, 4), 48, (32, 64)


def recurrence_score(texture: np.ndarray, points: tuple[int, ...] = (SEARCH_POINTS,)) -> float:
    return float(np.median([recurrence(texture, dim=d, points=n)["longest_h1_over_diameter"]
                            for d in SEARCH_DIMS for n in points]))


def _onsets(piece: Piece) -> np.ndarray:
    onsets = np.zeros(len(piece.lfo_rate))
    for nt in piece.notes:
        onsets[min(len(onsets) - 1, int(nt.start / piece.step))] += 1
    return onsets


def _ranks(v: np.ndarray) -> np.ndarray:
    order = np.argsort(v, kind="stable")
    r = np.empty(len(v))
    r[order] = np.arange(len(v), dtype=float)
    for val in np.unique(v):                                             # average ranks over ties
        tie = v == val
        r[tie] = r[tie].mean()
    return r


def held_out(genome: Genome, name: str, cfg: "EvolveConfig") -> float:
    piece = compose_genome(genome, name, cfg.seconds, cfg.voices)
    if cfg.objective == "recurrence":
        return recurrence_score(piece.lattice.std(axis=0), HELD_OUT_POINTS)
    o = _onsets(piece)
    return float(np.corrcoef(_ranks(o), _ranks(piece.lfo_rate))[0, 1]) if o.std() > 0 else 0.0


@dataclass(frozen=True)
class EvolveConfig:
    iterations: int = 240                       # evaluations after the initial population
    initial: int = 24                           # random genomes, plus the seed's own
    bins: tuple[int, int] = (6, 6)
    dimension_range: tuple[float, float] = (1.0, 1.45)
    entropy_range: tuple[float, float] = (2.2, math.log2(7))
    objective: str = "recurrence"
    seconds: float = 32.0
    voices: int = 4
    mutation_scale: float = 1.0
    edge_grid: int = 256                        # descriptor resolution; reports use 512

    def validate(self) -> "EvolveConfig":
        if self.objective not in OBJECTIVES:
            raise ValueError(f"objective must be one of {OBJECTIVES}, got {self.objective!r}")
        if self.iterations < 0 or self.initial < 1 or min(self.bins) < 1:
            raise ValueError("iterations ≥ 0, initial ≥ 1 and bins ≥ 1 are required")
        return self


def _texture_metrics(piece: Piece) -> dict:
    notes = piece.notes
    pcs = np.zeros(12)
    for nt in notes:
        pcs[nt.pitch % 12] += nt.duration
    p = pcs[pcs > 0] / pcs.sum() if pcs.sum() > 0 else np.zeros(0)
    onsets = _onsets(piece)
    poly = 0
    if notes:
        ev = sorted([(n.start, 1) for n in notes] + [(n.start + n.duration, -1) for n in notes],
                    key=lambda e: (e[0], e[1]))
        live = 0
        for _, d in ev:
            live += d
            poly = max(poly, live)
    return {"notes": len(notes), "polyphony_max": poly,
            "pitch_class_entropy_bits": float(-(p * np.log2(p)).sum()) if len(p) else 0.0,
            "recurrence": recurrence_score(piece.lattice.std(axis=0)),
            "coupling": float(np.corrcoef(onsets, piece.lfo_rate)[0, 1]) if onsets.std() > 0 else 0.0}


def evaluate(genome: Genome, name: str, cfg: EvolveConfig) -> dict:
    piece = compose_genome(genome, name, cfg.seconds, cfg.voices)
    m = _texture_metrics(piece)
    m["edge_dimension"] = edge_dimension(genome.c, cfg.edge_grid, 160)
    m["valid"] = m["notes"] >= 16 and m["polyphony_max"] >= 2
    m["fitness"] = m[cfg.objective] if m["valid"] else -math.inf
    return m


def _cell(m: dict, cfg: EvolveConfig) -> tuple[int, int]:
    def bin_of(v: float, lo: float, hi: float, k: int) -> int:
        return int(np.clip(math.floor((v - lo) / (hi - lo) * k), 0, k - 1))
    return (bin_of(m["edge_dimension"], *cfg.dimension_range, cfg.bins[0]),
            bin_of(m["pitch_class_entropy_bits"], *cfg.entropy_range, cfg.bins[1]))


def _random_genome(ch: Chaos) -> Genome:
    u = ch.uniform(6)
    modes = list(MODES)
    return Genome(theta=2 * math.pi * u[0], radius=RADIUS[0] + (RADIUS[1] - RADIUS[0]) * u[1],
                  zoom=ZOOM[0] + (ZOOM[1] - ZOOM[0]) * u[2], density=DENSITY[0] + (DENSITY[1] - DENSITY[0]) * u[3],
                  mode=modes[int(u[4] * len(modes))], root=36 + int(u[5] * 12)).validate()


def qd_search(ch: Chaos, evaluate, cell_of, random_genome, mutate, to_dict, from_dict, bins: tuple[int, ...],
              iterations: int, initial: int, keep: tuple[str, ...] = (), base=None, offset: float = 0.0,
              progress=None) -> dict:
    """MAP-Elites, independent of what is being searched (Mouret & Clune 2015).

    evaluate(genome) → dict with "valid" and "fitness" (higher is better) plus any measurements; cell_of(that dict)
    → a tuple of bin indices. A base genome, if given, is evaluated first. Then `initial` random genomes, then
    `iterations` mutations of uniformly chosen elites. All variation comes from `ch`, in a fixed order, so a search
    is reproducible. `offset` is added to every fitness in the QD score (the sum over the archive), which needs
    non-negative values.
    """
    archive: dict[tuple, dict] = {}
    history: list[list[float]] = []
    counts = {"evaluations": 0, "valid": 0}
    total = int(np.prod(bins))

    def offer(g, parent, it: int) -> dict:
        m = evaluate(g)
        counts["evaluations"] += 1
        if not m["valid"]:
            return m
        counts["valid"] += 1
        cell = cell_of(m)
        if cell not in archive or m["fitness"] > archive[cell]["fitness"]:
            archive[cell] = {"cell": list(cell), "genome": to_dict(g), "fitness": m["fitness"], "born": it,
                             "parent": list(parent) if parent else None, **{k: m[k] for k in keep if k in m}}
        return m

    def snapshot() -> None:
        fit = [e["fitness"] for e in archive.values()]
        history.append([counts["evaluations"], len(archive) / total, float(sum(f + offset for f in fit)),
                        float(max(fit, default=-math.inf))])

    baseline = offer(base, None, 0) if base is not None else None
    for _ in range(initial):
        offer(random_genome(ch), None, 0)
    snapshot()
    for it in range(1, iterations + 1):
        if not archive:
            offer(random_genome(ch), None, it)
            continue
        cells = sorted(archive)
        parent = cells[int(ch.scalar() * len(cells))]
        offer(mutate(from_dict(archive[parent]["genome"]), ch), parent, it)
        if it % 10 == 0 or it == iterations:
            snapshot()
            if progress:
                progress(history[-1])
    return {"archive": archive, "history": history, "baseline": baseline, "coverage": len(archive) / total, **counts}


def map_elites(name: str, cfg: EvolveConfig = EvolveConfig(), base: Genome | None = None,
               progress=None) -> dict:
    cfg.validate()
    base = base or Genome.from_seed(name)
    run = qd_search(Chaos(f"{name}/map-elites/{cfg.objective}"), lambda g: evaluate(g, name, cfg),
                    lambda m: _cell(m, cfg), _random_genome, lambda g, ch: g.mutate(ch, cfg.mutation_scale),
                    lambda g: g.to_dict(), Genome.from_dict, cfg.bins, cfg.iterations, cfg.initial,
                    keep=("edge_dimension", "pitch_class_entropy_bits", "notes", "polyphony_max", "recurrence",
                          "coupling"),
                    base=base, offset=1.0 if cfg.objective == "coupling" else 0.0, progress=progress)
    baseline, history = run["baseline"], run["history"]
    elites = sorted(run["archive"].values(), key=lambda e: -e["fitness"])
    champion = elites[0] if elites else None
    check = None
    if champion and baseline["valid"]:
        hb, hc = held_out(base, name, cfg), held_out(Genome.from_dict(champion["genome"]), name, cfg)
        check = {"estimator": ("recurrence median over dims 2-4 at 32 and 64 points (the search used 48)"
                               if cfg.objective == "recurrence" else "Spearman rank correlation (the search used Pearson)"),
                 "baseline": hb, "champion": hc, "gain": hc - hb}
    return {
        "name": name, "config": {**asdict(cfg), "bins": list(cfg.bins)},
        "evaluations": run["evaluations"], "valid": run["valid"],
        "coverage": run["coverage"], "qd_score": history[-1][2] if history else 0.0,
        "baseline": {"genome": base.to_dict(), "valid": baseline["valid"], "fitness": baseline["fitness"],
                     "cell": list(_cell(baseline, cfg)), "edge_dimension": baseline["edge_dimension"],
                     "pitch_class_entropy_bits": baseline["pitch_class_entropy_bits"]},
        "champion": champion,
        "gain_over_baseline": (champion["fitness"] - baseline["fitness"]) if champion and baseline["valid"] else None,
        "held_out": check,
        "history": {"columns": ["evaluations", "coverage", "qd_score", "best"], "rows": history},
        "elites": elites,
    }
