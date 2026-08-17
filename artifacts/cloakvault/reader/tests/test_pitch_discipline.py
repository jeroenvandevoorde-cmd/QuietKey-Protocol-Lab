"""Synthetic regression tests for the shared layout-consistent pitch
discipline (registration.select_pitch) — owner-mandated coverage BEFORE any
S46 replay:

  * true pitch near nominal
  * mild scale change
  * perspective-derived pitch variation
  * strong half-pitch harmonic
  * double-pitch harmonic
  * repeated-stroke glyph patterns
  * local occlusion
  * illumination gradients

Required property: a strong harmonic must not defeat a geometrically
plausible fundamental merely because the harmonic has a numerically higher
raw alignment score. Conversely the filter must not reject ordinary
print/camera scaling.

All images are synthetic; no capture data, no S46, no token contents.
"""
from __future__ import annotations

import numpy as np
import pytest

from reader.registration import (enumerate_pitch_candidates, register_line,
                                 select_pitch)

RNG = np.random.default_rng(20260817)
COUNTS = [46, 48, 50, 87]  # profile production_layout.token_line_char_counts


def synth_line(n_chars: int = 48, pitch: float = 12.0, height: int = 18,
               stroke_doubling: float = 0.0, occlusion: tuple | None = None,
               illum_gradient: float = 0.0, pitch_drift: float = 0.0,
               seed: int = 7) -> tuple[np.ndarray, float]:
    """Monospace-ish text line strip on white paper. Each glyph draws 1-3
    vertical strokes inside its cell (never on the cell boundary), leaving a
    real inter-character gap — the structure that makes half-pitch locks
    physically wrong. `stroke_doubling` in [0,1] forces two strokes exactly
    pitch/2 apart in that fraction of glyphs (strong half-pitch harmonic).
    `pitch_drift` linearly scales pitch across the line (perspective).
    Returns (image in [0,1], mean effective pitch)."""
    rng = np.random.default_rng(seed)
    pad = int(3 * pitch)
    # effective per-cell pitches (perspective: linear ramp)
    pitches = pitch * (1.0 + pitch_drift * (np.arange(n_chars) / max(n_chars - 1, 1) - 0.5))
    width = pad * 2 + int(np.ceil(pitches.sum()))
    img = np.ones((height, width))
    x = float(pad)
    y0, y1 = height // 4, height - height // 4
    for k in range(n_chars):
        p = pitches[k]
        sw = max(1, int(round(p / 8.0)))  # stroke width scales with pitch
        max_str = 3 if p >= 10 else 2 if p >= 7 else 1
        if stroke_doubling and rng.random() < stroke_doubling:
            offs = [0.30 * p, 0.80 * p]  # exactly p/2 apart -> harmonic comb
        elif p < 9.0:
            # near the resolution limit real glyphs blur into one blob per
            # cell; random multi-stroke placement would destroy the very
            # periodicity a camera still sees
            offs = [0.5 * p]
        else:
            n_str = rng.integers(1, max_str + 1)
            offs = sorted(rng.uniform(0.22 * p, 0.82 * p, size=n_str))
        for o in offs:
            c = int(round(x + o))
            img[y0:y1, max(c - sw // 2 - 1, 0):c + (sw + 1) // 2] = 0.15
        x += p
    if occlusion is not None:
        a, b = occlusion
        img[:, int(pad + a * (width - 2 * pad)):int(pad + b * (width - 2 * pad))] = 0.1
    if illum_gradient:
        ramp = 1.0 - illum_gradient * np.linspace(0, 1, width)[None, :]
        img = 1.0 - (1.0 - img) * 1.0
        img = img * ramp + (1 - ramp) * 0.0  # darken toward one side
        img = np.clip(img, 0.0, 1.0)
    span = float(pitches.sum())
    return img, span


def _sel(img, span, n=48, **kw):
    return select_pitch(img, span=span, expected_char_counts=COUNTS, **kw)


def test_true_pitch_near_nominal():
    img, span = synth_line(n_chars=48, pitch=12.0)
    s = _sel(img, span)
    assert s.method == "layout"
    assert abs(s.pitch - 12.0) / 12.0 < 0.08


@pytest.mark.parametrize("scale", [0.6, 0.8, 1.25, 1.6])
def test_mild_and_strong_scale_change_accepted(scale):
    """Ordinary print/camera scaling must not be rejected: the layout window
    is span-relative, hence scale-invariant."""
    p = 12.0 * scale
    img, span = synth_line(n_chars=48, pitch=p)
    s = _sel(img, span)
    assert abs(s.pitch - p) / p < 0.08, s.diagnostics()


def test_perspective_pitch_variation():
    img, span = synth_line(n_chars=48, pitch=12.0, pitch_drift=0.12)
    s = _sel(img, span)
    assert abs(s.pitch - 12.0) / 12.0 < 0.10


def test_strong_half_pitch_harmonic_not_selected():
    """Every glyph doubled at exactly p/2: the autocorrelation score at p/2
    beats the fundamental, but the fundamental is layout-plausible and its
    cells are occupied — the half pitch must lose."""
    img, span = synth_line(n_chars=48, pitch=12.0, stroke_doubling=1.0, seed=3)
    cands = enumerate_pitch_candidates(
        np.abs(np.diff(1.0 - img, axis=1)).mean(axis=0))
    s = _sel(img, span)
    assert abs(s.pitch - 12.0) / 12.0 < 0.08, s.diagnostics()
    # the harmonic really was competitive (test is meaningful)
    assert any(abs(p - 6.0) < 1.5 for p, _ in cands)


def test_half_pitch_rejection_recorded_in_diagnostics():
    img, span = synth_line(n_chars=48, pitch=12.0, stroke_doubling=1.0, seed=3)
    s = _sel(img, span)
    assert any(r["kind"] in ("half_pitch", "layout_implausible_harmonic")
               for r in s.harmonic_rejections), s.diagnostics()


def test_double_pitch_harmonic_not_selected():
    """A 2p autocorrelation peak always exists; it must not win when p is
    layout-plausible."""
    img, span = synth_line(n_chars=48, pitch=12.0, seed=11)
    s = _sel(img, span)
    assert abs(s.pitch - 12.0) / 12.0 < 0.08
    assert not any(abs(c.pitch - 24.0) < 2.0 and c.pitch == s.pitch
                   for c in s.candidates)


def test_repeated_stroke_glyph_patterns():
    """60% of glyphs carry an internal p/2 stroke pair (like m/w-heavy
    text) — fundamental must still win."""
    img, span = synth_line(n_chars=48, pitch=12.0, stroke_doubling=0.6, seed=5)
    s = _sel(img, span)
    assert abs(s.pitch - 12.0) / 12.0 < 0.08, s.diagnostics()


def test_local_occlusion():
    img, span = synth_line(n_chars=48, pitch=12.0, occlusion=(0.40, 0.52), seed=9)
    s = _sel(img, span)
    assert abs(s.pitch - 12.0) / 12.0 < 0.10, s.diagnostics()


def test_illumination_gradient():
    img, span = synth_line(n_chars=48, pitch=12.0, illum_gradient=0.5, seed=13)
    s = _sel(img, span)
    assert abs(s.pitch - 12.0) / 12.0 < 0.10, s.diagnostics()


def test_neighbor_pitch_agreement_rescues_harmonic_line():
    """When the layout window alone cannot disambiguate (87-char window
    overlaps a 48-char half-pitch), the neighboring-line pitch must."""
    img, span = synth_line(n_chars=48, pitch=12.0, stroke_doubling=1.0, seed=17)
    s = select_pitch(img, span=span, expected_char_counts=COUNTS,
                     neighbor_pitch=12.1)
    assert abs(s.pitch - 12.0) / 12.0 < 0.08, s.diagnostics()


def test_register_line_with_selected_pitch_yields_expected_cells():
    img, span = synth_line(n_chars=48, pitch=12.0, stroke_doubling=1.0, seed=21)
    s = _sel(img, span)
    model = register_line(img, pitch_hint=s.pitch)
    assert 44 <= model.n_cells <= 52, model.n_cells


def test_no_layout_info_falls_back_honestly():
    img, span = synth_line(n_chars=48, pitch=12.0, seed=23)
    s = select_pitch(img)
    assert s.pitch > 0
    assert s.method in ("occupancy", "legacy_fallback")
