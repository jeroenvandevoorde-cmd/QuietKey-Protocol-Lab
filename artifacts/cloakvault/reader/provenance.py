"""Corpus provenance and leakage guards.

Every image corpus the reader touches is described by a manifest in
``reader/corpora/`` carrying explicit ``usage_flags``. Code that trains,
calibrates, or validates MUST consult these flags; the guards here make
misuse loud instead of silent.

Key rule (owner-binding): Bridge Run 01 is permanently seen development
data. It may drive locator development and regression tests, but its
image hashes must never appear in a classifier bank's provenance and it
must never be called validation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

CORPORA_DIR = Path(__file__).resolve().parent / "corpora"

BRIDGE_RUN01_CORPUS_ID = "bridge-run01-development"


class ProvenanceError(RuntimeError):
    """A corpus usage flag was violated."""


def load_corpus_manifest(corpus_id: str) -> dict[str, Any]:
    path = CORPORA_DIR / f"{corpus_id}.json"
    if not path.exists():
        raise ProvenanceError(f"unknown corpus manifest: {corpus_id} ({path})")
    data = json.loads(path.read_text())
    if data.get("corpus_id") != corpus_id:
        raise ProvenanceError(f"corpus_id mismatch in {path}")
    if "usage_flags" not in data:
        raise ProvenanceError(f"corpus manifest {corpus_id} lacks usage_flags")
    return data


def corpus_image_hashes(corpus_id: str) -> set[str]:
    data = load_corpus_manifest(corpus_id)
    return {im["sha256"] for im in data["images"]}


def require_flag(corpus_id: str, flag: str) -> None:
    """Raise unless the corpus explicitly allows `flag`."""
    data = load_corpus_manifest(corpus_id)
    flags = data["usage_flags"]
    if flag not in flags:
        raise ProvenanceError(f"corpus {corpus_id} does not declare flag {flag!r}")
    if flags[flag] is not True:
        raise ProvenanceError(
            f"corpus {corpus_id} forbids {flag!r} (status: {data.get('status')})"
        )


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def assert_no_banned_hashes(
    provenance_hashes: Iterable[str],
    banned_corpus_ids: Iterable[str] = (BRIDGE_RUN01_CORPUS_ID,),
) -> None:
    """Fail if any provenance hash belongs to a corpus whose flags forbid
    classifier training. Used by the bank builder and its tests."""
    prov = set(provenance_hashes)
    for cid in banned_corpus_ids:
        data = load_corpus_manifest(cid)
        if data["usage_flags"].get("classifier_training_allowed") is True:
            continue
        banned = {im["sha256"] for im in data["images"]}
        hit = prov & banned
        if hit:
            raise ProvenanceError(
                f"classifier bank provenance contains {len(hit)} image(s) from "
                f"corpus {cid}, which forbids classifier training: "
                + ", ".join(sorted(hit)[:3])
            )
