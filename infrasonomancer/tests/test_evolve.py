"""MAP-Elites: determinism, archive integrity, and that the seed's own piece is the baseline it must beat."""
import math
import unittest

import infrasonomancer as I
from infrasonomancer.evolve import _cell, evaluate

CFG = I.EvolveConfig(iterations=30, initial=6, bins=(3, 3), seconds=8.0, edge_grid=128)


class MapElites(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = I.map_elites("evolve test", CFG)

    def test_deterministic(self):
        again = I.map_elites("evolve test", CFG)
        self.assertEqual(again["elites"], self.res["elites"])
        self.assertEqual(again["history"], self.res["history"])

    def test_counts_and_history(self):
        r = self.res
        self.assertEqual(r["evaluations"], 1 + CFG.initial + CFG.iterations)
        self.assertGreater(r["coverage"], 0)
        self.assertEqual(len(r["elites"]), round(r["coverage"] * 9))
        qd = [row[2] for row in r["history"]["rows"]]
        best = [row[3] for row in r["history"]["rows"]]
        self.assertEqual(qd, sorted(qd))                                   # an archive only ever improves
        self.assertEqual(best, sorted(best))

    def test_archive_integrity(self):
        cells = set()
        for e in self.res["elites"]:
            m = evaluate(I.Genome.from_dict(e["genome"]), "evolve test", CFG)
            self.assertTrue(m["valid"])
            self.assertEqual(m["fitness"], e["fitness"])                   # re-evaluation reproduces the record
            self.assertEqual(list(_cell(m, CFG)), e["cell"])
            cells.add(tuple(e["cell"]))
        self.assertEqual(len(cells), len(self.res["elites"]))

    def test_champion_is_at_least_the_baseline(self):
        r = self.res
        self.assertTrue(r["baseline"]["valid"])
        self.assertEqual(r["baseline"]["genome"], I.Genome.from_seed("evolve test").to_dict())
        self.assertGreaterEqual(r["champion"]["fitness"], r["baseline"]["fitness"])
        self.assertAlmostEqual(r["gain_over_baseline"], r["champion"]["fitness"] - r["baseline"]["fitness"])
        self.assertEqual(r["champion"], r["elites"][0])
        h = r["held_out"]
        self.assertIn("32 and 64 points", h["estimator"])
        self.assertAlmostEqual(h["gain"], h["champion"] - h["baseline"])

    def test_coupling_objective_and_config_errors(self):
        r = I.map_elites("evolve test", I.EvolveConfig(iterations=5, initial=3, bins=(2, 2), objective="coupling",
                                                        seconds=8.0, edge_grid=128))
        self.assertTrue(all(-1.0 <= e["fitness"] <= 1.0 for e in r["elites"]))
        self.assertTrue(all(e["fitness"] == e["coupling"] for e in r["elites"]))
        self.assertIn("Spearman", r["held_out"]["estimator"])
        self.assertTrue(-1.0 <= r["held_out"]["champion"] <= 1.0)
        with self.assertRaises(ValueError):
            I.map_elites("x", I.EvolveConfig(objective="beauty"))

    def test_invalid_genomes_are_never_archived(self):
        sparse = I.Genome.from_dict(dict(I.Genome.from_seed("sparse").to_dict(), density=0.001))
        m = evaluate(sparse, "sparse", CFG)
        self.assertFalse(m["valid"])
        self.assertTrue(math.isinf(m["fitness"]) and m["fitness"] < 0)


if __name__ == "__main__":
    unittest.main()
