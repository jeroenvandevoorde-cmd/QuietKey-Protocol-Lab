"""Task 2 (Reader v0.2.1): deterministic quality audit of all 19 Bridge Run 01
development images. Reports every metric value against every profile
threshold. Diagnostic only — changes NO threshold, decodes NOTHING.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from reader.profile import load_profile  # noqa: E402
from reader.quality import assess_quality  # noqa: E402

CAPTURES = ROOT / "bridge" / "captures"
PROFILE = ROOT / "reader" / "profiles" / "spike-reader-v02-development.json"
OUT_JSON = ROOT / "reader" / "BRIDGE-RUN01-QUALITY-AUDIT.json"

# Which metrics each threshold constrains, and the comparison direction.
THRESHOLD_MAP = [
    ("laplacian_variance", "sharpness_min_laplacian_var", ">=", "LOW_SHARPNESS"),
    ("under_frac", "exposure_max_under_frac", "<=", "UNDEREXPOSED"),
    ("over_frac", "exposure_max_over_frac", "<=", "OVEREXPOSED"),
    ("footer_tonal_range", "exposure_min_footer_range", ">=", "LOW_FOOTER_TONAL_RANGE"),
    ("glare_region_frac", "glare_max_region_frac", "<=", "GLARE"),
    ("page_boundary_confidence", "page_min_boundary_confidence", ">=", "PAGE_NOT_CONFIDENT"),
    ("footer_line_candidates", "footer_min_line_candidates", ">=", "FOOTER_SIGNAL_TOO_WEAK"),
    ("footer_periodicity", "footer_min_periodicity", ">=", "FOOTER_SIGNAL_TOO_WEAK"),
    ("footer_extent_frac", "footer_min_extent_frac", ">=", "FOOTER_SIGNAL_TOO_WEAK"),
]


def load_gray(p: Path) -> np.ndarray:
    img = ImageOps.exif_transpose(Image.open(p)).convert("L")
    return np.asarray(img, dtype=np.float64) / 255.0


def main() -> None:
    profile = load_profile(PROFILE)
    q = profile.quality
    rows = []
    for p in sorted(CAPTURES.glob("bridge-*.jpeg")):
        r = assess_quality(load_gray(p), q)
        checks = []
        for metric, tkey, op, reason in THRESHOLD_MAP:
            val = r.metrics.get(metric)
            thr = q[tkey]
            ok = (val >= thr) if op == ">=" else (val <= thr)
            checks.append({"metric": metric, "value": val, "threshold_key": tkey,
                           "threshold": thr, "direction": op, "pass": bool(ok),
                           "reason_if_fail": reason})
        rows.append({"sheet": p.name, "status": r.status, "reasons": r.reasons,
                     "metrics": r.metrics, "checks": checks})

    by_reason: dict[str, list[str]] = {}
    for row in rows:
        for reason in row["reasons"]:
            by_reason.setdefault(reason, []).append(row["sheet"])

    payload = {
        "audit": "bridge-run01-quality-audit (Task 2, Reader v0.2.1)",
        "development_data": True,
        "profile": {"path": str(PROFILE.relative_to(ROOT)), "sha256": profile.sha256},
        "thresholds": q,
        "status_counts": {s: sum(1 for r in rows if r["status"] == s)
                          for s in ("ACCEPT", "RECAPTURE")},
        "rejections_grouped_by_reason": by_reason,
        "images": rows,
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2) + "\n")
    for row in rows:
        print(f"{row['sheet']:45s} {row['status']:9s} {';'.join(row['reasons'])}")
    print(json.dumps(payload["rejections_grouped_by_reason"], indent=2))
    print("written:", OUT_JSON)


if __name__ == "__main__":
    main()
