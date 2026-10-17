"""The evolve engine repurposed: instead of searching for pieces, search for the conditions under which the
synchronization instruments give the wrong answer, and map them.

Genome: a breath–heart Scenario (ratio, breathing rate, position across the Arnold tongue, coupling, noise levels,
record length). Each evaluation simulates a raw recording and runs `cardioresp.assess`, whose verdicts are
"locked" (interaction at level α and under one net phase slip) or not. A right call scores 0; a wrong one scores
½ + ½·clarity, where clarity says how unambiguous the reference was: 1 − |slips| for a locked reference,
min(1, (|slips| − 1)/4) for a slipping one (full at 5 slips). A pipeline that cannot run scores 1. Three targets:

    locking       the instrument as a user runs it (raw signals) against what the true phases did
    statistics    the same analysis on the true phases against what they did: the method's own limit
    measurement   raw signals against true phases: what beat detection, band choice and Hilbert phase change

MAP-Elites keeps the worst case found in each cell of a 2-D grid over two scenario axes, so the result is a failure
map rather than a single counter-example: quality-diversity search used as adversarial testing. Every failure with
score ≥ 0.5 is then re-simulated with three fresh noise seeds, so a map entry is a reproducible condition and not
one unlucky draw.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from .cardioresp import Scenario, assess, simulate
from .chaos import Chaos
from .evolve import qd_search

RATIOS = ((4, 1), (3, 1), (5, 1), (9, 2), (7, 2), (11, 3))
BOUNDS = {"breath_hz": (0.12, 0.40), "detuning": (-3.0, 3.0), "coupling": (0.05, 1.0), "phase_noise": (0.0, 0.6),
          "breath_noise": (0.0, 0.1), "sensor_noise": (0.0, 0.6), "seconds": (90.0, 300.0)}
AXES = {"detuning": (lambda sc: abs(sc.detuning), (0.0, 3.0)),
        "sensor_noise": (lambda sc: sc.sensor_noise, BOUNDS["sensor_noise"]),
        "breath_noise": (lambda sc: sc.breath_noise, BOUNDS["breath_noise"]),
        "phase_noise": (lambda sc: sc.phase_noise, BOUNDS["phase_noise"]),
        "coupling": (lambda sc: sc.coupling, BOUNDS["coupling"]),
        "seconds": (lambda sc: sc.seconds, BOUNDS["seconds"])}
TARGETS = ("locking", "statistics", "measurement")


@dataclass(frozen=True)
class EnvelopeConfig:
    target: str = "locking"
    axes: tuple[str, str] = ("detuning", "sensor_noise")
    bins: tuple[int, int] = (6, 6)
    iterations: int = 160
    initial: int = 24
    surrogates: int = 39
    alpha: float = 0.05
    replays: int = 3

    def validate(self) -> "EnvelopeConfig":
        if self.target not in TARGETS:
            raise ValueError(f"target must be one of {TARGETS}, got {self.target!r}")
        if len(self.axes) != 2 or any(a not in AXES for a in self.axes) or self.axes[0] == self.axes[1]:
            raise ValueError(f"axes must be two different names from {sorted(AXES)}, got {self.axes}")
        if self.iterations < 0 or self.initial < 1 or min(self.bins) < 1 or self.surrogates < 19:
            raise ValueError("iterations ≥ 0, initial ≥ 1, bins ≥ 1 and surrogates ≥ 19 are required")
        return self


def _clip(name: str, v: float) -> float:
    lo, hi = BOUNDS[name]
    return float(min(hi, max(lo, v)))


def random_scenario(ch: Chaos) -> Scenario:
    for _ in range(200):
        u = ch.uniform(8)
        n, m = RATIOS[int(u[0] * len(RATIOS))]
        lo, hi = BOUNDS["coupling"]
        sc = Scenario(n=n, m=m, breath_hz=_clip("breath_hz", 0.12 + 0.28 * u[1]), detuning=float(-3.0 + 6.0 * u[2]),
                      coupling=float(lo * (hi / lo) ** u[3]), phase_noise=float(0.6 * u[4]),
                      breath_noise=float(0.1 * u[5]), sensor_noise=float(0.6 * u[6]), seconds=float(round(90 + 210 * u[7])))
        try:
            return sc.validate()
        except ValueError:
            continue
    raise RuntimeError("no valid random scenario in 200 draws")


def mutate_scenario(sc: Scenario, ch: Chaos) -> Scenario:
    """Gaussian steps of a tenth of each range; the ratio changes with probability 0.1. Draws a fixed count of
    variates per attempt; an attempt that leaves the valid region is retried, and after 20 the parent returns."""
    for _ in range(20):
        z, u = ch.normal(7), ch.uniform(2)
        d = {k: _clip(k, getattr(sc, k) + 0.1 * (BOUNDS[k][1] - BOUNDS[k][0]) * z[i])
             for i, k in enumerate(("breath_hz", "detuning", "coupling", "phase_noise", "breath_noise",
                                    "sensor_noise", "seconds"))}
        d["seconds"] = float(round(d["seconds"]))
        n, m = RATIOS[int(u[1] * len(RATIOS))] if u[0] < 0.1 else (sc.n, sc.m)
        try:
            return Scenario(n=n, m=m, fs=sc.fs, **d).validate()
        except ValueError:
            continue
    return sc


def severity(says_locked: bool | None, reference_locked: bool, reference_slips: float) -> float:
    """0 for a right call, 1 for no call, else ½ + ½·clarity of the reference."""
    if says_locked is None:
        return 1.0
    if says_locked == reference_locked:
        return 0.0
    s = abs(reference_slips)
    clarity = (1.0 - s) if reference_locked else (s - 1.0) / 4.0
    return 0.5 + 0.5 * float(min(1.0, max(0.0, clarity)))


def score(sc: Scenario, cfg: EnvelopeConfig, seed: str) -> dict:
    rec = simulate(sc, seed)
    a = assess(rec, cfg.surrogates, cfg.alpha, seed=f"{seed}/surrogates")
    o, pipe, truth = a["oracle"], a["pipeline"] or {}, a["truth"]
    if cfg.target == "locking":
        fitness, call = severity(a["pipeline_locked"], truth["locked"], truth["net_slips"]), a["pipeline_call"]
    elif cfg.target == "statistics":
        fitness, call = severity(a["oracle_locked"], truth["locked"], truth["net_slips"]), a["oracle_call"]
    else:
        fitness = severity(a["pipeline_locked"], a["oracle_locked"], o["net_slips"])
        call = "failed" if a["pipeline_locked"] is None else "agrees with oracle" if fitness == 0 else (
            "misses oracle's lock" if a["oracle_locked"] else "locks where oracle does not")
    return {"valid": True, "fitness": float(fitness), "call": call, "true_slips": truth["net_slips"],
            "true_index": rec.truth["true_index"], "oracle_verdict": o["verdict"], "oracle_p": o["p"],
            "oracle_slips": o["net_slips"], "oracle_ratio": o["ratio"], "pipeline_verdict": pipe.get("verdict"),
            "pipeline_p": pipe.get("p"), "pipeline_slips": pipe.get("net_slips"), "pipeline_ratio": pipe.get("ratio"),
            "beat_error_ms": pipe.get("beat_error_ms_median"), "pipeline_error": a["pipeline_error"],
            **{name: float(AXES[name][0](sc)) for name in cfg.axes}}


def failure_map(name: str, cfg: EnvelopeConfig = EnvelopeConfig(), progress=None) -> dict:
    cfg.validate()
    sim_seed = f"{name}/simulate"

    def cell_of(m: dict) -> tuple[int, int]:
        out = []
        for axis, k in zip(cfg.axes, cfg.bins):
            lo, hi = AXES[axis][1]
            out.append(int(np.clip(math.floor((m[axis] - lo) / (hi - lo) * k), 0, k - 1)))
        return tuple(out)

    keep = ("call", "true_slips", "true_index", "oracle_verdict", "oracle_p", "oracle_slips", "oracle_ratio",
            "pipeline_verdict", "pipeline_p", "pipeline_slips", "pipeline_ratio", "beat_error_ms",
            "pipeline_error") + tuple(cfg.axes)
    run = qd_search(Chaos(f"{name}/envelope/{cfg.target}/{','.join(cfg.axes)}"), lambda sc: score(sc, cfg, sim_seed),
                    cell_of, random_scenario, mutate_scenario, lambda sc: sc.to_dict(), Scenario.from_dict, cfg.bins,
                    cfg.iterations, cfg.initial, keep=keep, base=Scenario(), progress=progress)
    elites = sorted(run["archive"].values(), key=lambda e: -e["fitness"])
    grid = [[None] * cfg.bins[1] for _ in range(cfg.bins[0])]
    for e in elites:
        grid[e["cell"][0]][e["cell"][1]] = e["fitness"]
    failures = []
    for e in (e for e in elites if e["fitness"] >= 0.5):
        sc = Scenario.from_dict(e["genome"])
        again = [score(sc, cfg, f"{name}/replay/{k}")["fitness"] for k in range(cfg.replays)]
        failures.append({**{k: e.get(k) for k in ("cell", "fitness", "call", "true_slips", "oracle_verdict", "oracle_p",
                                                  "oracle_slips", "pipeline_verdict", "pipeline_p", "pipeline_slips",
                                                  "pipeline_error")},
                         "scenario": e["genome"], "replay_fitness": again,
                         "reproduces": sum(f >= 0.5 for f in again)})
    edges = {axis: list(np.linspace(*AXES[axis][1], k + 1)) for axis, k in zip(cfg.axes, cfg.bins)}
    return {
        "name": name, "config": {**asdict(cfg), "axes": list(cfg.axes), "bins": list(cfg.bins)},
        "evaluations": run["evaluations"], "coverage": run["coverage"],
        "baseline": {"scenario": Scenario().to_dict(), **{k: run["baseline"][k] for k in (
            "fitness", "call", "true_slips", "oracle_verdict", "pipeline_verdict")}},
        "worst_case_map": {"rows": cfg.axes[0], "columns": cfg.axes[1], "edges": edges, "fitness": grid},
        "failures": failures,
        "reproducible_failures": sum(1 for f in failures if f["reproduces"] >= 2),
        "safe_cells": sum(1 for e in elites if e["fitness"] < 0.1),
        "history": {"columns": ["evaluations", "coverage", "qd_score", "worst"], "rows": run["history"]},
        "elites": elites,
    }
