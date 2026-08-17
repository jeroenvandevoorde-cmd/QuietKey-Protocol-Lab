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


@dataclass
class PitchCandidate:
    """One raw pitch hypothesis considered by select_pitch (diagnostics)."""
    pitch: float
    score: float               # normalized autocorrelation at this lag
    cell_count: int            # implied cells over the active span
    empty_frac: float          # fraction of interior cells with negligible ink
    layout_ok: bool | None     # within tolerance of an expected layout pitch (None = no layout info)
    rejected: str | None       # rejection reason, e.g. HALF_PITCH_ARTIFACT


@dataclass
class PitchSelection:
    """Result of layout-consistent pitch selection (shared discipline).

    Used by BOTH the calibration extractor and the normal frame pipeline so
    harmonic handling cannot drift between them."""
    pitch: float
    method: str                       # 'layout' | 'occupancy' | 'legacy_fallback'
    candidates: list[PitchCandidate]
    expected_pitches: list[float]     # layout-derived expected pitches (may be empty)
    rel_tol: float
    neighbor_pitch: float | None
    harmonic_rejections: list[dict]   # explicit record of rejected half/double locks

    def diagnostics(self) -> dict:
        """JSON-safe development diagnostics. Never includes token contents."""
        return {
            "selected_pitch": round(self.pitch, 3),
            "method": self.method,
            "expected_pitches": [round(p, 3) for p in self.expected_pitches],
            "rel_tol": self.rel_tol,
            "neighbor_pitch": round(self.neighbor_pitch, 3) if self.neighbor_pitch else None,
            "candidates": [
                {"pitch": round(c.pitch, 3), "score": round(c.score, 4),
                 "cell_count": c.cell_count, "empty_frac": round(c.empty_frac, 3),
                 "layout_ok": c.layout_ok, "rejected": c.rejected}
                for c in self.candidates],
            "harmonic_rejections": self.harmonic_rejections,
        }


def enumerate_pitch_candidates(
    col_profile: np.ndarray, pitch_min: float = 4.0, pitch_max: float = 60.0,
    floor_frac: float = 0.30,
) -> list[tuple[float, float]]:
    """All local autocorrelation maxima in [pitch_min, pitch_max] with a
    normalized score >= floor_frac of the global peak, parabolic-refined.

    Unlike estimate_pitch (which commits to the smallest strong peak), this
    exposes the full harmonic family so a caller with structural knowledge
    can pick the geometrically plausible fundamental.
    """
    sig = col_profile - col_profile.mean()
    if sig.std() < 1e-9:
        return []
    ac = np.correlate(sig, sig, mode="full")[sig.size - 1:]
    lo, hi = int(pitch_min), int(min(pitch_max, sig.size // 2))
    if hi <= lo:
        return []
    seg = ac[lo:hi]
    peak = float(seg.max())
    if peak <= 0:
        return []
    out: list[tuple[float, float]] = []
    for i in range(1, seg.size - 1):
        if seg[i] >= floor_frac * peak and seg[i] >= seg[i - 1] and seg[i] >= seg[i + 1]:
            lag = lo + i
            a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
            denom = a - 2 * b + c
            ref = lag + (0.5 * (a - c) / denom if abs(denom) > 1e-12 else 0.0)
            score = float(seg[i] / peak)
            # merge near-duplicate refined lags
            if not any(abs(ref - p) < 1.0 for p, _ in out):
                out.append((float(ref), score))
    return out


def _cell_empty_frac(line_img: np.ndarray, pitch: float) -> tuple[float, int]:
    """Fraction of interior cells with negligible ink mass at this pitch,
    plus the implied interior cell count.

    On monospace print, cells at the TRUE pitch are almost all occupied; a
    half-pitch lock interleaves glyph centers with inter-character gaps, so
    roughly half its cells are near-empty. Robust and layout-free.
    """
    ink = 1.0 - np.asarray(line_img, dtype=np.float64)
    mass = np.clip(ink - np.median(ink), 0.0, None).sum(axis=0)
    col = grad_profile(ink)
    sig = col - col.mean()
    g_phase, _ = _comb_phase(sig, pitch)
    active = np.where(col > col.mean())[0]
    if active.size == 0:
        return 1.0, 0
    left, right = float(active[0]), float(active[-1])
    j = np.ceil((left - g_phase - pitch / 2.0) / pitch)
    x_start = g_phase + j * pitch
    n = int((right - x_start) // pitch) + 1
    if n < 4:
        return 1.0, max(n, 0)
    masses = []
    for k in range(n):
        c = x_start + k * pitch
        a, b = int(round(c - pitch / 2.0)), int(round(c + pitch / 2.0))
        if a < 0 or b > mass.size:
            continue
        masses.append(mass[a:b].sum())
    if len(masses) < 4:
        return 1.0, n
    m = np.asarray(masses[1:-1])  # interior cells only (edges may be padding)
    med = float(np.median(m[m > 0])) if (m > 0).any() else 0.0
    if med <= 0:
        return 1.0, n
    return float(np.mean(m < 0.30 * med)), n


# Tolerances for layout-consistent pitch discipline.
#
# REL_TOL rationale (recorded per owner instruction): the production
# calibration extractor has, across cal-run01 and cal-run02, accepted
# registrations only inside a 0.8 < pitch/expected < 1.25 band (see
# reader/calibration/extract_v2.py and phased-geometry.json: detected
# fundamental pitches sit within a few percent of span/expected_chars on
# all 276 accepted cal-run02 footer lines). 0.20 relative keeps the proven
# band while comfortably covering print/camera scale and mild perspective
# (synthetic tests exercise both). NOT derived from S46/Bridge.
_LAYOUT_REL_TOL = 0.20
# Neighbor lines of one footer share the print pitch; the structural
# locator already uses 0.14 relative agreement (_PITCH_TOL). Same basis.
_NEIGHBOR_REL_TOL = 0.15
# Occupancy dominance: a half-pitch lock on monospace text leaves ~50% of
# interior cells empty vs ~0-10% at the fundamental (synthetic tests +
# cal-run02 behaviour); 0.20 separation is a conservative margin.
_OCCUPANCY_DOMINANCE = 0.20


def select_pitch(
    line_img: np.ndarray,
    span: float | None = None,
    expected_char_counts: list[int] | None = None,
    neighbor_pitch: float | None = None,
    pitch_min: float = 4.0,
    pitch_max: float = 60.0,
    rel_tol: float = _LAYOUT_REL_TOL,
) -> PitchSelection:
    """Layout-consistent glyph-pitch selection with explicit harmonic
    discipline. GENERIC: uses only public structural information (candidate
    line extent, expected typography char counts from the bound profile,
    neighbor-line pitch, harmonic/occupancy consistency). No per-image or
    damage-family logic, no ground-truth characters.

    Selection rule: a strong harmonic must not defeat a geometrically
    plausible fundamental merely because its raw alignment score is higher.
    Alignment score only breaks ties among plausible candidates.
    """
    ink = 1.0 - np.asarray(line_img, dtype=np.float64)
    col = grad_profile(ink)
    raw = enumerate_pitch_candidates(col, pitch_min, pitch_max)
    # ensure the double of every raw candidate is present: if a half-pitch
    # harmonic dominated the autocorrelation, its fundamental (2x) may sit
    # below the enumeration floor.
    lags = [p for p, _ in raw]
    for p, s in list(raw):
        d = 2.0 * p
        if d <= pitch_max and not any(abs(d - q) < max(1.0, 0.05 * d) for q in lags):
            sig = col - col.mean()
            ac = np.correlate(sig, sig, mode="full")[sig.size - 1:]
            li = int(round(d))
            sc = float(ac[li] / (ac[int(round(lags[0]))] + 1e-12)) if li < ac.size else 0.0
            raw.append((d, max(sc, 0.0)))
            lags.append(d)

    expected = []
    if span and expected_char_counts:
        expected = sorted({span / w for w in expected_char_counts if w > 0})

    cands: list[PitchCandidate] = []
    for p, s in sorted(raw):
        ef, n = _cell_empty_frac(line_img, p)
        lok = None
        if expected:
            lok = any(abs(p / pe - 1.0) <= rel_tol for pe in expected)
        cands.append(PitchCandidate(pitch=p, score=s, cell_count=n,
                                    empty_frac=ef, layout_ok=lok, rejected=None))

    harmonic_rejections: list[dict] = []
    # occupancy dominance: reject p when ~2p exists with clearly lower
    # empty fraction (p is a half-pitch artifact of 2p).
    for c in cands:
        for d in cands:
            if c is d:
                continue
            if abs(d.pitch / (2.0 * c.pitch) - 1.0) <= 0.10 and d.cell_count >= 4 \
                    and c.empty_frac >= d.empty_frac + _OCCUPANCY_DOMINANCE:
                c.rejected = "HALF_PITCH_ARTIFACT"
                harmonic_rejections.append({
                    "rejected_pitch": round(c.pitch, 3),
                    "kept_fundamental": round(d.pitch, 3),
                    "empty_frac_rejected": round(c.empty_frac, 3),
                    "empty_frac_fundamental": round(d.empty_frac, 3),
                    "kind": "half_pitch"})
                break

    pool = [c for c in cands if c.rejected is None]
    method = "occupancy"
    if expected:
        lay = [c for c in pool if c.layout_ok]
        if lay:
            pool, method = lay, "layout"
            for c in cands:
                if c.rejected is None and not c.layout_ok:
                    c.rejected = "LAYOUT_IMPLAUSIBLE"
                    if any(abs(c.pitch / (0.5 * k.pitch) - 1.0) <= 0.10
                           or abs(c.pitch / (2.0 * k.pitch) - 1.0) <= 0.10 for k in pool):
                        harmonic_rejections.append({
                            "rejected_pitch": round(c.pitch, 3),
                            "kind": "layout_implausible_harmonic"})
    if neighbor_pitch:
        nb = [c for c in pool if abs(c.pitch / neighbor_pitch - 1.0) <= _NEIGHBOR_REL_TOL]
        if nb:
            pool = nb

    if pool:
        if method == "layout":
            # Among layout-plausible candidates, the one CLOSEST to an exact
            # layout pitch (span/char_count) wins; alignment score only
            # breaks near-ties. This closes the near-2:1 window overlap
            # between distinct printed line widths (e.g. an 87-char window
            # admitting the half pitch of a 48-char line): the fundamental
            # matches its own width nearly exactly, the harmonic only
            # approximately matches a DIFFERENT width.
            def dev(c: PitchCandidate) -> float:
                return min(abs(c.pitch / pe - 1.0) for pe in expected)
            best = min(pool, key=lambda c: (round(dev(c), 2), -c.score))
        else:
            # No layout evidence separates the harmonic family: keep the
            # historical estimator's rule (smallest strong lag) so behaviour
            # is unchanged except for occupancy-vetoed half-pitch artifacts.
            strong = [c for c in pool if c.score >= 0.8]
            best = min(strong, key=lambda c: c.pitch) if strong \
                else max(pool, key=lambda c: c.score)
        return PitchSelection(best.pitch, method, cands, expected, rel_tol,
                              neighbor_pitch, harmonic_rejections)
    # honest fallback: no structural evidence separates candidates — use
    # the historical estimator so behaviour on non-footer content is
    # unchanged, and record it.
    legacy = estimate_pitch(col, pitch_min, pitch_max)
    return PitchSelection(legacy, "legacy_fallback", cands, expected, rel_tol,
                          neighbor_pitch, harmonic_rejections)


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


def register_line(line_img: np.ndarray, n_cells_hint: int | None = None,
                  pitch_hint: float | None = None) -> LineModel:
    """Full per-line registration: path + pitch + drift model.

    `pitch_hint` overrides autocorrelation pitch estimation when the caller
    knows the print geometry a priori (calibration sheets with a known
    layout); production reading never passes it."""
    ink = 1.0 - np.asarray(line_img, dtype=np.float64)
    col = grad_profile(ink)
    pitch = float(pitch_hint) if pitch_hint else estimate_pitch(col)
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

    # Hinted cell count: the n-cell window must sit ON the printed run.
    # The left-edge snap can land one pitch early/late (padding noise, a
    # faint first glyph), which would shift every later cell by one — so
    # slide the whole window by integer pitches and keep the placement
    # covering the most ink. Purely image-driven; no layout content used.
    if n_cells_hint is not None and n_cells > 0:
        # Placement must ignore ink that bleeds in from vertically adjacent
        # lines through the crop padding — that foreign ink lives in the top
        # and bottom pad rows, so judge placement on the central rows only.
        h = ink.shape[0]
        core = ink[h // 4: h - h // 4, :] if h >= 8 else ink
        core_mass = np.clip(core - np.median(core), 0.0, None).sum(axis=0)

        def window_mass(x0: float) -> float:
            tot = 0.0
            for k in range(n_cells):
                c = x0 + k * pitch
                a, b = int(round(c - pitch / 2.0)), int(round(c + pitch / 2.0))
                if b <= 0 or a >= core_mass.size:
                    continue
                tot += float(core_mass[max(a, 0):min(b, core_mass.size)].sum())
            return tot
        shifts = [s for s in range(-4, 5)]
        best_s = max(shifts, key=lambda s: (window_mass(x_start + s * pitch),
                                            -abs(s)))
        if best_s:
            x_start += best_s * pitch

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
