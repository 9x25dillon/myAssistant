"""Chaos, fractal, genome, score and render.   python -m unittest discover -s tests -t ."""
import hashlib
import math
import unittest

import numpy as np

import infrasonomancer as I
from tests.helpers import chaos

SEED = "infrasonomantic digiology – K1LL x DIANNE v1"


class ChaosTests(unittest.TestCase):
    def test_deterministic_uniform_and_seed_sensitive(self):
        a, b, c = chaos(20000), chaos(20000), chaos(20000, "other")
        self.assertTrue(np.array_equal(a, b))
        self.assertFalse(np.array_equal(a, c))
        self.assertAlmostEqual(a.mean(), 0.5, delta=0.01)
        self.assertAlmostEqual(a.var(), 1 / 12, delta=0.003)
        hist = np.histogram(a, bins=10, range=(0, 1))[0] / len(a)
        self.assertLess(np.abs(hist - 0.1).max(), 0.01)
        self.assertLess(abs(np.corrcoef(a[:-1], a[1:])[0, 1]), 0.03)

    def test_normal_and_integers(self):
        z = I.Chaos("z").normal(20001)
        self.assertEqual(len(z), 20001)
        self.assertAlmostEqual(z.mean(), 0.0, delta=0.03)
        self.assertAlmostEqual(z.std(), 1.0, delta=0.03)
        self.assertAlmostEqual(float(np.mean(np.abs(z) < 1.96)), 0.95, delta=0.01)
        k = I.Chaos("k").integers(12000, 6)
        self.assertEqual(set(k.tolist()), set(range(6)))
        self.assertLess(np.abs(np.bincount(k) / 12000 - 1 / 6).max(), 0.015)


class FractalTests(unittest.TestCase):
    def test_box_dimension_of_known_sets(self):
        line = np.zeros((256, 256), bool)
        line[128, :] = True
        square = np.ones((256, 256), bool)
        self.assertAlmostEqual(I.box_dimension(line), 1.0, delta=0.05)
        self.assertAlmostEqual(I.box_dimension(square), 2.0, delta=0.05)
        self.assertAlmostEqual(I.box_dimension(I.boundary(square)), 1.0, delta=0.1)
        with self.assertRaises(ValueError):
            I.box_dimension(np.ones((8, 8), bool))

    def test_sierpinski_carpet_dimension(self):
        carpet = np.ones((1, 1), bool)
        for _ in range(5):                                                 # 243 × 243, log 8 / log 3 ≈ 1.893
            z = np.zeros_like(carpet)
            carpet = np.block([[carpet, carpet, carpet], [carpet, z, carpet], [carpet, carpet, carpet]])
        self.assertAlmostEqual(I.box_dimension(np.pad(carpet, ((0, 13), (0, 13)))), math.log(8) / math.log(3),
                               delta=0.08)

    def test_julia_boundary_is_fractal(self):
        dim = I.edge_dimension(complex(-0.123, 0.745))                      # Douady's rabbit
        self.assertTrue(1.1 < dim < 1.6, dim)

    def test_cardioid_parametrisation_inverts(self):
        for theta, r in ((0.3, 0.99), (2.5, 0.5), (5.9, 0.996)):
            th, rr = I.cardioid_coordinates(I.cardioid_c(theta, r))
            self.assertAlmostEqual(th, theta, places=9)
            self.assertAlmostEqual(rr, r, places=9)
        _, outside = I.cardioid_coordinates(complex(0.4, 0.0))               # past the cusp at 1/4
        self.assertGreater(outside, 1.0)

    def test_every_seed_gives_a_connected_julia_set_with_a_fractal_edge(self):
        cs = []
        for k in range(12):
            p = I.compose(f"seed {k}", seconds=4.0)
            cs.append(p.c)
            _, filled = I.julia(p.c, 256, 256, 200)
            self.assertGreater(filled.mean(), 0.01, p.c)
            self.assertGreater(I.box_dimension(I.boundary(filled)), 1.0, p.c)
            self.assertGreater(len(p.notes), 0)
        gaps = [abs(a - b) for i, a in enumerate(cs) for b in cs[i + 1:]]
        self.assertGreater(min(gaps), 1e-3)


class GenomeTests(unittest.TestCase):
    def test_round_trip_and_validation(self):
        g = I.Genome.from_seed(SEED)
        self.assertEqual(I.Genome.from_dict(g.to_dict()), g)
        bad = dict(g.to_dict(), radius=1.2, mode="locrian", root=120)
        with self.assertRaises(ValueError) as e:
            I.Genome.from_dict(bad)
        for word in ("radius", "mode", "root"):
            self.assertIn(word, str(e.exception))
        with self.assertRaises(ValueError):
            I.Genome.from_dict({"theta": 1.0})

    def test_mutation_is_local_valid_and_deterministic(self):
        g = I.Genome.from_seed(SEED)
        kids = [g.mutate(I.Chaos(f"m{k}")) for k in range(60)]
        self.assertEqual(g.mutate(I.Chaos("m0")), kids[0])
        near = np.mean([abs(k.c - g.c) for k in kids])
        far = np.mean([abs(I.Genome.from_seed(f"r{k}").c - g.c) for k in range(60)])
        self.assertLess(near, far / 5)                                      # a step is much smaller than a jump
        self.assertTrue(all(0.985 <= k.radius <= 0.997 and 0.04 <= k.density <= 0.16 for k in kids))

    def test_seed_genome_reproduces_the_v2_piece(self):
        p = I.compose(SEED)
        pcm = np.round(I.render(p, 22050) * 32767).astype("<i2").tobytes()
        self.assertEqual(hashlib.sha256(pcm).hexdigest()[:16], "72a49e21d1037831")


class PieceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.piece = I.compose(SEED, seconds=8.0)
        cls.audio = I.render(cls.piece, 8000)

    def test_same_seed_same_piece_different_seed_different(self):
        again = I.compose(SEED, seconds=8.0)
        self.assertEqual(again.notes, self.piece.notes)
        self.assertTrue(np.array_equal(I.render(again, 8000), self.audio))
        self.assertNotEqual(I.compose("another seed", seconds=8.0).notes, self.piece.notes)

    def test_score_stays_in_mode_and_voice_limit(self):
        p = self.piece
        scale = set(I.MODES[p.mode])
        self.assertTrue(all((n.pitch - p.root) % 12 in scale for n in p.notes))
        for t in np.arange(0, p.seconds, p.step):
            self.assertLessEqual(sum(1 for n in p.notes if n.start <= t + 1e-9 < n.start + n.duration), 4)
        self.assertTrue(all(1 <= n.velocity <= 127 and n.duration > 0 for n in p.notes))

    def test_bad_arguments_are_refused(self):
        for kw in ({"seconds": 0}, {"voices": 0}, {"width": 4}):
            with self.assertRaises(ValueError):
                I.compose(SEED, **kw)
        with self.assertRaises(ValueError):
            I.render(self.piece, 4000)

    def _rms(self, a, k=400):
        return np.sqrt(np.convolve(a ** 2, np.ones(k) / k, "same")) + 1e-9

    def test_lfo_is_sub_20hz_modulation_and_actually_reaches_the_audio(self):
        p = self.piece
        self.assertTrue(0.1 - 1e-9 <= p.lfo_rate.min() and p.lfo_rate.max() <= 8.0 + 1e-9)
        dry = I.render(p, 8000, lfo=False)
        ratio = self._rms(self.audio) / self._rms(dry)
        intended = I.lfo_envelope(p, 8000)
        busy = self._rms(dry) > 0.05
        self.assertGreater(np.corrcoef(ratio[busy], intended[busy])[0, 1], 0.8)
        self.assertLessEqual(np.max(np.abs(self.audio)), 0.9)

    def test_stereo_pulse_is_antiphase_and_vanishes_in_mono(self):
        p = self.piece
        e0, e1 = I.lfo_envelope(p, 8000, 0.35, 0.0), I.lfo_envelope(p, 8000, 0.35, np.pi)
        self.assertTrue(np.allclose(e0 + e1, 2 - 0.35))
        st = I.render(p, 8000, stereo=True)
        self.assertEqual(st.shape, (int(8 * 8000), 2))
        dry = self._rms(I.render(p, 8000, lfo=False))
        busy = dry > 0.05
        left, right = self._rms(st[:, 0]) / dry, self._rms(st[:, 1]) / dry
        self.assertGreater(np.corrcoef(left[busy], e0[busy])[0, 1], 0.8)
        self.assertGreater(np.corrcoef(right[busy], e1[busy])[0, 1], 0.8)
        self.assertLess(np.corrcoef(left[busy], right[busy])[0, 1], -0.6)
        mono = self._rms(st.sum(axis=1)) / dry
        self.assertLess(np.std(mono[busy]) / np.mean(mono[busy]), 0.25 * np.std(left[busy]) / np.mean(left[busy]))


if __name__ == "__main__":
    unittest.main()
