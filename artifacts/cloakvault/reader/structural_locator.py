"""Structural footer locator v2 — candidate enumeration, physical structure only.

Reader v0.2 shipped a single-shot locator that thresholded row-ink over the
full image width in a fixed bottom band. Bridge Run 01 development analysis
(seen regression data; locator development on it is explicitly permitted)
exposed four architectural failures:

  1. the dark table surface below/beside the page dominates a global row
     threshold, so faint true footer rows are never detected as bands;
  2. full-width row profiles dilute a footer that spans a fraction of the
     page width;
  3. serif body-text lines score high on generic autocorrelation "period-
     icity", producing false candidates with no print-pitch structure;
  4. an all-or-nothing cross-line pitch filter fails the whole image when
     only non-footer bands were found.

v2 replaces all four with general structural methods (no wrapper, content,
or domain knowledge; no per-image or per-sheet conditions):

  * page segmentation in LOG space (multiplicative shading becomes an
    additive offset; paper/table reflectance gap survives);
  * ink normalization by a paper-envelope background (separable grayscale
    closing with a kernel larger than any glyph, then blurred) — immune to
    shadow gradients that flood a plain threshold;
  * row-band detection against a LOCAL rolling-median baseline inside the
    page interior only;
  * per-band monospace evidence: autocorrelation of the band's column ink
    profile restricted to the band's own ink span, with harmonic
    suppression for pitch estimation (comb score at the print pitch —
    monospace lines score high, serif body and ring ink do not);
  * grouping of pitch-compatible, left-aligned, evenly spaced line runs
    into bounded candidate hypotheses, with pair synthesis (missing line
    above/below a valid pair) and single synthesis (lines at the median
    gap around one strong line) so damage that erases the periodicity of
    one or two lines never zeroes the candidate set;
  * deterministic, bounded, content-free candidate ranking (structural
    scores only). Downstream decoding may try each candidate; protocol
    structure (sentinel, RS, AEAD) decides — it never feeds back into
    geometry search.

It still has NO dependency on: domain names, URL prefix/suffix lengths,
fixed line lengths, fixed token slices, recipe/body content, or document
genre. Honest failure: an empty candidate list means FOOTER_LOCALIZATION_
FAIL upstream; nothing is manufactured.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .registration import estimate_pitch

# Structural constants (geometry/optics, not wrapper semantics).
MAX_CANDIDATES = 5          # bounded, deterministic downstream work
_MIN_COMB = 0.22            # minimum comb score to call a band monospace-like
_PITCH_TOL = 0.14           # relative pitch agreement within a candidate
_GAP_TOL = 0.45             # relative line-gap agreement within a candidate
_LEFT_ALIGN_PITCHES = 3.0   # flush-left agreement, in units of glyph pitch


@dataclass
class LineHypothesis:
    row_start: int          # absolute image rows
    row_end: int
    x0: int                 # ink-span columns (absolute)
    x1: int
    pitch: float
    comb: float             # comb score at the print pitch (0 if synthesized)
    detected: bool          # False = synthesized from pair/single structure


@dataclass
class FooterCandidate:
    lines: list[LineHypothesis]
    pitch: float
    gap: float
    score: float
    n_detected: int
    diagnostics: dict = field(default_factory=dict)


@dataclass
class FooterLineCandidate:
    """Back-compatible per-line view (v0.2 API)."""
    row_start: int
    row_end: int
    pitch: float
    periodicity: float
    extent_frac: float
    score: float


@dataclass
class FooterLocateResult:
    ok: bool
    reason: str | None
    candidates: list[FooterLineCandidate]


# ── deterministic numpy morphology helpers ──────────────────────────────

def _running_extreme_1d(a: np.ndarray, k: int, op) -> np.ndarray:
    """Running max/min over window k along the last axis (log-step shifts)."""
    out = a.copy()
    shift = 1
    remaining = k - 1
    while remaining > 0:
        s = min(shift, remaining)
        left = np.empty_like(out)
        left[..., s:] = out[..., :-s]
        left[..., :s] = out[..., :1]
        right = np.empty_like(out)
        right[..., :-s] = out[..., s:]
        right[..., -s:] = out[..., -1:]
        out = op(op(out, left), right)
        remaining -= s
        shift *= 2
    return out


def _gray_close(a: np.ndarray, k: int) -> np.ndarray:
    """Separable grayscale closing (dilation then erosion) with a k×k box."""
    d = _running_extreme_1d(a, k, np.maximum)
    d = _running_extreme_1d(d.T, k, np.maximum).T
    e = _running_extreme_1d(d, k, np.minimum)
    e = _running_extreme_1d(e.T, k, np.minimum).T
    return e


def _box_blur_1d(a: np.ndarray, k: int) -> np.ndarray:
    if k <= 1:
        return a
    c = np.cumsum(np.concatenate([a[:1].repeat(k), a, a[-1:].repeat(k)]))
    out = (c[2 * k :] - c[: -2 * k]) / (2 * k)
    return out[: a.shape[0]] if out.shape[0] > a.shape[0] else out


def _box_blur(a: np.ndarray, k: int) -> np.ndarray:
    if k <= 1:
        return a
    pad = k // 2
    p = np.pad(a, pad, mode="edge")
    c = np.cumsum(np.cumsum(p, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    s = (
        c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    ) / float(k * k)
    return s[: a.shape[0], : a.shape[1]]


def _rolling_median(a: np.ndarray, k: int) -> np.ndarray:
    k = max(3, k | 1)
    pad = k // 2
    p = np.pad(a, pad, mode="edge")
    win = np.lib.stride_tricks.sliding_window_view(p, k)
    return np.median(win, axis=1)


# ── page segmentation (log-space Otsu) ──────────────────────────────────

def _otsu_threshold(values: np.ndarray) -> float:
    hist, edges = np.histogram(values, bins=256)
    mids = (edges[:-1] + edges[1:]) / 2.0
    c = np.cumsum(hist).astype(np.float64)
    tot = c[-1]
    csum = np.cumsum(hist * mids)
    w0 = c / tot
    w1 = 1.0 - w0
    m0 = csum / np.maximum(c, 1)
    m1 = (csum[-1] - csum) / np.maximum(tot - c, 1)
    var = w0 * w1 * (m0 - m1) ** 2
    return float(mids[int(np.argmax(var))])


def page_region(gray: np.ndarray) -> tuple[int, int, int, int, float]:
    """(row0, row1, col0, col1, confidence) of the paper region.

    Otsu in log space: multiplicative shading (phone shadow crossing the
    boundary) becomes an additive offset while the paper/table reflectance
    gap survives.
    """
    lg = np.log(np.clip(gray, 1e-3, None))
    t = _otsu_threshold(lg[:: max(1, gray.shape[0] // 512), :: max(1, gray.shape[1] // 512)].ravel())
    mask = lg > t
    frac = float(mask.mean())
    rows = mask.mean(axis=1) > 0.5
    cols = mask.mean(axis=0) > 0.5
    if not rows.any() or not cols.any():
        return 0, gray.shape[0], 0, gray.shape[1], 0.0
    ridx = np.where(rows)[0]
    cidx = np.where(cols)[0]
    return int(ridx[0]), int(ridx[-1]) + 1, int(cidx[0]), int(cidx[-1]) + 1, frac


# ── band analysis ───────────────────────────────────────────────────────

def _comb_and_pitch(colprof: np.ndarray) -> tuple[float, float]:
    """Comb score and pitch of a band's column ink profile.

    Pitch estimation reuses registration.estimate_pitch (gradient-energy
    autocorrelation with harmonic suppression). The comb score is the
    normalized autocorrelation at that pitch lag.
    """
    sig = colprof - colprof.mean()
    if sig.std() < 1e-9 or sig.size < 32:
        return 0.0, 0.0
    pitch = estimate_pitch(colprof)
    if pitch <= 0:
        return 0.0, 0.0
    ac = np.correlate(sig, sig, mode="full")[sig.size - 1 :]
    ac = ac / (ac[0] + 1e-12)
    lag = int(round(pitch))
    if lag < 2 or lag >= ac.size:
        return 0.0, 0.0
    lo, hi = max(2, lag - 1), min(ac.size, lag + 2)
    return float(ac[lo:hi].max()), float(pitch)


def _band_runs(on: np.ndarray, min_h: int, max_h: int,
               grow: np.ndarray | None = None) -> list[tuple[int, int]]:
    """Contiguous True runs, optionally hysteresis-grown into `grow`.

    Seeds come from a strict threshold; a lenient mask recovers the full
    glyph height (ascenders/descenders are fainter in the row profile than
    the x-height core and would otherwise be cut off)."""
    bands: list[tuple[int, int]] = []
    start = None
    n = on.shape[0]
    for i, v in enumerate(list(on) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            s, e = start, i
            if grow is not None:
                while s > 0 and grow[s - 1] and (e - s) < max_h:
                    s -= 1
                while e < n and grow[e] and (e - s) < max_h:
                    e += 1
            if min_h <= e - s <= max_h:
                if bands and s < bands[-1][1]:
                    bands[-1] = (bands[-1][0], max(bands[-1][1], e))
                else:
                    bands.append((s, e))
            start = None
    return bands


def _ink_span(colprof: np.ndarray) -> tuple[int, int]:
    """Robust text span: outermost columns of sustained ink runs.

    A light box blur then a fraction-of-peak threshold; immune to isolated
    background specks that inflate a cumulative-mass span.
    """
    sm = _box_blur_1d(colprof, 9)
    thr = max(0.25 * float(np.percentile(sm, 99)), float(sm.mean()) + 1e-9)
    idx = np.where(sm > thr)[0]
    if idx.size == 0:
        return 0, 0
    return int(idx[0]), int(idx[-1]) + 1


def _score_band(ink: np.ndarray, s: int, e: int, r0: int, c0: int) -> LineHypothesis | None:
    colprof = ink[s:e, :].mean(axis=0)
    x0, x1 = _ink_span(colprof)
    if x1 - x0 < 32:
        return None
    comb, pitch = _comb_and_pitch(colprof[x0:x1])
    if comb < _MIN_COMB or pitch <= 0:
        return None
    # a monospace text line is many glyphs wide; reject speck runs
    if (x1 - x0) < 8 * pitch:
        return None
    # text-run structure: a glyph line alternates ink/gap at roughly the
    # glyph pitch; stain edges, tears, and paper texture produce a few
    # long ink runs instead and must not masquerade as text lines
    seg = colprof[x0:x1]
    on = seg > 0.5 * float(np.percentile(seg, 90))
    n_runs = int(np.count_nonzero(np.diff(on.astype(np.int8)) == 1)) + int(on[0])
    expected = (x1 - x0) / pitch
    if n_runs < 0.35 * expected:
        return None
    return LineHypothesis(row_start=r0 + s, row_end=r0 + e,
                          x0=c0 + x0, x1=c0 + x1,
                          pitch=pitch, comb=comb, detected=True)


def _detect_bands(ink: np.ndarray, r0: int, c0: int, c1: int,
                  page_h: int) -> list[LineHypothesis]:
    """Two-pass row-band detection.

    Pass 1: rows against a local rolling-median baseline over the whole
    page width. Pass 2 (local expansion): a short text block (e.g. a token
    footer spanning a fraction of the page width) dilutes a full-width row
    profile, so for every monospace-scored band the neighbourhood is
    re-scanned with the row profile restricted to that band's own column
    span, recovering faint sibling lines of the same block.
    """
    max_h = max(6, page_h // 35)
    prof = ink.mean(axis=1)
    base = _rolling_median(prof, max(25, page_h // 40))
    resid = prof - base
    mad = float(np.median(np.abs(resid - np.median(resid)))) + 1e-9

    out: list[LineHypothesis] = []
    lenient = resid > 1.25 * mad
    for s, e in _band_runs(resid > 4.0 * mad, 2, max_h, grow=lenient):
        h = _score_band(ink, s, e, r0, c0)
        if h is not None:
            out.append(h)

    # pass 2 — local expansion around each detected monospace band
    n_rows = ink.shape[0]
    for h in list(out):
        lh = h.row_end - h.row_start
        y0 = max(0, h.row_start - r0 - 8 * lh)
        y1 = min(n_rows, h.row_end - r0 + 8 * lh)
        xa, xb = h.x0 - c0, h.x1 - c0
        lprof = ink[y0:y1, max(0, xa):xb].mean(axis=1)
        lbase = _rolling_median(lprof, max(25, 4 * lh) | 1)
        lresid = lprof - lbase
        lmad = float(np.median(np.abs(lresid - np.median(lresid)))) + 1e-9
        for s, e in _band_runs(lresid > 3.0 * lmad, 2, max_h,
                               grow=lresid > 1.25 * lmad):
            rs, re = r0 + y0 + s, r0 + y0 + e
            if any(min(re, o.row_end) - max(rs, o.row_start) > 0 for o in out):
                continue
            cand = _score_band(ink, y0 + s, y0 + e, r0, c0)
            if cand is not None:
                out.append(cand)
    # deterministic order and de-overlap (keep higher comb)
    out.sort(key=lambda l: (-l.comb, l.row_start))
    kept: list[LineHypothesis] = []
    for l in out:
        if any(min(l.row_end, o.row_end) - max(l.row_start, o.row_start) > 0 for o in kept):
            continue
        kept.append(l)
    kept.sort(key=lambda l: l.row_start)
    return kept


# ── grouping and synthesis ──────────────────────────────────────────────

def _mid(l: LineHypothesis) -> float:
    return (l.row_start + l.row_end) / 2.0


def _pitch_agree(pa: float, pb: float) -> bool:
    """Pitch agreement modulo the factor-2 harmonic.

    Autocorrelation pitch estimation on a damaged/faint line can lock onto
    the half-pitch harmonic; that is an estimator artifact, not a different
    print pitch, so p and 2p (either way) are treated as compatible."""
    for x, y in ((pa, pb), (pa, 2 * pb), (2 * pa, pb)):
        if abs(x - y) <= _PITCH_TOL * max(x, y):
            return True
    return False


def _compatible(a: LineHypothesis, b: LineHypothesis) -> bool:
    if not _pitch_agree(a.pitch, b.pitch):
        return False
    # same text block: flush-left alignment OR substantial horizontal
    # overlap (damage such as a tear can eat a line's left edge without
    # detaching it from its block)
    p = max(a.pitch, b.pitch)
    left_aligned = abs(a.x0 - b.x0) <= _LEFT_ALIGN_PITCHES * p
    ov = min(a.x1, b.x1) - max(a.x0, b.x0)
    min_w = max(1, min(a.x1 - a.x0, b.x1 - b.x0))
    return left_aligned or (ov / min_w) >= 0.60


def _synth(base: LineHypothesis, row_offset: float) -> LineHypothesis:
    h = base.row_end - base.row_start
    rs = int(round(base.row_start + row_offset))
    return LineHypothesis(row_start=rs, row_end=rs + h, x0=base.x0, x1=base.x1,
                          pitch=base.pitch, comb=0.0, detected=False)


def _candidate(lines: list[LineHypothesis], img_h: int) -> FooterCandidate:
    det = [l for l in lines if l.detected]
    gaps = [_mid(b) - _mid(a) for a, b in zip(lines, lines[1:])]
    gap = float(np.median(gaps)) if gaps else 0.0
    pitch = float(np.median([l.pitch for l in det])) if det else 0.0
    depth = float(np.mean([_mid(l) for l in lines])) / float(img_h)
    comb_sum = float(sum(l.comb for l in det))
    # depth² prior: the token block is structurally the LAST text block on
    # the page (print exhaust below body content) — a squared prior favors
    # bottom blocks decisively without any content/wrapper knowledge
    score = comb_sum + 0.30 * len(det) + 1.0 * depth * depth
    return FooterCandidate(lines=lines, pitch=pitch, gap=gap, score=score,
                           n_detected=len(det),
                           diagnostics={"comb_sum": round(comb_sum, 4),
                                        "depth": round(depth, 4)})


def locate_footer_candidates(img: np.ndarray,
                             max_candidates: int = MAX_CANDIDATES) -> list[FooterCandidate]:
    """Bounded, deterministic, content-free footer candidate enumeration."""
    gray = np.asarray(img, dtype=np.float64)
    if gray.ndim == 3:
        gray = gray.mean(axis=2)
    if gray.max() > 1.5:
        gray = gray / 255.0
    h, w = gray.shape

    r0, r1, c0, c1, page_conf = page_region(gray)
    # interior inset: kill page-edge shadows / border artifacts
    ins_r = max(2, (r1 - r0) // 80)
    ins_c = max(2, (c1 - c0) // 80)
    r0i, r1i, c0i, c1i = r0 + ins_r, r1 - ins_r, c0 + ins_c, c1 - ins_c
    if r1i - r0i < 32 or c1i - c0i < 32:
        return []
    page = gray[r0i:r1i, c0i:c1i]
    ph, pw = page.shape

    # paper-envelope normalization: closing kernel larger than any glyph
    k = max(9, pw // 60)
    env = _gray_close(page, k)
    env = _box_blur(env, max(3, k // 2))
    ink = np.clip(1.0 - page / np.clip(env, 1e-3, None), 0.0, 1.0)

    # search the lower part of the PAGE (structural prior: print exhaust
    # sits below body content; generous fraction, not a tight crop)
    search_top = ph // 2
    hyps = _detect_bands(ink[search_top:], r0i + search_top, c0i, c1i, ph)
    hyps.sort(key=lambda l: l.row_start)

    candidates: list[FooterCandidate] = []

    # runs of >=3 compatible, evenly spaced lines
    n = len(hyps)
    for i in range(n):
        for j in range(i + 1, n):
            if not _compatible(hyps[i], hyps[j]):
                continue
            gap_ij = _mid(hyps[j]) - _mid(hyps[i])
            if gap_ij <= 0 or gap_ij > 8 * max(hyps[i].pitch, hyps[j].pitch):
                continue
            for k2 in range(j + 1, n):
                if not _compatible(hyps[j], hyps[k2]):
                    continue
                gap_jk = _mid(hyps[k2]) - _mid(hyps[j])
                if gap_jk <= 0:
                    continue
                if abs(gap_jk - gap_ij) > _GAP_TOL * max(gap_ij, gap_jk):
                    continue
                candidates.append(_candidate([hyps[i], hyps[j], hyps[k2]], h))
            # pair synthesis: missing third line above and below
            pair = [hyps[i], hyps[j]]
            candidates.append(_candidate([_synth(hyps[i], -gap_ij)] + pair, h))
            candidates.append(_candidate(pair + [_synth(hyps[j], gap_ij)], h))

    # single synthesis: full triple around each strong line at a structural
    # gap estimate (median detected gap, else a line-height multiple)
    all_gaps = [
        _mid(b) - _mid(a)
        for a, b in zip(hyps, hyps[1:])
        if _compatible(a, b) and 0 < _mid(b) - _mid(a) <= 8 * max(a.pitch, b.pitch)
    ]
    for l in hyps:
        gap_est = float(np.median(all_gaps)) if all_gaps else 2.6 * (l.row_end - l.row_start)
        candidates.append(_candidate([_synth(l, -gap_est), l, _synth(l, gap_est)], h))
        candidates.append(_candidate([l, _synth(l, gap_est), _synth(l, 2 * gap_est)], h))
        candidates.append(_candidate([_synth(l, -2 * gap_est), _synth(l, -gap_est), l], h))

    if not candidates:
        return []

    # deterministic ranking; deduplicate hypotheses covering the same rows
    candidates.sort(key=lambda c: (-c.score, c.lines[0].row_start))
    kept: list[FooterCandidate] = []

    def _shared_lines(a: FooterCandidate, b: FooterCandidate) -> int:
        n = 0
        for la in a.lines:
            for lb in b.lines:
                if min(la.row_end, lb.row_end) - max(la.row_start, lb.row_start) > 0:
                    n += 1
                    break
        return n

    for c in candidates:
        dup = any(_shared_lines(c, k) >= 2 and k.n_detected >= c.n_detected
                  for k in kept)
        if not dup:
            c.diagnostics["page_confidence"] = round(page_conf, 4)
            kept.append(c)
        if len(kept) >= max_candidates:
            break
    return kept


# ── v0.2-compatible single-shot view ────────────────────────────────────

def locate_footer_lines(img: np.ndarray, **_ignored) -> FooterLocateResult:
    """Back-compatible adapter: per-line view of the best candidate."""
    cands = locate_footer_candidates(img)
    if not cands:
        return FooterLocateResult(False, "no structural footer candidate", [])
    best = cands[0]
    lines = [
        FooterLineCandidate(
            row_start=l.row_start, row_end=l.row_end, pitch=l.pitch,
            periodicity=l.comb, extent_frac=(l.x1 - l.x0) / float(np.asarray(img).shape[1]),
            score=best.score,
        )
        for l in best.lines
    ]
    return FooterLocateResult(True, None, lines)
