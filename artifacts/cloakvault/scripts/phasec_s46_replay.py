"""Phase C step 4 — DEVELOPMENT_REPLAY of Bridge S46 with the copy1 bank.

Creates the cal-run02 development profile (clone of cal-run01 profile with
the bank swapped; frozen 0.64/0.02 untouched) if absent, then reruns S46
through the same candidate-attempt loop and deepest-honest-failure
selection rule as read_frame (mirroring the acceptance audit's recording
funnel) and audits E/e/2E+e vs the T5 ground truth. S46 never enters any bank; this is regression/replay use of
Bridge Run 01 development material only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from reader.frame import _attempt_candidate  # noqa: E402
from reader.profile import load_profile  # noqa: E402
from reader.provenance import require_flag  # noqa: E402
from reader.quality import assess_quality  # noqa: E402
from reader.spike_bank_classifier import SpikeBank, make_spike_classifier  # noqa: E402
from reader.structural_locator import locate_footer_candidates  # noqa: E402

import phaseb_acceptance_audit as AUD  # noqa: E402

BASE_PROFILE = ROOT / "reader" / "profiles" / "cal-run01-development.json"
PROFILE_OUT = ROOT / "reader" / "profiles" / "cal-run02-development.json"
BANK_REL = "reader/banks/cal-run02-copy1-bank.npz"
S46 = ROOT / "bridge" / "captures" / "bridge-baseline-0-std-S46.jpeg"
OUT = ROOT / "reader" / "calibration" / "phasec-s46-replay.json"


def validate_bank_provenance(bm: dict) -> None:
    """Enforce the owner's bank provenance rules for the replay bank,
    independently of how the bank came to exist: correct identity, a
    nonempty capture list that is a subset of the cal-run02 COPY1 captures,
    and no Bridge hashes. Raises on any violation — the replay must never
    run (nor claim 'S46 NEVER IN BANK') against a tainted bank."""
    from reader.provenance import assert_no_banned_hashes, load_corpus_manifest
    if bm.get("bank_id") != "cal-run02-copy1-bank-v1":
        raise RuntimeError(f"unexpected bank_id {bm.get('bank_id')!r}; refusing")
    if bm.get("corpus_id") != "cal-run02-production-raw":
        raise RuntimeError(f"unexpected corpus_id {bm.get('corpus_id')!r}; refusing")
    listed = set(bm.get("capture_sha256s") or [])
    if not listed:
        raise RuntimeError("bank manifest lists no capture hashes; refusing")
    corpus = load_corpus_manifest("cal-run02-production-raw")
    copy1 = {e["sha256"] for e in corpus["images"] if e["print_copy"] == "copy1"}
    if not listed <= copy1:
        raise RuntimeError("bank provenance lists non-copy1 captures "
                           "(copy2/Bridge/unknown); refusing")
    assert_no_banned_hashes(listed)


def ensure_profile() -> Path:
    """(Re)write the cal-run02 profile from the current bank. Always
    regenerated so the profile's bank metadata can never go stale: every
    bank-derived field is replaced from the cal-run02 bank manifest."""
    from reader.provenance import sha256_file
    base = json.loads(BASE_PROFILE.read_text())
    assert base["confidence_floor"] == 0.64 and base["margin_floor"] == 0.02
    bank_manifest_path = ROOT / "reader" / "banks" / "cal-run02-copy1-bank.manifest.json"
    bm = json.loads(bank_manifest_path.read_text())
    npz_sha = sha256_file(ROOT / BANK_REL)
    if npz_sha != bm["npz_sha256"]:
        raise RuntimeError("bank npz does not match its manifest; refusing to build profile")
    validate_bank_provenance(bm)
    base["profile_id"] = "cal-run02-development"
    base["classifier_id"] = (f"{bm['bank_id']} (production-path sheet, copy1 only, "
                             f"{bm['feature_version']} features, per-class max NN)")
    base["calibration_corpora"] = [f"{bm['corpus_id']} (copy1 only)"]
    base["glyph_bank"] = {
        "path": BANK_REL,
        "sha256": npz_sha,
        "manifest": str(bank_manifest_path.relative_to(ROOT)),
        "bank_id": bm["bank_id"],
        "n_samples": bm["n_samples"],
        "capture_sha256s": bm["capture_sha256s"],
    }
    PROFILE_OUT.write_text(json.dumps(base, indent=2) + "\n")
    return PROFILE_OUT


def main() -> None:
    require_flag("bridge-run01-development", "regression_testing_allowed")
    profile = load_profile(ensure_profile())
    classifier = make_spike_classifier(SpikeBank(ROOT / profile.data["glyph_bank"]["path"]))

    img = ImageOps.exif_transpose(Image.open(S46)).convert("L")
    gray = np.asarray(img, dtype=np.float64) / 255.0
    q = assess_quality(gray, profile.quality)
    cands = locate_footer_candidates(gray)

    attempts, winner = [], None
    for i, cand in enumerate(cands):
        a = _attempt_candidate(gray, cand, i, profile, classifier)
        attempts.append(a)
        if a.category is None:
            winner = a
            break
    chosen = winner or max(attempts, key=lambda a: (a.depth,
                                                    -a.erasures if a.classified else 0,
                                                    -a.index))
    token = chosen.token
    char_stats = rs_stats = None
    if token is not None and len(token) == len(AUD.GT_TOKEN):
        c = sum(1 for a, b in zip(token, AUD.GT_TOKEN) if a == b and a != "?")
        er = token.count("?")
        char_stats = {"token_chars": len(token), "correct": c, "erasure": er,
                      "confident_wrong": len(token) - c - er}
        rs_stats = AUD._token_rs_audit(token)
    aead = "NOT_REACHED"
    if winner is not None and token is not None:
        try:
            out = AUD.cv3.decode_pipeline(token.replace("?", "q"),
                                          bytes.fromhex(AUD.T5["vault_key_hex"]))
            aead = ("AUTHENTICATED" if bytes(out).hex() == AUD.T5["entropy_hex"]
                    else "ENTROPY_MISMATCH")
        except Exception as exc:
            aead = f"FAIL:{type(exc).__name__}"
    rec = {
        "replay": "DEVELOPMENT_REPLAY — Bridge S46 vs cal-run02 copy1 bank",
        "status": "DEVELOPMENT / NOT GATE-A1 / S46 NEVER IN BANK",
        "profile": "cal-run02-development (frozen 0.64/0.02)",
        "quality_status": q.status,
        "candidate_index_used_zero_based": chosen.index,
        "n_candidates": len(cands),
        "rs_valid": winner is not None,
        "rs_reason": chosen.reason,
        "classified_chars": chosen.classified,
        "erasure_cells": chosen.erasures,
        "token_char_stats_vs_gt": char_stats,
        "rs_byte_audit_vs_gt": rs_stats,
        "aead": aead,
        "category": "RS_VALID" if winner is not None else
                    (chosen.category.name if chosen.category else "?"),
    }
    OUT.write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
