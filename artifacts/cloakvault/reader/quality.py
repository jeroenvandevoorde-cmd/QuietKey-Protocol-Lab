"""Capture-quality gate — deterministic, offline, no ML/cloud inference.

Assesses image suitability BEFORE any deep token decoding, so that an
objectively unsuitable acquisition (blur, exposure, glare, bad page
geometry, absent footer signal) is rejected with explicit reasons instead
of surfacing later as a mysterious decode failure.

All metrics are simple, documented, deterministic numpy computations on a
grayscale image in [0, 1]. Thresholds come from a Reader Profile and are
DEVELOPMENT values (NOT GATE-A1 / NOT PRODUCTION).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

# Explicit machine-readable reasons (structured result, not a bare bool).
LOW_SHARPNESS = "LOW_SHARPNESS"
UNDEREXPOSED = "UNDEREXPOSED"
OVEREXPOSED = "OVEREXPOSED"
LOW_FOOTER_TONAL_RANGE = "LOW_FOOTER_TONAL_RANGE"
GLARE = "GLARE"
PAGE_NOT_CONFIDENT = "PAGE_NOT_CONFIDENT"
FOOTER_SIGNAL_TOO_WEAK = "FOOTER_SIGNAL_TOO_WEAK"


@dataclass
class QualityResult:
    status: str  # "ACCEPT" | "RECAPTURE"
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


def _as_gray(img: np.ndarray) -> np.ndarray:
    a = np.asarray(img, dtype=np.float64)
    if a.ndim == 3:
        a = a.mean(axis=2)
    if a.max() > 1.5:
        a = a / 255.0
    return np.clip(a, 0.0, 1.0)


def laplacian_variance(gray: np.ndarray) -> float:
    """Documented focus metric: variance of the 4-neighbour Laplacian."""
    g = gray
    lap = (
        -4.0 * g[1:-1, 1:-1]
        + g[:-2, 1:-1]
        + g[2:, 1:-1]
        + g[1:-1, :-2]
        + g[1:-1, 2:]
    )
    return float(lap.var())


def exposure_metrics(gray: np.ndarray, footer_band: np.ndarray) -> dict[str, float]:
    under = float((gray < 0.02).mean())
    over = float((gray > 0.98).mean())
    # p1..p99: text ink is sparse relative to paper, so wider percentiles
    # are needed to see the ink tail without being single-pixel noise.
    p1, p99 = np.percentile(footer_band, [1, 99])
    return {
        "under_frac": under,
        "over_frac": over,
        "footer_tonal_range": float(p99 - p1),
    }


def _largest_region_frac(mask: np.ndarray) -> float:
    """Largest 4-connected True region as a fraction of the image.

    Deterministic BFS labelling on a downsampled mask (bounded work).
    """
    # Downsample by block-max to at most ~128 px on the long side.
    h, w = mask.shape
    step = max(1, max(h, w) // 128)
    small = mask[::step, ::step]
    sh, sw = small.shape
    seen = np.zeros_like(small, dtype=bool)
    best = 0
    for i in range(sh):
        for j in range(sw):
            if small[i, j] and not seen[i, j]:
                size = 0
                stack = [(i, j)]
                seen[i, j] = True
                while stack:
                    y, x = stack.pop()
                    size += 1
                    for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                        if 0 <= ny < sh and 0 <= nx < sw and small[ny, nx] and not seen[ny, nx]:
                            seen[ny, nx] = True
                            stack.append((ny, nx))
                best = max(best, size)
    return best / float(sh * sw)


def glare_region_frac(gray: np.ndarray) -> float:
    """Fraction covered by the largest near-saturated specular region."""
    return _largest_region_frac(gray > 0.97)


def page_boundary_confidence(gray: np.ndarray) -> float:
    """Crude deterministic page-boundary evidence.

    Paper is expected to be a large, relatively bright, relatively uniform
    region distinct from surround. Score combines the fraction of
    paper-like pixels with edge contrast along the paper-region boundary
    rows/columns. This is a development heuristic, not production optics.
    """
    bright = gray > min(0.55, float(np.percentile(gray, 40)))
    paper_frac = float(bright.mean())
    # Edge energy near image borders (a full page fills the frame; a
    # partially visible or undetectable page loses border contrast).
    gy, gx = np.gradient(gray)
    grad = np.hypot(gx, gy)
    interior = float(grad[grad.shape[0] // 4 : -grad.shape[0] // 4, :].mean() + 1e-9)
    score = paper_frac
    # Penalize when almost no gradient structure exists at all (blank/black).
    if interior < 1e-4:
        score *= 0.25
    return float(min(1.0, score))


def footer_evidence(gray: np.ndarray) -> dict[str, float]:
    """Pre-OCR footer diagnostics on the bottom 30% band.

    * text-line candidates: dark-row bands in the row-ink profile;
    * monospace periodicity: peak of the autocorrelation of the column
      ink profile of the strongest line band (excluding lag 0 region);
    * pitch consistency: agreement of periodicity across line halves;
    * usable horizontal extent of the strongest band.
    """
    h = gray.shape[0]
    band = gray[int(h * 0.70) :, :]
    ink = 1.0 - band
    row_prof = ink.mean(axis=1)
    thr = row_prof.mean() + 0.5 * row_prof.std()
    rows = row_prof > thr
    # count contiguous row bands of plausible height
    lines = []
    start = None
    for i, v in enumerate(list(rows) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if 2 <= i - start <= max(4, band.shape[0] // 4):
                lines.append((start, i))
            start = None
    n_lines = len(lines)

    periodicity = 0.0
    pitch_consistency = 0.0
    extent = 0.0
    if lines:
        # strongest band by ink mass
        s, e = max(lines, key=lambda se: ink[se[0] : se[1], :].sum())
        col = ink[s:e, :].mean(axis=0)
        col = col - col.mean()
        active = np.where(np.abs(col) > 0.5 * np.abs(col).std())[0]
        if active.size:
            extent = (active[-1] - active[0]) / float(band.shape[1])

        def _peak(sig: np.ndarray) -> float:
            if sig.std() < 1e-9:
                return 0.0
            ac = np.correlate(sig, sig, mode="full")[sig.size - 1 :]
            ac = ac / (ac[0] + 1e-12)
            lo = 3
            hi = min(sig.size // 2, 200)
            return float(ac[lo:hi].max()) if hi > lo else 0.0

        periodicity = _peak(col)
        half = col.size // 2
        p1, p2 = _peak(col[:half]), _peak(col[half:])
        pitch_consistency = 1.0 - min(1.0, abs(p1 - p2) / max(p1, p2, 1e-9))

    return {
        "line_candidates": float(n_lines),
        "periodicity": periodicity,
        "pitch_consistency": pitch_consistency,
        "extent_frac": float(extent),
    }


def assess_quality(img: np.ndarray, quality_thresholds: dict) -> QualityResult:
    """Deterministic capture-quality assessment. Structured result."""
    q = quality_thresholds
    gray = _as_gray(img)
    footer_band = gray[int(gray.shape[0] * 0.70) :, :]

    reasons: list[str] = []
    metrics: dict[str, Any] = {}

    metrics["laplacian_variance"] = lv = laplacian_variance(gray)
    if lv < q["sharpness_min_laplacian_var"]:
        reasons.append(LOW_SHARPNESS)

    exp = exposure_metrics(gray, footer_band)
    metrics.update(exp)
    if exp["under_frac"] > q["exposure_max_under_frac"]:
        reasons.append(UNDEREXPOSED)
    if exp["over_frac"] > q["exposure_max_over_frac"]:
        reasons.append(OVEREXPOSED)
    if exp["footer_tonal_range"] < q["exposure_min_footer_range"]:
        reasons.append(LOW_FOOTER_TONAL_RANGE)

    metrics["glare_region_frac"] = gf = glare_region_frac(gray)
    if gf > q["glare_max_region_frac"]:
        reasons.append(GLARE)

    metrics["page_boundary_confidence"] = pc = page_boundary_confidence(gray)
    if pc < q["page_min_boundary_confidence"]:
        reasons.append(PAGE_NOT_CONFIDENT)

    fe = footer_evidence(gray)
    metrics.update({f"footer_{k}": v for k, v in fe.items()})
    if (
        fe["line_candidates"] < q["footer_min_line_candidates"]
        or fe["periodicity"] < q["footer_min_periodicity"]
        or fe["extent_frac"] < q["footer_min_extent_frac"]
    ):
        reasons.append(FOOTER_SIGNAL_TOO_WEAK)

    status = "ACCEPT" if not reasons else "RECAPTURE"
    return QualityResult(status=status, reasons=reasons, metrics=metrics)
