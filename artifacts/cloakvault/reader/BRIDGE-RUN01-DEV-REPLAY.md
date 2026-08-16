# Bridge Run 01 — Reader v0.2 development replay (NOT Gate A evidence)

Status: **development/regression data only.** Bridge Run 01 is permanently
seen material (see `../spike/bridge/BRIDGE-RUN01-STATUS.md`); nothing here
is unseen confirmation, and no thresholds were tuned on these results.

* Profile: `spike-reader-v02-development.json` — sha256 `fb8972d98a9b458f3f6080b22d9d4204c6ab811b7e7b848f21135db495898da1`
* Profile status: DEVELOPMENT / NOT GATE-A1 / NOT PRODUCTION
* Corpus: 19 grayscale conversions (EXIF-orientation applied, /255) of the
  Bridge Run 01 JPEGs; npy corpus manifest sha256 `06145f601e35ddc920eb9ad43e124ec8bf37a114854dff9b81134913882e09fa`
* development_data flag in validator output: True

## Headline regression outcome

* **S28 (pristine start control, failed the original session gate):**
  `CAPTURE_QUALITY_REJECT` — reasons LOW_SHARPNESS + FOOTER_SIGNAL_TOO_WEAK
  (laplacian_variance 0.0007 vs floor; no footer band with credible
  periodicity found). Reader v0.2's acquisition-time quality gate would
  have demanded an immediate recapture instead of silently proceeding.
* **S46 (pristine end control, read successfully in the session):**
  quality `ACCEPT`, footer band located (periodicity 0.98, extent 1.00).

This is the intended v0.2 behaviour: the S28 failure mode is caught at
CAPTURE, explicitly, before any decode is attempted.

## Category counts (19 images)

{
  "CAPTURE_QUALITY_REJECT": 13,
  "FOOTER_LOCALIZATION_FAIL": 3,
  "RS_BUDGET_EXCEEDED": 3
}

## Per-image results

| capture | category | failing stage |
| --- | --- | --- |
| bridge-baseline-0-std-S28 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-baseline-0-std-S46 | FOOTER_LOCALIZATION_FAIL | FOOTER |
| bridge-bodyring-1-std-S43 | FOOTER_LOCALIZATION_FAIL | FOOTER |
| bridge-cliptear-1-std-S44 | FOOTER_LOCALIZATION_FAIL | FOOTER |
| bridge-coffee-2-std-S29 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-coffee-2-std-S30 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-crumple-1-std-S37 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-crumple-2-std-S31 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-crumple-2-std-S32 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-edge-3-std-S42 | RS_BUDGET_EXCEEDED | RS |
| bridge-fade-3-std-S41 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-fold-3-std-S38 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-scratch-3-std-S39 | RS_BUDGET_EXCEEDED | RS |
| bridge-scuff-3-std-S40 | RS_BUDGET_EXCEEDED | RS |
| bridge-spanstain-1-std-S45 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-water-2-std-S33 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-water-2-std-S34 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-water-3-std-S35 | CAPTURE_QUALITY_REJECT | CAPTURE |
| bridge-water-3-std-S36 | CAPTURE_QUALITY_REJECT | CAPTURE |

## Honest caveats

1. **Classification is not meaningful on real captures yet.** Reader v0.2
   carries no calibrated real-print glyph bank (a terminal-optics
   calibration item); cells classified against the synthetic development
   bank produce erasures/garbage and the pipeline fails closed at RS.
   The three `RS_BUDGET_EXCEEDED` results demonstrate fail-closed
   behaviour, not read failures of the print. No decode succeeded and
   none was expected.
2. `FOOTER_LOCALIZATION_FAIL` on three quality-ACCEPT portrait captures is
   a real v0.2 localization gap on full-page phone photos (small footer,
   large body text) — recorded as a development finding, not tuned away.
3. Raw JPEGs are kept untracked (they carry device EXIF/GPS); provenance
   is pinned by the raw-capture manifest below.

## Raw capture provenance (`bridge/captures/CAPTURE-MANIFEST.json`)

| file | sha256 |
| --- | --- |
| bridge-baseline-0-std-S28.jpeg | `71d2922c589020748bd58a6b27d62e8ab8c10804ccf4a8aa59af7b7f0239422c` |
| bridge-baseline-0-std-S46.jpeg | `bf1b1de98b23d7d4c3120968ce02e3c64ec49031b880309cc6c3581be08d4b8a` |
| bridge-bodyring-1-std-S43.jpeg | `260cdc3d1a2c52d880393d2aef7036e5aa1e071b73031ff08a82a84ec8ec85ef` |
| bridge-cliptear-1-std-S44.jpeg | `d514afb34ba8cf30e5fb749a5773b450cd14782d25d37fc871b7397bcbbc3a09` |
| bridge-coffee-2-std-S29.jpeg | `1eb17eedc1eba813f85d70db840c678c0d5528ac0da0c9d3efe95d3e0be480bb` |
| bridge-coffee-2-std-S30.jpeg | `865afae28f8e003cc75b4e3e5b7aaa4be4aed981bb875acf57ed53f6c18539bc` |
| bridge-crumple-1-std-S37.jpeg | `93e316a14037cad427c026d08c8194db2b428d835c4e49186dd959c6c46b2f67` |
| bridge-crumple-2-std-S31.jpeg | `f3c7114069fd514070026d7c3b0808a1e5a97f0c7d3e03f997103f2bf7d04541` |
| bridge-crumple-2-std-S32.jpeg | `7a6312a3fcabe3eb4b5d7ea46993ba87b5b02f39233aa69ff2755337c928bc1a` |
| bridge-edge-3-std-S42.jpeg | `4a93401add9c375174f93b7a13260157fd221f00813c50ee9fd13bf0f29a32c4` |
| bridge-fade-3-std-S41.jpeg | `da51e1883e523d77e666e96a1a7571170f08b027cdec3b555d9cb2975f2cf8c9` |
| bridge-fold-3-std-S38.jpeg | `d0252bf3de39fc9fe21226c5b3f305e68f8f656e5b0928c1bb79433676ee956e` |
| bridge-scratch-3-std-S39.jpeg | `cfd7159105d01d969e0b548334f349b6364490ef4295aa24900d903e99d4dddf` |
| bridge-scuff-3-std-S40.jpeg | `62f38006872eb7552c60a3efe892dad6b4f8c76d683671d50e09e29c5349e751` |
| bridge-spanstain-1-std-S45.jpeg | `fa400af0f0d8d645ad3fb534e9f24adf664275e88064ce83d44a4aa6782dd252` |
| bridge-water-2-std-S33.jpeg | `534c2eeca85041292399050b15c4c595507fbb45b251de08987186fea5a48b03` |
| bridge-water-2-std-S34.jpeg | `ded6a0c17cbc74bce16add04985d3d65dff690bec329147bf0b8204c0cca8a10` |
| bridge-water-3-std-S35.jpeg | `a6c61c52f749b502303c9998bf98fa3cee57ce3573f8c41611c473f87589c299` |
| bridge-water-3-std-S36.jpeg | `29ddbe80e0a802e6294c05a0818f732f51ced21579f5ec15f2545d9183c899ed` |
