"""Deterministic variates from the r = 4 logistic map, seeded by text. No PRNG anywhere in the package."""

from __future__ import annotations

import hashlib
import math

import numpy as np

PHI = (math.sqrt(5.0) - 1.0) / 2.0


class Chaos:
    """Uniform variates from x ↦ 4x(1−x). Deterministic; not cryptographic.

    The map has invariant density 1/(π√(x(1−x))); u = (2/π)·arcsin(√x) carries it exactly onto U(0, 1).
    64 lanes advance together, every 3rd iterate is kept, and a golden-ratio Weyl rotation breaks the residual
    structure of a single orbit (the same construction as kgirl.evolve.chaos).
    """

    def __init__(self, seed: str, lanes: int = 64):
        h = hashlib.sha256(seed.encode("utf-8")).digest()
        base = int.from_bytes(h[:8], "big") / 2 ** 64
        self._weyl = int.from_bytes(h[8:16], "big") / 2 ** 64
        self._x = 0.05 + 0.9 * ((base + PHI * (np.arange(lanes) + 1)) % 1.0)
        self.digest = h
        for _ in range(16):
            self._step()

    def _step(self) -> None:
        x = self._x
        for _ in range(3):
            x = 4.0 * x * (1.0 - x)
        stuck = (x < 1e-12) | (x > 1 - 1e-12) | (np.abs(x - 0.75) < 1e-12)
        x[stuck] = 0.05 + 0.9 * ((np.arange(int(stuck.sum())) * PHI + self._weyl + 0.137) % 1.0)
        self._x = x

    def uniform(self, n: int) -> np.ndarray:
        out = np.empty(n)
        for i in range(0, n, len(self._x)):
            self._step()
            u = (2.0 / np.pi) * np.arcsin(np.sqrt(self._x))
            self._weyl = (self._weyl + PHI) % 1.0
            take = min(len(u), n - i)
            out[i:i + take] = ((u + self._weyl) % 1.0)[:take]
        return out

    def scalar(self) -> float:
        return float(self.uniform(1)[0])

    def normal(self, n: int) -> np.ndarray:
        """Standard normal variates by Box–Muller on pairs of uniforms."""
        u = self.uniform(2 * ((n + 1) // 2)).reshape(-1, 2)
        r = np.sqrt(-2.0 * np.log(np.maximum(u[:, 0], 1e-300)))
        z = np.concatenate([r * np.cos(2 * np.pi * u[:, 1]), r * np.sin(2 * np.pi * u[:, 1])])
        return z[:n]

    def integers(self, n: int, high: int) -> np.ndarray:
        """Integers in [0, high)."""
        return np.minimum((self.uniform(n) * high).astype(np.int64), high - 1)
