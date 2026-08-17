"""Phase C — minimal print-domain transfer experiment (owner Tasks 5–6).

Protocol (owner-fixed, frozen operating point 0.64/0.02 throughout):
  1. Extract labelled token glyphs from every cal-run02 capture with the
     span-aware v2 extractor (per-capture /tmp cache, resumable).
  2. Build a bank from COPY 1 captures ONLY.
  3. Evaluate: (a) leave-one-capture-out inside copy1; (b) the copy1 bank
     against ALL copy2 samples (the transfer target — copy2 never trains).
  4. DEVELOPMENT_REPLAY of Bridge S46 against the copy1 bank (S46 never in
     any bank): full funnel with E/e/2E+e vs the RS budget.
  5. Emit the report; the A/B/C verdict is derived from the numbers.

Nothing here tunes thresholds or touches frozen files.
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from reader.calibration.bank import build_bank  # noqa: E402
from reader.calibration.evaluate import (  # noqa: E402
    FROZEN_CONF_FLOOR, FROZEN_MARGIN_FLOOR, _score, grouped_holdout)
from reader.calibration.extract_v2 import extract_capture_v2  # noqa: E402
from reader.provenance import (  # noqa: E402
    assert_no_banned_hashes, load_corpus_manifest, require_flag, sha256_file)

from phaseb_calibration import load_gray  # noqa: E402

CORPUS_ID = "cal-run02-production-raw"
CORPUS = ROOT / "reader" / "corpora" / f"{CORPUS_ID}.json"
CAPTURES = ROOT / "reader" / "calibration" / "captures"
GT_PATH = (ROOT / "reader" / "calibration" / "sheets" /
           "calibration-sheet-calsheet-production-v2-s20260817.groundtruth.json")
BANK_ID = "cal-run02-copy1-bank-v1"
BANK_NPZ = ROOT / "reader" / "banks" / "cal-run02-copy1-bank.npz"
BANK_MANIFEST = ROOT / "reader" / "banks" / "cal-run02-copy1-bank.manifest.json"
PROFILE_OUT = ROOT / "reader" / "profiles" / "cal-run02-development.json"
BASE_PROFILE = ROOT / "reader" / "profiles" / "cal-run01-development.json"
REPORT_OUT = ROOT / "reader" / "calibration" / "phasec-transfer-report.json"

CACHE_DIR = Path("/tmp/phasec-extract-cache")
_CODE_SHA = hashlib.sha256(
    (ROOT / "reader" / "calibration" / "extract_v2.py").read_bytes()
    + (ROOT / "reader" / "calibration" / "extract.py").read_bytes()
    + (ROOT / "reader" / "registration.py").read_bytes()
    + (ROOT / "reader" / "structural_locator.py").read_bytes()).hexdigest()[:16]


def _extract_one(entry: dict, gt: dict, gt_sha: str):
    key = CACHE_DIR / f"{entry['sha256'][:24]}-g{gt_sha[:16]}-{_CODE_SHA}.pkl"
    if key.exists():
        with key.open("rb") as f:
            return pickle.load(f)
    res = extract_capture_v2(load_gray(CAPTURES / entry["filename"]), gt,
                             capture_sha256=entry["sha256"],
                             page_footer_indices=entry["page_footer_indices"])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = key.with_suffix(".tmp")
    with tmp.open("wb") as f:
        pickle.dump(res, f)
    tmp.replace(key)
    return res


def main() -> None:
    manifest = load_corpus_manifest(CORPUS_ID)
    require_flag(CORPUS_ID, "classifier_training_allowed")
    assert manifest["usage_flags"]["training_copy_restriction"] == "copy1"
    gt = json.loads(GT_PATH.read_text())
    gt_sha = sha256_file(GT_PATH)

    per_capture = {}
    samples_by_copy: dict[str, list] = {"copy1": [], "copy2": []}
    for entry in manifest["images"]:
        # Verify the capture bytes against the registered hash BEFORE any
        # labelling: a swapped/corrupted file must fail loudly, not mislabel.
        actual = sha256_file(CAPTURES / entry["filename"])
        if actual != entry["sha256"]:
            raise RuntimeError(f"capture hash mismatch for {entry['filename']}: "
                               f"{actual} != manifest {entry['sha256']}")
        res = _extract_one(entry, gt, gt_sha)
        per_capture[entry["filename"]] = {
            "print_copy": entry["print_copy"],
            "condition": entry["condition"],
            "page": entry["page"],
            "n_samples": len(res.samples),
            "lines_used": res.lines_used,
            "n_footers": res.n_footers,
            "dropped": res.lines_dropped,
        }
        samples_by_copy[entry["print_copy"]] += res.samples
        print(f"{entry['filename']}: {len(res.samples)} samples, "
              f"{res.n_footers} footers, {res.lines_used} lines", flush=True)

    copy1_shas = {e["sha256"] for e in manifest["images"] if e["print_copy"] == "copy1"}
    copy1, copy2 = samples_by_copy["copy1"], samples_by_copy["copy2"]
    assert_no_banned_hashes({s.capture_sha256 for s in copy1})
    assert all(s.capture_sha256 in copy1_shas for s in copy1), "copy separation violated"
    assert not any(s.capture_sha256 in copy1_shas for s in copy2), "copy separation violated"

    # ── bank from copy1 ONLY ─────────────────────────────────────────────
    if not BANK_NPZ.exists():
        build_bank(copy1, BANK_NPZ, BANK_MANIFEST, bank_id=BANK_ID, corpus_id=CORPUS_ID)
    bank_note = json.loads(BANK_MANIFEST.read_text())
    # A pre-existing bank is trusted ONLY after re-verifying its provenance:
    # npz bytes match the manifest, and every listed capture hash is a
    # manifest copy1 capture (copy2 / anything else must never train).
    npz_sha = hashlib.sha256(BANK_NPZ.read_bytes()).hexdigest()
    if npz_sha != bank_note["npz_sha256"]:
        raise RuntimeError("bank npz does not match its manifest; refusing")
    if bank_note["corpus_id"] != CORPUS_ID or bank_note["bank_id"] != BANK_ID:
        raise RuntimeError("bank manifest identity mismatch; refusing")
    listed = set(bank_note["capture_sha256s"])
    if not listed or not listed <= copy1_shas:
        raise RuntimeError("bank provenance lists non-copy1 captures; refusing")
    assert_no_banned_hashes(listed)

    # ── (a) leave-one-capture-out inside copy1 ───────────────────────────
    loco_copy1 = grouped_holdout(copy1)

    # ── (b) copy1 bank -> all copy2 (transfer target, never trained) ─────
    transfer = _score(copy1, copy2, FROZEN_CONF_FLOOR, FROZEN_MARGIN_FLOOR)
    transfer_by_condition = {}
    for cond in ("std", "room"):
        sub = [s for s, e in ((s, next(e for e in manifest["images"]
                                       if e["sha256"] == s.capture_sha256))
                              for s in copy2) if e["condition"] == cond]
        transfer_by_condition[cond] = _score(copy1, sub, FROZEN_CONF_FLOOR,
                                             FROZEN_MARGIN_FLOOR)

    report = {
        "phase": "C — production-domain transfer experiment",
        "status": "DEVELOPMENT / NOT GATE-A1",
        "operating_point": {"confidence_floor": FROZEN_CONF_FLOOR,
                            "margin_floor": FROZEN_MARGIN_FLOOR, "frozen": True},
        "corpus_id": CORPUS_ID,
        "extractor_code_sha": _CODE_SHA,
        "groundtruth_sha256": gt_sha,
        "n_samples": {"copy1": len(copy1), "copy2": len(copy2)},
        "per_capture": per_capture,
        "bank": {"id": BANK_ID, "path": str(BANK_NPZ.relative_to(ROOT)),
                 "n_samples": bank_note.get("n_samples"),
                 "trained_on": "copy1 captures only"},
        "copy1_loco_holdout": loco_copy1,
        "copy2_transfer": transfer,
        "copy2_transfer_by_condition": transfer_by_condition,
    }
    REPORT_OUT.write_text(json.dumps(report, indent=2) + "\n")
    print("\nwritten:", REPORT_OUT.relative_to(ROOT))
    print(json.dumps({
        "copy1_loco_mean_decided": loco_copy1.get("mean_accuracy_on_decided"),
        "copy2_transfer": {k: transfer.get(k) for k in
                           ("n", "accuracy_on_decided", "erasure_rate",
                            "confident_wrong_rate")},
    }, indent=1))


if __name__ == "__main__":
    main()
