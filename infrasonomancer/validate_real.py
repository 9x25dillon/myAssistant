#!/usr/bin/env python3
"""Validate the physiology endpoints on two real recordings, end to end and reproducibly.

    python validate_real.py --data biodata --fetch --out validation.json

Data (downloaded from PyPI with --fetch, SHA-256 checked, used locally, never redistributed; both GPL-3.0):
    pyphysio 4.10.0 wheel   test_data/medical.txt.bz2   ECG, EDA, BVP, respiration; 120 s at 2048 Hz.
                            The bundled info file says 1024 Hz; pyphysio's own loader uses 2048 Hz, and only 2048 Hz
                            gives the documented 120 s and a physiological heart rate (both are reported below).
    systole 0.3.1 sdist     datasets/Task1_ECG.npy, Task1_Respiration.npy   ~25.6 min at 1000 Hz, one healthy adult
                            during an emotional picture task (Legrand & Allen 2022).

Checks, none of which uses a reference annotation (there is none in either package):
    1. two sensors, one heart: every ECG R wave should be followed by one BVP pulse at a near-constant transit time
    2. two sensors, one breath: heart rate from the ECG should be coherent with the respiration belt at the
       breathing rate (respiratory sinus arrhythmia), tested against time-shift surrogates, block by block; the HRV
       HF spectral peak is printed beside it because it is the common shortcut, and it is the weaker test
    3. cardiorespiratory phase synchronization, with surrogate p-values: reported as found, whatever it is
"""

from __future__ import annotations

import argparse
import bz2
import hashlib
import io
import json
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import infrasonomancer as I                                                      # noqa: E402
from infrasonomancer.__main__ import _clean                                     # noqa: E402

SOURCES = {
    "pyphysio-4.10.0-py3-none-any.whl": (
        "https://files.pythonhosted.org/packages/a1/b1/220f1584a0902725a2817903d05938670eb61f5053f638c2fcff6e61f6e0/"
        "pyphysio-4.10.0-py3-none-any.whl", "fee94db877b7366354911e4adb94b902be8447d6bc834aad9c6656a584e81088"),
    "systole-0.3.1.tar.gz": (
        "https://files.pythonhosted.org/packages/db/f1/91738b0927b1055f2efc7afbac8233493b32d7c3dd943eb80a7e715c21d0/"
        "systole-0.3.1.tar.gz", "9bc145f7b87caa57b53e45f34276bcfefec101bc1c662e4e104f53fdfa5a405a"),
}
FILES = ("medical.tsv", "Task1_ECG.npy", "Task1_Respiration.npy")


def fetch(data: Path) -> None:
    """Download, verify and extract only the named members to fixed names (no archive paths are trusted)."""
    data.mkdir(parents=True, exist_ok=True)
    blobs = {}
    for name, (url, digest) in SOURCES.items():
        cached = data / "_downloads" / name
        if not cached.exists():
            cached.parent.mkdir(exist_ok=True)
            print(f"downloading {name}", file=sys.stderr)
            with urllib.request.urlopen(url, timeout=120) as r:
                cached.write_bytes(r.read())
        blob = cached.read_bytes()
        if hashlib.sha256(blob).hexdigest() != digest:
            raise SystemExit(f"{name}: SHA-256 mismatch; delete {cached} and retry")
        blobs[name] = blob
    with zipfile.ZipFile(io.BytesIO(blobs["pyphysio-4.10.0-py3-none-any.whl"])) as z:
        (data / "medical.tsv").write_bytes(bz2.decompress(z.read("pyphysio/test_data/medical.txt.bz2")))
    with tarfile.open(fileobj=io.BytesIO(blobs["systole-0.3.1.tar.gz"]), mode="r:gz") as t:
        for member in ("Task1_ECG.npy", "Task1_Respiration.npy"):
            f = t.extractfile(f"systole-0.3.1/src/systole/datasets/{member}")
            (data / member).write_bytes(f.read())


def match_pulses(r: np.ndarray, p: np.ndarray, lo: float = 0.05, hi: float = 0.6) -> dict:
    j = np.searchsorted(p, r + lo)
    ok = j < len(p)
    lag = np.full(len(r), np.nan)
    lag[ok] = p[j[ok]] - r[ok]
    good = (lag >= lo) & (lag <= hi)
    used = set(j[good].tolist())
    return {"r_waves": len(r), "pulses": len(p), "r_followed_by_a_pulse": int(good.sum()),
            "transit_ms": {"median": 1e3 * float(np.median(lag[good])), "sd": 1e3 * float(np.std(lag[good])),
                           "iqr": [1e3 * float(q) for q in np.percentile(lag[good], [25, 75])]},
            "r_without_pulse_s": np.round(r[~good], 2).tolist(),
            "pulses_without_r_s": np.round([p[k] for k in range(len(p)) if k not in used], 2).tolist()}


def blocks(beats: np.ndarray, resp: np.ndarray, fs: float, band: tuple[float, float],
           seconds: float = 300.0) -> list[dict]:
    """Per block: the HRV HF peak, and the coherence of breathing with heart rate (its peak and surrogate p)."""
    out = []
    for t0 in np.arange(0.0, len(resp) / fs - seconds / 2, seconds):
        t1 = min(t0 + seconds, len(resp) / fs)
        b = beats[(beats >= t0) & (beats < t1)]
        seg = resp[int(t0 * fs):int(t1 * fs)]
        c = I.rate_coupling(seg, fs, b - t0, band=band, surrogates=199, seed=f"block {t0:.0f}")
        h = I.hrv(b)
        out.append({"t_s": [float(t0), float(t1)], "mean_hr_bpm": h.get("mean_hr_bpm"), "hf_peak_hz": h.get("hf_peak_hz"),
                    "respiration_clipped_samples": int(np.sum(seg <= resp.min() + 1e-9)),
                    "breathing_peak_hz": c["signal_peak_hz"], "coherence_at_breathing": c["msc_at_signal_peak"],
                    "p": c["p_at_signal_peak"], "in_band_max": [c["peak_hz"], c["peak_msc"], c["p"]]})
    return out


def pyphysio(data: Path) -> dict:
    names, table = I.read_table(data / "medical.tsv")
    fs = 2048.0
    ecg, bvp, resp = table[:, 0], table[:, 2], table[:, 3]
    r = I.detect_beats(ecg, fs, "ecg")
    p = I.detect_beats(bvp, fs, "ppg")
    hr_ecg, hr_bvp = I.hrv(r), I.hrv(p)
    breath = I.stream_from_signal(resp, fs, band=(0.1, 0.5))
    sync = I.synchronize(breath, I.stream_from_events(r), surrogates=199)
    dominant = I.dominant_frequency(resp[::16], fs / 16, 0.05, 1.0)
    return {
        "samples": len(table), "sample_rate_check": {
            "fs_1024": {"seconds": len(table) / 1024, "mean_hr_bpm": hr_ecg["mean_hr_bpm"] / 2},
            "fs_2048": {"seconds": len(table) / 2048, "mean_hr_bpm": hr_ecg["mean_hr_bpm"]}},
        "ecg_hrv": hr_ecg, "bvp_hrv": hr_bvp, "ecg_vs_bvp": match_pulses(r, p),
        "breathing": {"dominant_hz": dominant, "mean_phase_rate_hz": breath.rate_hz, **breath.info},
        "rsa_check": {"hf_peak_hz": hr_ecg.get("hf_peak_hz"), "breathing_dominant_hz": dominant,
                      "difference_hz": abs(hr_ecg.get("hf_peak_hz", np.nan) - dominant)},
        "rate_coupling": I.rate_coupling(resp, fs, r, band=(0.1, 0.5), seconds=30.0),
        "synchronization": sync,
    }


def systole(data: Path) -> dict:
    fs = 1000.0
    ecg = np.load(data / "Task1_ECG.npy", allow_pickle=False)
    resp = np.load(data / "Task1_Respiration.npy", allow_pickle=False)
    r = I.detect_beats(ecg, fs, "ecg")
    breath = I.stream_from_signal(resp, fs, band=(0.15, 0.5))
    per_block = blocks(r, resp, fs, (0.15, 0.5))
    return {
        "seconds": len(ecg) / fs, "respiration_clipped_samples": int(np.sum(resp <= resp.min() + 1e-9)),
        "ecg_hrv": I.hrv(r),
        "breathing": {"mean_phase_rate_hz": breath.rate_hz, **breath.info},
        "rate_coupling": I.rate_coupling(resp, fs, r, band=(0.15, 0.5)),
        "rsa_blocks": per_block,
        "synchronization": I.synchronize(breath, I.stream_from_events(r), surrogates=199),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", required=True, help="directory holding (or receiving) the recordings")
    ap.add_argument("--fetch", action="store_true", help="download and verify the recordings from PyPI first")
    ap.add_argument("--out", default="validation.json")
    a = ap.parse_args(argv)
    data = Path(a.data)
    if a.fetch:
        fetch(data)
    missing = [f for f in FILES if not (data / f).exists()]
    if missing:
        print(f"error: {missing} not in {data}; run with --fetch", file=sys.stderr)
        return 1
    result = {"pyphysio_medical": pyphysio(data), "systole_task1": systole(data)}
    Path(a.out).write_text(json.dumps(_clean(result), indent=2) + "\n")
    p, s = result["pyphysio_medical"], result["systole_task1"]
    m = p["ecg_vs_bvp"]
    print(f"pyphysio: {m['r_waves']} R waves, {m['pulses']} pulses, {m['r_followed_by_a_pulse']} matched; transit "
          f"{m['transit_ms']['median']:.1f} ± {m['transit_ms']['sd']:.1f} ms; unmatched R at {m['r_without_pulse_s']}")
    print(f"          HR {p['ecg_hrv']['mean_hr_bpm']:.1f} bpm; breathing {p['rsa_check']['breathing_dominant_hz']:.4f} Hz"
          f" vs HRV HF peak {p['rsa_check']['hf_peak_hz']:.4f} Hz")
    for name, r in (("pyphysio", p), ("systole", s)):
        w, win = r["synchronization"]["whole_record"], r["synchronization"]["windows"]
        print(f"{name:9s} sync {w['ratio']} index {w['index']:.3f} (surrogates {w['surrogate_mean']:.3f}) p {w['p']:.2f},"
              f" {w['net_slips']:+.1f} net slips: {w['verdict']}; windows locked {win['locked_fraction']:.3f} vs "
              f"{win['locked_fraction_expected']:.3f} p {win['p']:.2f}")
    for name, r in (("pyphysio", p), ("systole", s)):
        c = r["rate_coupling"]
        print(f"{name:9s} breathing↔heart-rate coherence at the breathing peak {c['signal_peak_hz']:.3f} Hz: "
              f"{c['msc_at_signal_peak']:.2f} (p {c['p_at_signal_peak']:.3f}); in-band maximum {c['peak_msc']:.2f} at "
              f"{c['peak_hz']:.3f} Hz (p {c['p']:.3f}), {c['segments']} segments of {c['segment_s']:g} s")
    print(f"systole:  {s['ecg_hrv']['beats']} beats, {s['ecg_hrv']['intervals_excluded']} intervals excluded, HR "
          f"{s['ecg_hrv']['mean_hr_bpm']:.1f} bpm; per 5 min:")
    for b in s["rsa_blocks"]:
        print(f"          {b['t_s'][0]:6.0f}–{b['t_s'][1]:6.0f} s  breathing {b['breathing_peak_hz']:.3f} Hz  coherence "
              f"{b['coherence_at_breathing']:.2f} (p {b['p']:.3f})  clipped {b['respiration_clipped_samples']:4d}  "
              f"HRV HF peak {b['hf_peak_hz']:.3f}  HR {b['mean_hr_bpm']:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
