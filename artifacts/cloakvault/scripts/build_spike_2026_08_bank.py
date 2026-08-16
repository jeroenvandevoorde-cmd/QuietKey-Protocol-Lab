"""Task 0: build the frozen historical profile "spike-2026-08".

Binds, byte-identified by SHA-256:
  - the spike glyph bank built from baseline captures S01 and S02 ONLY,
    via the spike's own frozen code path (spike/reader/gatea_nn_layer.py
    build_global_bank -> spike_reader rectify/enhance/find_token_lines),
  - the spike feature and normalization pipeline (feat_from_gray,
    centroid_align, CLAHE enhance, 19x34 windows, blur sigmas 0/0.8/1.4/2.0),
  - conf_floor 0.64, margin_floor 0.02.

No Bridge Run 01 image is used for training. No threshold is changed.
The spike source files are imported unmodified (they are frozen as-run:
they expect cwd = spike/captures and GT at /tmp/qkcheck/...; this script
satisfies both externally rather than editing them).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]  # artifacts/cloakvault
SPIKE_READER = ROOT / "spike" / "reader"
CAPTURES = ROOT / "spike" / "captures"
BASELINES = ["baseline-0-std-S01..jpeg", "baseline-0-std-S02.jpeg"]  # S01 file has a double dot as uploaded
BANK_OUT = ROOT / "reader" / "banks" / "spike-2026-08-bank.npz"
PROFILE_OUT = ROOT / "reader" / "profiles" / "spike-2026-08.json"
DEV_PROFILE = ROOT / "reader" / "profiles" / "spike-reader-v02-development.json"


def ensure_spike_env() -> None:
    # spike_reader.py loads GT from the historical absolute path; provide it.
    qk = Path("/tmp/qkcheck/artifacts/cloakvault")
    if not qk.exists():
        qk.parent.mkdir(parents=True, exist_ok=True)
        os.makedirs(qk.parent, exist_ok=True)
        qk.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(ROOT, qk)
        except FileExistsError:
            pass
    sys.path.insert(0, str(SPIKE_READER))


def main() -> None:
    ensure_spike_env()
    os.chdir(CAPTURES)  # spike code takes bare filenames relative to captures
    import gatea_nn_layer as nn  # frozen spike code, imported unmodified
    import spike_reader as sr

    for b in BASELINES:
        assert (CAPTURES / b).exists(), f"missing baseline capture: {b}"

    feats, labels = nn.build_global_bank(BASELINES)
    # Reference grid pitch at spike rect scale (needed for scale-normalized
    # window extraction in the reader adapter; a measurement, not a tunable).
    pitches = []
    for b in BASELINES:
        blocks = sr.find_token_lines(sr.rectify(b))
        assert len(blocks) == 5
        _, pc = nn.line_grid(blocks)
        pitches.append(pc)
    pitch_ref = float(np.median(pitches))

    BANK_OUT.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        BANK_OUT,
        features=feats.astype(np.float32),
        labels=np.array(labels),
        pitch_ref=np.array([pitch_ref]),
        win_w=np.array([nn.WIN_W]), win_h=np.array([nn.WIN_H]), pad=np.array([nn.PAD]),
    )
    bank_sha = hashlib.sha256(BANK_OUT.read_bytes()).hexdigest()

    dev = json.loads(DEV_PROFILE.read_text())
    profile = {
        "profile_format_version": 1,
        "reader_version": "0.2-dev",
        "status": "DEVELOPMENT / NOT GATE-A1 / NOT PRODUCTION",
        "profile_id": "spike-2026-08",
        "purpose": "Task 0 diagnosis experiment ONLY: frozen historical spike bank replayed through Reader v0.2. Not a calibration; not a candidate production profile.",
        "confidence_floor": 0.64,
        "margin_floor": 0.02,
        "confidence_floor_note": "Frozen historical spike operating point (verdict_analysis.py CF/MF). Not tuned; not to be tuned.",
        "capture_quality": dev["capture_quality"],
        "capture_quality_note": "Same v0.2 development gate thresholds; Task 0 runs the gate in REPORT-ONLY mode (verdict logged, never blocks).",
        "classifier_id": "spike-gatea-nn-pooled-bank (baseline-0-std-S01 + baseline-0-std-S02, blur sigmas 0/0.8/1.4/2.0, gray+Sobel z-score features, per-class max NN)",
        "glyph_bank": {
            "path": str(BANK_OUT.relative_to(ROOT)),
            "sha256": bank_sha,
            "samples": int(feats.shape[0]),
            "feature_dim": int(feats.shape[1]),
            "pitch_ref_rect_px": pitch_ref,
            "training_captures": BASELINES,
            "training_note": "Built exclusively from spike baseline captures S01 and S02 via frozen spike code. No Bridge Run 01 image used.",
        },
        "registration_model_id": "perline-robust-piecewise-phase-v1",
        "calibration_corpora": [
            "spike baseline captures S01+S02 (historical, pre-Bridge; harvested by frozen spike pipeline)"
        ],
        "validation_corpora_note": "Bridge Run 01 is seen development material; Task 0 results are diagnosis, not validation.",
        "created": str(date.today()),
        "source_commit": None,
        "warning": "HISTORICAL DIAGNOSIS PROFILE. DEVELOPMENT ONLY. NOT GATE-A1. NOT PRODUCTION.",
    }
    PROFILE_OUT.write_text(json.dumps(profile, indent=2) + "\n")
    print(json.dumps({
        "bank": str(BANK_OUT), "bank_sha256": bank_sha,
        "samples": int(feats.shape[0]), "feature_dim": int(feats.shape[1]),
        "pitch_ref_rect_px": pitch_ref,
        "profile": str(PROFILE_OUT),
        "profile_sha256": hashlib.sha256(PROFILE_OUT.read_bytes()).hexdigest(),
    }, indent=2))


if __name__ == "__main__":
    main()
