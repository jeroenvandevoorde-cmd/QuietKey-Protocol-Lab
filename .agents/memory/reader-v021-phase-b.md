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
