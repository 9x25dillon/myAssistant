"""Every file format the endpoints read or write, stdlib + numpy only.

    WAV   read: RIFF PCM 8/16/24/32-bit, IEEE float 32/64, WAVE_FORMAT_EXTENSIBLE.   write: 16-bit PCM, any channels
    MIDI  write: Standard MIDI File type 0
    PNG   read: all colour types and bit depths, Adam7 interlace, tRNS.               write: 8/16-bit gray/RGB/RGBA
    text  read: CSV / TSV / semicolon / whitespace columns, optional header, '#' comments, a time column or --fs
    NPY   read: 1-D or 2-D numeric arrays (allow_pickle=False)
"""

from __future__ import annotations

import math
import struct
import wave
import zlib
from pathlib import Path

import numpy as np

from .score import Piece

# ============================================================================================ WAV

_PCM, _FLOAT, _EXTENSIBLE = 0x0001, 0x0003, 0xFFFE


def write_wav(path: str | Path, audio: np.ndarray, sr: int = 22050) -> None:
    """16-bit PCM. `audio` is (n,) or (n, channels), in [−1, 1]."""
    a = np.asarray(audio, dtype=float)
    channels = 1 if a.ndim == 1 else a.shape[1]
    pcm = np.clip(np.round(a * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def read_wav(path: str | Path) -> tuple[int, np.ndarray]:
    """(sample rate, samples as float64 of shape (frames, channels) in [−1, 1])."""
    data = Path(path).read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a RIFF/WAVE file")
    fmt = pcm = None
    pos = 12
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body_end = len(data) if size == 0xFFFFFFFF else min(len(data), pos + 8 + size)   # streamed: size unknown
        if cid == b"fmt ":
            fmt = data[pos + 8:body_end]
        elif cid == b"data":
            pcm = data[pos + 8:body_end]
        pos = body_end + (size & 1 if size != 0xFFFFFFFF else 0)
    if fmt is None or pcm is None or len(fmt) < 16:
        raise ValueError(f"{path}: missing fmt or data chunk")
    tag, channels, sr, _, block, bits = struct.unpack("<HHIIHH", fmt[:16])
    if tag == _EXTENSIBLE:
        if len(fmt) < 40:
            raise ValueError(f"{path}: truncated WAVE_FORMAT_EXTENSIBLE header")
        tag = struct.unpack("<H", fmt[24:26])[0]                         # first two bytes of the subformat GUID
    if channels < 1 or block < 1 or block != channels * ((bits + 7) // 8):
        raise ValueError(f"{path}: inconsistent header ({channels} channels, {bits} bits, block {block})")
    frames = len(pcm) // block
    raw = np.frombuffer(pcm[:frames * block], dtype=np.uint8)
    width = block // channels
    if tag == _PCM and width == 1:
        x = (raw.astype(np.float64) - 128.0) / 128.0
    elif tag == _PCM and width == 2:
        x = raw.view("<i2").astype(np.float64) / 32768.0
    elif tag == _PCM and width == 3:
        b = raw.reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v).astype(np.float64) / float(1 << 23)
    elif tag == _PCM and width == 4:
        x = raw.view("<i4").astype(np.float64) / float(1 << 31)
    elif tag == _FLOAT and width == 4:
        x = raw.view("<f4").astype(np.float64)
    elif tag == _FLOAT and width == 8:
        x = raw.view("<f8").astype(np.float64)
    else:
        raise ValueError(f"{path}: format tag 0x{tag:04x} with {bits}-bit samples is neither PCM nor IEEE float "
                         "(compressed WAV: decode it to PCM first)")
    return sr, x.reshape(frames, channels)


# ============================================================================================ MIDI

def _vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def write_midi(path: str | Path, piece: Piece, bpm: float = 120.0, division: int = 480) -> None:
    """Standard MIDI File type 0: notes on channel 1 and the LFO rate on CC1 (mod wheel), log-mapped 0.1–8 Hz."""
    tick = division * bpm / 60.0                                          # ticks per second
    events: list[tuple[int, int, bytes]] = []                             # (tick, order, bytes)
    for nt in piece.notes:
        events.append((round(nt.start * tick), 1, bytes([0x90, nt.pitch, nt.velocity])))
        events.append((round((nt.start + nt.duration) * tick), 0, bytes([0x80, nt.pitch, 0])))
    lo, hi = math.log(0.1), math.log(8.0)
    for col, rate in enumerate(piece.lfo_rate):
        cc = int(round(127 * (math.log(rate) - lo) / (hi - lo)))
        events.append((round(col * piece.step * tick), 2, bytes([0xB0, 1, max(0, min(127, cc))])))
    events.sort()
    track = bytearray(b"\x00\xff\x51\x03" + int(60e6 / bpm).to_bytes(3, "big"))
    name = f"infrasonomancer: {piece.seed}".encode("utf-8")[:120]
    track += b"\x00\xff\x03" + _vlq(len(name)) + name
    last = 0
    for t, _, data in events:
        track += _vlq(t - last) + data
        last = t
    track += b"\x00\xff\x2f\x00"
    with open(path, "wb") as fh:
        fh.write(b"MThd" + struct.pack(">IHHH", 6, 0, 1, division))
        fh.write(b"MTrk" + struct.pack(">I", len(track)) + track)


# ============================================================================================ PNG

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def _paeth(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    p = a + b - c
    pa, pb, pc = np.abs(p - a), np.abs(p - b), np.abs(p - c)
    return np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, b, c))


def _unfilter(stream: memoryview, pos: int, rows: int, row_bytes: int, bpp: int) -> tuple[np.ndarray, int]:
    out = np.zeros((rows, row_bytes), dtype=np.uint8)
    prior = np.zeros(row_bytes, dtype=np.int64)
    for y in range(rows):
        if pos + 1 + row_bytes > len(stream):
            raise ValueError("PNG image data is truncated")
        ftype = stream[pos]
        f = np.frombuffer(stream[pos + 1:pos + 1 + row_bytes], dtype=np.uint8).astype(np.int64)
        pos += 1 + row_bytes
        if ftype == 0:
            r = f
        elif ftype == 1:                                                   # Sub: a running sum per byte lane
            r = np.empty_like(f)
            for j in range(bpp):
                r[j::bpp] = np.cumsum(f[j::bpp]) & 0xFF
        elif ftype == 2:
            r = (f + prior) & 0xFF
        elif ftype in (3, 4):                                              # Average, Paeth: serial recurrences
            fl, up, rl = f.tolist(), prior.tolist(), [0] * row_bytes
            for i in range(row_bytes):
                a = rl[i - bpp] if i >= bpp else 0
                if ftype == 3:
                    rl[i] = (fl[i] + ((a + up[i]) >> 1)) & 0xFF
                else:
                    b, c = up[i], (up[i - bpp] if i >= bpp else 0)
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    rl[i] = (fl[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 0xFF
            r = np.array(rl, dtype=np.int64)
        else:
            raise ValueError(f"PNG filter type {ftype} is not defined")
        out[y] = r
        prior = r
    return out, pos


def _unpack(rows: np.ndarray, width: int, channels: int, depth: int) -> np.ndarray:
    if depth == 16:
        return rows.view(">u2").reshape(rows.shape[0], width, channels).astype(np.uint16)
    if depth == 8:
        return rows.reshape(rows.shape[0], width, channels)
    shifts = np.arange(8 - depth, -1, -depth, dtype=np.uint8)                # most significant bits first
    vals = (rows[:, :, None] >> shifts) & ((1 << depth) - 1)
    return vals.reshape(rows.shape[0], -1)[:, :width * channels].reshape(rows.shape[0], width, channels)


def read_png(path: str | Path) -> np.ndarray:
    """Pixel array: (h, w) gray, (h, w, 2) gray+alpha, (h, w, 3) RGB, (h, w, 4) RGBA; uint8 or uint16. Palette images
    are expanded to RGB, or RGBA when a tRNS chunk is present; gray/RGB tRNS keys become an alpha channel."""
    data = Path(path).read_bytes()
    if data[:8] != _PNG_SIG:
        raise ValueError(f"{path}: not a PNG file")
    pos, idat, palette, trns, header = 8, bytearray(), None, None, None
    while pos + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length or zlib.crc32(ctype + body) != struct.unpack(">I", data[pos + 8 + length:
                                                                                   pos + 12 + length])[0]:
            raise ValueError(f"{path}: chunk {ctype!r} is truncated or fails its CRC")
        if ctype == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif ctype == b"PLTE":
            palette = np.frombuffer(body, dtype=np.uint8).reshape(-1, 3)
        elif ctype == b"tRNS":
            trns = body
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if header is None:
        raise ValueError(f"{path}: no IHDR chunk")
    width, height, depth, ctype_, compression, filt, interlace = header
    if ctype_ not in _CHANNELS or depth not in _DEPTHS[ctype_] or compression or filt or interlace > 1:
        raise ValueError(f"{path}: invalid PNG header (colour type {ctype_}, depth {depth}, interlace {interlace})")
    if ctype_ == 3 and palette is None:
        raise ValueError(f"{path}: palette image without PLTE")
    channels = _CHANNELS[ctype_]
    bpp = max(1, depth * channels // 8)
    stream = memoryview(zlib.decompress(bytes(idat)))
    shape = (height, width, channels)
    img = np.zeros(shape, dtype=np.uint16 if depth == 16 else np.uint8)
    passes = _ADAM7 if interlace else ((0, 0, 1, 1),)
    pos = 0
    for x0, y0, dx, dy in passes:
        pw, ph = -(-(width - x0) // dx) if width > x0 else 0, -(-(height - y0) // dy) if height > y0 else 0
        if pw == 0 or ph == 0:
            continue
        rows, pos = _unfilter(stream, pos, ph, -(-(pw * channels * depth) // 8), bpp)
        img[y0::dy, x0::dx] = _unpack(rows, pw, channels, depth)
    if ctype_ == 3:
        idx = img[:, :, 0].astype(np.intp)
        if idx.max(initial=0) >= len(palette):
            raise ValueError(f"{path}: palette index out of range")
        rgb = palette[idx]
        if trns is None:
            return rgb
        alpha = np.full(len(palette), 255, dtype=np.uint8)
        alpha[:len(trns)] = np.frombuffer(trns, dtype=np.uint8)[:len(palette)]
        return np.concatenate([rgb, alpha[idx][:, :, None]], axis=2)
    if trns is not None and ctype_ in (0, 2):
        key = np.array(struct.unpack(">" + "H" * channels, trns[:2 * channels]))
        alpha = np.where((img.reshape(height, width, channels) == key).all(axis=2), 0, (1 << depth) - 1)
        img = np.concatenate([img, alpha.astype(img.dtype)[:, :, None]], axis=2)
        channels += 1
    if depth < 8 and ctype_ == 0:
        img = (img.astype(np.uint16) * 255 // ((1 << depth) - 1)).astype(np.uint8)   # 1/2/4-bit gray → 0..255
    return img[:, :, 0] if channels == 1 else img


def write_png(path: str | Path, img: np.ndarray, filter_type: int | None = None) -> None:
    """8- or 16-bit gray (h, w), gray+alpha (h, w, 2), RGB (h, w, 3) or RGBA (h, w, 4). By default each row takes the
    filter with the smallest sum of absolute signed residuals (the libpng heuristic); filter_type 0–4 forces one."""
    if filter_type is not None and filter_type not in range(5):
        raise ValueError(f"filter_type must be 0-4 or None, got {filter_type}")
    a = np.asarray(img)
    if a.dtype == bool:
        a = a.astype(np.uint8) * 255
    if a.dtype not in (np.uint8, np.uint16):
        raise ValueError(f"write_png needs uint8 or uint16 pixels, got {a.dtype}")
    if a.ndim == 2:
        a = a[:, :, None]
    if a.ndim != 3 or a.shape[2] not in (1, 2, 3, 4):
        raise ValueError(f"write_png needs (h, w) or (h, w, 1-4), got {np.asarray(img).shape}")
    h, w, ch = a.shape
    depth = 16 if a.dtype == np.uint16 else 8
    raw = (a.astype(">u2").view(np.uint8) if depth == 16 else a).reshape(h, -1).astype(np.int64)
    bpp = ch * depth // 8
    prior = np.zeros(raw.shape[1], dtype=np.int64)
    out = bytearray()
    for y in range(h):
        r = raw[y]
        left = np.concatenate([np.zeros(bpp, np.int64), r[:-bpp]])
        upleft = np.concatenate([np.zeros(bpp, np.int64), prior[:-bpp]])
        cands = (r, r - left, r - prior, r - ((left + prior) >> 1), r - _paeth(left, prior, upleft))
        cands = [c & 0xFF for c in cands]
        cost = [int(np.abs(np.where(c > 127, c - 256, c)).sum()) for c in cands]
        k = int(np.argmin(cost)) if filter_type is None else filter_type
        out.append(k)
        out += cands[k].astype(np.uint8).tobytes()
        prior = r
    ctype = {1: 0, 2: 4, 3: 2, 4: 6}[ch]

    def chunk(t: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + t + body + struct.pack(">I", zlib.crc32(t + body))

    Path(path).write_bytes(_PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(bytes(out), 9)) + chunk(b"IEND", b""))


def image_mask(img: np.ndarray, foreground: str = "minority") -> np.ndarray:
    """Binary mask of an image by Otsu's threshold on luminance; transparent pixels are background.
    foreground: 'dark', 'light', or 'minority' (whichever class has fewer pixels: the drawn set, usually)."""
    src = np.asarray(img)
    if src.dtype == bool:
        return src.copy()
    peak = {np.dtype(np.uint8): 255.0, np.dtype(np.uint16): 65535.0}.get(src.dtype, max(1.0, float(np.max(src))))
    a = src.astype(np.float64)
    alpha = None
    if a.ndim == 3:
        if a.shape[2] in (2, 4):
            alpha, a = a[:, :, -1] / peak, a[:, :, :-1]
        a = a @ np.array([0.2126, 0.7152, 0.0722]) if a.shape[2] == 3 else a[:, :, 0]
    lum = a / peak
    hist = np.histogram(lum, bins=256, range=(0.0, 1.0))[0].astype(np.float64)
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    mu = np.cumsum(hist * (np.arange(256) + 0.5))
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mu[-1] * w0 / w0[-1] - mu) ** 2 / (w0 * w1)
    between[~np.isfinite(between)] = -1
    thresh = (int(np.argmax(between)) + 1) / 256.0
    dark = lum < thresh
    if foreground == "dark":
        mask = dark
    elif foreground == "light":
        mask = ~dark
    elif foreground == "minority":
        mask = dark if dark.sum() <= dark.size / 2 else ~dark
    else:
        raise ValueError(f"foreground must be dark, light or minority, got {foreground!r}")
    return mask if alpha is None else mask & (alpha > 0.5)


# ============================================================================================ series

def _numeric(token: str) -> float | None:
    t = token.strip()
    if t == "" or t.lower() in ("nan", "na", "null", "none"):
        return math.nan
    try:
        return float(t)
    except ValueError:
        return None


def read_table(path: str | Path) -> tuple[list[str], np.ndarray]:
    """(column names, float array of shape (rows, columns)). Missing cells are NaN. Without a header the columns
    are named 0, 1, ...; an empty header cell at position i is named _i (pandas writes its index that way)."""
    lines = [ln for ln in Path(path).read_text(encoding="utf-8-sig").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise ValueError(f"{path}: no data rows")
    probe = lines[min(1, len(lines) - 1)]
    delim = "," if "," in probe else "\t" if "\t" in probe else ";" if ";" in probe else None

    def split(line: str) -> list[str]:
        return line.split(delim) if delim else line.split()

    first = split(lines[0])
    header = any(_numeric(tok) is None for tok in first)
    names = ([tok.strip() or f"_{i}" for i, tok in enumerate(first)] if header      # "_0": an unnamed (index) column
             else [str(i) for i in range(len(first))])
    body = lines[1:] if header else lines
    rows = []
    for k, line in enumerate(body, start=2 if header else 1):
        vals = [_numeric(tok) for tok in split(line)]
        if any(v is None for v in vals):
            raise ValueError(f"{path}: line {k} has a non-numeric cell: {line[:80]!r}")
        vals += [math.nan] * (len(names) - len(vals))
        rows.append(vals[:len(names)])
    if not rows:
        raise ValueError(f"{path}: header but no data rows")
    return names, np.array(rows, dtype=np.float64)


def _pick(names: list[str], column: str | int | None, path: str | Path, exclude: set[int] = frozenset()) -> int:
    if column is None:
        candidates = [i for i in range(len(names)) if i not in exclude]
        if len(candidates) != 1:
            raise ValueError(f"{path}: choose a column with --column; columns are {names}")
        return candidates[0]
    if isinstance(column, int) or str(column).lstrip("-").isdigit() and str(column) not in names:
        i = int(column)
        if not -len(names) <= i < len(names):
            raise ValueError(f"{path}: column {i} out of range; columns are {names}")
        return i % len(names)
    if str(column) not in names:
        raise ValueError(f"{path}: no column {column!r}; columns are {names}")
    return names.index(str(column))


def _index_columns(names: list[str]) -> set[int]:
    return {0} if names and names[0] in ("_0", "index", "Unnamed: 0") else set()


def _fill_nan(x: np.ndarray) -> tuple[np.ndarray, int]:
    bad = ~np.isfinite(x)
    if not bad.any():
        return x, 0
    good = np.flatnonzero(~bad)
    if len(good) < 2:
        raise ValueError("series has fewer than two finite samples")
    x = x[good[0]:good[-1] + 1].copy()
    bad = ~np.isfinite(x)
    idx = np.arange(len(x))
    x[bad] = np.interp(idx[bad], idx[~bad], x[~bad])
    return x, int(bad.sum())


def read_series(path: str | Path, column: str | int | None = None, fs: float | None = None,
                time_column: str | int | None = None) -> tuple[float, np.ndarray, dict]:
    """(sample rate Hz, uniformly sampled float series, provenance). WAV carries its own rate; NPY and text need
    `fs` or a time column (seconds). An irregular time column is resampled linearly at its median step; interior
    NaNs are interpolated and edge NaNs trimmed, and both are counted in the provenance."""
    p = Path(path)
    info: dict = {"path": str(p)}
    suffix = p.suffix.lower()
    if suffix == ".wav":
        sr, x = read_wav(p)
        if fs is not None and abs(fs - sr) > 1e-9:
            raise ValueError(f"{p}: the file says {sr} Hz, --fs says {fs}")
        i = _pick([str(k) for k in range(x.shape[1])], 0 if column is None else column, p)
        fs, series, info["column"] = float(sr), x[:, i], i
    elif suffix == ".npy":
        arr = np.load(p, allow_pickle=False)
        if arr.ndim == 1:
            series = arr.astype(np.float64)
            info["column"] = 0
        elif arr.ndim == 2:
            i = _pick([str(k) for k in range(arr.shape[1])], column, p)
            series, info["column"] = arr[:, i].astype(np.float64), i
        else:
            raise ValueError(f"{p}: expected a 1-D or 2-D array, got shape {arr.shape}")
        if fs is None:
            raise ValueError(f"{p}: an .npy array has no time base; pass --fs")
    else:
        names, table = read_table(p)
        tcol = None if time_column is None else _pick(names, time_column, p)
        i = _pick(names, column, p, exclude=_index_columns(names) | ({tcol} if tcol is not None else set()))
        series, info["column"] = table[:, i], names[i]
        if tcol is not None:
            t = table[:, tcol]
            ok = np.isfinite(t)
            t, series = t[ok], series[ok]
            dt = np.diff(t)
            if len(dt) < 1 or np.any(dt <= 0):
                raise ValueError(f"{p}: time column {names[tcol]!r} must be strictly increasing")
            step = float(np.median(dt))
            if fs is not None and abs(1 / step - fs) > 0.01 * fs:
                raise ValueError(f"{p}: time column implies {1 / step:.6g} Hz, --fs says {fs}")
            fs = 1.0 / step
            if np.max(np.abs(dt - step)) > 0.01 * step:
                grid = np.arange(t[0], t[-1] + step / 2, step)
                finite = np.isfinite(series)
                series = np.interp(grid, t[finite], series[finite])
                info["resampled"] = True
            info["time_column"] = names[tcol]
        elif fs is None:
            raise ValueError(f"{p}: no time column given; pass --fs or --time-column")
    if not fs > 0:
        raise ValueError(f"{p}: sample rate must be > 0")
    series, filled = _fill_nan(np.asarray(series, dtype=np.float64))
    info.update(fs=float(fs), samples=len(series), seconds=len(series) / fs, nan_filled=filled)
    return float(fs), series, info


def read_events(path: str | Path, column: str | int | None = None, intervals: bool = False,
                unit: float = 1.0) -> tuple[np.ndarray, dict]:
    """Event times in seconds, strictly increasing. With `intervals`, the column holds successive intervals
    (RR intervals, say) and times are their running sum from 0. `unit` converts to seconds (1e-3 for ms)."""
    p = Path(path)
    if p.suffix.lower() == ".npy":
        arr = np.load(p, allow_pickle=False).astype(np.float64)
        v = arr if arr.ndim == 1 else arr[:, _pick([str(k) for k in range(arr.shape[1])], column, p)]
        col = column or 0
    else:
        names, table = read_table(p)
        i = _pick(names, column, p, exclude=_index_columns(names))
        v, col = table[:, i], names[i]
    v = v[np.isfinite(v)] * unit
    if intervals:
        if np.any(v <= 0):
            raise ValueError(f"{p}: intervals must be > 0")
        v = np.concatenate([[0.0], np.cumsum(v)])
    if len(v) < 3 or np.any(np.diff(v) <= 0):
        raise ValueError(f"{p}: need at least 3 strictly increasing event times")
    return v, {"path": str(p), "column": col, "events": len(v), "intervals": intervals, "unit_s": unit}


def write_csv(path: str | Path, header: list[str], columns: list[np.ndarray], fmt: str = "{:.6g}") -> None:
    n = len(columns[0])
    if any(len(c) != n for c in columns):
        raise ValueError("write_csv: columns differ in length")
    lines = [",".join(header)]
    lines += [",".join(fmt.format(c[k]) if isinstance(c[k], (float, np.floating)) else str(c[k]) for c in columns)
              for k in range(n)]
    Path(path).write_text("\n".join(lines) + "\n")
