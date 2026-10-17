"""The source's dual-wavelength cast, and the counter-pair render, against exact answers."""
import unittest

import numpy as np

import infrasonomancer as I
import infrasonomancer.dualcast as D
from infrasonomancer.cardioresp import Scenario, simulate

try:
    from scipy.signal import chirp, fftconvolve
except ImportError:                                                        # pragma: no cover
    chirp = fftconvolve = None


class SourceReproduction(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rep = D.analyse()

    @unittest.skipIf(chirp is None, "scipy not installed")
    def test_bit_identical_to_the_source_code_path(self):
        t, l1, l2, comb = D.cast()
        self.assertTrue(np.array_equal(l1, chirp(t, f0=8.5e12 - 432e3, f1=8.5e12 + 432e3, t1=1)))
        self.assertTrue(np.array_equal(l2, chirp(t, f0=8.5e12 + 432e3, f1=8.5e12 - 432e3, t1=1)))
        rc = np.exp(-t / 5e-10)
        self.assertLess(np.abs(D.convolve_same(comb, rc) - fftconvolve(comb, rc, mode="same")).max(), 1e-12)
        x, v = np.arange(7.0), np.array([1.0, -2.0, 0.5, 3.0])
        self.assertTrue(np.allclose(D.convolve_same(x, v), fftconvolve(x, v, mode="same")))

    def test_what_the_arrays_contain(self):
        r = self.rep
        self.assertEqual(r["sample_rate_hz"], 9999.0)
        rem = 8_500_000_000_000 % 9999                                                     # 5008, folded: 4991
        self.assertEqual(r["carrier_alias_hz"], float(min(rem, 9999 - rem)))
        self.assertEqual(r["carrier_alias_hz"], 4991.0)
        self.assertEqual(r["band_edge_aliases_hz"], [2965.0, 2948.0])
        self.assertEqual(r["destructive_nulls_in_record"], 432000)
        self.assertEqual(r["resolved_samples"], 115)
        self.assertLess(r["envelope_identity_max_error"], 1e-8)
        self.assertTrue(1e-3 < r["float_vs_exact_max_sample_error"] < 0.05)                # float loses ~0.01

    def test_the_rc_filter_is_an_impulse_that_drops_half_the_signal(self):
        rc = self.rep["rc_filter"]
        self.assertEqual((rc["nonzero_kernel_samples"], rc["same_mode_shift_samples"], rc["gain"]), (1, 4999, 20.0))
        self.assertTrue(rc["transmitted_equals_shifted_combined"])

    def test_exact_phases_agree_with_float_where_float_is_exact_enough(self):
        dc = D.DualCast(carrier=40.0, deviation=3.0, samples=2001, duration=2.0)
        _, l1, l2, _ = D.cast(dc)
        e1, e2 = D.cast_exact(dc)
        self.assertLess(max(np.abs(l1 - e1).max(), np.abs(l2 - e2).max()), 1e-10)
        with self.assertRaises(ValueError):
            D.DualCast(carrier=1.0, deviation=2.0).validate()

    def test_alias_frequency(self):
        for f, fs, want in ((1000, 8000, 1000), (7000, 8000, 1000), (8000 * 5 + 250, 8000, 250), (4000, 8000, 4000),
                            (-300, 8000, 300)):
            self.assertEqual(D.alias_frequency(f, fs), want)
        t = np.arange(8000) / 8000.0
        self.assertAlmostEqual(I.dominant_frequency(np.cos(2 * np.pi * 7000 * t), 8000.0), 1000.0, delta=0.5)


class CounterPair(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.locked = simulate(Scenario(seconds=120.0))
        cls.free = simulate(Scenario(seconds=120.0, detuning=2.5))

    def test_channels_sit_at_carrier_minus_and_plus_half_the_fast_rate(self):
        t = np.arange(0, 100.0, 0.01)
        st = D.counter_pair(t, 2 * np.pi * 0.25 * t, 2 * np.pi * 1.2 * t, 1000.0, 8000, depth=0.0)
        self.assertAlmostEqual(I.dominant_frequency(st[:, 0], 8000.0, 900), 999.4, delta=0.02)
        self.assertAlmostEqual(I.dominant_frequency(st[:, 1], 8000.0, 900), 1000.6, delta=0.02)
        mono = st.mean(axis=1)
        env = np.abs(I.coherence.analytic(mono)) / 0.89
        ta = np.arange(len(mono)) / 8000
        closed = D.mono_envelope(2 * np.pi * 0.25 * ta, 2 * np.pi * 1.2 * ta, 0.0)
        self.assertLess(np.abs(env - closed)[8000:-8000].max(), 1e-6)

    def test_locked_nulls_match_the_closed_form(self):
        rec = self.locked
        st = D.counter_pair(rec.t_model, rec.phi_r, rec.phi_h, 4991.0, 22050)
        na = D.null_analysis(st, 22050, rec.t_model, rec.phi_r, rec.phi_h, 4)
        self.assertAlmostEqual(na["rate_hz"], rec.scenario.heart_hz, delta=0.01)
        self.assertLess(na["timing_error_ms"]["max_abs"], 1.0)
        self.assertLess(na["depth_db"]["max_abs_error_db"], 0.05)
        self.assertGreater(na["depth_db"]["scored_nulls"], 0.9 * na["nulls"])
        self.assertGreater(na["stroboscopic_lock_index"], 0.95)                       # the pattern repeats every 4
        self.assertAlmostEqual(na["mono_to_stereo_energy_db"], -3.0, delta=0.3)

    def test_unlocked_null_pattern_drifts(self):
        rec = self.free
        st = D.counter_pair(rec.t_model, rec.phi_r, rec.phi_h, 4991.0, 22050)
        self.assertLess(D.null_analysis(st, 22050, rec.t_model, rec.phi_r, rec.phi_h, 4)["stroboscopic_lock_index"],
                        0.5)

    def test_refusals_and_room_offset(self):
        t = np.arange(0, 10.0, 0.01)
        with self.assertRaises(ValueError):
            D.counter_pair(t, t, t, 6000.0, 11025)
        with self.assertRaises(ValueError):
            D.counter_pair(t, t, t, 1000.0, 11025, depth=1.0)
        wavelength = 343.0 / 4991.0
        circular = lambda a, b: min(abs(a - b), 1 - abs(a - b))                           # noqa: E731
        for path, want in ((wavelength, 0.0), (wavelength / 2, 0.5), (wavelength / 4, 0.25), (3 * wavelength / 4, 0.75)):
            self.assertLess(circular(D.null_offset_for_path(path, 4991.0), want), 1e-9, path)


if __name__ == "__main__":
    unittest.main()
