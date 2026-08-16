"""Spike historical glyph-bank classifier for Reader v0.2 (Task 0 diagnosis).

Wraps the FROZEN spike feature and normalization pipeline
(spike/reader/gatea_nn_layer.py: centroid_align + feat_from_gray, CLAHE
enhance, 19x34 windows with 3px pad, per-class max nearest-neighbour) so
the reader's CLASSIFICATION stage can score cells against the historical
S01+S02 bank instead of the synthetic development templates.

Fidelity notes (documented, not hidden):
- The spike operated on a perspective-rectified 2480x3508 page where the
  print pitch measured ~18.8 px, equal to the 19 px window width. Reader
  v0.2 works on the raw capture, so each cell window is extracted at the
  line's MEASURED pitch and scale-normalized (resized) to the spike's
  window geometry before feature extraction. This is a unit conversion,
  not a new feature pipeline.
- CLAHE enhancement (clipLimit 2.5, tile 16x16 — spike enhance()) is
  applied to the line strip before window extraction, matching the spike's
  rect_e input.
- Thresholding is the spike rule verbatim: '?' when c1 < conf_floor or
  (c1 - c2) < margin_floor.

No Bridge image contributes to the bank; nothing here tunes a threshold.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


class SpikeBank:
    def __init__(self, npz_path: str | Path):
        d = np.load(npz_path, allow_pickle=False)
        self.features = d["features"].astype(np.float32)   # (N, 1292) L2-normalized
        self.labels = np.array(d["labels"])                 # (N,) single chars
        self.pitch_ref = float(d["pitch_ref"][0])
        self.win_w = int(d["win_w"][0])
        self.win_h = int(d["win_h"][0])
        self.pad = int(d["pad"][0])


def _centroid_align(win: np.ndarray, win_w: int, win_h: int, pad: int):
    """Byte-for-byte the spike's centroid_align logic (gatea_nn_layer.py)."""
    inner = win[pad:pad + win_h, pad:pad + win_w].astype(np.float64)
    ink = np.clip(inner.mean() - inner, 0, None)
    tot = ink.sum()
    if tot < 1e-3:
        return win[pad:pad + win_h, pad:pad + win_w], True
    xs = np.arange(win_w)
    ys = np.arange(win_h)
    cx = (ink.sum(0) * xs).sum() / tot
    cy = (ink.sum(1) * ys).sum() / tot
    dx = max(-pad, min(pad, int(round(cx - (win_w - 1) / 2))))
    dy = max(-pad, min(pad, int(round(cy - (win_h - 1) / 2))))
    return win[pad + dy:pad + dy + win_h, pad + dx:pad + dx + win_w], False


def _feat_from_gray(g: np.ndarray) -> np.ndarray:
    """Byte-for-byte the spike's feat_from_gray (gray + Sobel magnitude z-scores)."""
    g = g.astype(np.float32)
    gz = (g - g.mean()) / (g.std() + 1e-6)
    sx = cv2.Sobel(g, cv2.CV_32F, 1, 0, 3)
    sy = cv2.Sobel(g, cv2.CV_32F, 0, 1, 3)
    mag = np.sqrt(sx * sx + sy * sy)
    mz = (mag - mag.mean()) / (mag.std() + 1e-6)
    v = np.concatenate([gz.ravel(), mz.ravel()])
    return v / (np.linalg.norm(v) + 1e-9)


def make_spike_classifier(bank: SpikeBank):
    """Return classify(line_img, centers, y_center, conf_floor, margin_floor)
    with the same contract as reader.synthglyphs.classify_cells."""
    W, H, P = bank.win_w, bank.win_h, bank.pad
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(16, 16))  # spike enhance()
    classes = np.unique(bank.labels)
    class_idx = {c: np.flatnonzero(bank.labels == c) for c in classes}

    def classify(line_img: np.ndarray, centers: np.ndarray, y_center: float,
                 confidence_floor: float, margin_floor: float, alphabet: str = ""):
        img = np.asarray(line_img, dtype=np.float64)
        if img.max() <= 1.5:
            img = img * 255.0
        strip = clahe.apply(np.clip(img, 0, 255).astype(np.uint8))
        pitch = float(np.median(np.diff(centers))) if len(centers) > 1 else bank.pitch_ref
        s = pitch / bank.pitch_ref  # raw px per spike-rect px
        ww = max(3, int(round((W + 2 * P) * s)))
        wh = max(3, int(round((H + 2 * P) * s)))
        chars: list[str] = []
        confs: list[float] = []
        margins: list[float] = []
        for cx in centers:
            x0 = int(round(cx - ww / 2))
            y0 = int(round(y_center - wh / 2))
            win = strip[max(0, y0):y0 + wh, max(0, x0):x0 + ww]
            full = np.full((wh, ww), 255, np.uint8)
            if win.size:
                full[:win.shape[0], :win.shape[1]] = win
            win = cv2.resize(full, (W + 2 * P, H + 2 * P), interpolation=cv2.INTER_AREA)
            a, blank = _centroid_align(win, W, H, P)
            if blank:
                chars.append("?"); confs.append(0.0); margins.append(0.0)
                continue
            v = _feat_from_gray(a)
            sc = bank.features @ v
            per = {c: float(sc[idx].max()) for c, idx in class_idx.items()}
            rk = sorted(per.items(), key=lambda t: -t[1])
            c1, c2 = rk[0][1], rk[1][1]
            if c1 < confidence_floor or (c1 - c2) < margin_floor:
                chars.append("?")
            else:
                chars.append(rk[0][0])
            confs.append(c1); margins.append(c1 - c2)
        return "".join(chars), confs, margins

    return classify
