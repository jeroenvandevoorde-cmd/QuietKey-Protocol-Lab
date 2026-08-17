#!/usr/bin/env python3
"""Deterministic calibration-sheet generator (Reader v0.2.1, Task 5).

Produces a printable HTML sheet whose glyph blocks use the PRODUCTION
footer typography (Menlo 10px, gray, copied verbatim from the product
print path — see spike/sheet.html and src/pages/create.tsx), plus a
ground-truth JSON describing the exact layout and character content.

Design constraints:
- Charset is exactly the 32-character Bech32 alphabet (which already
  contains 'c', 'v', and '0' — full sentinel coverage). No wrapper
  constants, no real tokens, no protocol structure: content is a seeded
  equal-count shuffle so every class appears the same number of times at
  varied positions with no periodic artifacts.
- Fully deterministic from (generator_version, seed): same inputs →
  byte-identical HTML and ground truth.
- Multiple blocks at different page positions so locator + registration
  see the geometry in more than one context.

Usage:
  python scripts/gen_calibration_sheet.py --seed 20260817 \
      --out reader/calibration/sheets
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

GENERATOR_VERSION = "calsheet-v1"
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"  # index order is canonical
CHARS_PER_LINE = 48          # production footer wraps token at 48 chars
LINES_PER_BLOCK = 12
BLOCKS = 4                   # 4*12*48 = 2304 glyphs = 72 per class

CSS = """\
  @page { size: A4; margin: 16mm; }
  html, body { margin: 0; padding: 0; background: #fff; color: #000; }
  body { font-family: Georgia, 'Times New Roman', serif; font-size: 10.5pt; line-height: 1.3; }
  /* Product footer typography (src/pages/create.tsx footer block +
     --app-font-mono in src/index.css). Do not restyle. */
  .token-lines {
    font-family: Menlo, monospace;   /* --app-font-mono */
    font-size: 10px;                 /* text-[10px] */
    color: #6b7280;                  /* text-gray-500 */
    word-break: break-all;           /* break-all */
  }
  .block { margin-bottom: 22mm; }
  .block:last-child { margin-bottom: 0; }
  .block-label { font-family: Menlo, monospace; font-size: 9pt; font-weight: bold;
                 color: #000; margin-bottom: 1mm; }
  .filler { margin: 0 0 6mm 0; }
  .scale-wrap { margin: 0 0 10mm 0; }
  .scale-bar { position: relative; width: 50mm; height: 4mm;
               border: 0.4mm solid #000; box-sizing: border-box; }
  .scale-bar .tick { position: absolute; top: 0; width: 0.3mm; height: 2mm; background: #000; }
  .scale-label { font-size: 8pt; margin-top: 1mm; font-family: Menlo, monospace; }
  .sheet-header { font-size: 12pt; font-weight: bold; margin: 0 0 2mm 0; }
  .sheet-sub { font-size: 9pt; color: #333; margin: 0 0 8mm 0; }
  .screen-note { border: 2px dashed #b45309; background: #fffbeb; color: #78350f;
                 font-family: Inter, sans-serif; font-size: 13px; line-height: 1.5;
                 padding: 14px 16px; margin: 0 0 24px 0; }
  @media print { .screen-note { display: none !important; } }
  @media screen { body { padding: 24px; max-width: 210mm; margin: 0 auto; } }
"""

# Deterministic serif filler between blocks so blocks sit at different
# page depths with body-text context above them (mimics production pages).
FILLER = (
    "Set the oven to a moderate heat and let it settle while the butter "
    "softens on the counter. Sift the dry ingredients twice, folding them "
    "together gently so the mixture stays light. When the batter just "
    "comes together, stop; overworking it makes the crumb dense."
)


def build_lines(seed: int) -> list[str]:
    total = BLOCKS * LINES_PER_BLOCK * CHARS_PER_LINE
    per_class = total // len(BECH32_CHARSET)
    assert per_class * len(BECH32_CHARSET) == total
    pool = list(BECH32_CHARSET) * per_class
    rng = random.Random(f"{GENERATOR_VERSION}:{seed}")
    rng.shuffle(pool)
    text = "".join(pool)
    return [text[i : i + CHARS_PER_LINE] for i in range(0, total, CHARS_PER_LINE)]


def render_html(sheet_id: str, seed: int, lines: list[str]) -> str:
    blocks_html = []
    for b in range(BLOCKS):
        blk = lines[b * LINES_PER_BLOCK : (b + 1) * LINES_PER_BLOCK]
        rows = "\n".join(f"<div>{ln}</div>" for ln in blk)
        blocks_html.append(
            f'<div class="block">\n'
            f'<div class="block-label">CAL {sheet_id} BLOCK {b + 1} OF {BLOCKS}</div>\n'
            f'<div class="token-lines">\n{rows}\n</div>\n</div>\n'
            f'<p class="filler">{FILLER}</p>'
        )
    ticks = "".join(
        f'<span class="tick" style="left:{i * 10}mm"></span>' for i in range(1, 5)
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>QuietKey reader calibration sheet {sheet_id}</title>
<style>
{CSS}</style>
</head>
<body>
<div class="screen-note">
Print at <strong>100% scale</strong> (no "fit to page"). Verify the printed
scale bar is exactly 50&nbsp;mm with a ruler before capturing; if it is not,
reprint. Follow reader/calibration/CALIBRATION-CAPTURE-PROTOCOL.md.
</div>
<p class="sheet-header">Reader calibration sheet {sheet_id}</p>
<p class="sheet-sub">generator {GENERATOR_VERSION} · seed {seed} ·
{BLOCKS} blocks × {LINES_PER_BLOCK} lines × {CHARS_PER_LINE} chars ·
DEVELOPMENT CALIBRATION MATERIAL — carries no secret</p>
<div class="scale-wrap">
  <div class="scale-bar">{ticks}</div>
  <div class="scale-label">scale bar: exactly 50 mm when printed correctly</div>
</div>
{chr(10).join(blocks_html)}
</body>
</html>
"""


def generate(seed: int, out_dir: Path) -> dict:
    sheet_id = f"{GENERATOR_VERSION}-s{seed}"
    lines = build_lines(seed)
    html = render_html(sheet_id, seed, lines)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"calibration-sheet-{sheet_id}.html"
    html_path.write_text(html)
    counts = {c: sum(ln.count(c) for ln in lines) for c in BECH32_CHARSET}
    gt = {
        "sheet_id": sheet_id,
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "charset": BECH32_CHARSET,
        "blocks": BLOCKS,
        "lines_per_block": LINES_PER_BLOCK,
        "chars_per_line": CHARS_PER_LINE,
        "per_class_count": counts,
        "lines": lines,
        "typography": {
            "source": "production footer (src/pages/create.tsx + src/index.css)",
            "font_family": "Menlo, monospace",
            "font_size_px": 10,
            "color": "#6b7280",
            "note": "NOT a frozen artifact; matches product print path at v0.2.1",
        },
        "html_sha256": hashlib.sha256(html_path.read_bytes()).hexdigest(),
        "status": "DEVELOPMENT CALIBRATION MATERIAL / NOT GATE-A1 EVIDENCE",
    }
    gt_path = out_dir / f"calibration-sheet-{sheet_id}.groundtruth.json"
    gt_path.write_text(json.dumps(gt, indent=2, sort_keys=True) + "\n")
    return {"sheet_id": sheet_id, "html": str(html_path), "groundtruth": str(gt_path),
            "html_sha256": gt["html_sha256"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--out", type=Path, default=Path("reader/calibration/sheets"))
    args = ap.parse_args()
    print(json.dumps(generate(args.seed, args.out), indent=2))


if __name__ == "__main__":
    main()
