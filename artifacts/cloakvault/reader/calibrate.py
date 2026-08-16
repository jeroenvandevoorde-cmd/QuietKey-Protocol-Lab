"""Calibration path: calibration corpus → parameters → candidate profile.

Calibration MAY optimize/tune. Its output profile must identify the corpus
used and is always written as a NEW candidate file marked DEVELOPMENT /
NOT GATE-A1 / NOT PRODUCTION. Formal Gate A1 will recalibrate and freeze
using its own calibration corpus.

Deliberately separate from validate.py, which can never tune.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path

import numpy as np

from .profile import DEVELOPMENT_STATUS, load_profile
from .quality import _as_gray, laplacian_variance


def _load_images(corpus_dir: Path) -> list[tuple[str, np.ndarray]]:
    imgs = []
    for p in sorted(corpus_dir.glob("*.npy")):
        imgs.append((p.name, np.load(p)))
    return imgs


def calibrate(corpus_dir: Path, base_profile: Path, out_path: Path, corpus_id: str) -> dict:
    base = load_profile(base_profile)
    images = _load_images(corpus_dir)
    if not images:
        raise SystemExit(f"no .npy images in calibration corpus {corpus_dir}")
    data = json.loads(json.dumps(base.data))  # deep copy

    # Example calibration: set the sharpness floor from the corpus
    # distribution (25th percentile * 0.5). Calibration may tune; the
    # frozen spike classifier operating point (0.64 / 0.02) is NOT tuned.
    lvs = [laplacian_variance(_as_gray(img)) for _, img in images]
    data["capture_quality"]["sharpness_min_laplacian_var"] = round(
        float(np.percentile(lvs, 25)) * 0.5, 6
    )

    data["status"] = DEVELOPMENT_STATUS
    data["calibration_corpora"] = [corpus_id]
    data["created"] = datetime.date.today().isoformat()
    data["warning"] = base.data["warning"]
    if out_path.exists():
        raise SystemExit(f"refusing to overwrite existing profile {out_path}; choose a new name")
    out_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    return {
        "profile_written": str(out_path),
        "profile_sha256": hashlib.sha256(out_path.read_bytes()).hexdigest(),
        "corpus_id": corpus_id,
        "images": len(images),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Reader v0.2 calibration (may tune; writes NEW candidate profile)")
    ap.add_argument("--corpus", required=True, type=Path)
    ap.add_argument("--corpus-id", required=True)
    ap.add_argument("--base-profile", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    print(json.dumps(calibrate(a.corpus, a.base_profile, a.out, a.corpus_id), indent=2))


if __name__ == "__main__":
    main()
