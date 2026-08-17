"""Validation path: frozen profile + validation corpus → metrics ONLY.

Hard separation from calibration (accidental tuning is made technically
difficult):

  * REQUIRES an existing profile file; there is no way to supply or
    override any threshold on the command line — no threshold arguments
    exist at all;
  * loads thresholds exclusively from the profile;
  * refuses grid-search: processes the corpus exactly once with exactly
    one profile;
  * never writes or rewrites profiles (read-only open);
  * records the profile SHA-256 and the validation-corpus manifest
    SHA-256 in its output;
  * outputs metrics only.

Bridge Run 01 rule: Bridge Run 01 is seen development/regression material
and MUST NOT be reported as unseen validation; corpus IDs containing
"bridge-run01" are tagged development_data=true in the output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

from .frame import read_frame
from .profile import load_profile


def validate(profile_path: Path, corpus_dir: Path, manifest_path: Path,
             development_replay: bool = False) -> dict:
    """Metrics run. `development_replay=False` (real validation) REFUSES any
    corpus registered with validation_use_allowed=false (e.g. Bridge Run 01).
    `development_replay=True` permits a seen corpus registered with
    regression_testing_allowed=true, and the output is labelled a
    development replay — it is never validation."""
    from .provenance import CORPORA_DIR, ProvenanceError, load_corpus_manifest

    profile = load_profile(profile_path)  # raises if absent/invalid
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    manifest = json.loads(manifest_path.read_text())

    corpus_id_early = manifest.get("corpus_id", "")
    registered = (CORPORA_DIR / f"{corpus_id_early}.json").exists()
    if registered:
        flags = load_corpus_manifest(corpus_id_early)["usage_flags"]
        if not development_replay and flags.get("validation_use_allowed") is not True:
            raise ProvenanceError(
                f"corpus {corpus_id_early} forbids validation use; "
                "rerun with development_replay=True (--development-replay) "
                "and the output will be labelled a development replay")
        if development_replay and flags.get("regression_testing_allowed") is not True:
            raise ProvenanceError(
                f"corpus {corpus_id_early} does not allow regression/replay use")
    elif "bridge-run01" in corpus_id_early.lower() and not development_replay:
        raise ProvenanceError(
            f"corpus {corpus_id_early} looks like Bridge Run 01 (permanently "
            "seen); it can never be validated — use --development-replay")

    categories: Counter[str] = Counter()
    per_image = []
    for entry in manifest["images"]:
        img = np.load(corpus_dir / entry["filename"])
        r = read_frame(img, profile)
        categories[r.category.value] += 1
        per_image.append({"filename": entry["filename"], "category": r.category.value,
                          "failing_stage": (r.failing_stage().value if r.failing_stage() else None)})

    corpus_id = manifest.get("corpus_id", str(corpus_dir))
    return {
        "profile_path": profile.path,
        "profile_sha256": profile.sha256,
        "profile_status": profile.status,
        "corpus_id": corpus_id,
        "corpus_manifest_sha256": manifest_sha,
        "development_data": "bridge-run01" in corpus_id.lower(),
        "development_replay": development_replay,
        "run_kind": "DEVELOPMENT_REPLAY" if development_replay else "VALIDATION",
        "images": len(per_image),
        "category_counts": dict(categories),
        "per_image": per_image,
        "note": "metrics only; validation never tunes, never writes profiles",
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Reader v0.2 validation (frozen profile + corpus -> metrics; cannot tune)"
    )
    # Deliberately NO threshold/tuning arguments.
    ap.add_argument("--profile", required=True, type=Path, help="existing frozen profile JSON")
    ap.add_argument("--corpus", required=True, type=Path, help="directory of .npy images")
    ap.add_argument("--manifest", required=True, type=Path, help="corpus manifest JSON")
    ap.add_argument("--out", type=Path, help="write metrics JSON here (optional)")
    ap.add_argument("--development-replay", action="store_true",
                    help="permit a seen development/regression corpus; output is labelled a replay, never validation")
    a = ap.parse_args()
    result = validate(a.profile, a.corpus, a.manifest,
                      development_replay=a.development_replay)
    text = json.dumps(result, indent=2)
    if a.out:
        a.out.write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
