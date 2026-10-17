"""Fractal Infrasonomancer · measured.

    seed text ─sha256─▶ Genome (θ, radius, zoom, density, mode, root) ─▶ Julia lattice, c in the main cardioid
              ─▶ score: columns = time, rows = degrees of the mode; the filled interior is silent, the edge sings
              ─▶ slow pulse: lattice column means set a 0.1–8 Hz rate, applied as amplitude modulation of audible
                 sound (stereo: antiphase between the ears). Nothing is emitted below 20 Hz
              ─▶ render.wav + score.mid + report.json (only numbers measured on what was produced)

Modules
    chaos       deterministic logistic-map variates (no PRNG)
    fractal     Julia lattices, cardioid parametrisation, box-counting dimension
    score       Genome, compose
    render      additive synthesis, mono or stereo pulse
    formats     WAV / MIDI / PNG / CSV / NPY readers and writers
    analysis    Hurst (R/S), DFA, persistent homology, delay embedding, Welch PSD and coherence, piece report
    physio      ECG / PPG beat detection, HRV
    coherence   phase streams, n:m synchronization and rate coupling with surrogate tests, synchrogram, PLL
    evolve      MAP-Elites: a generic engine (qd_search) and the music search over genomes
    dualcast    the source's dual-wavelength cast reproduced exactly; the counter-pair render and its nulls
    cardioresp  breath and heart as coupled phase oscillators (Arnold tongue ground truth), raw sensor signals
    envelope    the engine repurposed: MAP-Elites over scenarios for where the instruments fail
    cascade     recoherence cascade: coupled voices beat, lock, and by locking set off the next, higher generation

Command line: python -m infrasonomancer {compose,evolve,beats,coherence,pll,series,fractal,dualcast,
              cardioresp,cascade,envelope} --help
"""

from .analysis import (analyse, autocorrelation, delay_embed, describe_series, dfa, dominant_frequency,
                       embedding_delay, hurst_rs, msc, persistence, recurrence, welch)
from .chaos import PHI, Chaos
from .coherence import (PhaseStream, PLLResult, coherence_report, nearest_ratio, nm_phase_locking, pll_track,
                        rate_coupling, stream_from_events, stream_from_signal, synchrogram, synchronize)
from .cardioresp import Recording, Scenario, assess, simulate
from .cascade import (Cascade, CascadeConfig, cascade_report, cascade_timeline, fluctuation_weight, recohere,
                      render_cascade, sethares_dissonance)
from .dualcast import DualCast, alias_frequency, cast, cast_exact, counter_pair, mono_envelope, null_analysis
from .envelope import EnvelopeConfig, failure_map
from .evolve import EvolveConfig, map_elites, qd_search
from .formats import (image_mask, read_events, read_png, read_series, read_table, read_wav, write_csv, write_midi,
                      write_png, write_wav)
from .fractal import box_dimension, boundary, cardioid_c, cardioid_coordinates, edge_dimension, julia
from .physio import bandpass, detect_beats, hrv, rolling_max
from .render import dry, lfo_envelope, render
from .score import MODES, NOTE_NAMES, Genome, Note, Piece, compose, compose_genome

__all__ = ["alias_frequency", "analyse", "assess", "autocorrelation", "bandpass", "boundary", "box_dimension",
           "cardioid_c", "cardioid_coordinates", "Cascade", "CascadeConfig", "cascade_report", "cascade_timeline",
           "fluctuation_weight", "recohere", "render_cascade", "sethares_dissonance", "cast", "cast_exact", "Chaos", "coherence_report", "compose",
           "compose_genome", "counter_pair", "delay_embed", "describe_series", "detect_beats", "dfa",
           "dominant_frequency", "dry", "DualCast", "edge_dimension", "embedding_delay",
           "EnvelopeConfig", "EvolveConfig", "failure_map", "Genome", "hrv", "hurst_rs", "image_mask", "julia", "lfo_envelope",
           "map_elites", "MODES", "mono_envelope", "msc", "nearest_ratio", "nm_phase_locking", "Note",
           "NOTE_NAMES", "null_analysis", "persistence", "PhaseStream", "PHI", "Piece", "pll_track", "PLLResult",
           "qd_search", "rate_coupling", "read_events", "read_png", "read_series", "read_table", "read_wav",
           "Recording", "recurrence", "render", "rolling_max", "Scenario", "simulate", "stream_from_events",
           "stream_from_signal", "synchrogram", "synchronize", "welch", "write_csv", "write_midi", "write_png",
           "write_wav"]

__version__ = "3.2.0"
