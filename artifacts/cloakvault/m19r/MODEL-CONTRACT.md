# M19-R deterministic model and validation contract

Status: **DRAFT / NOT ACTIVE / Owner ratification required**. This document
describes the code in `synthetic_model.py`; it authorizes no generation.

## Pairing and operator order

The seed is SHA-256 over the registered domain, separator, fixed public master
seed, lineage, cell ordinal, and realization. Profile is deliberately absent,
so one lineage/cell/realization parameter record is reused byte-for-byte for all
three profiles. Locate geometry, when applicable, precedes the common integer
translate/shear, Q16 gain plus u8 offset, and integer box blur. The remaining
class operator then runs, followed by glare when the cell lighting is glare.

- baseline: no damage operator; dim multiplies the sampled gain by 3/4 and
  subtracts 24; glare adds the deterministic diagonal specular band.
- coffee: 1/3/6 cup-foot rings at C for levels 1/2/3.
- water: one filled pool at C with 7/11/16 mm radius.
- crumple: triangular-wave integer coordinate warp and 4/12 creases.
- edge: a 20 mm bottom notch centered at x=67 mm, 17/22/27 mm deep.
- fade: severity lightening across F and 4/8/12 abrasion strokes.
- fold: a two-tone vertical crease fixed at x=67 mm.
- scratch: 1/3/6 cuts; level 3 is three parallel and three perpendicular.
- scuff: 5/15/30 deterministic left-to-right 40 mm strokes within F. Forty
  millimetres maps to `round_half_up(40 * image_width / 210)` pixels; each
  start is sampled only where that full span ends inside F, so no stroke is
  clipped or shortened.
- locate: level 0 unchanged. Level 1 preserves the frozen 20-degree off-normal,
  15-degree clockwise rotation, and all-corners-in-frame facts with a candidate
  pinhole model. Its page plane tilts about the horizontal center line with the
  top edge nearer; virtual camera distance is two page heights and projected
  page scale is Q16 `41943` (64 percent of the frame). Those two exact candidate
  values still require the model-freeze ratification. Q16 constants are
  cos(20)=61584, sin(20)=22415,
  cos(15)=63299 and sin(15)=16962. The inverse projective raster map is
  nearest-neighbor, the outside field is white, and all four projected page
  corners remain inside the frame before the common bounded geometry.

All raster operations are u8 grayscale and integer-only. The box blur is an
exact clipped-area two-dimensional mean with one half-up division per output
pixel, evaluated by separable rolling sums in O(pixels) time. SHA-256 counter
output drives every bounded choice. There is no adaptive state or source of
entropy.

## Six validation families

Inputs are a clean render, a same-size observed image already in the declared
page coordinate system, and four Q16 page corners in top-left, top-right,
bottom-right, bottom-left order. F maps the exact millimetre rectangle
`x=[16,117.6165], y=[274.12,281.00]` with lower bounds floored, upper bounds
ceiled, lower-inclusive and upper-exclusive.

1. Geometry computes each corner's Euclidean error normalized by the page
   diagonal in Q16, then the integer-square-root RMS and maximum.
2. Damage placement uses a full-frame mask where absolute observed-minus-clean
   is at least 24. Its centroid is the half-up Q16 coordinate mean; footer
   overlap is changed pixels in F divided by all changed pixels.
3. Connectedness uses four-neighbor components on that mask and records the
   component count and half-up largest-component fraction.
4. Contrast/luminance sorts observed pixels in F and uses index
   `floor((n-1)*p)` for p05, p25, median, p75 and p95; IQR is p75-p25.
5. Blur/edge spectrum uses forward horizontal and vertical absolute gradients
   in F, recording normalized mean energy and the fraction at least 32.
6. Glare uses pixels in F whose observed value is at least 250 and whose signed
   increase from clean is at least 24, recording coverage and centroid.

An empty mask has centroid `(-1,-1)`, zero overlap, zero components, and zero
largest fraction. Capture 1 is the sole future anchor center for its cell.
Exactly three synthetic realization vectors are aggregated fieldwise using the
middle order statistic. There is no cross-cell pooling, trimming, missing-value
imputation, or tolerance adjustment. Both centroids absent passes presence;
only one absent yields a named mismatch. Every other comparison uses the exact
candidate bounds in `MODEL-FREEZE-DRAFT.json`; any named failure stops the
comparison without regeneration.

## Activation boundary

The only future path is
`artifacts/cloakvault/m19r/registrations/MODEL-FREEZE-ACTIVE.json`, schema
`QK-M19R-MODEL-FREEZE-ACTIVATION-V1`. A later code change must compile the
exact file SHA-256, Owner decision id, and Decision Log commit. The file must
then bind the exact draft, implementation, clean-render manifest, and payload
registry hashes and the narrow scope. All three compiled values are `None` in
this build, so no JSON file can activate it. The comparison writer is also
absent and must arrive only with that later change.
