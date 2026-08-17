"""Deterministic calibration bank builder (Reader v0.2.1, Task 10).

Builds a real-print glyph bank from extracted GlyphSamples using the same
feature pipeline as the frozen spike classifier (scale-normalize to the
19x34+3px window, CLAHE-free here — windows are already local strips —
centroid align, gray+Sobel z-score features, L2 normalized). The bank is
deterministic: same samples + same params → byte-identical npz + manifest.

Provenance is mandatory. The manifest records every contributing capture
SHA-256, and building FAILS (ProvenanceError) if any contributing hash
belongs to a corpus whose flags forbid classifier training (Bridge Run 01).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from reader.calibration.extract import GlyphSample
from reader.provenance import assert_no_banned_hashes
from reader.spike_bank_classifier import _centroid_align, _feat_from_gray

BANK_FORMAT_VERSION = 1
FEATURE_VERSION = "spike-feat-v1"  # same features as the frozen spike bank
WIN_W, WIN_H, PAD = 19, 34, 3


def sample_feature(s: GlyphSample) -> np.ndarray | None:
    win = np.asarray(s.window, dtype=np.float64)
    if win.max() <= 1.5:
        win = win * 255.0
    full = np.clip(win, 0, 255).astype(np.uint8)
    full = cv2.resize(full, (WIN_W + 2 * PAD, WIN_H + 2 * PAD),
                      interpolation=cv2.INTER_AREA)
    aligned, blank = _centroid_align(full, WIN_W, WIN_H, PAD)
    if blank:
        return None
    return _feat_from_gray(aligned).astype(np.float32)


def build_bank(
    samples: Iterable[GlyphSample],
    out_npz: Path,
    out_manifest: Path,
    bank_id: str,
    corpus_id: str,
    max_per_class: int | None = None,
) -> dict:
    """Build bank npz + provenance manifest. Deterministic; fails on
    banned provenance or existing outputs."""
    if out_npz.exists() or out_manifest.exists():
        raise SystemExit(f"refusing to overwrite existing bank {out_npz}")

    ordered = sorted(
        samples, key=lambda s: (s.capture_sha256, s.sheet_id, s.line, s.col)
    )
    hashes = sorted({s.capture_sha256 for s in ordered})
    assert_no_banned_hashes(hashes)

    feats: list[np.ndarray] = []
    labels: list[str] = []
    per_class: dict[str, int] = {}
    for s in ordered:
        if max_per_class is not None and per_class.get(s.label, 0) >= max_per_class:
            continue
        v = sample_feature(s)
        if v is None:
            continue
        feats.append(v)
        labels.append(s.label)
        per_class[s.label] = per_class.get(s.label, 0) + 1

    if not feats:
        raise SystemExit("no usable samples; refusing to write an empty bank")

    out_npz.parent.mkdir(parents=True, exist_ok=True)
    # deterministic npz (no compression timestamps issue: savez is zip with
    # fixed names; use uncompressed savez for byte stability)
    np.savez(
        out_npz,
        features=np.stack(feats),
        labels=np.array(labels),
        pitch_ref=np.array([18.8]),
        win_w=np.array([WIN_W]),
        win_h=np.array([WIN_H]),
        pad=np.array([PAD]),
    )
    manifest = {
        "bank_format_version": BANK_FORMAT_VERSION,
        "bank_id": bank_id,
        "feature_version": FEATURE_VERSION,
        "corpus_id": corpus_id,
        "capture_sha256s": hashes,
        "n_samples": len(labels),
        "per_class_counts": {k: per_class[k] for k in sorted(per_class)},
        "npz_sha256": hashlib.sha256(out_npz.read_bytes()).hexdigest(),
        "status": "DEVELOPMENT / NOT GATE-A1 / NOT PRODUCTION",
        "prohibitions": [
            "Bridge Run 01 hashes are banned from this provenance list (enforced).",
            "This bank must not be presented as Gate A1 evidence.",
        ],
    }
    out_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
