"""The standalone S46 replay must refuse any bank whose provenance is
tainted — even when the NPZ hash matches its (tainted) manifest. Otherwise
the replay could emit 'S46 NEVER IN BANK' against a bank that trained on
Bridge material or copy2."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from phasec_s46_replay import validate_bank_provenance  # noqa: E402

S46_SHA = "bf1b1de98b23d7d4c3120968ce02e3c64ec49031b880309cc6c3581be08d4b8a"
CORPUS = json.loads((ROOT / "reader" / "corpora" / "cal-run02-production-raw.json").read_text())
COPY1 = [e["sha256"] for e in CORPUS["images"] if e["print_copy"] == "copy1"]
COPY2 = [e["sha256"] for e in CORPUS["images"] if e["print_copy"] == "copy2"]


def _manifest(hashes):
    return {"bank_id": "cal-run02-copy1-bank-v1",
            "corpus_id": "cal-run02-production-raw",
            "capture_sha256s": hashes}


def test_valid_copy1_bank_accepted():
    validate_bank_provenance(_manifest(COPY1))


def test_s46_in_bank_provenance_refused():
    with pytest.raises(Exception):
        validate_bank_provenance(_manifest(COPY1 + [S46_SHA]))


def test_copy2_in_bank_provenance_refused():
    with pytest.raises(RuntimeError):
        validate_bank_provenance(_manifest(COPY1 + COPY2[:1]))


def test_empty_capture_list_refused():
    with pytest.raises(RuntimeError):
        validate_bank_provenance(_manifest([]))


def test_wrong_identity_refused():
    m = _manifest(COPY1)
    m["bank_id"] = "cal-run01-bank-v1"
    with pytest.raises(RuntimeError):
        validate_bank_provenance(m)
    m = _manifest(COPY1)
    m["corpus_id"] = "bridge-run01-development"
    with pytest.raises(RuntimeError):
        validate_bank_provenance(m)
