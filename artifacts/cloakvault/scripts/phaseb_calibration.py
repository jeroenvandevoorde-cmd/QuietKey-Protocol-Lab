"""Phase B calibration pipeline (Reader v0.2.1, Tasks post-21).

Owner supplied real-print calibration captures (campaign cal-run01).
This script runs the whole Phase B chain, refusing to continue at any
unsafe step:

  1. registers/loads the corpus manifest reader/corpora/cal-run01-raw.json
     and enforces its usage flags (classifier training + threshold
     calibration allowed; Gate A1 evidence NOT allowed);
  2. verifies every capture's SHA-256 against the capture manifest;
  3. extracts labelled glyphs with the known-layout extractor (captures
     that cannot be labelled safely are rejected, never guessed);
  4. grouped-holdout evaluation at the FROZEN operating point
     (conf 0.64 / margin 0.02 — reported, never tuned);
  5. builds the deterministic real-print bank (Bridge hashes banned);
  6. writes a NEW DEVELOPMENT profile referencing the bank (never
     overwrites an existing profile).

Owner note (recorded, not silently accepted): the capture protocol asks
for >= 2 printed copies. All 8 captures are labelled copy1; the owner
reports a second printed copy was made and visually established as
identical. Grouped holdout therefore uses leave-one-CAPTURE-out (8
groups) and additionally reports leave-one-CONDITION-out (4 groups).
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reader.calibration.bank import build_bank  # noqa: E402
from reader.calibration.evaluate import grouped_holdout  # noqa: E402
from reader.calibration.extract import extract_capture  # noqa: E402
from reader.provenance import require_flag, sha256_file  # noqa: E402

CAPTURES = ROOT / "reader" / "calibration" / "captures"
CAPTURE_MANIFEST = CAPTURES / "CAPTURE-MANIFEST.json"
SHEETS = ROOT / "reader" / "calibration" / "sheets"
CORPUS_ID = "cal-run01-raw"
CORPUS_MANIFEST = ROOT / "reader" / "corpora" / f"{CORPUS_ID}.json"
BANK_ID = "cal-run01-bank-v1"
BANK_NPZ = ROOT / "reader" / "banks" / "cal-run01-bank.npz"
BANK_MANIFEST = ROOT / "reader" / "banks" / "cal-run01-bank.manifest.json"
PROFILE_OUT = ROOT / "reader" / "profiles" / "cal-run01-development.json"
BASE_PROFILE = ROOT / "reader" / "profiles" / "spike-reader-v02-development.json"
REPORT_OUT = ROOT / "reader" / "calibration" / "phaseb-cal-run01-report.json"


def register_corpus(cm: dict) -> None:
    """Write the corpus manifest (once) from the capture manifest."""
    if CORPUS_MANIFEST.exists():
        return
    manifest = {
        "corpus_id": CORPUS_ID,
        "corpus_format_version": 1,
        "status": "REAL-PRINT CALIBRATION MATERIAL / DEVELOPMENT / NOT GATE-A1",
        "description": (
            "Calibration captures of sheet calsheet-v1-s20260817 (campaign "
            "cal-run01), supplied by the owner at the Task 21 checkpoint. "
            "Public sheet content — no secret material."),
        "usage_flags": {
            "locator_development_allowed": True,
            "regression_testing_allowed": True,
            "classifier_training_allowed": True,
            "threshold_calibration_allowed": True,
            "validation_use_allowed": False,
            "gate_a1_evidence_allowed": False,
        },
        "capture_manifest_sha256": sha256_file(CAPTURE_MANIFEST),
        "images": [
            {"filename": im["filename"], "sha256": im["sha256"],
             "copy": im["copy"], "condition": im["condition"],
             "page": page_of(im["filename"]),
             "page_block_indices": ([0, 1, 2] if page_of(im["filename"]) == 1
                                    else [3])}
            for im in cm["images"]
        ],
        "notes": [
            "page / page_block_indices: the physical print paginated 3+1 "
            "(blocks 1-3 on page 1, block 4 on page 2). Page ordinal is "
            "derived from the capture filename suffix (-1/-2) and verified "
            "by eye against every capture (page 2 shows a lone 'BLOCK 4 OF "
            "4' header). Block hints are applied ONLY from this recorded "
            "metadata, never inferred at extraction time.",
            "validation_use_allowed=false: these captures calibrate the bank; "
            "once used for training they can never be validation material.",
            "Protocol asks >= 2 printed copies. All captures are labelled "
            "copy1; owner reports a second printed copy was produced and "
            "visually established as identical. Recorded as a deviation — "
            "copy-level holdout is therefore impossible for this campaign.",
        ],
    }
    CORPUS_MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"registered corpus manifest: {CORPUS_MANIFEST.relative_to(ROOT)}")


def load_gray(p: Path) -> np.ndarray:
    img = ImageOps.exif_transpose(Image.open(p)).convert("L")
    return np.asarray(img, dtype=np.float64) / 255.0


def page_of(filename: str) -> int:
    """Page ordinal from the capture filename suffix ("...-N.jpeg")."""
    stem = filename.rsplit(".", 1)[0]
    return int(stem.rsplit("-", 1)[1])


def page_block_hint(entry: dict, n_blocks: int) -> int | None:
    """Block hint for a capture, from RECORDED corpus metadata only.

    Returns the block index a single-group page may be labelled as, or
    None when the metadata does not pin the page to exactly one block.
    Never infers pagination from image content.
    """
    indices = entry.get("page_block_indices")
    if not indices or len(indices) != 1:
        return None
    idx = indices[0]
    if not (0 <= idx < n_blocks):
        raise ValueError(f"page_block_indices out of range: {indices}")
    return idx


# Extraction of a 12-MP capture takes O(1 min); cache each capture's result
# outside the repo. The key covers everything that determines the labelled
# output: capture sha, ground-truth sha, block hint, and the sha of every
# code module extraction depends on. Makes the pipeline resumable while any
# input or behavior change invalidates the cache.
CACHE_DIR = Path("/tmp/phaseb-extract-cache")
_EXTRACTOR_SHA = hashlib.sha256(
    (ROOT / "reader" / "calibration" / "extract.py").read_bytes()
    + (ROOT / "reader" / "registration.py").read_bytes()
    + (ROOT / "reader" / "structural_locator.py").read_bytes()).hexdigest()[:16]


def cache_key(capture_sha: str, gt_sha: str, block_hint: int | None,
              extractor_sha: str = _EXTRACTOR_SHA) -> str:
    return f"{capture_sha[:24]}-g{gt_sha[:16]}-{extractor_sha}-h{block_hint}"


def _extract_one(args: tuple[str, str, dict, str, int | None]):
    """Worker: extract one capture (cached)."""
    filename, sha, gt, gt_sha, block_hint = args
    key = CACHE_DIR / (cache_key(sha, gt_sha, block_hint) + ".pkl")
    if key.exists():
        with key.open("rb") as f:
            return filename, pickle.load(f)
    from reader.calibration.extract import extract_capture as _ec
    res = _ec(load_gray(CAPTURES / filename), gt,
              capture_sha256=sha, block_hint=block_hint)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = key.with_suffix(".tmp")
    with tmp.open("wb") as f:
        pickle.dump(res, f)
    tmp.replace(key)
    return filename, res


def main() -> None:
    cm = json.loads(CAPTURE_MANIFEST.read_text())
    assert cm["corpus_id"] == CORPUS_ID
    register_corpus(cm)
    require_flag(CORPUS_ID, "classifier_training_allowed")
    require_flag(CORPUS_ID, "threshold_calibration_allowed")

    sheet_ids = {im["sheet_id"] for im in cm["images"]}
    assert len(sheet_ids) == 1, f"mixed sheets in campaign: {sheet_ids}"
    sheet_id = sheet_ids.pop()
    gt_path = next(SHEETS.glob(f"*{sheet_id}.groundtruth.json"))
    gt = json.loads(gt_path.read_text())
    assert gt["sheet_id"] == sheet_id
    gt_sha = sha256_file(gt_path)
    corpus = json.loads(CORPUS_MANIFEST.read_text())
    corpus_by_name = {im["filename"]: im for im in corpus["images"]}

    samples = []
    per_capture = []
    cond_by_sha: dict[str, str] = {}
    for im in cm["images"]:
        p = CAPTURES / im["filename"]
        actual = sha256_file(p)
        if actual != im["sha256"]:
            raise SystemExit(f"HASH MISMATCH for {im['filename']}: manifest is stale")
        cond_by_sha[im["sha256"]] = im["condition"]

    with ProcessPoolExecutor(max_workers=4) as ex:
        results = dict(ex.map(_extract_one, [
            (im["filename"], im["sha256"], gt, gt_sha, None)
            for im in cm["images"]]))
    for im in cm["images"]:
        res = results[im["filename"]]
        per_capture.append({
            "filename": im["filename"], "condition": im["condition"],
            "lines_used": res.lines_used, "samples": len(res.samples),
            "accepted": bool(res.samples), "block_hint": None,
            "n_groups": res.n_groups,
            "dropped": res.lines_dropped,
        })
        samples.extend(res.samples)
        status = "ACCEPT" if res.samples else "REJECT"
        print(f"{im['filename']:55s} {status:7s} lines={res.lines_used} samples={len(res.samples)}")

    # ── pagination second pass ──────────────────────────────────────────
    # The physical print paginated 3+1: blocks 1-3 on page 1, block 4 on
    # page 2. That pagination is RECORDED per capture in the corpus
    # manifest (page / page_block_indices — see manifest notes for the
    # derivation); hints are applied only from that metadata, never
    # inferred from image content. Three additional guards:
    #   1. the metadata must pin the page to exactly one block index;
    #   2. the unhinted extraction must have seen exactly one group
    #      (BLOCK_GROUPS_1 rejection);
    #   3. at least one sibling capture must show the other n-1 groups on
    #      a single page (corroborates the recorded pagination).
    # The hinted extractor additionally requires one COMPLETE group.
    n_blocks = gt["blocks"]
    page1_full = [c for c in per_capture
                  if c["n_groups"] == n_blocks - 1]
    hint_jobs = []
    if page1_full:
        for c in per_capture:
            if c["accepted"]:
                continue
            if not any("BLOCK_GROUPS_1" in d["reason"] for d in c["dropped"]):
                continue
            hint = page_block_hint(corpus_by_name[c["filename"]], n_blocks)
            if hint is None:
                continue
            sha = next(im["sha256"] for im in cm["images"]
                       if im["filename"] == c["filename"])
            hint_jobs.append((c["filename"], sha, gt, gt_sha, hint))
    if hint_jobs:
        hint_by_name = {j[0]: j[4] for j in hint_jobs}
        with ProcessPoolExecutor(max_workers=4) as ex:
            hinted = dict(ex.map(_extract_one, hint_jobs))
        for c in per_capture:
            res = hinted.get(c["filename"])
            if res is not None and res.samples:
                hint = hint_by_name[c["filename"]]
                c.update({"lines_used": res.lines_used,
                          "samples": len(res.samples), "accepted": True,
                          "block_hint": hint,
                          "dropped": res.lines_dropped})
                samples.extend(res.samples)
                print(f"{c['filename']:55s} ACCEPT (page-2 hint block "
                      f"{hint + 1}) lines={res.lines_used} samples={len(res.samples)}")

    accepted = [c for c in per_capture if c["accepted"]]
    if len(accepted) < 2:
        raise SystemExit("fewer than 2 usable captures; grouped holdout impossible — stopping")

    print("\n== grouped holdout (leave-one-capture-out, frozen 0.64/0.02) ==")
    hold_cap = grouped_holdout(samples)
    print(json.dumps({k: hold_cap[k] for k in
                      ("n_groups", "mean_accuracy_on_decided", "operating_point")}, indent=2))
    print("\n== grouped holdout (leave-one-condition-out) ==")
    hold_cond = grouped_holdout(samples, group_key=lambda s: cond_by_sha[s.capture_sha256])
    if "error" not in hold_cond:
        print(json.dumps({k: hold_cond[k] for k in
                          ("n_groups", "mean_accuracy_on_decided")}, indent=2))

    bank_manifest = build_bank(samples, BANK_NPZ, BANK_MANIFEST,
                               bank_id=BANK_ID, corpus_id=CORPUS_ID)
    print(f"\nbank: {BANK_NPZ.relative_to(ROOT)} "
          f"({bank_manifest['n_samples']} samples, npz sha {bank_manifest['npz_sha256'][:12]}…)")

    if PROFILE_OUT.exists():
        raise SystemExit(f"refusing to overwrite existing profile {PROFILE_OUT}")
    base = json.loads(BASE_PROFILE.read_text())
    profile = dict(base)
    profile.update({
        "profile_id": "cal-run01-development",
        "classifier_id": (
            f"{BANK_ID} (real-print calibration bank, campaign cal-run01, "
            "spike-feat-v1 features, per-class max NN)"),
        "glyph_bank": {
            "path": str(BANK_NPZ.relative_to(ROOT)),
            "sha256": bank_manifest["npz_sha256"],
            "samples": bank_manifest["n_samples"],
            "manifest": str(BANK_MANIFEST.relative_to(ROOT)),
        },
        "calibration_corpora": [CORPUS_ID],
        "created": "2026-08-17",
        "status": "DEVELOPMENT / NOT GATE-A1 / NOT PRODUCTION",
        "warning": base["warning"],
    })
    PROFILE_OUT.write_text(json.dumps(profile, indent=2) + "\n")
    print(f"profile: {PROFILE_OUT.relative_to(ROOT)}")

    REPORT_OUT.write_text(json.dumps({
        "campaign_id": cm["campaign_id"],
        "corpus_id": CORPUS_ID,
        "sheet_id": sheet_id,
        "groundtruth_sha256": sha256_file(gt_path),
        "per_capture": per_capture,
        "holdout_leave_one_capture_out": hold_cap,
        "holdout_leave_one_condition_out": hold_cond,
        "bank": bank_manifest,
        "profile_path": str(PROFILE_OUT.relative_to(ROOT)),
        "status": "DEVELOPMENT / NOT GATE-A1",
        "pagination_deviation_note": (
            "The printed sheet paginated 3+1: blocks 1-3 on page 1, block 4 "
            "on page 2. Page-2 captures show a single block group and are "
            "labelled block 4 via an explicit block hint, justified by "
            "sibling page-1 captures of the same printed copy; hinted "
            "captures still require exactly one complete 12-line group. "
            "Mislabelling would surface as cratered holdout accuracy for "
            "those capture groups."),
        "copy_deviation_note": (
            "All captures labelled copy1; owner reports second printed copy "
            "visually identical. Copy-level holdout impossible; capture- and "
            "condition-level holdout reported instead."),
    }, indent=2) + "\n")
    print(f"report: {REPORT_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
