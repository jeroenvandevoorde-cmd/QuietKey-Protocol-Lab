#!/usr/bin/env python3
"""QuietKey M19 Phase 1 deterministic, outcome-blind print-master generator.

Bench-only corpus tooling. It performs no OCR, Reed-Solomon operation, capsule
authentication, or decoding. Inputs are the literal public tokens frozen at the
product source commit recorded below.
"""

from __future__ import annotations

import hashlib
import struct
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


GENERATOR_ID = "QuietKey M19 deterministic PDF renderer v1"
PAYLOAD_SOURCE_COMMIT = "8d321f318ff9b6cdc1065407b26ada447e219215"
PROTOCOL_COMMIT = "48cc239cb77116aa4f945a627c9a280ccde082fd"
FONT_SOURCE_COMMIT = "3f3e95b63aec51670841a39594d88786c50768f5"
PRODUCT_HEAD_AT_RENDER = "fc7ecec3a5bd1344490a1c4e65147c92670474e6"

ROOT = Path("artifacts/cloakvault/m19/phase1")
FONTS = ROOT / "inputs" / "fonts"
BODIES = ROOT / "inputs" / "bodies"
PAYLOADS = ROOT / "inputs" / "payloads"
RENDERER = ROOT / "inputs" / "renderer"
MASTERS = ROOT / "masters"
MANIFESTS = ROOT / "manifests"

ARCHIVE = FONTS / "liberation-fonts-ttf-2.1.5.tar.gz"
SERIF = FONTS / "LiberationSerif-Regular.ttf"
MONO = FONTS / "LiberationMono-Regular.ttf"
LICENSE = FONTS / "LICENSE"

EXPECTED_FILES = {
    ARCHIVE: (2_385_008, "7191c669bf38899f73a2094ed00f7b800553364f90e2637010a69c0e268f25d0"),
    SERIF: (393_576, "058ea80864aef09a23f45cbec2bb5400bc3dfbdea01c3f10538a21fcb497fb74"),
    MONO: (319_508, "f2b83c763e8afd21709333370bed4774337fae82267937e2b5aea7e2fbd922c1"),
    LICENSE: (4_414, "93fed46019c38bbe566b479d22148e2e8a1e85ada614accb0211c37b2c61c19b"),
}

RECIPE_BODY = (
    "ROASTED TOMATO AND WHITE BEAN STEW\n"
    "A simple supper for four\n"
    "\n"
    "INGREDIENTS\n"
    "2 tablespoons olive oil\n"
    "1 medium yellow onion, finely chopped\n"
    "2 garlic cloves, minced\n"
    "1 teaspoon smoked paprika\n"
    "1/2 teaspoon dried thyme\n"
    "2 cans (400 g each) white beans, drained and rinsed\n"
    "1 can (400 g) chopped tomatoes\n"
    "250 ml vegetable stock\n"
    "1 tablespoon tomato paste\n"
    "1 teaspoon red wine vinegar\n"
    "Salt and black pepper\n"
    "A small handful of flat-leaf parsley\n"
    "\n"
    "METHOD\n"
    "1. Warm the olive oil in a wide saucepan over medium heat.\n"
    "2. Add the onion and a small pinch of salt. Cook for 8 minutes, stirring occasionally, until soft.\n"
    "3. Add the garlic, paprika, and thyme. Stir for 30 seconds.\n"
    "4. Add the beans, tomatoes, stock, and tomato paste. Bring to a gentle simmer.\n"
    "5. Cook uncovered for 20 minutes, stirring twice, until the sauce is thick but still spoonable.\n"
    "6. Stir in the vinegar. Season with salt and black pepper.\n"
    "7. Divide among four warm bowls and finish with parsley.\n"
    "\n"
    "SERVING NOTE\n"
    "Serve with toasted bread or boiled potatoes. Cool leftovers promptly, cover, and refrigerate for up to two days. Reheat once until steaming throughout.\n"
)

TRAVEL_BODY = (
    "A QUIET DAY BY TRAIN\n"
    "Practical notes for an unhurried city visit\n"
    "\n"
    "BEFORE LEAVING\n"
    "Check the outbound and return times the evening before. Save the timetable offline and write the final return time on paper. Pack a refillable bottle, a light layer, a small umbrella, and one simple snack. Wear shoes that remain comfortable on stone streets.\n"
    "\n"
    "ON ARRIVAL\n"
    "Leave the station by the main exit and pause before choosing a direction. Note the station name and the street used for the return. Walk the first ten minutes without a fixed list; this makes the scale of the centre easier to understand.\n"
    "\n"
    "MORNING\n"
    "Choose one museum, market, or historic building and give it a full hour. Arrive near opening time. Keep the rest of the morning flexible, and stop for coffee somewhere with visible prices and room to sit.\n"
    "\n"
    "MIDDAY\n"
    "Eat before the busiest lunch period if possible. A bakery, soup counter, or small cafe is usually faster than a formal meal. Refill the water bottle and check the return platform only after lunch.\n"
    "\n"
    "AFTERNOON\n"
    "Take one longer walk along a river, park, or residential street. Turn back while there is still generous time. Aim to reach the station twenty minutes before departure.\n"
    "\n"
    "USEFUL HABITS\n"
    "Keep tickets and identification in the same secure pocket. Photograph no private documents. Carry out litter, respect quiet areas, and leave gates exactly as found. If plans change, choose the simpler route home.\n"
)


@dataclass(frozen=True)
class Payload:
    q: int
    payload_id: str
    lineage: str
    profile: str
    token: str
    token_sha256: str


PAYLOAD_DATA = (
    Payload(0, "T0-Rs72_60", "T0", "RS(72,60)", "222i62s62n52g42b3a7t3h953my2b6mwy7t7yq3n2xjxvfge6fwwymixi4a9aimkg8usknu6mjxg7ex3d7g72397y9mquemmmycwew3eyedrrr722452", "e6ba56bfa0292affe5f0747495e0a2aa67f39eeb98b76484f005597226a6da99"),
    Payload(1, "T0-Rs76_60", "T0", "RS(76,60)", "222i62s62n52g42b3a7t3h953my2b6mwy7t7yq3n2xjxvfge6fwwymixi4a9aimkg8usknu6mjxg7ex3d7g72397y9mquemmf74h57h8vaexqz6c7bieuuvu6a", "38d85f4aa94aff7d653f211244a6a32d410716414eabedc4b1e05c8ebb9c015b"),
    Payload(2, "T0-Rs80_60", "T0", "RS(80,60)", "222i62s62n52g42b3a7t3h953my2b6mwy7t7yq3n2xjxvfge6fwwymixi4a9aimkg8usknu6mjxg7ex3d7g72397y9mquemmdrgp5t4axuxsaxs2b9y7p49hc9bi8vkb", "ae87f22fddbf5e364552963f7d4073a7882c8abb1e68a2fd4952a17a4c3f43a5"),
    Payload(9, "T3-Rs72_60", "T3", "RS(72,60)", "82sm6etn8nv5gg3t9axt8h3r7vbem4pumfczftvtimj4dvcvv5yp8crk2inng5dpi6qxwtt23afe25scdr6jznrty946y2s8rty789c5qa3rpn3d3gwi", "604fc27a4cb7714370b57811c148e921ca0908e752f216715aa00d0b9b35d818"),
    Payload(10, "T3-Rs76_60", "T3", "RS(76,60)", "82sm6etn8nv5gg3t9axt8h3r7vbem4pumfczftvtimj4dvcvv5yp8crk2inng5dpi6qxwtt23afe25scdr6jznrty946y2s8bj3z2fnvfzcqx6vi5cdg38nsas", "7354178679d626d75781441aaeda00726d66b554418a10f3306243b9cecbe10f"),
    Payload(11, "T3-Rs80_60", "T3", "RS(80,60)", "82sm6etn8nv5gg3t9axt8h3r7vbem4pumfczftvtimj4dvcvv5yp8crk2inng5dpi6qxwtt23afe25scdr6jznrty946y2s838i7i2qytggq9pafwvqh8eavqenih5ue", "9e59903c25aa5f3d40cb8b1cdb084ba41df9fd39ea39f09d26e2c0e17b211441"),
)


@dataclass(frozen=True)
class Cell:
    c: int
    identity: str
    damage_class: str
    level: int
    lighting: str
    sequence: str


CELLS = (
    Cell(0, "baseline-0-dim-S01", "baseline", 0, "dim", "S01"),
    Cell(1, "baseline-0-glare-S02", "baseline", 0, "glare", "S02"),
    Cell(2, "baseline-0-std-S01", "baseline", 0, "std", "S01"),
    Cell(3, "baseline-0-std-S02", "baseline", 0, "std", "S02"),
    Cell(4, "coffee-1-S03", "coffee", 1, "std", "S03"),
    Cell(5, "coffee-2-S04", "coffee", 2, "std", "S04"),
    Cell(6, "coffee-3-S05", "coffee", 3, "std", "S05"),
    Cell(7, "crumple-1-S21", "crumple", 1, "std", "S21"),
    Cell(8, "crumple-2-S22", "crumple", 2, "std", "S22"),
    Cell(9, "edge-1-S23", "edge", 1, "std", "S23"),
    Cell(10, "edge-2-S24", "edge", 2, "std", "S24"),
    Cell(11, "edge-3-S25", "edge", 3, "std", "S25"),
    Cell(12, "fade-1-S12", "fade", 1, "std", "S12"),
    Cell(13, "fade-2-S13", "fade", 2, "std", "S13"),
    Cell(14, "fade-3-S14", "fade", 3, "std", "S14"),
    Cell(15, "fold-1-S18", "fold", 1, "std", "S18"),
    Cell(16, "fold-2-S19", "fold", 2, "std", "S19"),
    Cell(17, "fold-3-S20", "fold", 3, "std", "S20"),
    Cell(18, "locate-0-S26", "locate", 0, "std", "S26"),
    Cell(19, "locate-1-S27", "locate", 1, "std", "S27"),
    Cell(20, "scratch-1-S15", "scratch", 1, "std", "S15"),
    Cell(21, "scratch-2-S16", "scratch", 2, "std", "S16"),
    Cell(22, "scratch-3-S17", "scratch", 3, "std", "S17"),
    Cell(23, "scuff-1-S09", "scuff", 1, "std", "S09"),
    Cell(24, "scuff-2-S10", "scuff", 2, "std", "S10"),
    Cell(25, "scuff-3-S11", "scuff", 3, "std", "S11"),
    Cell(26, "water-1-S06", "water", 1, "std", "S06"),
    Cell(27, "water-2-S07", "water", 2, "std", "S07"),
    Cell(28, "water-3-S08", "water", 3, "std", "S08"),
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def check_exact(path: Path, size: int, digest: str) -> bytes:
    data = path.read_bytes()
    assert len(data) == size, (path, len(data), size)
    assert sha256_bytes(data) == digest, path
    return data


def u16(data: bytes, off: int) -> int:
    return struct.unpack_from(">H", data, off)[0]


def i16(data: bytes, off: int) -> int:
    return struct.unpack_from(">h", data, off)[0]


def u32(data: bytes, off: int) -> int:
    return struct.unpack_from(">I", data, off)[0]


class TrueTypeMetrics:
    def __init__(self, data: bytes, pdf_name: str, fixed: bool) -> None:
        self.data = data
        self.pdf_name = pdf_name
        self.fixed = fixed
        num_tables = u16(data, 4)
        self.tables: dict[str, tuple[int, int]] = {}
        for index in range(num_tables):
            off = 12 + 16 * index
            tag = data[off : off + 4].decode("ascii")
            self.tables[tag] = (u32(data, off + 8), u32(data, off + 12))
        head = self.table("head")
        hhea = self.table("hhea")
        maxp = self.table("maxp")
        self.units = u16(head, 18)
        self.bbox = (i16(head, 36), i16(head, 38), i16(head, 40), i16(head, 42))
        self.ascent = i16(hhea, 4)
        self.descent = i16(hhea, 6)
        self.num_hmetrics = u16(hhea, 34)
        self.num_glyphs = u16(maxp, 4)
        hmtx = self.table("hmtx")
        advances = [u16(hmtx, 4 * index) for index in range(self.num_hmetrics)]
        advances.extend([advances[-1]] * (self.num_glyphs - self.num_hmetrics))
        self.advances = advances
        self.cmap = self._read_cmap()
        for code in range(32, 127):
            assert code in self.cmap, (pdf_name, code)

    def table(self, tag: str) -> bytes:
        off, length = self.tables[tag]
        return self.data[off : off + length]

    def _read_cmap(self) -> dict[int, int]:
        data = self.table("cmap")
        candidates: list[tuple[int, int, int]] = []
        for index in range(u16(data, 2)):
            off = 4 + 8 * index
            platform = u16(data, off)
            encoding = u16(data, off + 2)
            sub = u32(data, off + 4)
            rank = 0 if (platform, encoding) == (3, 10) else 1 if (platform, encoding) == (3, 1) else 2
            candidates.append((rank, sub, u16(data, sub)))
        for _, sub, fmt in sorted(candidates):
            if fmt == 12:
                result: dict[int, int] = {}
                count = u32(data, sub + 12)
                for index in range(count):
                    off = sub + 16 + 12 * index
                    start, end, gid = u32(data, off), u32(data, off + 4), u32(data, off + 8)
                    for code in range(max(start, 32), min(end, 126) + 1):
                        result[code] = gid + code - start
                if all(code in result for code in range(32, 127)):
                    return result
            if fmt == 4:
                seg_count = u16(data, sub + 6) // 2
                end_off = sub + 14
                start_off = end_off + 2 * seg_count + 2
                delta_off = start_off + 2 * seg_count
                range_off = delta_off + 2 * seg_count
                result = {}
                for code in range(32, 127):
                    for seg in range(seg_count):
                        end_code = u16(data, end_off + 2 * seg)
                        start_code = u16(data, start_off + 2 * seg)
                        if start_code <= code <= end_code:
                            delta = i16(data, delta_off + 2 * seg)
                            ro_word = range_off + 2 * seg
                            ro = u16(data, ro_word)
                            if ro == 0:
                                gid = (code + delta) & 0xFFFF
                            else:
                                gid_off = ro_word + ro + 2 * (code - start_code)
                                gid = u16(data, gid_off)
                                if gid:
                                    gid = (gid + delta) & 0xFFFF
                            result[code] = gid
                            break
                if all(code in result for code in range(32, 127)):
                    return result
        raise AssertionError(f"no complete ASCII cmap in {self.pdf_name}")

    def width_units(self, text: str) -> int:
        return sum(self.advances[self.cmap[ord(char)]] for char in text)

    def width_points(self, text: str, font_size: float) -> float:
        return self.width_units(text) * font_size / self.units

    def pdf_width(self, code: int) -> float:
        return self.advances[self.cmap[code]] * 1000.0 / self.units

    def scaled_1000(self, value: int) -> float:
        return value * 1000.0 / self.units


def num(value: float) -> str:
    text = f"{value:.8f}".rstrip("0").rstrip(".")
    return text if text != "-0" else "0"


def pdf_escape(text: str) -> str:
    assert text.isascii()
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def stream_object(entries: str, data: bytes) -> bytes:
    return f"<< {entries} /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream"


def to_unicode_cmap() -> bytes:
    rows = [f"<{code:02X}> <{code:04X}>" for code in range(32, 127)]
    return (
        "/CIDInit /ProcSet findresource begin\n"
        "12 dict begin\n"
        "begincmap\n"
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
        "/CMapName /QuietKeyASCII def\n"
        "/CMapType 2 def\n"
        "1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
        f"{len(rows)} beginbfchar\n" + "\n".join(rows) + "\nendbfchar\n"
        "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n"
    ).encode("ascii")


def font_objects(font: TrueTypeMetrics, file_obj: int, descriptor_obj: int, cmap_obj: int) -> tuple[bytes, bytes, bytes, bytes]:
    font_stream = stream_object(f"/Length1 {len(font.data)}", font.data)
    flags = 33 if font.fixed else 32
    bbox = " ".join(num(font.scaled_1000(value)) for value in font.bbox)
    descriptor = (
        f"<< /Type /FontDescriptor /FontName /{font.pdf_name} /Flags {flags} "
        f"/FontBBox [{bbox}] /ItalicAngle 0 /Ascent {num(font.scaled_1000(font.ascent))} "
        f"/Descent {num(font.scaled_1000(font.descent))} /CapHeight {num(font.scaled_1000(font.ascent))} "
        f"/StemV 80 /FontFile2 {file_obj} 0 R >>"
    ).encode("ascii")
    cmap_stream = stream_object("", to_unicode_cmap())
    widths = " ".join(num(font.pdf_width(code)) for code in range(32, 127))
    font_dict = (
        f"<< /Type /Font /Subtype /TrueType /BaseFont /{font.pdf_name} /FirstChar 32 /LastChar 126 "
        f"/Widths [{widths}] /Encoding /WinAnsiEncoding /FontDescriptor {descriptor_obj} 0 R "
        f"/ToUnicode {cmap_obj} 0 R >>"
    ).encode("ascii")
    return font_stream, descriptor, cmap_stream, font_dict


def wrap_body(source: str, font: TrueTypeMetrics, font_size: float, max_width: float) -> list[str]:
    assert source.endswith("\n")
    visual: list[str] = []
    for source_line in source[:-1].split("\n"):
        if source_line == "":
            visual.append("")
            continue
        words = source_line.split(" ")
        assert all(words)
        current = words[0]
        for word in words[1:]:
            candidate = current + " " + word
            if font.width_points(candidate, font_size) <= max_width:
                current = candidate
            else:
                assert font.width_points(current, font_size) <= max_width
                visual.append(current)
                current = word
        assert font.width_points(current, font_size) <= max_width
        visual.append(current)
    return visual


def build_pdf(body: str, token: str, serif: TrueTypeMetrics, mono: TrueTypeMetrics) -> tuple[bytes, dict[str, str]]:
    mm = 72.0 / 25.4
    page_w, page_h = 210.0 * mm, 297.0 * mm
    margin = 16.0 * mm
    body_size, body_leading = 10.5, 10.5 * 1.3
    footer_size, footer_leading = 7.5, 7.5 * 1.3
    max_width = page_w - 2 * margin
    lines = wrap_body(body, serif, body_size, max_width)
    body_first_baseline = page_h - margin - body_size
    body_last_baseline = body_first_baseline - (len(lines) - 1) * body_leading

    content: list[str] = ["0 g"]
    for index, line in enumerate(lines):
        if line:
            y = body_first_baseline - index * body_leading
            content.append(f"BT /FSerif {num(body_size)} Tf 1 0 0 1 {num(margin)} {num(y)} Tm ({pdf_escape(line)}) Tj ET")

    token_a, token_b = token[:64], token[64:]
    assert len(token_a) == 64 and len(token_b) in (52, 58, 64)
    font_height = (mono.ascent - mono.descent) * footer_size / mono.units
    lower_baseline = margin + (footer_leading - font_height) / 2.0 - mono.descent * footer_size / mono.units
    upper_baseline = lower_baseline + footer_leading
    content.append(f"BT /FMono {num(footer_size)} Tf 1 0 0 1 {num(margin)} {num(upper_baseline)} Tm ({token_a}) Tj ET")
    content.append(f"BT /FMono {num(footer_size)} Tf 1 0 0 1 {num(margin)} {num(lower_baseline)} Tm ({token_b}) Tj ET")
    content_bytes = ("\n".join(content) + "\n").encode("ascii")

    objects: list[bytes] = []
    objects.extend(font_objects(serif, 1, 2, 3))
    objects.extend(font_objects(mono, 5, 6, 7))
    objects.append(stream_object("", content_bytes))
    objects.append(
        (
            f"<< /Type /Page /Parent 11 0 R /MediaBox [0 0 {num(page_w)} {num(page_h)}] "
            f"/CropBox [0 0 {num(page_w)} {num(page_h)}] /Resources << /Font << /FSerif 4 0 R /FMono 8 0 R >> >> "
            f"/Contents 9 0 R >>"
        ).encode("ascii")
    )
    objects.append(b"<< /Type /Pages /Kids [10 0 R] /Count 1 >>")
    objects.append(b"<< /Type /Catalog /Pages 11 0 R >>")

    output = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 12 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    pdf = bytes(output)

    footer_span_mm = mono.width_points(token_a, footer_size) / mm
    f_top_from_top_mm = 297.0 - (margin + 2 * footer_leading) / mm
    assert abs(footer_span_mm - 101.6165364583) < 0.000001
    assert round(f_top_from_top_mm, 2) == 274.12
    assert round(297.0 - margin / mm, 2) == 281.00
    assert body_last_baseline > margin + 2 * footer_leading + 20.0
    assert pdf.count(serif.data) == 1 and pdf.count(mono.data) == 1
    assert pdf.count(b"/FontFile2") == 2
    assert b"Helvetica" not in pdf
    for forbidden in (b"/JavaScript", b"/OpenAction", b"/EmbeddedFiles", b"/URI", b"/Launch", b"/Annots", b"/AA"):
        assert forbidden not in pdf
    return pdf, {
        "body_visual_lines": str(len(lines)),
        "body_last_baseline_pt": num(body_last_baseline),
        "footer_span_mm": f"{footer_span_mm:.10f}",
        "f_top_from_top_mm": f"{f_top_from_top_mm:.10f}",
        "footer_lower_edge_from_top_mm": "281.0000000000",
    }


def write_inputs() -> None:
    for directory in (BODIES, PAYLOADS, RENDERER, MASTERS, MANIFESTS):
        directory.mkdir(parents=True, exist_ok=True)
    recipe = RECIPE_BODY.encode("ascii")
    travel = TRAVEL_BODY.encode("ascii")
    assert len(recipe) == 1_112 and recipe.count(b"\n") == 28
    assert len(travel) == 1_417 and travel.count(b"\n") == 20
    assert sha256_bytes(recipe) == "ec51fb35a729d2c29bcae039209994bdf5fcd20fb92eb886155a8b4cfde929b9"
    assert sha256_bytes(travel) == "69745a655c87647f32b86c832ad40a3f1903e4510125ad1a272651cb37050230"
    (BODIES / "recipe-body.txt").write_bytes(recipe)
    (BODIES / "travel-body.txt").write_bytes(travel)
    for payload in PAYLOAD_DATA:
        data = payload.token.encode("ascii")
        assert len(data) in (116, 122, 128)
        assert sha256_bytes(data) == payload.token_sha256
        (PAYLOADS / f"q{payload.q:02d}-{payload.payload_id}.txt").write_bytes(data)


def page_rows(master_hashes: dict[tuple[int, str], tuple[str, str]]) -> list[str]:
    rows: list[str] = []
    position = 0
    for cell in CELLS:
        for payload in PAYLOAD_DATA:
            position += 1
            template = "recipe" if (payload.q + cell.c) % 2 == 0 else "travel"
            template_code = "R" if template == "recipe" else "T"
            master_path, master_hash = master_hashes[(payload.q, template)]
            page_id = f"P1-c{cell.c:02d}-{cell.sequence}-q{payload.q:02d}-{payload.payload_id}-{template_code}"
            fields = (
                f"position={position:03d}",
                f"page_id={page_id}",
                f"cell_ordinal={cell.c:02d}",
                f"cell_id={cell.identity}",
                f"damage_class={cell.damage_class}",
                f"level={cell.level}",
                f"lighting={cell.lighting}",
                f"sequence={cell.sequence}",
                f"q={payload.q:02d}",
                f"payload_id={payload.payload_id}",
                f"lineage={payload.lineage}",
                f"profile={payload.profile}",
                f"template={template}",
                f"master_path={master_path}",
                f"master_sha256={master_hash}",
                f"scheduled_slots={page_id}-A01,{page_id}-A02,{page_id}-A03",
            )
            rows.append("page=" + ";".join(fields))
    assert position == 174
    return rows


def verify_matrix(rows: list[str]) -> None:
    parsed = [dict(field.split("=", 1) for field in row.removeprefix("page=").split(";")) for row in rows]
    assert len(parsed) == 174
    assert len({row["page_id"] for row in parsed}) == 174
    assert len({slot for row in parsed for slot in row["scheduled_slots"].split(",")}) == 522
    assert Counter(row["template"] for row in parsed) == {"recipe": 87, "travel": 87}
    assert Counter(row["profile"] for row in parsed) == {"RS(72,60)": 58, "RS(76,60)": 58, "RS(80,60)": 58}
    assert Counter(row["lineage"] for row in parsed) == {"T0": 87, "T3": 87}
    assert set(Counter(row["payload_id"] for row in parsed).values()) == {29}
    assert Counter(row["lighting"] for row in parsed) == {"std": 162, "dim": 6, "glare": 6}
    for cell in CELLS:
        cell_rows = [row for row in parsed if row["cell_ordinal"] == f"{cell.c:02d}"]
        assert len(cell_rows) == 6
        assert Counter(row["template"] for row in cell_rows) == {"recipe": 3, "travel": 3}
        assert Counter(row["profile"] for row in cell_rows) == {"RS(72,60)": 2, "RS(76,60)": 2, "RS(80,60)": 2}


def main() -> None:
    for path, (size, digest) in EXPECTED_FILES.items():
        check_exact(path, size, digest)
    write_inputs()
    serif_data = SERIF.read_bytes()
    mono_data = MONO.read_bytes()
    serif = TrueTypeMetrics(serif_data, "LiberationSerif", False)
    mono = TrueTypeMetrics(mono_data, "LiberationMono", True)
    mono_advances = {mono.advances[mono.cmap[ord(char)]] for payload in PAYLOAD_DATA for char in payload.token}
    assert mono_advances == {1229}

    master_hashes: dict[tuple[int, str], tuple[str, str]] = {}
    master_entries: list[str] = []
    for payload in PAYLOAD_DATA:
        for template, body in (("recipe", RECIPE_BODY), ("travel", TRAVEL_BODY)):
            pdf_a, layout_a = build_pdf(body, payload.token, serif, mono)
            pdf_b, layout_b = build_pdf(body, payload.token, serif, mono)
            assert pdf_a == pdf_b and layout_a == layout_b
            filename = f"q{payload.q:02d}-{payload.payload_id}-{template}.pdf"
            path = MASTERS / filename
            path.write_bytes(pdf_a)
            digest = sha256_bytes(pdf_a)
            relative = path.as_posix()
            master_hashes[(payload.q, template)] = (relative, digest)
            master_entries.append(
                "master="
                + ";".join(
                    (
                        f"q={payload.q:02d}",
                        f"payload_id={payload.payload_id}",
                        f"lineage={payload.lineage}",
                        f"profile={payload.profile}",
                        f"token_length={len(payload.token)}",
                        f"token_sha256={payload.token_sha256}",
                        f"template={template}",
                        f"path={relative}",
                        f"bytes={len(pdf_a)}",
                        f"sha256={digest}",
                        "pages=1",
                        "repeat_generation_equal=true",
                        f"body_visual_lines={layout_a['body_visual_lines']}",
                        f"body_last_baseline_pt={layout_a['body_last_baseline_pt']}",
                        f"footer_span_mm={layout_a['footer_span_mm']}",
                        f"f_top_from_top_mm={layout_a['f_top_from_top_mm']}",
                    )
                )
            )
    assert len(master_entries) == 12

    rows = page_rows(master_hashes)
    verify_matrix(rows)
    page_block = ("\n".join(rows) + "\n").encode("ascii")
    page_tsv = MANIFESTS / "M19-A1-PHASE1-PAGES.tsv"
    header = (
        "position\tpage_id\tcell_ordinal\tcell_id\tdamage_class\tlevel\tlighting\tsequence\tq\tpayload_id\tlineage\tprofile\ttemplate\tmaster_path\tmaster_sha256\tscheduled_slot_1\tscheduled_slot_2\tscheduled_slot_3\n"
    )
    tsv_rows = []
    for row in rows:
        fields = dict(field.split("=", 1) for field in row.removeprefix("page=").split(";"))
        slots = fields["scheduled_slots"].split(",")
        tsv_rows.append("\t".join((fields["position"], fields["page_id"], fields["cell_ordinal"], fields["cell_id"], fields["damage_class"], fields["level"], fields["lighting"], fields["sequence"], fields["q"], fields["payload_id"], fields["lineage"], fields["profile"], fields["template"], fields["master_path"], fields["master_sha256"], *slots)))
    page_tsv.write_bytes((header + "\n".join(tsv_rows) + "\n").encode("ascii"))

    self_path = Path(__file__)
    self_hash = sha256_file(self_path)
    master_block = ("\n".join(master_entries) + "\n").encode("ascii")
    manifest_lines = [
        "# QUIETKEY_M19_A1_PHASE1_PRINT_INPUTS_V1",
        "# EXPERIMENTAL - NO REAL FUNDS - NOT A WALLET",
        "phase=1",
        "status=digital-print-inputs-only;physical-printing-not-started;captures-not-started",
        "outcome_blind=true",
        "decode_outcomes=0",
        "decoder_execution=0",
        "fresh_capture_pixel_inspection=0",
        f"payload_source_commit={PAYLOAD_SOURCE_COMMIT}",
        f"protocol_commit={PROTOCOL_COMMIT}",
        f"font_source_register_commit={FONT_SOURCE_COMMIT}",
        f"product_head_at_render={PRODUCT_HEAD_AT_RENDER}",
        f"generator_id={GENERATOR_ID}",
        f"generator_python={sys.version.split()[0]}",
        f"generator_path={self_path.as_posix()}",
        f"generator_sha256={self_hash}",
        "pdf_version=1.7",
        "pdf_metadata=none",
        "pdf_identifier=none",
        "pdf_boxes=MediaBox-and-CropBox-exact-A4-210x297mm;UserUnit-implicit-1;Rotate-implicit-0",
        "body_layout=left-aligned;black-on-white;top-left-at-16mm-margin;10.5pt;line-height-1.3;ASCII-space-word-wrap-without-hyphenation;no-kerning-or-font-features;trailing-source-LF-not-an-extra-visual-line;overflow-reject",
        "footer_layout=left-16mm;bottom-16mm;7.5pt;line-height-1.3;break-after-symbol-64;no-separator;no-ligatures;no-kerning-or-font-features;only-token-visible",
        "font_embedding=both-complete-unmodified-TTF-streams;uncompressed;no-subsets;no-fallback;no-third-font",
        "active_content=none;no-annotations-actions-JavaScript-attachments-URI-or-launch",
        "font_install_verification=PASS;archive-and-both-TTFs-and-license-match-QK-DEC-094-and-SOURCE-REGISTER",
        "font_tag_commit=4b0192046158094654e865245832c66d2104219e",
        "font_archive_bytes=2385008",
        "font_archive_sha256=7191c669bf38899f73a2094ed00f7b800553364f90e2637010a69c0e268f25d0",
        "serif_bytes=393576",
        "serif_sha256=058ea80864aef09a23f45cbec2bb5400bc3dfbdea01c3f10538a21fcb497fb74",
        "mono_bytes=319508",
        "mono_sha256=f2b83c763e8afd21709333370bed4774337fae82267937e2b5aea7e2fbd922c1",
        "license_bytes=4414",
        "license_sha256=93fed46019c38bbe566b479d22148e2e8a1e85ada614accb0211c37b2c61c19b",
        "license_git_blob=aba73e8a403084a93a245ca00e4a0db007886e0a",
        "recipe_body=1112-bytes;28-LF;final-LF;sha256-ec51fb35a729d2c29bcae039209994bdf5fcd20fb92eb886155a8b4cfde929b9",
        "travel_body=1417-bytes;20-LF;final-LF;sha256-69745a655c87647f32b86c832ad40a3f1903e4510125ad1a272651cb37050230",
        "matrix_rule=recipe-iff-(q+c)-mod-2-equals-0;strict-order-c-then-q;phase1-q-00-01-02-09-10-11",
        "expected_masters=12",
        "expected_pages=174",
        "expected_scheduled_captures=522",
        "expected_templates=recipe-87-pages-261-captures;travel-87-pages-261-captures",
        "expected_profiles=each-58-pages-174-captures",
        "expected_lineages=each-87-pages-261-captures",
        "expected_payloads=each-29-pages-87-captures",
        "expected_lighting=std-162-pages-486-captures;dim-6-pages-18-captures;glare-6-pages-18-captures",
        "water_capture_window=default-mechanical-treatment-rule;begin-within-2-hours-of-completion;water-drying-complete-after-30-minute-flat-air-dry",
        "physical_record_at_use=all-QK-DEC-094-identities-settings-timestamps-EXIF-and-batch-facts-pending-before-applicable-use",
        "physical_retake_rule=only-obvious-blur-page-edge-cutoff-or-wrong-cell;first-nonfaulty-image-is-sole-canonical-capture",
        "physical_deviation_rule=all-other-listed-deviations-stop-phase-and-tombstone-slot;no-replacement-reprint-retreatment-renumbering-or-slot-reuse-without-Owner-direction",
        f"pages_tsv_path={page_tsv.as_posix()}",
        f"pages_tsv_bytes={page_tsv.stat().st_size}",
        f"pages_tsv_sha256={sha256_file(page_tsv)}",
        f"master_entry_block_sha256={sha256_bytes(master_block)}",
        f"page_entry_block_sha256={sha256_bytes(page_block)}",
        "BEGIN_MASTER_ENTRIES",
        *master_entries,
        "END_MASTER_ENTRIES",
        "BEGIN_PAGE_ENTRIES",
        *rows,
        "END_PAGE_ENTRIES",
    ]
    manifest = MANIFESTS / "M19-A1-PHASE1-PRINT-INPUTS.sha256"
    manifest.write_bytes(("\n".join(manifest_lines) + "\n").encode("ascii"))

    assert manifest.read_bytes().endswith(b"\n")
    print(f"generated_masters={len(master_entries)}")
    print(f"scheduled_pages={len(rows)}")
    print("scheduled_captures=522")
    print(f"manifest_sha256={sha256_file(manifest)}")
    print(f"page_tsv_sha256={sha256_file(page_tsv)}")


if __name__ == "__main__":
    main()
