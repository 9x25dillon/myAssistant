"""Julia lattices and box-counting dimension."""

from __future__ import annotations

import cmath
import math

import numpy as np


def cardioid_c(theta: float, radius: float) -> complex:
    """c = (λ/2)(1 − λ/2) with λ = radius·e^{iθ}. For radius < 1 the map z² + c has an attracting fixed point, so c
    lies in the Mandelbrot set's main cardioid and the Julia set is connected; radius → 1 moves c to the cardioid's
    edge, where the Julia set's boundary is most intricate."""
    lam = radius * complex(math.cos(theta), math.sin(theta))
    return lam / 2 * (1 - lam / 2)


def cardioid_coordinates(c: complex) -> tuple[float, float]:
    """Inverse of cardioid_c: λ = 1 − √(1 − 4c), returned as (θ, |λ|)."""
    lam = 1 - cmath.sqrt(1 - 4 * c)
    return math.atan2(lam.imag, lam.real) % (2 * math.pi), abs(lam)


def julia(c: complex, width: int = 128, height: int = 64, max_iter: int = 120, zoom: float = 1.0,
          center: tuple[float, float] = (0.0, 0.0)) -> tuple[np.ndarray, np.ndarray]:
    """(normalized escape time in [0, 1], filled-set mask) on a width × height grid."""
    xs = np.linspace(-1.8, 1.8, width) / zoom + center[0]
    ys = np.linspace(-1.2, 1.2, height) / zoom + center[1]
    z = xs[None, :] + 1j * ys[:, None]
    escape = np.full(z.shape, max_iter, dtype=float)
    alive = np.ones(z.shape, dtype=bool)
    for i in range(max_iter):
        z[alive] = z[alive] * z[alive] + c
        out = alive & (np.abs(z) > 2.0)
        escape[out] = i
        alive &= ~out
        if not alive.any():
            break
    return escape / max_iter, alive


def box_dimension(mask: np.ndarray) -> float:
    """Box-counting dimension: slope of log N(s) against log(1/s) over box sizes 2, 4, ..., n/8.

    Grids coarser than 8 boxes per side are left out: there, edge terms (a square outline has 4(n/s) − 4 boxes,
    not 4(n/s)) bend the log-log line and bias the slope upward. Returns 0.0 when fewer than two scales are occupied.
    """
    m = np.asarray(mask, dtype=bool)
    if m.ndim != 2 or min(m.shape) < 16:
        raise ValueError(f"box_dimension needs a 2-D mask at least 16 × 16, got shape {m.shape}")
    n = 1 << int(math.floor(math.log2(min(m.shape))))
    m = m[:n, :n]
    sizes, counts = [], []
    s = n // 8
    while s >= 2:
        k = n // s
        blocks = m[:k * s, :k * s].reshape(k, s, k, s).any(axis=(1, 3))
        if blocks.sum() > 0:
            sizes.append(s)
            counts.append(int(blocks.sum()))
        s //= 2
    if len(sizes) < 2:
        return 0.0
    return float(np.polyfit(np.log(1.0 / np.array(sizes)), np.log(counts), 1)[0])


def boundary(filled: np.ndarray) -> np.ndarray:
    """Cells of the filled set with at least one 4-neighbour outside it."""
    f = np.asarray(filled, dtype=bool)
    p = np.pad(f, 1, constant_values=False)
    inner = p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
    return f & ~inner


def edge_dimension(c: complex, size: int = 512, max_iter: int = 200) -> float:
    """Box dimension of the Julia set's boundary for parameter c, on a size × size grid."""
    return box_dimension(boundary(julia(c, size, size, max_iter)[1]))
