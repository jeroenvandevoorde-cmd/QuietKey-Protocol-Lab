"""Task 9 — calibration/validation separation.

Validation must require a frozen profile, load thresholds from it, refuse
tuning, record profile and manifest SHA-256s, and output metrics only.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from reader.profile import default_development_profile_path, load_profile
from reader.synthglyphs import render_page
from reader.validate import validate

ROOT = Path(__file__).resolve().parents[2]


def _mk_corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    img = render_page(["qpzry9x8gf2tvdw0s3jn54khce6mua7lqpzry9x8gf2tvdw0"] * 3)
    np.save(corpus / "synthetic_page.npy", img)
    blank = np.ones((300, 500))
    np.save(corpus / "blank_page.npy", blank)
    manifest = {
        "corpus_id": "synthetic-dev-corpus-v1",
        "images": [{"filename": "synthetic_page.npy"}, {"filename": "blank_page.npy"}],
    }
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps(manifest))
    return corpus, mpath


def test_validation_requires_existing_profile(tmp_path):
    corpus, mpath = _mk_corpus(tmp_path)
    with pytest.raises(FileNotFoundError):
        validate(tmp_path / "nonexistent-profile.json", corpus, mpath)


def test_validation_records_hashes_and_outputs_metrics_only(tmp_path):
    corpus, mpath = _mk_corpus(tmp_path)
    ppath = default_development_profile_path()
    before = ppath.read_bytes()
    out = validate(ppath, corpus, mpath)
    assert ppath.read_bytes() == before, "validation modified the profile"
    assert out["profile_sha256"] == hashlib.sha256(before).hexdigest()
    assert out["corpus_manifest_sha256"] == hashlib.sha256(mpath.read_bytes()).hexdigest()
    assert out["images"] == 2
    assert sum(out["category_counts"].values()) == 2
    # explicit categories only — never a generic FAIL
    from reader.taxonomy import ResultCategory

    for cat in out["category_counts"]:
        assert cat in {c.value for c in ResultCategory}
    assert "FAIL" not in out["category_counts"]


def test_validation_cli_has_no_tuning_arguments():
    """Accidental tuning is technically difficult: no threshold flags exist."""
    src = (ROOT / "reader" / "validate.py").read_text()
    for banned in ["confidence", "margin", "threshold", "floor", "tune", "grid"]:
        for line in src.splitlines():
            if "add_argument" in line:
                assert banned not in line.lower(), f"tuning argument leaked: {line.strip()}"


def test_validation_cli_rejects_threshold_flag(tmp_path):
    corpus, mpath = _mk_corpus(tmp_path)
    r = subprocess.run(
        [sys.executable, "-m", "reader.validate",
         "--profile", str(default_development_profile_path()),
         "--corpus", str(corpus), "--manifest", str(mpath),
         "--confidence-floor", "0.1"],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode != 0, "validate accepted a tuning flag"


def test_bridge_run01_tagged_development(tmp_path):
    corpus, mpath = _mk_corpus(tmp_path)
    m = json.loads(mpath.read_text())
    m["corpus_id"] = "bridge-run01-development-regression"
    mpath.write_text(json.dumps(m))
    out = validate(default_development_profile_path(), corpus, mpath)
    assert out["development_data"] is True


def test_calibration_writes_new_profile_never_overwrites(tmp_path):
    from reader.calibrate import calibrate

    corpus, _ = _mk_corpus(tmp_path)
    out = tmp_path / "candidate-profile.json"
    res = calibrate(corpus, default_development_profile_path(), out, "synthetic-dev-corpus-v1")
    assert out.exists()
    written = load_profile(out)
    assert "NOT GATE-A1" in written.status
    assert written.data["calibration_corpora"] == ["synthetic-dev-corpus-v1"]
    assert res["profile_sha256"] == written.sha256
    with pytest.raises(SystemExit, match="refusing to overwrite"):
        calibrate(corpus, default_development_profile_path(), out, "x")
