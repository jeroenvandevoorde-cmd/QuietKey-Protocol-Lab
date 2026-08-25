#!/usr/bin/env python3
"""Programmatic and raster preflight for QK-DEC-094 Phase 1 masters."""

from __future__ import annotations

import hashlib
import re
import struct
import subprocess
import sys
from pathlib import Path


ROOT = Path("artifacts/cloakvault/m19/phase1")
MASTERS = ROOT / "masters"
PAYLOADS = ROOT / "inputs" / "payloads"
BODIES = ROOT / "inputs" / "bodies"
RENDERER = ROOT / "inputs" / "renderer" / "qk_m19_pdfgen_v1.py"
PREFLIGHT = ROOT / "preflight"
RENDERS = PREFLIGHT / "renders"
REPORT = ROOT / "manifests" / "M19-A1-PHASE1-DIGITAL-PREFLIGHT.txt"


def run(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def version(command: str) -> str:
    result = run(command, "-v")
    text = (result.stdout + result.stderr).decode("utf-8", "replace")
    return text.splitlines()[0].strip()


def norm_visible(text: str) -> str:
    return " ".join(text.replace("\f", " ").split())


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    return struct.unpack(">II", data[16:24])


def main() -> None:
    RENDERS.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(MASTERS.glob("*.pdf"))
    assert len(pdfs) == 12
    body = {
        "recipe": (BODIES / "recipe-body.txt").read_text("ascii"),
        "travel": (BODIES / "travel-body.txt").read_text("ascii"),
    }
    payload_files = {path.name.split("-", 1)[0]: path for path in PAYLOADS.glob("q*.txt")}
    assert set(payload_files) == {"q00", "q01", "q02", "q09", "q10", "q11"}
    records: list[str] = []
    for pdf in pdfs:
        match = re.fullmatch(r"(q(?:00|01|02|09|10|11))-(.+)-(recipe|travel)\.pdf", pdf.name)
        assert match, pdf.name
        q, _, template = match.groups()
        token = payload_files[q].read_text("ascii")
        info = run("pdfinfo", str(pdf)).stdout.decode("utf-8")
        assert re.search(r"^Pages:\s+1$", info, re.MULTILINE)
        assert re.search(r"^Page size:\s+595\.276 x 841\.89 pts \(A4\)$", info, re.MULTILINE)
        assert re.search(r"^Page rot:\s+0$", info, re.MULTILINE)
        assert re.search(r"^Encrypted:\s+no$", info, re.MULTILINE)
        assert re.search(r"^JavaScript:\s+no$", info, re.MULTILINE)
        fonts_text = run("pdffonts", str(pdf)).stdout.decode("utf-8")
        font_rows = [line.split() for line in fonts_text.splitlines()[2:] if line.strip()]
        assert len(font_rows) == 2
        assert {row[0] for row in font_rows} == {"LiberationSerif", "LiberationMono"}
        assert all(row[1:6] == ["TrueType", "WinAnsi", "yes", "no", "yes"] for row in font_rows)
        extracted = run("pdftotext", "-layout", str(pdf), "-").stdout.decode("utf-8")
        expected_visible = norm_visible(body[template] + token[:64] + " " + token[64:])
        assert norm_visible(extracted) == expected_visible, pdf.name
        prefix = RENDERS / pdf.stem
        run("pdftoppm", "-r", "150", "-png", "-singlefile", str(pdf), str(prefix))
        png = prefix.with_suffix(".png")
        width, height = png_size(png)
        assert (width, height) == (1241, 1754)
        records.append(
            "master="
            + ";".join(
                (
                    f"pdf={pdf.as_posix()}",
                    f"pdf_bytes={pdf.stat().st_size}",
                    f"pdf_sha256={sha(pdf)}",
                    "pages=1",
                    "page_size=A4-595.276x841.89pt",
                    "rotation=0",
                    "encrypted=no",
                    "javascript=no",
                    "fonts=LiberationSerif,LiberationMono",
                    "fonts_embedded=yes",
                    "fonts_subset=no",
                    "unicode_maps=yes",
                    "visible_text_match=true",
                    f"png={png.as_posix()}",
                    f"png_bytes={png.stat().st_size}",
                    f"png_sha256={sha(png)}",
                    f"png_pixels={width}x{height}",
                )
            )
        )
    lines = [
        "# QUIETKEY_M19_A1_PHASE1_DIGITAL_PREFLIGHT_V1",
        "# EXPERIMENTAL - NO REAL FUNDS - NOT A WALLET",
        "programmatic_status=PASS",
        "visual_inspection_status=PENDING",
        "physical_printing_status=NOT_STARTED",
        "capture_status=NOT_STARTED",
        "decode_outcomes=0",
        "decoder_execution=0",
        f"verifier_python={sys.version.split()[0]}",
        f"verifier_path={Path(__file__).as_posix()}",
        f"verifier_sha256={sha(Path(__file__))}",
        f"renderer_sha256={sha(RENDERER)}",
        f"pdfinfo_version={version('pdfinfo')}",
        f"pdffonts_version={version('pdffonts')}",
        f"pdftotext_version={version('pdftotext')}",
        f"pdftoppm_version={version('pdftoppm')}",
        "expected_masters=12",
        "checked_masters=12",
        "raster_dpi=150",
        "BEGIN_MASTER_CHECKS",
        *records,
        "END_MASTER_CHECKS",
    ]
    REPORT.write_bytes(("\n".join(lines) + "\n").encode("ascii"))
    print("programmatic_status=PASS")
    print("checked_masters=12")
    print(f"report_sha256={sha(REPORT)}")


if __name__ == "__main__":
    main()
