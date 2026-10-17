"""WAV, MIDI, PNG, tables, series and events. Pillow, pypng and scipy are used as independent references when
installed; those tests skip otherwise."""
import struct
import tempfile
import unittest
import wave
import zlib
from pathlib import Path

import numpy as np

import infrasonomancer as I
from tests.helpers import chaos

try:
    from PIL import Image
except ImportError:                                                        # pragma: no cover
    Image = None
try:
    import png as pypng
except ImportError:                                                        # pragma: no cover
    pypng = None
try:
    from scipy.io import wavfile
except ImportError:                                                        # pragma: no cover
    wavfile = None

GUID_TAIL = b"\x00\x00\x00\x00\x10\x00\x80\x00\x00\xaa\x00\x38\x9b\x71"


def riff(tag, channels, sr, bits, payload, extensible=False, extra=b""):
    block = channels * ((bits + 7) // 8)
    fmt = struct.pack("<HHIIHH", 0xFFFE if extensible else tag, channels, sr, sr * block, block, bits)
    if extensible:
        fmt += struct.pack("<HHI", 22, bits, 0) + struct.pack("<H", tag) + GUID_TAIL
    body = b"fmt " + struct.pack("<I", len(fmt)) + fmt + extra + b"data" + struct.pack("<I", len(payload)) + payload
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body


class Tmp(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.d = Path(self._d.name)

    def tearDown(self):
        self._d.cleanup()


class WavTests(Tmp):
    x = np.array([-1.0, -0.5, -0.123, 0.0, 0.25, 0.5, 0.999])

    def read_bytes(self, raw):
        (self.d / "a.wav").write_bytes(raw)
        return I.read_wav(self.d / "a.wav")

    def test_every_pcm_and_float_width(self):
        x = self.x
        cases = {
            "8-bit": (1, 8, (np.clip(np.round(x * 128) + 128, 0, 255)).astype(np.uint8).tobytes(), 1 / 128),
            "16-bit": (1, 16, np.clip(np.round(x * 32768), -32768, 32767).astype("<i2").tobytes(), 1 / 32768),
            "24-bit": (1, 24, b"".join(int(v).to_bytes(3, "little", signed=True)
                                       for v in np.clip(np.round(x * 2 ** 23), -2 ** 23, 2 ** 23 - 1)), 2 ** -23),
            "32-bit": (1, 32, np.clip(np.round(x * 2 ** 31), -2 ** 31, 2 ** 31 - 1).astype("<i4").tobytes(), 2 ** -31),
            "float32": (3, 32, x.astype("<f4").tobytes(), 1e-7),
            "float64": (3, 64, x.astype("<f8").tobytes(), 1e-15),
        }
        for name, (tag, bits, payload, tol) in cases.items():
            for ext in (False, True):
                with self.subTest(name, extensible=ext):
                    sr, y = self.read_bytes(riff(tag, 1, 8000, bits, payload, ext))
                    self.assertEqual((sr, y.shape), (8000, (len(x), 1)))
                    self.assertLessEqual(np.abs(y[:, 0] - x).max(), tol * 1.01)

    def test_odd_chunks_stereo_and_errors(self):
        pcm = np.array([[1000, -1000], [2000, -2000], [3000, -3000]], "<i2").tobytes()
        odd = b"LIST" + struct.pack("<I", 5) + b"abcde" + b"\x00"                # odd chunk + pad byte
        sr, y = self.read_bytes(riff(1, 2, 44100, 16, pcm, extra=odd))
        self.assertEqual(y.shape, (3, 2))
        self.assertTrue(np.allclose(y[:, 0], -y[:, 1]))
        self.assertAlmostEqual(y[2, 0], 3000 / 32768)
        for raw in (b"RIFX" + b"\x00" * 40, riff(2, 1, 8000, 4, b"\x00" * 8), riff(1, 1, 8000, 16, b"")[:-8][:36]):
            with self.assertRaises(ValueError):
                self.read_bytes(raw)

    def test_writer_round_trip_mono_and_stereo(self):
        mono = 0.9 * np.sin(np.linspace(0, 20, 1000))
        I.write_wav(self.d / "m.wav", mono, 16000)
        sr, y = I.read_wav(self.d / "m.wav")
        self.assertEqual(sr, 16000)
        self.assertLess(np.abs(y[:, 0] - mono).max(), 2 / 32768)            # written ×32767, read ÷32768
        st = np.stack([mono, -mono], 1)
        I.write_wav(self.d / "s.wav", st, 16000)
        with wave.open(str(self.d / "s.wav")) as w:
            self.assertEqual((w.getnchannels(), w.getnframes()), (2, 1000))
        self.assertLess(np.abs(I.read_wav(self.d / "s.wav")[1] - st).max(), 2 / 32768)

    @unittest.skipIf(wavfile is None, "scipy not installed")
    def test_agrees_with_scipy(self):
        x = 0.8 * np.sin(np.linspace(0, 50, 2000))
        for dtype, scale in (("int16", 32768), ("int32", 2 ** 31), ("float32", 1.0)):
            data = np.stack([x, x[::-1]], 1)
            arr = (data * (scale - 1)).astype(dtype) if dtype != "float32" else data.astype("float32")
            wavfile.write(self.d / f"{dtype}.wav", 11025, arr)
            sr, y = I.read_wav(self.d / f"{dtype}.wav")
            self.assertEqual(sr, 11025)
            self.assertTrue(np.allclose(y, arr.astype(float) / scale, atol=1e-7), dtype)


class MidiTests(Tmp):
    def test_structure(self):
        piece = I.compose("midi", seconds=4.0)
        I.write_midi(self.d / "a.mid", piece)
        raw = (self.d / "a.mid").read_bytes()
        self.assertEqual(raw[:4], b"MThd")
        self.assertEqual(struct.unpack(">IHHH", raw[4:14]), (6, 0, 1, 480))
        self.assertEqual(raw[14:18], b"MTrk")
        self.assertEqual(struct.unpack(">I", raw[18:22])[0], len(raw) - 22)
        self.assertTrue(raw.endswith(b"\x00\xff\x2f\x00"))
        self.assertGreaterEqual(raw.count(b"\x90"), len(piece.notes))

    def test_variable_length_quantities(self):                             # SMF spec examples
        for n, enc in ((0, b"\x00"), (0x40, b"\x40"), (0x7F, b"\x7f"), (0x80, b"\x81\x00"), (0x2000, b"\xc0\x00"),
                       (0x3FFF, b"\xff\x7f"), (0x200000, b"\x81\x80\x80\x00"), (0x0FFFFFFF, b"\xff\xff\xff\x7f")):
            self.assertEqual(I.formats._vlq(n), enc)


class PngTests(Tmp):
    def images(self):
        u = chaos(64 * 48 * 4, "png")
        grad = np.add.outer(np.arange(48), np.arange(64)).astype(float)
        g8 = ((grad * 2 + 40 * u[:64 * 48].reshape(48, 64)) % 256).astype(np.uint8)
        return {
            "gray8": g8,
            "gray16": (grad * 700 + 3000 * u[:3072].reshape(48, 64)).astype(np.uint16),
            "gray+alpha": np.stack([g8, 255 - g8], 2),
            "rgb": np.stack([g8, g8[::-1], (g8.astype(int) * 3) % 256], 2).astype(np.uint8),
            "rgba16": (np.stack([grad, grad[::-1], grad * 0.5, 0 * grad + 40], 2) * 600).astype(np.uint16),
        }

    def test_round_trip_with_every_filter(self):
        for name, img in self.images().items():
            for f in (None, 0, 1, 2, 3, 4):
                with self.subTest(name, filter=f):
                    I.write_png(self.d / "a.png", img, filter_type=f)
                    self.assertTrue(np.array_equal(I.read_png(self.d / "a.png"), img))

    @unittest.skipIf(Image is None, "Pillow not installed")
    def test_pillow_reads_what_we_write(self):
        for name, img in self.images().items():
            if name == "rgba16":
                continue                                                   # Pillow has no 16-bit RGBA mode
            for f in (None, 1, 3, 4):
                I.write_png(self.d / "a.png", img, filter_type=f)
                ref = np.array(Image.open(self.d / "a.png"))
                with self.subTest(name, filter=f):
                    self.assertTrue(np.array_equal(ref.astype(img.dtype), img))

    @unittest.skipIf(Image is None, "Pillow not installed")
    def test_we_read_what_pillow_writes(self):
        img = self.images()["rgb"]
        Image.fromarray(img).save(self.d / "rgb.png")
        self.assertTrue(np.array_equal(I.read_png(self.d / "rgb.png"), img))
        Image.fromarray(img).convert("RGBA").save(self.d / "rgba.png")
        self.assertTrue(np.array_equal(I.read_png(self.d / "rgba.png")[:, :, :3], img))
        gray = self.images()["gray8"]
        Image.fromarray(gray).convert("1").save(self.d / "bw.png")                # 1-bit
        bw = np.array(Image.open(self.d / "bw.png").convert("L"))
        self.assertTrue(np.array_equal(I.read_png(self.d / "bw.png"), bw))
        pal = Image.fromarray(img).quantize(colors=13)                             # palette, 4-bit indices
        pal.info["transparency"] = 2
        pal.save(self.d / "pal.png", transparency=2, bits=4)
        ref = np.array(Image.open(self.d / "pal.png").convert("RGBA"))
        self.assertTrue(np.array_equal(I.read_png(self.d / "pal.png"), ref))

    @unittest.skipIf(pypng is None, "pypng not installed")
    def test_interlaced_and_low_bit_depths_from_pypng(self):
        img = self.images()["rgb"]
        with open(self.d / "i.png", "wb") as fh:
            pypng.Writer(64, 48, greyscale=False, interlace=True).write(fh, img.reshape(48, -1).tolist())
        self.assertTrue(np.array_equal(I.read_png(self.d / "i.png"), img))
        g16 = self.images()["gray16"]
        with open(self.d / "i16.png", "wb") as fh:
            pypng.Writer(64, 48, greyscale=True, bitdepth=16, interlace=True).write(fh, g16.tolist())
        self.assertTrue(np.array_equal(I.read_png(self.d / "i16.png"), g16))
        for depth in (2, 4):
            levels = (self.images()["gray8"] >> (8 - depth)).astype(np.uint8)
            with open(self.d / f"g{depth}.png", "wb") as fh:
                pypng.Writer(64, 48, greyscale=True, bitdepth=depth, interlace=depth == 4).write(fh, levels.tolist())
            expect = (levels.astype(int) * 255 // (2 ** depth - 1)).astype(np.uint8)
            self.assertTrue(np.array_equal(I.read_png(self.d / f"g{depth}.png"), expect), depth)
        with open(self.d / "key.png", "wb") as fh:                                 # tRNS colour key on grey
            pypng.Writer(64, 48, greyscale=True, transparent=7).write(fh, (self.images()["gray8"] % 16).tolist())
        ga = I.read_png(self.d / "key.png")
        self.assertEqual(ga.shape, (48, 64, 2))
        self.assertTrue(np.array_equal(ga[:, :, 1] == 0, self.images()["gray8"] % 16 == 7))

    def test_corruption_is_detected(self):
        I.write_png(self.d / "a.png", self.images()["gray8"])
        raw = bytearray((self.d / "a.png").read_bytes())
        raw[40] ^= 0xFF
        (self.d / "b.png").write_bytes(bytes(raw))
        with self.assertRaises((ValueError, zlib.error)):
            I.read_png(self.d / "b.png")
        (self.d / "c.png").write_bytes(b"GIF89a" + bytes(30))
        with self.assertRaises(ValueError):
            I.read_png(self.d / "c.png")

    def test_mask_by_otsu(self):
        truth = np.zeros((64, 64), bool)
        truth[10:20, :] = True
        img = np.where(truth, 40, 200) + (24 * (chaos(64 * 64, "o") - 0.5)).reshape(64, 64)
        img = img.astype(np.uint8)
        self.assertTrue(np.array_equal(I.image_mask(img), truth))                # minority = the dark band
        self.assertTrue(np.array_equal(I.image_mask(img, "light"), ~truth))
        rgba = np.dstack([img, img, img, np.where(np.arange(64) < 15, 0, 255)[:, None].repeat(64, 1)]).astype(np.uint8)
        m = I.image_mask(rgba, "dark")
        self.assertFalse(m[:15].any())                                            # transparent → background
        self.assertTrue(np.array_equal(m[15:], truth[15:]))


class TableTests(Tmp):
    def write(self, name, text):
        (self.d / name).write_text(text)
        return self.d / name

    def test_delimiters_headers_comments_and_gaps(self):
        csv = self.write("a.csv", "# made by hand\ntime,resp,ecg\n0,1,5\n0.5,,6\n1.0,3,7\n")
        names, tab = I.read_table(csv)
        self.assertEqual(names, ["time", "resp", "ecg"])
        self.assertTrue(np.isnan(tab[1, 1]))
        fs, x, info = I.read_series(csv, "resp", time_column="time")
        self.assertEqual((fs, info["nan_filled"]), (2.0, 1))
        self.assertTrue(np.allclose(x, [1, 2, 3]))
        tsv = self.write("b.tsv", "1\t10\n2\t20\n3\t30\n4\t40\n")
        fs, x, _ = I.read_series(tsv, 1, fs=100)
        self.assertTrue(np.allclose(x, [10, 20, 30, 40]))
        ws = self.write("c.txt", "  1.5   2.5\n  3.5   4.5\n")
        self.assertTrue(np.allclose(I.read_table(ws)[1], [[1.5, 2.5], [3.5, 4.5]]))
        semi = self.write("d.csv", "a;b\n1;2\n3;4\n")
        self.assertEqual(I.read_table(semi)[0], ["a", "b"])

    def test_irregular_time_is_resampled_and_errors_are_explained(self):
        t = np.array([0.0, 0.1, 0.2, 0.35, 0.4, 0.5])
        f = self.write("irr.csv", "t,v\n" + "".join(f"{a},{2 * a}\n" for a in t))
        fs, x, info = I.read_series(f, "v", time_column="t")
        self.assertAlmostEqual(fs, 10.0)
        self.assertTrue(info["resampled"])
        self.assertTrue(np.allclose(x, 2 * np.arange(6) * 0.1))
        two = self.write("two.csv", "a,b\n1,2\n3,4\n")
        for call, words in ((lambda: I.read_series(two, fs=1), "choose a column"),
                            (lambda: I.read_series(two, "a"), "--fs"),
                            (lambda: I.read_series(two, "zz", fs=1), "no column"),
                            (lambda: I.read_series(self.write("bad.csv", "1,2\n3,x\n"), 0, fs=1), "non-numeric")):
            with self.assertRaises(ValueError) as e:
                call()
            self.assertIn(words, str(e.exception))

    def test_wav_and_npy_series(self):
        I.write_wav(self.d / "s.wav", np.stack([np.zeros(100), 0.5 * np.ones(100)], 1), 1000)
        fs, x, _ = I.read_series(self.d / "s.wav", 1)
        self.assertEqual(fs, 1000.0)
        self.assertAlmostEqual(float(x.mean()), 0.5, delta=1e-4)
        np.save(self.d / "a.npy", np.arange(10.0))
        self.assertEqual(I.read_series(self.d / "a.npy", fs=5)[0], 5.0)
        with self.assertRaises(ValueError):
            I.read_series(self.d / "a.npy")

    def test_events_times_and_intervals(self):
        f = self.write("rr.txt", ",rr\n0,800\n1,820\n2,790\n3,\n4,810\n")         # pandas index column, a gap
        t, info = I.read_events(f, intervals=True, unit=1e-3)
        self.assertTrue(np.allclose(t, [0, 0.8, 1.62, 2.41, 3.22]))
        self.assertEqual(info["column"], "rr")
        g = self.write("beats.csv", "t_s\n0.5\n1.3\n2.1\n2.95\n")
        self.assertTrue(np.allclose(I.read_events(g)[0], [0.5, 1.3, 2.1, 2.95]))
        with self.assertRaises(ValueError):
            I.read_events(self.write("bad.csv", "t\n1\n0.5\n2\n"))

    def test_csv_writer(self):
        I.write_csv(self.d / "w.csv", ["a", "b"], [np.array([1.0, 2.5]), ["x", "y"]])
        self.assertEqual((self.d / "w.csv").read_text(), "a,b\n1,x\n2.5,y\n")


if __name__ == "__main__":
    unittest.main()
