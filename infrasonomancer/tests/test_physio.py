"""Beat detection and HRV against synthetic recordings whose beat times are known."""
import unittest

import numpy as np

import infrasonomancer as I
from tests.helpers import beat_times, chaos, synthetic_ecg, synthetic_ppg

FS, SECONDS = 500.0, 90.0


def nearest_error(found, truth):
    j = np.clip(np.searchsorted(found, truth), 1, len(found) - 1)
    return np.minimum(np.abs(found[j] - truth), np.abs(found[j - 1] - truth))


class Building(unittest.TestCase):
    def test_rolling_max_equals_brute_force(self):
        x = chaos(500, "rm")
        for w in (1, 3, 7, 50, 51):
            h = (w | 1) // 2
            brute = np.array([x[max(0, i - h):i + h + 1].max() for i in range(len(x))])
            self.assertTrue(np.array_equal(I.rolling_max(x, w), brute), w)

    def test_bandpass_passes_the_band_and_stops_the_rest(self):
        t = np.arange(20000) / FS
        for f, gain in ((10.0, 1.0), (1.0, 0.0), (60.0, 0.0)):
            y = I.bandpass(np.sin(2 * np.pi * f * t), FS, 5.0, 20.0)
            self.assertAlmostEqual(np.std(y[2000:-2000]) * np.sqrt(2), gain, delta=0.02, msg=f)


class Beats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.truth = beat_times(SECONDS)

    def test_ecg_finds_every_r_wave_either_polarity(self):
        for polarity in (1.0, -1.0):
            found = I.detect_beats(synthetic_ecg(self.truth, FS, SECONDS, polarity), FS, "ecg")
            self.assertEqual(len(found), len(self.truth), polarity)
            self.assertLess(nearest_error(found, self.truth).max(), 0.002)

    def test_ecg_with_heavy_noise_and_weak_beats(self):
        noisy = I.detect_beats(synthetic_ecg(self.truth, FS, SECONDS, noise=0.15), FS)
        self.assertEqual(len(noisy), len(self.truth))
        scale = np.ones(len(self.truth))
        scale[[30, 60]] = 0.3                                              # a third of the usual amplitude
        weak = I.detect_beats(synthetic_ecg(self.truth, FS, SECONDS, scale=scale), FS)
        self.assertEqual(len(weak), len(self.truth))
        self.assertLess(nearest_error(weak, self.truth).max(), 0.002)

    def test_ppg_upstrokes_follow_beats_at_a_constant_delay(self):
        found = I.detect_beats(synthetic_ppg(self.truth, FS, SECONDS), FS, "ppg")
        self.assertEqual(len(found), len(self.truth))
        lag = found - self.truth
        self.assertLess(np.std(lag), 0.003)
        self.assertTrue(0.25 < np.mean(lag) < 0.4)

    def test_refusals(self):
        for call in (lambda: I.detect_beats(np.zeros(100), FS),
                     lambda: I.detect_beats(np.zeros(4000), 40.0, "ecg"),
                     lambda: I.detect_beats(np.zeros(4000), FS, "eeg")):
            with self.assertRaises(ValueError):
                call()


class Variability(unittest.TestCase):
    def test_constant_rhythm(self):
        h = I.hrv(np.arange(0, 100, 0.8))
        self.assertAlmostEqual(h["mean_hr_bpm"], 75.0)
        self.assertAlmostEqual(h["sdnn_ms"], 0.0, places=6)
        self.assertAlmostEqual(h["rmssd_ms"], 0.0, places=6)
        self.assertNotIn("lf_ms2", h)                                       # 99 s: too short for LF

    def test_respiratory_sinus_arrhythmia_shows_the_breathing_rate(self):
        h = I.hrv(beat_times(300, rsa=0.06, f_resp=0.27, jitter=0.005))
        self.assertAlmostEqual(h["hf_peak_hz"], 0.27, delta=0.01)
        self.assertGreater(h["hf_ms2"], 5 * h["lf_ms2"])
        self.assertAlmostEqual(h["sdnn_ms"], 60 / np.sqrt(2), delta=6)      # amplitude / √2 for a sinusoid

    def test_ectopic_beats_are_excluded_not_averaged_in(self):
        clean = beat_times(200, jitter=0.0)
        bad = np.sort(np.concatenate([clean, [clean[50] + 0.3, clean[120] + 0.25]]))
        hc, hb = I.hrv(clean), I.hrv(bad)
        self.assertEqual(hb["intervals_excluded"], 4)
        self.assertAlmostEqual(hb["sdnn_ms"], hc["sdnn_ms"], delta=0.05 * hc["sdnn_ms"])
        self.assertAlmostEqual(hb["mean_hr_bpm"], hc["mean_hr_bpm"], delta=0.2)


if __name__ == "__main__":
    unittest.main()
