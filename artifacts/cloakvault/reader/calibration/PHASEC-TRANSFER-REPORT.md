# Phase C — Production-Domain Transfer Experiment (Tasks 5–6)

Status: **DEVELOPMENT / NOT GATE-A1** · frozen 0.64/0.02 throughout · copy2
never trained on · S46 never in any bank (DEVELOPMENT_REPLAY only) · Bridge
hashes banned from bank construction (enforced + regression-tested).

Data: 12 owner captures of the production-path v2 sheet — 2 physical print
copies × 3 captures (std-a, std-b, room) × 2 pages, registered in
`reader/corpora/cal-run02-production-raw.json` with per-image `print_copy`,
page, and `page_footer_indices` (page→footer mapping verified against the
globally unique ground-truth tokens: footers 0–7 page 1, 8–15 page 2).
Capture bytes are re-verified against the registered SHA-256 before any
labelling.

## Extraction (span-aware v2, `reader/calibration/extract_v2.py`)

Production footers have no uniform `chars_per_line`; per-line expected cell
counts come from the printed lines (87 URL / 48 / 50 with `&v=1`), and only
the 142 token cells per footer are harvested (URL prefix, suffix, trailer
excluded via `token_line_spans`). Label-integrity rules (mislabeling is
strictly worse than dropping; adversarial tests in
`reader/tests/test_extract_v2_label_integrity.py`):

- registration must be layout-consistent (0.8–1.25× span/expected chars) —
  NO fallback; the half-pitch harmonic can never label.
- duplicate detections of the same physical line (2×-pitch harmonic bands
  a fraction of a line height away, same span — observed on real captures)
  are deduped geometrically before grouping.
- a footer group is accepted ONLY as exactly 3 token lines in reading
  order with the expected width-ratio pattern; stray bands reject the
  group, and a wrong per-page group count rejects the whole capture.

Results: 10/12 captures accepted (1090–1136 samples each); 2/12 rejected
honestly (`copy1-std-a2`, `copy2-std-a2`: FOOTER_GROUPS ≠ 8 — band
detection missed faint groups; rejected rather than guessed).
Totals: copy1 = 5,634 samples, copy2 = 5,680.

## Bank + evaluation (`scripts/phasec_transfer.py`, report JSON alongside)

Bank `cal-run02-copy1-bank.npz` built from **copy1 only**. Provenance is
enforced on every run, including reruns over a pre-existing bank: npz sha
vs manifest, bank/corpus identity, listed capture hashes ⊆ manifest copy1
hashes, Bridge-hash ban.

| evaluation | n | decided acc | erasure | confident-wrong | median conf |
|---|---|---|---|---|---|
| copy1 leave-one-capture-out (5 folds) | 5,634 | **0.877** (fold mean, range 0.840–0.923) | — | — | — |
| copy1 bank → ALL copy2 | 5,680 | **0.827** | 0.182 | 0.142 | 0.925 |
| … copy2 std only | 3,408 | 0.877 | 0.163 | 0.103 | — |
| … copy2 room only | 2,272 | 0.747 | 0.210 | 0.199 | — |

Cross-copy transfer works: copy2 (never trained) scores essentially at the
copy1 holdout level, median top-cosine 0.92 (vs 0.55 for S46 under the
cal-run01 bank in the parity diagnostic). Confident-wrong is spread evenly
across classes (no dominant confusion pair) and concentrates in room
light — capture/illumination noise, not glyph-identity confusion.

## S46 DEVELOPMENT_REPLAY vs copy1 bank (`scripts/phasec_s46_replay.py`)

Profile `cal-run02-development.json` is regenerated from the bank manifest
on every run (bank metadata can never go stale; 0.64/0.02 untouched). Same
candidate-attempt loop and deepest-honest-failure selection rule as
`read_frame` (mirroring the acceptance-audit funnel):

- quality ACCEPT, candidate index 1 (zero-based) of 5, **RS_BUDGET_EXCEEDED**
- classified cells 350 (again ≈2× expected — the half-pitch registration
  harmonic), erasure cells 330
- vs T5 ground truth: 1/142 correct, 136 erasure, 5 confident-wrong
- RS bytes: E=0, e=83, **2E+e = 83 vs budget 34**. AEAD not reached.
- vs the cal-run01-bank replay (350 classified / 312 erasure cells / RS
  e=81): the outcome class is identical (1/142 correct, budget exceeded
  by ~2.4×); the new bank shifts a few confident-wrongs into erasures
  (16→5 CW, 125→136 erasure) but moves the read no closer to decoding.

## Verdict (owner decision tree)

**B — calibration generalizes, Bridge S46 remains unreadable — with the
failure mechanism isolated.** Evidence:

- Within the production print domain, the bank transfers across physical
  copies (0.83 decided on never-seen copy2) → NOT verdict C (the
  classifier does not fail within a matched domain).
- S46 replay remains in the same failure class (1/142, 2E+e = 83) and
  again classifies 350 cells — the frame pipeline's **half-pitch
  registration harmonic** (documented in the parity diagnostic) destroys
  the read before the bank can matter; a domain-matched bank cannot help
  when every window contains half a glyph.
- Whether a *residual* print-density gap remains on top (S46's halved
  contrast) cannot be measured until the harmonic is fixed; the parity
  diagnostic's pitch-hinted probe suggests some gap persists (median
  cosine 0.65 vs copy2's 0.92, though crop rules differ).

**Not verdict A**: the Bridge replay still fails. **Blocked on**: the frame
pipeline lacks the layout-consistent pitch filter the calibration extractor
already uses. Fixing it is a reader-behavior change and per process needs
owner approval (previously flagged). No thresholds were tuned; nothing was
optimized against S46.

## Caveats / deviations

- 2 of 12 captures (both std-a page 2) rejected by band detection; coverage
  remains 5 capture-folds for copy1 LOCO and both conditions for copy2.
- Confident-wrong 10–20% on copy2 is far above the RS budget for a real
  read even with correct registration; if a Bridge-style read is attempted
  after the harmonic fix, expect RS margin to remain the binding
  constraint, especially in room light.
- v2 tokens are sentinel-prefixed balanced calibration content, not
  RS-valid tokens (documented in the sheet ground truth).
