---
name: Reader v0.2.1 Phase B state
description: Phase B (real-print calibration bank cal-run01) results and durable extraction lessons; read before resuming Gate A reader work.
---

## Status (2026-08-17)
Phase B COMPLETE on branch `reader-v021-calibration` (commits through 159a830; worktree `/tmp/reader-v021` — /tmp is wiped between sessions, recreate with `git worktree add`). Bank `cal-run01-bank.npz` (4032 samples, 6/8 captures), profile `cal-run01-development.json`, LOCO holdout 0.71 / condition-holdout 0.73 decided-accuracy at frozen 0.64/0.02. Bridge Run 01 dev replay with the new bank: 19/19 reach RS stage (0 footer fails) vs baseline 14 RS + 5 footer-fail — RS_BUDGET_EXCEEDED now the sole funnel wall. Still DEVELOPMENT / NOT GATE-A1; do not merge branch.

## Deviations recorded (in phaseb report + corpus manifest)
- Sheet printed paginated 3+1 (blocks 1-3 page 1, block 4 page 2); captures `*-1/-2.jpeg` are pages, not repeats.
- copy1 only (owner reports copy2 visually identical) — copy-level holdout impossible.
- Both angle captures fail extraction (perspective keystone, not rotation) — honest capture-quality failure, out of scope.

## Durable lessons (real-print extraction)
- Autocorrelation registration half-pitch harmonics score deceptively well on cell-alignment metrics (half-pitch centers still touch ink). Filter registration candidates to layout-consistent pitch (0.8–1.25× span/48) BEFORE score-based selection; a hint-always policy hurts synthetic phase fits (holdout 0.55 vs 1.0), a ratio-fallback-only policy hurts real photos — dual-register and pick within the layout-consistent pool.
- A single-block page may only be labelled via metadata recorded in the corpus manifest (`page_block_indices`), never inferred from image content — inferred pagination was a review-round FAIL. Guards: metadata pins exactly one block + unhinted BLOCK_GROUPS_1 + sibling capture shows the other n-1 groups.
- Resumable /tmp caches for slow pipelines must key on EVERY labelled-output input: capture sha, ground-truth sha, hint, and code revision of all behavior modules (extract, registration, structural_locator); replay caches need profile sha + reader code sha. Regression tests in `reader/tests/test_phaseb_pipeline.py`.
- Sub-page groups smaller than max(2, lpb/2) lines must be dropped as strays before block indexing or labels silently shift.
- Shell timeout is 300s and background processes die with the shell session — long pipelines need per-item caching + rerun-until-done, or in-script ProcessPoolExecutor.

## Acceptance audit (post-Phase B)
- Owner-ordered analysis-only audit → `reader/calibration/ACCEPTANCE-REPORT-cal-run01.md` + JSON via read-only `scripts/phaseb_acceptance_audit.py`. Verdict: **B — bank INADEQUATE**; Bridge Run 02 and Reader freeze remain blocked pending owner review.
- 0.711/0.731 were FOLD-MEAN decided accuracies; pooled sample-level = 0.768/0.761. Confident-wrong 16% — far beyond RS(83,49) 34-unit budget.
- Central finding: pristine gate-accepted S46 reads 1/142 token chars with the cal bank → calibration↔Bridge print domain shift; more captures of the current sheet won't help. Copy-out holdout invalid (copy 1 only).
- Angle captures fail at line-band layout validation (PITCH_LAYOUT_MISMATCH from perspective pitch variation), deskew ≈0° — needs homography rectification, not more data.

## Phase C transfer experiment (durable lessons)
- Verdict B confirmed: cal-run02 copy1 bank transfers to never-seen copy2 (0.83 decided, median cosine 0.92) but S46 replay still fails identically (1/142, 2E+e 83 vs 34) because the frame pipeline's half-pitch registration harmonic classifies 350 cells; bank domain was NOT the binding failure. Frame-pipeline layout-consistent pitch filter fix awaits owner approval.
- Band detector sometimes reports one printed line TWICE: a 2x-pitch harmonic band a fraction of a line height away with the same x-span. Any exact-group-count rule must dedupe these geometrically first (gap<0.35 line height, heavy span overlap, similar span length, keep the layout-consistent one) or good captures get rejected.
- Standalone replay/eval scripts must independently re-validate bank provenance (identity, capture hashes ⊆ allowed set, banned-hash check) — checks living only in the bank-building script don't protect direct execution; a reviewer caught this twice.
- Confident-wrong on production-domain sheets is spread evenly across classes and concentrates in room light — illumination noise, not glyph confusion; RS margin stays the binding constraint even with correct registration.

## Production-parity diagnostic (durable lessons)
- S46 collapse has TWO stacked causes: (1) line registration locks the half-pitch harmonic on production-context footer lines (registered ~11 px vs layout 21 px → half-glyph windows); a layout-pitch hint corrects it and lifts median bank cosine 0.55→0.65. (2) A residual print-domain gap remains — glyph geometry matches cal but contrast is roughly halved (Bridge print far fainter); attribution provisional until a token-span-matched control (Task 5).
- Calibration sheets must REUSE production rendering code, never copy appearance: the v2 generator imports the production wrap/render functions, extracts the footer class string and @media print block verbatim at generation time, and pins source sha256s so tests fail on drift. See `reader/calibration/PRODUCTION-PARITY-DIAGNOSTIC.md`.
- v2 tokens start with the production sentinel but are deliberately NOT RS-valid (decodability precludes exact class balance). The v1 extractor's uniform `chars_per_line` assumption does NOT fit production footers — a span-aware extraction (URL prefix / `&v=1` / trailer exclusion via `token_line_spans`) must be built before consuming v2 captures.
- STOPPED at physical checkpoint: owner to print 2 copies of the v2 sheet (same printer/settings as Bridge); transfer experiment + A/B/C verdict blocked on captures.
