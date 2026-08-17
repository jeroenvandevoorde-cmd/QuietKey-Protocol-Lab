"""Bridge Run 01 locator regression tests (Reader v0.2.1, Tasks 3/4).

Bridge Run 01 is permanently seen DEVELOPMENT data; its manifest allows
locator regression testing only. These tests skip when the gitignored raw
images are absent (CI without captures) and verify hashes before use.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from reader.provenance import (
    BRIDGE_RUN01_CORPUS_ID,
    load_corpus_manifest,
    require_flag,
    sha256_file,
)
from reader.structural_locator import MAX_CANDIDATES, locate_footer_candidates

CAPTURES = ROOT / "bridge" / "captures"


def _gt_images():
    data = load_corpus_manifest(BRIDGE_RUN01_CORPUS_ID)
    return [im for im in data["images"] if im.get("footer_rows_gt")]


def _load(im):
    path = CAPTURES / im["filename"]
    if not path.exists():
        pytest.skip(f"bridge capture not present (gitignored): {im['filename']}")
    if sha256_file(path) != im["sha256"]:
        pytest.fail(f"bridge capture hash mismatch: {im['filename']}")
    from scripts.bridge_quality_audit import load_gray
    return load_gray(path)


def test_regression_use_is_flagged_allowed():
    require_flag(BRIDGE_RUN01_CORPUS_ID, "regression_testing_allowed")


@pytest.mark.parametrize("im", _gt_images(), ids=lambda im: im["filename"])
def test_footer_in_top5_candidates_on_accept_sheets(im):
    gray = _load(im)
    a, b = im["footer_rows_gt"]
    cands = locate_footer_candidates(gray)
    assert len(cands) <= MAX_CANDIDATES
    hit = None
    for ci, c in enumerate(cands):
        overlap = sum(
            1 for l in c.lines
            if min(l.row_end, b) - max(l.row_start, a) > 0
        )
        if overlap >= 2:
            hit = ci
            break
    assert hit is not None, (
        f"{im['filename']}: no candidate overlaps GT footer rows {a}-{b} "
        f"in top-{MAX_CANDIDATES}"
    )


def test_candidate_enumeration_is_bounded_and_deterministic():
    ims = _gt_images()
    gray = _load(ims[0])
    c1 = locate_footer_candidates(gray)
    c2 = locate_footer_candidates(gray)
    assert len(c1) <= MAX_CANDIDATES
    assert [(l.row_start, l.row_end) for c in c1 for l in c.lines] == \
           [(l.row_start, l.row_end) for c in c2 for l in c.lines]
