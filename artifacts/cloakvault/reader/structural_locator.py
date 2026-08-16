"""Structural footer locator — physical structure only, no wrapper semantics.

Finds candidate token-bearing footer text using ONLY:

  * bottom-of-page spatial prior;
  * text-line geometry (row ink bands);
  * monospace periodicity and glyph-pitch consistency;
  * line continuity and usable horizontal extent.

It has NO dependency on: domain names, arecipeforamaster.com, PREFIX=39,
fixed URL prefix/suffix lengths, "&v=1", fixed line lengths such as
[87, 48, 50], fixed token slices, exact token-start columns, recipe/body
content, or document genre. It must tolerate arbitrary ordinary text
before and after the token.

Protocol-visible structure (Bech32 compatibility, sentinel cv0, length
142) is applied LATER, by the separate structural extraction layer
(token_extract.py), on the transcribed text. Visual localization and
protocol extraction are deliberately separate layers.

The historical spike locator (wrapper-specific) is preserved as-run in
spike/reader/locate_reader_legacy_wrapper.py and is NOT used here.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .registration import estimate_pitch, grad_profile


@dataclass
class FooterLineCandidate:
    row_start: int  # absolute image row
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


def _row_bands(ink: np.ndarray, min_h: int = 2) -> list[tuple[int, int]]:
    prof = ink.mean(axis=1)
    thr = prof.mean() + 0.5 * prof.std()
    bands, start = [], None
    for i, v in enumerate(list(prof > thr) + [False]):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_h:
                bands.append((start, i))
            start = None
    return bands


def _periodicity(col: np.ndarray) -> float:
    sig = col - col.mean()
    if sig.std() < 1e-9:
        return 0.0
    ac = np.correlate(sig, sig, mode="full")[sig.size - 1 :]
    ac = ac / (ac[0] + 1e-12)
    lo, hi = 3, min(sig.size // 2, 200)
    return float(ac[lo:hi].max()) if hi > lo else 0.0


def locate_footer_lines(
    img: np.ndarray,
    bottom_frac: float = 0.50,
    min_periodicity: float = 0.12,
    min_extent_frac: float = 0.30,
) -> FooterLocateResult:
    """Return scored candidate monospace text lines in the bottom band."""
    gray = np.asarray(img, dtype=np.float64)
    if gray.ndim == 3:
        gray = gray.mean(axis=2)
    if gray.max() > 1.5:
        gray = gray / 255.0
    h, w = gray.shape
    band_top = int(h * (1.0 - bottom_frac))
    ink = 1.0 - gray[band_top:, :]

    candidates: list[FooterLineCandidate] = []
    for s, e in _row_bands(ink):
        strip = ink[s:e, :]
        col = grad_profile(strip)
        per = _periodicity(col)
        pitch = estimate_pitch(col)
        active = np.where(col > col.mean())[0]
        extent = (active[-1] - active[0]) / float(w) if active.size else 0.0
        # score: periodic, wide, plausible pitch; bottom-of-page prior
        depth_prior = (s + band_top) / float(h)
        score = per * extent * (1.0 if pitch > 0 else 0.0) * depth_prior
        if per >= min_periodicity and extent >= min_extent_frac and pitch > 0:
            candidates.append(
                FooterLineCandidate(
                    row_start=band_top + s,
                    row_end=band_top + e,
                    pitch=pitch,
                    periodicity=per,
                    extent_frac=float(extent),
                    score=float(score),
                )
            )

    if not candidates:
        return FooterLocateResult(False, "insufficient periodic line candidates", [])

    # pitch consistency across candidate lines (same monospace footer font)
    pitches = np.array([c.pitch for c in candidates])
    med = float(np.median(pitches))
    kept = [c for c in candidates if abs(c.pitch - med) <= 0.25 * med]
    if not kept:
        return FooterLocateResult(False, "glyph pitch inconsistent across lines", [])
    kept.sort(key=lambda c: c.row_start)
    return FooterLocateResult(True, None, kept)
