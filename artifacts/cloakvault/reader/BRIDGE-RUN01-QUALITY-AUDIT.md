# Bridge Run 01 — capture-quality reject audit (Reader v0.2.1, Task 2)

Status: **DEVELOPMENT HEURISTIC — NOT GATE A1.** All thresholds below are
development heuristics set during v0.2 on synthetic + spike material; none
were tuned on Bridge data. Bridge Run 01 is permanently seen development
data; this audit is diagnostic documentation, not validation.

Machine-readable results: `BRIDGE-RUN01-QUALITY-AUDIT.json`
(19 images: 6 ACCEPT / 13 RECAPTURE).

## Metrics, what they physically detect, and evidence

### 1. `LOW_SHARPNESS` — laplacian variance below floor

- **Physical failure detected:** optical defocus / motion blur / camera
  shake. Blur destroys the high-frequency stroke edges the classifier
  needs; a blurred glyph is unrecoverable no matter how good the bank is.
- **Direction:** laplacian variance too LOW.
- **Threshold:** `sharpness_min_laplacian_var` from the active profile
  (development heuristic; set from spike-era distributions).
- **Fired on (11):** S28 S29 S30 S31 S32 S33 S34 S35 S36 S37 S38.
- **Evidence this is capture, not damage:** S28 is the *pristine* start
  control — physically undamaged paper — and still fails on sharpness.
  Its session-time read also failed, and v0.2's gate catches it at
  CAPTURE time with an explicit recapture demand instead of a silent
  downstream decode failure.

### 2. `FOOTER_SIGNAL_TOO_WEAK` — no credible periodic footer band

- **Physical failure detected:** the token block's monospace periodicity
  is not detectable anywhere on the page — combination of blur, low
  contrast, fade, or lighting that flattens the glyph comb signal.
- **Direction:** best footer-band comb score too LOW.
- **Threshold:** development heuristic on the band comb score (same
  family as the locator's `_MIN_COMB`), from the profile's
  `capture_quality` block.
- **Fired on (6):** S28 S30 S37 S38 S41 S45.
- **Evidence:** on S41 (fade-3) the print itself is faded — footer comb
  collapses while page-level sharpness is marginal; on S45 (spanstain)
  the stain suppresses band contrast across the token block's x-span.

## Interpretation guardrails

- A RECAPTURE verdict means "this image cannot support a read attempt" —
  it deliberately does NOT distinguish camera fault from paper damage in
  every case (Task 19 refines the reporting distinction; the funnel keeps
  them as CAPTURE_QUALITY_REJECT either way).
- 11/19 low-sharpness images in one session says the capture protocol
  (holding distance, focus tap, lighting) dominates the failure budget —
  see the capture guidance note (`reader/UX-CAPTURE-GUIDANCE.md`).
- No threshold in this audit may be re-tuned against Bridge Run 01 to
  "fix" its numbers; that is the leakage the corpus manifest flags forbid.
