# Reader v0.2.1 Calibration Acceptance Report — cal-run01

Status: **DEVELOPMENT / NOT GATE-A1 / ANALYSIS-ONLY**
Operating point: conf 0.64 / margin 0.02 — FROZEN, reported as-is, not tuned.
Machine-readable companion: `reader/calibration/acceptance-audit-cal-run01.json`
(produced by `scripts/phaseb_acceptance_audit.py`; no thresholds, bank,
classifier, registration, quality gates, protocol code, or Bridge artifacts
were modified).

---

## 1. Metric definitions

Per evaluated glyph cell the classifier produces top cosine score `c1`
(per-class max nearest-neighbour against the training-fold bank) and margin
`m = c1 − c2` (second-best class). At the frozen operating point:

- **erased**: `c1 < 0.64 OR m < 0.02` → output `?`
- **decided**: not erased
- **correct**: decided AND predicted class == ground-truth label
- **confident wrong**: decided AND predicted class != ground-truth label

Formulas (N = evaluated samples, C = correct, X = confident wrong, R = erased;
N = C + X + R):

- decided accuracy = `C / (C + X)` = `C / (N − R)`
- coverage (decided %) = `(N − R) / N`
- erasure rate = `R / N`; confident-wrong rate = `X / N`

**Denominators of the previously reported numbers.** 0.711 (LOCO) and 0.731
(condition-out) were the **unweighted mean over folds of per-fold decided
accuracy** — i.e. mean over 6 capture folds / 3 condition folds of
`C_f / (C_f + X_f)`. They are NOT pooled sample-level accuracies. Pooled
sample-level decided accuracy is 0.768 (capture-out) / 0.761 (condition-out);
the fold-mean is lower because two weak folds get equal weight.

Granularity: all calibration metrics are **character (glyph-cell) level**, not
byte level. **Sentinel/wrapper cells are NOT included**: only the 48
labelled calibration-grid columns per line are sampled (the calibration sheet
ground truth covers exactly these cells; there is no wrapper text inside the
sampled blocks). Byte-level figures appear only in §8 RS accounting.

## 2. Complete frozen-operating-point outcome

### A. Leave-one-capture-out (6 folds, 4032 samples)

| metric | value |
|---|---|
| evaluated characters | 4032 |
| correct | 2150 (53.3%) |
| erasure | 1234 (30.6%) |
| confident wrong | 648 (**16.1%**) |
| pooled decided accuracy | 0.768 |
| coverage | 69.4% |
| mean per-fold decided accuracy | 0.711 (as previously reported) |

Per-fold (see §5 for capture identity):

| fold (capture) | n | correct | erasure | conf-wrong | decided acc | coverage |
|---|---|---|---|---|---|---|
| std-1 (2 pages, 24 lines) | 1152 | 798 | 202 | 152 | 0.840 | 0.825 |
| std-2 | 576 | 417 | 111 | 48 | 0.897 | 0.807 |
| shadow-2 | 576 | 381 | 158 | 37 | 0.911 | 0.726 |
| shadow-1 | 576 | 316 | 153 | 107 | 0.747 | 0.734 |
| lowlight-2 | 576 | 143 | 285 | 148 | 0.491 | 0.505 |
| lowlight-1 | 576 | 95 | 325 | 156 | **0.378** | 0.436 |

(Fold→capture mapping: sha 4eb1dc4b=std-1, b4656ffe=std-2, f4f2c6c0=shadow-2,
235d4d25=shadow-1, cfbc8f4e=lowlight-2, c23b50c1=lowlight-1; full shas in the
JSON.)

### B. Leave-one-condition-out (3 folds)

| metric | value |
|---|---|
| evaluated | 4032 |
| correct | 2173 (53.9%) |
| erasure | 1176 (29.2%) |
| confident wrong | 683 (**16.9%**) |
| pooled decided accuracy | 0.761 |
| coverage | 70.8% |
| mean per-fold decided accuracy | 0.731 (as previously reported) |

| fold | n | correct | erasure | conf-wrong | decided acc | coverage |
|---|---|---|---|---|---|---|
| std | 1728 | 1220 | 293 | 215 | 0.850 | 0.830 |
| shadow | 1152 | 518 | 450 | 184 | 0.738 | 0.609 |
| lowlight | 1152 | 435 | 433 | 284 | **0.605** | 0.624 |

### C. Leave-one-print-copy-out

**INVALID with the current corpus** — every accepted capture is physical
copy 1 (a recorded corpus deviation). Copy-level generalization is
unmeasured and unmeasurable until copy-2+ captures exist.

Per-class sample counts: 30–36 held-out samples per glyph per single-page
capture; totals per glyph 99–142 (full table in JSON `per_glyph_health`,
`bank_examples` = training-bank examples per class).

## 3. Confusion analysis

Full decided confusion matrix: JSON key `confusion_matrix_decided`.
Top confident-wrong substitutions (capture-out records):

| src→pred | n | med conf | med margin | conditions/pages |
|---|---|---|---|---|
| 5→8 | 5 | 0.881 | 0.050 | std/1 ×4, lowlight/2 |
| 6→p | 5 | 0.894 | 0.057 | spread across all conditions |
| n→u | 5 | 0.723 | 0.043 | lowlight/1 ×3, std |
| g→q | 4 | 0.790 | 0.070 | spread |
| t→q | 4 | 0.936 | 0.026 | std/1 ×2, lowlight, shadow |
| 8→w | 4 | 0.907 | 0.029 | spread |
| w→9 | 4 | 0.872 | 0.063 | spread |
| u→n | 4 | 0.847 | 0.068 | std/1 ×4 |
| h→n | 4 | 0.751 | 0.053 | std/1 ×3 |
| x→z | 4 | 0.849 | 0.025 | spread |
| c→3 | 4 | 0.898 | 0.060 | lowlight/1 ×3 |
| 5→9 | 4 | 0.800 | 0.072 | shadow/1 ×3 |
| q→t | 4 | 0.940 | 0.044 | shadow/2 ×3 |
| 3→c | 3 | 0.846 | 0.030 | spread |
| 5→g | 3 | 0.875 | 0.047 | std/1 ×2 |

Interpretation: the head of the list is dominated by **visually similar
Bech32 pairs** (n↔u, c↔3, t↔q, x↔z, g↔q, 5↔8/9/g, 8↔w) with high top
confidences (0.72–0.94) and thin margins — genuine shape confusability, not
gross geometry failures. However the tail is extremely flat: 648 confident
wrongs spread over ~330 distinct pairs (max count 5), and errors concentrate
in the lowlight/shadow page-1 captures. That flatness indicates a second,
**non-shape component: low-contrast/blur-driven feature collapse** in the
weak captures rather than isolated confusable pairs.

## 4. Per-glyph health

Full table in JSON (`per_glyph_health`: bank examples, held-out n, correct%,
erasure%, confident-wrong%, median conf, median margin per glyph).

Materially weak classes (capture-out): **c (36% correct, 22% conf-wrong),
5 (41%, 26% conf-wrong), n (42%, 20%), u (42%, 19%), v (43%), 6 (48%, 22%),
g (47%, 19%), 7 (47%), f (47%), l (50% correct but 46% erasure)**.
Best classes: m/s (69%), 0 (66%), h (65%), 9/x (64%).

There is no healthy majority hiding a few bad classes: **no glyph exceeds
69% correct** under grouped holdout, and 30 of 32 classes are below 60%.
Weakness is broad-based, worst for the confusable pairs above.

## 5. Copy / condition generalization

- **Capture folds** (§2A table): std-1 0.840, std-2 0.897, shadow-2 0.911,
  shadow-1 0.747, lowlight-2 0.491, lowlight-1 0.378.
- **Condition folds** (§2B): std 0.850, shadow 0.738, lowlight 0.605.
- **Copy folds**: impossible — copy 1 only.

Reading: the 0.71–0.73 averages are NOT caused by one bad outlier group
alone; they are the combination of (a) a strong std cluster (~0.85–0.90),
(b) a genuinely weak **lowlight** condition (both lowlight captures are the
two worst folds; coverage collapses to ~0.44–0.51), and (c) broadly thin
margins everywhere (median margins 0.025–0.065, right at the 0.02 floor).
Page effects are secondary (page-1 slightly worse than page-2 in lowlight/
shadow). Copy-specific printing effects are **unknown** (single copy).
Conclusion: lighting sensitivity + generally weak discrimination, not a
single poor group.

## 6. Angle capture failure

Both angle captures were rejected with **zero lines extracted**
(no unsafe labels were ever assigned — rejection happens before labelling).

- `…-angle-1.jpeg`: 8 candidate bands, all dropped; dominant reason
  `PITCH_LAYOUT_MISMATCH` with ratios r≈0.31–0.32 (half/harmonic pitch)
  and r≈2.23 — the registered pitch is inconsistent with the 48-column
  layout span.
- `…-angle-2.jpeg`: 12 bands dropped; global deskew measured only −0.20°
  (in-plane rotation is NOT the problem), then the same
  `PITCH_LAYOUT_MISMATCH` r≈0.31–0.48 pattern.

Stage attribution: failure occurs at **line-band layout validation /
local registration** — the perspective keystone makes the apparent glyph
pitch vary along the line, so no single-pitch registration satisfies the
span/48 layout constraint. It is NOT page-quadrilateral detection (none is
attempted; only rotation deskew exists), NOT unsafe labelling, NOT the
capture gate. The rejections are honest.

Is the perspective mild enough to support later? Yes, plausibly: in-plane
rotation is near zero and the bands ARE found; what is missing is a
perspective (keystone) rectification step before registration. A future
Reader adding page-quadrilateral estimation + homography rectification
should reasonably handle captures like these. They were correctly kept out
of the bank.

## 7. Extraction quality (six accepted captures)

| capture | lines used | lines dropped | pitch median (px) | pitch IQR | samples |
|---|---|---|---|---|---|
| std-1 (pages 1–3 blocks) | 24 | 14 | 21.41 | 0.18 | 1152 |
| std-2 | 12 | 10 | 20.59 | 0.06 | 576 |
| lowlight-1 | 12 | 10 | 28.88 | 0.11 | 576 |
| lowlight-2 | 12 | 7 | 30.32 | 0.15 | 576 |
| shadow-1 | 12 | 8 | 30.56 | 0.12 | 576 |
| shadow-2 | 12 | 10 | 29.95 | 0.07 | 576 |

Dropped "lines" are overwhelmingly harmonic/stray candidate bands
(`PITCH_LAYOUT_MISMATCH` at r≈0.31/0.32/0.57 — half-pitch and header/footer
text) — expected scanner behaviour, not lost calibration lines: every
capture yielded its full complement of true lines (24 for the 3-block page-1
capture std-1, 12 per single-block page-2 or per-page otherwise).
Unsafe-label rejections: 0 (labels come only from recorded corpus metadata;
the triple guard never fired after hints). Per-line phase/drift residuals
are not persisted by the extractor; pitch IQR (≤0.18 px) is the recorded
dispersion proxy and indicates tight registration on accepted lines.

**Copy 1 vs copy 2**: no comparison possible — all captures are copy 1.
The recorded copy1 deviations are exactly this: the Phase B plan called for
two physical copies; only copy 1 was photographed, and pages arrived as
paginated 3+1-block sheets (page metadata now recorded in the corpus
manifest). Pitch differences between std (~21 px) and lowlight/shadow
(~29–31 px) captures are camera-distance differences of the same print, and
are normalized by pitch-relative windowing.

## 8. Bridge RS funnel with the new bank (DEVELOPMENT_REPLAY only)

Instrumented read-only rerun of all 19 sheets (identical candidate-selection
rule to `read_frame`; byte accounting audited against T5 ground truth;
RS budget 2E+e ≤ 34). "c/e/w" = correct/erasure/confident-wrong over the
142 ground-truth token characters of the winning candidate.

| sheet | gate | cand | c | e | w | E | e(bytes) | 2E+e | RS | AEAD | category |
|---|---|---|---|---|---|---|---|---|---|---|---|
| baseline-0 S28 | RECAPTURE* | 4 | 0 | 142 | 0 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| baseline-0 S46 | ACCEPT | 1 | 1 | 121 | 20 | 2 | 81 | 85 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| bodyring-1 S43 | ACCEPT | 1 | 0 | 133 | 9 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| cliptear-1 S44 | ACCEPT | 0 | 1 | 118 | 23 | 5 | 78 | 88 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| coffee-2 S29 | RECAPTURE* | 4 | 0 | 127 | 15 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| coffee-2 S30 | RECAPTURE* | 0 | 40 | 54 | 48 | 22 | 44 | 88 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| crumple-1 S37 | RECAPTURE* | 2 | 1 | 140 | 1 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| crumple-2 S31 | RECAPTURE* | 2 | 1 | 137 | 4 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| crumple-2 S32 | RECAPTURE* | 3 | 0 | 142 | 0 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| edge-3 S42 | ACCEPT | 3 | 0 | 142 | 0 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| fade-3 S41 | RECAPTURE* | 0 | 2 | 137 | 3 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| fold-3 S38 | RECAPTURE* | 0 | 0 | 130 | 12 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| scratch-3 S39 | ACCEPT | 1 | 1 | 121 | 20 | 2 | 81 | 85 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| scuff-3 S40 | ACCEPT | 2 | 3 | 127 | 12 | 2 | 81 | 85 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| spanstain-1 S45 | RECAPTURE* | 2 | 1 | 131 | 10 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| water-2 S33 | RECAPTURE* | 3 | 1 | 132 | 9 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| water-2 S34 | RECAPTURE* | 1 | 1 | 104 | 37 | 11 | 72 | 94 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| water-3 S35 | RECAPTURE* | 3 | 0 | 142 | 0 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |
| water-3 S36 | RECAPTURE* | 2 | 1 | 141 | 0 | 0 | 83 | 83 | FAIL | not reached | RS_BUDGET_EXCEEDED |

\* gate verdicts marked RECAPTURE reflect the audit's blocking-gate
assessment of the raw capture; the recorded replay ran the development
funnel to depth as configured — no Bridge artifact was altered.

Summary — stated plainly, NOT as "19/19 reach RS":

- within RS budget (2E+e ≤ 34): **0 / 19**
- over RS budget: **19 / 19** (minimum 2E+e = 83, budget 34)
- RS-valid: **0**; AEAD-authenticated: **0**
- Token-region decided accuracy is catastrophic: across all sheets only 54
  of 142×19 = 2698 GT token characters are read correctly; 223 are decided
  wrong. Best sheet (S30) reads 40/142 correct but with 48 confident wrongs.

## 9. Pristine controls

**S28** (pristine, capture 1): capture gate verdict = **RECAPTURE**
(`LOW_SHARPNESS`: laplacian variance 6.7e-4 below floor;
`FOOTER_SIGNAL_TOO_WEAK`; page-boundary confidence 0.68). Run to depth it
still fails: winning candidate rank 4, 0/142 token chars decided,
e = 83 bytes (fully erased codeword), 2E+e = 83 > 34, RS FAIL, AEAD not
reached. S28's failure is at least partially explained by capture quality.

**S46** (pristine, capture 2): capture gate **ACCEPT** (sharpness 1.8e-3,
no glare, page confidence 0.85). Candidate rank 1. Token region:
**1 correct / 121 erasure / 20 confident wrong**; bytes E = 2, e = 81,
2E+e = 85 vs budget 34; RS FAIL; AEAD not reached.

This is the audit's central diagnostic: a clean, accepted, well-localized
pristine sheet yields 85% erasure and near-zero correct decisions **with
the real-print calibration bank**. Meanwhile the same bank scores 0.77
decided accuracy on held-out calibration captures. The bank therefore
transfers poorly across the **print/render generation gap between the
calibration sheet and the Bridge sheets** (different print run; glyph
appearance at footer pitch ~21 px differs enough that most cells fall below
conf 0.64 and the few decided ones are dominated by confusions). This is a
domain-shift failure of the calibration material, not a localization
failure (localization succeeded) and not RS math.

## 10. Comparison against the historical bank/path

Historical (task0 synthetic-template path) vs new calibration-bank replay,
where technically comparable (development replays of the same 19 captures;
historical files untouched):

| measure | historical path | new cal-run01 bank |
|---|---|---|
| funnel depth | 14 RS_BUDGET_EXCEEDED + 5 FOOTER_LOCALIZATION_FAIL | 19/19 RS stage (locator fix, not bank) |
| pristine S46 | FOOTER_LOCALIZATION_FAIL (never classified) | reaches RS; 1/142 correct; 2E+e = 85 |
| pristine S28 | RS_BUDGET_EXCEEDED, e = 83 | RS_BUDGET_EXCEEDED, e = 83 (unchanged) |
| RS-valid / authenticated | 0 / 0 | 0 / 0 (unchanged) |
| erasure mass | ~94.7% of classified cells erased | ~94.6% erased (unchanged) |
| confident-wrong (token region) | not measurable for the 5 locator-fail sheets | measured: 223 decided-wrong over 19 sheets |

Funnel-depth improvement is attributable to the v0.2.1 locator work, which
predates this bank. On the classifier axes the audit asks about —
confident-wrong rate, erasure rate, RS byte budget, authenticated
recovery — the new bank produced **no measurable improvement on Bridge
material**: erasures still saturate the codeword and no sheet moves toward
the RS budget.

## 11. Calibration adequacy verdict

**B. CALIBRATION BANK INADEQUATE — ADDITIONAL CALIBRATION REQUIRED**

Grounds: (1) pristine, gate-accepted S46 decodes essentially nothing with
the new bank (§9); (2) the Bridge byte-level audit (§8) shows every sheet at 2E+e ≥ 83
against the 34-unit budget (which allows at most 17 error bytes even with
zero erasures), and the 16% held-out confident-wrong rate is supporting
classifier-level evidence that decided outputs are unreliable; (3) no glyph class exceeds 69% held-out
accuracy and lowlight coverage collapses below 51%; (4) copy-level
generalization is unmeasured (single copy).

Specific additional physical calibration material required (not "more
data"):

1. **A calibration sheet printed in the same print run/pipeline as the
   Bridge (production-style) sheets, photographed straight-on at the
   production footer pitch (~21 px at capture)** — the S46 result shows the
   dominant failure is calibration↔production print domain shift, which no
   amount of extra captures of the current sheet will fix.
2. **At least 2 independent physical print copies** of that sheet
   (currently copy 1 only), to make leave-one-copy-out valid and expose
   copy-specific ink/toner variation.
3. **≥2 additional straight-on captures per lighting condition** (currently
   1 capture/page/condition), so capture-fold variance can be separated
   from condition effects.
4. **Better-exposed lowlight material** (current lowlight folds: 0.38/0.49
   decided accuracy, coverage <51%) — e.g. lowlight captures at 2 distinct
   exposure levels.
5. **Targeted extra samples for the weak confusable classes**
   c, 5, n, u, v, 6, g, 7, f, l (all ≤50% held-out correct), which drive
   the confusion head (n↔u, c↔3, t↔q, g↔q, 5↔8/9).
6. Mild-angle captures remain out of scope for the bank until a perspective
   rectification stage exists (§6); do not supply angled material for
   calibration purposes.

## 12. No-changes attestation

This audit changed no thresholds (0.64/0.02 untouched), rebuilt no bank
(`cal-run01-bank.npz` sha unchanged), modified no quality thresholds,
registration, image-specific logic, Bridge result files, or protocol code.
New files: this report, the audit JSON, and the read-only audit script.
