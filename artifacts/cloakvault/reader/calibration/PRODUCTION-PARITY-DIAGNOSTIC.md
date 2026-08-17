# Production-Domain Parity Diagnostic — Tasks 1–3

Status: **DEVELOPMENT / ANALYSIS-ONLY** · frozen 0.64/0.02 untouched · no RS,
token-format, protocol, registration, or threshold changes · S46 never
enters any training material.

Companion artifacts:
- `reader/calibration/parity-diagnostic-cal-run01-vs-S46.json` (Task 2, from
  read-only `scripts/parity_diagnostic.py`)
- `reader/calibration/sheets/calibration-sheet-calsheet-production-v2-s20260817.html`
  + `.groundtruth.json` (Task 3, from `scripts/gen_calibration_sheet_v2.ts`)
- `reader/corpora/cal-run02-production-raw.json` (Task 8 provenance manifest)

---

## Task 1 — Production footer rendering path, traced

Production Recovery Document footer path (all verified in source):

- Token wrapping: `src/lib/codec/footer.ts` — `FOOTER_WRAP_WIDTH = 48`,
  `wrapToken` slices 48/48/46 for the 142-char token.
- Footer lines: `src/lib/pipeline.ts` `renderFooter` — line 1 is
  `https://arecipeforamaster.com/print?id=<first 48 token chars>`, middle
  lines raw, `&v=1` appended to the last token line, then a
  `Printed <date> · page 1 of 1` line.
- DOM: `src/pages/create.tsx` — footer `<div>` with classes
  `mt-8 pt-2 border-t border-gray-200 text-[10px] text-gray-500 font-mono
  break-all`; one `<div>` per line.
- Typography: `--app-font-mono: Menlo, monospace` (`src/index.css`); footer
  is 10px monospace, color `#6b7280`; document print style (verbatim
  `@media print` block): A4, 16mm margins, body Georgia 10.5pt,
  line-height 1.3. No footer-specific letter-spacing or weight.
- Print path: literal `window.print()` — browser print, no PDF library.
- Physical: Bridge campaign log records 100% scale (never fit-to-page),
  48-char line ≈ 77 mm (±2 mm), same printer/paper as spike. Printer
  make/model, paper brand, browser/OS, and actual installed-font fallback
  are NOT recorded anywhere (capture manifest fields deliberately null).

### Parity table (production/Bridge vs cal-run01 sheet)

| Property | Production/Bridge | cal-run01 (calsheet-v1) | Match? |
|---|---|---|---|
| Renderer code | `renderFooter`/`wrapToken` + create.tsx DOM + index.css, browser print | Python generator emitting hand-copied CSS values | **NO — appearance copied, code not reused** |
| Font family (CSS) | Menlo, monospace | Menlo, monospace | YES (CSS level) |
| Actual rasterized font | UNKNOWN (Menlo availability on printing machine unrecorded) | UNKNOWN (different machine possible) | **UNKNOWN — possible divergence** |
| Font size | 10px | 10px | YES |
| Font weight | default 400 | default 400 | YES |
| Letter spacing | none set | none set | YES |
| Line height | inherits print 1.3 | inherits body 1.3 | YES (nominal) |
| Monospace handling | `font-mono` var | same value, hand-copied | YES (value) |
| Line content | URL prefix line + raw lines + `&v=1` + `Printed …` context | pure 48-char glyph lines, no URL/context | **NO** |
| Token wrapping | `wrapToken` 48/48/46 | 48-char slices (reimplemented) | value-equal, code not shared |
| Layout context | footer after serif recipe body, `border-t`, `mt-8 pt-2` | labelled 12-line blocks + filler paragraphs | **NO** |
| Render engine / browser | UNKNOWN (unrecorded) | UNKNOWN (unrecorded) | UNKNOWN |
| HTML vs PDF | browser HTML print | browser HTML print | YES |
| Page scale / print scaling | A4 16mm, 100%, no fit-to-page | same instruction | YES (instructed) |
| Physical glyph pitch | 48 chars ≈ 77 mm ⇒ ≈1.60 mm/char | measured captures ≈1.5–1.6 mm/char (scale bar) | YES (approx) |
| Printer/paper/settings | unrecorded (campaign log: "same as spike") | unrecorded | UNKNOWN — cannot assert match |
| Ink density of physical print | see Task 2: measured contrast ~75 | measured contrast ~133 | **NO — Bridge print is much fainter** |

Flagged divergences: renderer-code reuse (none), URL/context lines,
layout context, actual rasterized font (unknown), printer/toner density
(measured to differ), plus all UNKNOWN rows above. MATCH was not inferred
anywhere evidence is absent.

## Task 2 — Visual-domain difference, quantified

Compared: 1728 clean cal-run01 std glyph windows vs 349 windows from the
pristine S46 footer after the exact audited localization (candidate rank 1)
— development material only, S46 used for analysis, never training.

**Finding A — registration harmonic failure on S46 (geometry problem).**
The production-context footer registers at pitch ≈ **10.9–11.3 px**, while
the locator's own layout pitch for the same lines is ≈ 21.0 px and the
calibration sheets register at ≈ 21.3 px. `register_line` on Bridge footer
lines locks the **half-pitch harmonic**, so classification windows cover
half-glyphs (this also explains S46's inflated 350 classified cells).
Diagnostic-only re-registration with the locator's pitch as the public
`pitch_hint` parameter (no code changed) restores pitch 21.0.

**Finding B — after fixing geometry, a print-density gap remains.**
Physical stats (medians):

| quantity | cal std | S46 (harmonic) | S46 (pitch-hinted) |
|---|---|---|---|
| ink fraction | 0.140 | 0.286 | 0.178 |
| glyph height frac | 0.650 | 0.870 | 0.614 |
| stroke width px | 1.91 | 1.91 | 1.91 |
| fg mean (ink) | 63.9 | 104.5 | 105.2 |
| bg mean | 197.5 | 182.0 | 182.3 |
| **contrast (bg−fg)** | **133.0** | 76.2 | **74.7** |
| gradient energy | 165.7 | 150.2 | 107.7 |

Under hinted registration the glyph *geometry* (height, width, stroke,
centroid) matches calibration closely — consistent with identical
typography — while **contrast is nearly halved**: the Bridge print/capture
is much fainter, and edge energy is correspondingly lower.

*Methodological caveat:* the S46 windows come from all cells of the selected
footer candidate lines (including URL-prefix, `&v=1`, and trailer cells),
while cal windows are labelled token glyphs; glyph-set mix and crop rules
therefore differ. Contrast/fg/bg statistics are largely insensitive to
glyph identity, but the comparison is not a matched-cell control. A
token-span-matched re-analysis is planned as part of the Task 5 transfer
evaluation, when the v2 span-aware extraction is built.

**Finding C — feature-space distances.** Top cosine vs the cal-run01 bank:
cal held-out medians ≈ 0.89–0.93 (acceptance audit); S46 median **0.553**
under production registration (87% of cells below the 0.64 floor) improving
to **0.654** with the pitch hint (still 48% below floor, median margin
0.022 at the 0.02 floor).

**Conclusion (Task 2):** S46 is clearly out-of-domain relative to cal-run01
through TWO stacked mechanisms:
1. half-pitch registration harmonic in the production footer context
   (extraction/geometry; established directly — pitch 11 vs layout 21,
   doubled cells, ~+0.10 median cosine when corrected);
2. a residual domain gap that persists with corrected geometry — the
   evidence points to print/capture density (halved contrast) as the main
   component, possibly compounded by unrecorded printer/font differences,
   but this attribution is provisional pending the matched-cell control
   above.
Neither mechanism is addressed by more captures of the v1 sheet.

## Task 3 — calibration-sheet-production-v2

Generated by `scripts/gen_calibration_sheet_v2.ts` (TypeScript so it can
IMPORT the production code rather than imitate it):

- reuses `wrapToken`/`FOOTER_WRAP_WIDTH` and `renderFooter` directly —
  every calibration block is a full production footer: URL first line,
  `&v=1` suffix, `Printed …` trailer;
- extracts the footer className VERBATIM from `src/pages/create.tsx` at
  generation time (generation fails if the source drifts) and maps exactly
  those utilities through a pinned, regression-tested table;
- copies the whole `@media print` block and `--app-font-mono` declaration
  VERBATIM from `src/index.css`;
- content: deterministic public seed 20260817, 16 footers × 142 chars =
  2272 glyphs, **exactly 71 per class** (all 32 Bech32 glyphs) including
  sentinel occurrences, interleaved with serif recipe filler so footers
  occupy multiple page positions;
- every token starts with the production sentinel `cv0` (imported from the
  production codec) so structural location sees real token prefixes; tokens
  are balanced calibration content, deliberately NOT RS-checksum-valid
  (decodability would preclude exact class balance — recorded in the
  ground truth `tokens_note`);
- known remaining work (deferred to Task 5, needs captures anyway): the
  reader's extraction must learn to consume the v2 `token_line_spans`
  schema (URL prefix / `&v=1` / trailer exclusion) — the v1 extractor's
  uniform `chars_per_line` assumption does not apply to production-style
  footers;
- same physical pitch (10px Menlo, A4 16mm, 100% scale instruction);
- ground truth records tokens, printed lines, per-line token spans, class
  counts, generator id, source commit `58cd280…`, and SHA-256 of all four
  production source files.

Regression tests added (Task 9): `src/lib/gen-calibration-v2.test.ts`
(renderer reuse, verbatim CSS, deterministic balance, source-hash pinning)
and `reader/tests/test_production_provenance.py` (Bridge hashes banned from
bank construction, S46 cannot enter calibration folds, two-copy manifest
rules, sheet provenance). All suites pass: 104 vitest, 93 reader pytest,
12 interop-python, cross-interop.

## Task 4 — physical checkpoint (OWNER ACTION)

STOP. Owner is asked to print
`reader/calibration/sheets/calibration-sheet-calsheet-production-v2-s20260817.html`:

- at least TWO physical copies, preferably two separate print jobs;
- same printer, paper, scale (100%, never fit-to-page) and settings as the
  Bridge Recovery Documents;
- per copy, three clean photographs: straight-on A, straight-on B, and one
  moderate ordinary-room-light capture;
- no damage, no intentional lowlight, no angles.

Tasks 5–6 (Copy1-only bank, Copy1→Copy2 transfer, S46 development replay,
A/B/C decision) begin only after these captures arrive.
