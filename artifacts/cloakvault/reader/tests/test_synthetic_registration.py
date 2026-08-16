"""Task 5 — synthetic geometry test suite (engineering tests only, NOT Gate A evidence).

Exercises the deformable registration independently of Bridge layouts:
clean geometry, perspective, smooth phase drift, mild bow, local damage,
occlusion → erasure semantics. The supported envelope demonstrated here is
documented in reader/SYNTHETIC-ENVELOPE.md.
"""
import numpy as np
import pytest

from reader.registration import estimate_pitch, register_line
from reader.synthglyphs import (
    CELL_W,
    apply_bow,
    apply_illumination,
    apply_local_fold,
    apply_occlusion,
    apply_perspective,
    apply_phase_drift,
    classify_cells,
    render_line,
)

TEXT = "qpzry9x8gf2tvdw0s3jn54khce6mua7lqpzry9x8gf2tvdw0"  # 48 monospace cells
PAD = 12


def true_centers(n=len(TEXT)):
    return PAD + CELL_W / 2 + np.arange(n) * CELL_W


def register_and_centers(img, n=len(TEXT)):
    m = register_line(img, n_cells_hint=n)
    return m, m.centers()


def test_clean_geometry_preserved():
    img = render_line(TEXT)
    m, centers = register_and_centers(img)
    assert abs(m.pitch - CELL_W) < 0.2
    err = np.abs(centers - true_centers())
    assert err.max() < 1.5, f"max center error {err.max():.2f}px"


def test_pitch_estimation_accuracy():
    img = render_line(TEXT)
    ink = 1.0 - img
    assert abs(estimate_pitch(ink.mean(axis=0)) - CELL_W) < 0.2


def test_moderate_perspective_tolerated():
    img = apply_perspective(render_line(TEXT), 0.06)
    m, centers = register_and_centers(img)
    # registration still finds a consistent periodic grid (pitch near cell width)
    assert abs(m.pitch - CELL_W) < 0.8


def test_smooth_phase_drift_followed():
    drift = 3.0  # px across the line (< half a cell, smooth)
    img = apply_phase_drift(render_line(TEXT), drift)
    m, centers = register_and_centers(img)
    # under x' = x + d*x/w mapping, content at true center c appears at c - drift*c/w
    w = img.shape[1]
    expected = true_centers() - drift * true_centers() / (w - 1)
    err = np.abs(centers - expected)
    assert err.max() < 0.5 * CELL_W, (
        f"phase drift accumulated into {err.max():.2f}px (> half cell) by line end"
    )


def test_mild_bow_followed():
    img = apply_bow(render_line(TEXT), 2.0)
    m, _ = register_and_centers(img)
    xs = np.linspace(0, img.shape[1] - 1, 20)
    ys = np.polyval(m.y_path_coeffs, xs)
    assert np.ptp(ys) > 0.8  # path follows the bow rather than staying flat
    assert np.ptp(ys) < 4.0  # smooth, low-order


def test_local_damage_does_not_shift_clean_regions():
    img = render_line(TEXT)
    w = img.shape[1]
    damaged = apply_local_fold(img, w // 2 - 20, 40, 3.0)
    damaged = apply_occlusion(damaged, w // 2 - 12, 24, value=0.1)
    m, centers = register_and_centers(damaged)
    clean_left = np.abs(centers[:10] - true_centers()[:10])
    clean_right = np.abs(centers[-8:] - true_centers()[-8:])
    assert clean_left.max() < 0.4 * CELL_W, "left clean region dragged by damage"
    assert clean_right.max() < 0.6 * CELL_W, "right clean region dragged by damage"


def test_unreadable_cells_become_erasures_not_confident_characters(dev_profile):
    img = render_line(TEXT)
    w = img.shape[1]
    x0, wd = w // 2 - 16, 32
    damaged = apply_occlusion(img, x0, wd, value=0.1)
    m, centers = register_and_centers(damaged)
    y_mid = float(np.mean(np.polyval(m.y_path_coeffs, centers)))
    text, confs, margins = classify_cells(
        damaged, centers, y_mid, dev_profile.confidence_floor, dev_profile.margin_floor
    )
    occluded = [k for k, c in enumerate(centers) if x0 <= c <= x0 + wd]
    assert occluded, "test setup: no occluded cells"
    for k in occluded:
        assert text[k] == "?" or text[k] == TEXT[k], (
            f"occluded cell {k} classified as confident WRONG char {text[k]!r}"
        )
    assert any(text[k] == "?" for k in occluded), "occlusion produced no erasures"


def test_clean_page_classifies_cleanly(dev_profile):
    img = render_line(TEXT)
    m, centers = register_and_centers(img)
    y_mid = float(np.mean(np.polyval(m.y_path_coeffs, centers)))
    text, _, _ = classify_cells(img, centers, y_mid, dev_profile.confidence_floor, dev_profile.margin_floor)
    assert text == TEXT


def test_uneven_illumination_tolerated(dev_profile):
    img = apply_illumination(render_line(TEXT), 0.25)
    m, centers = register_and_centers(img)
    y_mid = float(np.mean(np.polyval(m.y_path_coeffs, centers)))
    text, _, _ = classify_cells(img, centers, y_mid, dev_profile.confidence_floor, dev_profile.margin_floor)
    correct = sum(a == b for a, b in zip(text, TEXT))
    assert correct >= len(TEXT) - 4
    assert all(t == "?" or t == e for t, e in zip(text, TEXT)), "confident wrong char under illumination"


def test_determinism():
    img = apply_phase_drift(render_line(TEXT), 2.0)
    m1, c1 = register_and_centers(img)
    m2, c2 = register_and_centers(img)
    assert np.array_equal(c1, c2) and m1.pitch == m2.pitch
