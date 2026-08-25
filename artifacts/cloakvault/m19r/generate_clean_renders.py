#!/usr/bin/env python3
"""Generate deterministic M19-R clean full-page renders without decoding."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FROZEN = REPO / "artifacts" / "cloakvault" / "m19" / "phase1"
RENDERER = FROZEN / "inputs" / "renderer" / "qk_m19_pdfgen_v1.py"
FONTS = FROZEN / "inputs" / "fonts"
BODIES = FROZEN / "inputs" / "bodies"
PHASE1_MASTERS = FROZEN / "masters"
PAYLOADS = HERE / "inputs" / "PAYLOADS.tsv"
OUTPUT = HERE / "generated" / "clean"
MANIFEST = HERE / "generated" / "CLEAN-RENDERS.json"

FROZEN_INPUT_COMMIT = "74c60d41c983dcee6fdc22fd910ec2048628413c"
PAYLOAD_SOURCE_COMMIT = "8d321f318ff9b6cdc1065407b26ada447e219215"
PAYLOAD_SOURCE_REPOSITORY = "https://github.com/jeroenvandevoorde-cmd/QuietKey"
PAYLOAD_SOURCE_PATH = "host/qk-a1-codec/tests/fixtures/spike_reencode.txt"
PAYLOAD_SOURCE_BLOB = "10734221f2020c21b4f716f14bb1af53d5f0a29d"
PAYLOAD_SOURCE_SHA256 = "839cd6fc016bcbc47eb02b4e99f4837ee52c3cfeea4df44a9b1e68fa2adac970"
RENDERER_SHA256 = "8272fd78438bb7b7e9932f007805ffa6336cb8aeb7293129ca9a16f4cfd24a99"
SERIF_SHA256 = "058ea80864aef09a23f45cbec2bb5400bc3dfbdea01c3f10538a21fcb497fb74"
MONO_SHA256 = "f2b83c763e8afd21709333370bed4774337fae82267937e2b5aea7e2fbd922c1"
RECIPE_SHA256 = "ec51fb35a729d2c29bcae039209994bdf5fcd20fb92eb886155a8b4cfde929b9"
TRAVEL_SHA256 = "69745a655c87647f32b86c832ad40a3f1903e4510125ad1a272651cb37050230"
ALPHABET = frozenset("23456789abcdefghijkmnpqrstuvwxyz")
PROFILES = {"Rs72_60": 116, "Rs76_60": 122, "Rs80_60": 128}


@dataclass(frozen=True)
class Payload:
    q: int
    payload_id: str
    lineage: str
    profile: str
    token_length: int
    token_sha256: str
    token_ascii: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relative(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def require_file(path: Path, digest: str) -> bytes:
    data = path.read_bytes()
    if sha256_bytes(data) != digest:
        raise RuntimeError("frozen input digest mismatch: {}".format(relative(path)))
    return data


def load_payloads() -> List[Payload]:
    with PAYLOADS.open("r", encoding="ascii", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(rows) != 18:
        raise RuntimeError("expected 18 payload rows, got {}".format(len(rows)))
    payloads = []
    for expected_q, row in enumerate(rows):
        payload = Payload(
            q=int(row["q"]),
            payload_id=row["payload_id"],
            lineage=row["lineage"],
            profile=row["profile"],
            token_length=int(row["token_length"]),
            token_sha256=row["token_sha256"],
            token_ascii=row["token_ascii"],
        )
        if payload.q != expected_q:
            raise RuntimeError("payload q sequence is not 00..17")
        if payload.profile not in PROFILES or PROFILES[payload.profile] != payload.token_length:
            raise RuntimeError("profile/length mismatch at q{:02d}".format(payload.q))
        if payload.payload_id != "{}-{}".format(payload.lineage, payload.profile):
            raise RuntimeError("payload id mismatch at q{:02d}".format(payload.q))
        if sha256_bytes(payload.token_ascii.encode("ascii")) != payload.token_sha256:
            raise RuntimeError("token digest mismatch at q{:02d}".format(payload.q))
        if len(payload.token_ascii) != payload.token_length:
            raise RuntimeError("token length mismatch at q{:02d}".format(payload.q))
        if not set(payload.token_ascii) <= ALPHABET:
            raise RuntimeError("non-alphabet symbol at q{:02d}".format(payload.q))
        payloads.append(payload)
    if {p.lineage for p in payloads} != {"T0", "T1", "T2", "T3", "T4", "T5"}:
        raise RuntimeError("lineage set mismatch")
    for lineage in {p.lineage for p in payloads}:
        if {p.profile for p in payloads if p.lineage == lineage} != set(PROFILES):
            raise RuntimeError("profile set mismatch for {}".format(lineage))
    return payloads


def load_frozen_renderer() -> Any:
    require_file(RENDERER, RENDERER_SHA256)
    spec = importlib.util.spec_from_file_location("qk_m19_pdfgen_v1_frozen", RENDERER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen renderer")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def poppler_version() -> str:
    result = subprocess.run(
        ["pdftoppm", "-v"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    first = (result.stdout + result.stderr).decode("utf-8", "replace").splitlines()[0]
    if not re.fullmatch(r"pdftoppm version [0-9]+(?:\.[0-9]+)+", first):
        raise RuntimeError("unexpected pdftoppm version output")
    return first


def render_png(pdf: bytes, temp: Path, stem: str) -> bytes:
    pdf_path = temp / (stem + ".pdf")
    prefix_a = temp / (stem + "-a")
    prefix_b = temp / (stem + "-b")
    pdf_path.write_bytes(pdf)
    command = ["pdftoppm", "-r", "150", "-png", "-singlefile", str(pdf_path)]
    subprocess.run(command + [str(prefix_a)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    subprocess.run(command + [str(prefix_b)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    png_a = prefix_a.with_suffix(".png").read_bytes()
    png_b = prefix_b.with_suffix(".png").read_bytes()
    if png_a != png_b:
        raise RuntimeError("repeated rasterization differs for {}".format(stem))
    if png_a[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError("rasterizer did not emit PNG")
    width = int.from_bytes(png_a[16:20], "big")
    height = int.from_bytes(png_a[20:24], "big")
    if (width, height) != (1241, 1754):
        raise RuntimeError("unexpected raster dimensions: {}x{}".format(width, height))
    return png_a


def generate() -> dict:
    payloads = load_payloads()
    module = load_frozen_renderer()
    serif_data = require_file(FONTS / "LiberationSerif-Regular.ttf", SERIF_SHA256)
    mono_data = require_file(FONTS / "LiberationMono-Regular.ttf", MONO_SHA256)
    bodies = {
        "recipe": require_file(BODIES / "recipe-body.txt", RECIPE_SHA256).decode("ascii"),
        "travel": require_file(BODIES / "travel-body.txt", TRAVEL_SHA256).decode("ascii"),
    }
    serif = module.TrueTypeMetrics(serif_data, "LiberationSerif", False)
    mono = module.TrueTypeMetrics(mono_data, "LiberationMono", True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    records = []
    with tempfile.TemporaryDirectory(prefix="qk-m19r-clean-") as temp_name:
        temp = Path(temp_name)
        for payload in payloads:
            for template in ("recipe", "travel"):
                pdf_a, layout_a = module.build_pdf(
                    bodies[template], payload.token_ascii, serif, mono
                )
                pdf_b, layout_b = module.build_pdf(
                    bodies[template], payload.token_ascii, serif, mono
                )
                if pdf_a != pdf_b or layout_a != layout_b:
                    raise RuntimeError("frozen renderer is not repeatable")
                stem = "q{:02d}-{}-{}".format(payload.q, payload.payload_id, template)
                frozen_master = PHASE1_MASTERS / (stem + ".pdf")
                master_equivalence = None
                if frozen_master.exists():
                    master_equivalence = pdf_a == frozen_master.read_bytes()
                    if not master_equivalence:
                        raise RuntimeError("clean PDF differs from frozen master: {}".format(stem))
                png = render_png(pdf_a, temp, stem)
                out = OUTPUT / (stem + ".png")
                if out.exists() and out.read_bytes() != png:
                    raise RuntimeError("existing clean render differs: {}".format(relative(out)))
                out.write_bytes(png)
                records.append(
                    {
                        "bytes": len(png),
                        "clean_pdf_bytes": len(pdf_a),
                        "clean_pdf_sha256": sha256_bytes(pdf_a),
                        "frozen_phase1_master_equal": master_equivalence,
                        "lineage": payload.lineage,
                        "path": relative(out),
                        "payload_id": payload.payload_id,
                        "profile": payload.profile,
                        "q": payload.q,
                        "sha256": sha256_bytes(png),
                        "template": template,
                        "token_length": payload.token_length,
                        "token_sha256": payload.token_sha256,
                    }
                )
    expected_names = {Path(record["path"]).name for record in records}
    extra = {path.name for path in OUTPUT.glob("*.png")} - expected_names
    if extra:
        raise RuntimeError("unexpected clean renders: {}".format(sorted(extra)))
    manifest = {
        "authority": "QK-DEC-103",
        "clean_render_count": len(records),
        "clean_render_purpose": "frozen-clean-render-input-only",
        "comparison_generation": "DISABLED",
        "decode_operations": 0,
        "frozen_input_commit": FROZEN_INPUT_COMMIT,
        "format_version": 1,
        "fresh_anchor_inputs": 0,
        "geometry": {
            "dpi": 150,
            "height_pixels": 1754,
            "page": "A4-portrait",
            "width_pixels": 1241,
        },
        "payload_registry": {
            "count": len(payloads),
            "path": relative(PAYLOADS),
            "sha256": sha256_file(PAYLOADS),
            "source_blob": PAYLOAD_SOURCE_BLOB,
            "source_commit": PAYLOAD_SOURCE_COMMIT,
            "source_path": PAYLOAD_SOURCE_PATH,
            "source_repository": PAYLOAD_SOURCE_REPOSITORY,
            "source_sha256": PAYLOAD_SOURCE_SHA256,
        },
        "poppler": poppler_version(),
        "records": records,
        "renderer": {"path": relative(RENDERER), "sha256": RENDERER_SHA256},
        "scoring_operations": 0,
        "status": "GENERATED_CLEAN_INPUTS_ONLY",
        "templates": ["recipe", "travel"],
    }
    if len(records) != 36:
        raise RuntimeError("expected 36 clean renders")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("ascii")
    if MANIFEST.exists() and MANIFEST.read_bytes() != encoded:
        # A tool-version change is material and must not silently replace the record.
        raise RuntimeError("existing clean-render manifest differs")
    MANIFEST.write_bytes(encoded)
    return manifest


def verify_existing() -> dict:
    manifest = json.loads(MANIFEST.read_text("ascii"))
    if manifest["clean_render_count"] != 36 or len(manifest["records"]) != 36:
        raise RuntimeError("clean-render manifest count mismatch")
    for record in manifest["records"]:
        path = REPO / record["path"]
        data = path.read_bytes()
        if len(data) != record["bytes"] or sha256_bytes(data) != record["sha256"]:
            raise RuntimeError("clean-render byte mismatch: {}".format(record["path"]))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    manifest = verify_existing() if args.verify_existing else generate()
    print("clean_renders={}".format(manifest["clean_render_count"]))
    print("manifest_sha256={}".format(sha256_file(MANIFEST)))
    print("comparison_generation={}".format(manifest["comparison_generation"]))


if __name__ == "__main__":
    main()
