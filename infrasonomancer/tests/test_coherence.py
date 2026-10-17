"""Synchronization with known ground truth: locked, unrelated, and a calibration check of the null."""
import unittest

import numpy as np

import infrasonomancer as I
from tests.helpers import beat_times, breathing, chaos, free_beats, locked_beats

FS = 50.0


class TwoSignalIndex(unittest.TestCase):
    def test_nm_phase_locking_breath_and_heart(self):
        t = np.arange(int(120 * FS)) / FS
        breath_phase = 2 * np.pi * 0.25 * t + 0.3 * np.sin(2 * np.pi * 0.02 * t)
        breath = np.cos(breath_phase)
        locked_heart = np.cos(4 * breath_phase + 0.4) + 0.3 * (chaos(len(t), "h") - 0.5)
        drift = 2 * np.pi * np.cumsum(1.0 + 0.15 * np.sin(2 * np.pi * 0.013 * t)) / FS
        free_heart = np.cos(drift) + 0.3 * (chaos(len(t), "f") - 0.5)
        rep = I.coherence_report(breath, locked_heart, FS)
        self.assertEqual(rep["ratio"], "4:1")
        self.assertGreater(rep["locking_index"], 0.8)
        self.assertLess(I.nm_phase_locking(breath, free_heart, FS, 4, 1), 0.3)

    def test_nearest_ratio(self):
        self.assertEqual(I.nearest_ratio(0.25, 1.0), (4, 1, 0.0))
        n, m, d = I.nearest_ratio(0.25, 1.1)                               # 4.4 beats per breath
        self.assertEqual((n, m), (9, 2))
        self.assertAlmostEqual(d, 0.05 / 2.2)


class Streams(unittest.TestCase):
    def test_event_phase_is_two_pi_per_event(self):
        ev = np.array([0.5, 1.4, 2.2, 3.3])
        s = I.stream_from_events(ev)
        self.assertTrue(np.allclose(s.phase_at(ev), 2 * np.pi * np.arange(4)))
        self.assertAlmostEqual(float(s.phase_at(np.array([0.95]))[0]), np.pi)
        with self.assertRaises(ValueError):
            I.stream_from_events(np.array([1.0, 0.5, 2.0]))

    def test_signal_phase_rate_and_band_warning(self):
        x, phase = breathing(200, FS, f=0.3)
        s = I.stream_from_signal(x, FS)
        self.assertAlmostEqual(s.rate_hz, 0.3, delta=0.005)
        self.assertNotIn("warning", s.info)
        self.assertGreater(s.info["band_power_fraction"], 0.8)
        inside = (np.arange(len(x)) / FS > s.t0 + 5) & (np.arange(len(x)) / FS < s.t1 - 5)
        t = np.arange(len(x))[inside] / FS
        err = np.angle(np.exp(1j * (s.phase_at(t) - phase[inside])))
        self.assertLess(np.abs(err - np.angle(np.mean(np.exp(1j * err)))).max(), 0.3)
        self.assertIn("warning", I.stream_from_signal(x, FS, band=(2.0, 3.0)).info)
        with self.assertRaises(ValueError):
            I.stream_from_signal(x[:500], FS)


class Synchronization(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.x, cls.phase = breathing(300, FS)
        cls.breath = I.stream_from_signal(cls.x, FS)

    def test_locked_rhythms_are_found_and_significant(self):
        beats = locked_beats(self.phase, FS, 4, 1)
        res = I.synchronize(self.breath, I.stream_from_events(beats), surrogates=99)
        w = res["whole_record"]
        self.assertEqual(w["ratio"], "4:1")
        self.assertGreater(w["index"], 0.8)
        self.assertAlmostEqual(w["p"], 0.01)                               # the smallest p 99 surrogates can give
        self.assertGreater(res["windows"]["locked_fraction"], 0.9)
        self.assertLessEqual(res["windows"]["p"], 0.02)
        ev, psi = I.synchrogram(beats, self.breath, 1)
        self.assertGreater(abs(np.mean(np.exp(2j * np.pi * 4 * psi))), 0.8)  # four horizontal bands

    def test_verdict_separates_locked_interacting_and_unrelated(self):
        from infrasonomancer.cardioresp import Scenario, simulate, true_breath_stream
        locked = I.synchronize(self.breath, I.stream_from_events(locked_beats(self.phase, FS, 4, 1)), surrogates=39)
        self.assertEqual(locked["whole_record"]["verdict"], "locked")
        self.assertLess(abs(locked["whole_record"]["net_slips"]), 1)
        free = I.synchronize(self.breath, I.stream_from_events(free_beats(300, seed="unrelated")), surrogates=39)
        self.assertNotEqual(free["whole_record"]["verdict"], "locked")
        rec = simulate(Scenario(detuning=1.6, coupling=0.6, phase_noise=0.02, breath_noise=0.01, seconds=300.0))
        drift = I.synchronize(true_breath_stream(rec), I.stream_from_events(rec.beats), surrogates=39)
        self.assertEqual(drift["whole_record"]["verdict"], "interacting, not locked")
        self.assertGreater(abs(drift["whole_record"]["net_slips"]), 10)

    def test_non_integer_locking(self):
        beats = locked_beats(self.phase, FS, 9, 2)
        res = I.synchronize(self.breath, I.stream_from_events(beats), surrogates=99)
        self.assertEqual(res["whole_record"]["ratio"], "9:2")
        self.assertLessEqual(res["whole_record"]["p"], 0.02)

    def test_unrelated_rhythms_are_never_called_locked(self):
        res = I.synchronize(self.breath, I.stream_from_events(free_beats(300)), surrogates=99)
        self.assertNotEqual(res["whole_record"]["verdict"], "locked")      # p itself is only calibrated, below
        self.assertGreater(abs(res["whole_record"]["net_slips"]), 5)
        self.assertLess(res["windows"]["slip_free_fraction"], 0.5)

    def test_null_is_calibrated(self):
        rejections = 0
        for k in range(20):
            x, _ = breathing(240, FS, f=0.21 + 0.006 * k, seed=f"b{k}")
            res = I.synchronize(I.stream_from_signal(x, FS), I.stream_from_events(free_beats(240, 0.97 + 0.015 * k,
                                                                                               seed=f"f{k}")),
                                surrogates=39, seed=f"s{k}")
            rejections += res["whole_record"]["p"] <= 0.05
            self.assertNotEqual(res["whole_record"]["verdict"], "locked")
        self.assertLessEqual(rejections, 3)                                # P(≥ 4 of 20 | α = 0.05) ≈ 0.016

    def test_refusals(self):
        short = I.stream_from_events(np.arange(0.0, 40.0, 0.9))
        with self.assertRaises(ValueError):
            I.synchronize(self.breath, short)


class RateCoupling(unittest.TestCase):
    def test_respiratory_sinus_arrhythmia_is_coherent_at_the_breathing_rate(self):
        fs, seconds = 25.0, 400.0
        t = np.arange(int(seconds * fs)) / fs
        resp = np.sin(2 * np.pi * 0.25 * t) + 0.2 * (chaos(len(t), "r") - 0.5)
        coupled = beat_times(seconds, rsa=0.06, f_resp=0.25, jitter=0.02)
        c = I.rate_coupling(resp, fs, coupled, surrogates=99)
        self.assertAlmostEqual(c["signal_peak_hz"], 0.25, delta=0.02)
        self.assertGreater(c["msc_at_signal_peak"], 0.8)
        self.assertAlmostEqual(c["p_at_signal_peak"], 0.01)
        other = beat_times(seconds, rsa=0.06, f_resp=0.37, jitter=0.02, seed="o")   # modulated, but not by this breath
        d = I.rate_coupling(resp, fs, other, surrogates=99)
        self.assertLess(d["msc_at_signal_peak"], 0.3)
        self.assertGreater(d["p_at_signal_peak"], 0.05)
        with self.assertRaises(ValueError):
            I.rate_coupling(resp[:1000], fs, coupled[:40])


class PhaseLockedLoop(unittest.TestCase):
    def test_pll_locks_on_a_tone_and_not_on_noise(self):
        fs, f0 = 1000.0, 10.0
        t = np.arange(int(5 * fs)) / fs
        r = I.pll_track(np.cos(2 * np.pi * 10.2 * t + 0.7), fs, f0)
        self.assertGreater(r.lock_fraction, 0.95)
        self.assertAlmostEqual(r.final_frequency, 10.2, delta=0.05)
        noise = 2 * (chaos(len(t), "n") - 0.5)
        self.assertLess(I.pll_track(noise, fs, f0).lock_fraction, 0.2)
        with self.assertRaises(ValueError):
            I.pll_track(noise, fs, 600.0)


if __name__ == "__main__":
    unittest.main()
