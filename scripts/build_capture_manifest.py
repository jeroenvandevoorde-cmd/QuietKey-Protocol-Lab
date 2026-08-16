#!/usr/bin/env python3
"""Deterministic raw-capture manifest builder (Gate A provenance tooling).

Usage:
    python3 scripts/build_capture_manifest.py <image_dir> [--out manifest.json]
        [--corpus-id ID] [--campaign-id ID] [--meta sidecar.json]

For every image file (jpg/jpeg/png/npy) records: filename, SHA-256, file
size, pixel dimensions and EXIF orientation where they can be read
deterministically from the file itself, plus any per-file metadata found
in an optional user-supplied sidecar JSON ({"<filename>": {...}}).

Unknown information stays null. NOTHING is ever invented: no fabricated
hashes, capture IDs, printers, cameras, or lighting categories.

Status note: no raw spike or Bridge Run 01 captures are present in this
repository, so no historical manifests could be generated locally; this
limitation is reported in the Reader v0.2 milestone report. The tool is
committed so that Bridge Run 02 / Gate A1 provenance can be produced from
photograph to result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

EXTS = {".jpg", ".jpeg", ".png", ".npy"}

META_FIELDS = [
    "capture_id", "campaign_id", "condition_family", "severity",
    "printer_id", "paper_id", "camera_id", "lighting", "notes",
]


def _png_dims(data: bytes):
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 24:
        return None
    w, h = struct.unpack(">II", data[16:24])
    return w, h


def _jpeg_dims_orientation(data: bytes):
    """Minimal deterministic JPEG SOF dimensions + EXIF orientation."""
    dims, orientation = None, None
    i = 2
    n = len(data)
    while i + 4 <= n and data[i] == 0xFF:
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seglen = struct.unpack(">H", data[i + 2 : i + 4])[0]
        seg = data[i + 4 : i + 2 + seglen]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", seg[1:5])
            dims = (w, h)
        elif marker == 0xE1 and seg[:6] == b"Exif\x00\x00":
            tiff = seg[6:]
            if len(tiff) >= 8:
                endian = "<" if tiff[:2] == b"II" else ">"
                (ifd_off,) = struct.unpack(endian + "I", tiff[4:8])
                if ifd_off + 2 <= len(tiff):
                    (count,) = struct.unpack(endian + "H", tiff[ifd_off : ifd_off + 2])
                    for e in range(count):
                        o = ifd_off + 2 + e * 12
                        if o + 12 > len(tiff):
                            break
                        tag, typ, cnt = struct.unpack(endian + "HHI", tiff[o : o + 8])
                        if tag == 0x0112:
                            (orientation,) = struct.unpack(endian + "H", tiff[o + 8 : o + 10])
        if marker == 0xDA:
            break
        i += 2 + seglen
    return dims, orientation


def _npy_dims(data: bytes):
    if data[:6] != b"\x93NUMPY":
        return None
    try:
        hlen = struct.unpack("<H", data[8:10])[0]
        header = data[10 : 10 + hlen].decode("latin1")
        shape = header.split("'shape':")[1].split("(")[1].split(")")[0]
        parts = [int(p) for p in shape.replace(",", " ").split()]
        if len(parts) >= 2:
            return parts[1], parts[0]  # (w, h)
    except Exception:
        return None
    return None


def build_manifest(image_dir: Path, corpus_id, campaign_id, sidecar: dict) -> dict:
    entries = []
    for p in sorted(image_dir.iterdir()):
        if p.suffix.lower() not in EXTS or not p.is_file():
            continue
        data = p.read_bytes()
        dims, orientation = None, None
        if p.suffix.lower() == ".png":
            dims = _png_dims(data)
        elif p.suffix.lower() in (".jpg", ".jpeg"):
            dims, orientation = _jpeg_dims_orientation(data)
        elif p.suffix.lower() == ".npy":
            dims = _npy_dims(data)
        meta = sidecar.get(p.name, {})
        entry = {
            "filename": p.name,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
            "width": dims[0] if dims else None,
            "height": dims[1] if dims else None,
            "exif_orientation": orientation,
        }
        for f in META_FIELDS:
            entry[f] = meta.get(f)  # null unless explicitly supplied
        entries.append(entry)
    return {
        "manifest_format_version": 1,
        "corpus_id": corpus_id,
        "campaign_id": campaign_id,
        "image_count": len(entries),
        "images": entries,
        "note": "Unknown fields are null; metadata is never invented.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("image_dir", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--corpus-id", default=None)
    ap.add_argument("--campaign-id", default=None)
    ap.add_argument("--meta", type=Path, help="optional sidecar JSON of per-file metadata")
    a = ap.parse_args()
    if not a.image_dir.is_dir():
        sys.exit(f"not a directory: {a.image_dir}")
    sidecar = json.loads(a.meta.read_text()) if a.meta else {}
    manifest = build_manifest(a.image_dir, a.corpus_id, a.campaign_id, sidecar)
    text = json.dumps(manifest, indent=2, sort_keys=True)
    if a.out:
        a.out.write_text(text + "\n")
        print(f"wrote {a.out} ({manifest['image_count']} images)")
    else:
        print(text)


if __name__ == "__main__":
    main()
