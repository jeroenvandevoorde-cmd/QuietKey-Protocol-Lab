"""Locally deformable per-line registration (Reader v0.2, DEVELOPMENT).

A four-corner homography corrects page perspective but not curl, folds,
bow, local stretching, or phase drift. This module therefore models each
candidate footer line independently:

  * its own vertical path y(x)          — robust low-order polynomial;
  * its own glyph pitch                 — autocorrelation of the ink comb;
  * its own smoothly drifting phase     — piecewise-linear phase model
                                          fitted by windowed comb
                                          correlation with robust
                                          (outlier-downweighted) smoothing.

Character centers are NOT assumed to satisfy x(k) = x0 + k*p exactly for
the full line: the phase model allows smooth drift while a smoothness
constraint prevents a stained/smeared region from hijacking the fit.

Deterministic, explainable, no ground-truth token characters, no secret
data.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class LineModel:
    y_path_coeffs: np.ndarray  # polynomial coeffs for y(x) (np.polyval order)
    pitch: float
    phase_knots_x: np.ndarray  # window centers
    phase_knots: np.ndarray  # local phase offset (pixels) at each knot
    x_start: float
    n_cells: int
    window_weights: np.ndarray  # robust weight per knot (0..1)

    def y_at(self, x: np.ndarray | float) -> np.ndarray | float:
        return np.polyval(self.y_path_coeffs, x)

    def centers(self) -> np.ndarray:
        """x-centers of the n_cells glyph cells under the drift model."""
        k = np.arange(self.n_cells)
        base = self.x_start + k * self.pitch
        drift = np.interp(base, self.phase_knots_x, self.phase_knots)
        return base + drift


def grad_profile(ink: np.ndarray) -> np.ndarray:
    """Column profile of horizontal gradient energy.

    High-pass by construction: solid occlusion blocks and smooth
    illumination ramps contribute almost nothing, while periodic glyph
    structure survives — so damaged regions cannot hijack pitch/phase
    estimation.
    """
    g = np.abs(np.diff(ink, axis=1)).mean(axis=0)
    return np.append(g, g[-1])


def _robust_polyfit(x: np.ndarray, y: np.ndarray, deg: int, iters: int = 5) -> np.ndarray:
    """IRLS polynomial fit with Huber-style weights (deterministic)."""
    w = np.ones_like(y, dtype=np.float64)
    coeffs = np.polyfit(x, y, deg)
    for _ in range(iters):
        r = y - np.polyval(coeffs, x)
        s = np.median(np.abs(r)) * 1.4826 + 1e-9
        w = np.minimum(1.0, 1.5 * s / (np.abs(r) + 1e-12))
        coeffs = np.polyfit(x, y, deg, w=w)
    return coeffs


def estimate_line_path(line_img: np.ndarray, deg: int = 2) -> np.ndarray:
    """Estimate the ink-centroid vertical path y(x) of a line strip.

    Returns polynomial coefficients (low order → smooth bow only).
    Columns with negligible ink are ignored; the fit is robust so a local
    smear cannot bend the whole path.
    """
    ink = 1.0 - np.asarray(line_img, dtype=np.float64)
    ink = ink - ink.min()
    colmass = ink.sum(axis=0)
    ys = np.arange(line_img.shape[0], dtype=np.float64)
    valid = colmass > 0.2 * np.median(colmass[colmass > 0]) if (colmass > 0).any() else np.zeros_like(colmass, bool)
    xs = np.where(valid)[0].astype(np.float64)
    if xs.size < deg + 2:
        return np.array([line_img.shape[0] / 2.0])  # constant path
    cy = (ink[:, valid] * ys[:, None]).sum(axis=0) / (colmass[valid] + 1e-12)
    return _robust_polyfit(xs, cy, deg)


def estimate_pitch(col_profile: np.ndarray, pitch_min: float = 4.0, pitch_max: float = 60.0) -> float:
    """Glyph pitch from the autocorrelation peak of the column ink profile."""
    sig = col_profile - col_profile.mean()
    if sig.std() < 1e-9:
        return 0.0
    ac = np.correlate(sig, sig, mode="full")[sig.size - 1 :]
    lo, hi = int(pitch_min), int(min(pitch_max, sig.size // 2))
    if hi <= lo:
        return 0.0
    seg = ac[lo:hi]
    peak = float(seg.max())
    if peak <= 0:
        return 0.0
    # Harmonic suppression: a lag of k*pitch scores as high as pitch, so
    # take the SMALLEST local-max lag within 80% of the global peak.
    lag = lo + int(np.argmax(seg))
    for i in range(1, seg.size - 1):
        if seg[i] >= 0.8 * peak and seg[i] >= seg[i - 1] and seg[i] >= seg[i + 1]:
            lag = lo + i
            break
    # parabolic refinement
    if 0 < lag < ac.size - 1:
        a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
        denom = a - 2 * b + c
        if abs(denom) > 1e-12:
            lag = lag + 0.5 * (a - c) / denom
    return float(lag)


def _comb_phase(sig: np.ndarray, pitch: float) -> tuple[float, float]:
    """Best phase in [0, pitch) for a comb of ink peaks; returns (phase, score)."""
    n = sig.size
    x = np.arange(n)
    # correlation with a cosine comb — deterministic closed form
    ang = 2.0 * np.pi * x / pitch
    c = float(np.dot(sig, np.cos(ang)))
    s = float(np.dot(sig, np.sin(ang)))
    phase = (np.arctan2(s, c) / (2.0 * np.pi)) * pitch
    score = np.hypot(c, s) / (np.linalg.norm(sig) * np.sqrt(n / 2.0) + 1e-12)
    return float(phase % pitch), float(score)


def fit_phase_drift(
    col_profile: np.ndarray,
    pitch: float,
    window_cells: int = 12,
    smooth_lambda: float = 4.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Piecewise-linear local phase model with robust smoothing.

    Splits the line into overlapping windows (~window_cells glyphs each),
    measures each window's local comb phase, unwraps against the global
    phase, downweights low-score (damaged) windows, and solves a
    regularized least-squares smoothing so one bad region cannot drag its
    neighbours: minimize sum w_i (d_i - m_i)^2 + lambda * sum (d_{i+1}-d_i)^2.

    Returns (knot_x, knot_drift, knot_weights).
    """
    sig = col_profile - col_profile.mean()
    n = sig.size
    win = max(int(window_cells * pitch), int(3 * pitch))
    step = max(win // 2, 1)
    starts = list(range(0, max(n - win, 1), step)) or [0]

    g_phase, _ = _comb_phase(sig, pitch)
    xs, drifts, weights = [], [], []
    for s0 in starts:
        seg = sig[s0 : s0 + win]
        if seg.std() < 1e-9:
            continue
        ph, sc = _comb_phase(seg, pitch)
        # local phase is relative to segment start; convert to absolute drift
        # vs the global comb: expected local phase = (g_phase - s0) mod pitch
        expected = (g_phase - s0) % pitch
        d = ph - expected
        # wrap to nearest (drift assumed < pitch/2 per window)
        d = (d + pitch / 2.0) % pitch - pitch / 2.0
        xs.append(s0 + win / 2.0)
        drifts.append(d)
        weights.append(sc)
    if not xs:
        return np.array([0.0, float(n)]), np.zeros(2), np.zeros(2)

    x = np.asarray(xs)
    m = np.asarray(drifts)
    w = np.asarray(weights)
    w = w / (w.max() + 1e-12)
    # robust pass: downweight outliers vs median drift
    med = np.median(m)
    mad = np.median(np.abs(m - med)) * 1.4826 + 1e-9
    w = w * np.minimum(1.0, 2.5 * mad / (np.abs(m - med) + 1e-12))

    k = m.size
    # solve (W + lam*L) d = W m  with L the 1-D graph Laplacian
    W = np.diag(w)
    L = np.zeros((k, k))
    for i in range(k - 1):
        L[i, i] += 1.0
        L[i + 1, i + 1] += 1.0
        L[i, i + 1] -= 1.0
        L[i + 1, i] -= 1.0
    d = np.linalg.solve(W + smooth_lambda * L + 1e-9 * np.eye(k), W @ m)
    return x, d, w


def register_line(line_img: np.ndarray, n_cells_hint: int | None = None) -> LineModel:
    """Full per-line registration: path + pitch + drift model."""
    ink = 1.0 - np.asarray(line_img, dtype=np.float64)
    col = grad_profile(ink)
    pitch = estimate_pitch(col)
    if pitch <= 0:
        raise ValueError("no periodic structure in line")
    kx, kd, kw = fit_phase_drift(col, pitch)
    y_coeffs = estimate_line_path(line_img)

    # First cell center: strongest comb alignment near the left active edge.
    sig = col - col.mean()
    g_phase, _ = _comb_phase(sig, pitch)
    active = np.where(col > col.mean())[0]
    left = float(active[0]) if active.size else 0.0
    # snap to comb: centers are at g_phase + j*pitch
    j = np.ceil((left - g_phase - pitch / 2.0) / pitch)
    x_start = g_phase + j * pitch
    n_cells = n_cells_hint or int((col.size - x_start) // pitch)

    # Refine the constant phase bias of the gradient basis: robust median
    # of per-cell ink-centroid offsets (damaged cells cannot skew a median).
    # Baseline-subtracted ink mass: paper is not perfectly white, so the
    # background level (median) must be removed before cells can be judged
    # empty or centroids computed.
    mass = np.clip(ink - np.median(ink), 0.0, None).sum(axis=0)
    xs_axis = np.arange(mass.size, dtype=np.float64)
    for _ in range(3):  # iterate: window truncation limits one-pass correction
        offsets = []
        for k in range(max(n_cells, 1)):
            c = x_start + k * pitch
            a, b = int(round(c - pitch / 2.0)), int(round(c + pitch / 2.0))
            if a < 0 or b > mass.size:
                continue
            m_cell = mass[a:b]
            if m_cell.sum() > 1e-9:
                offsets.append(float((m_cell * xs_axis[a:b]).sum() / m_cell.sum()) - c)
        if not offsets:
            break
        step = float(np.median(offsets))
        x_start += step
        if abs(step) < 0.05:
            break

    # Usable interval (spec: per-line modelling): trim leading/trailing
    # cells whose ink mass is negligible — they are padding, not glyphs.
    if n_cells_hint is None and n_cells > 0:
        cell_mass = []
        for k in range(n_cells):
            c = x_start + k * pitch
            a, b = int(round(c - pitch / 2.0)), int(round(c + pitch / 2.0))
            cell_mass.append(mass[max(a, 0) : max(b, 0)].sum())
        cm = np.asarray(cell_mass)
        med = np.median(cm[cm > 0]) if (cm > 0).any() else 0.0
        keep = cm > 0.10 * med
        if keep.any():
            first, last = int(np.argmax(keep)), int(len(keep) - np.argmax(keep[::-1]) - 1)
            x_start += first * pitch
            n_cells = last - first + 1
        else:
            n_cells = 0
    return LineModel(
        y_path_coeffs=np.atleast_1d(y_coeffs),
        pitch=pitch,
        phase_knots_x=kx,
        phase_knots=kd,
        x_start=float(x_start),
        n_cells=max(n_cells, 0),
        window_weights=kw,
    )
