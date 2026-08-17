"""Reader v0.2.1 Calibration Acceptance Audit (owner-requested).

ANALYSIS ONLY. This script:
  - does NOT tune thresholds (0.64/0.02 frozen, reported as-is);
  - does NOT rebuild the bank, modify the classifier, registration,
    quality gates, protocol code, or any Bridge result artifact;
  - reads existing captures/samples/banks and recomputes evaluation
    statistics at the frozen operating point for reporting purposes.

Outputs:
  reader/calibration/acceptance-audit-cal-run01.json  (machine-readable)

Bridge Run 01 remains DEVELOPMENT_REPLAY material (regression flag
enforced). Per-sheet Bridge analysis is cached under /tmp keyed by
profile + code revision (slow pipeline, resumable).
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "interop" / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

import cloakvault_v3 as cv3  # frozen reference decoder (read-only)  # noqa: E402
from reader.calibration.bank import sample_feature  # noqa: E402
from reader.frame import _attempt_candidate  # noqa: E402
from reader.profile import load_profile  # noqa: E402
from reader.provenance import require_flag, sha256_file  # noqa: E402
from reader.quality import assess_quality  # noqa: E402
from reader.spike_bank_classifier import SpikeBank, make_spike_classifier  # noqa: E402
from reader.structural_locator import locate_footer_candidates  # noqa: E402

import phaseb_calibration as PB  # noqa: E402  (reuses its extraction cache)

FROZEN_CONF, FROZEN_MARGIN = 0.64, 0.02
OUT_JSON = ROOT / "reader" / "calibration" / "acceptance-audit-cal-run01.json"
PROFILE = ROOT / "reader" / "profiles" / "cal-run01-development.json"
BASELINE_REPLAY = ROOT / "reader" / "task0-spike-2026-08-replay.json"
NEW_REPLAY = ROOT / "reader" / "bridge-run01-dev-replay-v021-calbank.json"
PHASEB_REPORT = ROOT / "reader" / "calibration" / "phaseb-cal-run01-report.json"

GT_TOKENS = json.loads((ROOT / "spike" / "tokens.json").read_text())
T5 = next(t for t in GT_TOKENS["tokens"] if t["id"] == "T5")
GT_TOKEN = "".join(T5["wrapped_lines"])
assert len(GT_TOKEN) == cv3.TOKEN_LEN


# ───────────────────────── calibration samples ──────────────────────────

def collect_samples():
    """Re-load the exact labelled samples that built cal-run01-bank via the
    phaseb extraction cache (same code revision → cache hits, no re-extract
    variance)."""
    cm = json.loads(PB.CAPTURE_MANIFEST.read_text())
    corpus = json.loads(PB.CORPUS_MANIFEST.read_text())
    corpus_by_name = {im["filename"]: im for im in corpus["images"]}
    gt_path = next(PB.SHEETS.glob(f"*{cm['images'][0]['sheet_id']}.groundtruth.json"))
    gt = json.loads(gt_path.read_text())
    gt_sha = sha256_file(gt_path)
    n_blocks = gt["blocks"]

    report = json.loads(PHASEB_REPORT.read_text())
    hint_by_name = {c["filename"]: c["block_hint"] for c in report["per_capture"]}

    jobs = [(im["filename"], im["sha256"], gt, gt_sha,
             hint_by_name.get(im["filename"])) for im in cm["images"]]
    with ProcessPoolExecutor(max_workers=4) as ex:
        results = dict(ex.map(PB._extract_one, jobs))
    meta = {im["sha256"]: {"filename": im["filename"],
                           "condition": im["condition"], "copy": im["copy"],
                           "page": corpus_by_name[im["filename"]].get("page")}
            for im in cm["images"]}
    samples = [s for im in cm["images"] for s in results[im["filename"]].samples]
    return samples, results, meta, gt, report


# ─────────────────────── detailed grouped holdout ───────────────────────

def audited_holdout(samples, meta, group_key, scheme_name):
    """Reimplementation of evaluate._score bookkeeping with full per-sample
    records, at the FROZEN operating point. Same NN scoring math as
    reader/calibration/evaluate.py (per-class max cosine)."""
    groups = sorted({group_key(s) for s in samples})
    if len(groups) < 2:
        return {"scheme": scheme_name, "error": "NEED_AT_LEAST_2_GROUPS",
                "groups": groups}
    records = []  # (label, pred|None erased, top_conf, margin, group, capture_sha)
    folds = {}
    for g in groups:
        train = [s for s in samples if group_key(s) != g]
        test = [s for s in samples if group_key(s) == g]
        feats, labels = [], []
        for s in train:
            v = sample_feature(s)
            if v is not None:
                feats.append(v)
                labels.append(s.label)
        F = np.stack(feats)
        L = np.array(labels)
        idx = {c: np.flatnonzero(L == c) for c in sorted(set(labels))}
        fc = Counter()
        for s in test:
            v = sample_feature(s)
            if v is None:
                continue
            sc = F @ v
            per = sorted(((float(sc[i].max()), c) for c, i in idx.items()),
                         reverse=True)
            c1, top = per[0]
            margin = c1 - (per[1][0] if len(per) > 1 else -1.0)
            erased = c1 < FROZEN_CONF or margin < FROZEN_MARGIN
            outcome = ("erasure" if erased else
                       "correct" if top == s.label else "confident_wrong")
            fc[outcome] += 1
            records.append({"label": s.label, "pred": None if erased else top,
                            "conf": c1, "margin": margin, "outcome": outcome,
                            "group": g, "capture": s.capture_sha256})
        n = sum(fc.values())
        decided = n - fc["erasure"]
        folds[g] = {
            "n": n, "correct": fc["correct"], "erasure": fc["erasure"],
            "confident_wrong": fc["confident_wrong"],
            "accuracy_on_decided": fc["correct"] / max(1, decided),
            "coverage": decided / max(1, n),
        }
    tot = Counter(r["outcome"] for r in records)
    n = sum(tot.values())
    decided = n - tot["erasure"]
    return {
        "scheme": scheme_name,
        "operating_point": {"confidence_floor": FROZEN_CONF,
                            "margin_floor": FROZEN_MARGIN, "frozen": True},
        "totals": {
            "evaluated": n, "correct": tot["correct"],
            "erasure": tot["erasure"], "confident_wrong": tot["confident_wrong"],
            "correct_pct": 100 * tot["correct"] / max(1, n),
            "erasure_pct": 100 * tot["erasure"] / max(1, n),
            "confident_wrong_pct": 100 * tot["confident_wrong"] / max(1, n),
            "accuracy_on_decided": tot["correct"] / max(1, decided),
            "coverage_pct": 100 * decided / max(1, n),
        },
        "mean_fold_accuracy_on_decided": float(np.mean(
            [f["accuracy_on_decided"] for f in folds.values()])),
        "folds": folds,
        "_records": records,
    }


def confusion_analysis(records, meta):
    pairs = defaultdict(list)
    for r in records:
        if r["outcome"] == "confident_wrong":
            pairs[(r["label"], r["pred"])].append(r)
    rows = []
    for (src, pred), rs in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
        conds = Counter(meta[r["capture"]]["condition"] + "/" +
                        meta[r["capture"]]["filename"].rsplit("-", 1)[-1].split(".")[0]
                        for r in rs)
        rows.append({
            "source": src, "predicted": pred, "count": len(rs),
            "median_confidence": float(np.median([r["conf"] for r in rs])),
            "median_margin": float(np.median([r["margin"] for r in rs])),
            "by_condition_page": dict(conds),
        })
    matrix = Counter((r["label"], r["pred"] or "?") for r in records)
    return rows, {f"{a}->{b}": c for (a, b), c in sorted(matrix.items())}


def per_glyph_health(records, bank_labels):
    bank_counts = Counter(bank_labels)
    by_label = defaultdict(list)
    for r in records:
        by_label[r["label"]].append(r)
    out = {}
    for label in sorted(set(bank_counts) | set(by_label)):
        rs = by_label.get(label, [])
        n = len(rs)
        c = sum(1 for r in rs if r["outcome"] == "correct")
        e = sum(1 for r in rs if r["outcome"] == "erasure")
        w = sum(1 for r in rs if r["outcome"] == "confident_wrong")
        out[label] = {
            "bank_examples": bank_counts.get(label, 0),
            "held_out": n,
            "correct_pct": 100 * c / max(1, n),
            "erasure_pct": 100 * e / max(1, n),
            "confident_wrong_pct": 100 * w / max(1, n),
            "median_confidence": float(np.median([r["conf"] for r in rs])) if rs else None,
            "median_margin": float(np.median([r["margin"] for r in rs])) if rs else None,
        }
    return out


# ───────────────────────── Bridge instrumented rerun ────────────────────

BRIDGE = ROOT / "bridge" / "captures"
CACHE_DIR = Path("/tmp/phaseb-audit-cache")
_CODE_SHA = hashlib.sha256(
    b"".join(p.read_bytes() for p in sorted((ROOT / "reader").glob("*.py")))
    + Path(__file__).read_bytes()).hexdigest()[:16]
_wp = None  # worker profile
_wc = None  # worker classifier


def _token_rs_audit(token: str) -> dict:
    """Byte-level RS accounting of a (possibly erased) 142-char token vs the
    known T5 ground truth. Reimplements the frozen decoder's bit packing
    READ-ONLY; the frozen file is not modified."""
    S, DC, N = cv3.SENTINEL, cv3.DATA_CHARS, cv3.RS_N

    def received(body: str, gt_body: str):
        bits, erased = "", set()
        for i in range(DC):
            ch = body[i]
            if ch == "?":
                erased.add((i * 5) // 8)
                end = (i * 5 + 4) // 8
                if end < N:
                    erased.add(end)
                ch = gt_body[i]  # content of erased bytes is irrelevant to E
            bits += f"{cv3.CHARSET.index(ch):05b}"
        bits = bits[: N * 8]
        return bytes(int(bits[i * 8:i * 8 + 8], 2) for i in range(N)), erased

    gt_body = GT_TOKEN[len(S):]
    body = token[len(S):]
    rec, erased = received(body, gt_body)
    gt_rec, _ = received(gt_body, gt_body)
    E = sum(1 for i in range(N) if i not in erased and rec[i] != gt_rec[i])
    e = len(erased)
    return {"rs_error_bytes_E": E, "rs_erasure_bytes_e": e,
            "two_E_plus_e": 2 * E + e, "rs_parity_budget": cv3.RS_PARITY,
            "within_budget": 2 * E + e <= cv3.RS_PARITY}


def _audit_sheet(path_str: str) -> dict:
    """Worker: rerun one Bridge sheet read-only with a recording classifier;
    reconstruct the winning candidate's token and compare to ground truth."""
    global _wp, _wc
    p = Path(path_str)
    if _wp is None:
        _wp = load_profile(PROFILE)
        _wc = make_spike_classifier(
            SpikeBank(ROOT / _wp.data["glyph_bank"]["path"]))
    key = CACHE_DIR / f"{p.name}-{_wp.sha256[:16]}-{_CODE_SHA}.pkl"
    if key.exists():
        with key.open("rb") as f:
            return pickle.load(f)

    img = ImageOps.exif_transpose(Image.open(p)).convert("L")
    gray = np.asarray(img, dtype=np.float64) / 255.0
    q = assess_quality(gray, _wp.quality)
    cands = locate_footer_candidates(gray)

    attempts = []
    winner = None
    for i, cand in enumerate(cands):
        a = _attempt_candidate(gray, cand, i, _wp, _wc)
        attempts.append(a)
        if a.category is None:
            winner = a
            break
    # identical selection rule to read_frame (deepest honest failure)
    chosen = winner or max(
        attempts, key=lambda a: (a.depth, -a.erasures if a.classified else 0,
                                 -a.index))
    token = chosen.token
    char_stats = rs_stats = None
    if token is not None and len(token) == len(GT_TOKEN):
        c = sum(1 for a, b in zip(token, GT_TOKEN) if a == b and a != "?")
        er = token.count("?")
        w = len(token) - c - er
        char_stats = {"token_chars": len(token), "correct": c,
                      "erasure": er, "confident_wrong": w}
        rs_stats = _token_rs_audit(token)
    aead = None
    if winner is not None:
        try:
            out = cv3.decode_pipeline(token.replace("?", "q"), bytes.fromhex(T5["vault_key_hex"]))
            aead = "AUTHENTICATED" if bytes(out).hex() == T5["entropy_hex"] else "ENTROPY_MISMATCH"
        except Exception as exc:
            aead = f"FAIL:{type(exc).__name__}"
    rec = {
        "sheet": p.name,
        "quality_status": q.status,
        "quality_reasons": q.reasons,
        "quality_metrics": {k: q.metrics[k] for k in
                            ("laplacian_variance", "under_frac", "over_frac",
                             "glare_region_frac", "page_boundary_confidence")
                            if k in q.metrics},
        "candidate_rank_used": chosen.index,
        "n_candidates": len(cands),
        "rs_valid": winner is not None,
        "rs_reason": chosen.reason,
        "classified_chars": chosen.classified,
        "erasure_cells": chosen.erasures,
        "decoder_rs_erasures": chosen.rs_erasures,
        "token_char_stats_vs_gt": char_stats,
        "rs_byte_audit_vs_gt": rs_stats,
        "aead": aead if winner is not None else "NOT_REACHED",
        "category": "RS_VALID" if winner is not None else
                    (chosen.category.name if chosen.category else "?"),
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = key.with_suffix(".tmp")
    with tmp.open("wb") as f:
        pickle.dump(rec, f)
    tmp.replace(key)
    return rec


def main() -> None:
    require_flag("cal-run01-raw", "classifier_training_allowed")
    require_flag("bridge-run01-development", "regression_testing_allowed")

    samples, results, meta, gt, report = collect_samples()
    bank = SpikeBank(ROOT / json.loads(PROFILE.read_text())["glyph_bank"]["path"])
    bank_labels = list(bank.labels)

    cond_of = lambda s: meta[s.capture_sha256]["condition"]  # noqa: E731
    cap = audited_holdout(samples, meta, lambda s: s.capture_sha256,
                          "leave-one-capture-out")
    cond = audited_holdout(samples, meta, cond_of, "leave-one-condition-out")
    copies = sorted({m["copy"] for m in meta.values()})
    copy_out = ({"scheme": "leave-one-print-copy-out",
                 "error": "INVALID_WITH_CURRENT_CORPUS",
                 "copies_present": copies,
                 "note": "all captures are copy1; copy-level holdout is "
                         "impossible (recorded corpus deviation)"}
                if len(copies) < 2 else
                audited_holdout(samples, meta, lambda s: meta[s.capture_sha256]["copy"],
                                "leave-one-print-copy-out"))

    confusion_rows, matrix = confusion_analysis(cap["_records"], meta)
    glyph_health = per_glyph_health(cap["_records"], bank_labels)

    # extraction quality per accepted capture
    extraction = []
    for sha, m in meta.items():
        res = next(r for fn, r in results.items() if fn == m["filename"])
        pitches = [s.pitch for s in res.samples]
        extraction.append({
            "filename": m["filename"], "condition": m["condition"],
            "page": m["page"], "accepted": bool(res.samples),
            "lines_used": res.lines_used,
            "lines_dropped": len(res.lines_dropped),
            "drop_reasons": Counter(d["reason"].split(":")[0].split("_LINES")[0]
                                    for d in res.lines_dropped).most_common(6),
            "samples": len(res.samples),
            "pitch_median": float(np.median(pitches)) if pitches else None,
            "pitch_iqr": (float(np.percentile(pitches, 75) - np.percentile(pitches, 25))
                          if pitches else None),
        })

    # Bridge rerun (read-only, cached)
    sheets = sorted(BRIDGE.glob("bridge-*.jpeg"))
    with ProcessPoolExecutor(max_workers=4) as ex:
        bridge_rows = list(ex.map(_audit_sheet, [str(p) for p in sheets]))

    baseline = json.loads(BASELINE_REPLAY.read_text())
    new_replay = json.loads(NEW_REPLAY.read_text())

    for scheme in (cap, cond):
        scheme.pop("_records", None)

    OUT_JSON.write_text(json.dumps({
        "audit": "reader-v021-calibration-acceptance",
        "status": "DEVELOPMENT / NOT GATE-A1 / ANALYSIS-ONLY",
        "frozen_operating_point": {"confidence_floor": FROZEN_CONF,
                                   "margin_floor": FROZEN_MARGIN},
        "holdout_leave_one_capture_out": cap,
        "holdout_leave_one_condition_out": cond,
        "holdout_leave_one_print_copy_out": copy_out,
        "confusion_top": confusion_rows,
        "confusion_matrix_decided": matrix,
        "per_glyph_health": glyph_health,
        "extraction_quality": extraction,
        "bridge_rerun": bridge_rows,
        "baseline_replay_categories": baseline["category_counts"],
        "new_replay_categories": new_replay["category_counts"],
    }, indent=2, default=str) + "\n")
    print("written:", OUT_JSON.relative_to(ROOT))


if __name__ == "__main__":
    main()
