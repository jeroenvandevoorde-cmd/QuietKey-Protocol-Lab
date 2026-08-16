# Reader v0.2 — Supported Synthetic Envelope (engineering tests only)

These bounds are demonstrated by `reader/tests/test_synthetic_registration.py`
on deterministic synthetic monospace lines (hash-glyph bank, cell pitch
8 px). They are engineering tests, NOT Gate A evidence, and transformations
were not artificially tuned to make every test pass — the envelope below is
what the current algorithms genuinely support.

| Transformation | Demonstrated envelope |
| --- | --- |
| Clean geometry | max center error < 1.5 px (< 0.2 cell) |
| Global perspective | top-edge shrink up to 6 %: pitch recovered within 0.8 px |
| Smooth horizontal phase drift | 3 px linear drift over ~48 cells: no accumulation ≥ half a cell by line end |
| Vertical line bow | 2 px sinusoidal bow followed by the low-order line path |
| Local fold + occlusion | 3 px fold and 24 px solid occlusion mid-line: clean left/right regions stay within 0.4–0.6 cell |
| Occlusion → erasures | occluded cells become `?` or stay correct; never confident wrong characters |
| Uneven illumination | 25 % multiplicative ramp: ≥ 44/48 cells correct, remainder erasures only |
| Determinism | identical inputs give identical models/centers |

Known limits (outside the demonstrated envelope):

* perspective beyond ~6 % top shrink is untested;
* fold displacements approaching half a cell pitch will alias;
* the classifier bank is synthetic — real print/camera glyph templates
  require separate calibration (terminal optics, Gate A1).
