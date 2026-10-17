# BPSN Build Specification — Phases 1–4 (v1.0)

Oct 17, 2026 · @Randy Lynn

v1.0 completes Phase 3 with 24 ranked enhancements, each carrying a figure of merit, a baseline, a test and a threshold that rejects it. It settles the compute platform, deployment order and security priorities, and adds Phase 4: architecture, verification matrix and gates G0–G4. Review of v0.9 adds eight baseline corrections (CORR-10–17).

Conventions as v0.9: \[A-n\] assumption, \[SPEC\] speculative with its falsification test, \[CORR\] correction. Status: BUILD = feasible with available component classes; VERIFY = needs a bench experiment; SPEC = speculative mechanism; HOLD = blocked pending safety, regulatory or architecture review.

## 0. Baseline corrections

Seventeen corrections constrain everything downstream. CORR-1–9 carry over from v0.9 unchanged; CORR-10–17 come from this review, and each changes a requirement in Phase 3 or 4.

| ID | Baseline claim | Correction | Consequence for spec |
| --- | --- | --- | --- |
| CORR-1 | FSO link is immune to eavesdropping | Diffuse reflection of a NIR beam off walls, ceilings or clothing is collectable with a telescope and APD. FSO is low probability of intercept, not immune. | Encryption mandatory on the optical plane; absorptive receiver baffle; margin-controlled TX power; eavesdrop resistance measured (T-10), not asserted. |
| CORR-2 | >10 GHz modulation makes the signal look like noise to RF scanners | Category error: optical carriers (\~350 THz) are invisible to RF scanners at any modulation rate. Modulation rate buys bandwidth, not covertness. | Removed from security claims. LPI comes from directionality, baffling and power control only. |
| CORR-3 | NAV/LUM LEDs can excite the BDX beat-frequency engine | Beat encoding needs coherence length ≫ beamlet–LO path difference; LEDs (10–40 nm linewidth) give \~10–50 µm. | Cytometry excitation is a single-frequency laser (e.g., 488 nm DPSS). QW-QD LEDs serve other roles (S-05, S-15). |
| CORR-4 | Wearable or bedside hub with flow cytometry | Fluidics, sheath flow, laser, AOD and PMT are bedside/cart only; diagnostic claims put cytometry on an IVD path (21 CFR 864 / IVDR). | Two SKUs: BPSN-H (hub, cytometry) and BPSN-W (wearable, no cytometry). Cytometry scoped research-use unless the program accepts the IVD timeline. |
| CORR-5 | 20 GHz LED bandwidth as a given | LUM claims >20 GHz; NAV publishes no device data; commercial micro-LEDs reach \~1–3 GHz. | Gate-0 risk: architecture closes at 1–2.5 Gb/s/λ on COTS and scales to 10–20 Gb/s/λ only if custom arrays validate (E-20). |
| CORR-6 | Visible light (VLC) as primary link | Blue light at NICU/ICU irradiances raises IEC 62471 photobiological and circadian concerns, plus flicker artefacts in pulse oximetry. | Primary FSO in NIR (850/940/1310 nm). 450 nm only as a low-rate, low-irradiance link-state beacon. |
| CORR-7 | Optical link immune to jamming | A bright LED or laser aimed at the receiver saturates the TIA. | Narrowband filters, AGC with saturation alarm, angle-of-arrival detection (S-19), fail-closed on optical jam (E-08). |
| CORR-8 | AOD re-aims beamlets away from a detected human | AOD deflection is tens of mrad inside a sealed flow-cell path, irrelevant to human exposure. | Safety = RF-comb kill (zeroth-order dump) + mechanical shutter + enclosure interlock (E-01). |
| CORR-9 | RF reduced by 90 % (10 dB) | 10 dB is weak against exposure margins and against what the architecture can do. | Target ≥ 20 dB reduction, or full RF mute when FSO is up (E-10). |
| CORR-10 | Optical plane emits no RF (implied by CORR-2) | The drivers do: LED/laser drive currents switching at Gb/s rates radiate at the symbol rate and harmonics, and that emanation is data-correlated. | Shielded driver layout; data-correlation emanation scan in T-11; constant-power line coding (E-17) lowers the correlation. |
| CORR-11 | S-14: InGaN chirp \~ −0.03 to −0.1 nm/K | Thermal shift is a red shift, roughly +0.03 to +0.06 nm/K for blue InGaN (current-induced blue shift competes). The primary NIR plane matters more: GaAs-based 850 nm emitters drift ≈ +0.26 nm/K (bandgap ≈ −0.45 meV/K). | WDM guard bands on the NIR plane are sized for ≈ 8 nm drift over a 30 K swing, or the emitters are temperature-controlled. |
| CORR-12 | S-01: shared 10 MHz GPSDO timebase | GPS reception inside hospitals is unreliable. | Shared timebase = local OCXO; multi-hub time via IEEE 1588 PTP; GPSDO optional. |
| CORR-13 | S-10: full duplex cuts the PQC handshake to \~1 RTT | TLS 1.3 is already 1-RTT, and a 3 m link has a 20 ns round trip; handshake time is set by ML-KEM/ML-DSA compute (milliseconds on embedded cores). | S-10 keeps its channel-binding value only; no latency claim (E-05). |
| CORR-14 | O-03: badge answers each challenge with an ML-DSA signature | An ML-DSA-44 signature is 2,420 bytes (ML-DSA-65: 3,309 bytes): about 2 s per answer at a 10 kb/s retro-modulator, plus milliseconds of signing energy. | Per-authentication answers use symmetric challenge–response; ML-DSA only at enrolment and key rotation (E-18). |
| CORR-15 | O-02: harvest-now-decrypt-later on RF becomes moot | Pre-positioning removes the RF key exchange, but the exposure moves to the FSO handshake, which CORR-1 says is interceptable; the reservoir itself becomes an at-rest target. | FSO handshake is PQC-hybrid (E-05); reservoir in the secure element, single-use keys, erase after use, bounded size (E-06). |
| CORR-16 | S-15: falsify SpO₂ at < 2 % error on 20 subjects | Twenty subjects screens feasibility only. Oximeter accuracy evidence (ISO 80601-2-61 ARMS) needs larger, skin-pigmentation-diverse cohorts, as current FDA guidance asks. | E-23 keeps the 20-subject screen as its rejection test and claims nothing clinical from it. |
| CORR-17 | S-05: falsify FD lifetime at < 0.5° phase resolution at 200 MHz on fluorescein | Fluorescein's lifetime is ≈ 4 ns, so phase sensitivity peaks near f = 1/(2πτ) ≈ 40 MHz. At 200 MHz the phase sits near 79° and moves only ≈ 2.7° per ns. | E-22 tests at 40 MHz and 200 MHz; GHz excitation earns its place only on sub-ns lifetimes. |

## 1. Phase 1 — Advantage extraction

Phase 1 is carried from v0.9 unchanged except for the last column of 1.3, which names the Phase 3 enhancement (E-n) that carries each synergy and any correction that now applies to it.

### 1.1 Per-patent capability inventory (claimed → implicit/unclaimed)

**MXL — presence-aware wireless.** Claimed: presence sensing via PIR, camera, mic array, RSSI, temperature, motion, activity or a received message; control of TX power, directivity, band, airtime, fragmentation, retry count and link technology; handover or offload to AP, VLC, PLC or Ethernet; traffic classes (non-deferrable, short-term and long-term deferrable); deferral while a human is present.

- Implicit: the traffic classifier is a generic policy engine, usable against jamming as well as presence.
- Implicit: multi-sensor fusion yields a confidence score usable as an authentication factor ("who" as well as "whether").
- Implicit: fragmentation and airtime control bound peak RF duty cycle, which matters for implant EMC (IEC 60601-1-2, ISO 14117).
- Implicit: "received message" as a presence input enables cooperative presence (a badge announces itself).
- Implicit: handover to VLC means the modem is already a cross-medium scheduler.

**LUM — UWB FSO.** Claimed: < 500 ps LED arrays; Wilkinson in-phase dividers and traveling-wave drive; MQW detectors with TIA and Wilkinson combiners; > 20 GHz; WDM; dual-wavelength full duplex; integrated 3-terminal LED + detector stack; wavelength modulation as signalling.

- Implicit: sub-ns edges enable optical time-of-flight ranging (\~3–7 cm single-shot, mm with averaging).
- Implicit: combiner-fed detector arrays can be segmented for angle of arrival.
- Implicit: the 3-terminal stack is a native optocoupler/isolator.
- Implicit: wavelength modulation is a low-rate side channel orthogonal to intensity data.
- Implicit: Wilkinson networks impose a bandpass that doubles as RF-side EMI filtering.
- Implicit: WDM channels are physically separable, so each can be its own key domain.

**NAV — QW-QD with Auger suppression.** Claimed: QD in a higher-gap, higher-effective-mass QW/wire barrier; suppressed Auger recombination; higher IQE at high carrier density; improved transient response; arrays and superlattices; multi-wavelength (RGB) via QD composition and size; improved extraction.

- Implicit: droop suppression at high current density is the regime fast modulation needs, so devices run cooler with less thermal chirp.
- Implicit: narrower QD emission linewidth than bulk QW improves WDM channel isolation.
- Implicit: monolithic multi-λ superlattice plus MQW absorbers is an on-chip multispectral spectrometer.
- Implicit \[SPEC\]: reduced Auger means less hot-carrier noise and lower relative intensity noise.
- Implicit: per-element addressable arrays give programmable spatial emission patterns.

**BDX — RF-comb AOD cytometry.** Claimed: AOD driven by an RF comb produces N beamlets at RF-shifted optical frequencies; fluorescence beat frequencies encode position; image-free sorting in < 100 µs; time-frequency waveform analysis; co-localization, size, aspect ratio, N/C ratio and kurtosis from beat data.

- Implicit: the detector output is an RF signal in the 10–100 MHz band, so any SDR chain can demodulate it.
- Implicit: the RF comb is a programmable spatial channel map; removing a tone removes a beamlet (optical firewall).
- Implicit: the < 100 µs FPGA decision kernel is a reusable hard-real-time classifier.
- Implicit: time-frequency feature extraction is a generic signal-anomaly engine.
- Implicit: tone frequencies can be randomized per session (anti-crosstalk, anti-injection).
- Implicit: beat-frequency fluorescence can measure immune-cell populations relevant to vaccine immunogenicity.

**MRN — mRNA/LNP context anchor.** Claimed as data primitive: sequence, chemical modification map, LNP composition, lot, immunogenicity readouts, cold-chain temperature history.

- Implicit: cold-chain logs are physically rooted, monotonic, time-stamped records, so they can serve as a freshness or nonce source.
- Implicit: lot identity binds to cytometry readouts, giving a provenance chain from formulation to immune response.
- Implicit: genomic and sequence payloads are large, bursty and long-term deferrable, while excursion alarms are non-deferrable — a direct fit for the MXL classes.

### 1.2 Cross-patent synergy matrix

Cells list synergy IDs (defined in 1.3); the diagonal is intra-patent extension.

|  | MXL | LUM | NAV | BDX | MRN |
| --- | --- | --- | --- | --- | --- |
| MXL | S-28 (fragmentation → implant EMC) | S-04 (optical ToF presence), S-16 (room map → FSO pointing), S-17 (link blockage = presence), S-22 (visible consent beacon) | S-22, S-06b (cool arrays → safe-touch wearables) | S-03 (presence → cytometry interlock), S-21 (BDX kernel as interlock FSM) | S-07 (traffic classes ↔ cold chain), S-08 (deferral vs jamming) |
| LUM | — | S-10 (full-duplex PQC), S-19 (AoA via segmented combiners), S-23 (optical key fill) | S-14 (Auger suppression → chirp-stable WDM), S-15 (on-chip spectroscopy) | S-01/S-02 (shared RF chain via SDR), S-06 (3-terminal isolator in sort loop), S-05 (FD-lifetime excitation) | S-09 (λ-modulation integrity beacon for MRN payloads) |
| NAV | — | — | S-15 (superlattice spectrometer) | S-05 (GHz LED FD-FLIM), S-26 (QD cartridge tags) | S-15b (LNP turbidity / particle sizing via multispectral scatter) \[SPEC\] |
| BDX | — | — | — | S-11 (comb as firewall), S-18 (time-frequency anomaly engine → RF sentinel) \[SPEC\] | S-13 (immunogenicity bound to lot), S-24 (excursion → sample validity gating) |
| MRN | — | — | — | — | S-12 (cold chain as freshness anchor) |

### 1.3 Ranked synergy list (novelty × value; 1 = highest)

| Rank | ID | Synergy | Patents | Novelty / value | v0.9 status | Carried by (v1.0) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | S-01 | SDR/RFSoC DAC generates the AOD RF comb; one synthesizer and timebase drive the AOD and the SDR sentinel; comb tones are software-defined per session. | BDX + SDR | High / High — no separate AWG; makes tone randomization (S-11) free | Buildable | E-03; CORR-12 (OCXO, not GPSDO) |
| 2 | S-02 | SDR ADC/DSP demodulates cytometry beat frequencies: PMT/SiPM output (10–60 MHz beats) digitized by an RFSoC ADC; the sentinel's polyphase channelizer performs the beat decomposition. | BDX + SDR | High / High — one digital front end serves sentinel and cytometer | Buildable | E-03 |
| 3 | S-04 | Zero-RF presence detection by optical ToF with the FSO head's own < 500 ps LED and MQW detector. | LUM + NAV + MXL | High / High | Buildable; \[A-1\] ToF SNR at 3 m, 10 ns pulses, 100 averages | E-10, E-18 |
| 4 | S-23 | Optical key fill: FSO delivers a high-rate reservoir of PQC-wrapped session keys; RF fallback consumes it and never carries a key exchange. | LUM + crypto | High / High | Buildable | E-06; CORR-15 |
| 5 | S-12 | Cold-chain record as Therapy Manifest freshness anchor: anchor = H(latest signed temperature record); manifest valid only if anchor age < Δt and excursion flag = 0. | MRN + crypto | High / High | Buildable | E-12 |
| 6 | S-07 | MXL traffic classes mapped to the biomedical data plane: alarms and implant telemetry non-deferrable; cytometry results short-term; genomic bulk long-term, released only with FSO up and no human in the RF path. | MXL + MRN | Med / High | Buildable | E-09 |
| 7 | S-08 | Deferral engine as jamming-DoS defense: non-deferrable promoted to FSO, deferrable queued with bounded TTL and cryptographic receipts, RF retries capped. | MXL + SDR | Med / High | Buildable | E-09 |
| 8 | S-13 | Immunogenicity provenance: beat-frequency assay of RBD-tetramer⁺ B cells / activated T cells, result hash-bound to vaccine lot, LNP formulation and cold-chain hash. | BDX + MRN | High / High (clinical) | Buildable; IVD path | E-15 |
| 9 | S-15 | On-chip multispectral spectroscopy (SpO₂, bilirubin, tissue hemoglobin) from the comm head. | NAV + LUM + MXL | High / Med | \[SPEC\] < 2 % SpO₂ error vs reference, 20 subjects | E-23; CORR-16 |
| 10 | S-03 | Presence → cytometry safety interlock: enclosure open, or presence within 0.5 m of the optical port → comb mute, shutter, sort results quarantined as "interrupted". | MXL + BDX | Low / High (safety) | Buildable | E-01 (presence is an extra trip input, never the safety function) |
| 11 | S-05 | GHz LED as frequency-domain lifetime excitation (100 MHz–2 GHz) beside the laser beat channel. | NAV + LUM + BDX | High / Med | \[SPEC\] < 0.5° phase resolution at 200 MHz on fluorescein | E-22; CORR-17 |
| 12 | S-11 | AOD RF comb as tunable optical firewall: per-session randomized tones; injected light cannot match the session tone map and is rejected. | BDX + SDR + security | Med / Med | Buildable | E-13 |
| 13 | S-19 | Angle of arrival via segmented Wilkinson-combined detector quadrants: rejects off-axis injection, localizes a jammer. | LUM + security | Med / Med | Buildable | E-08 |
| 14 | S-14 | Auger-suppressed arrays → thermally stable WDM and lower thermal side-channel leakage. | NAV + LUM | Med / Med | \[SPEC\] ≥ 3× lower chirp vs reference QW LED | E-20; CORR-11 |
| 15 | S-17 | FSO link blockage as a presence sensor: power drop with intact alignment = object in beam. | LUM + MXL | Med / Med | Buildable | E-10 |
| 16 | S-10 | Full-duplex dual-λ FSO for the PQC handshake, with a channel-binding token from the λ pair and comb map. | LUM + crypto | Med / Med | Buildable | E-05; CORR-13 |
| 17 | S-09 | Wavelength modulation as an out-of-band integrity beacon carrying a MAC over the ledger head. | LUM + crypto | Med / Med | \[SPEC\] λ-dither BER < 1e-3 at 1 kb/s | E-21 |
| 18 | S-26 | QD fluorescent tags on cytometry cartridges read by the same detector: anti-counterfeit and lot binding. | NAV + BDX | Med / Med | Buildable | E-15 |
| 19 | S-21 | BDX < 100 µs decision kernel reused as the implant-command safety FSM. | BDX + crypto | Low / Med | Buildable | E-19 (HOLD) |
| 20 | S-22 | Visible blue beacon as a patient-perceivable consent / transmission indicator. | NAV + MXL | Low / Med | Buildable | Backlog |
| 21 | S-16 | MXL room occupancy map → FSO pointing policy avoiding occlusion and eye proximity. | MXL + LUM | Low / Med | Buildable | Backlog |
| 22 | S-06 | LUM 3-terminal LED + detector as galvanic isolator and trigger line in the sort loop. | LUM + BDX | Med / Low | Buildable | Backlog |
| 23 | S-20 | Presence camera as FSO alignment aid and optical-path tamper detector. | MXL + LUM | Low / Med | Buildable | Backlog |
| 24 | S-28 | MXL fragmentation/airtime control → bounded RF duty cycle near implants (ISO 14117 margin). | MXL | Low / Med | Buildable | E-14 |
| 25 | S-24 | Cold-chain excursion gates sample validity. | MRN + BDX | Low / Med | Buildable | E-15 |
| 26 | S-18 | BDX time-frequency features applied to SDR spectrograms for jammer classification. | BDX + SDR | Med / Low | \[SPEC\] ≥ 95 % classification vs baseline CNN | Backlog (advisory only, never a safety input) |
| 27 | S-15b | Multispectral scatter for LNP particle size / turbidity QC at bedside. | NAV + MRN | High / Low | \[SPEC\] R² > 0.8 vs DLS on 30 lots | Backlog |
| 28 | S-25 | Physical-layer key generation from FSO channel randomness. | LUM + crypto | — | \[SPEC, likely fails\] Eve–Bob MI < 0.01 bit/sample at 20 cm | Not relied upon; measured by T-26 |

## 2. Phase 2 — Overlooked advantages

Phase 2 is carried from v0.9; the last column names the enhancement that carries each item and the correction that now limits it.

| Rank | ID | Overlooked capability | Patents | Baseline gap | Value | v0.9 status / falsification | Carried by (v1.0) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | O-01 | RF-silent diagnostic mode: cytometry + FSO + optical ToF presence run a full assay and upload with zero intentional RF emission; only unintentional emissions (clock harmonics, AOD comb leakage at 80–120 MHz) remain, a CISPR 11 / IEC 60601-1-2 problem rather than a SAR problem. | BDX + LUM + MXL | Baseline treats RF as an always-on sentinel; the sentinel can be receive-only (no LO leakage > −80 dBm with proper isolation). | High | Buildable; \[A-2\] AOD drive shielding achieves < 30 dBµV/m at 3 m | E-11; CORR-10 adds driver emanation |
| 2 | O-02 | Optical key fill for RF fallback: FSO pre-positions large volumes of PQC-wrapped key material; RF fallback never performs a key exchange over the air. | LUM + crypto | Baseline negotiates keys on whichever link is active. | High | Buildable | E-06; CORR-15 narrows the HNDL claim |
| 3 | O-03 | Covert clinician optical challenge–response: badge retro-modulator (MEMS corner cube or micro-LED) answers an FSO-head challenge; LOS-bound, invisible to RF sniffers, and an identity-bearing MXL "received message" presence input. | LUM + MXL + crypto | Baseline uses RFID/NFC or a password. | High | Buildable; \[A-3\] retro-modulator ≪ 1 mW average | E-18; CORR-14 replaces per-answer ML-DSA |
| 4 | O-04 | Cold-chain logger's signed, counter-indexed records as an external monotonic clock: anti-replay for manifests even if hub time is attacked. | MRN + crypto | Baseline uses the device RTC only. | High | Buildable | E-12; \[A-4\] loggers sign records |
| 5 | O-05 | AOD as tunable optical firewall: tone map changes per sample, patient or cartridge; a sorter-injection attack must know the current map; unknown tones quarantine the run. | BDX + SDR + security | Baseline treats cytometry as a sensor, not an attack surface. | Med–High | Buildable | E-13 |
| 6 | O-06 | Deferral engine as DoS defense: bounded-TTL queue and receipts turn "jammed" from a safety event into an availability event with proof of deferral; clinicians get a reason code. | MXL | Baseline ignores the RF band with no accounting. | Med–High | Buildable | E-09 |
| 7 | O-07 | Wavelength modulation as integrity: binds the physical emitter (λ-dither signature + QD spectral fingerprint) to the session, a form of optical hardware attestation. | LUM + NAV + crypto | Not in baseline. | Med | \[SPEC\] per S-09, plus fingerprint uniqueness over ≥ 100 dies | E-21 |
| 8 | O-08 | Photonic side-channel resistance: data-dependent thermal chirp and droop are an optical side channel for an LOS observer with a spectrometer; Auger suppression and constant-aggregate-power coding reduce the coupling. | NAV + LUM | Not considered. | Med | \[SPEC\] TVLA: no leakage > 4.5σ at 1e6 traces | E-17 (coding, COTS); E-20 (Auger part) |
| 9 | O-09 | Superlattice QW-QD arrays as on-chip spectroscopic sensor: the wearable comm head becomes an SpO₂ / bilirubin / methemoglobin sensor with no extra optics. | NAV + LUM | Not considered. | High (product) | \[SPEC\] per S-15 | E-23; CORR-16 |
| 10 | O-10 | Optical ToF presence as a vital-sign radar substitute: sub-ns pulses at 100 Hz frame rate give chest-wall displacement (respiration) at zero RF. | LUM + NAV + MXL | Baseline relies on PIR/camera. | Med | \[SPEC\] respiration rate ±2 bpm vs capnography, n = 20 | E-24 |
| 11 | O-11 | WDM channels as cryptographic domains: each λ carries its own key hierarchy and traffic class; compromise of one λ chain exposes no other; simplifies HIPAA minimum-necessary segmentation. | LUM + crypto | Baseline uses WDM for throughput only. | Med | Buildable | E-16 |
| 12 | O-12 | Hard-real-time decision kernel reuse: sort-kernel discipline (deterministic, formally bounded latency) on the implant actuation path. | BDX | Not considered. | Med | Buildable | E-19 (HOLD) |
| 13 | O-13 | Implant EMC coexistence: a declared implant becomes a presence class that caps RF duty cycle and bans bands near implant telemetry (MICS/MedRadio 401–406 MHz). | MXL | Baseline treats presence as a binary human. | Med | Buildable | E-14 (band list from the implant's manifest, see 3.3) |
| 14 | O-14 | Consumable and reagent authenticity: QD tags + lot binding + cold chain make counterfeit reagents detectable. | NAV + BDX + MRN | Not considered. | Med | Buildable | E-15 |
| 15 | O-15 | Regulatory evidence by construction: every policy decision is a ledger event with inputs, rule version and outcome, so IEC 81001-5-1 / ISO 14971 traceability is generated at runtime. | All | Baseline ledger covers data, not control decisions. | High (program) | Buildable | E-04 |

## 3. Phase 3 — Enhancements (ranked)

Nine BUILD items lead the ranking because they close the hub on COTS parts and generate the evidence every later test reuses; the four SPEC items come last and wait on custom arrays (E-20). Rank weighs integrated system value, early risk reduction and evidence reuse, not novelty. ID order is rank order.

### 3.0 Design rules

1. Build on verified components first: commercial optical devices, an SDR/RFSoC, established cryptographic libraries and deterministic software, before any custom semiconductor fabrication.
2. Separate safety from optimization: laser shutdown, enclosure interlocks, implant command authorization and clinical-result validity never depend on ML confidence or best-effort networking.
3. Make every enhancement falsifiable: each row has a figure of merit, a baseline, a test and a threshold that rejects it.
4. Keep the SKUs distinct: BPSN-H owns cytometry and the diagnostic research workflow; BPSN-W owns wearable communications and any separately validated sensing.
5. Treat security as defense in depth: directionality, randomized AOD tones, wavelength side channels and key pre-positioning complement authenticated encryption, key management and a threat model; they never replace them.

### 3.1 Ranked enhancements

Test IDs point to the verification matrix (4.2); "reject if" is the falsification threshold.

| ID | Enhancement | Draws from | Mitigates / unlocks | Figure of merit (target) | Baseline | Test | Reject if | Status | SKU |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| E-01 | Hardwired optical interlock chain: enclosure and port switches drive a dual-channel safety relay that removes laser enable, AOD RF-amplifier power and shutter hold; software can trip it, never re-arm it | CORR-8, S-03, S-21 | Laser exposure in service or under fault; makes laser safety independent of RFSoC, ML and network | Port emission below the IEC 60825-1 Class 1 AEL within 10 ms of any trip; no single fault leaves emission on | v0.9 S-03 software FSM | T-01 | Any trip slower than 10 ms, or any injected single fault that leaves emission on | BUILD | H |
| E-02 | COTS NIR FSO link: 850 or 940 nm emitter with diffuser, Si PIN/APD + TIA, ceiling receiver; IEEE 802.11bb (800–1000 nm) PHY where interop is needed | CORR-5, CORR-6, LUM | Gate-0 risk: the system closes on parts that exist today | ≥ 1 Gb/s goodput at 3 m within ±15° of boresight; post-FEC BER ≤ 1e-12; Class 1 at every accessible position | Wi-Fi 6 at the same positions | T-02, T-03 | < 1 Gb/s at 3 m inside the ±15° cone, or Class 1 not met | BUILD | H, W |
| E-03 | Shared RFSoC timebase: DAC synthesizes the 80–120 MHz AOD comb; ADC + polyphase channelizer decompose PMT/SiPM beats; one OCXO serves comb, demodulator and sentinel | S-01, S-02, CORR-12 | Removes the separate AWG and digitizer; makes tone randomization (E-13) free | Comb spurs ≤ −60 dBc in the AOD band; channel crosstalk ≤ −40 dB; bead CV within 5 % (relative) of the reference chain | Discrete AWG + digitizer on the same flow cell | T-04 | Spurs > −50 dBc, crosstalk > −30 dB, or bead CV worse by > 10 % relative | BUILD | H |
| E-04 | Control-decision ledger: append-only, hash-chained, signed record of every policy and safety decision (inputs, rule version, outcome), written asynchronously off the safety path | O-15 | ISO 14971 / IEC 81001-5-1 traceability generated at runtime; incident reconstruction | 100 % of safety-relevant decisions logged with rule version; append p99 ≤ 1 ms; truncation, reorder and edit detected 100 % | v0.9 data-only ledger | T-05 | Any decision missing, any tamper undetected, or any safety action delayed by the ledger | BUILD | H, W |
| E-05 | PQC-hybrid FSO session: TLS 1.3 with X25519MLKEM768 and ML-DSA-65 certificates; exporter-derived binding token over λ pair, comb-map ID and link counters | S-10, CORR-1, CORR-13 | Harvest-now-decrypt-later on the interceptable optical plane; binds the session to the physical link | All FIPS 203/204 KATs pass; interop with two independent stacks; full handshake ≤ 20 ms on the hub, ≤ 250 ms on the wearable | Classical ECDHE + ECDSA | T-06 | Any KAT or interop failure; handshake > 50 ms (hub) or > 1 s (wearable) | BUILD | H, W |
| E-06 | Optical key pre-positioning: the FSO session delivers a reservoir of 256-bit keys wrapped under a secure-element key; each RF session derives traffic keys by HKDF from one reservoir key, which is then erased | S-23, O-02, CORR-15 | Removes every public-key exchange from RF; RF stays usable when FSO drops | Zero key exchanges on RF in protocol traces; reservoir covers ≥ 7 days of fallback; erased keys unrecoverable | Key exchange on whichever link is active | T-07 | Any RF key exchange, a reservoir under 72 h of fallback, or any erased key recovered | BUILD | H, W |
| E-07 | Eavesdrop-resistance controls: absorptive receiver baffle, TX power held ≤ 6 dB above the link threshold, encryption mandatory; interception measured, not asserted | CORR-1, CORR-2 | Diffuse-reflection interception; turns LPI into a number | Intercept BER ≥ 1e-2 for a 50 mm telescope + APD at every surveyed point outside the 0.5 m beam keep-out | Unbaffled emitter at full power | T-10 | Intercept BER < 1e-3 at any surveyed point outside the keep-out | BUILD | H, W |
| E-08 | Optical jamming defense: narrowband interference filter, AGC with saturation alarm, quadrant angle-of-arrival detector, fail-closed to RF fallback on reservoir keys | CORR-7, S-19 | Receiver saturation, off-axis injection and spoofing | Saturation alarm ≤ 10 ms; AoA error ≤ 5°; injection outside the FoV rejected ≥ 40 dB; failover ≤ 100 ms | Unfiltered receiver without AoA | T-08 | Any unalarmed saturation, AoA error > 10°, or failover > 1 s | BUILD | H, W |
| E-09 | Traffic classes and bounded-TTL deferral: MXL classes on the biomedical plane; non-deferrable traffic promoted to FSO under RF jamming; deferrable traffic queued with bounded TTL and signed receipts; RF retries capped | S-07, S-08, O-06 | Jamming DoS becomes an accounted availability event with a reason code | Non-deferrable p99 delivery ≤ 1 s whenever either link is up; TTL honoured 100 %; every deferral carries a verifiable receipt | Best-effort queue | T-09 | Any non-deferrable message lost, or delayed > 1 s with a link up; any deferral without a receipt | BUILD | H, W |
| E-10 | Zero-RF presence fusion: optical ToF, link blockage and PIR fused in the MXL policy engine; RF reduced ≥ 20 dB or muted while FSO is up and a person is in the RF path | S-04, S-17, CORR-9 | Unneeded RF exposure; ends the RF-emitting presence sensor | ≥ 20 dB conducted and radiated reduction within 100 ms; presence miss ≤ 1 % at 0.5–3 m | PIR only, 10 dB | T-12 | Reduction < 20 dB, response > 500 ms, or miss rate > 1 % | VERIFY \[A-1\] | H, W |
| E-11 | RF-silent diagnostic mode: assay plus FSO upload with the sentinel receive-only, AOD drive shielded and no intentional emitter powered | O-01, CORR-10 | Removes intentional RF from the diagnostic workflow | Zero intentional emission; radiated emissions ≥ 6 dB under the applicable CISPR 11 Group 1 limit; AOD comb leakage < 30 dBµV/m at 3 m; no data-correlated emanation | Same assay with RF uplink | T-11 | Any intentional emission, margin < 3 dB, or data-correlated emanation detected | VERIFY \[A-2\] | H |
| E-12 | Therapy manifest with cold-chain freshness anchor: manifest signed with ML-DSA-65; anchor = H(latest signed logger record); valid only if anchor age < Δt and excursion flag = 0; the logger counter is the monotonic clock | S-12, O-04 | Replay of stale manifests; hub-clock rollback | 100 % of stale, replayed or rolled-back manifests rejected; 0 valid manifests rejected | RTC-only validity | T-13 | Any stale or replayed manifest accepted | BUILD \[A-4\] | H |
| E-13 | Session-randomized AOD tone map: per-run tone set drawn from the DRBG inside the AOD band; energy at non-session tones rejected; foreign modulated light quarantines the run | S-11, O-05 | Sort or analysis injection by modulated light; crosstalk | Injection at a non-session tone detected ≥ 99.9 %; false quarantine ≤ 0.1 % of clean runs; bead CV within 5 % (relative) of a fixed map; recalibration ≤ 30 s per map | Fixed tone map | T-14 | Detection < 99 %, false quarantine > 1 %, or bead CV worse by > 10 % relative | BUILD | H |
| E-14 | Implant EMC coexistence: a declared implant caps RF duty cycle and excludes its telemetry bands (MedRadio 401–406 MHz and any band its manifest lists) | S-28, O-13 | Interference with implant telemetry; ISO 14117 margin | Band exclusion enforced 100 %; duty-cycle cap enforced within one scheduling interval; field at the implant site below ISO 14117 test levels | Uncapped scheduler | T-15 | Any transmission in an excluded band, or any cap breach | BUILD | H, W |
| E-15 | Result provenance and reagent authenticity: each cytometry result hash-bound to vaccine lot, LNP formulation and cold-chain hash; excursion-exposed reagents flag their results; QD cartridge tags read by the same detector | S-13, S-24, S-26, O-14 | Unbound results; counterfeit reagents | 100 % of results bound; 100 % of excursion-exposed runs flagged; counterfeit cartridge detection ≥ 99 % | Results without provenance | T-16 | Any unbound result, any unflagged excursion run, or detection < 95 % | BUILD clinical claims on HOLD (CORR-4) | H |
| E-16 | WDM channels as key domains: each λ gets its own key hierarchy (domain-separated KDF labels) and traffic class (λ1 control, λ2 bulk) | O-11 | One λ chain's compromise exposing another; HIPAA minimum necessary | No key, nonce or KDF label shared across λ domains; one domain's keys decrypt 0 bytes of another | Shared session keys across λ | T-17 | Any cross-domain key reuse | BUILD needs 2 λ with CORR-11 guard bands | H |
| E-17 | Constant-aggregate-power line coding: balanced code plus a dummy λ or complementary drive, so emitted power and driver current are data-independent | O-08, CORR-10 | Optical and RF side channels from data-dependent power, chirp and emanation | TVLA: no leakage > 4.5σ at 1e6 traces on the emission spectrogram or driver near field | Unbalanced coding | T-18 | Leakage > 4.5σ within 1e6 traces | VERIFY | H, W |
| E-18 | Badge optical challenge–response: AES-CMAC under a per-badge key over a retro-modulator, ToF distance-bounded; ML-DSA only for enrolment and key rotation | O-03, S-04, CORR-14 | Badge cloning and relay; gives MXL an identity-bearing presence input | Authentication ≤ 500 ms at 1.5 m LOS; badge average power ≤ 1 mW; a relay adding > 1 m of path detected | RFID/NFC badge | T-19 | Latency > 1 s, power > 2 mW, or a relay adding 2 m accepted | VERIFY \[A-3\] | H |
| E-19 | Implant command FSM: verify signature → bounds check → actuate on a deterministic core with measured WCET; fail-closed; no ML or best-effort network on the path | S-21, O-12 | Unauthorized or out-of-bounds implant commands | 0 unauthorized actuations in the fault-injection campaign; end-to-end WCET ≤ 10 ms with 2× margin | No dedicated path | T-20 | Any unauthorized actuation, or WCET above bound | HOLD needs implant partner + regulatory review \[A-5\] | H |
| E-20 | Custom LUM/NAV arrays at 10–20 Gb/s/λ, including the Auger-suppression chirp claim (S-14) | CORR-5, S-14 | Throughput ceiling of COTS emitters | −3 dB modulation bandwidth ≥ 7 GHz; ≥ 10 Gb/s/λ at 3 m with post-FEC BER ≤ 1e-12; chirp ≥ 3× lower than a reference QW LED | COTS emitter of E-02 | T-21 | Bandwidth < 5 GHz, < 5 Gb/s/λ, or chirp improvement < 2× | VERIFY G0 decides funding | H, W |
| E-21 | λ-dither integrity beacon and emitter fingerprint: slow λ dither carries a MAC over the ledger head; intensity and λ planes must agree; QD spectral fingerprint attests the emitter | S-09, O-07 | A second physical plane an attacker must also control | λ-dither BER < 1e-3 at 1 kb/s with dual-filter balanced detection; fingerprint FAR ≤ 1e-4 at FRR ≤ 1e-2 over ≥ 100 dies | No out-of-band integrity | T-22 | BER ≥ 1e-3, or FAR > 1e-3 | SPEC | H |
| E-22 | GHz-LED frequency-domain lifetime channel: QW-QD LED modulated 40 MHz–2 GHz adds phase-fluorometry lifetime beside the laser beat channel | S-05, CORR-17 | Lifetime as a label-free dimension | Lifetime resolution ≤ 0.1 ns on fluorescein (≈ 4 ns) at 40 MHz (0.5° phase); phase resolution < 0.5° at 200 MHz | Laser beat channel alone | T-23 | Lifetime resolution > 0.3 ns at 40 MHz | SPEC | H |
| E-23 | Comm-head multispectral SpO₂: superlattice multi-λ emitters and MQW detectors in the wearable head (bilirubin and tissue Hb later) | S-15, O-09, CORR-16 | Sensing with no extra optics | Feasibility screen: < 2 % SpO₂ error vs reference, 20 subjects; no clinical claim | Reference oximeter | T-24 | Error ≥ 2 % on the screen | SPEC needs E-20 arrays | W |
| E-24 | Optical ToF respiration: sub-ns pulses at 100 Hz frame rate measure chest-wall displacement at zero RF | O-10 | Respiration monitoring without RF radar | Respiration rate within ±2 bpm of capnography, n = 20 (feasibility) | Capnography | T-25 | Disagreement > 2 bpm on > 5 % of 1-minute epochs | SPEC | H, W |

Backlog, unranked and scheduled after G3: S-06, S-16, S-20 and S-22 (BUILD, low value); S-18 and S-15b (SPEC, low value; S-18 advisory only, never a safety input). S-25 is not relied upon; T-26 measures it once.

### 3.2 Decision: primary compute platform

BPSN-H runs on one AMD Zynq UltraScale+ RFSoC Gen 3 (ZU47DR class: 8 × 14-bit 5 GS/s ADC, 8 × 14-bit 9.85 GS/s DAC, quad Cortex-A53, dual Cortex-R5F) beside a separate lockstep safety MCU and a hardwired interlock. BPSN-W runs on an Armv8-M TrustZone microcontroller with a secure element and no RFSoC.

| Function | Hosted on | Why there |
| --- | --- | --- |
| AOD comb synthesis, 80–120 MHz, per-run tone maps | RFSoC DAC, first Nyquist zone, NCO bank in programmable logic | S-01, E-03, E-13: one synthesizer, tones defined in software |
| Beat demodulation (10–60 MHz) and the < 100 µs sort decision | RFSoC ADC, polyphase channelizer and decision kernel in programmable logic | Deterministic latency that no OS scheduler can disturb (E-03) |
| RF sentinel, receive-only | Second RFSoC ADC channel, FFT in programmable logic | O-01, E-11: sensing without any emitter |
| Policy engine, deferral queues, ledger, TLS 1.3 + PQC, manifest checks | Cortex-A53 cluster, Linux; OpenSSL 3.5+ or AWS-LC | E-04–E-12 are throughput work, not hard real time |
| Laser and interlock supervision | Separate lockstep safety MCU (TI Hercules or Infineon AURIX class) plus a dual-channel safety relay | Rule 2: no common silicon, clock or power rail with the RFSoC; the MCU can trip and log, never re-arm (E-01) |
| Implant command FSM (HOLD) | Safety MCU, or an isolated lockstep R5F partition if the G3 review accepts the isolation argument | Deterministic WCET (E-19); decided when the hold lifts |
| Root of trust | Discrete secure element or TPM 2.0: device identity, reservoir key-encryption key, measured boot | Keys stay out of DRAM except in use (E-06) |
| Timebase | 10 MHz OCXO into the RFSoC clock tree | CORR-12 |
| FSO PHY | COTS transceiver (802.11bb-class module, or emitter + TIA on the RFSoC's GTY transceivers) | E-02 |

Alternatives rejected:

- Discrete AWG + digitizer + x86 host: loses the shared timebase that S-01/S-02 rest on, roughly doubles the converter BOM, and puts sort decisions behind a general-purpose OS.
- GPU or Jetson-class SoC: no direct RF sampling, so it still needs the converters, and its latency is not deterministic.
- Safety logic on the RFSoC's own R5F cores: rejected for the laser interlock because it shares silicon, clock and power with the plane it protects.

Bench work for G1 uses an RFSoC evaluation board (ZCU216 or ZCU208 class); the custom carrier comes at G3. The RFSoC draws tens of watts, which the mains-powered hub can afford and the wearable cannot.

### 3.3 Decision: deployment priority

The hub's communications core ships first, research-use cytometry second, the wearable third; implant commands and every SPEC item wait for their own evidence. Each release needs the gate named in 4.3.

1. **R1 — BPSN-H communications core (after G2).** E-01, E-02, E-04 to E-10 and E-14, all BUILD on COTS parts. Pilot in one ward with non-diagnostic data. It goes first because it closes on parts that exist, runs on mains power, and its ledger and T-series evidence is reused by every later release.
2. **R2 — BPSN-H cytometry, research use only (after G3).** E-03, E-11, E-12, E-13 and E-15, labelled RUO with no diagnostic claim (CORR-4). It needs laser classification and EMC pre-compliance first; G4 decides whether to enter the IVD path.
3. **R3 — BPSN-W wearable communications (after G3).** The wearable profiles of E-02, E-05, E-06, E-14 and E-17, plus E-18 badges on the hub side, with no sensing claims. It comes after the hub because power, size and skin-distance eye safety are harder, and the hub is its key and policy anchor.
4. **R4 — implant command path (when the E-19 hold lifts).** Needs an implant partner's protocol, that partner's regulatory strategy and a safety review. Implant EMC coexistence (E-14) already ships in R1.
5. **R5 — custom arrays and SPEC sensing (after G4).** E-20 first; E-21 to E-24 only on E-20 parts that passed T-21, each still subject to its own rejection test.

### 3.4 Decision: security priority

Integrity of anything that can hurt a patient comes first and confidentiality third; covertness is ranked last and never relied on. When two objectives conflict, the higher one wins and the system fails closed.

1. **Integrity and authorization of safety-relevant commands and states:** implant commands, interlock state, sort actuation.
2. **Integrity and provenance of results and manifests:** cytometry results, therapy manifests, the decision ledger.
3. **Confidentiality of PHI and genomic data,** including against harvest-now-decrypt-later, since genomic data stays sensitive for decades.
4. **Availability of non-deferrable alarms** under RF and optical jamming.
5. **Low probability of intercept:** directionality, baffling and power control as defense in depth only.

| Adversary | Capability | Target | Controls | Tests |
| --- | --- | --- | --- | --- |
| A1 Passive optical eavesdropper | Telescope + APD on diffuse reflections; records traffic | PHI; session keys for later decryption | E-05, E-07, E-16 | T-06, T-10 |
| A2 RF jammer | Wideband or narrowband jamming of the fallback | Alarm availability | E-06, E-08 failover, E-09 | T-07, T-09 |
| A3 Optical jammer or injector | Bright source at the receiver; modulated light into the flow cell | Link availability; sort and analysis integrity | E-08, E-13 | T-08, T-14 |
| A4 Insider with physical access | Opens the enclosure, swaps cartridges, replays manifests, rolls back the clock | Laser safety; results; manifests | E-01, E-04, E-12, E-15 | T-01, T-05, T-13, T-16 |
| A5 Supply-chain attacker | Counterfeit reagents; tampered firmware | Result validity; device integrity | E-15; signed firmware with measured boot | T-16, T-06 |
| A6 Network attacker on the hospital LAN | Man-in-the-middle; lateral movement | Data plane | E-05 mutual authentication, E-16 segmentation | T-06, T-17 |
| A7 Future quantum adversary | Breaks ECDH/ECDSA on recorded traffic | Long-lived PHI and genomic data | E-05 hybrid ML-KEM, E-06 256-bit symmetric keys, hash-based firmware signatures | T-06 |
| A8 Side-channel observer | Spectrometer or near-field probe in line of sight | Data and keys via emission | E-17 | T-18 |

| Function | Baseline choice |
| --- | --- |
| Key establishment | TLS 1.3 with the X25519MLKEM768 hybrid group (ML-KEM-768, FIPS 203) |
| Signatures | ML-DSA-65 (FIPS 204) for certificates, manifests and ledger checkpoints |
| Firmware signing | LMS or XMSS (NIST SP 800-208) held in an HSM, or SLH-DSA (FIPS 205); where boot ROM verifies only classical signatures, the second-stage loader verifies the PQC signature |
| Symmetric | AES-256-GCM, or ChaCha20-Poly1305 on cores without AES hardware; HKDF-SHA-384; SHA-384 hash chains |
| Randomness | SP 800-90A DRBG seeded from an SP 800-90B-assessed entropy source in the secure element |
| Libraries | OpenSSL 3.5+ (adds ML-KEM, ML-DSA and SLH-DSA; default TLS keyshare X25519MLKEM768) or AWS-LC; FIPS 140-3 validated module versions where certificates exist; KAT-checked implementations on the wearable |
| Process | FDA section 524B obligations (SBOM, vulnerability handling, patching); IEC 81001-5-1 lifecycle; threat model re-reviewed at every gate |

The plan never relies on physical-layer key generation (S-25), tone-map secrecy on its own, the λ-dither beacon (SPEC) or covertness.

## 4. Phase 4 — Integration and verification

Phase 4 turns the 24 enhancements into one architecture, 26 tests and five gates. A release ships only when every test its gate names has passed; a failed test rejects its enhancement rather than its threshold.

### 4.1 Architecture

The hub has three planes, and only the safety plane can enable the beam: the RFSoC's real-time plane can request a trip, never a re-arm.

&#91;embedded content: BPSN-H architecture · 3 planes, 12 blocks\]

Peers sit outside the drawing: the FSO PHY talks to the ceiling receiver; the RF fallback radio carries only reservoir-keyed traffic (E-06); cold-chain loggers, badges and BPSN-W reach the application plane through the PQC session.

### 4.2 Verification matrix

Every enhancement has one primary test; thresholds live in 3.1, methods here. Each test writes its raw results into the decision ledger (E-04), so evidence accumulates in one place.

| Test | Verifies | Method and equipment | Sample / duration | Standard or reference | Gate |
| --- | --- | --- | --- | --- | --- |
| T-01 | E-01 | Photodiode and fast scope at the port; trip each switch; inject welded relay contact, stuck shutter, RFSoC hang, MCU reset | 1,000 trips per switch; one campaign per fault class | IEC 60825-1; IEC 60601-1 single-fault condition | G1 |
| T-02 | E-02 | BERT and traffic generator over a 0.5–4 m × 0–30° grid, ambient 0–1,000 lux (fluorescent, LED, daylight) | ≥ 3e12 error-free bits per point (95 % confidence at 1e-12) | IEEE 802.11bb where used | G0 |
| T-03 | E-02, E-01 | Radiometry at all accessible positions, worst-case drive; LEDs and the 450 nm beacon per IEC 62471 | Every emitter | IEC 60825-1; IEC 62471 | G1 (FSO), G3 (cytometry laser) |
| T-04 | E-03 | Spectrum analyzer on the DAC output; bead standards through the RFSoC chain and a reference AWG + digitizer on the same flow cell | ≥ 10,000 events per bead population, 3 runs per chain | — | G1 |
| T-05 | E-04 | Replay 1e6 synthetic decisions; inject truncation, reorder, edit and power loss; time safety actions with the ledger saturated | 1e6 events; 100 power cuts | IEC 81001-5-1; ISO 14971 | G1 |
| T-06 | E-05, firmware signing | ACVP/KAT vectors; interop between OpenSSL 3.5+, AWS-LC and the wearable stack; handshake timing; tampered-image rejection | All KATs; 10,000 handshakes per pair; 100 tampered images | FIPS 203, 204, 205; SP 800-208 | G2 |
| T-07 | E-06 | 72 h RF-only run after FSO loss; protocol-trace inspection; forensic read of erased reservoir slots | 72 h, full trace | NIST SP 800-88 | G2 |
| T-08 | E-08 | Calibrated LED and laser jammers swept in irradiance and angle (0–90°); modulated off-axis injection | 10 angles × 5 levels × 20 trials | — | G2 |
| T-09 | E-09 | Conducted, then shielded-room over-the-air jamming; replay of recorded ward traffic with seeded alarms | 24 h per jammer profile; ≥ 10,000 alarms | IEC 60601-1-8 alarm priorities | G2 |
| T-10 | E-07 | 50 mm telescope + APD at surveyed positions (corners, door, 2 m off-axis, reflections off clothing and ceiling) with the link at operating power | ≥ 30 positions × 3 room geometries | CORR-1 | G2 |
| T-11 | E-11, CORR-10 | Semi-anechoic radiated scan in RF-silent mode; near-field probe on drivers with known-plaintext correlation | Full CISPR 11 scan; 1e6-trace correlation | CISPR 11; IEC 60601-1-2 | G3 |
| T-12 | E-10 | Human-subject and phantom walk-throughs over 0.5–3 m; conducted and radiated RF logged through each transition | ≥ 1,000 passes; 10 subjects of varied build | — | G2 |
| T-13 | E-12 | Stale-manifest replay, hub RTC rollback, spliced logger records, forged excursion flags | ≥ 1,000 attack cases and 1,000 valid manifests | — | G2 |
| T-14 | E-13 | Modulated LED injected into the flow cell at session and non-session tones during bead runs | ≥ 1,000 clean and ≥ 1,000 injected runs | — | G3 |
| T-15 | E-14 | Implant simulator in a phantom with field probe; band-exclusion and duty-cycle logs | Every declared band; 24 h | ISO 14117; IEC 60601-1-2 | G3 |
| T-16 | E-15 | End-to-end runs with seeded unbound results, excursion-exposed reagents and counterfeit cartridges (missing or wrong QD tag) | ≥ 500 runs; ≥ 100 counterfeit cartridges | — | G3 |
| T-17 | E-16 | Static audit of KDF labels and key usage; key-compromise exercise on one λ domain | Whole codebase; one exercise per domain | — | G2 |
| T-18 | E-17 | Fixed-vs-random TVLA on the emission spectrogram and the driver near field | 1e6 traces per channel | — | G2 |
| T-19 | E-18 | Latency and badge power at 0.5–3 m; relay rig adding 1–5 m of path | ≥ 1,000 authentications; ≥ 200 relay attempts | — | G3 |
| T-20 | E-19 | WCET under worst-case load; fault injection (bit flips, malformed and replayed commands) | ≥ 1e6 commands; ≥ 1e4 injected faults | IEC 62304; ISO 14971 | On hold with E-19 |
| T-21 | E-20 | VNA small-signal bandwidth; BERT at 10 Gb/s; Δλ vs duty cycle against a reference QW LED; accelerated-life screen | ≥ 20 devices from ≥ 2 wafers | — | G0 (funding), G4 (adoption) |
| T-22 | E-21 | Dual-filter balanced detection BER at 1 kb/s; fingerprint enrolment and matching across dies, temperature and ageing | ≥ 100 dies | — | G4 |
| T-23 | E-22 | Phase fluorometry on fluorescein (≈ 4 ns) and a sub-ns reference dye at 40 and 200 MHz | 10 runs per frequency | — | G4 |
| T-24 | E-23 | Comparison with a reference oximeter during controlled desaturation | 20 subjects (screen only) | ISO 80601-2-61 for any later full study | G4 |
| T-25 | E-24 | Simultaneous capnography | 20 subjects, 1-minute epochs | — | G4 |
| T-26 | S-25 | Eve–Bob mutual information at 20 cm offset | One campaign | — | G2, informational; expected to fail |

### 4.3 Gates G0–G4

Five gates sequence the program: R1 ships at G2, R2 and R3 at G3, and no SPEC item ships before G4. G0 decides only custom-array funding; the COTS plan proceeds either way.

&#91;embedded content: Gate roadmap · 5 stages, gates G0–G4\]

A gate that fails sends the program back to the stage above it; the failed test rejects its enhancement and the gate is re-run without it, unless the enhancement is E-01, which no release ships without.

### 4.4 Regulatory path and top risks

Each module takes its own path, so a delay in one cannot hold the others: the hub core is a medical electrical device, cytometry starts as research use only, and implant commands belong to the implant maker's submission.

| Module | Path | Main standards | Gate |
| --- | --- | --- | --- |
| BPSN-H communications core | Medical device once it carries alarms or implant data (not a pure data-transfer system); class to be confirmed by regulatory affairs | IEC 60601-1, -1-2, -1-8; IEC 60825-1; IEC 62471; IEC 62304; IEC 81001-5-1; ISO 14971; IEC 62366-1; FDA section 524B; FCC Part 15 / EU RED for the RF fallback | G3 |
| BPSN-H cytometry | Research use only first (21 CFR 809.10(c) labelling, no clinical claims); IVD later under 21 CFR 864 or EU IVDR 2017/746 with performance studies | IEC 61010-1 and -2-101 if outside the patient environment, IEC 60601-1 if inside it; IEC 60825-1 | G3 (RUO), G4 (IVD decision) |
| BPSN-W wearable | Medical device if it carries clinical alarms; home use adds the home-healthcare collateral | IEC 60601-1, -1-2, -1-11; IEC 60825-1; IEC 62471; ISO 10993-1; IEC 62133-2 | G3 |
| Implant command path | Part of the implant manufacturer's submission (PMA supplement or equivalent) | ISO 14117; IEC 62304; ISO 14971 | Held with E-19 |
| Comm-head SpO₂ (if E-23 survives) | Oximeter clearance with a large, pigmentation-diverse accuracy study | ISO 80601-2-61; FDA pulse-oximeter guidance | After G4 |

| Risk | Likelihood / impact | Early signal | Mitigation |
| --- | --- | --- | --- |
| R-01 COTS FSO misses 1 Gb/s at 3 m in ambient light | Med / High | T-02 at G0 | Narrower filters, 1310 nm option, or 500 Mb/s per λ on more λ |
| R-02 Custom LUM/NAV arrays do not validate | High / Med | T-21 at G0 | The architecture closes on COTS (E-02); custom parts only raise throughput |
| R-03 Interlock or laser classification fails single-fault analysis | Low / High | T-01, T-03 at G1 | Hardware redesign before any cytometry release |
| R-04 Research-use cytometry drifts into diagnostic claims | Med / High | Labelling and marketing review | RUO labelling locked until the G4 IVD decision |
| R-05 No implant partner | High / Med | R4 planning | E-19 stays on hold; E-14 ships regardless |
| R-06 PQC library or FIPS 140-3 validation lags the chosen versions | Med / Med | T-06 | Two independent stacks; hybrid groups keep classical security meanwhile |
| R-07 Unintentional emissions erase the RF-silent margin | Med / Med | T-11 pre-scan on the G1 bench | Shielded AOD drive and driver layout before G3 |
| R-08 Clinicians reject NIR emitters near neonates | Low / Med | T-03 classification and user research | IEC 62471 exempt-group evidence; emitters out of direct view |

## Open questions

Eight assumptions carry the plan; each has the test or decision that retires it and the gate by which it must be retired.

| ID | Assumption | Retired by | By |
| --- | --- | --- | --- |
| \[A-1\] | Optical ToF presence reaches usable SNR at 3 m with 10 ns pulses and 100 averages | T-12 | G2 |
| \[A-2\] | AOD drive shielding holds comb leakage under 30 dBµV/m at 3 m | T-11 | G3 |
| \[A-3\] | The badge retro-modulator averages well under 1 mW | T-19 | G3 |
| \[A-4\] | Cold-chain loggers emit signed, counter-indexed records, or a gateway signs them | Supplier survey, then T-13 | G2 |
| \[A-5\] | An implant maker will expose a command protocol and co-own the regulatory path | Partner decision | Before E-19 leaves hold |
| \[A-6\] | Target rooms can take a ceiling FSO receiver with line of sight to every bed position | Site survey | Before the R1 pilot |
| \[A-7\] | NICU/ICU clinicians accept NIR emitters once IEC 62471 exempt-group classification is shown | T-03 and user research | G3 |
| \[A-8\] | LUM/NAV samples (≥ 20 devices from ≥ 2 wafers) are available for characterization | Supplier commitment | G0 |

One question has no assumption behind it yet: whether the hub core, if it carries no alarms, could be a non-device data system. Regulatory affairs should answer it before G1, because it sets the documentation load for R1.

## Sources

No source page could be opened from the session that wrote v1.0 (page fetch was blocked). Figures marked below were checked against web-search summaries on 2026-10-17 and from memory; confirm each against its primary document before G1. Physical derivations (CORR-11, CORR-17, T-02 bit counts) are worked from first principles in the text.

- [NIST FIPS 203, 204, 205](https://csrc.nist.gov/pubs/fips/204/final) (August 2024): ML-KEM, ML-DSA (signature sizes in CORR-14), SLH-DSA.
- [NIST SP 800-208](https://csrc.nist.gov/pubs/sp/800/208/final): LMS and XMSS for firmware signing.
- [OpenSSL 3.5 release notes](https://openssl-library.org/news/openssl-3.5-notes): 3.5.0 released 8 April 2025, adds ML-KEM, ML-DSA and SLH-DSA, default keyshares X25519MLKEM768 and X25519.
- [IEEE 802.11bb-2023](https://standards.ieee.org/standard/802_11bb-2023.html): light communications in the 800–1000 nm band; IEEE lists it as superseded, so check the current amendment before relying on it.
- [AMD DS926, Zynq UltraScale+ RFSoC data sheet](https://docs.amd.com/r/en-US/ds926-zynq-ultrascale-plus-rfsoc/RF-ADC/RF-DAC-to-PL-Interface-Switching-Characteristics): Gen 3 converter counts and rates in 3.2.
- [FDA draft guidance on pulse oximeters, January 2025 (RAPS summary)](https://www.raps.org/resource/pulse-oximeters-fda-drafts-guidance-to-address-per.html): larger, pigmentation-diverse accuracy cohorts (CORR-16).
- Cited by designation only: IEC 60825-1, IEC 62471, IEC 60601-1 (with -1-2, -1-8, -1-11), IEC 61010-1 and -2-101, ISO 14117, ISO 14971, IEC 62304, IEC 81001-5-1, IEC 62366-1, ISO 80601-2-61, ISO 10993-1, IEC 62133-2, CISPR 11, NIST SP 800-88, SP 800-90A/B, 21 CFR 809.10(c), 21 CFR 864, EU IVDR 2017/746.
