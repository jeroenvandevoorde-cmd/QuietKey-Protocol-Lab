"""Label-safety and cache-soundness regression tests for the Phase B
calibration pipeline script (scripts/phaseb_calibration.py).

These pin the two review-round guarantees:
  1. A single-group page can only receive a block hint from RECORDED
     corpus metadata (page_block_indices) — never inferred.
  2. The extraction cache key covers every labelled-output input: capture
     sha, ground-truth sha, hint, and extractor code revision.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "phaseb_calibration", ROOT / "scripts" / "phaseb_calibration.py")
phaseb = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("phaseb_calibration", phaseb)
_spec.loader.exec_module(phaseb)


class TestPageBlockHint:
    def test_no_metadata_no_hint(self):
        assert phaseb.page_block_hint({"filename": "x-2.jpeg"}, 4) is None

    def test_multi_block_page_no_hint(self):
        entry = {"page": 1, "page_block_indices": [0, 1, 2]}
        assert phaseb.page_block_hint(entry, 4) is None

    def test_empty_indices_no_hint(self):
        assert phaseb.page_block_hint({"page_block_indices": []}, 4) is None

    def test_single_block_page_hints_that_block(self):
        entry = {"page": 2, "page_block_indices": [3]}
        assert phaseb.page_block_hint(entry, 4) == 3

    def test_out_of_range_index_raises(self):
        with pytest.raises(ValueError):
            phaseb.page_block_hint({"page_block_indices": [4]}, 4)


class TestCacheKey:
    CAP = "c" * 64
    GT = "a" * 64

    def test_groundtruth_change_invalidates(self):
        k1 = phaseb.cache_key(self.CAP, self.GT, None)
        k2 = phaseb.cache_key(self.CAP, "b" * 64, None)
        assert k1 != k2

    def test_capture_change_invalidates(self):
        assert (phaseb.cache_key(self.CAP, self.GT, None)
                != phaseb.cache_key("d" * 64, self.GT, None))

    def test_hint_change_invalidates(self):
        assert (phaseb.cache_key(self.CAP, self.GT, None)
                != phaseb.cache_key(self.CAP, self.GT, 3))

    def test_extractor_revision_invalidates(self):
        assert (phaseb.cache_key(self.CAP, self.GT, None)
                != phaseb.cache_key(self.CAP, self.GT, None,
                                    extractor_sha="0" * 16))

    def test_extractor_sha_covers_locator(self):
        # _EXTRACTOR_SHA must be derived from all extraction-affecting
        # modules, including the structural locator.
        import hashlib
        expected = hashlib.sha256(
            (ROOT / "reader" / "calibration" / "extract.py").read_bytes()
            + (ROOT / "reader" / "registration.py").read_bytes()
            + (ROOT / "reader" / "structural_locator.py").read_bytes()
        ).hexdigest()[:16]
        assert phaseb._EXTRACTOR_SHA == expected

    def test_page_of(self):
        assert phaseb.page_of("cal-x-copy1-std-1.jpeg") == 1
        assert phaseb.page_of("cal-x-copy1-shadow-2.jpeg") == 2
