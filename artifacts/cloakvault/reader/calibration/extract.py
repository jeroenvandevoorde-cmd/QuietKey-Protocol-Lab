"""Known-layout glyph extractor (Reader v0.2.1, Task 8).

Given a capture of a calibration sheet and the sheet's ground-truth JSON,
harvest labelled glyph windows. Calibration is the ONE place where the
layout is known a priori (blocks × lines × 48 chars, Bech32 charset), so
extraction may use that knowledge — but it still reuses the reader's own
structural machinery (page segmentation, band detection, registration),
never wrapper constants.

Output: per-capture list of GlyphSample records (window pixels + label +
provenance) plus per-line diagnostics. Lines whose registration does not
yield exactly chars_per_line cells are DROPPED with a recorded reason —
never guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from reader import structural_locator as SL
from reader.registration import register_line


@dataclass
class GlyphSample:
    label: str
    window: np.ndarray          # grayscale window, raw capture scale
    pitch: float
    capture_sha256: str
    sheet_id: str
    block: int                  # 0-based block index
    line: int                   # 0-based line index within sheet
    col: int                    # 0-based char column


@dataclass
class ExtractionResult:
    samples: list[GlyphSample] = field(default_factory=list)
    lines_used: int = 0
    lines_dropped: list[dict[str, Any]] = field(default_factory=list)


def _text_bands(gray: np.ndarray) -> list[SL.LineHypothesis]:
    """All monospace-scored text bands on the page (full height)."""
    r0, r1, c0, c1, _conf = SL.page_region(gray)
    ins_r = max(2, (r1 - r0) // 80)
    ins_c = max(2, (c1 - c0) // 80)
    r0i, r1i, c0i, c1i = r0 + ins_r, r1 - ins_r, c0 + ins_c, c1 - ins_c
    page = gray[r0i:r1i, c0i:c1i]
    ph, pw = page.shape
    k = max(9, pw // 60)
    env = SL._box_blur(SL._gray_close(page, k), max(3, k // 2))
    ink = np.clip(1.0 - page / np.clip(env, 1e-3, None), 0, 1)
    return SL._detect_bands(ink, r0i, c0i, c1i, ph)


def extract_capture(
    gray: np.ndarray,
    ground_truth: dict[str, Any],
    capture_sha256: str,
) -> ExtractionResult:
    """Extract labelled glyphs from one calibration capture.

    Matching strategy: the sheet has blocks*lines_per_block glyph lines of
    exactly chars_per_line monospace cells. Bands are filtered to those
    whose registered cell count equals chars_per_line and whose pitch is
    consistent with the page-wide median glyph pitch; surviving bands are
    matched to ground-truth lines IN READING ORDER. If the count does not
    match the sheet's line count exactly, the capture is rejected (partial
    line-to-label guesses would poison the bank).
    """
    chars_per_line = int(ground_truth["chars_per_line"])
    lines_gt: list[str] = list(ground_truth["lines"])
    sheet_id = ground_truth["sheet_id"]
    lpb = int(ground_truth["lines_per_block"])

    # Ground truth must be internally consistent BEFORE any pixel work:
    # a malformed/truncated line would silently shift label assignment.
    charset = set(ground_truth.get("charset", "")) or None
    for i, text in enumerate(lines_gt):
        if len(text) != chars_per_line:
            raise ValueError(
                f"ground truth line {i} has {len(text)} chars, expected "
                f"{chars_per_line}; refusing to extract")
        if charset is not None and not set(text) <= charset:
            raise ValueError(f"ground truth line {i} contains chars outside declared charset")

    res = ExtractionResult()
    g = np.asarray(gray, dtype=float)
    if g.max() > 1.5:
        g = g / 255.0

    bands = _text_bands(g)
    registered: list[tuple[SL.LineHypothesis, Any, np.ndarray, float]] = []
    for band in bands:
        pad_y = max(2, band.row_end - band.row_start)
        pad_x = int(round(2 * max(band.pitch, 1.0)))
        strip = g[max(0, band.row_start - pad_y):band.row_end + pad_y,
                  max(0, band.x0 - pad_x):band.x1 + pad_x]
        try:
            model = register_line(strip)
        except Exception as exc:  # registration is allowed to fail per band
            res.lines_dropped.append({
                "rows": [band.row_start, band.row_end],
                "reason": f"REGISTRATION_ERROR:{type(exc).__name__}",
            })
            continue
        centers = model.centers()
        if len(centers) != chars_per_line:
            res.lines_dropped.append({
                "rows": [band.row_start, band.row_end],
                "reason": f"CELL_COUNT_{len(centers)}_EXPECTED_{chars_per_line}",
            })
            continue
        registered.append((band, model, strip, float(model.pitch)))

    # Reading-order assignment is only safe if the surviving bands are a
    # homogeneous set (one print pitch): a stray non-sheet line that happens
    # to register 48 cells would shift every subsequent label.
    if registered:
        med_pitch = float(np.median([p for *_, p in registered]))
        outliers = [(b.row_start, b.row_end) for b, _, _, p in registered
                    if abs(p - med_pitch) > 0.2 * med_pitch]
        if outliers:
            res.lines_dropped.append({
                "rows": None,
                "reason": f"PITCH_INCONSISTENT_BANDS_{outliers}: capture rejected",
            })
            res.samples = []
            return res

    if len(registered) != len(lines_gt):
        res.lines_dropped.append({
            "rows": None,
            "reason": (
                f"LINE_COUNT_{len(registered)}_EXPECTED_{len(lines_gt)}: "
                "capture rejected — cannot assign labels safely"),
        })
        res.samples = []
        return res

    registered.sort(key=lambda t: t[0].row_start)
    for li, ((band, model, strip, pitch), text) in enumerate(zip(registered, lines_gt)):
        centers = model.centers()
        y_mid = float(np.mean(model.y_at(centers)))
        wh = max(4, int(round(1.9 * pitch)))
        ww = max(4, int(round(1.3 * pitch)))
        for col, (cx, label) in enumerate(zip(centers, text)):
            x0 = int(round(cx - ww / 2))
            y0 = int(round(y_mid - wh / 2))
            win = strip[max(0, y0):y0 + wh, max(0, x0):x0 + ww]
            if win.size == 0:
                continue
            res.samples.append(GlyphSample(
                label=label, window=win.copy(), pitch=pitch,
                capture_sha256=capture_sha256, sheet_id=sheet_id,
                block=li // lpb, line=li, col=col,
            ))
        res.lines_used += 1
    return res
