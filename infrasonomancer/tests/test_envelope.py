"""The repurposed search: scoring, mutation bounds, determinism and archive integrity."""
import unittest

import infrasonomancer.envelope as E
from infrasonomancer.cardioresp import Scenario
from infrasonomancer.chaos import Chaos

CFG = E.EnvelopeConfig(iterations=6, initial=3, bins=(2, 2), surrogates=19, replays=1)


class Scoring(unittest.TestCase):
    def test_severity(self):
        self.assertEqual(E.severity(True, True, 0.2), 0.0)
        self.assertEqual(E.severity(False, False, 10.0), 0.0)
        self.assertEqual(E.severity(None, True, 0.0), 1.0)                    # no call at all
        self.assertAlmostEqual(E.severity(False, True, 0.0), 1.0)             # a clean lock called absent
        self.assertAlmostEqual(E.severity(False, True, 0.9), 0.55)            # a lock with 0.9 net slips
        self.assertAlmostEqual(E.severity(True, False, -9.0), 1.0)            # 9 slips called locked
        self.assertAlmostEqual(E.severity(True, False, 3.0), 0.75)
        self.assertAlmostEqual(E.severity(True, False, 1.0), 0.5)

    def test_random_and_mutated_scenarios_stay_valid_and_in_bounds(self):
        ch = Chaos("bounds")
        scs = [E.random_scenario(ch) for _ in range(30)]
        scs += [E.mutate_scenario(s, ch) for s in scs]
        for s in scs:
            s.validate()
            self.assertIn((s.n, s.m), E.RATIOS)
            for k, (lo, hi) in E.BOUNDS.items():
                self.assertTrue(lo <= getattr(s, k) <= hi, (k, getattr(s, k)))

    def test_config_errors(self):
        for bad in (dict(target="vibes"), dict(axes=("detuning", "detuning")), dict(axes=("colour", "seconds")),
                    dict(surrogates=5)):
            with self.assertRaises(ValueError):
                E.EnvelopeConfig(**bad).validate()


class Search(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = E.failure_map("envelope test", CFG)

    def test_deterministic_and_counted(self):
        again = E.failure_map("envelope test", CFG)
        self.assertEqual(again["elites"], self.res["elites"])
        self.assertEqual(self.res["evaluations"], 1 + CFG.initial + CFG.iterations)
        self.assertEqual(self.res["baseline"]["scenario"], Scenario().to_dict())

    def test_archive_integrity(self):
        for e in self.res["elites"]:
            m = E.score(Scenario.from_dict(e["genome"]), CFG, "envelope test/simulate")
            self.assertEqual(m["fitness"], e["fitness"])
            self.assertEqual(m["call"], e["call"])
        grid = self.res["worst_case_map"]["fitness"]
        self.assertEqual(sum(v is not None for row in grid for v in row), len(self.res["elites"]))

    def test_statistics_target_scores_against_the_physics(self):
        cfg = E.EnvelopeConfig(target="statistics", axes=("detuning", "breath_noise"), surrogates=19)
        locked = E.score(Scenario(), cfg, "s")
        self.assertLess(abs(locked["true_slips"]), 1)
        self.assertEqual((locked["fitness"], locked["call"], locked["oracle_verdict"]), (0.0, "right", "locked"))
        self.assertIn("breath_noise", locked)
        drifting = E.score(Scenario(detuning=2.5), cfg, "s")
        self.assertGreater(abs(drifting["true_slips"]), 5)
        self.assertEqual(drifting["fitness"], 0.0)                         # interacting or not, it is not locked
        self.assertNotEqual(drifting["oracle_verdict"], "locked")


if __name__ == "__main__":
    unittest.main()
