"""Every command end to end on files, through the same entry point a shell uses."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

import infrasonomancer as I
from infrasonomancer.__main__ import main
from tests.helpers import breathing, locked_beats, synthetic_ecg


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main([str(a) for a in argv])
        except SystemExit as e:                                            # argparse usage errors
            code = e.code
    return code, out.getvalue(), err.getvalue()


class Cli(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.d = Path(self._d.name)

    def tearDown(self):
        self._d.cleanup()

    def test_compose_then_reproduce_from_genome(self):
        code, out, _ = run("compose", "cli seed", "--seconds", 6, "--sr", 8000, "--out", self.d / "a")
        self.assertEqual(code, 0)
        rep = json.loads(out)
        for f in ("render.wav", "score.mid", "report.json", "genome.json"):
            self.assertTrue((self.d / "a" / f).exists(), f)
        code, _, _ = run("compose", "cli seed", "--seconds", 6, "--sr", 8000, "--genome", self.d / "a" / "report.json",
                         "--out", self.d / "b")
        self.assertEqual(code, 0)
        self.assertEqual((self.d / "a" / "render.wav").read_bytes(), (self.d / "b" / "render.wav").read_bytes())
        inline = json.dumps(dict(rep["genome"], mode="dorian"))
        code, out, _ = run("compose", "cli seed", "--seconds", 6, "--sr", 8000, "--genome", inline, "--stereo",
                           "--out", self.d / "c")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out)["mode"].endswith("dorian"))
        self.assertEqual(I.read_wav(self.d / "c" / "render.wav")[1].shape[1], 2)
        code, _, err = run("compose", "cli seed", "--genome", inline, "--density", 0.1, "--out", self.d / "d")
        self.assertEqual(code, 1)
        self.assertIn("--density", err)

    def test_evolve_and_reproduce_the_champion(self):
        code, out, _ = run("evolve", "cli evolve", "--iterations", 10, "--initial", 3, "--bins", "2x2", "--seconds", 4,
                           "--sr", 8000, "--render-top", 2, "--quiet", "--out", self.d / "e")
        self.assertEqual(code, 0)
        summary = json.loads(out)
        archive = json.loads((self.d / "e" / "archive.json").read_text())
        self.assertEqual(summary["evaluations"], 14)
        self.assertEqual(archive["champion"]["genome"], summary["champion"]["genome"])
        self.assertEqual(len(summary["rendered"]), min(2, len(archive["elites"])))
        code, _, _ = run("compose", "cli evolve", "--seconds", 4, "--sr", 8000, "--genome",
                         self.d / "e" / "champion" / "genome.json", "--out", self.d / "f")
        self.assertEqual(code, 0)
        self.assertEqual((self.d / "e" / "champion" / "render.wav").read_bytes(),
                         (self.d / "f" / "render.wav").read_bytes())
        self.assertEqual(run("evolve", "x", "--bins", "2x2x2", "--out", self.d / "g")[0], 1)

    def test_beats_and_coherence_on_files(self):
        fs, seconds = 250.0, 200.0
        x, phase = breathing(seconds, fs)
        beats = locked_beats(phase, fs, 4, 1)
        ecg = synthetic_ecg(beats, fs, seconds)
        t = np.arange(len(x)) / fs
        I.write_csv(self.d / "rec.csv", ["time", "resp", "ecg"], [t, x, ecg])
        code, out, _ = run("beats", self.d / "rec.csv", "--column", "ecg", "--time-column", "time", "--kind", "ecg",
                           "--out", self.d / "beats.csv")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["hrv"]["beats"], len(beats))
        self.assertEqual(len(I.read_events(self.d / "beats.csv")[0]), len(beats))
        for y_args in (("--y", self.d / "rec.csv", "--y-kind", "ecg", "--y-column", "ecg", "--y-time-column", "time"),
                       ("--y", self.d / "beats.csv", "--y-kind", "beats")):
            code, out, err = run("coherence", "--x", self.d / "rec.csv", "--x-kind", "signal", "--x-column", "resp",
                                 "--x-time-column", "time", *y_args, "--surrogates", 49, "--out", self.d / "coh")
            self.assertEqual(code, 0, err)
            res = json.loads(out)
            self.assertEqual(res["whole_record"]["ratio"], "4:1")
            self.assertLessEqual(res["whole_record"]["p"], 0.02)
            self.assertNotIn("_table", res)
        self.assertEqual(len((self.d / "coh" / "windows.csv").read_text().splitlines()) - 1,
                         res["windows"]["count"])
        self.assertTrue((self.d / "coh" / "synchrogram.csv").read_text().startswith("t_s,psi_m1,psi_m2,psi_m3"))
        rr = np.diff(beats) * 1e3
        I.write_csv(self.d / "rr.csv", ["rr_ms"], [rr])
        code, out, _ = run("coherence", "--x", self.d / "rec.csv", "--x-kind", "signal", "--x-column", "resp",
                           "--x-fs", fs, "--x-band", "0.15,0.4", "--y", self.d / "rr.csv", "--y-kind", "rr",
                           "--y-unit", 0.001, "--surrogates", 19)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["x"]["band_hz"], [0.15, 0.4])

    def test_pll_series_and_fractal(self):
        fs = 1000
        tone = 0.5 * np.cos(2 * np.pi * 10.2 * np.arange(5 * fs) / fs)
        I.write_wav(self.d / "tone.wav", tone, fs)
        code, out, _ = run("pll", self.d / "tone.wav", "--f0", 10, "--out", self.d / "track.csv")
        self.assertEqual(code, 0)
        res = json.loads(out)
        self.assertGreater(res["lock_fraction"], 0.95)
        self.assertAlmostEqual(res["final_frequency_hz"], 10.2, delta=0.05)
        np.save(self.d / "s.npy", np.sin(2 * np.pi * 0.5 * np.arange(1200) / 20.0))
        code, out, _ = run("series", self.d / "s.npy", "--fs", 20, "--out", self.d / "series.json")
        self.assertEqual(code, 0)
        self.assertAlmostEqual(json.loads(out)["dominant_hz"], 0.5, delta=0.005)
        code, out, _ = run("fractal", "--c=-0.123,0.745", "--png", self.d / "rabbit.png")
        self.assertEqual(code, 0)
        rabbit = json.loads(out)
        self.assertTrue(rabbit["main_cardioid"]["inside"] is False and 1.1 < rabbit["edge_box_dimension"] < 1.6)
        code, out, _ = run("fractal", "--image", self.d / "rabbit.png", "--foreground", "dark")
        self.assertEqual(code, 0)
        self.assertGreater(json.loads(out)["box_dimension"], 1.5)                 # the filled set, drawn dark
        code, out, _ = run("fractal", "--seed", "infrasonomantic digiology – K1LL x DIANNE v1")
        self.assertTrue(json.loads(out)["main_cardioid"]["inside"])

    def test_dualcast_cardioresp_and_envelope(self):
        code, out, _ = run("dualcast", "--samples", 2000, "--out", self.d / "dc")
        self.assertEqual(code, 0)
        rep = json.loads(out)
        self.assertEqual(rep["sample_rate_hz"], 1999.0)
        self.assertEqual(rep["carrier_alias_hz"], I.alias_frequency(8.5e12, 1999.0))
        self.assertEqual(rep["rc_filter"]["same_mode_shift_samples"], 999)
        sr, st = I.read_wav(self.d / "dc" / "source_stereo.wav")
        self.assertEqual((sr, st.shape), (1999, (2000, 2)))
        for f in ("combined.wav", "transmitted.wav", "analysis.json"):
            self.assertTrue((self.d / "dc" / f).exists(), f)

        code, out, err = run("cardioresp", "--seconds", 90, "--surrogates", 19, "--sonify", "--sr", 11025,
                             "--out", self.d / "cr")
        self.assertEqual(code, 0, err)
        res = json.loads(out)
        self.assertEqual(res["assessment"]["pipeline_call"], "right")
        self.assertEqual(res["sonification"]["carrier_hz"], 4991.0)
        self.assertGreater(res["sonification"]["nulls"], 60)
        self.assertNotIn("_depths", res["sonification"])
        sr, st = I.read_wav(self.d / "cr" / "dualcast_pair.wav")
        self.assertEqual((sr, st.shape[1]), (11025, 2))
        self.assertEqual(len((self.d / "cr" / "recording.csv").read_text().splitlines()), 1 + 90 * 250)
        code, _, _ = run("cardioresp", "--scenario", self.d / "cr" / "assessment.json", "--surrogates", 19,
                         "--out", self.d / "cr2")
        self.assertEqual(code, 0)
        self.assertEqual((self.d / "cr" / "recording.csv").read_bytes(), (self.d / "cr2" / "recording.csv").read_bytes())
        code, _, err = run("cardioresp", "--n", 11, "--breath-hz", 0.9, "--out", self.d / "bad")
        self.assertEqual(code, 1)
        self.assertIn("bpm", err)

        code, out, err = run("envelope", "--iterations", 3, "--initial", 2, "--bins", "2x2", "--surrogates", 19,
                             "--replays", 1, "--quiet", "--out", self.d / "env")
        self.assertEqual(code, 0, err)
        summary = json.loads(out)
        self.assertEqual((summary["evaluations"], summary["target"]), (6, "locking"))
        self.assertTrue((self.d / "env" / "archive.json").exists())
        self.assertEqual(len((self.d / "env" / "map.csv").read_text().splitlines()), 3)
        self.assertEqual(run("envelope", "--axes", "detuning,colour", "--out", self.d / "env2")[0], 1)

    def test_errors_explain_themselves(self):
        np.save(self.d / "a.npy", np.zeros(100))
        code, _, err = run("series", self.d / "a.npy")
        self.assertEqual(code, 1)
        self.assertIn("--fs", err)
        self.assertEqual(run("fractal")[0], 1)
        self.assertEqual(run("nonsense")[0], 2)
        self.assertEqual(run("beats", self.d / "missing.csv", "--fs", 100, "--kind", "ecg")[0], 1)


if __name__ == "__main__":
    unittest.main()
