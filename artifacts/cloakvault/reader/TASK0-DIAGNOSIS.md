# Task 0 — Diagnosis Experiment: frozen historical profile "spike-2026-08" through Reader v0.2

**Status: DEVELOPMENT DIAGNOSIS. Bridge Run 01 is seen development data. No Gate claim. No threshold changed. No Bridge image used for training. Reported, not optimized.**

Date: 2026-08-17.

## 1. Frozen historical profile "spike-2026-08"

| Binding | Value |
| --- | --- |
| Glyph bank | Spike pooled global bank, built EXCLUSIVELY from `spike/captures/baseline-0-std-S01..jpeg` + `baseline-0-std-S02.jpeg` via the frozen spike code path (`spike/reader/gatea_nn_layer.py build_global_bank`, unmodified; imported, not copied) |
| Bank file | `reader/banks/spike-2026-08-bank.npz` — 5,680 samples × 1,292 features (19×34 gray + Sobel-magnitude z-scores, L2-normalized; blur sigmas 0/0.8/1.4/2.0) |
| **Bank SHA-256** | `d72a8f92a4f2a79ea666edc19dc958dc89fec0bd48757f3add561eff8ed702a6` |
| Feature/normalization pipeline | Spike pipeline verbatim: CLAHE (clipLimit 2.5, tile 16×16), centroid alignment ±3 px, gray+Sobel z-score features, per-class max nearest-neighbour (`reader/spike_bank_classifier.py`; alignment/feature functions replicated byte-for-byte from `gatea_nn_layer.py`) |
| conf_floor / margin_floor | 0.64 / 0.02 (frozen; unchanged) |
| Profile file | `reader/profiles/spike-2026-08.json`, SHA-256 `345d7da84d08aaa9022310610462e49aab9bae826b928a2d718a499bffac1133` |
| Quality gate | v0.2 development thresholds, run in **REPORT-ONLY** mode (verdict logged per sheet, never blocks) |
| Scale bridging (documented) | The spike classified on a 2480×3508 rectified page (measured grid pitch 18.798 px ≈ its 19 px window). Reader v0.2 runs on the raw capture, so each cell window is extracted at the line's measured pitch and resized to the spike window geometry before feature extraction — a unit conversion recorded in the bank (`pitch_ref_rect_px`), not a tunable and not a new pipeline. |

## 2. Harness fidelity control (prerequisite for interpreting the funnel)

The adapter was scored on spike baseline S02 (T1–T4, 568 cells) at correct, spike-derived cell geometry with the frozen floors: **561 correct / 6 erasures / 1 silent-wrong (98.8 % correct; silent-wrong 0.18 %)** — consistent with the spike's handoff figure (534/568 at zero threshold, before floors). The bank, features, normalization, thresholds, and adapter are therefore faithful. Any Bridge failure below is not a harness artifact.

AEAD hook: real authenticated decode via the frozen reference decoder (`interop/python/cloakvault_v3.py decode_pipeline`) with the T5 vault key from `spike/tokens.json`; success additionally requires recovered entropy == T5 ground truth. (Bridge production pages carry T5 per `bridge-log-01`.)

## 3. End-to-end run: all 19 Bridge Run 01 images, gate report-only

Full machine-readable funnel: `reader/task0-spike-2026-08-replay.json`.

### Per-sheet outcomes

| Sheet | Gate (report-only) | Gate reasons | Terminal category | '?' cells | RS erasure bytes |
| --- | --- | --- | --- | --- | --- |
| S28 baseline-0 | RECAPTURE | LOW_SHARPNESS; FOOTER_SIGNAL_TOO_WEAK | RS_BUDGET_EXCEEDED | 2833 | 83 |
| S29 coffee-2 | RECAPTURE | LOW_SHARPNESS | RS_BUDGET_EXCEEDED | 621 | 83 |
| S30 coffee-2 | RECAPTURE | LOW_SHARPNESS; FOOTER_SIGNAL_TOO_WEAK | RS_BUDGET_EXCEEDED | 3041 | 82 |
| S31 crumple-2 | RECAPTURE | LOW_SHARPNESS | RS_BUDGET_EXCEEDED | 1655 | 82 |
| S32 crumple-2 | RECAPTURE | LOW_SHARPNESS | RS_BUDGET_EXCEEDED | 3182 | 83 |
| S33 water-2 | RECAPTURE | LOW_SHARPNESS | RS_BUDGET_EXCEEDED | 2544 | 83 |
| S34 water-2 | RECAPTURE | LOW_SHARPNESS | RS_BUDGET_EXCEEDED | 1453 | 83 |
| S35 water-3 | RECAPTURE | LOW_SHARPNESS | RS_BUDGET_EXCEEDED | 4433 | 83 |
| S36 water-3 | RECAPTURE | LOW_SHARPNESS | FOOTER_LOCALIZATION_FAIL | — | — |
| S37 crumple-1 | RECAPTURE | LOW_SHARPNESS; FOOTER_SIGNAL_TOO_WEAK | FOOTER_LOCALIZATION_FAIL | — | — |
| S38 fold-3 | RECAPTURE | LOW_SHARPNESS; FOOTER_SIGNAL_TOO_WEAK | RS_BUDGET_EXCEEDED | 3372 | 83 |
| S39 scratch-3 | ACCEPT | — | RS_BUDGET_EXCEEDED | 501 | 81 |
| S40 scuff-3 | ACCEPT | — | RS_BUDGET_EXCEEDED | 1154 | 83 |
| S41 fade-3 | RECAPTURE | FOOTER_SIGNAL_TOO_WEAK | RS_BUDGET_EXCEEDED | 974 | 78 |
| S42 edge-3 | ACCEPT | — | RS_BUDGET_EXCEEDED | 2418 | 80 |
| S43 bodyring-1 | ACCEPT | — | FOOTER_LOCALIZATION_FAIL | — | — |
| S44 cliptear-1 | ACCEPT | — | FOOTER_LOCALIZATION_FAIL | — | — |
| S45 spanstain-1 | RECAPTURE | FOOTER_SIGNAL_TOO_WEAK | RS_BUDGET_EXCEEDED | 1431 | 81 |
| S46 baseline-0 | ACCEPT | — | FOOTER_LOCALIZATION_FAIL | — | — |

### Stage funnel (19 sheets)

| Stage | Reached | Passed |
| --- | --- | --- |
| CAPTURE gate (report-only) | 19 | 6 ACCEPT / 13 RECAPTURE (logged, none blocked) |
| FOOTER localization | 19 | 14 (5 fail: S36 S37 S43 S44 **S46 pristine**) |
| REGISTRATION + CLASSIFICATION | 14 | 14 nominal — but see confound below |
| TOKEN_EXTRACTION (142-char structural) | 14 | 14 |
| RS decode (frozen decoder) | 14 | 0 (all budget-exceeded; 78–83 erased RS bytes of 83) |
| AEAD authenticated | 0 | **0** |

**Authenticated decodes: 0 of 19.**

### Reference-baseline comparison

Against the attached appendix (validated Run 01 failure mechanisms) and `bridge-log-01`: the pristine session controls S28 and S46 both fail (S28 soft/dim → all-erasure RS overflow; S46 → footer never localized), which under the campaign log's own rule indicts session/reader, not damage. The observed failure modes match appendix mechanisms 4–9 exactly: full-width serif body lines selected as candidates (S42 produced 10 candidates with ~200-cell grids at pitch ≈ 14.8 spanning the page width — footer lines are 48 chars over ~1/3 page), no autocorrelation-at-pitch footer signature, no sentinel-anchored x0/margin anchoring, no per-line scale normalization. The spike-side reference (S02 pristine 94 % pre-floor) is reproduced by the harness control in §2.

## 4. Decision rule — outcome as specified

Authenticated decodes = 0 < 5 → **the rule's "bank and feature incompatibility confirmed as a primary defect; Task 3 plus Phase B are the fix" branch fires.**

**Mandatory honesty annotation (this is diagnosis, not advocacy):** the funnel does not cleanly reach the bank. On all 14 sheets that passed footer localization, the located "footer" candidates were full-width body-text lines mis-registered into ~200-cell grids (ground-truth character agreement at zero floor ≈ chance; mean confidence ≈ 0.46–0.52 vs ≥ 0.64 floor), so the classifier was scored on windows that do not contain footer glyphs. Given the §2 control (98.8 % correct through the identical bank+adapter at correct geometry), this run **confirms locator/registration incompatibility with real captures as the dominant, upstream primary defect**, and leaves bank-vs-real-print compatibility **untested at reader-provided geometry** — neither confirmed nor refuted by the <5 count. What the run does refute: the hypothesis that the quality gate alone was hiding successes (gate report-only produced zero decodes), and (via §2) any harness-level incompatibility of bank, features, normalization, or floors.

## 5. Discipline statement

- No Bridge Run 01 image contributed to the bank or any training step.
- No threshold changed: 0.64/0.02 applied verbatim; gate thresholds untouched (mode report-only for this experiment only; blocking remains the default and is test-covered).
- Frozen files untouched: protocol doc, test vector, reference decoder, spike source files (imported as-is).
- Reader test suite after the pluggable-classifier/report-only changes: 53/53 pass; default behavior (blocking gate, synthetic classifier) unchanged.
