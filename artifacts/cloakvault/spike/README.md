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

Decode verification additionally requires the Python cryptography package;
use the interop test environment (the same venv as the interop pytest suite).

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
2. `verdict_analysis.py`
3. `t0free_harness.py`
4. `locate_reader.py`
5. `ocr_baseline.py`

The committed `t0free_harness.py`, `locate_reader.py` and `ocr_baseline.py`
hardcode the reference decoder path
`/tmp/qkcheck/artifacts/cloakvault/interop/python` as run; clone or symlink
the repository there to rerun them, while `verdict_analysis.py` takes
`--decoder-path` explicitly. These files are frozen as-run and must not be
edited.

Rounding note: the 6-decimal float rounding in sweep_records.json was
verified against the original full-precision records; it changes zero
threshold classifications across all 19,170 cells, so the JSON reproduces
the published token outcomes exactly.

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
