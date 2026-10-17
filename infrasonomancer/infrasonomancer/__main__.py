"""python -m infrasonomancer <command> — every tool in the package, on your own files.

    compose    SEED [--genome G] [--stereo] --out DIR      render.wav, score.mid, report.json, genome.json
    evolve     SEED [--objective recurrence|coupling]      archive.json, champion/, elite_NN/ (--render-top)
    beats      FILE --kind ecg|ppg                         beat times (CSV) and HRV (JSON)
    coherence  --x FILE --x-kind K --y FILE --y-kind K     n:m phase synchronization and (signal + beats) the
                                                           rhythm↔rate spectral coherence, both with surrogate
                                                           p-values; windows.csv, synchrogram.csv
    pll        FILE --f0 HZ                                phase-locked loop: lock fraction, frequency track CSV
    series     FILE                                        dominant rate, Hurst, DFA, recurrence (persistent H1)
    fractal    --c RE,IM | --seed TEXT | --image PNG       box-counting dimension; --png writes the image or mask
    dualcast   [--carrier 8.5e12 --deviation 432e3 ...]     the source's dual-wavelength cast, reproduced exactly:
                                                           source_stereo.wav (L=λ1, R=λ2), combined.wav, analysis
    cardioresp [--n 4 --m 1 --detuning δ ...] [--sonify]    breath and heart as coupled oscillators: raw recording,
                                                           ground truth, assessment; the locked counter-pair render
    envelope   [--target measurement|statistics]           MAP-Elites over scenarios for where the instruments
                                                           fail: archive.json, map.csv

Inputs: .wav (rate from the file), .npy (needs --fs), or text columns (CSV/TSV/whitespace, optional header;
needs --fs or --time-column). Stream kinds for coherence: signal (Hilbert phase of its dominant band, or
--x-band LO,HI), ecg / ppg (beats detected, 2π per beat), beats (a file of event times, s), rr (a file of
intervals; --x-unit 0.001 for ms). JSON goes to stdout and, with --out, to a file. Exit 0 on success, 1 when
the data cannot be processed (the message says why), 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

from .analysis import analyse, describe_series
from .cardioresp import Scenario, assess, simulate
from .coherence import pll_track, rate_coupling, stream_from_events, stream_from_signal, synchrogram, synchronize
from .dualcast import DualCast, alias_frequency, analyse as analyse_dualcast, cast, cast_exact, counter_pair, \
    null_analysis, transmit
from .cascade import CascadeConfig, cascade_report, cascade_timeline, recohere, render_cascade
from .envelope import AXES, TARGETS, EnvelopeConfig, failure_map
from .evolve import OBJECTIVES, EvolveConfig, map_elites
from .formats import image_mask, read_events, read_png, read_series, write_csv, write_midi, write_png, write_wav
from .fractal import box_dimension, boundary, cardioid_coordinates, julia
from .physio import detect_beats, hrv
from .render import render
from .score import Genome, compose


def _clean(obj):
    """JSON-safe: non-finite floats become null, numpy scalars and arrays become Python values."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return _clean(obj.tolist())
    if isinstance(obj, (np.floating, float)):
        return float(obj) if math.isfinite(obj) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _emit(result: dict, out: str | None = None) -> None:
    text = json.dumps(_clean(result), indent=2, ensure_ascii=False)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text + "\n")
    print(text)


def _pair(text: str, what: str) -> tuple[float, float]:
    try:
        a, b = (float(v) for v in text.split(","))
    except ValueError:
        raise ValueError(f"{what} must be two numbers separated by a comma, got {text!r}") from None
    return a, b


def _load_genome(arg: str) -> Genome:
    src = arg.strip()
    data = json.loads(src) if src.startswith("{") else json.loads(Path(src).read_text())
    if "genome" in data and isinstance(data["genome"], dict):                 # report.json, champion, elite
        data = data["genome"]
    return Genome.from_dict(data)


def _write_piece(out: Path, piece, sr: int, stereo: bool) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    audio = render(piece, sr, stereo=stereo)
    write_wav(out / "render.wav", audio, sr)
    write_midi(out / "score.mid", piece)
    report = analyse(piece, audio, sr)
    (out / "report.json").write_text(json.dumps(_clean(report), indent=2, ensure_ascii=False) + "\n")
    (out / "genome.json").write_text(json.dumps(piece.genome.to_dict(), indent=2) + "\n")
    return report


# ============================================================================================ commands

def cmd_compose(a: argparse.Namespace) -> int:
    if a.genome and a.density is not None:
        raise ValueError("--density is part of the genome; set it in the genome instead of on the command line")
    genome = _load_genome(a.genome) if a.genome else None
    piece = compose(a.seed, a.seconds, 0.08 if a.density is None else a.density, a.voices, genome=genome)
    _emit(_write_piece(Path(a.out), piece, a.sr, a.stereo))
    return 0


def cmd_evolve(a: argparse.Namespace) -> int:
    bins = tuple(int(v) for v in a.bins.lower().split("x"))
    if len(bins) != 2:
        raise ValueError(f"--bins must look like 6x6, got {a.bins!r}")
    cfg = EvolveConfig(iterations=a.iterations, initial=a.initial, bins=bins, objective=a.objective,
                       seconds=a.seconds, voices=a.voices, mutation_scale=a.mutation_scale)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res = map_elites(a.seed, cfg, progress=(lambda row: print(
        f"  {row[0]:4d} evaluations  coverage {row[1]:.2f}  qd {row[2]:.3f}  best {row[3]:.4f}", file=sys.stderr))
        if not a.quiet else None)
    (out / "archive.json").write_text(json.dumps(_clean(res), indent=2, ensure_ascii=False) + "\n")
    rendered = []
    for k, elite in enumerate(res["elites"][:max(1, a.render_top)]):
        piece = compose(a.seed, a.seconds, voices=a.voices, genome=Genome.from_dict(elite["genome"]))
        target = out / ("champion" if k == 0 else f"elite_{k:02d}")
        rep = _write_piece(target, piece, a.sr, a.stereo)
        rendered.append({"dir": str(target), "fitness": elite["fitness"], "cell": elite["cell"],
                         "pcm_sha256": rep["audio"]["pcm_sha256"]})
    summary = {k: res[k] for k in ("name", "evaluations", "valid", "coverage", "qd_score", "baseline",
                                   "gain_over_baseline", "held_out")}
    summary["champion"] = {k: res["champion"][k] for k in ("cell", "fitness", "edge_dimension",
                                                           "pitch_class_entropy_bits", "genome")} if res["champion"] else None
    summary["objective"] = a.objective
    summary["rendered"] = rendered
    _emit(summary)
    return 0


def _series(a: argparse.Namespace) -> tuple[float, np.ndarray, dict]:
    return read_series(a.file, a.column, a.fs, a.time_column)


def cmd_beats(a: argparse.Namespace) -> int:
    fs, x, info = _series(a)
    beats = detect_beats(x, fs, a.kind)
    result = {"source": info, "kind": a.kind, "hrv": hrv(beats)}
    if a.out:
        write_csv(a.out, ["t_s"], [beats])
        result["beats_csv"] = a.out
    _emit(result)
    return 0


def _stream(a: argparse.Namespace, side: str):
    kind, path = getattr(a, f"{side}_kind"), getattr(a, side)
    col, unit = getattr(a, f"{side}_column"), getattr(a, f"{side}_unit")
    if kind in ("beats", "rr"):
        times, info = read_events(path, col, intervals=(kind == "rr"), unit=unit)
        s = stream_from_events(times)
        s.info.update(source=info)
        return s
    fs, x, info = read_series(path, col, getattr(a, f"{side}_fs"), getattr(a, f"{side}_time_column"))
    if kind in ("ecg", "ppg"):
        times = detect_beats(x, fs, kind)
        s = stream_from_events(times)
        s.info.update(source=info, hrv=hrv(times))
        return s
    band = _pair(getattr(a, f"{side}_band"), f"--{side}-band") if getattr(a, f"{side}_band") else None
    s = stream_from_signal(x, fs, band=band)
    s.info.update(source=info)
    return s


def cmd_coherence(a: argparse.Namespace) -> int:
    x, y = _stream(a, "x"), _stream(a, "y")
    res = synchronize(x, y, rate=a.rate, window=a.window, step=a.step, max_n=a.max_n, max_m=a.max_m,
                      surrogates=a.surrogates, alpha=a.alpha)
    res["x"] = {"kind": x.kind, "rate_hz": x.rate_hz, **x.info}
    res["y"] = {"kind": y.kind, "rate_hz": y.rate_hz, **y.info}
    sig, ev = (x, y) if x.samples is not None and y.events is not None else (y, x)
    if sig.samples is not None and ev.events is not None:                   # a rhythm and a beat train: RSA-type coupling
        try:
            res["rate_coupling"] = rate_coupling(*sig.samples, ev.events, band=tuple(sig.info["band_hz"]),
                                                 surrogates=a.surrogates)
        except ValueError as e:
            res["rate_coupling"] = {"skipped": str(e)}
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        tab = res["_table"]
        write_csv(out / "windows.csv", ["t_start_s", "t_end_s", "ratio", "index", "locked", "net_slips"],
                  [tab["t_start"], tab["t_end"], tab["ratio"], tab["index"], tab["locked"], tab["slips"]])
        events, cont = (y.events, x) if y.events is not None else (x.events, y)
        if events is not None and cont.kind == "signal":
            cols = []
            for m in range(1, a.max_m + 1):
                t, psi = synchrogram(events, cont, m)
                cols.append(psi)
            write_csv(out / "synchrogram.csv", ["t_s"] + [f"psi_m{m}" for m in range(1, a.max_m + 1)], [t] + cols)
        (out / "coherence.json").write_text(json.dumps(_clean(res), indent=2, ensure_ascii=False) + "\n")
    _emit(res)
    return 0


def cmd_pll(a: argparse.Namespace) -> int:
    fs, x, info = _series(a)
    r = pll_track(x, fs, a.f0, a.bandwidth, a.zeta, a.lock_threshold)
    result = {"source": info, "f0_hz": a.f0, "bandwidth_hz": a.bandwidth, "lock_fraction": r.lock_fraction,
              "final_frequency_hz": r.final_frequency, "frequency_sd_hz": float(np.std(r.frequency[len(x) // 2:]))}
    if a.out:
        hop = max(1, len(x) // 20000)                                         # at most ~20 000 rows
        idx = np.arange(0, len(x), hop)
        write_csv(a.out, ["t_s", "frequency_hz", "locked"], [idx / fs, r.frequency[idx], r.locked[idx].astype(int)])
        result["track_csv"] = a.out
        result["track_hop_samples"] = int(hop)
    _emit(result)
    return 0


def cmd_series(a: argparse.Namespace) -> int:
    fs, x, info = _series(a)
    _emit({"source": info, **describe_series(x, fs, a.points, a.fmin, a.fmax)}, a.out)
    return 0


def cmd_fractal(a: argparse.Namespace) -> int:
    chosen = [v for v in (a.c, a.seed, a.image) if v is not None]
    if len(chosen) != 1:
        raise ValueError("give exactly one of --c, --seed or --image")
    if a.image:
        img = read_png(a.image) if a.image.lower().endswith(".png") else np.load(a.image, allow_pickle=False)
        mask = image_mask(img, a.foreground)
        result = {"source": a.image, "shape": list(mask.shape), "foreground": a.foreground,
                  "foreground_fraction": float(mask.mean()), "box_dimension": box_dimension(mask)}
        if a.png:
            write_png(a.png, mask)
    else:
        c = complex(*_pair(a.c, "--c")) if a.c else Genome.from_seed(a.seed).c
        escape, filled = julia(c, a.size, a.size, a.iter)
        edge = boundary(filled)
        theta, lam = cardioid_coordinates(c)
        result = {"c": [c.real, c.imag], "size": a.size, "max_iter": a.iter,
                  "filled_fraction": float(filled.mean()),
                  "edge_box_dimension": box_dimension(edge) if edge.any() else 0.0,
                  "main_cardioid": {"inside": lam < 1.0, "theta": theta, "radius": lam}}
        if a.png:
            write_png(a.png, np.where(filled, 0, np.round(255 * (1 - escape) ** 2)).astype(np.uint8))
    if a.png:
        result["png"] = a.png
    _emit(result)
    return 0


def cmd_dualcast(a: argparse.Namespace) -> int:
    dc = DualCast(a.carrier, a.deviation, a.samples, a.duration, a.data_rate, a.rc_tau).validate()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    _, l1, l2, combined = cast(dc)
    if a.exact:
        l1, l2 = cast_exact(dc)
        combined = (l1 + l2) / 2
    sr = int(round(dc.fs))
    write_wav(out / "source_stereo.wav", 0.89 * np.stack([l1, l2], axis=1), sr)
    write_wav(out / "combined.wav", 0.89 * combined, sr)
    tx = transmit(dc, combined)
    gain = dc.data_rate / 1e9
    write_wav(out / "transmitted.wav", 0.89 * tx / gain, sr)
    rep = analyse_dualcast(dc)
    rep["files"] = {"source_stereo.wav": "L = λ1, R = λ2 (unprocessed), × 0.89", "combined.wav": "(λ1 + λ2)/2 × 0.89",
                    "transmitted.wav": f"the source's transmitted schema ÷ {gain:g} × 0.89", "sample_rate_hz": sr,
                    "phases": "exact rational" if a.exact else "float64, as the source computes them"}
    (out / "analysis.json").write_text(json.dumps(_clean(rep), indent=2) + "\n")
    _emit(rep)
    return 0


def cmd_cascade(a: argparse.Namespace) -> int:
    if a.config:
        src = a.config.strip()
        d = json.loads(src) if src.startswith("{") else json.loads(Path(src).read_text())
        cfg = CascadeConfig.from_dict(d.get("config", d))                    # cascade.json or a bare config
    else:
        cfg = CascadeConfig(seed=a.seed, generators=tuple(g.strip() for g in a.generators.split(",")), depth=a.depth,
                            f0=a.f0, f_max=a.f_max, min_cents=a.min_cents, beat_hz=a.beat_hz, coupling=a.coupling,
                            adapt=not a.no_adapt, backreaction=a.backreaction, ramp_s=a.ramp, dwell_s=a.dwell,
                            lock_hz=a.lock_hz, stagger_s=a.stagger, attack_s=a.attack, harmonics=a.harmonics,
                            rolloff=a.rolloff, tilt_db_oct=a.tilt, breath_hz=a.breath_hz, breath_depth=a.breath_depth,
                            tail_s=a.tail, fade_s=a.fade, max_seconds=a.max_seconds).validate()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    c = recohere(cfg)
    write_wav(out / "cascade.wav", render_cascade(c, a.sr, stereo=not a.mono), a.sr)
    tl = cascade_timeline(c, sr=a.sr)
    write_csv(out / "timeline.csv", list(tl), list(tl.values()))
    rep = cascade_report(c, tl)
    rep["files"] = {"cascade.wav": f"{'mono' if a.mono else 'stereo'}, {a.sr} Hz, peak −1 dBFS",
                    "timeline.csv": "per 0.25 s: voices, coherence, beat_index, max_beat_hz, dissonance, centroid_hz",
                    "cascade.json": "this report; --config cascade.json reproduces the run"}
    (out / "cascade.json").write_text(json.dumps(_clean(rep), indent=2, ensure_ascii=False) + "\n")
    _emit({k: v for k, v in rep.items() if k not in ("voice_table", "pair_table", "config")})
    return 0


def _scenario(a: argparse.Namespace) -> Scenario:
    if a.scenario:
        src = a.scenario.strip()
        d = json.loads(src) if src.startswith("{") else json.loads(Path(src).read_text())
        d = d.get("scenario", d)
        return Scenario.from_dict(d)
    return Scenario(a.n, a.m, a.breath_hz, a.detuning, a.coupling, a.phase_noise, a.breath_noise, a.sensor_noise,
                    a.seconds, a.fs).validate()


def cmd_cardioresp(a: argparse.Namespace) -> int:
    sc = _scenario(a)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rec = simulate(sc, a.seed)
    write_csv(out / "recording.csv", ["t_s", "resp", "ecg", "ppg"], [rec.t, rec.resp, rec.ecg, rec.ppg])
    write_csv(out / "beats_true.csv", ["t_s"], [rec.beats])
    result = {"scenario": sc.to_dict(), "truth": rec.truth, "assessment": assess(rec, a.surrogates, seed=a.seed)}
    if a.sonify:
        carrier = alias_frequency(8.5e12, DualCast().fs) if a.carrier == "source" else float(a.carrier)
        stereo = counter_pair(rec.t_model, rec.phi_r, rec.phi_h, carrier, a.sr, a.depth)
        write_wav(out / "dualcast_pair.wav", stereo, a.sr)
        nulls = null_analysis(stereo, a.sr, rec.t_model, rec.phi_r, rec.phi_h, sc.n, a.depth)
        dep = nulls["_depths"]
        write_csv(out / "nulls.csv", ["t_s", "predicted_depth", "measured_depth"],
                  [dep["t_s"], dep["predicted"], dep["measured"]])
        heart = float((rec.phi_h[-1] - rec.phi_h[0]) / (2 * np.pi * (rec.t_model[-1] - rec.t_model[0])))
        result["sonification"] = {"carrier_hz": carrier, "carrier_source": "alias of the source's 8.5 THz at its "
                                  "9999 Hz grid" if a.carrier == "source" else "given", "sample_rate": a.sr,
                                  "depth": a.depth, "mean_heart_hz": heart, "left_hz": carrier - heart / 2,
                                  "right_hz": carrier + heart / 2, **nulls}
    (out / "assessment.json").write_text(json.dumps(_clean(result), indent=2) + "\n")
    _emit(result)
    return 0


def cmd_envelope(a: argparse.Namespace) -> int:
    bins = tuple(int(v) for v in a.bins.lower().split("x"))
    axes = tuple(v.strip() for v in a.axes.split(","))
    if len(bins) != 2:
        raise ValueError(f"--bins must look like 6x6, got {a.bins!r}")
    cfg = EnvelopeConfig(target=a.target, axes=axes, bins=bins, iterations=a.iterations, initial=a.initial,
                         surrogates=a.surrogates, alpha=a.alpha, replays=a.replays)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res = failure_map(a.name, cfg, progress=(lambda row: print(
        f"  {row[0]:4d} evaluations  coverage {row[1]:.2f}  worst {row[3]:.3f}", file=sys.stderr)) if not a.quiet else None)
    (out / "archive.json").write_text(json.dumps(_clean(res), indent=2) + "\n")
    grid, edges = res["worst_case_map"]["fitness"], res["worst_case_map"]["edges"]
    e0, e1 = edges[axes[0]], edges[axes[1]]
    header = [f"{axes[0]}\\{axes[1]}"] + [f"{e1[j]:.3g}-{e1[j + 1]:.3g}" for j in range(bins[1])]
    rows = [f"{e0[i]:.3g}-{e0[i + 1]:.3g}" for i in range(bins[0])]
    cols = [rows] + [["" if grid[i][j] is None else f"{grid[i][j]:.3f}" for i in range(bins[0])] for j in range(bins[1])]
    write_csv(out / "map.csv", header, cols)
    _emit({k: res[k] for k in ("name", "evaluations", "coverage", "baseline", "reproducible_failures",
                               "safe_cells", "failures", "worst_case_map")} | {"target": a.target})
    return 0


# ============================================================================================ parser

def _source_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("file", help=".wav, .npy, or text columns")
    p.add_argument("--column", help="column name or index (needed when the file has several)")
    p.add_argument("--fs", type=float, help="sample rate, Hz (not needed for .wav or with --time-column)")
    p.add_argument("--time-column", help="column of sample times in seconds")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m infrasonomancer", description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("compose", help="seed text (and optional genome) → render.wav, score.mid, report.json")
    p.add_argument("seed")
    p.add_argument("--genome", help="genome.json, report.json, an archive elite, or inline JSON")
    p.add_argument("--seconds", type=float, default=32.0)
    p.add_argument("--density", type=float, help="fraction of lattice cells that sound (default 0.08)")
    p.add_argument("--voices", type=int, default=4)
    p.add_argument("--sr", type=int, default=22050)
    p.add_argument("--stereo", action="store_true", help="pulse in antiphase between left and right")
    p.add_argument("--out", default="out")
    p.set_defaults(func=cmd_compose)

    p = sub.add_parser("evolve", help="MAP-Elites over genomes; renders the champion")
    p.add_argument("seed")
    p.add_argument("--objective", choices=OBJECTIVES, default="recurrence")
    p.add_argument("--iterations", type=int, default=240)
    p.add_argument("--initial", type=int, default=24)
    p.add_argument("--bins", default="6x6", help="edge-dimension bins x pitch-entropy bins")
    p.add_argument("--mutation-scale", type=float, default=1.0)
    p.add_argument("--seconds", type=float, default=32.0)
    p.add_argument("--voices", type=int, default=4)
    p.add_argument("--sr", type=int, default=22050)
    p.add_argument("--stereo", action="store_true")
    p.add_argument("--render-top", type=int, default=1, help="render the best K elites")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--out", default="out/evolve")
    p.set_defaults(func=cmd_evolve)

    p = sub.add_parser("beats", help="heartbeats from ECG or PPG, and HRV")
    _source_args(p)
    p.add_argument("--kind", choices=("ecg", "ppg"), required=True)
    p.add_argument("--out", help="write beat times to this CSV")
    p.set_defaults(func=cmd_beats)

    p = sub.add_parser("coherence", help="n:m synchronization of two rhythms with surrogate p-values")
    for side in ("x", "y"):
        p.add_argument(f"--{side}", required=True, metavar="FILE")
        p.add_argument(f"--{side}-kind", choices=("signal", "ecg", "ppg", "beats", "rr"), required=True)
        p.add_argument(f"--{side}-column")
        p.add_argument(f"--{side}-fs", type=float)
        p.add_argument(f"--{side}-time-column")
        p.add_argument(f"--{side}-band", metavar="LO,HI", help="pass band for kind=signal (default: around the "
                                                               "dominant rhythm)")
        p.add_argument(f"--{side}-unit", type=float, default=1.0, help="seconds per file unit for beats/rr")
    p.add_argument("--window", type=float, default=30.0)
    p.add_argument("--step", type=float, default=5.0)
    p.add_argument("--rate", type=float, default=10.0, help="phase sampling rate for the analysis, Hz")
    p.add_argument("--max-n", type=int, default=12)
    p.add_argument("--max-m", type=int, default=3)
    p.add_argument("--surrogates", type=int, default=199)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--out", help="directory for coherence.json, windows.csv, synchrogram.csv")
    p.set_defaults(func=cmd_coherence)

    p = sub.add_parser("pll", help="track a rhythm with a phase-locked loop")
    _source_args(p)
    p.add_argument("--f0", type=float, required=True, help="free-running frequency, Hz")
    p.add_argument("--bandwidth", type=float, default=2.0)
    p.add_argument("--zeta", type=float, default=0.707)
    p.add_argument("--lock-threshold", type=float, default=0.6)
    p.add_argument("--out", help="write the frequency track to this CSV")
    p.set_defaults(func=cmd_pll)

    p = sub.add_parser("series", help="dominant rate, Hurst, DFA and recurrence of a series")
    _source_args(p)
    p.add_argument("--points", type=int, default=48, help="embedding points for persistent homology (≤ 80)")
    p.add_argument("--fmin", type=float, default=0.01)
    p.add_argument("--fmax", type=float)
    p.add_argument("--out", help="also write the JSON here")
    p.set_defaults(func=cmd_series)

    p = sub.add_parser("fractal", help="box-counting dimension of a Julia set or of an image")
    p.add_argument("--c", metavar="RE,IM", help="Julia parameter; Douady's rabbit is --c=-0.123,0.745")
    p.add_argument("--seed", help="the Julia parameter a seed text chooses")
    p.add_argument("--image", help=".png or .npy image; the foreground is found by Otsu's threshold")
    p.add_argument("--foreground", choices=("minority", "dark", "light"), default="minority")
    p.add_argument("--size", type=int, default=512)
    p.add_argument("--iter", type=int, default=200)
    p.add_argument("--png", help="write the Julia set (or the image mask) as PNG")
    p.set_defaults(func=cmd_fractal)

    p = sub.add_parser("dualcast", help="the source's dual-wavelength cast, reproduced exactly and measured")
    d = DualCast()
    p.add_argument("--carrier", type=float, default=d.carrier)
    p.add_argument("--deviation", type=float, default=d.deviation)
    p.add_argument("--samples", type=int, default=d.samples)
    p.add_argument("--duration", type=float, default=d.duration)
    p.add_argument("--data-rate", type=float, default=d.data_rate)
    p.add_argument("--rc-tau", type=float, default=d.rc_tau)
    p.add_argument("--exact", action="store_true", help="write exact-phase signals instead of the float64 ones")
    p.add_argument("--out", default="out/dualcast")
    p.set_defaults(func=cmd_dualcast)

    p = sub.add_parser("cardioresp", help="breath and heart as coupled oscillators: raw recording and assessment")
    s = Scenario()
    p.add_argument("--scenario", help="scenario JSON (inline, a file, or an envelope failure entry)")
    p.add_argument("--n", type=int, default=s.n, help="heart cycles ...")
    p.add_argument("--m", type=int, default=s.m, help="... per m breaths")
    p.add_argument("--breath-hz", type=float, default=s.breath_hz)
    p.add_argument("--detuning", type=float, default=s.detuning, help="δ across the Arnold tongue; |δ| < 1 locks")
    p.add_argument("--coupling", type=float, default=s.coupling, help="ε, rad/s")
    p.add_argument("--phase-noise", type=float, default=s.phase_noise)
    p.add_argument("--breath-noise", type=float, default=s.breath_noise)
    p.add_argument("--sensor-noise", type=float, default=s.sensor_noise)
    p.add_argument("--seconds", type=float, default=s.seconds)
    p.add_argument("--fs", type=float, default=s.fs)
    p.add_argument("--seed", default="cardioresp")
    p.add_argument("--surrogates", type=int, default=99)
    p.add_argument("--sonify", action="store_true", help="render the locked counter-pair (dualcast_pair.wav)")
    p.add_argument("--carrier", default="source", help="'source' = what the 8.5 THz value actually made (4991 Hz), "
                                                       "or a frequency in Hz")
    p.add_argument("--sr", type=int, default=22050)
    p.add_argument("--depth", type=float, default=0.35)
    p.add_argument("--out", default="out/cardioresp")
    p.set_defaults(func=cmd_cardioresp)

    p = sub.add_parser("cascade", help="voices that beat, lock and set off the next, higher generation")
    k = CascadeConfig()
    p.add_argument("--config", help="cascade.json from an earlier run (or a config JSON) to reproduce it")
    p.add_argument("--seed", default=k.seed)
    p.add_argument("--generators", default=",".join(k.generators), help="ratios > 1, e.g. 2,3 or 2,3/2 or 2,3,5")
    p.add_argument("--depth", type=int, default=k.depth)
    p.add_argument("--f0", type=float, default=None, help="root in Hz (default: from the seed, 55–82.4 Hz)")
    p.add_argument("--f-max", type=float, default=k.f_max)
    p.add_argument("--min-cents", type=float, default=k.min_cents, help="consonance guard; 0 turns it off")
    p.add_argument("--beat-hz", type=float, default=k.beat_hz, help="detuning bound per voice")
    p.add_argument("--coupling", type=float, default=k.coupling, help="> 1 locks; < 1 beats until it adapts")
    p.add_argument("--no-adapt", action="store_true", help="keep each pair's coupling as sized at birth")
    p.add_argument("--backreaction", type=float, default=k.backreaction)
    p.add_argument("--ramp", type=float, default=k.ramp_s)
    p.add_argument("--dwell", type=float, default=k.dwell_s)
    p.add_argument("--lock-hz", type=float, default=k.lock_hz)
    p.add_argument("--stagger", type=float, default=k.stagger_s)
    p.add_argument("--attack", type=float, default=k.attack_s)
    p.add_argument("--harmonics", type=int, default=k.harmonics)
    p.add_argument("--rolloff", type=float, default=k.rolloff)
    p.add_argument("--tilt", type=float, default=k.tilt_db_oct, help="dB per octave above f0")
    p.add_argument("--breath-hz", type=float, default=k.breath_hz, help="slow swell; 0 turns it off")
    p.add_argument("--breath-depth", type=float, default=k.breath_depth)
    p.add_argument("--tail", type=float, default=k.tail_s)
    p.add_argument("--fade", type=float, default=k.fade_s)
    p.add_argument("--max-seconds", type=float, default=k.max_seconds)
    p.add_argument("--sr", type=int, default=22050)
    p.add_argument("--mono", action="store_true")
    p.add_argument("--out", default="out/cascade")
    p.set_defaults(func=cmd_cascade)

    p = sub.add_parser("envelope", help="MAP-Elites over scenarios: where do the instruments fail?")
    p.add_argument("--target", choices=TARGETS, default=EnvelopeConfig.target)
    p.add_argument("--axes", default="detuning,sensor_noise", help=f"two of {','.join(sorted(AXES))}")
    p.add_argument("--bins", default="6x6")
    p.add_argument("--iterations", type=int, default=160)
    p.add_argument("--initial", type=int, default=24)
    p.add_argument("--surrogates", type=int, default=39)
    p.add_argument("--alpha", type=float, default=0.05)
    p.add_argument("--replays", type=int, default=3)
    p.add_argument("--name", default="envelope")
    p.add_argument("--quiet", action="store_true")
    p.add_argument("--out", default="out/envelope")
    p.set_defaults(func=cmd_envelope)
    return ap


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        return a.func(a)
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
