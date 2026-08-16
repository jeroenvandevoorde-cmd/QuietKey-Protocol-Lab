# Gate A Capture Spike

## Purpose

Empirical damage envelope for the CloakVault v3 footer token reader. This is
an informative input to Gate A1, not a Gate A1 acceptance run: it covers one
printer, one paper, and one phone camera.

Produced 16 August 2026 in an offline analysis container.

## Environment pins

- Python 3.12.3
- opencv-python-headless 4.13.0
- numpy 2.4.4
- tesseract 5.3.4

## Inputs

29 phone captures, 4032x3024 JPEG, EXIF orientation 6 (27 token sheets,
2 locate pages). The captures are not stored in this directory.

- Ground truth: `artifacts/cloakvault/spike/tokens.json`
- Reference decoder: `artifacts/cloakvault/interop/python/cloakvault_v3.py`

## Frozen reader operating point

- `conf_floor` 0.64
- `margin_floor` 0.02

## Rerun order

Run all from a directory containing the captures:

1. `sweep_harness2.py`
2. `t0free_harness.py`
3. `locate_reader.py`
4. `ocr_baseline.py`

## Headline results

| Path | Result |
| --- | --- |
| T0-selected path | 118/135 tokens decode |
| T0-free production path | 116/135 |
| Locate pages | 2/2 |
| Tesseract stock | 0/135 |
| Tesseract with charset whitelist | 2/135 |

## Rules

Files under `reports/` are immutable dated records. Corrections become new
addendum reports. A rerun that changes results requires a new report, never
an edit to an old one.
