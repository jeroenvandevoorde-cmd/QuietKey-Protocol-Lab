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
    n_groups: int = 0  # block groups seen on the page (after stray removal)


def _deskew(gray: np.ndarray) -> tuple[np.ndarray, float]:
    """Rotate so the paper's left edge is vertical.

    Row-band detection assumes near-horizontal lines; a hand-held angled
    capture tilts them enough to smear the row profile. The paper/table
    boundary gives a robust global angle: fit the leftmost paper column
    per row, rotate by the median slope. Returns (image, degrees applied).
    """
    from PIL import Image as _Image
    # Projection-profile method on a downscale: the correct rotation makes
    # text rows maximally distinct, i.e. maximizes the variance of the
    # row-mean ink profile. Robust to keystone/perspective (uses the text
    # itself, not the paper edge).
    small = np.asarray(_Image.fromarray(
        (np.clip(gray, 0, 1) * 255).astype(np.uint8)).reduce(4),
        dtype=np.float64) / 255.0
    dark = np.clip(float(np.median(small)) - small, 0.0, None)
    im_s = _Image.fromarray((np.clip(dark / max(dark.max(), 1e-9), 0, 1) * 255).astype(np.uint8))

    def sharpness(a: float) -> float:
        arr = np.asarray(im_s.rotate(-a, resample=_Image.BILINEAR),
                         dtype=np.float64)
        prof = arr.mean(axis=1)
        return float(np.var(np.diff(prof)))

    coarse = max(np.arange(-6.0, 6.01, 0.5), key=sharpness)
    angle = float(max(np.arange(coarse - 0.5, coarse + 0.51, 0.1), key=sharpness))
    if abs(angle) < 0.15:
        return gray, 0.0
    im = _Image.fromarray((np.clip(gray, 0, 1) * 255).astype(np.uint8))
    rot = im.rotate(-angle, resample=_Image.BILINEAR,
                    fillcolor=int(np.median(gray) * 255))
    return np.asarray(rot, dtype=np.float64) / 255.0, angle


def _text_bands(gray: np.ndarray,
                chars_per_line: int | None = None) -> list[SL.LineHypothesis]:
    """All monospace-scored text bands on the page (full height).

    The locator's `_detect_bands` uses a rolling-median baseline sized for
    ISOLATED few-line blocks (a token footer); on a dense calibration sheet
    (12-line blocks, ~60% row duty cycle) the median tracks the text itself
    and suppresses every line. Calibration knows the layout a priori, so
    band detection here is simpler and denser: Otsu threshold on the
    smoothed row-ink profile, contiguous runs, then the locator's own
    per-band monospace scoring (`_score_band`) — which still rejects serif
    paragraphs, headers, and the scale bar.
    """
    # Paper region from per-row/column MEDIAN brightness (robust to text and
    # to a dark table filling the border; the locator's log-Otsu page mask
    # can claim the whole frame when the table is bright).
    colmed = np.median(gray, axis=0)
    rowmed = np.median(gray, axis=1)
    cid = np.where(colmed > SL._otsu_threshold(colmed))[0]
    rid = np.where(rowmed > SL._otsu_threshold(rowmed))[0]
    if cid.size == 0 or rid.size == 0:
        return []
    r0i, r1i, c0i, c1i = int(rid[0]), int(rid[-1]) + 1, int(cid[0]), int(cid[-1]) + 1
    page = gray[r0i:r1i, c0i:c1i]
    ph, pw = page.shape
    k = max(9, pw // 60)
    env = SL._box_blur(SL._gray_close(page, k), max(3, k // 2))
    ink = np.clip(1.0 - page / np.clip(env, 1e-3, None), 0, 1)

    # Row score = FRACTION of columns with strong ink, not mean ink: the
    # glyph block spans only part of the page width, and a full-width mean
    # dilutes dense-but-narrow lines below a global threshold.
    score = SL._box_blur_1d((ink > 0.35).mean(axis=1), 3)
    thr = max(SL._otsu_threshold(score), 0.005)
    on = score > thr
    max_h = max(6, ph // 20)

    def cal_band(s: int, e: int) -> SL.LineHypothesis | None:
        """Band scoring for the known-layout sheet. The locator's
        `_ink_span` takes OUTERMOST threshold crossings, which right-edge
        shading noise inflates to the full page width; here the span is the
        longest sustained ink run instead (a glyph line is one contiguous
        48-char block, no word gaps)."""
        colprof = ink[s:e, :].mean(axis=0)
        sm = SL._box_blur_1d(colprof, 9)
        t = 0.3 * float(np.percentile(sm, 98))
        mask = sm > t
        gap_tol = max(20, pw // 50)
        segs: list[list[int]] = []
        idx = np.where(mask)[0]
        if idx.size == 0:
            return None
        for x in idx:
            if segs and x - segs[-1][1] <= gap_tol:
                segs[-1][1] = x
            else:
                segs.append([x, x])
        a, b = max(segs, key=lambda ab: ab[1] - ab[0])
        b += 1
        if b - a < 32:
            return None
        comb, pitch = SL._comb_and_pitch(colprof[a:b])
        if comb < SL._MIN_COMB or pitch <= 0:
            return None
        return SL.LineHypothesis(row_start=r0i + s, row_end=r0i + e,
                                 x0=c0i + a, x1=c0i + b,
                                 pitch=pitch, comb=comb, detected=True)

    out: list[SL.LineHypothesis] = []
    start = None
    for i, v in enumerate(list(on) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            s, e = start, i
            start = None
            if 2 <= e - s <= max_h:
                h = cal_band(s, e)
                if h is not None:
                    out.append(h)
    out.sort(key=lambda l: l.row_start)
    if chars_per_line is None:
        return out

    # ── layout-aware gap filling ────────────────────────────────────────
    # Thresholded row scores miss the occasional faint line (lighting,
    # shadow). The block's OWN line spacing predicts where a missing line
    # must be, so re-score exactly those row windows without the row-score
    # gate (cal_band's span/comb checks still apply).
    def layout_ok(b: SL.LineHypothesis) -> bool:
        p_exp = (b.x1 - b.x0) / chars_per_line
        r = b.pitch / p_exp if p_exp > 0 else 0.0
        return 0.85 < r < 1.2 or 1.8 < r < 2.2

    glyph = [b for b in out if layout_ok(b)]
    if len(glyph) < 4:
        return out
    heights = [b.row_end - b.row_start for b in glyph]
    med_h = float(np.median(heights))
    gaps = np.diff([b.row_start for b in glyph])
    intra = gaps[gaps < 3 * med_h]
    if intra.size == 0:
        return out
    d = float(np.median(intra))  # within-block line spacing

    def try_at(rs: float) -> SL.LineHypothesis | None:
        """Best layout-plausible band near the predicted row (spacing
        prediction is approximate; search a third of a line spacing each
        way and keep the highest-comb candidate)."""
        best = None
        for off in range(-int(d / 3), int(d / 3) + 1, 3):
            s = int(round(rs)) + off - r0i
            e = s + int(round(med_h))
            if s < 0 or e > ph:
                continue
            h = cal_band(s, e)
            if h is not None and layout_ok(h) and (best is None or h.comb > best.comb):
                best = h
        return best

    added = True
    while added:
        added = False
        glyph.sort(key=lambda b: b.row_start)
        # interior gaps ≈ k*d (k ≥ 2) inside a block
        for a, b in zip(glyph, glyph[1:]):
            gap = b.row_start - a.row_start
            k_f = gap / d
            if 1.7 < k_f < 3.4:  # 1 or 2 missing lines; larger = block gap
                cand = try_at(a.row_start + d)
                if cand is not None and all(
                        min(cand.row_end, o.row_end) - max(cand.row_start, o.row_start) <= 0
                        for o in glyph):
                    glyph.append(cand)
                    added = True
        if added:
            continue
        # extend one line above the first / below the last glyph line
        glyph.sort(key=lambda b: b.row_start)
        for rs in (glyph[0].row_start - d, glyph[-1].row_start + d):
            cand = try_at(rs)
            if cand is not None and all(
                    min(cand.row_end, o.row_end) - max(cand.row_start, o.row_start) <= 0
                    for o in glyph):
                glyph.append(cand)
                added = True

    merged = {(b.row_start, b.row_end): b for b in out}
    merged.update({(b.row_start, b.row_end): b for b in glyph})
    res = sorted(merged.values(), key=lambda b: b.row_start)
    return res


def extract_capture(
    gray: np.ndarray,
    ground_truth: dict[str, Any],
    capture_sha256: str,
    block_hint: int | None = None,
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
    def _layout_ok_count(bs: list[SL.LineHypothesis]) -> int:
        n = 0
        for b in bs:
            p_exp = (b.x1 - b.x0) / chars_per_line
            r = b.pitch / p_exp if p_exp > 0 else 0.0
            if 0.85 < r < 1.2 or 1.8 < r < 2.2:
                n += 1
        return n

    # Deskew helps genuinely tilted captures but the interpolation can hurt
    # already-straight ones; keep whichever variant yields more
    # layout-plausible glyph bands.
    bands = _text_bands(g, chars_per_line)
    g_rot, skew_deg = _deskew(g)
    if skew_deg != 0.0:
        bands_rot = _text_bands(g_rot, chars_per_line)
        if _layout_ok_count(bands_rot) > _layout_ok_count(bands):
            g, bands = g_rot, bands_rot
            res.lines_dropped.append({
                "rows": None,
                "reason": f"INFO_DESKEWED_{skew_deg:.2f}_DEG",
            })
    registered: list[tuple[SL.LineHypothesis, Any, np.ndarray, float]] = []
    for band in bands:
        # Known layout: a glyph line is exactly chars_per_line cells across
        # its ink span, so the expected pitch is span/chars_per_line. Accept
        # the band only if its measured comb pitch agrees directly or as the
        # factor-2 harmonic (fine glyph strokes often lock autocorrelation
        # onto half-pitch); everything else (headers, serif paragraphs,
        # title, scale bar) is dropped here.
        span = float(band.x1 - band.x0)
        p_exp = span / chars_per_line
        r = band.pitch / p_exp if p_exp > 0 else 0.0
        if not (0.85 < r < 1.2 or 1.8 < r < 2.2):
            res.lines_dropped.append({
                "rows": [band.row_start, band.row_end],
                "reason": f"PITCH_LAYOUT_MISMATCH_r={r:.2f}",
            })
            continue
        pad_y = max(2, band.row_end - band.row_start)
        pad_x = int(round(2 * max(p_exp, 1.0)))
        strip = g[max(0, band.row_start - pad_y):band.row_end + pad_y,
                  max(0, band.x0 - pad_x):band.x1 + pad_x]
        try:
            # Register twice — autocorrelation pitch (sub-pixel accurate
            # when it locks the true pitch, e.g. clean synthetic renders)
            # and the layout pitch span/48 (robust when autocorrelation
            # locks a harmonic, common on real photos). Keep whichever
            # model actually aligns cells with ink.
            candidates = []
            for ph_hint in (None, p_exp):
                try:
                    m = register_line(strip, n_cells_hint=chars_per_line,
                                      pitch_hint=ph_hint)
                except Exception:
                    continue
                candidates.append(m)
            if not candidates:
                raise ValueError("registration failed for both pitch modes")
            # The band already passed the layout-pitch plausibility check,
            # so a model whose registered pitch contradicts the layout is
            # a harmonic/subharmonic lock — never preferable, even if its
            # cell-alignment score edges ahead (half-pitch centers still
            # touch ink). Filter to layout-consistent models first.
            consistent = [m for m in candidates if 0.8 < m.pitch / p_exp < 1.25]
            pool = consistent or candidates
            model = max(pool, key=lambda m: _alignment_score(strip, m))
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
        # Hint-registered cells must actually contain ink: an accidental
        # non-glyph band forced to chars_per_line cells would have many
        # empty cells and must not survive to label assignment.
        ink_strip = np.clip(np.median(strip) - strip, 0, None)
        mass = ink_strip.sum(axis=0)
        empty = 0
        for cx in centers:
            a, b = int(round(cx - p_exp / 2)), int(round(cx + p_exp / 2))
            if a < 0 or b > mass.size or mass[a:b].sum() < 0.05 * mass.mean() * p_exp:
                empty += 1
        if empty > chars_per_line // 10:
            res.lines_dropped.append({
                "rows": [band.row_start, band.row_end],
                "reason": f"EMPTY_CELLS_{empty}_OF_{chars_per_line}",
            })
            continue
        registered.append((band, model, strip, float(model.pitch)))

    # Reading-order assignment is only safe if the surviving bands are a
    # homogeneous set (one print pitch): a stray non-sheet line that happens
    # to register 48 cells would shift every subsequent label.
    if registered:
        med_pitch = float(np.median([p for *_, p in registered]))
        outliers = [t for t in registered
                    if abs(t[3] - med_pitch) > 0.2 * med_pitch]
        for b, *_ in outliers:
            res.lines_dropped.append({
                "rows": [b.row_start, b.row_end],
                "reason": "PITCH_OUTLIER_VS_PAGE_MEDIAN",
            })
        registered = [t for t in registered if t not in outliers]

    # ── per-block label assignment ──────────────────────────────────────
    # A physical print may paginate: trailing blocks spill onto a second
    # page absent from the capture (observed with cal-run01: block 4 of 4
    # printed on page 2). Assignment is therefore PER BLOCK, and only under
    # geometric anchors that make a silent block-index shift impossible:
    #   1. ≥ 2 block groups on the page (spacing is otherwise unmeasurable);
    #   2. inter-group spacing consistent (a wholly missed MIDDLE block
    #      would show up as a double gap);
    #   3. the first group sits within one block spacing of the topmost
    #      detected content (a wholly missed FIRST block would not);
    #   4. only groups with exactly lines_per_block lines are used
    #      (a partial block cannot map its lines to labels safely).
    if not registered:
        res.lines_dropped.append({
            "rows": None,
            "reason": "LINE_COUNT_0: capture rejected — no registered lines",
        })
        res.samples = []
        return res

    registered.sort(key=lambda t: t[0].row_start)

    # Complete-page fast path: every ground-truth line was registered, so
    # sequential assignment is unambiguous regardless of how (or whether)
    # blocks are visually separated. This also covers synthetic renders
    # with no inter-block gap.
    if len(registered) == len(lines_gt) and block_hint is None:
        for bi in range(len(lines_gt) // lpb):
            _emit_block(res, registered[bi * lpb:(bi + 1) * lpb], bi,
                        lines_gt, lpb, capture_sha256, sheet_id)
        return res

    starts = [t[0].row_start for t in registered]
    med_h = float(np.median([t[0].row_end - t[0].row_start for t in registered]))
    gaps = np.diff(starts)
    intra = gaps[gaps < 3 * med_h] if gaps.size else np.array([])
    if intra.size == 0:
        res.lines_dropped.append({
            "rows": None,
            "reason": (f"LINE_COUNT_{len(registered)}_EXPECTED_{len(lines_gt)}"
                       "_NO_INTRA_BLOCK_SPACING: capture rejected — cannot group blocks"),
        })
        res.samples = []
        return res
    d = float(np.median(intra))

    groups: list[list[tuple[SL.LineHypothesis, Any, np.ndarray, float]]] = [[registered[0]]]
    for t in registered[1:]:
        if t[0].row_start - groups[-1][-1][0].row_start > 2.5 * d:
            groups.append([t])
        else:
            groups[-1].append(t)

    # Stray bands (a header fragment, a footer sliver) form tiny "groups"
    # of their own; left in place they would consume a block index and
    # silently shift every later block's labels. A real block group has
    # lines_per_block lines (possibly a few missed); anything under half
    # that is a stray, dropped from indexing with a recorded reason.
    strays = [grp for grp in groups if len(grp) < max(2, lpb // 2)]
    for grp in strays:
        res.lines_dropped.append({
            "rows": [grp[0][0].row_start, grp[-1][0].row_end],
            "reason": f"STRAY_GROUP_{len(grp)}_LINES",
        })
    groups = [grp for grp in groups if grp not in strays]
    res.n_groups = len(groups)
    if not groups:
        res.lines_dropped.append({"rows": None,
                                  "reason": "NO_BLOCK_GROUPS: capture rejected"})
        res.samples = []
        return res

    n_blocks_gt = len(lines_gt) // lpb

    # `block_hint`: caller-supplied pagination knowledge (e.g. "this
    # capture is page 2 of a print that paginated 3+1, so its single block
    # is block index 3"). The hint must come from corpus-level evidence
    # (sibling captures of the SAME physical print showing the leading
    # blocks), never from a guess; it is only honoured when the page shows
    # EXACTLY one block group — any other geometry contradicts the premise
    # and rejects the capture instead.
    if block_hint is not None:
        if not (0 <= block_hint < n_blocks_gt):
            raise ValueError(f"block_hint {block_hint} out of range")
        if len(groups) != 1:
            res.lines_dropped.append({
                "rows": None,
                "reason": (f"BLOCK_HINT_{block_hint}_BUT_{len(groups)}_GROUPS:"
                           " capture rejected — hint contradicts page"),
            })
            res.samples = []
            return res
        grp = groups[0]
        if len(grp) != lpb:
            res.lines_dropped.append({
                "rows": [grp[0][0].row_start, grp[-1][0].row_end],
                "reason": f"INCOMPLETE_BLOCK_{block_hint}_LINES_{len(grp)}_EXPECTED_{lpb}",
            })
            res.samples = []
            return res
        _emit_block(res, grp, block_hint, lines_gt, lpb,
                    capture_sha256, sheet_id)
        return res

    reject = None
    if len(groups) < 2:
        reject = f"BLOCK_GROUPS_{len(groups)}: need >=2 groups to anchor block indices"
    elif len(groups) > n_blocks_gt:
        reject = f"BLOCK_GROUPS_{len(groups)}_EXCEED_GT_{n_blocks_gt}"
    else:
        gstarts = [grp[0][0].row_start for grp in groups]
        inter = np.diff(gstarts)
        if inter.size and (inter.max() - inter.min()) > 0.25 * float(np.median(inter)):
            reject = "INTER_BLOCK_SPACING_INCONSISTENT: possible missing middle block"
        else:
            top_content = min(b.row_start for b in bands) if bands else gstarts[0]
            spacing = float(np.median(inter)) if inter.size else 0.0
            if spacing > 0 and gstarts[0] - top_content > spacing:
                reject = "FIRST_BLOCK_OFFSET_TOO_LARGE: possible missing first block"
    if reject is not None:
        res.lines_dropped.append({"rows": None,
                                  "reason": f"{reject}: capture rejected"})
        res.samples = []
        return res

    for bi, grp in enumerate(groups):
        if len(grp) != lpb:
            res.lines_dropped.append({
                "rows": [grp[0][0].row_start, grp[-1][0].row_end],
                "reason": f"INCOMPLETE_BLOCK_{bi}_LINES_{len(grp)}_EXPECTED_{lpb}",
            })
            continue
        _emit_block(res, grp, bi, lines_gt, lpb, capture_sha256, sheet_id)
    return res


def _alignment_score(strip: np.ndarray, model: Any) -> float:
    """How well a registration model's cell centers align with ink.

    Score = mean ink mass inside a half-pitch window around each center,
    normalized by the strip's overall column ink mass. A misregistered
    model (harmonic pitch, phase slip) puts centers into inter-glyph gaps
    and scores lower.
    """
    ink = np.clip(np.median(strip) - strip, 0, None)
    mass = ink.sum(axis=0)
    total = float(mass.mean())
    if total <= 0:
        return 0.0
    centers = model.centers()
    if centers.size == 0:
        return 0.0
    half = max(1, int(round(model.pitch / 4)))
    vals = []
    for cx in centers:
        a = int(round(cx)) - half
        b = int(round(cx)) + half + 1
        if a < 0 or b > mass.size:
            vals.append(0.0)
        else:
            vals.append(float(mass[a:b].mean()))
    return float(np.mean(vals)) / total


def _emit_block(res: ExtractionResult,
                grp: list[tuple[SL.LineHypothesis, Any, np.ndarray, float]],
                bi: int, lines_gt: list[str], lpb: int,
                capture_sha256: str, sheet_id: str) -> None:
    """Emit labelled glyph samples for one complete block group."""
    texts = lines_gt[bi * lpb:(bi + 1) * lpb]
    for j, ((band, model, strip, pitch), text) in enumerate(zip(grp, texts)):
        li = bi * lpb + j
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
                block=bi, line=li, col=col,
            ))
        res.lines_used += 1
