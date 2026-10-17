"""Recoherence cascade: exact lattice, Adler's slip rate, births caused by locks, the climb in the audio, the CLI."""
import contextlib
import io
import json
import math
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

import numpy as np

import infrasonomancer as I
from infrasonomancer.__main__ import main
from infrasonomancer.cascade import _lattice, held_at_end, parse_generators

FAST = dict(ramp_s=2.0, dwell_s=1.0, stagger_s=0.5, attack_s=1.0, tail_s=4.0, fade_s=2.0, max_seconds=120.0)


def centroid(x: np.ndarray, sr: int) -> float:
    power = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2
    return float(np.sum(power * np.fft.rfftfreq(len(x), 1 / sr)) / np.sum(power))


def slip_rate(psi: np.ndarray, t: np.ndarray, j: int) -> float:
    """Mean |dψ/dt| over whole slips only: from t[j] to the last crossing of ψ(t[j]) ± 2πm."""
    d = np.abs(psi[j:] - psi[j])
    m = int(d[-1] // (2 * np.pi))
    k = int(np.searchsorted(d, 2 * np.pi * m))                       # d is monotone while the pair slips
    tk = np.interp(2 * np.pi * m, d[k - 1:k + 1], t[j:][k - 1:k + 1])
    return 2 * np.pi * m / (tk - t[j])


class Lattice(unittest.TestCase):
    def test_voices_are_exact_products_and_coupled_on_a_tree(self):
        cfg = I.CascadeConfig(generators=("2", "3/2"), depth=3, f0=55.0, min_cents=0)
        voices, pairs = _lattice(parse_generators(cfg.generators), cfg, 55.0, I.Chaos("lattice"))
        expect = sorted(Fraction(2) ** a * Fraction(3, 2) ** b for a in range(4) for b in range(4) if a + b <= 3)
        self.assertEqual(sorted(v.ratio for v in voices), expect)
        for e in pairs:
            child, parent = voices[e.child], voices[e.parent]
            self.assertEqual(e.q * child.ratio, e.p * parent.ratio)            # coincident partials, exactly
            self.assertEqual(child.depth, parent.depth + 1)
        per_child = np.bincount([e.child for e in pairs if e.coupled], minlength=len(voices))
        self.assertEqual(per_child.tolist(), [0] + [1] * (len(voices) - 1))   # one coupled parent each: a tree
        self.assertEqual(sum(not e.coupled for e in pairs), 3)                # 3, 9/2 and 27/8 … the merges
        self.assertEqual(voices[0].pan, 0.0)
        self.assertTrue(all(abs(v.pan) <= 0.8 + 1e-12 for v in voices))

    def test_consonance_guard_skips_a_limma_and_its_line(self):
        g = parse_generators(("2", "3/2"))
        off = I.CascadeConfig(generators=("2", "3/2"), depth=5, f0=55.0, min_cents=0)
        on = I.CascadeConfig(generators=("2", "3/2"), depth=5, f0=55.0)
        self.assertIn(Fraction(243, 32), [v.ratio for v in _lattice(g, off, 55.0, I.Chaos("x"))[0]])
        kept = [v.ratio for v in _lattice(g, on, 55.0, I.Chaos("x"))[0]]
        self.assertNotIn(Fraction(243, 32), kept)                              # 90 cents below 8
        cents = [abs(1200 * math.log2(a / b)) for a in kept for b in kept if a != b]
        self.assertGreaterEqual(min(cents), 150)

    def test_rejects_what_cannot_work(self):
        for gens in (("1",), ("2", "4"), ("3/2", "9/4"), ("17/16",), ("abc",)):
            with self.assertRaises(ValueError):
                parse_generators(gens)
        with self.assertRaises(ValueError):
            I.CascadeConfig(generators=("2", "5/4"), harmonics=4).validate()   # coupling needs partial 5
        with self.assertRaises(ValueError):
            I.CascadeConfig(beat_hz=4.0).validate()                            # beats too fast for the control rate


class Dynamics(unittest.TestCase):
    def pair(self, coupling: float) -> I.Cascade:
        return I.recohere(I.CascadeConfig(seed="adler pair", generators=("3/2",), depth=1, coupling=coupling,
                                          adapt=False, ramp_s=0.01, max_seconds=60.0, tail_s=1.0, fade_s=0.0))

    def test_slip_rate_below_threshold_is_adlers(self):
        c = self.pair(0.6)
        e = c.pairs[0]
        self.assertGreater(abs(e.delta) / (2 * np.pi), 0.2)                   # the seed gives a clear beat
        self.assertFalse(np.isfinite(c.coherent[1]))
        expected = math.sqrt(e.delta ** 2 - ((1 + c.config.backreaction) * e.k_max) ** 2)
        self.assertAlmostEqual(slip_rate(c.psi(0), c.t, int(5 * c.config.control_hz)) / expected, 1.0, delta=2e-3)

    def test_locks_above_threshold_at_adlers_phase(self):
        c = self.pair(1.5)
        e = c.pairs[0]
        self.assertTrue(np.isfinite(c.coherent[1]) and held_at_end(c) == [True])
        psi_star = math.asin(e.delta / ((1 + c.config.backreaction) * e.k_max))
        self.assertAlmostEqual(math.sin(c.psi(0)[-1]), math.sin(psi_star), places=4)

    def test_adaptation_rescues_a_weak_pair(self):
        c = I.recohere(I.CascadeConfig(seed="adler pair", generators=("3/2",), depth=1, coupling=0.6, ramp_s=1.0,
                                       max_seconds=60.0, tail_s=1.0, fade_s=0.0))
        e = c.pairs[0]
        self.assertTrue(np.isfinite(c.coherent[1]))
        self.assertGreater((1 + c.config.backreaction) * e.k_max, abs(e.delta))


class Cascade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = I.CascadeConfig(seed="unit cascade", depth=3, **FAST)
        cls.c = I.recohere(cls.cfg)
        cls.sr = 8000
        cls.audio = I.render_cascade(cls.c, cls.sr)
        cls.tl = I.cascade_timeline(cls.c, sr=cls.sr)
        cls.rep = I.cascade_report(cls.c, cls.tl)

    def test_every_voice_locks_and_holds(self):
        r = self.rep
        self.assertTrue(r["all_coherent"] and r["all_held_at_end"])
        self.assertEqual(r["voices"], 10)
        self.assertGreater(r["timeline"]["coherence_end"], 0.999)
        self.assertLess(r["timeline"]["beat_index_end"], 1e-3)
        self.assertGreater(r["timeline"]["beat_index_peak"], 0.02)            # it did beat before it locked
        self.assertAlmostEqual(r["seconds"], r["cascade_complete_s"] + FAST["tail_s"] + FAST["fade_s"], delta=0.02)

    def test_births_are_caused_by_parents_locking(self):
        c = self.c
        for v in c.voices[1:]:
            self.assertGreaterEqual(c.born[v.index], max(c.coherent[list(v.parents)]) - 1e-9)
            self.assertGreaterEqual(c.coherent[v.index], c.born[v.index] + self.cfg.dwell_s - 1e-9)
        first = [min(c.born[v.index] for v in c.voices if v.depth == d) for d in range(4)]
        self.assertEqual(first, sorted(first))

    def test_the_audio_climbs(self):
        sr, x = self.sr, self.audio
        self.assertEqual(x.shape, (int(self.c.seconds * sr), 2))
        self.assertAlmostEqual(float(np.max(np.abs(x))), 0.89, places=6)
        mono = I.render_cascade(self.c, sr, stereo=False)                      # the timeline ignores panning
        t0, t1 = self.c.complete_s, self.c.complete_s + FAST["tail_s"]
        early = centroid(mono[:int(2.0 * sr)], sr)
        late = centroid(mono[int(t0 * sr):int(t1 * sr)], sr)
        self.assertGreater(late, 1.4 * early)
        tl = self.tl
        predicted = float(np.nanmean(tl["centroid_hz"][(tl["t_s"] >= t0) & (tl["t_s"] < t1)]))
        self.assertAlmostEqual(late / predicted, 1.0, delta=0.15)             # the model describes the sound

    def test_deterministic_per_seed(self):
        np.testing.assert_array_equal(I.render_cascade(I.recohere(self.cfg), self.sr), self.audio)
        self.assertNotEqual(I.recohere(I.CascadeConfig(seed="another", depth=1, **FAST)).f0, self.c.f0)

    def test_perceptual_proxies(self):
        self.assertAlmostEqual(float(I.fluctuation_weight(4.0)), 1.0)
        self.assertEqual(float(I.fluctuation_weight(0.0)), 0.0)
        self.assertLess(float(I.fluctuation_weight(16.0)), 0.5)
        d = lambda df: I.sethares_dissonance([400.0, 400.0 + df], [1.0, 1.0])  # noqa: E731
        self.assertEqual(d(0.0), 0.0)
        self.assertGreater(d(25.0), d(2.0))                                    # the Plomp–Levelt hump …
        self.assertGreater(d(25.0), d(120.0))                                  # … peaks near a quarter band


class Cli(unittest.TestCase):
    def test_cascade_command_writes_and_reproduces(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            args = ["cascade", "--seed", "cli cascade", "--depth", "2", "--ramp", "2", "--dwell", "1", "--stagger",
                    "0.5", "--attack", "1", "--tail", "3", "--fade", "1", "--sr", "8000", "--out", str(d / "a")]
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(args), 0)
            brief = json.loads(out.getvalue())
            self.assertTrue(brief["all_coherent"])
            self.assertNotIn("voice_table", brief)
            rep = json.loads((d / "a" / "cascade.json").read_text())
            rows = (d / "a" / "timeline.csv").read_text().splitlines()
            self.assertEqual(rows[0], "t_s,voices,coherence,beat_index,max_beat_hz,dissonance,centroid_hz")
            self.assertEqual(len(rows) - 1, math.ceil(rep["seconds"] / 0.25 - 1e-9))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["cascade", "--config", str(d / "a" / "cascade.json"), "--sr", "8000",
                                       "--out", str(d / "b")]), 0)
            self.assertEqual((d / "a" / "cascade.wav").read_bytes(), (d / "b" / "cascade.wav").read_bytes())
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(["cascade", "--generators", "2,4", "--out", str(d / "c")]), 1)


if __name__ == "__main__":
    unittest.main()
