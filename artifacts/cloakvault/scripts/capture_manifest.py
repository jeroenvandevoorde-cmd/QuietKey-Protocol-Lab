#!/usr/bin/env python3
"""Capture-manifest tool (Reader v0.2.1, Task 7).

Builds a deterministic JSON manifest (hashes + metadata, no image data)
for a directory of raw capture JPEGs. The raw images stay gitignored;
only the manifest is committed.

Filename convention parsed automatically (calibration campaigns):
  cal-<sheetid>-<copy>-<condition>-<n>.jpeg
Anything unparseable gets nulls the owner fills in by hand.

Deterministic: same directory content → byte-identical manifest (files
sorted by name, keys sorted, no timestamps).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

try:  # EXIF orientation is geometry-relevant; PII EXIF is NOT copied
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

CAL_RE = re.compile(r"^cal-(?P<sheet>.+)-(?P<copy>copy\d+)-(?P<cond>[a-z0-9]+)-(?P<n>\d+)\.(jpe?g|png)$", re.I)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def image_entry(path: Path) -> dict:
    entry: dict = {
        "filename": path.name,
        "sha256": sha256_file(path),
        "size_bytes": path.stat().st_size,
        "width": None,
        "height": None,
        "exif_orientation": None,
        "sheet_id": None,
        "copy": None,
        "condition": None,
        "printer_id": None,
        "paper_id": None,
        "camera_id": None,
        "notes": None,
    }
    if Image is not None:
        with Image.open(path) as im:
            entry["width"], entry["height"] = im.size
            exif = im.getexif()
            entry["exif_orientation"] = int(exif.get(274)) if exif.get(274) else None
    m = CAL_RE.match(path.name)
    if m:
        entry["sheet_id"] = m.group("sheet")
        entry["copy"] = m.group("copy")
        entry["condition"] = m.group("cond")
    return entry


def build_manifest(directory: Path, campaign_id: str, corpus_id: str) -> dict:
    files = sorted(
        p for p in directory.iterdir()
        if p.suffix.lower() in (".jpg", ".jpeg", ".png") and p.is_file()
    )
    images = [image_entry(p) for p in files]
    return {
        "manifest_format_version": 1,
        "campaign_id": campaign_id,
        "corpus_id": corpus_id,
        "image_count": len(images),
        "images": images,
        "status": "DEVELOPMENT CALIBRATION MATERIAL / NOT GATE-A1 EVIDENCE",
        "note": "raw images are gitignored (EXIF/GPS); manifest carries hashes only",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True)
    ap.add_argument("--campaign-id", required=True)
    ap.add_argument("--corpus-id", required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    manifest = build_manifest(args.dir, args.campaign_id, args.corpus_id)
    args.out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.out}: {manifest['image_count']} images")


if __name__ == "__main__":
    main()
