"""Estimators against cases with known answers."""
import math
import unittest

import numpy as np

import infrasonomancer as I
from tests.helpers import chaos

try:
    from scipy import signal as sps
except ImportError:                                                        # pragma: no cover
    sps = None


def pink(n, seed="pink"):
    """1/f noise: white chaos noise shaped by 1/√f in the frequency domain."""
    spec = np.fft.rfft(chaos(n, seed) - 0.5)
    f = np.fft.rfftfreq(n)
    spec[1:] /= np.sqrt(f[1:])
    spec[0] = 0
    return np.fft.irfft(spec, n)


class Scaling(unittest.TestCase):
    def test_hurst_white_noise_and_random_walk(self):
        noise = chaos(4096) - 0.5
        self.assertTrue(0.4 < I.hurst_rs(noise) < 0.65, I.hurst_rs(noise))
        self.assertGreater(I.hurst_rs(np.cumsum(noise)), 0.85)

    def test_dfa_white_pink_and_brown(self):
        white = chaos(2 ** 14, "w") - 0.5
        self.assertAlmostEqual(I.dfa(white), 0.5, delta=0.06)
        self.assertAlmostEqual(I.dfa(pink(2 ** 14)), 1.0, delta=0.08)
        self.assertAlmostEqual(I.dfa(np.cumsum(white)), 1.5, delta=0.08)
        self.assertTrue(math.isnan(I.dfa(white[:20])))

    def test_dfa_handles_long_series(self):
        self.assertAlmostEqual(I.dfa(chaos(300000, "long") - 0.5), 0.5, delta=0.06)


class Topology(unittest.TestCase):
    def test_persistence_circle_has_one_long_loop_and_a_cloud_has_none(self):
        ang = 2 * np.pi * np.arange(40) / 40
        circle = np.stack([np.cos(ang), np.sin(ang)], 1)
        bars = I.persistence(circle)
        h1 = sorted((d - b for b, d in bars[1]), reverse=True)
        self.assertGreater(h1[0], 1.4)                                    # born ≈ 0.157, dies ≈ √3
        self.assertTrue(len(h1) == 1 or h1[1] < 0.1)
        self.assertEqual(len(bars[0]), 40)                                # 39 merges + 1 infinite
        self.assertEqual(sum(1 for b, d in bars[0] if math.isinf(d)), 1)
        cloud = np.stack([chaos(40, "x"), chaos(40, "y")], 1)
        self.assertLess(max((d - b for b, d in I.persistence(cloud)[1]), default=0.0), 0.2)
        with self.assertRaises(ValueError):
            I.persistence(np.zeros((81, 2)))

    def test_two_circles_give_two_loops(self):
        ang = 2 * np.pi * np.arange(24) / 24
        a = np.stack([np.cos(ang), np.sin(ang)], 1)
        bars = I.persistence(np.concatenate([a, 0.5 * a + [4.0, 0.0]]))
        long = [d - b for b, d in bars[1] if d - b > 0.5]
        self.assertEqual(len(long), 2)
        self.assertEqual(sum(1 for b, d in bars[0] if d - b > 2.0), 2)       # two components until they merge

    def test_delay_embedding_turns_a_sine_into_a_loop(self):
        t = np.arange(400) / 400
        x = np.sin(2 * np.pi * 5 * t)
        self.assertIn(I.embedding_delay(x), (20, 21))                    # a quarter of the 80-sample period
        rec = I.recurrence(x, dim=2)
        self.assertGreater(rec["longest_h1_over_diameter"], 0.4)
        self.assertLess(I.recurrence(chaos(400, "n"), dim=2)["longest_h1_over_diameter"], 0.25)

    def test_fft_autocorrelation_matches_direct(self):
        x = chaos(300, "ac") - 0.5
        direct = np.correlate(x - x.mean(), x - x.mean(), "full")[299:]
        self.assertTrue(np.allclose(I.autocorrelation(x), direct / direct[0]))


class Spectra(unittest.TestCase):
    def test_dominant_frequency_is_sub_bin_accurate(self):
        fs = 10.0
        t = np.arange(int(120 * fs)) / fs
        for f0 in (0.2537, 0.31, 1.234):
            x = np.cos(2 * np.pi * f0 * t + 0.4) + 0.2 * (chaos(len(t), str(f0)) - 0.5)
            self.assertAlmostEqual(I.dominant_frequency(x, fs), f0, delta=0.002)
        x = np.cos(2 * np.pi * 0.05 * t) * 3 + np.cos(2 * np.pi * 0.3 * t)
        self.assertAlmostEqual(I.dominant_frequency(x, fs, fmin=0.1), 0.3, delta=0.002)
        with self.assertRaises(ValueError):
            I.dominant_frequency(x, fs, fmin=6.0)

    def test_welch_integrates_to_the_variance(self):
        fs = 50.0
        x = chaos(20000, "wv") - 0.5 + 0.5 * np.sin(2 * np.pi * 3 * np.arange(20000) / fs)
        f, p = I.welch(x, fs, seconds=20)
        self.assertAlmostEqual(float(np.sum(p) * (f[1] - f[0])), float(np.var(x)), delta=0.03 * np.var(x))
        self.assertAlmostEqual(float(f[np.argmax(p)]), 3.0, delta=0.05)

    @unittest.skipIf(sps is None, "scipy not installed")
    def test_welch_matches_scipy(self):
        fs = 4.0
        x = chaos(4000, "sp") - 0.5
        f, p = I.welch(x, fs, seconds=64)
        fr, pr = sps.welch(x, fs, nperseg=256)
        self.assertTrue(np.allclose(f, fr))
        self.assertTrue(np.allclose(p, pr, rtol=1e-10))

    def test_coherence_of_a_filtered_copy_is_one_and_of_independent_noise_is_small(self):
        fs = 10.0
        x = chaos(6000, "cx") - 0.5
        y = np.convolve(x, [0.5, 0.3, 0.2], "same") + 0.05 * (chaos(6000, "cy") - 0.5)
        f, c = I.msc(x, y, fs, seconds=25.6)
        band = (f > 0.2) & (f < 4.0)
        self.assertGreater(c[band].mean(), 0.9)
        f, c = I.msc(x, chaos(6000, "other") - 0.5, fs, seconds=25.6)
        self.assertLess(c[1:].mean(), 0.1)                                 # ≈ 1/K for K ≈ 45 segments
        with self.assertRaises(ValueError):
            I.msc(x, x[:-1], fs, 10)

    @unittest.skipIf(sps is None, "scipy not installed")
    def test_coherence_matches_scipy(self):
        x, y = chaos(3000, "a") - 0.5, chaos(3000, "b") - 0.5
        y = 0.6 * x + y
        f, c = I.msc(x, y, 4.0, seconds=64)
        fr, cr = sps.coherence(x, y, 4.0, nperseg=256)
        self.assertTrue(np.allclose(f, fr))
        self.assertTrue(np.allclose(c, cr, rtol=1e-9, atol=1e-12))

    def test_describe_series_fields(self):
        fs = 20.0
        t = np.arange(int(60 * fs)) / fs
        d = I.describe_series(np.sin(2 * np.pi * 0.5 * t) + 0.1 * (chaos(len(t), "d") - 0.5), fs)
        self.assertAlmostEqual(d["dominant_hz"], 0.5, delta=0.005)
        self.assertGreater(d["recurrence"]["longest_h1_over_diameter"], 0.3)
        for k in ("hurst_rs_levels", "hurst_rs_increments", "dfa_alpha", "samples", "seconds"):
            self.assertIn(k, d)


class PieceReport(unittest.TestCase):
    def test_report_fields_and_genome(self):
        p = I.compose("report", seconds=4.0)
        a = I.render(p, 8000)
        r = I.analyse(p, a, 8000)
        self.assertEqual(I.Genome.from_dict(r["genome"]), p.genome)
        self.assertEqual(r["audio"]["channels"], 1)
        self.assertEqual(I.analyse(p, I.render(p, 8000, stereo=True), 8000)["audio"]["channels"], 2)
        self.assertLessEqual(r["pitch_class_entropy_bits"], math.log2(7) + 1e-9)
        self.assertTrue(1.0 < r["fractal_boundary_dimension"] < 2.0)


if __name__ == "__main__":
    unittest.main()
