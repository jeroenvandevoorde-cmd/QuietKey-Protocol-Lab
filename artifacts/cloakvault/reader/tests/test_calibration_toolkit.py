"""Reader v0.2.1 calibration toolkit tests (Phase A, synthetic only).

Covers: deterministic sheet generation, known-layout extraction, bank
determinism, Bridge-hash provenance ban, grouped-holdout leakage rules.
No real calibration captures exist yet; everything here runs on synthetic
renders (engineering tests, NOT Gate A evidence).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from reader.calibration.bank import build_bank
from reader.calibration.evaluate import grouped_holdout
from reader.calibration.extract import extract_capture
from reader.provenance import (
    BRIDGE_RUN01_CORPUS_ID,
    ProvenanceError,
    assert_no_banned_hashes,
    load_corpus_manifest,
    require_flag,
)
from reader.synthglyphs import render_page
from scripts.gen_calibration_sheet import BECH32_CHARSET, build_lines, generate


# ---------- sheet generator (Task 5) ----------

def test_sheet_generator_deterministic(tmp_path):
    a = generate(1234, tmp_path / "a")
    b = generate(1234, tmp_path / "b")
    assert a["html_sha256"] == b["html_sha256"]
    c = generate(1235, tmp_path / "c")
    assert c["html_sha256"] != a["html_sha256"]


def test_sheet_charset_is_bech32_with_equal_counts(tmp_path):
    r = generate(42, tmp_path)
    gt = json.loads(Path(r["groundtruth"]).read_text())
    assert set(gt["charset"]) == set(BECH32_CHARSET)
    assert {"c", "v", "0"} <= set(gt["charset"])  # sentinel coverage
    counts = gt["per_class_count"]
    assert len(set(counts.values())) == 1  # exactly equal per-class counts
    all_text = "".join(gt["lines"])
    assert set(all_text) <= set(BECH32_CHARSET)


def test_sheet_content_not_periodic():
    lines = build_lines(7)
    text = "".join(lines)
    arr = np.frombuffer(text.encode(), dtype=np.uint8).astype(float)
    arr = arr - arr.mean()
    for lag in (1, 2, 4, 8, 48):
        r = float(np.corrcoef(arr[:-lag], arr[lag:])[0, 1])
        assert abs(r) < 0.1, f"periodic artifact at lag {lag}: r={r}"


# ---------- provenance guards (Tasks 4/10) ----------

def test_bridge_corpus_flags_forbid_training_and_validation():
    data = load_corpus_manifest(BRIDGE_RUN01_CORPUS_ID)
    flags = data["usage_flags"]
    assert flags["classifier_training_allowed"] is False
    assert flags["threshold_calibration_allowed"] is False
    assert flags["validation_use_allowed"] is False
    assert flags["gate_a1_evidence_allowed"] is False
    assert flags["locator_development_allowed"] is True
    with pytest.raises(ProvenanceError):
        require_flag(BRIDGE_RUN01_CORPUS_ID, "classifier_training_allowed")
    require_flag(BRIDGE_RUN01_CORPUS_ID, "regression_testing_allowed")


def test_bridge_hashes_banned_from_bank_provenance():
    data = load_corpus_manifest(BRIDGE_RUN01_CORPUS_ID)
    a_bridge_hash = data["images"][0]["sha256"]
    with pytest.raises(ProvenanceError):
        assert_no_banned_hashes(["deadbeef" * 8, a_bridge_hash])
    assert_no_banned_hashes(["deadbeef" * 8])  # non-bridge is fine


# ---------- known-layout extractor (Task 8) ----------

def _mini_gt(n_lines=4):
    lines = build_lines(99)[:n_lines]
    return {
        "sheet_id": "test-mini",
        "chars_per_line": 48,
        "lines_per_block": 2,
        "blocks": (n_lines + 1) // 2,
        "lines": lines,
    }


def test_extractor_recovers_labels_on_synthetic_render():
    gt = _mini_gt()
    img = render_page(gt["lines"])
    res = extract_capture(img, gt, "cap-synth-1")
    assert res.lines_used == len(gt["lines"])
    assert len(res.samples) == len(gt["lines"]) * 48
    # labels must line up with ground truth exactly
    for s in res.samples[:96]:
        assert s.label == gt["lines"][s.line][s.col]


def test_extractor_rejects_line_count_mismatch():
    gt = _mini_gt(4)
    img = render_page(gt["lines"][:3])  # one line missing from "capture"
    res = extract_capture(img, gt, "cap-synth-bad")
    assert res.samples == []
    assert any("LINE_COUNT" in d["reason"] for d in res.lines_dropped)


# ---------- bank builder determinism + ban (Task 10) ----------

def _synthetic_samples(capture_id: str, noise_seed: int | None = None):
    gt = _mini_gt()
    img = render_page(gt["lines"])
    if noise_seed is not None:
        rng = np.random.default_rng(noise_seed)
        img = np.clip(img + rng.normal(0, 0.02, img.shape), 0, 1)
    return extract_capture(img, gt, capture_id).samples


def test_bank_build_is_deterministic(tmp_path):
    samples = _synthetic_samples("cap-a")
    m1 = build_bank(samples, tmp_path / "b1.npz", tmp_path / "b1.json",
                    "bank-test", "corpus-test")
    m2 = build_bank(samples, tmp_path / "b2.npz", tmp_path / "b2.json",
                    "bank-test", "corpus-test")
    assert m1["npz_sha256"] == m2["npz_sha256"]
    assert m1["per_class_counts"] == m2["per_class_counts"]
    assert m1["status"].startswith("DEVELOPMENT")


def test_bank_refuses_bridge_provenance(tmp_path):
    data = load_corpus_manifest(BRIDGE_RUN01_CORPUS_ID)
    samples = _synthetic_samples(data["images"][0]["sha256"])
    with pytest.raises(ProvenanceError):
        build_bank(samples, tmp_path / "x.npz", tmp_path / "x.json",
                   "bank-bad", "corpus-bad")


# ---------- grouped holdout (Task 9) ----------

def test_grouped_holdout_refuses_single_group():
    samples = _synthetic_samples("only-capture")
    out = grouped_holdout(samples)
    assert out["error"] == "NEED_AT_LEAST_2_GROUPS"


def test_grouped_holdout_leave_one_capture_out():
    samples = _synthetic_samples("cap-a") + _synthetic_samples("cap-b", noise_seed=5)
    out = grouped_holdout(samples)
    assert out["n_groups"] == 2
    assert out["operating_point"]["frozen"] is True
    assert set(out["folds"]) == {"cap-a", "cap-b"}
    for fold in out["folds"].values():
        assert fold["n"] > 0
    # synthetic renders are near-identical: decided accuracy should be high
    assert out["mean_accuracy_on_decided"] > 0.9


def test_grouped_holdout_never_writes_profiles(tmp_path, monkeypatch):
    """Evaluation is read-only: no file writes, no threshold changes."""
    profiles_dir = ROOT / "reader" / "profiles"
    before = {p.name: p.read_bytes() for p in profiles_dir.glob("*.json")}
    samples = _synthetic_samples("cap-a") + _synthetic_samples("cap-b", noise_seed=5)
    grouped_holdout(samples)
    after = {p.name: p.read_bytes() for p in profiles_dir.glob("*.json")}
    assert before == after


# ---------- enforcement (code-review round: reject, don't tag) ----------

def test_calibrate_refuses_bridge_corpus(tmp_path):
    from reader.calibrate import calibrate
    with pytest.raises(ProvenanceError):
        calibrate(tmp_path, ROOT / "reader" / "profiles" / "spike-reader-v02-development.json",
                  tmp_path / "new-profile.json", BRIDGE_RUN01_CORPUS_ID)


def test_validate_refuses_bridge_without_replay_flag(tmp_path):
    from reader.validate import validate
    manifest = {"corpus_id": BRIDGE_RUN01_CORPUS_ID, "images": []}
    mpath = tmp_path / "m.json"
    mpath.write_text(json.dumps(manifest))
    prof = ROOT / "reader" / "profiles" / "spike-reader-v02-development.json"
    with pytest.raises(ProvenanceError):
        validate(prof, tmp_path, mpath)
    out = validate(prof, tmp_path, mpath, development_replay=True)
    assert out["run_kind"] == "DEVELOPMENT_REPLAY"
    assert out["development_replay"] is True


def test_grouped_holdout_refuses_bridge_samples():
    data = load_corpus_manifest(BRIDGE_RUN01_CORPUS_ID)
    samples = _synthetic_samples(data["images"][0]["sha256"]) + _synthetic_samples("cap-b", noise_seed=5)
    with pytest.raises(ProvenanceError):
        grouped_holdout(samples)


def test_extractor_rejects_malformed_ground_truth():
    gt = _mini_gt()
    img = render_page(gt["lines"])
    bad = dict(gt)
    bad["lines"] = [gt["lines"][0][:-1]] + gt["lines"][1:]  # truncated line
    with pytest.raises(ValueError):
        extract_capture(img, bad, "cap-x")
    bad2 = dict(gt)
    bad2["charset"] = BECH32_CHARSET
    bad2["lines"] = ["b" * 48] + gt["lines"][1:]  # 'b' not in bech32
    with pytest.raises(ValueError):
        extract_capture(img, bad2, "cap-x")
