"""Synthetic signals with known answers. All noise comes from Chaos, so every test is deterministic."""

import numpy as np

import infrasonomancer as I


def chaos(n, seed="test"):
    return I.Chaos(seed).uniform(n)


def beat_times(seconds, base_rr=0.85, rsa=0.06, jitter=0.02, f_resp=0.25, seed="rr"):
    """Beat times whose RR intervals follow breathing (respiratory sinus arrhythmia) plus jitter."""
    u = chaos(int(seconds / 0.3) + 10, seed)
    t, out, k = 0.4, [], 0
    while t < seconds - 0.6:
        out.append(t)
        t += base_rr + rsa * np.sin(2 * np.pi * f_resp * t) + jitter * (u[k] - 0.5)
        k += 1
    return np.array(out)


def synthetic_ecg(beats, fs, seconds, polarity=1.0, noise=0.03, scale=None, seed="ecg"):
    """P-QRS-T complexes as Gaussians (McSharry et al. 2003, simplified) at the given R times, plus baseline
    wander, 50 Hz mains and noise. scale: optional per-beat amplitude factors."""
    n = int(seconds * fs)
    t = np.arange(n) / fs
    x = np.zeros(n)
    waves = ((-0.20, 0.025, 0.12), (-0.035, 0.010, -0.12), (0.0, 0.009, 1.0), (0.035, 0.010, -0.25),
             (0.25, 0.045, 0.30))
    for k, tk in enumerate(beats):
        a = (1 + 0.25 * np.sin(2 * np.pi * 0.1 * tk)) * (1.0 if scale is None else scale[k])
        i0, i1 = max(0, int((tk - 0.5) * fs)), min(n, int((tk + 0.6) * fs))
        tt = t[i0:i1] - tk
        for off, sd, amp in waves:
            x[i0:i1] += a * amp * np.exp(-((tt - off) ** 2) / (2 * sd ** 2))
    x = polarity * x
    x += 0.4 * np.sin(2 * np.pi * 0.3 * t) + 0.2 * np.sin(2 * np.pi * 0.05 * t) + 0.05 * np.sin(2 * np.pi * 50 * t)
    return x + 2 * noise * (chaos(n, seed) - 0.5)


def synthetic_ppg(beats, fs, seconds, ptt=0.25, noise=0.02, seed="ppg"):
    """A pulse wave (systolic and dicrotic Gaussians) `ptt` seconds after each beat; steepest upstroke at a fixed
    offset from the beat."""
    n = int(seconds * fs)
    t = np.arange(n) / fs
    x = np.zeros(n)
    for tk in beats:
        i0, i1 = max(0, int((tk + ptt - 0.3) * fs)), min(n, int((tk + ptt + 0.9) * fs))
        tt = t[i0:i1] - tk - ptt
        x[i0:i1] += np.exp(-((tt - 0.12) ** 2) / (2 * 0.06 ** 2)) + 0.35 * np.exp(-((tt - 0.38) ** 2) / (2 * 0.07 ** 2))
    x += 0.3 * np.sin(2 * np.pi * 0.07 * t)
    return x + 2 * noise * (chaos(n, seed) - 0.5)


def breathing(seconds, fs, f=0.25, wobble=0.02, seed="breath"):
    """(signal, phase) of a breathing trace whose rate wanders slowly."""
    t = np.arange(int(seconds * fs)) / fs
    phase = 2 * np.pi * f * t + 0.3 * np.sin(2 * np.pi * wobble * t)
    return np.cos(phase) + 0.1 * (chaos(len(t), seed) - 0.5), phase


def locked_beats(breath_phase, fs, n=4, m=1, jitter=0.03, seed="lock"):
    """n beats per m breaths, phase-locked: beat k falls where (n/m)·φ_breath crosses 2πk, then jittered by
    ±jitter seconds (uniform)."""
    target = n * breath_phase / m
    t = np.arange(len(breath_phase)) / fs
    k = np.arange(np.ceil(target[0] / (2 * np.pi)) + 1, np.floor(target[-1] / (2 * np.pi)))
    times = np.interp(2 * np.pi * k, target, t)
    return times + 2 * jitter * (chaos(len(times), seed) - 0.5)


def free_beats(seconds, rate=1.07, seed="free"):
    """Heartbeats with their own slowly wandering rate, unrelated to breathing."""
    t = np.arange(int(seconds * 50)) / 50
    phase = 2 * np.pi * np.cumsum(rate + 0.12 * np.sin(2 * np.pi * 0.013 * t + 1.0)
                                  + 0.05 * (chaos(len(t), seed) - 0.5)) / 50
    k = np.arange(1, np.floor(phase[-1] / (2 * np.pi)))
    return np.interp(2 * np.pi * k, phase, t)
