"""Phase D prerequisite: derive the runtime pitch/line-height tolerance
EMPIRICALLY from cal-run02 production calibration captures (allowed source
per owner instruction step 4), NOT from S46/Bridge (banned source).

For every accepted footer token line in the cal-run02 captures we record

    ratio = layout-consistent expected pitch (band span / expected chars)
            over detected band ink height (row_end - row_start)

The ratio is scale- and perspective-invariant to first order (pitch and
ink height scale together under zoom / mild perspective), so its observed
distribution — over 2 physical copies, 2 pages, 3 capture conditions —
defines the physically plausible glyph-pitch range the runtime frame
pipeline may accept for a monospace production footer line.

Writes reader/calibration/phased-geometry.json.
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

from reader.calibration import extract_v2 as EV2  # noqa: E402
from reader.calibration.extract_v2 import (  # noqa: E402
    band_is_token_plausible, dedupe_same_line_bands, group_bands_by_spacing,
    is_footer_group)

CORPUS = json.loads((ROOT / "reader/corpora/cal-run02-production-raw.json").read_text())
GT = json.loads(next((ROOT / "reader/calibration/sheets").glob(
    "*production-v2*.groundtruth.json")).read_text())


def main() -> None:
    f0 = GT["footers"][0]
    widths = [len(l) for l in f0["lines_as_printed"][:3]]
    cache = Path("/tmp/phased-geom-cache")
    cache.mkdir(exist_ok=True)
    rows = []
    for entry in CORPUS["images"]:
        cfile = cache / f"{entry['sha256']}.json"
        if cfile.exists():
            rows.extend(json.loads(cfile.read_text()))
            continue
        crows: list[dict] = []
        path = ROOT / "reader/calibration/captures" / entry["filename"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"capture hash mismatch: {path}")
        g = np.asarray(ImageOps.exif_transpose(Image.open(path)).convert("L"),
                       dtype=np.float64) / 255.0
        bands = EV2._text_bands(g, None)
        g_rot, skew = EV2._deskew(g)
        if skew != 0.0:
            b2 = EV2._text_bands(g_rot, None)
            tb_a = [b for b in bands if band_is_token_plausible(b, widths)]
            tb_b = [b for b in b2 if band_is_token_plausible(b, widths)]
            if len(tb_b) > len(tb_a):
                bands = b2
        bands.sort(key=lambda b: b.row_start)
        tb = [b for b in bands if band_is_token_plausible(b, widths)]
        tb = dedupe_same_line_bands(tb, widths)
        for grp in (group_bands_by_spacing(tb) if tb else []):
            if not is_footer_group(grp, widths):
                continue
            for li, b in enumerate(grp):
                span = float(b.x1 - b.x0)
                p_exp = span / widths[li]
                h = float(b.row_end - b.row_start)
                crows.append({
                    "capture": entry["capture_id"], "copy": entry["print_copy"],
                    "condition": entry["condition"], "line": li,
                    "band_height": h, "p_exp": round(p_exp, 3),
                    "detected_pitch": round(float(b.pitch), 3),
                    "pitch_over_height": round(p_exp / h, 4),
                })
        cfile.write_text(json.dumps(crows))
        rows.extend(crows)
        print(f"{entry['capture_id']}: {len(crows)} lines", flush=True)
    ratios = np.array([r["pitch_over_height"] for r in rows])
    summary = {
        "source": "cal-run02 production captures (owner-approved tolerance source)",
        "n_lines": len(rows),
        "ratio_min": float(ratios.min()),
        "ratio_max": float(ratios.max()),
        "ratio_median": float(np.median(ratios)),
        "ratio_p5": float(np.percentile(ratios, 5)),
        "ratio_p95": float(np.percentile(ratios, 95)),
        "rows": rows,
    }
    (ROOT / "reader/calibration/phased-geometry.json").write_text(
        json.dumps(summary, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
