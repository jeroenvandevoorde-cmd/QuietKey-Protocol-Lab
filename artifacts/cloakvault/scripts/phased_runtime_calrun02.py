"""Phase D step 5/6 — run the ACTUAL frame pipeline on all 12 cal-run02
production captures (owner instruction: do not evaluate only with the
known-layout calibration extractor).

Per capture/footer this reports quality status, locator status, selected
candidate, selected vs expected pitch, cell count, registration status,
classification correct/erasure/confident-wrong against calibration ground
truth at frozen 0.64/0.02, and any harmonic rejection. Calibration tokens
are intentionally not RS-valid, so no authenticated decoding is required.

GT alignment note: ground-truth footers are located on the page with the
same band-grouping used by the calibration extractor — ONLY to know which
GT footer a runtime candidate overlaps. Registration, pitch selection, and
classification are the normal frame-reader path (frame.prepare_candidate_lines
+ registration.register_line + bank classifier), not the extractor.

Results cached per capture in /tmp (keyed on capture sha + code sha) so the
run survives shell timeouts. Writes reader/calibration/phased-runtime-calrun02.json.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from reader.calibration.extract_v2 import (  # noqa: E402
    _text_bands, band_is_token_plausible, dedupe_same_line_bands,
    group_bands_by_spacing, is_footer_group)
from reader.calibration.extract import _deskew  # noqa: E402
from reader.frame import prepare_candidate_lines  # noqa: E402
from reader.profile import load_profile  # noqa: E402
from reader.quality import assess_quality  # noqa: E402
from reader.registration import register_line  # noqa: E402
from reader.spike_bank_classifier import SpikeBank, make_spike_classifier  # noqa: E402
from reader.structural_locator import locate_footer_candidates  # noqa: E402

from phasec_s46_replay import ensure_profile  # noqa: E402  (validates bank provenance)

CORPUS_PATH = ROOT / "reader/corpora/cal-run02-production-raw.json"
CORPUS = json.loads(CORPUS_PATH.read_text())
GT = json.loads(next((ROOT / "reader/calibration/sheets").glob(
    "*production-v2*.groundtruth.json")).read_text())
CAPTURES = ROOT / "reader/calibration/captures"
OUT = ROOT / "reader/calibration/phased-runtime-calrun02.json"

CODE_SHA = hashlib.sha256(b"".join(
    (ROOT / p).read_bytes() for p in (
        "reader/frame.py", "reader/registration.py",
        "reader/structural_locator.py", "scripts/phased_runtime_calrun02.py",
        "reader/profiles/cal-run01-development.json"))).hexdigest()[:16]
CACHE = Path("/tmp/phased-runtime-cache")
CACHE.mkdir(exist_ok=True)


def overlap(a0, a1, b0, b1) -> int:
    return max(0, min(a1, b1) - max(a0, b0))


def eval_capture(entry: dict, profile, classifier) -> dict:
    path = CAPTURES / entry["filename"]
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        raise RuntimeError(f"capture hash mismatch: {path}")
    gray = np.asarray(ImageOps.exif_transpose(Image.open(path)).convert("L"),
                      dtype=np.float64) / 255.0

    q = assess_quality(gray, profile.quality)

    f0 = GT["footers"][entry["page_footer_indices"][0]]
    widths = [len(l) for l in f0["lines_as_printed"][:3]]  # band plausibility only

    # GT footer locations (extractor band grouping — alignment only)
    bands = _text_bands(gray, None)
    g_rot, skew = _deskew(gray)
    used_gray = gray
    if skew != 0.0:
        b2 = _text_bands(g_rot, None)
        if (len([b for b in b2 if band_is_token_plausible(b, widths)])
                > len([b for b in bands if band_is_token_plausible(b, widths)])):
            bands, used_gray = b2, g_rot
    bands.sort(key=lambda b: b.row_start)
    tb = dedupe_same_line_bands(
        [b for b in bands if band_is_token_plausible(b, widths)], widths)
    groups = [g for g in (group_bands_by_spacing(tb) if tb else [])
              if is_footer_group(g, widths)]

    cands = locate_footer_candidates(used_gray)

    footers = []
    for gi, grp in enumerate(groups):
        fi = entry["page_footer_indices"][gi] if gi < len(entry["page_footer_indices"]) else None
        g0, g1 = grp[0].row_start, grp[-1].row_end
        # best-overlapping runtime candidate
        best_ci, best_ov = None, 0
        for ci, cand in enumerate(cands):
            r0 = min(l.row_start for l in cand.lines)
            r1 = max(l.row_end for l in cand.lines)
            ov = overlap(g0, g1, r0, r1)
            if ov > best_ov:
                best_ci, best_ov = ci, ov
        frec = {"gt_footer": fi, "rows": [int(g0), int(g1)],
                "locator": "MISS" if best_ci is None else "FOUND",
                "candidate_index": best_ci, "lines": []}
        if best_ci is None:
            footers.append(frec)
            continue
        cand = cands[best_ci]
        prepared = prepare_candidate_lines(used_gray, cand, profile)

        # Register + classify all lines FIRST (blind — no GT involved).
        classified = []  # (l, sel, li, text or None, fail_reason)
        for l, strip, sel, n_hint in prepared:
            ovs = [(overlap(l.row_start, l.row_end, b.row_start, b.row_end), j)
                   for j, b in enumerate(grp)]
            best = max(ovs) if ovs else (0, None)
            li = best[1] if best[0] > 0 else None
            try:
                model = register_line(strip, n_cells_hint=n_hint,
                                      pitch_hint=sel.pitch if sel.pitch > 0 else None)
            except ValueError as exc:
                classified.append((l, sel, li, None, str(exc)))
                continue
            centers = model.centers()
            y_mid = float(np.mean(model.y_at(centers)))
            text, confs, _ = classifier(strip, centers, y_mid,
                                        profile.confidence_floor,
                                        profile.margin_floor)
            classified.append((l, sel, li, text, None))

        # GT footer identity (EVALUATION ONLY): index-order group→footer
        # assignment breaks whenever a group is missed, so identify which
        # footer this candidate actually printed by text agreement across
        # small shifts. Reader output is unchanged — this only picks the
        # right answer key.
        def match_score(gt_f) -> int:
            tot = 0
            for _, _, li, text, _ in classified:
                if text is None or li is None:
                    continue
                gl = gt_f["lines_as_printed"][li] if li < len(gt_f["lines_as_printed"]) else ""
                tot += max(sum(1 for i, ch in enumerate(text)
                               if ch != "?" and 0 <= i + sh < len(gl)
                               and ch == gl[i + sh])
                           for sh in range(-2, 3))
            return tot
        scores = [(match_score(GT["footers"][fj]), fj)
                  for fj in entry["page_footer_indices"]]
        best_score, fi_text = max(scores)
        fi_used = fi_text if best_score >= 10 else fi
        frec["gt_footer_by_rows"] = fi
        frec["gt_footer"] = fi_used
        frec["gt_footer_id_method"] = ("text_match" if best_score >= 10
                                       else "row_order_fallback")

        gt_f = GT["footers"][fi_used] if fi_used is not None else None
        token = gt_f["token"] if gt_f else None
        f_widths = [len(x) for x in gt_f["lines_as_printed"][:3]] if gt_f else widths
        spans_by_line = ({s["line"]: s for s in gt_f["token_line_spans"]}
                         if gt_f else {})

        for l, sel, li, text, fail in classified:
            span = float(l.x1 - l.x0)
            exp_pitch = round(span / f_widths[li], 3) if li is not None else None
            lrec = {"gt_line": li, "detected": l.detected,
                    "selected_pitch": sel.diagnostics()["selected_pitch"],
                    "selection_method": sel.method,
                    "expected_pitch": exp_pitch,
                    "harmonic_rejections": sel.harmonic_rejections}
            if text is None:
                lrec.update({"registration": f"FAIL:{fail}", "cells": None})
                frec["lines"].append(lrec)
                continue
            lrec.update({"registration": "OK", "cells": len(text),
                         "expected_cells": f_widths[li] if li is not None else None})
            if li is not None and gt_f is not None:
                gl = gt_f["lines_as_printed"][li] if li < len(gt_f["lines_as_printed"]) else ""
                sh_scores = [(sum(1 for i, ch in enumerate(text)
                                  if ch != "?" and 0 <= i + sh < len(gl)
                                  and ch == gl[i + sh]), -abs(sh), sh)
                             for sh in range(-2, 3)]
                lrec["best_shift"] = max(sh_scores)[2] if max(sh_scores)[0] > 0 else None
            if li is not None and len(text) == f_widths[li] and token is not None:
                sp = spans_by_line[li]
                start, n_tok = int(sp["prefix_chars"]), int(sp["token_chars"])
                tok_off = sum(spans_by_line[j]["token_chars"] for j in range(li))
                gt_cells = token[tok_off:tok_off + n_tok]
                got = text[start:start + n_tok]
                cor = sum(1 for a, b in zip(got, gt_cells) if a == b and a != "?")
                era = got.count("?")
                lrec["token_cells"] = {"n": n_tok, "correct": cor, "erasure": era,
                                       "confident_wrong": n_tok - cor - era}
            frec["lines"].append(lrec)
        footers.append(frec)

    return {
        "capture_id": entry["capture_id"], "filename": entry["filename"],
        "copy": entry["print_copy"], "page": entry["page"],
        "condition": entry["condition"], "quality_status": q.status,
        "n_locator_candidates": len(cands),
        "n_gt_footers_located": len(groups),
        "n_gt_footers_expected": len(entry["page_footer_indices"]),
        "footers": footers,
    }


def main() -> None:
    profile = load_profile(ensure_profile())
    assert profile.confidence_floor == 0.64 and profile.margin_floor == 0.02
    classifier = make_spike_classifier(SpikeBank(ROOT / profile.data["glyph_bank"]["path"]))

    per_capture = []
    for entry in CORPUS["images"]:
        cfile = CACHE / f"{entry['sha256']}-{CODE_SHA}.json"
        if cfile.exists():
            per_capture.append(json.loads(cfile.read_text()))
            continue
        rec = eval_capture(entry, profile, classifier)
        cfile.write_text(json.dumps(rec))
        per_capture.append(rec)
        print(f"done {entry['filename']}", flush=True)

    def pool(recs):
        n = c = e = 0
        cells_ok = cells_total = 0
        for r in recs:
            for f in r["footers"]:
                for l in f["lines"]:
                    if l.get("cells") is not None and l.get("expected_cells"):
                        cells_total += 1
                        cells_ok += int(l["cells"] == l["expected_cells"])
                    tc = l.get("token_cells")
                    if tc:
                        n += tc["n"]; c += tc["correct"]; e += tc["erasure"]
        cw = n - c - e
        decided = n - e
        return {
            "token_cells": n, "correct": c, "erasure": e, "confident_wrong": cw,
            "correct_pct": round(c / n, 4) if n else None,
            "erasure_pct": round(e / n, 4) if n else None,
            "confident_wrong_pct": round(cw / n, 4) if n else None,
            "decided_accuracy": round(c / decided, 4) if decided else None,
            "coverage": round(decided / n, 4) if n else None,
            "lines_with_expected_cell_count": f"{cells_ok}/{cells_total}",
        }

    grouped = {}
    for key in ("copy", "page", "condition"):
        vals = sorted({r[key] for r in per_capture})
        grouped[f"by_{key}"] = {str(v): pool([r for r in per_capture if r[key] == v])
                                for v in vals}

    out = {
        "run": "phase D runtime frame-pipeline evaluation on cal-run02",
        "profile": "cal-run02-development (frozen 0.64/0.02)",
        "code_sha_prefix": CODE_SHA,
        "pooled": pool(per_capture),
        **grouped,
        "captures": per_capture,
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({"pooled": out["pooled"], **grouped}, indent=1))


if __name__ == "__main__":
    main()
