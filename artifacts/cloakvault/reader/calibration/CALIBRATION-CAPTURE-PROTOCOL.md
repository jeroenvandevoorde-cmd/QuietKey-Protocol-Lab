# Calibration Capture Protocol — Reader v0.2.1 (Phase A)

Status: DEVELOPMENT / NOT GATE-A1. This protocol produces the *calibration
corpus* for the real-print glyph bank. Calibration sheets carry no secret.

## What you need

- The generated calibration sheet HTML
  (`reader/calibration/sheets/calibration-sheet-<id>.html`) — print it from
  a browser at **100% scale** (no "fit to page", no shrink-to-margins).
- A ruler, to verify the printed 50 mm scale bar.
- The same printer/paper class you would use for real recovery documents.
- A phone camera (the same class of device used in Bridge Run 01 is fine).

## Printing

1. Print **at least 2 physical copies** of the sheet. Label them by hand in
   a corner OUTSIDE any glyph block: `copy-1`, `copy-2`, …
2. Measure the scale bar on every copy. If it is not 50 mm ± 1 mm, discard
   that copy and reprint. Do not capture an out-of-scale copy.

## Capture sessions

Capture **each copy under several conditions**. Minimum matrix per copy:

| condition id | description |
| --- | --- |
| `std`      | flat on a plain surface, indirect daylight, phone parallel, fill frame |
| `lowlight` | dimmer indoor light, no flash |
| `angle`    | phone tilted ~15° off-parallel |
| `shadow`   | partial soft shadow across the page |

Rules:

- Whole page in frame, all four corners visible.
- One image per (copy, condition) minimum; more is better.
- Use default camera app settings; do not edit, crop, or enhance images.
- File naming: `cal-<sheetid>-<copy>-<condition>-<n>.jpeg`
  e.g. `cal-calsheet-v1-s20260817-copy1-std-1.jpeg`.
- Place files in `reader/calibration/captures/` (gitignored — raw phone
  JPEGs carry EXIF/GPS and must not be committed).

## Manifest (required before any processing)

After copying the images in, run:

```
reader/.venv/bin/python scripts/capture_manifest.py \
  --dir reader/calibration/captures \
  --campaign-id cal-run01 \
  --corpus-id cal-run01-raw \
  --out reader/calibration/captures/CAPTURE-MANIFEST.json
```

The manifest (hashes only, no image data) IS committed. Fill in the
`printer_id`, `paper_id`, `camera_id`, `copy`, and `condition` fields per
image (the tool parses what it can from filenames; verify it).

## What happens next (Phase B — not before owner sign-off)

- Known-layout glyph extraction against the sheet's ground-truth JSON.
- Grouped-holdout evaluation (leave-one-capture-out at minimum; ideally
  leave-one-copy-out) — never evaluated on glyphs from a capture that
  contributed to the bank.
- Bank building with full provenance. Bridge Run 01 hashes are banned from
  bank provenance by an automated test.

## Explicit prohibitions

- Bridge Run 01 images are NOT calibration material. Never substitute them.
- Never tune the frozen operating point (conf 0.64 / margin 0.02) on Bridge
  data. A calibration-derived operating point, if any, goes in a NEW
  profile file marked DEVELOPMENT — existing profiles are never mutated.
