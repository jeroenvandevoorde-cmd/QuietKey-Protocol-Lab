"""Regression tests (owner Task 9): provenance guarantees for the
production-domain parity diagnostic.

- Bridge hashes are prohibited from bank construction.
- S46 (DEVELOPMENT_REPLAY only) cannot enter calibration holdout folds.
- The cal-run02 production corpus manifest enforces two-copy provenance
  separation and keeps all usage flags off until captures are registered.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from reader.calibration.bank import build_bank
from reader.calibration.evaluate import grouped_holdout
from reader.calibration.extract import GlyphSample
from reader.provenance import ProvenanceError, corpus_image_hashes

ROOT = Path(__file__).resolve().parents[2]
S46_SHA = "bf1b1de98b23d7d4c3120968ce02e3c64ec49031b880309cc6c3581be08d4b8a"
MANIFEST = ROOT / "reader" / "corpora" / "cal-run02-production-raw.json"
GT = (ROOT / "reader" / "calibration" / "sheets" /
      "calibration-sheet-calsheet-production-v2-s20260817.groundtruth.json")


def _sample(sha: str, label: str = "q") -> GlyphSample:
    rng = np.random.default_rng(0)
    win = (rng.random((34, 19)) * 255).astype(np.float64)
    return GlyphSample(label=label, window=win, pitch=21.0,
                       capture_sha256=sha, sheet_id="test", block=0, line=0, col=0)


def test_s46_sha_is_a_registered_bridge_hash():
    assert S46_SHA in corpus_image_hashes("bridge-run01-development")


def test_bridge_hashes_prohibited_from_bank_construction(tmp_path):
    samples = [_sample(S46_SHA, l) for l in "qpzry9x8"]
    with pytest.raises(ProvenanceError):
        build_bank(samples, tmp_path / "banned-bank.npz",
                   tmp_path / "banned-bank.manifest.json",
                   bank_id="banned-test", corpus_id="bridge-run01-development")
    assert not (tmp_path / "banned-bank.npz").exists()


def test_s46_cannot_enter_calibration_holdout_folds():
    samples = [_sample(S46_SHA, "q"), _sample("a" * 64, "p")]
    with pytest.raises(ProvenanceError):
        grouped_holdout(samples)


def test_cal_run02_manifest_two_copy_provenance():
    m = json.loads(MANIFEST.read_text())
    assert m["corpus_id"] == "cal-run02-production-raw"
    assert m["required_print_copies"] >= 2
    rules = m["provenance_rules"]
    assert rules["bridge_hashes_prohibited"] is True
    assert set(rules["distinct_print_copy_ids_required"]) == {"copy1", "copy2"}
    assert "print_copy" in rules["per_image_required_fields"]
    assert rules["s46_development_replay_only"] is True
    # Captures registered 2026-08-17: 2 copies x 3 conditions x 2 pages.
    flags = m["usage_flags"]
    assert len(m["images"]) == 12
    assert flags["classifier_training_allowed"] is True
    assert flags["calibration_allowed"] is True
    # copy2 is the transfer TARGET: evaluation-only, never trains a bank
    assert flags["training_copy_restriction"] == "copy1"
    assert flags["validation_allowed"] is False
    assert flags["regression_testing_allowed"] is False
    seen = set()
    for im in m["images"]:
        for f in rules["per_image_required_fields"]:
            assert im.get(f), f"{im.get('filename')} missing {f}"
        assert im["print_copy"] in {"copy1", "copy2"}
        assert im["page"] in (1, 2)
        expected = list(range(0, 8)) if im["page"] == 1 else list(range(8, 16))
        assert im["page_footer_indices"] == expected
        assert len(im["sha256"]) == 64
        seen.add((im["print_copy"], im["condition"], im["capture_id"], im["page"]))
    assert {c for c, *_ in seen} == {"copy1", "copy2"}
    assert len(seen) == 12  # no duplicate capture slots
    # no Bridge hashes may ever be listed
    bridge = corpus_image_hashes("bridge-run01-development")
    assert not ({im.get("sha256") for im in m["images"]} & bridge)


def test_production_sheet_groundtruth_provenance():
    gt = json.loads(GT.read_text())
    assert gt["generator"] == "calsheet-production-v2"
    prov = gt["rendering_provenance"]
    # renderer reuse is recorded and pinned by source hashes
    assert any("renderFooter" in s for s in prov["reused_production_code"])
    assert set(prov["source_sha256"]) == {
        "src/lib/codec/footer.ts", "src/lib/pipeline.ts",
        "src/pages/create.tsx", "src/index.css",
    }
    import hashlib
    for rel, recorded in prov["source_sha256"].items():
        actual = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        assert actual == recorded, f"{rel} drifted since sheet generation"
    # balanced classes, full alphabet
    assert len(gt["class_counts"]) == 32
    assert set(gt["class_counts"].values()) == {71}
    assert gt["provenance_rules"]["bridge_hashes_prohibited"] is True
