"""The coupled-oscillator model against Adler's equation, and the raw signals against their own ground truth."""
import math
import unittest

import numpy as np

from infrasonomancer import detect_beats
from infrasonomancer.cardioresp import Scenario, assess, cycle_times, simulate

QUIET = dict(phase_noise=0.0, breath_noise=0.0, seconds=300.0)


class ArnoldTongue(unittest.TestCase):
    def test_inside_the_tongue_the_phase_difference_settles_at_asin_delta(self):
        for n, m, delta in ((4, 1, 0.5), (9, 2, -0.7)):
            rec = simulate(Scenario(n=n, m=m, detuning=delta, **QUIET))
            psi = n * rec.phi_r[-1] - m * rec.phi_h[-1]
            self.assertAlmostEqual(math.remainder(psi - math.asin(delta), 2 * math.pi), 0.0, delta=0.01)
            self.assertGreater(rec.truth["true_index"], 0.99)
            self.assertLess(rec.truth["phase_slips"], 0.2)

    def test_outside_it_the_phase_slips_at_the_adler_rate(self):
        for n, m, delta, eps in ((4, 1, 1.5, 0.3), (4, 1, 2.0, 0.2), (7, 2, 1.8, 0.25)):
            rec = simulate(Scenario(n=n, m=m, detuning=delta, coupling=eps, **QUIET))
            span = rec.t_model[-1] - rec.t_model[len(rec.t_model) // 10]
            expected = span * m * eps * math.sqrt(delta ** 2 - 1) / (2 * math.pi)
            self.assertAlmostEqual(rec.truth["phase_slips"], expected, delta=0.03 * expected + 1.0)

    def test_a_drifting_pair_keeps_a_non_uniform_phase_difference(self):
        for delta in (1.5, 2.0, 3.0):                                       # Adler: R = |δ| − √(δ² − 1)
            rec = simulate(Scenario(detuning=delta, coupling=0.6, **dict(QUIET, seconds=600.0)))
            self.assertAlmostEqual(rec.truth["true_index"], delta - math.sqrt(delta ** 2 - 1), delta=0.01)

    def test_heart_rate_and_validation(self):
        sc = Scenario(n=4, m=1, breath_hz=0.25, detuning=1.0, coupling=2 * math.pi * 0.05)
        self.assertAlmostEqual(sc.heart_hz, 0.95)
        for bad in (dict(n=4, m=2), dict(breath_hz=0.9, n=11), dict(seconds=30.0), dict(fs=100.0),
                    dict(coupling=0.0)):
            with self.assertRaises(ValueError):
                Scenario(**bad).validate()
        sc = Scenario(n=7, m=2, detuning=0.4)
        self.assertEqual(Scenario.from_dict({**sc.to_dict(), "extra": 1}), sc)


class RawSignals(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = simulate(Scenario(seconds=120.0))

    def test_cycle_times_of_a_linear_phase(self):
        t = np.arange(0, 10.0, 0.01)
        self.assertTrue(np.allclose(cycle_times(t, 2 * np.pi * 1.3 * t), np.arange(1, 13) / 1.3))

    def test_ecg_beats_are_recovered_from_the_raw_trace(self):
        rec = self.rec
        found = detect_beats(rec.ecg, rec.scenario.fs, "ecg")
        self.assertEqual(len(found), len(rec.beats))
        self.assertLess(np.abs(found - rec.beats).max(), 0.002)
        ppg = detect_beats(rec.ppg, rec.scenario.fs, "ppg")
        self.assertEqual(len(ppg), len(rec.beats))
        self.assertLess(np.std(ppg - rec.beats), 0.003)
        self.assertEqual(len(rec.resp), len(rec.t))

    def test_deterministic(self):
        again = simulate(Scenario(seconds=120.0))
        self.assertTrue(np.array_equal(again.ecg, self.rec.ecg))
        self.assertFalse(np.array_equal(simulate(Scenario(seconds=120.0), seed="other").ecg, self.rec.ecg))


class Assessment(unittest.TestCase):
    def test_locked_and_unlocked_are_told_apart_by_both_chains(self):
        a = assess(simulate(Scenario()), surrogates=39)
        self.assertEqual((a["oracle_call"], a["pipeline_call"]), ("right", "right"))
        self.assertTrue(a["truth"]["locked"] and a["oracle_locked"] and a["pipeline_locked"])
        self.assertEqual(a["pipeline"]["ratio"], "4:1")
        self.assertLess(abs(a["pipeline"]["net_slips"]), 1)
        self.assertLess(a["pipeline"]["beat_error_ms_median"], 1.0)
        b = assess(simulate(Scenario(detuning=2.5)), surrogates=39)
        self.assertFalse(b["truth"]["locked"])
        self.assertGreater(abs(b["truth"]["net_slips"]), 5)
        self.assertEqual((b["oracle_call"], b["pipeline_call"]), ("right", "right"))


if __name__ == "__main__":
    unittest.main()
