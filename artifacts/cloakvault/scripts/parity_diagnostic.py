"""Production-domain parity diagnostic — Task 2 (visual-domain difference).

ANALYSIS ONLY. Compares clean calibration glyph windows (cal-run01, std
condition) against the pristine Bridge S46 footer glyph windows after the
SAME localization/registration used by the audited replay (candidate rank
selected by read_frame's rule). Ground truth is used only for reporting; no
bank is built or modified, no thresholds are touched, S46 never enters any
training set.

Output: reader/calibration/parity-diagnostic-cal-run01-vs-S46.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from reader.frame import _attempt_candidate  # noqa: E402
from reader.profile import load_profile  # noqa: E402
from reader.provenance import require_flag  # noqa: E402
from reader.registration import register_line  # noqa: E402
from reader.spike_bank_classifier import SpikeBank, make_spike_classifier  # noqa: E402
from reader.structural_locator import locate_footer_candidates  # noqa: E402

import phaseb_calibration as PB  # noqa: E402

PROFILE = ROOT / "reader" / "profiles" / "cal-run01-development.json"
S46 = ROOT / "bridge" / "captures" / "bridge-baseline-0-std-S46.jpeg"
OUT = ROOT / "reader" / "calibration" / "parity-diagnostic-cal-run01-vs-S46.json"


def window_stats(win: np.ndarray) -> dict | None:
    """Physical glyph statistics on one grayscale window (raw scale)."""
    g = np.asarray(win, dtype=np.float64)
    if g.max() <= 1.5:
        g = g * 255.0
    g8 = np.clip(g, 0, 255).astype(np.uint8)
    thr, binv = cv2.threshold(g8, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = binv > 0
    if ink.sum() < 4:
        return None
    ys, xs = np.nonzero(ink)
    h, w = ink.shape
    dist = cv2.distanceTransform(binv, cv2.DIST_L2, 3)
    stroke = 2.0 * float(np.median(dist[ink]))
    return {
        "ink_frac": float(ink.mean()),
        "glyph_height_frac": float((ys.max() - ys.min() + 1) / h),
        "glyph_width_frac": float((xs.max() - xs.min() + 1) / w),
        "stroke_width_px": stroke,
        "fg_mean": float(g[ink].mean()),
        "bg_mean": float(g[~ink].mean()),
        "contrast": float(g[~ink].mean() - g[ink].mean()),
        "centroid_dx": float((xs.mean() - (w - 1) / 2) / w),
        "centroid_dy": float((ys.mean() - (h - 1) / 2) / h),
        "grad_energy": float(np.mean(np.abs(cv2.Sobel(g8, cv2.CV_64F, 1, 0)) +
                                     np.abs(cv2.Sobel(g8, cv2.CV_64F, 0, 1)))),
        "otsu_thr": float(thr),
    }


def summarize(rows: list[dict]) -> dict:
    keys = rows[0].keys()
    out = {}
    for k in keys:
        v = np.array([r[k] for r in rows])
        out[k] = {"median": float(np.median(v)),
                  "p25": float(np.percentile(v, 25)),
                  "p75": float(np.percentile(v, 75))}
    return out


def cut_windows(gray01: np.ndarray, lines, pitch_scale: float = 1.0):
    """Cut per-cell windows exactly the way the spike classifier does
    (pitch-scaled 19x34+3 boxes) but return raw-scale crops."""
    wins, pitches = [], []
    for strip, centers, y_mid, pitch in lines:
        s = pitch / 18.8  # bank pitch_ref used by classifier scaling
        ww = max(3, int(round((19 + 6) * s)))
        wh = max(3, int(round((34 + 6) * s)))
        for cx in centers:
            x0 = int(round(cx - ww / 2))
            y0 = int(round(y_mid - wh / 2))
            win = strip[max(0, y0):y0 + wh, max(0, x0):x0 + ww]
            if win.size:
                wins.append(win)
                pitches.append(pitch)
    return wins, pitches


def s46_lines(profile):
    img = ImageOps.exif_transpose(Image.open(S46)).convert("L")
    gray = np.asarray(img, dtype=np.float64) / 255.0
    cands = locate_footer_candidates(gray)
    # identical selection to the audited replay: iterate in rank order,
    # keep the attempt read_frame would report (deepest honest failure)
    classifier = make_spike_classifier(SpikeBank(ROOT / profile.data["glyph_bank"]["path"]))
    attempts = []
    for i, cand in enumerate(cands):
        a = _attempt_candidate(gray, cand, i, profile, classifier)
        attempts.append((a, cand))
        if a.category is None:
            break
    chosen, cand = max(attempts, key=lambda t: (t[0].depth,
                                                -t[0].erasures if t[0].classified else 0,
                                                -t[0].index))
    lines = []
    lines_hinted = []
    confs_all, margins_all = [], []
    confs_h, margins_h = [], []
    for l in cand.lines:
        pad_y = max(2, (l.row_end - l.row_start) // 2)
        pad_x = int(round(2 * max(l.pitch, 1.0)))
        strip = gray[max(0, l.row_start - pad_y):min(gray.shape[0], l.row_end + pad_y),
                     max(0, l.x0 - pad_x):min(gray.shape[1], l.x1 + pad_x)]
        try:
            model = register_line(strip)
        except ValueError:
            continue
        centers = model.centers()
        y_mid = float(np.mean(model.y_at(centers)))
        lines.append((strip * 255.0, centers, y_mid, model.pitch))
        _, confs, margins = classifier(strip, centers, y_mid, 0.0, 0.0)
        confs_all += list(confs)
        margins_all += list(margins)
        # DIAGNOSTIC ONLY: re-register with the locator's layout pitch as a
        # hint (register_line public param). This changes NO production
        # behaviour; it measures how much of the collapse is the harmonic.
        try:
            mh = register_line(strip, pitch_hint=l.pitch)
        except (ValueError, TypeError):
            continue
        ch = mh.centers()
        yh = float(np.mean(mh.y_at(ch)))
        lines_hinted.append((strip * 255.0, ch, yh, mh.pitch))
        _, cfs, mgs = classifier(strip, ch, yh, 0.0, 0.0)
        confs_h += list(cfs)
        margins_h += list(mgs)
    return chosen.index, lines, confs_all, margins_all, lines_hinted, confs_h, margins_h


def main() -> None:
    require_flag("cal-run01-raw", "classifier_training_allowed")
    require_flag("bridge-run01-development", "regression_testing_allowed")
    profile = load_profile(PROFILE)
    bank = SpikeBank(ROOT / profile.data["glyph_bank"]["path"])
    classifier = make_spike_classifier(bank)

    # ── calibration side: std captures (clean condition), cached samples ──
    cm = json.loads(PB.CAPTURE_MANIFEST.read_text())
    report = json.loads((ROOT / "reader" / "calibration" /
                         "phaseb-cal-run01-report.json").read_text())
    hint = {c["filename"]: c["block_hint"] for c in report["per_capture"]}
    gt_path = next(PB.SHEETS.glob(f"*{cm['images'][0]['sheet_id']}.groundtruth.json"))
    gt = json.loads(gt_path.read_text())
    from reader.provenance import sha256_file
    gt_sha = sha256_file(gt_path)
    cal_rows, cal_pitches, cal_confs, cal_margins = [], [], [], []
    for im in cm["images"]:
        if im["condition"] != "std":
            continue
        _, res = PB._extract_one((im["filename"], im["sha256"], gt, gt_sha,
                                  hint.get(im["filename"])))
        for s in res.samples:
            st = window_stats(s.window)
            if st:
                cal_rows.append(st)
                cal_pitches.append(s.pitch)
        # full-bank top-cosine for the same windows (self-match upper bound
        # noted in output; holdout medians come from the acceptance audit)
        from reader.calibration.bank import sample_feature
        classes = np.unique(bank.labels)
        cidx = {c: np.flatnonzero(bank.labels == c) for c in classes}
        for s in res.samples:
            v = sample_feature(s)
            if v is None:
                continue
            sc = bank.features @ v
            per = sorted((float(sc[i].max()) for i in cidx.values()), reverse=True)
            cal_confs.append(per[0])
            cal_margins.append(per[0] - per[1])

    # ── S46 side ──
    (cand_rank, lines, s46_confs, s46_margins,
     lines_h, s46_confs_h, s46_margins_h) = s46_lines(profile)
    s46_wins, s46_pitches = cut_windows(None, lines)
    s46_wins_h, s46_pitches_h = cut_windows(None, lines_h)
    s46_rows_h = [st for st in (window_stats(w) for w in s46_wins_h) if st]
    s46_rows = [st for st in (window_stats(w) for w in s46_wins) if st]

    out = {
        "diagnostic": "cal-run01(std) vs Bridge S46 footer",
        "status": "DEVELOPMENT / ANALYSIS-ONLY / S46 NEVER TRAINED ON",
        "s46_candidate_rank": cand_rank,
        "n_windows": {"cal_std": len(cal_rows), "s46": len(s46_rows)},
        "pitch_px": {"cal_std_median": float(np.median(cal_pitches)),
                     "s46_median": float(np.median(s46_pitches)),
                     "s46_all_line_pitches": [float(p) for p in sorted(set(round(p, 3) for p in s46_pitches))],
                     "s46_hinted_median": float(np.median(s46_pitches_h)) if s46_pitches_h else None},
        "physical_stats": {"cal_std": summarize(cal_rows), "s46": summarize(s46_rows),
                           "s46_hinted": summarize(s46_rows_h) if s46_rows_h else None},
        "bank_top_cosine": {
            "note": "cal_std values are FULL-BANK self-matches (optimistic "
                    "upper bound, bank contains these samples); holdout "
                    "medians per glyph are in acceptance-audit JSON "
                    "(~0.89-0.93). s46 values are honest out-of-bank scores.",
            "cal_std_selfmatch": {p: float(np.percentile(cal_confs, p)) for p in (5, 25, 50, 75, 95)},
            "s46": {p: float(np.percentile(s46_confs, p)) for p in (5, 25, 50, 75, 95)},
            "cal_std_margin_selfmatch": {50: float(np.percentile(cal_margins, 50))},
            "s46_margin": {50: float(np.percentile(s46_margins, 50))},
            "frozen_conf_floor": 0.64,
            "s46_frac_below_conf_floor": float(np.mean(np.array(s46_confs) < 0.64)),
            "s46_hinted": ({p: float(np.percentile(s46_confs_h, p)) for p in (5, 25, 50, 75, 95)}
                           if s46_confs_h else None),
            "s46_hinted_margin": {50: float(np.percentile(s46_margins_h, 50))} if s46_margins_h else None,
            "s46_hinted_frac_below_conf_floor": (float(np.mean(np.array(s46_confs_h) < 0.64))
                                                 if s46_confs_h else None),
        },
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print("written:", OUT.relative_to(ROOT))
    print(json.dumps({k: out[k] for k in ("pitch_px", "bank_top_cosine")}, indent=1))


if __name__ == "__main__":
    main()
