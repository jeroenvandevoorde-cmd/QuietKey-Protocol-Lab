"""Task 10 — raw-capture manifest tool: deterministic, never invents metadata."""
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]  # workspace root
spec = importlib.util.spec_from_file_location(
    "build_capture_manifest", ROOT / "scripts" / "build_capture_manifest.py"
)
bcm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bcm)


def _tiny_png(tmp_path, name="a.png", w=3, h=2):
    # minimal PNG header sufficient for dimension parsing
    ihdr = struct.pack(">II", w, h)
    data = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + ihdr + b"\x08\x02\x00\x00\x00" + b"\x00" * 8
    p = tmp_path / name
    p.write_bytes(data)
    return p, data


def test_manifest_records_hash_size_dims(tmp_path):
    p, data = _tiny_png(tmp_path)
    np.save(tmp_path / "b.npy", np.ones((5, 7)))
    m = bcm.build_manifest(tmp_path, "corpus-x", "campaign-y", {})
    assert m["image_count"] == 2
    png = next(e for e in m["images"] if e["filename"] == "a.png")
    assert png["sha256"] == hashlib.sha256(data).hexdigest()
    assert (png["width"], png["height"]) == (3, 2)
    npy = next(e for e in m["images"] if e["filename"] == "b.npy")
    assert (npy["width"], npy["height"]) == (7, 5)


def test_unknown_metadata_stays_null(tmp_path):
    _tiny_png(tmp_path)
    m = bcm.build_manifest(tmp_path, None, None, {})
    e = m["images"][0]
    for f in bcm.META_FIELDS:
        assert e[f] is None, f"{f} should be null, never invented"
    assert m["corpus_id"] is None and m["campaign_id"] is None


def test_sidecar_metadata_applied_only_where_supplied(tmp_path):
    _tiny_png(tmp_path)
    _tiny_png(tmp_path, "c.png")
    sidecar = {"a.png": {"capture_id": "S28", "severity": "pristine"}}
    m = bcm.build_manifest(tmp_path, "x", "y", sidecar)
    a = next(e for e in m["images"] if e["filename"] == "a.png")
    c = next(e for e in m["images"] if e["filename"] == "c.png")
    assert a["capture_id"] == "S28" and a["severity"] == "pristine"
    assert c["capture_id"] is None


def test_deterministic_output(tmp_path):
    _tiny_png(tmp_path)
    m1 = bcm.build_manifest(tmp_path, "x", "y", {})
    m2 = bcm.build_manifest(tmp_path, "x", "y", {})
    assert json.dumps(m1, sort_keys=True) == json.dumps(m2, sort_keys=True)
