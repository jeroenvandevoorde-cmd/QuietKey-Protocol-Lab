"""Span-aware glyph extractor for production-path calibration sheets (v2).

The v2 sheet (calsheet-production-v2) renders full PRODUCTION footers:
    line 0:  https://<domain>/print?id=<token[0:48]>          (URL prefix + 48 token cells)
    line 1:  <token[48:96]>                                    (48 token cells)
    line 2:  <token[96:142]>&v=1                               (46 token cells + 4 suffix)
    line 3:  Printed <date> · page 1 of 1                      (context, never harvested)

Unlike v1 there is no uniform ``chars_per_line``: each line's expected cell
count comes from the ground truth's printed lines, and ONLY the token-span
cells (per ``token_line_spans``) are harvested as labelled samples. The URL
prefix, ``&v=1`` suffix, and Printed trailer are located and registered (they
constrain the line's cell grid) but excluded from labels.

Footer→ground-truth assignment uses corpus metadata (``page_footer_indices``,
verified against the unique tokens and recorded in the corpus manifest) plus
top-to-bottom order. The capture is REJECTED unless exactly the expected
number of complete footer groups is found — partial guesses never label.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from reader import structural_locator as SL
from reader.calibration.extract import GlyphSample, _alignment_score, _deskew, _text_bands
from reader.registration import register_line


def band_is_token_plausible(b, widths: list[int]) -> bool:
    """A band is token-plausible when its detected pitch is layout-consistent
    (or the known half-pitch harmonic of it) with ANY of the token line
    widths. Drops serif filler and the ~32-char Printed trailer (whose ratio
    lands between the accepted windows for all three widths)."""
    for n in widths:
        p_exp = (b.x1 - b.x0) / n
        r = b.pitch / p_exp if p_exp > 0 else 0.0
        if 0.85 < r < 1.2 or 1.8 < r < 2.2:
            return True
    return False


def _layout_distance(b, widths: list[int]) -> float:
    """How far the band's pitch is from exact layout consistency (r=1) for
    its best-matching expected width. Harmonic duplicates score worse."""
    best = float("inf")
    for n in widths:
        p_exp = (b.x1 - b.x0) / n
        if p_exp > 0:
            best = min(best, abs(b.pitch / p_exp - 1.0))
    return best


def dedupe_same_line_bands(tb: list, widths: list[int]) -> list:
    """Collapse duplicate detections of the SAME physical text line.

    Band detection sometimes reports one printed line twice: once at the
    true pitch and once as a 2x-pitch harmonic, a few rows apart with the
    same horizontal span. Keeping both would make a footer group 4 bands
    and reject it. Two row-sorted bands are duplicates when they are
    nearly touching vertically (gap < ~35% of a line height — observed
    duplicates sit ~0.15 line heights apart, distinct footer lines >1 line
    height), their horizontal spans overlap heavily AND are similar in
    length (a 48-char and an 87-char line never dedupe); the survivor is
    the more layout-consistent one.
    This is pure geometry — no ground-truth labels are consulted."""
    if not tb:
        return tb
    med_h = float(np.median([b.row_end - b.row_start for b in tb]))
    out = [tb[0]]
    for b in tb[1:]:
        prev = out[-1]
        gap = b.row_start - prev.row_end
        ov = min(b.x1, prev.x1) - max(b.x0, prev.x0)
        spans = sorted((b.x1 - b.x0, prev.x1 - prev.x0))
        min_span = max(1, spans[0])
        similar_span = spans[0] / max(1, spans[1]) > 0.8
        if gap < 0.35 * med_h and ov / min_span > 0.7 and similar_span:
            if _layout_distance(b, widths) < _layout_distance(prev, widths):
                out[-1] = b
        else:
            out.append(b)
    return out


def group_bands_by_spacing(tb: list) -> list[list]:
    """Split row-sorted token-plausible bands into vertically adjacent
    groups; footers are separated by filler paragraphs (larger gaps)."""
    heights = [b.row_end - b.row_start for b in tb]
    med_h = float(np.median(heights))
    groups: list[list] = [[tb[0]]]
    for b in tb[1:]:
        if b.row_start - groups[-1][-1].row_start > 2.2 * max(med_h * 1.6, 1.0):
            groups.append([b])
        else:
            groups[-1].append(b)
    return groups


def is_footer_group(grp: list, widths: list[int]) -> bool:
    """A group is a footer ONLY when it is EXACTLY the three token lines in
    reading order with the expected width-ratio pattern (line 0 the widest
    URL line). Any stray extra band inside the group's vertical range makes
    role-by-order ambiguous, so such groups are rejected wholesale —
    dropping is always preferred over mislabeling."""
    if len(grp) != 3:
        return False
    w = [b.x1 - b.x0 for b in grp]
    if w[0] != max(w):
        return False
    return (abs(w[1] / w[0] - widths[1] / widths[0]) < 0.12
            and abs(w[2] / w[0] - widths[2] / widths[0]) < 0.12)


@dataclass
class ExtractionResultV2:
    samples: list[GlyphSample] = field(default_factory=list)
    lines_used: int = 0
    lines_dropped: list[dict[str, Any]] = field(default_factory=list)
    n_footers: int = 0


def _register_expected(g: np.ndarray, band: SL.LineHypothesis, n_cells: int,
                       res: ExtractionResultV2):
    """Register one band against a KNOWN cell count (v1 dual-register rule:
    layout-consistent pitch pool first, alignment score second)."""
    span = float(band.x1 - band.x0)
    p_exp = span / n_cells
    r = band.pitch / p_exp if p_exp > 0 else 0.0
    if not (0.85 < r < 1.2 or 1.8 < r < 2.2):
        res.lines_dropped.append({"rows": [band.row_start, band.row_end],
                                  "reason": f"PITCH_LAYOUT_MISMATCH_r={r:.2f}_n={n_cells}"})
        return None
    pad_y = max(2, band.row_end - band.row_start)
    pad_x = int(round(2 * max(p_exp, 1.0)))
    strip = g[max(0, band.row_start - pad_y):band.row_end + pad_y,
              max(0, band.x0 - pad_x):band.x1 + pad_x]
    candidates = []
    for ph in (None, p_exp):
        try:
            candidates.append(register_line(strip, n_cells_hint=n_cells, pitch_hint=ph))
        except Exception:
            continue
    # Layout consistency is MANDATORY: a model whose pitch disagrees with
    # span/expected_chars would mislabel (half-pitch harmonic). No fallback —
    # dropping is always preferred over mislabeling.
    consistent = [m for m in candidates if 0.8 < m.pitch / p_exp < 1.25]
    if not consistent:
        res.lines_dropped.append({"rows": [band.row_start, band.row_end],
                                  "reason": "NO_LAYOUT_CONSISTENT_REGISTRATION"})
        return None
    model = max(consistent, key=lambda m: _alignment_score(strip, m))
    centers = model.centers()
    if len(centers) != n_cells:
        res.lines_dropped.append({"rows": [band.row_start, band.row_end],
                                  "reason": f"CELL_COUNT_{len(centers)}_EXPECTED_{n_cells}"})
        return None
    return band, model, strip


def extract_capture_v2(
    gray: np.ndarray,
    ground_truth: dict[str, Any],
    capture_sha256: str,
    page_footer_indices: list[int],
) -> ExtractionResultV2:
    """Extract labelled token glyphs from one v2 capture page.

    ``page_footer_indices`` is corpus-manifest metadata: the ground-truth
    footer indices printed on this page, in reading order.
    """
    res = ExtractionResultV2()
    sheet_id = ground_truth["sheet_id"]
    footers_gt = ground_truth["footers"]
    charset = set(ground_truth["alphabet"])
    for fi in page_footer_indices:
        tok = footers_gt[fi]["token"]
        if len(tok) != int(ground_truth["token_length"]) or not set(tok) <= charset:
            raise ValueError(f"ground-truth footer {fi} malformed; refusing to extract")

    g = np.asarray(gray, dtype=float)
    if g.max() > 1.5:
        g = g / 255.0

    # Expected token-line widths for this sheet (uniform across footers).
    f0 = footers_gt[page_footer_indices[0]]
    widths = [len(l) for l in f0["lines_as_printed"][:3]]  # e.g. [87, 48, 50]
    for fi in page_footer_indices:
        if [len(l) for l in footers_gt[fi]["lines_as_printed"][:3]] != widths:
            raise ValueError("footer line widths differ across ground truth; unsupported")

    def token_bands(bands: list[SL.LineHypothesis]) -> list[SL.LineHypothesis]:
        return [b for b in bands if band_is_token_plausible(b, widths)]

    bands_all = _text_bands(g, None)
    g_rot, skew = _deskew(g)
    if skew != 0.0:
        bands_rot = _text_bands(g_rot, None)
        if len(token_bands(bands_rot)) > len(token_bands(bands_all)):
            g, bands_all = g_rot, bands_rot
            res.lines_dropped.append({"rows": None, "reason": f"INFO_DESKEWED_{skew:.2f}_DEG"})
    bands_all.sort(key=lambda b: b.row_start)

    # Group candidate token bands into footers: a footer's 3 token lines are
    # consecutive at one line spacing; footers are separated by filler
    # paragraphs / trailer (larger gaps). Width ratio identifies line roles:
    # line 0 is the widest (URL), then 48, then 50-with-suffix — but widths
    # 48 vs 50 are near-identical in pixels, so role assignment inside a
    # group is BY ORDER, guarded by the width-ratio pattern check below.
    tb = token_bands(bands_all)
    if not tb:
        res.lines_dropped.append({"rows": None, "reason": "NO_TOKEN_BANDS: capture rejected"})
        return res
    tb = dedupe_same_line_bands(tb, widths)
    groups = group_bands_by_spacing(tb)

    footer_groups = [grp for grp in groups if is_footer_group(grp, widths)]
    for grp in groups:
        if not is_footer_group(grp, widths):
            res.lines_dropped.append({
                "rows": [grp[0].row_start, grp[-1].row_end],
                "reason": f"NON_FOOTER_GROUP_{len(grp)}_LINES"})

    if len(footer_groups) != len(page_footer_indices):
        res.lines_dropped.append({
            "rows": None,
            "reason": (f"FOOTER_GROUPS_{len(footer_groups)}_EXPECTED_"
                       f"{len(page_footer_indices)}: capture rejected")})
        res.samples = []
        return res
    res.n_footers = len(footer_groups)

    spans_by_line = {s["line"]: s for s in f0["token_line_spans"]}
    for grp, fi in zip(footer_groups, page_footer_indices):
        finfo = footers_gt[fi]
        token = finfo["token"]
        printed = finfo["lines_as_printed"]
        for li in range(3):
            reg = _register_expected(g, grp[li], widths[li], res)
            if reg is None:
                continue
            band, model, strip = reg
            centers = model.centers()
            y_mid = float(np.mean(model.y_at(centers)))
            pitch = float(model.pitch)
            wh = max(4, int(round(1.9 * pitch)))
            ww = max(4, int(round(1.3 * pitch)))
            span = spans_by_line[li]
            start = int(span["prefix_chars"])
            n_tok = int(span["token_chars"])
            tok_off = sum(spans_by_line[j]["token_chars"] for j in range(li))
            # cross-check GT internal consistency before labelling
            if printed[li][start:start + n_tok] != token[tok_off:tok_off + n_tok]:
                raise ValueError(f"ground-truth span mismatch footer {fi} line {li}")
            for k in range(n_tok):
                col = start + k
                cx = centers[col]
                x0 = int(round(cx - ww / 2))
                y0 = int(round(y_mid - wh / 2))
                win = strip[max(0, y0):y0 + wh, max(0, x0):x0 + ww]
                if win.size == 0:
                    continue
                res.samples.append(GlyphSample(
                    label=token[tok_off + k], window=win.copy(), pitch=pitch,
                    capture_sha256=capture_sha256, sheet_id=sheet_id,
                    block=fi, line=fi * 4 + li, col=col))
            res.lines_used += 1
    return res
