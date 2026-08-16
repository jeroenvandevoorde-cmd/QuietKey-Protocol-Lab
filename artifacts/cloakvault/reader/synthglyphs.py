"""Deterministic synthetic glyph bank and page renderer — engineering tests only.

Renders known token-like monospace lines and applies controlled geometric
transformations so the registration/locator algorithms can be exercised
independently of Bridge-specific layouts. These synthetic images do NOT
count as Gate A evidence.

Glyph bitmaps are deterministic 5x7 patterns derived from SHA-256 of the
character (development classifier only; terminal glyph templates require
separate calibration).
"""
from __future__ import annotations

import hashlib

import numpy as np

GLYPH_W, GLYPH_H = 5, 7
CELL_W, CELL_H = 8, 12  # cell with margins
ALPHABET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l" + "abcdefghijklmnopqrstuvwxyz0123456789:/?.&=_-,"


def glyph_bitmap(ch: str) -> np.ndarray:
    """Deterministic, distinct 5x7 bitmap for a character."""
    digest = hashlib.sha256(("QK-GLYPH:" + ch).encode()).digest()
    bits = np.unpackbits(np.frombuffer(digest, dtype=np.uint8))[: GLYPH_W * GLYPH_H]
    bmp = bits.reshape(GLYPH_H, GLYPH_W).astype(np.float64)
    bmp[0, GLYPH_W // 2] = 1.0  # guarantee some top ink (aids line banding)
    return bmp


_BANK: dict[str, np.ndarray] = {}


def glyph_cell(ch: str) -> np.ndarray:
    """Glyph placed in a CELL_H x CELL_W cell (ink=1)."""
    if ch not in _BANK:
        cell = np.zeros((CELL_H, CELL_W))
        if not ch.isspace():
            y0 = (CELL_H - GLYPH_H) // 2
            x0 = (CELL_W - GLYPH_W) // 2
            cell[y0 : y0 + GLYPH_H, x0 : x0 + GLYPH_W] = glyph_bitmap(ch)
        _BANK[ch] = cell
    return _BANK[ch]


PAPER = 0.88  # realistic paper reflectance; 1.0 would mimic saturation/glare


def render_line(text: str, pad: int = 12) -> np.ndarray:
    """Render a monospace text line: paper ~PAPER, dark ink (~0)."""
    cells = [glyph_cell(c) for c in text]
    ink = np.concatenate(cells, axis=1) if cells else np.zeros((CELL_H, 1))
    img = np.full((CELL_H + 2 * pad // 2, ink.shape[1] + 2 * pad), PAPER)
    img[pad // 2 : pad // 2 + CELL_H, pad : pad + ink.shape[1]] -= 0.85 * ink
    return img


def render_page(lines: list[str], width: int | None = None, top_blank: int = 120) -> np.ndarray:
    """Render lines near the bottom of a taller 'page' image."""
    imgs = [render_line(t) for t in lines]
    w = width or max(i.shape[1] for i in imgs)
    rows = [np.full((top_blank, w), PAPER)]
    for im in imgs:
        canvas = np.full((im.shape[0] + 4, w), PAPER)
        canvas[2 : 2 + im.shape[0], : min(w, im.shape[1])] = im[:, : min(w, im.shape[1])]
        rows.append(canvas)
    rows.append(np.full((20, w), PAPER))
    return np.concatenate(rows, axis=0)


# ── deterministic geometric transforms (inverse-mapped bilinear) ─────────────

def _sample_bilinear(img: np.ndarray, ys: np.ndarray, xs: np.ndarray, fill: float = 0.88) -> np.ndarray:
    h, w = img.shape
    y0 = np.floor(ys).astype(int)
    x0 = np.floor(xs).astype(int)
    fy, fx = ys - y0, xs - x0
    out = np.full(ys.shape, fill)
    valid = (y0 >= 0) & (y0 < h - 1) & (x0 >= 0) & (x0 < w - 1)
    yv, xv = y0[valid], x0[valid]
    fyv, fxv = fy[valid], fx[valid]
    out[valid] = (
        img[yv, xv] * (1 - fyv) * (1 - fxv)
        + img[yv + 1, xv] * fyv * (1 - fxv)
        + img[yv, xv + 1] * (1 - fyv) * fxv
        + img[yv + 1, xv + 1] * fyv * fxv
    )
    return out


def apply_phase_drift(img: np.ndarray, max_drift_px: float) -> np.ndarray:
    """Smooth horizontal phase drift: x' = x + drift(x), linear ramp."""
    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    drift = max_drift_px * (xx / (w - 1))
    return _sample_bilinear(img, yy, xx + drift)


def apply_bow(img: np.ndarray, bow_px: float) -> np.ndarray:
    """Mild vertical line bow: y' = y + bow * sin(pi * x / w)."""
    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    return _sample_bilinear(img, yy + bow_px * np.sin(np.pi * xx / (w - 1)), xx)


def apply_perspective(img: np.ndarray, shrink_frac: float) -> np.ndarray:
    """Global perspective: top edge horizontally shrunk by shrink_frac."""
    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    scale = 1.0 / (1.0 - shrink_frac * (1.0 - yy / (h - 1)))
    cx = (w - 1) / 2.0
    return _sample_bilinear(img, yy, cx + (xx - cx) * scale)


def apply_local_fold(img: np.ndarray, x0: int, width: int, dx: float) -> np.ndarray:
    """Fold-like local horizontal displacement in [x0, x0+width]."""
    h, w = img.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    bump = np.clip(1.0 - np.abs(xx - (x0 + width / 2)) / (width / 2), 0, 1)
    return _sample_bilinear(img, yy, xx + dx * bump)


def apply_occlusion(img: np.ndarray, x0: int, width: int, value: float = 0.15) -> np.ndarray:
    out = img.copy()
    out[:, x0 : x0 + width] = value
    return out


def apply_blur(img: np.ndarray, k: int) -> np.ndarray:
    """Separable box blur, kernel size k (odd)."""
    if k <= 1:
        return img
    ker = np.ones(k) / k
    out = np.apply_along_axis(lambda r: np.convolve(r, ker, mode="same"), 1, img)
    return np.apply_along_axis(lambda c: np.convolve(c, ker, mode="same"), 0, out)


def apply_illumination(img: np.ndarray, strength: float) -> np.ndarray:
    """Uneven illumination: multiplicative horizontal ramp."""
    h, w = img.shape
    ramp = 1.0 - strength * (np.arange(w) / (w - 1))
    return np.clip(img * ramp[None, :], 0, 1)


# ── development classifier (synthetic bank NCC) ─────────────────────────────

def classify_cells(
    line_img: np.ndarray,
    centers: np.ndarray,
    y_center: float,
    confidence_floor: float,
    margin_floor: float,
    alphabet: str = ALPHABET,
) -> tuple[str, list[float], list[float]]:
    """Classify glyph cells by normalized cross-correlation with the bank.

    Uncertainty becomes erasure '?' (confidence or margin below floors);
    the classifier never guesses. Returns (text, confidences, margins).
    """
    templates = {c: glyph_cell(c) for c in alphabet if not c.isspace()}
    tnorm = {c: (t - t.mean(), np.linalg.norm(t - t.mean()) + 1e-12) for c, t in templates.items()}
    out, confs, margins = [], [], []
    for cx in centers:
        # deterministic local snap: NCC is evaluated on a small +/- offset
        # grid and the best-scoring alignment wins (subpixel registration
        # residue must not masquerade as low glyph confidence).
        best, second, best_c = -1.0, -1.0, "?"
        for dy in (-1, 0, 1):
            for dx in (-2, -1, 0, 1, 2):
                y0 = int(round(y_center - CELL_H / 2)) + dy
                x0 = int(round(cx - CELL_W / 2)) + dx
                if y0 < 0 or x0 < 0 or y0 + CELL_H > line_img.shape[0] or x0 + CELL_W > line_img.shape[1]:
                    continue
                patch = 1.0 - line_img[y0 : y0 + CELL_H, x0 : x0 + CELL_W]
                p = patch - patch.mean()
                pn = np.linalg.norm(p) + 1e-12
                loc_best, loc_second, loc_c = -1.0, -1.0, "?"
                for c, (tt, tn) in tnorm.items():
                    score = float((p * tt).sum() / (pn * tn))
                    if score > loc_best:
                        loc_second, loc_best, loc_c = loc_best, score, c
                    elif score > loc_second:
                        loc_second = score
                if loc_best > best:
                    best, second, best_c = loc_best, loc_second, loc_c
        conf, margin = best, best - second
        if conf < confidence_floor or margin < margin_floor:
            out.append("?")
        else:
            out.append(best_c)
        confs.append(conf)
        margins.append(margin)
    return "".join(out), confs, margins
