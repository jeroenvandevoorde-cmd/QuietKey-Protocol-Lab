"""Task 8 — Reader Profile loading, hashing, and status marking."""
import hashlib
import json

import pytest

from reader.profile import (
    REQUIRED_FIELDS,
    default_development_profile_path,
    load_profile,
)


def test_development_profile_loads(dev_profile):
    assert dev_profile.data["profile_format_version"] == 1
    assert dev_profile.data["reader_version"] == "0.2-dev"


def test_status_is_not_gate_a1(dev_profile):
    assert "NOT GATE-A1" in dev_profile.status
    assert "NOT PRODUCTION" in dev_profile.status
    assert "NOT GATE-A1" in dev_profile.data["warning"]


def test_frozen_spike_operating_point_preserved(dev_profile):
    """0.64 / 0.02 remain the frozen historical spike operating point."""
    assert dev_profile.confidence_floor == 0.64
    assert dev_profile.margin_floor == 0.02


def test_sha256_recorded_and_correct(dev_profile):
    p = default_development_profile_path()
    assert dev_profile.sha256 == hashlib.sha256(p.read_bytes()).hexdigest()
    assert len(dev_profile.sha256) == 64


def test_required_fields_enforced(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"reader_version": "0.2-dev"}))
    with pytest.raises(ValueError, match="missing required fields"):
        load_profile(bad)


def test_all_required_fields_present(dev_profile):
    for f in REQUIRED_FIELDS:
        assert f in dev_profile.data, f


def test_no_invented_camera_metadata(dev_profile):
    """Unknown hardware metadata must be absent or null, never invented."""
    for k in ("camera_id", "printer_id", "terminal_optics"):
        assert dev_profile.data.get(k) in (None,), f"invented metadata {k}"
    assert dev_profile.data["source_commit"] is None  # unknown at authoring time
