---
name: Reader v0.2.1 Phase A state
description: Where the v0.2.1 calibration milestone stands and locator-v2 lessons; read before resuming Gate A reader work.
---

## Status (2026-08-17)
Phase A COMPLETE on branch `reader-v021-calibration` (worktree `/tmp/reader-v021`, base b118429). Stopped at the Task 21 physical-capture checkpoint: owner must print `reader/calibration/sheets/calibration-sheet-calsheet-v1-s20260817.html` and capture per `reader/calibration/CALIBRATION-CAPTURE-PROTOCOL.md`. Phase B (extraction → grouped holdout → bank → new DEVELOPMENT profile) only after captures arrive. No Bridge Run 02, no Gate A1. Do not merge; PR title "Gate A Reader v0.2.1: real-print calibration and locator closure".

## Durable lessons (locator v2)
- Band detection needs a rolling-median baseline window much larger than a line height (floor ~25 rows) AND hysteresis growth (strict seeds >4·MAD grown into >1.25·MAD) or glyph lines detect as 2-3 row slivers that starve the classifier.
- Stain/tear edges beat a comb score alone; the text-run structure filter (ink-run count ≈ span/pitch) is what kills them.
- Damaged lines fail strict flush-left and can return the half-pitch harmonic; block grouping must accept 60% horizontal overlap as alignment and pitch agreement modulo factor 2.
- **Why:** each of these was a real Bridge Run 01 failure mode (S43/S44/S46); regressions are guarded by `reader/tests/test_locator_regression.py` (skips when gitignored captures absent).

## Enforcement architecture (review round)
Corpus usage flags in `reader/corpora/*.json` are enforced in code, not just documented: calibrate() requires threshold_calibration_allowed; validate() refuses banned corpora unless --development-replay (output labelled DEVELOPMENT_REPLAY); grouped_holdout() and bank builds reject Bridge hashes. Synthetic test corpora must be registered in `reader/corpora/` or these paths refuse them.

## v0.2.1 Bridge funnel (development replay, never validation)
13 CAPTURE_QUALITY_REJECT / 6 RS_BUDGET_EXCEEDED (was 3 FOOTER_LOCALIZATION_FAIL + false positives in v0.2). All six quality-ACCEPT sheets localize; RS failure is expected until the real-print bank exists.
