# Fractal Infrasonomancer 3.1 · measured

Seed text → Julia fractal → score (MIDI) and audio (WAV) with a 0.1–8 Hz pulse, plus the measurement tools the
source texts only named, each callable on your own files. Python ≥ 3.10 and numpy; nothing else at run time.

```
seed ─sha256─▶ Genome (θ, radius, zoom, density, mode, root) ─▶ Julia lattice, c in the main cardioid
     ─▶ score: columns = time, rows = degrees of the mode; filled interior silent, the edge sings
     ─▶ pulse: lattice column means set a 0.1–8 Hz rate → amplitude modulation (stereo: antiphase L/R)
     ─▶ render.wav + score.mid + report.json + genome.json
```

## Commands

| command | does | writes |
|---|---|---|
| `compose SEED [--genome G] [--stereo]` | the piece a seed (or a genome) defines | `render.wav score.mid report.json genome.json` |
| `evolve SEED [--objective recurrence\|coupling]` | MAP-Elites over genomes; seed's own genome is the baseline | `archive.json champion/ elite_NN/` |
| `beats FILE --kind ecg\|ppg` | heartbeats (Pan–Tompkins / slope-sum) and HRV (Task Force 1996) | beat-time CSV, JSON |
| `coherence --x F --x-kind K --y F --y-kind K` | n:m phase synchronization + rhythm↔rate spectral coherence, surrogate p-values | `coherence.json windows.csv synchrogram.csv` |
| `pll FILE --f0 HZ` | second-order PLL: lock fraction, frequency track | track CSV, JSON |
| `series FILE` | dominant rate, Hurst (R/S), DFA α, persistent-H1 recurrence | JSON |
| `fractal --c RE,IM \| --seed TEXT \| --image PNG` | box-counting dimension; writes the set or the mask as PNG | PNG, JSON |
| `dualcast [--carrier --deviation --samples ...] [--exact]` | the source texts' dual-wavelength cast, reproduced and measured | `source_stereo.wav combined.wav transmitted.wav analysis.json` |
| `cardioresp [--n --m --detuning --coupling ...] [--sonify]` | breath and heart as coupled oscillators: raw recording, ground truth, assessment; the counter-pair render | `recording.csv beats_true.csv assessment.json dualcast_pair.wav nulls.csv` |
| `envelope [--target locking\|statistics\|measurement] [--axes A,B]` | the MAP-Elites engine repurposed: worst case per cell of a scenario grid, failures replayed | `archive.json map.csv` |

Inputs: `.wav` (any PCM width, float, extensible), `.npy` (with `--fs`), text columns (CSV/TSV/`;`/whitespace,
optional header, `#` comments, `--fs` or `--time-column`; irregular time is resampled, gaps interpolated and
counted). Stream kinds for `coherence`: `signal`, `ecg`, `ppg`, `beats` (event times), `rr` (intervals, `--x-unit
0.001` for ms). Exit 0 on success, 1 with a reason when the data cannot be processed, 2 on a usage error.

The commands that produced the files in `out/`:

```
python -m infrasonomancer compose "infrasonomantic digiology – K1LL x DIANNE v1" --out out/k1ll_x_dianne/original
python -m infrasonomancer compose "infrasonomantic digiology – K1LL x DIANNE v1" --stereo --out out/k1ll_x_dianne/stereo
python -m infrasonomancer evolve  "infrasonomantic digiology – K1LL x DIANNE v1" --render-top 3 --out out/k1ll_x_dianne/evolve
python -m infrasonomancer compose "NeuroSymbiotic Coherence Seed" --out out/nscts/original      # likewise stereo, evolve
python validate_real.py --data biodata --fetch --out out/validation.json
python -m infrasonomancer beats biodata/Task1_ECG.npy --fs 1000 --kind ecg --out beats.csv
python -m infrasonomancer coherence --x biodata/Task1_Respiration.npy --x-kind signal --x-fs 1000 --x-band 0.15,0.5 \
       --y beats.csv --y-kind beats --out coherence/
python -m infrasonomancer fractal --c=-0.123,0.745 --png rabbit.png
python -m infrasonomancer dualcast --out out/dualcast                       # --exact for exact-phase signals
python -m infrasonomancer cardioresp --sonify --out out/cardioresp/locked
python -m infrasonomancer cardioresp --detuning 2.5 --sonify --out out/cardioresp/drifting
python -m infrasonomancer envelope --target locking --axes detuning,sensor_noise --iterations 200 --out out/envelope/locking
python -m infrasonomancer envelope --target statistics --axes detuning,breath_noise --iterations 200 --out out/envelope/statistics
python -m infrasonomancer envelope --target measurement --axes detuning,sensor_noise --iterations 200 --out out/envelope/measurement
python -m unittest discover -s tests -t .
```

## Evidence

**L0 — standard methods, each tested against a known answer (102 tests in all).**
- Chaos generator: uniform moments and histogram; Box–Muller normals (95 % within ±1.96).
- Box dimension: line 1.0, square 2.0, Sierpinski carpet 1.893 (log 8 / log 3), Douady's rabbit edge in (1.1, 1.6).
- Persistent homology: one loop for a circle, two for two circles, none for a uniform cloud.
- DFA: white 0.5, 1/f 1.0, Brownian 1.5. Welch PSD and magnitude-squared coherence equal scipy's to 1e-9.
- WAV (8/16/24/32-bit, float32/64, extensible, odd chunks) and PNG (all colour types and depths, Adam7, palette +
  tRNS, every filter) agree with scipy, Pillow and pypng as independent references.
- ECG beats within 2 ms of truth at either polarity, with heavy noise, and at 30 % beat amplitude; PPG pulses at a
  constant delay (SD < 3 ms).
- Synchronization: locked 4:1 and 9:2 records give index > 0.98 at the smallest possible p; unrelated rhythms
  p > 0.05; across 10 null records 1 rejection at α = 0.05. The respiration↔heart-rate coherence finds synthetic
  RSA (> 0.8 at the breathing rate) and rejects modulation at another rate.
- `compose` from the seed reproduces the v2 audio byte for byte (PCM sha 72a49e21d1037831); `compose --genome`
  reproduces any evolved elite byte for byte.

**L0 — real recordings** (`validate_real.py`, downloaded from PyPI and SHA-256 checked; used locally, GPL-3.0).

| check | pyphysio `medical` (120 s, 2048 Hz) | systole `Task1` (25.6 min, 1000 Hz) |
|---|---|---|
| beats | 139 R waves; 141 BVP pulses | 1938 R waves; 1 of 1937 intervals excluded |
| one heart, two sensors | 135 of 139 R waves followed by a pulse at 307 ± 10 ms; all 4 misses fall in a BVP artifact (63.5–70.5 s) or at the record's end | (no second cardiac sensor) |
| one breath, two sensors | breathing 0.1619 Hz vs HRV HF peak 0.1610 Hz; coherence at the breathing peak 0.18, p 0.25 (6 segments: too short to resolve) | coherence at the breathing rate 0.88, 0.92, 0.74 (p 0.005) in the three unclipped 5-min blocks; 0.20 and 0.15 (n.s.) in the two blocks where the belt clipped (648 and 160 samples) |
| phase synchronization | 11:2, index 0.085 vs 0.055 surrogate mean, p 0.17 | 4:1, index 0.023 vs 0.024, p 0.52; locked windows 4.3 % vs 5.0 % expected |

The measurements exposed two facts about the data: pyphysio's info file says 1024 Hz but its loader uses 2048 Hz,
and only 2048 Hz gives the stated 120 s and a heart rate of 69.6 bpm (34.8 at 1024); and the systole respiration
is dominated by drift below 0.1 Hz, which the band-power warning flags (20 % of variance in the automatic band).

**L1 — evolution.** 265 evaluations per seed, objective = texture recurrence (median over embedding dims 2–4).

| seed | baseline → champion (in search) | held-out re-measurement (32 and 64 points) | coverage | champion |
|---|---|---|---|---|
| K1LL x DIANNE | 0.079 → 0.283 | 0.105 → 0.296 (gain 0.191, 94 % of the in-search gain) | 36 % of 36 cells | G dorian, c = 0.2692 − 0.0076i |
| NeuroSymbiotic | 0.067 → 0.330 | 0.087 → 0.224 (gain 0.136, 52 %) | 31 % | F# lydian, c = 0.2718 + 0.0093i |

Both runs, from different starting fractals, converged on c ≈ 0.27 ± 0.01i: inside the main cardioid next to its
cusp at c = 1/4 (θ ≈ ±0.3 rad). Why that region gives the most recurrent texture is not established here. The
NSCTS champion sits at two bounds (density 0.16, zoom 1.6), so its search was limited by the box, not exhausted.

The held-out column is the number to trust. Picking the best of 265 noisy measurements overstates the winner: an
earlier run that optimised a single embedding dimension kept 31 % (K1LL) and 83 % (NSCTS) of its in-search gain
under re-measurement, this run 94 % and 52 %. Two runs do not show that the median objective shrinks the bias;
reporting the held-out gain is what protects against it.

**L2 — untested hypotheses.** Whether a 0.1–8 Hz amplitude pulse, or its antiphase stereo form, changes a listener's
breathing or heart rhythm. `coherence` and `rate_coupling` are the instruments for that experiment (record breath and
ECG while listening vs silence, compare locking and coherence against surrogates); it has not been run.

## 3.1: the dual cast, breath and heart locked, and the evolve engine used as an instrument test

**The source's "dual-wavelength schema casting" (L0, reproduced bit for bit against scipy.signal.chirp).** On its
`linspace(0, 1, 10000)` grid (9999 Hz) λ1 and λ2 are counter-chirps at 8.5 THz ∓ 432 kHz, and exactly
combined = cos(2π fc t)·cos(2π d (t² − t)) (verified to 3e-10 with rational phases). What the arrays contain:

| claim in the source | what the arrays hold |
|---|---|
| an 8.5 THz carrier | a 4991 Hz tone: 8.5e12 mod 9999 = 5008, folded to 4991, 8.5 Hz under Nyquist; the band edges land at 2965 and 2948 Hz |
| a 864 kHz sweep | each chirp folds across Nyquist 172.8 times; the sum is broadband (spectral flatness 0.31) |
| counter-chirp interference | 432 000 destructive nulls in 1 s, of which only ±5.8 ms (115 samples) around t = 0.5 s are resolvable |
| a 0.5 ns RC filter | exp(−t/0.5 ns) on a 100 µs grid is one 1 and 9999 zeros; with `mode='same'` the "transmitted schema" is 20 × the second half of the signal followed by 4999 zeros |
| float64 phases | at 5·10¹³ rad the phase ulp is ~0.008 rad: samples differ from exact by up to 0.011 |

THz radiation cannot be produced by audio hardware or represented at audio sample rates; "the highest terahertz
frequency being made" by that code is the 4991 Hz alias, and that is the carrier used below.

**Breath and heart running locked (L0 mathematics; L1 as physiology).** `cardioresp` integrates
dφh = (ωh + ε sin(n φr − m φh)) dt + σ dW against a breathing phase; ψ = n φr − m φh obeys Adler's equation, so the
lock region is analytic (|δ| < 1). Tested: inside, ψ settles at asin δ; outside, it slips at m ε √(δ² − 1)/2π; while
slipping, its mean resultant is |δ| − √(δ² − 1) (simulation within 0.005 of theory at δ = 1.2–3). The raw outputs
are what sensors record: a belt signal, an ECG, a PPG, with drift, wander, mains hum and noise.

**The counter-pair, cancelled by its own interference (L0).** L = gL cos(Φ − φh/2), R = gR cos(Φ + φh/2) on the
4991 Hz carrier: the channels sit at 4990.5 and 4991.5 Hz for a 60 bpm heart, the mono sum 2 cos Φ cos(φh/2)
cancels once per heartbeat, and the breath (the antiphase gain pulse) sets each null's depth to D·|cos φr|/(2 − D).
Measured on 300 s renders: 299 nulls when locked, timing within 0.36 ms and depth within 0.0013 dB of the closed form;
the null-depth sequence repeats every 4 beats when locked (stroboscopic index 0.992) and drifts when not (0.23).
The cancellation is a property of the summed signal: through speakers the beat persists everywhere, offset by
π·fc·τ for a path difference cτ; over headphones nothing sums, and no binaural beat is heard above ~1.5 kHz.

**The evolve engine repurposed (L0 method, results L1).** `qd_search` is the MAP-Elites engine, shared with the
music search (whose outputs are unchanged). `envelope` searches scenarios for wrong calls and keeps the worst per
cell; every failure is re-simulated with 3 fresh noise seeds. The first maps found two faults in this package's
own coherence test, both now fixed and tested:

1. A small p is phase *interaction*, not locking: drifting coupled pairs keep R = |δ| − √(δ² − 1) > 0. The verdict is
   now three-way — locked (p ≤ α and under one net slip), interacting but not locked, or no evidence.
2. Choosing the ratio from mean rates misses drifting pairs (4:1-coupled, running at 3.5). The whole-record test
   now scans every ratio within 35 % detuning, with the maximum taken on the surrogates too: 3 rejections in 40
   null records at α = 0.05.

The maps after the fixes (225 scenarios each, 6 × 6 cells; failures = wrong calls scored ≥ 0.5):

| target | compares | cells right in the worst case | failures | reproduced in ≥ 2 of 3 replays |
|---|---|---|---|---|
| statistics | true phases vs what they did | 34 of 35 | 1 | 1: heavy heart-phase noise (σh 0.43) with 0.7 true slips, at the edge of the definition |
| locking | raw signals vs what the phases did | 26 of 36 | 10 | 2: both locked pairs called slipping, at sensor noise 0.47 and 0.60 |
| measurement | raw signals vs true phases | 30 of 35 | 5 | 3: the same, at sensor noise 0.48–0.56 |

The reproduced raw-signal failures share one mechanism: false ECG beats (62 → 115 and 76 → 90 detected), each a
phantom 2π in the heart's phase; the breath's Hilbert phase stays exact (15.04 vs 15.03 cycles). No reproduced
raw-signal failure occurs below sensor noise 0.45 (uniform ±0.45 of the R amplitude). Two detector changes were tried and not
kept: template validation (115 → 109 detections; it also changed a validated real-data count, BVP 141 → 140) and a
matched-filter pass (115 → 147, and the 25-minute recording's count moved from 1938 to 1937). On the real recordings the scanned test still finds no phase interaction (p 0.59, 0.86),
while breathing↔heart-rate coherence is significant: in them the coupling is in rate, not in phase.

## Limits

- Nothing below 20 Hz is emitted; the pulse is modulation of audible tones. In stereo the pulse is antiphase, so a
  mono fold-down carries none (measured: its envelope variation is under a quarter of one channel's).
- Hurst (R/S) on 127 texture samples is rough; DFA is the better estimator for long series.
- Recurrence is computed on ≤ 80 embedding points (persistent homology costs n³).
- The beat detector is offline and has no reference-annotated validation here (neither package ships annotations);
  the cross-sensor agreement above is the evidence.
- The breath–heart model is the standard phase-oscillator abstraction; its failure maps describe this package's
  instruments on that model, not real physiology, and the envelope search covers 225 scenarios per map, not all.
- Terahertz signals are outside audio entirely; the 4991 Hz carrier is what the source's arrays actually held.
- No health, entrainment or consciousness claims are made or implied.
