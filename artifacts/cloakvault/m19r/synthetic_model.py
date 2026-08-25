#!/usr/bin/env python3
"""Deterministic M19-R morphology primitives with a fail-closed corpus gate.

This module has no decoder, scorer, adaptive fitter, image-library dependency,
or fresh-capture path. It can transform an in-memory grayscale test image and
construct the QK-DEC-103 comparison plan. It cannot write the 1,566-image
comparison corpus while the committed registration remains a draft.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from array import array
from collections import deque
from dataclasses import dataclass
from math import isqrt
from pathlib import Path
from typing import List, Mapping, Optional, Sequence, Tuple


HERE = Path(__file__).resolve().parent
PAYLOADS_PATH = HERE / "inputs" / "PAYLOADS.tsv"
DRAFT_PATH = HERE / "registrations" / "MODEL-FREEZE-DRAFT.json"
ACTIVE_PATH = HERE / "registrations" / "MODEL-FREEZE-ACTIVE.json"
EXPECTED_STATUS = "DRAFT_NOT_ACTIVE"
# These remain None in every pre-activation build. A later Owner-ratified change
# must compile the exact registration hash, decision id, and Decision Log commit
# into this module before even a structurally valid file can pass.
EXPECTED_ACTIVE_REGISTRATION_SHA256: Optional[str] = None
EXPECTED_OWNER_DECISION_ID: Optional[str] = None
EXPECTED_DECISION_LOG_COMMIT: Optional[str] = None
PROFILES = ("Rs72_60", "Rs76_60", "Rs80_60")
LINEAGES = ("T0", "T1", "T2", "T3", "T4", "T5")
REALIZATIONS = (0, 1, 2)
Q16 = 65_536

# Candidate synthetic geometry preserving the frozen locate-1 facts. The page
# plane is tilted 20 degrees about its horizontal center line (top edge nearer)
# under a pinhole camera two page heights from page center, scaled to 64% of the
# frame, then rolled 15 degrees clockwise. The virtual distance and scale remain
# subject to the model-freeze ratification. Exact Q16 values make the candidate
# cross-version and leave enough perimeter for every page corner plus the
# common geometry bounds.
COS_15_Q16 = 63_299
SIN_15_Q16 = 16_962
COS_20_Q16 = 61_584
SIN_20_Q16 = 22_415
LOCATE_CAMERA_DISTANCE_PAGE_HEIGHTS = 2
LOCATE_DEPTH_Q16 = (SIN_20_Q16 + 1) // LOCATE_CAMERA_DISTANCE_PAGE_HEIGHTS
LOCATE_PAGE_SCALE_Q16 = 41_943

CELLS: Tuple[Tuple[str, str, str, int, str], ...] = (
    ("c00", "baseline-0-dim-S01", "baseline", 0, "dim"),
    ("c01", "baseline-0-glare-S02", "baseline", 0, "glare"),
    ("c02", "baseline-0-std-S01", "baseline", 0, "std"),
    ("c03", "baseline-0-std-S02", "baseline", 0, "std"),
    ("c04", "coffee-1-S03", "coffee", 1, "std"),
    ("c05", "coffee-2-S04", "coffee", 2, "std"),
    ("c06", "coffee-3-S05", "coffee", 3, "std"),
    ("c07", "crumple-1-S21", "crumple", 1, "std"),
    ("c08", "crumple-2-S22", "crumple", 2, "std"),
    ("c09", "edge-1-S23", "edge", 1, "std"),
    ("c10", "edge-2-S24", "edge", 2, "std"),
    ("c11", "edge-3-S25", "edge", 3, "std"),
    ("c12", "fade-1-S12", "fade", 1, "std"),
    ("c13", "fade-2-S13", "fade", 2, "std"),
    ("c14", "fade-3-S14", "fade", 3, "std"),
    ("c15", "fold-1-S18", "fold", 1, "std"),
    ("c16", "fold-2-S19", "fold", 2, "std"),
    ("c17", "fold-3-S20", "fold", 3, "std"),
    ("c18", "locate-0-S26", "locate", 0, "std"),
    ("c19", "locate-1-S27", "locate", 1, "std"),
    ("c20", "scratch-1-S15", "scratch", 1, "std"),
    ("c21", "scratch-2-S16", "scratch", 2, "std"),
    ("c22", "scratch-3-S17", "scratch", 3, "std"),
    ("c23", "scuff-1-S09", "scuff", 1, "std"),
    ("c24", "scuff-2-S10", "scuff", 2, "std"),
    ("c25", "scuff-3-S11", "scuff", 3, "std"),
    ("c26", "water-1-S06", "water", 1, "std"),
    ("c27", "water-2-S07", "water", 2, "std"),
    ("c28", "water-3-S08", "water", 3, "std"),
)


class ConfigurationError(ValueError):
    pass


class ModelFreezeRequired(RuntimeError):
    pass


@dataclass(frozen=True)
class GrayImage:
    width: int
    height: int
    pixels: bytes

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("image dimensions must be positive")
        if len(self.pixels) != self.width * self.height:
            raise ValueError("pixel count does not match dimensions")


@dataclass(frozen=True)
class SampleParameters:
    cell: str
    damage_class: str
    severity: int
    lighting: str
    translate_x: int
    translate_y: int
    shear_q16: int
    gain_q16: int
    offset: int
    blur_radius: int
    mask_count: int
    mask_opacity_q16: int
    mask_value: int
    glare_opacity_q16: int
    seed_sha256: str


@dataclass(frozen=True)
class MetricVector:
    geometry_corner_rms_q16: int
    geometry_corner_max_q16: int
    damage_centroid_x_q16: int
    damage_centroid_y_q16: int
    footer_overlap_q16: int
    component_count: int
    largest_component_fraction_q16: int
    luminance_median_u8: int
    contrast_iqr_u8: int
    luminance_p05_u8: int
    luminance_p95_u8: int
    edge_energy_q16: int
    high_edge_fraction_q16: int
    glare_coverage_q16: int
    glare_centroid_x_q16: int
    glare_centroid_y_q16: int


class CounterRng:
    """SHA-256 counter stream with a fully specified cross-version result."""

    def __init__(self, seed: bytes) -> None:
        if len(seed) != 32:
            raise ValueError("seed must be exactly 32 bytes")
        self.seed = seed
        self.counter = 0
        self.buffer = b""

    def _fill(self) -> None:
        block = hashlib.sha256(
            b"QuietKey/M19-R/rng/v1\x00"
            + self.seed
            + self.counter.to_bytes(8, "big")
        ).digest()
        self.counter += 1
        self.buffer += block

    def u32(self) -> int:
        while len(self.buffer) < 4:
            self._fill()
        value = int.from_bytes(self.buffer[:4], "big")
        self.buffer = self.buffer[4:]
        return value

    def integer(self, low: int, high: int) -> int:
        if low > high:
            raise ValueError("invalid integer range")
        span = high - low + 1
        cutoff = (1 << 32) - ((1 << 32) % span)
        while True:
            value = self.u32()
            if value < cutoff:
                return low + value % span


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_draft(path: Path = DRAFT_PATH) -> dict:
    try:
        value = json.loads(path.read_text("ascii"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError("cannot read model registration") from exc
    validate_draft(value)
    return value


def _integer_bound(bounds: Mapping[str, object], name: str) -> Tuple[int, int]:
    item = bounds.get(name)
    if not isinstance(item, dict) or set(item) != {"candidate", "min", "max", "unit"}:
        raise ConfigurationError("invalid bound {}".format(name))
    if item["candidate"] != "OWNER_RATIFICATION_REQUIRED":
        raise ConfigurationError("bound is not marked candidate: {}".format(name))
    low, high = item["min"], item["max"]
    if type(low) is not int or type(high) is not int or low > high:
        raise ConfigurationError("invalid integer endpoints: {}".format(name))
    return low, high


def validate_draft(value: Mapping[str, object]) -> None:
    if value.get("format_version") != 1:
        raise ConfigurationError("format_version must be 1")
    if value.get("authority") != "QK-DEC-103":
        raise ConfigurationError("authority must be QK-DEC-103")
    if value.get("status") != EXPECTED_STATUS:
        raise ConfigurationError("committed registration must remain DRAFT_NOT_ACTIVE")
    activation = value.get("activation")
    if not isinstance(activation, dict):
        raise ConfigurationError("missing activation object")
    if activation.get("comparison_generation_enabled") is not False:
        raise ConfigurationError("comparison generation must be disabled")
    if activation.get("active_registration_present") is not False:
        raise ConfigurationError("active registration must be absent")
    if activation.get("active_registration_required_path") != "artifacts/cloakvault/m19r/registrations/MODEL-FREEZE-ACTIVE.json":
        raise ConfigurationError("active registration path mismatch")
    if activation.get("required_schema") != "QK-M19R-MODEL-FREEZE-ACTIVATION-V1":
        raise ConfigurationError("activation schema mismatch")
    if activation.get("compiled_authority_binding") != "REQUIRED_AND_CURRENTLY_UNSET":
        raise ConfigurationError("activation authority binding mismatch")
    expected_shape = {
        "top_level_keys": ["schema", "status", "authority", "bindings", "scope"],
        "authority_keys": ["owner_decision_id", "parent_decision_id", "decision_log_commit"],
        "bindings_keys": [
            "draft_sha256",
            "implementation_sha256",
            "clean_render_manifest_sha256",
            "payload_registry_sha256",
        ],
        "scope_exact": {
            "comparison_image_generation": True,
            "fresh_anchor_decode": False,
            "scoring": False,
        },
    }
    if activation.get("future_document_shape") != expected_shape:
        raise ConfigurationError("future activation shape mismatch")
    model = value.get("model")
    if not isinstance(model, dict):
        raise ConfigurationError("missing model object")
    if model.get("class") != "qk-m19r-integer-morphology":
        raise ConfigurationError("unexpected model class")
    if model.get("version") != "candidate-v1-not-active":
        raise ConfigurationError("unexpected model version")
    if model.get("operator_order") != [
        "locate-geometry-if-locate",
        "translate-and-shear",
        "gain-and-luminance",
        "box-blur",
        "class-specific-operator-except-locate-geometry",
        "glare",
    ]:
        raise ConfigurationError("operator order mismatch")
    bounds = model.get("bounds")
    if not isinstance(bounds, dict):
        raise ConfigurationError("missing model bounds")
    expected_bounds = {
        "translate_x_pixels",
        "translate_y_pixels",
        "shear_q16",
        "gain_q16",
        "luminance_offset_u8",
        "blur_radius_pixels",
        "mask_count",
        "mask_opacity_q16",
        "mask_value_u8",
        "glare_opacity_q16",
    }
    if set(bounds) != expected_bounds:
        raise ConfigurationError("model bound set mismatch")
    for name in expected_bounds:
        _integer_bound(bounds, name)
    operators = model.get("class_operators")
    expected_operators = {
        "baseline": "lighting-only-v1",
        "coffee": "contact-ring-stain-v1",
        "water": "elliptical-pool-stain-v1",
        "crumple": "integer-warp-and-crease-v1",
        "edge": "bottom-notch-v1",
        "fade": "footer-abrasion-lighten-v1",
        "fold": "vertical-crease-v1",
        "scratch": "indexed-cut-lines-v1",
        "scuff": "bounded-abrasion-strokes-v1",
        "locate": "page-geometry-v1",
    }
    if not isinstance(operators, dict) or set(operators) != set(expected_operators):
        raise ConfigurationError("class operator set mismatch")
    for name, algorithm in expected_operators.items():
        item = operators[name]
        if not isinstance(item, dict) or item.get("algorithm") != algorithm:
            raise ConfigurationError("class operator mismatch: {}".format(name))
        if item.get("ratification") != "OWNER_RATIFICATION_REQUIRED":
            raise ConfigurationError("class operator not marked candidate: {}".format(name))
    seeds = value.get("seeds")
    if not isinstance(seeds, dict):
        raise ConfigurationError("missing seeds")
    seed_hex = seeds.get("public_master_seed_hex")
    if not isinstance(seed_hex, str) or len(seed_hex) != 64:
        raise ConfigurationError("public seed must be 32-byte hex")
    try:
        bytes.fromhex(seed_hex)
    except ValueError as exc:
        raise ConfigurationError("public seed is not hex") from exc
    if seeds.get("realizations") != [0, 1, 2]:
        raise ConfigurationError("comparison realizations must be 0,1,2")
    partitions = value.get("partitions")
    if not isinstance(partitions, dict):
        raise ConfigurationError("missing partitions")
    comparison = partitions.get("comparison")
    if not isinstance(comparison, dict):
        raise ConfigurationError("missing comparison partition")
    if comparison.get("expected_images") != 1566:
        raise ConfigurationError("comparison image count must be 1566")
    if comparison.get("lineages") != list(LINEAGES):
        raise ConfigurationError("comparison lineage order mismatch")
    if comparison.get("profiles") != list(PROFILES):
        raise ConfigurationError("comparison profile order mismatch")
    if comparison.get("cells") != [cell[0] for cell in CELLS]:
        raise ConfigurationError("comparison cell order mismatch")
    if comparison.get("realizations") != list(REALIZATIONS):
        raise ConfigurationError("comparison realization order mismatch")
    anchors = partitions.get("physical_anchors")
    if not isinstance(anchors, dict):
        raise ConfigurationError("missing anchor partition")
    if anchors.get("calibration_capture") != 1:
        raise ConfigurationError("capture 1 must be calibration")
    if anchors.get("locked_holdout_captures") != [2, 3]:
        raise ConfigurationError("captures 2 and 3 must remain locked")
    if anchors.get("fresh_anchor_decode_allowed") is not False:
        raise ConfigurationError("fresh-anchor decode must be false")
    validation = value.get("validation")
    if not isinstance(validation, dict):
        raise ConfigurationError("missing validation")
    per_cell = validation.get("per_cell")
    if not isinstance(per_cell, list) or len(per_cell) != 29:
        raise ConfigurationError("validation must contain 29 cell rows")
    for expected, actual in zip(CELLS, per_cell):
        cell, identity, damage_class, severity, lighting = expected
        if actual.get("cell") != cell or actual.get("identity") != identity:
            raise ConfigurationError("validation cell order mismatch")
        if actual.get("damage_class") != damage_class or actual.get("severity") != severity:
            raise ConfigurationError("validation cell taxonomy mismatch")
        if actual.get("lighting") != lighting:
            raise ConfigurationError("validation lighting mismatch")
        if actual.get("criteria_profile") != "candidate-shared-v1":
            raise ConfigurationError("validation criteria profile mismatch")
        if actual.get("ratification") != "OWNER_RATIFICATION_REQUIRED":
            raise ConfigurationError("cell criteria not marked candidate")
    criteria = validation.get("criteria_profiles", {}).get("candidate-shared-v1")
    required = {
        "geometry",
        "damage_mask_placement_and_footer_overlap",
        "connectedness",
        "contrast_and_luminance",
        "blur_and_edge_spectrum",
        "glare",
    }
    if not isinstance(criteria, dict) or set(criteria) != required:
        raise ConfigurationError("validation metric family set mismatch")
    metric_contract = validation.get("metric_contract")
    if not isinstance(metric_contract, dict):
        raise ConfigurationError("missing metric contract")
    exact_metric_contract = {
        "difference_threshold_u8": 24,
        "difference_mask": "one-iff-absolute-observed-minus-clean-is-at-least-24-over-full-frame",
        "edge_threshold_u8": 32,
        "edge_spectrum": "within-F-horizontal-and-vertical-forward-absolute-gradients;energy=sum-times-Q16-over-count-times-255-half-up;high-fraction=count-at-least-32-over-count-half-up",
        "glare_threshold_u8": 250,
        "glare_mask": "within-F-one-iff-observed-at-least-250-and-observed-minus-clean-at-least-24",
        "connectivity": 4,
        "connectedness": "four-neighbor-components-over-full-frame-difference-mask;largest-fraction-largest-size-over-total-mask-count-half-up",
        "quantile_rule": "sorted-index-floor-(n-1)-times-p",
        "contrast_luminance": "within-F-p05-p25-median-p75-p95-by-quantile-rule;contrast-IQR=p75-minus-p25",
        "footer_bounds": "x=[16,117.6165]mm;y=[274.12,281.00]mm;A4=210x297mm;lower-inclusive-upper-exclusive",
        "footer_overlap": "difference-mask-count-inside-F-over-total-full-frame-difference-mask-count-half-up;zero-if-mask-empty",
        "absent_centroid": -1,
        "centroid": "per-axis-sum-pixel-coordinate-times-Q16-over-count-times-axis-pixels-minus-one-half-up;minus-one-minus-one-if-empty",
        "geometry_corner_order": "top-left,top-right,bottom-right,bottom-left;coordinates-Q16-page-width-height",
        "geometry": "each-corner-Euclidean-distance-normalized-by-Q16-page-diagonal-half-up;RMS=isqrt-floor-mean-squared;max=maximum",
    }
    if metric_contract != exact_metric_contract:
        raise ConfigurationError("metric contract mismatch")
    aggregation = validation.get("aggregation")
    exact_aggregation = {
        "anchor_center": "single-capture-1-metric-vector-per-cell",
        "synthetic_center": "fieldwise-middle-order-statistic-of-exactly-three-realizations",
        "cross_cell_pooling": "forbidden",
        "rounding": "integer-only-half-up-where-division-is-marked;otherwise-floor",
        "missing_value_rule": "centroid-minus-one;both-absent-pass;one-absent-named-mismatch",
    }
    if aggregation != exact_aggregation:
        raise ConfigurationError("aggregation contract mismatch")
    if validation.get("failure_action") != "STOP_NO_ADAPTIVE_RETUNING_OR_REGENERATION":
        raise ConfigurationError("validation failure action mismatch")


def _payload_rows() -> List[dict]:
    with PAYLOADS_PATH.open("r", encoding="ascii", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(rows) != 18:
        raise ConfigurationError("payload registry must contain 18 rows")
    return rows


def comparison_plan() -> List[dict]:
    rows = _payload_rows()
    plan = []
    for row in rows:
        q = int(row["q"])
        for cell_ordinal, cell in enumerate(CELLS):
            for realization in REALIZATIONS:
                template = "recipe" if (q + cell_ordinal) % 2 == 0 else "travel"
                plan.append(
                    {
                        "cell": cell[0],
                        "lineage": row["lineage"],
                        "member_id": "{}-{}-r{}".format(row["payload_id"], cell[0], realization),
                        "payload_id": row["payload_id"],
                        "profile": row["profile"],
                        "q": q,
                        "realization": realization,
                        "template": template,
                    }
                )
    if len(plan) != 1566 or len({row["member_id"] for row in plan}) != 1566:
        raise AssertionError("comparison plan cardinality mismatch")
    for lineage in LINEAGES:
        for cell, _, _, _, _ in CELLS:
            for realization in REALIZATIONS:
                paired = [
                    row
                    for row in plan
                    if row["lineage"] == lineage
                    and row["cell"] == cell
                    and row["realization"] == realization
                ]
                if {row["profile"] for row in paired} != set(PROFILES):
                    raise AssertionError("profile pairing mismatch")
    return plan


def plan_sha256(plan: Sequence[Mapping[str, object]]) -> str:
    encoded = json.dumps(plan, separators=(",", ":"), sort_keys=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def derive_seed(config: Mapping[str, object], lineage: str, cell: str, realization: int) -> bytes:
    if lineage not in LINEAGES or cell not in {item[0] for item in CELLS}:
        raise ValueError("unknown lineage or cell")
    if realization not in REALIZATIONS:
        raise ValueError("comparison realization must be 0, 1, or 2")
    master = bytes.fromhex(config["seeds"]["public_master_seed_hex"])
    material = (
        config["seeds"]["derivation_domain"].encode("ascii")
        + b"\x00"
        + master
        + lineage.encode("ascii")
        + bytes([int(cell[1:]), realization])
    )
    return hashlib.sha256(material).digest()


def derive_parameters(
    config: Mapping[str, object], lineage: str, cell: str, realization: int
) -> SampleParameters:
    validate_draft(config)
    seed = derive_seed(config, lineage, cell, realization)
    rng = CounterRng(seed)
    bounds = config["model"]["bounds"]

    def pick(name: str) -> int:
        low, high = _integer_bound(bounds, name)
        return rng.integer(low, high)

    cell_row = next(item for item in CELLS if item[0] == cell)
    damage_class, severity, lighting = cell_row[2], cell_row[3], cell_row[4]
    class_counts = {
        "baseline": (0, 0, 0, 0),
        "coffee": (0, 1, 3, 6),
        "water": (0, 1, 1, 1),
        "crumple": (0, 4, 12, 12),
        "edge": (0, 1, 1, 1),
        "fade": (0, 4, 8, 12),
        "fold": (0, 1, 1, 1),
        "scratch": (0, 1, 3, 6),
        "scuff": (0, 5, 15, 30),
        "locate": (0, 0, 0, 0),
    }
    mask_count = class_counts[damage_class][severity]
    glare = pick("glare_opacity_q16") if lighting == "glare" else 0
    gain = pick("gain_q16")
    offset = pick("luminance_offset_u8")
    if lighting == "dim":
        gain = gain * 3 // 4
        offset -= 24
    return SampleParameters(
        cell=cell,
        damage_class=damage_class,
        severity=severity,
        lighting=lighting,
        translate_x=pick("translate_x_pixels"),
        translate_y=pick("translate_y_pixels"),
        shear_q16=pick("shear_q16"),
        gain_q16=gain,
        offset=offset,
        blur_radius=pick("blur_radius_pixels"),
        mask_count=mask_count,
        mask_opacity_q16=pick("mask_opacity_q16") if mask_count else 0,
        mask_value=pick("mask_value_u8") if mask_count else 255,
        glare_opacity_q16=glare,
        seed_sha256=seed.hex(),
    )


def _clamp(value: int) -> int:
    return 0 if value < 0 else 255 if value > 255 else value


def _round_div(numerator: int, denominator: int) -> int:
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    if numerator >= 0:
        return (numerator + denominator // 2) // denominator
    return -((-numerator + denominator // 2) // denominator)


def _translate_shear(image: GrayImage, dx: int, dy: int, shear_q16: int) -> GrayImage:
    out = bytearray([255]) * len(image.pixels)
    center = image.height // 2
    for y in range(image.height):
        row_shift = dx + ((y - center) * shear_q16 // Q16)
        source_y = y - dy
        if not 0 <= source_y < image.height:
            continue
        for x in range(image.width):
            source_x = x - row_shift
            if 0 <= source_x < image.width:
                out[y * image.width + x] = image.pixels[source_y * image.width + source_x]
    return GrayImage(image.width, image.height, bytes(out))


def _tone(image: GrayImage, gain_q16: int, offset: int) -> GrayImage:
    pixels = bytes(_clamp((value * gain_q16 + Q16 // 2) // Q16 + offset) for value in image.pixels)
    return GrayImage(image.width, image.height, pixels)


def _box_blur(image: GrayImage, radius: int) -> GrayImage:
    if radius == 0:
        return image
    if radius < 0:
        raise ValueError("blur radius must be non-negative")
    width, height = image.width, image.height
    # A separable rolling sum preserves the former single-rounding 2-D box
    # result: horizontal sums are retained as integers, vertical sums divide
    # once by the exact clipped rectangle area. Runtime is O(width * height)
    # for every radius and the intermediate uses four bytes per pixel.
    horizontal = array("I", [0]) * (width * height)
    horizontal_counts = [0] * width
    for x in range(width):
        horizontal_counts[x] = min(width - 1, x + radius) - max(0, x - radius) + 1
    for y in range(height):
        row = y * width
        right = min(width - 1, radius)
        running = sum(image.pixels[row : row + right + 1])
        for x in range(width):
            horizontal[row + x] = running
            leaving = x - radius
            entering = x + radius + 1
            if leaving >= 0:
                running -= image.pixels[row + leaving]
            if entering < width:
                running += image.pixels[row + entering]

    out = bytearray(width * height)
    vertical_counts = [
        min(height - 1, y + radius) - max(0, y - radius) + 1
        for y in range(height)
    ]
    for x in range(width):
        bottom = min(height - 1, radius)
        running = sum(horizontal[y * width + x] for y in range(bottom + 1))
        horizontal_count = horizontal_counts[x]
        for y in range(height):
            count = horizontal_count * vertical_counts[y]
            out[y * width + x] = (running + count // 2) // count
            leaving = y - radius
            entering = y + radius + 1
            if leaving >= 0:
                running -= horizontal[leaving * width + x]
            if entering < height:
                running += horizontal[entering * width + x]
    return GrayImage(width, height, bytes(out))


def _blend(out: bytearray, index: int, value: int, alpha_q16: int) -> None:
    old = out[index]
    out[index] = _clamp((old * (Q16 - alpha_q16) + value * alpha_q16 + Q16 // 2) // Q16)


def _footer_bounds(width: int, height: int) -> Tuple[int, int, int, int]:
    # Exact QK-DEC-094 F rectangle mapped to pixels. Lower bounds are floor;
    # upper bounds are ceil, yielding a lower-inclusive/upper-exclusive box.
    x0 = 16 * width // 210
    x1 = (1_176_165 * width + 2_100_000 - 1) // 2_100_000
    y0 = 27_412 * height // 29_700
    y1 = (281 * height + 297 - 1) // 297
    return x0, max(x0 + 1, min(width, x1)), y0, max(y0 + 1, min(height, y1))


def _challenge_point(width: int, height: int) -> Tuple[int, int]:
    return 67 * width // 210, 555 * height // 594


def _operator_rng(params: SampleParameters, label: bytes) -> CounterRng:
    seed = bytes.fromhex(params.seed_sha256)
    return CounterRng(hashlib.sha256(label + b"\x00" + seed).digest())


def _draw_line(
    out: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    value: int,
    alpha_q16: int,
    thickness: int = 1,
) -> None:
    dx, sx = abs(x1 - x0), 1 if x0 < x1 else -1
    dy, sy = -abs(y1 - y0), 1 if y0 < y1 else -1
    error = dx + dy
    radius = max(0, thickness - 1) // 2
    while True:
        for yy in range(max(0, y0 - radius), min(height, y0 + radius + 1)):
            for xx in range(max(0, x0 - radius), min(width, x0 + radius + 1)):
                _blend(out, yy * width + xx, value, alpha_q16)
        if x0 == x1 and y0 == y1:
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x0 += sx
        if twice <= dx:
            error += dx
            y0 += sy


def _ellipse(
    out: bytearray,
    width: int,
    height: int,
    cx: int,
    cy: int,
    rx: int,
    ry: int,
    value: int,
    alpha_q16: int,
    ring: bool,
) -> None:
    rx, ry = max(1, rx), max(1, ry)
    outer = rx * rx * ry * ry
    inner_rx, inner_ry = max(1, rx - max(1, rx // 10)), max(1, ry - max(1, ry // 10))
    inner = inner_rx * inner_rx * inner_ry * inner_ry
    for y in range(max(0, cy - ry), min(height, cy + ry + 1)):
        for x in range(max(0, cx - rx), min(width, cx + rx + 1)):
            dx, dy = x - cx, y - cy
            scaled_outer = dx * dx * ry * ry + dy * dy * rx * rx
            if scaled_outer > outer:
                continue
            if ring:
                scaled_inner = dx * dx * inner_ry * inner_ry + dy * dy * inner_rx * inner_rx
                if scaled_inner < inner:
                    continue
            _blend(out, y * width + x, value, alpha_q16)


def _coffee(image: GrayImage, params: SampleParameters) -> GrayImage:
    out = bytearray(image.pixels)
    rng = _operator_rng(params, b"coffee")
    base_x, base_y = _challenge_point(image.width, image.height)
    for _ in range(params.mask_count):
        cx = base_x + rng.integer(-max(1, image.width // 100), max(1, image.width // 100))
        cy = base_y + rng.integer(-max(1, image.height // 300), max(1, image.height // 300))
        rx = max(2, 75 * image.width // 420 + rng.integer(-2, 2))
        ry = max(2, 75 * image.height // 594 + rng.integer(-2, 2))
        _ellipse(out, image.width, image.height, cx, cy, rx, ry, min(params.mask_value, 150), params.mask_opacity_q16, True)
    return GrayImage(image.width, image.height, bytes(out))


def _water(image: GrayImage, params: SampleParameters) -> GrayImage:
    out = bytearray(image.pixels)
    rng = _operator_rng(params, b"water")
    cx, cy = _challenge_point(image.width, image.height)
    radii_mm = (0, 7, 11, 16)
    radius = radii_mm[params.severity]
    rx = max(1, radius * image.width // 210 + rng.integer(0, 2))
    ry = max(1, radius * image.height // 297 + rng.integer(0, 2))
    _ellipse(out, image.width, image.height, cx, cy, rx, ry, max(params.mask_value, 190), params.mask_opacity_q16, False)
    return GrayImage(image.width, image.height, bytes(out))


def _triangle_wave(position: int, period: int, amplitude: int) -> int:
    period = max(2, period)
    phase = position % period
    half = max(1, period // 2)
    rising = phase if phase <= half else period - phase
    return ((2 * rising - half) * amplitude) // half


def _crumple(image: GrayImage, params: SampleParameters) -> GrayImage:
    amplitude = max(1, params.severity * min(image.width, image.height) // 180)
    period_x = max(4, image.width // (3 + params.severity))
    period_y = max(4, image.height // (4 + params.severity))
    warped = bytearray([255]) * len(image.pixels)
    for y in range(image.height):
        for x in range(image.width):
            sx = x + _triangle_wave(y, period_y, amplitude)
            sy = y + _triangle_wave(x, period_x, amplitude)
            if 0 <= sx < image.width and 0 <= sy < image.height:
                warped[y * image.width + x] = image.pixels[sy * image.width + sx]
    rng = _operator_rng(params, b"crumple")
    for index in range(params.mask_count):
        x0 = rng.integer(0, image.width - 1)
        x1 = rng.integer(0, image.width - 1)
        value = 235 if index % 2 == 0 else 80
        _draw_line(warped, image.width, image.height, x0, 0, x1, image.height - 1, value, params.mask_opacity_q16, 1)
    return GrayImage(image.width, image.height, bytes(warped))


def _edge(image: GrayImage, params: SampleParameters) -> GrayImage:
    out = bytearray(image.pixels)
    center_x, _ = _challenge_point(image.width, image.height)
    half_width = max(1, 10 * image.width // 210)
    depth_mm = (0, 17, 22, 27)[params.severity]
    depth = max(1, depth_mm * image.height // 297)
    for y in range(max(0, image.height - depth), image.height):
        for x in range(max(0, center_x - half_width), min(image.width, center_x + half_width + 1)):
            out[y * image.width + x] = 255
    return GrayImage(image.width, image.height, bytes(out))


def _fade(image: GrayImage, params: SampleParameters) -> GrayImage:
    out = bytearray(image.pixels)
    x0, x1, y0, y1 = _footer_bounds(image.width, image.height)
    alpha = (0, 8_192, 18_432, 32_768)[params.severity]
    for y in range(y0, y1):
        for x in range(x0, x1):
            _blend(out, y * image.width + x, 255, alpha)
    rng = _operator_rng(params, b"fade")
    for _ in range(params.mask_count):
        y = rng.integer(y0, y1 - 1)
        _draw_line(out, image.width, image.height, x0, y, x1 - 1, y, 255, min(Q16, alpha + 8192), 1)
    return GrayImage(image.width, image.height, bytes(out))


def _fold(image: GrayImage, params: SampleParameters) -> GrayImage:
    out = bytearray(image.pixels)
    x, _ = _challenge_point(image.width, image.height)
    width = max(1, params.severity * image.width // 420)
    alpha = (0, 16_384, 28_672, 40_960)[params.severity]
    for offset in range(-width, width + 1):
        value = 255 if offset <= 0 else 64
        _draw_line(out, image.width, image.height, x + offset, 0, x + offset, image.height - 1, value, alpha, 1)
    return GrayImage(image.width, image.height, bytes(out))


def _scratch(image: GrayImage, params: SampleParameters) -> GrayImage:
    out = bytearray(image.pixels)
    x0, x1, y0, y1 = _footer_bounds(image.width, image.height)
    rng = _operator_rng(params, b"scratch")
    for index in range(params.mask_count):
        if params.severity == 3 and index >= 3:
            x = x0 + (index - 2) * max(1, (x1 - x0) // 4)
            _draw_line(out, image.width, image.height, x, y0, x, y1 - 1, 255, params.mask_opacity_q16, 1)
        else:
            y = rng.integer(y0, y1 - 1)
            _draw_line(out, image.width, image.height, x0, y, x1 - 1, y, 255, params.mask_opacity_q16, 1)
    return GrayImage(image.width, image.height, bytes(out))


def _scuff(image: GrayImage, params: SampleParameters) -> GrayImage:
    out = bytearray(image.pixels)
    for start, y, end in _scuff_segments(image, params):
        _draw_line(out, image.width, image.height, start, y, end, y, 245, params.mask_opacity_q16, 1)
    return GrayImage(image.width, image.height, bytes(out))


def _scuff_segments(image: GrayImage, params: SampleParameters) -> Tuple[Tuple[int, int, int], ...]:
    """Return exact left-to-right 40 mm scuff strokes wholly inside F.

    Page millimetres map to raster coordinates with half-up rounding. The
    start is sampled only from the interval that can contain the complete
    stroke, so no right-edge clipping or shortened pass is possible.
    """
    x0, x1, y0, y1 = _footer_bounds(image.width, image.height)
    stroke = max(1, (40 * image.width + 105) // 210)
    last_start = x1 - 1 - stroke
    if last_start < x0:
        raise ValueError("image is too narrow for a 40 mm scuff stroke inside F")
    rng = _operator_rng(params, b"scuff")
    segments = []
    for _ in range(params.mask_count):
        start = rng.integer(x0, last_start)
        y = rng.integer(y0, y1 - 1)
        segments.append((start, y, start + stroke))
    return tuple(segments)


def _locate_forward_point(width: int, height: int, x: int, y: int) -> Tuple[int, int]:
    """Map one source pixel to the frozen locate-1 quadrilateral in Q16."""
    center_x_q16 = (width - 1) * Q16 // 2
    center_y_q16 = (height - 1) * Q16 // 2
    local_x_q16 = x * Q16 - center_x_q16
    local_y_q16 = y * Q16 - center_y_q16
    vertical_q16 = _round_div(local_y_q16, max(1, height - 1))
    perspective_q16 = Q16 + _round_div(LOCATE_DEPTH_Q16 * vertical_q16, Q16)
    projected_x_q16 = _round_div(local_x_q16 * LOCATE_PAGE_SCALE_Q16, perspective_q16)
    projected_y_q16 = _round_div(local_y_q16 * LOCATE_PAGE_SCALE_Q16, Q16)
    projected_y_q16 = _round_div(projected_y_q16 * COS_20_Q16, Q16)
    projected_y_q16 = _round_div(projected_y_q16 * Q16, perspective_q16)
    rolled_x_q16 = _round_div(
        COS_15_Q16 * projected_x_q16 - SIN_15_Q16 * projected_y_q16,
        Q16,
    )
    rolled_y_q16 = _round_div(
        SIN_15_Q16 * projected_x_q16 + COS_15_Q16 * projected_y_q16,
        Q16,
    )
    return center_x_q16 + rolled_x_q16, center_y_q16 + rolled_y_q16


def _locate_page_corners(width: int, height: int) -> Tuple[Tuple[int, int], ...]:
    """Return ordered Q16 pixel coordinates for the locate-1 page corners."""
    return tuple(
        _locate_forward_point(width, height, x, y)
        for x, y in ((0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1))
    )


def _locate_geometry(image: GrayImage, params: SampleParameters) -> GrayImage:
    if params.severity == 0:
        return image
    width, height = image.width, image.height
    corners = _locate_page_corners(width, height)
    if any(
        x < 0 or x > (width - 1) * Q16 or y < 0 or y > (height - 1) * Q16
        for x, y in corners
    ):
        raise AssertionError("locate-1 page corner escaped the frame")

    center_x_q16 = (width - 1) * Q16 // 2
    center_y_q16 = (height - 1) * Q16 // 2
    min_x = max(0, min(x for x, _ in corners) // Q16 - 1)
    max_x = min(width - 1, (max(x for x, _ in corners) + Q16 - 1) // Q16 + 1)
    min_y = max(0, min(y for _, y in corners) // Q16 - 1)
    max_y = min(height - 1, (max(y for _, y in corners) + Q16 - 1) // Q16 + 1)
    scale_cos_q16 = _round_div(LOCATE_PAGE_SCALE_Q16 * COS_20_Q16, Q16)
    out = bytearray([255]) * len(image.pixels)
    for y in range(min_y, max_y + 1):
        output_y_q16 = y * Q16 - center_y_q16
        for x in range(min_x, max_x + 1):
            output_x_q16 = x * Q16 - center_x_q16
            # Undo the 15-degree roll, then analytically invert the fixed
            # 20-degree pinhole projection.
            projected_x_q16 = _round_div(
                COS_15_Q16 * output_x_q16 + SIN_15_Q16 * output_y_q16,
                Q16,
            )
            projected_y_q16 = _round_div(
                -SIN_15_Q16 * output_x_q16 + COS_15_Q16 * output_y_q16,
                Q16,
            )
            projected_vertical_q16 = _round_div(projected_y_q16, max(1, height - 1))
            inverse_denominator_q16 = scale_cos_q16 - _round_div(
                LOCATE_DEPTH_Q16 * projected_vertical_q16,
                Q16,
            )
            if inverse_denominator_q16 <= 0:
                continue
            source_vertical_q16 = _round_div(
                projected_vertical_q16 * Q16,
                inverse_denominator_q16,
            )
            perspective_q16 = Q16 + _round_div(
                LOCATE_DEPTH_Q16 * source_vertical_q16,
                Q16,
            )
            projected_horizontal_q16 = _round_div(projected_x_q16, max(1, width - 1))
            source_horizontal_q16 = _round_div(
                projected_horizontal_q16 * perspective_q16,
                LOCATE_PAGE_SCALE_Q16,
            )
            if not (
                -Q16 // 2 <= source_horizontal_q16 <= Q16 // 2
                and -Q16 // 2 <= source_vertical_q16 <= Q16 // 2
            ):
                continue
            source_x_q16 = center_x_q16 + source_horizontal_q16 * max(1, width - 1)
            source_y_q16 = center_y_q16 + source_vertical_q16 * max(1, height - 1)
            source_x = _round_div(source_x_q16, Q16)
            source_y = _round_div(source_y_q16, Q16)
            if 0 <= source_x < width and 0 <= source_y < height:
                out[y * width + x] = image.pixels[source_y * width + source_x]
    return GrayImage(width, height, bytes(out))


def _glare(image: GrayImage, params: SampleParameters) -> GrayImage:
    if params.glare_opacity_q16 == 0:
        return image
    out = bytearray(image.pixels)
    _, _, y0, y1 = _footer_bounds(image.width, image.height)
    center = (y0 + y1) // 2
    half_band = max(1, (y1 - y0) // 2)
    for x in range(image.width):
        band_y = center + (x - image.width // 2) * max(1, y1 - y0) // max(1, image.width)
        for y in range(max(0, band_y - half_band), min(image.height, band_y + half_band + 1)):
            _blend(out, y * image.width + x, 255, params.glare_opacity_q16)
    return GrayImage(image.width, image.height, bytes(out))


def apply_model(image: GrayImage, params: SampleParameters) -> GrayImage:
    transformed = _locate_geometry(image, params) if params.damage_class == "locate" else image
    transformed = _translate_shear(transformed, params.translate_x, params.translate_y, params.shear_q16)
    transformed = _tone(transformed, params.gain_q16, params.offset)
    transformed = _box_blur(transformed, params.blur_radius)
    operators = {
        "baseline": lambda current, _: current,
        "coffee": _coffee,
        "water": _water,
        "crumple": _crumple,
        "edge": _edge,
        "fade": _fade,
        "fold": _fold,
        "scratch": _scratch,
        "scuff": _scuff,
        "locate": lambda current, _: current,
    }
    transformed = operators[params.damage_class](transformed, params)
    return _glare(transformed, params)


def _quantile(values: Sequence[int], numerator: int, denominator: int) -> int:
    if not values:
        raise ValueError("quantile requires at least one value")
    ordered = sorted(values)
    index = (len(ordered) - 1) * numerator // denominator
    return ordered[index]


def _centroid_q16(indices: Sequence[int], width: int, height: int) -> Tuple[int, int]:
    if not indices:
        return -1, -1
    count = len(indices)
    sum_x = sum(index % width for index in indices)
    sum_y = sum(index // width for index in indices)
    x_denominator = count * max(1, width - 1)
    y_denominator = count * max(1, height - 1)
    return (
        (sum_x * Q16 + x_denominator // 2) // x_denominator,
        (sum_y * Q16 + y_denominator // 2) // y_denominator,
    )


def _mask_centroid_q16(mask: bytes, width: int, height: int) -> Tuple[Tuple[int, int], int]:
    count = 0
    sum_x = 0
    sum_y = 0
    for index, value in enumerate(mask):
        if value:
            count += 1
            sum_x += index % width
            sum_y += index // width
    if count == 0:
        return (-1, -1), 0
    x_denominator = count * max(1, width - 1)
    y_denominator = count * max(1, height - 1)
    return (
        (sum_x * Q16 + x_denominator // 2) // x_denominator,
        (sum_y * Q16 + y_denominator // 2) // y_denominator,
    ), count


def _component_metrics(mask: bytes, width: int, height: int) -> Tuple[int, int]:
    visited = bytearray(len(mask))
    components = 0
    largest = 0
    total = sum(1 for value in mask if value)
    if total == 0:
        return 0, 0
    for start, value in enumerate(mask):
        if not value or visited[start]:
            continue
        components += 1
        visited[start] = 1
        queue = deque([start])
        size = 0
        while queue:
            index = queue.popleft()
            size += 1
            x, y = index % width, index // width
            if x > 0:
                neighbor = index - 1
                if mask[neighbor] and not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if x + 1 < width:
                neighbor = index + 1
                if mask[neighbor] and not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if y > 0:
                neighbor = index - width
                if mask[neighbor] and not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if y + 1 < height:
                neighbor = index + width
                if mask[neighbor] and not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
        largest = max(largest, size)
    return components, (largest * Q16 + total // 2) // total


def _diagonal_distance_q16(first: Tuple[int, int], second: Tuple[int, int]) -> int:
    dx, dy = first[0] - second[0], first[1] - second[1]
    distance = isqrt(dx * dx + dy * dy)
    diagonal = isqrt(2 * Q16 * Q16)
    return (distance * Q16 + diagonal // 2) // diagonal


def compute_metrics(
    clean: GrayImage,
    observed: GrayImage,
    corners_q16: Sequence[Tuple[int, int]] = (),
    config: Optional[Mapping[str, object]] = None,
) -> MetricVector:
    """Compute the six frozen metric families without reading any file path.

    Images must already be in the same deterministic page coordinate system.
    Geometry corners are supplied by the future rig/rectification record in
    top-left, top-right, bottom-right, bottom-left order. Omission means exact
    expected page corners and is useful only for synthetic/unit inputs.
    """
    if (clean.width, clean.height) != (observed.width, observed.height):
        raise ValueError("metric images must have identical dimensions")
    active_config = config if config is not None else load_draft()
    validate_draft(active_config)
    contract = active_config["validation"]["metric_contract"]
    difference_threshold = contract["difference_threshold_u8"]
    glare_threshold = contract["glare_threshold_u8"]
    edge_threshold = contract["edge_threshold_u8"]
    width, height = clean.width, clean.height
    expected_corners = ((0, 0), (Q16, 0), (Q16, Q16), (0, Q16))
    actual_corners = tuple(corners_q16) if corners_q16 else expected_corners
    if len(actual_corners) != 4:
        raise ValueError("exactly four ordered geometry corners are required")
    corner_distances = [
        _diagonal_distance_q16(actual, expected)
        for actual, expected in zip(actual_corners, expected_corners)
    ]
    geometry_rms = isqrt(sum(value * value for value in corner_distances) // 4)
    geometry_max = max(corner_distances)

    mask = bytes(
        1 if abs(observed_value - clean_value) >= difference_threshold else 0
        for clean_value, observed_value in zip(clean.pixels, observed.pixels)
    )
    damage_centroid, damage_count = _mask_centroid_q16(mask, width, height)
    x0, x1, y0, y1 = _footer_bounds(width, height)
    footer_indices = [y * width + x for y in range(y0, y1) for x in range(x0, x1)]
    footer_overlap_count = sum(mask[index] for index in footer_indices)
    footer_overlap = (
        (footer_overlap_count * Q16 + damage_count // 2) // damage_count
        if damage_count
        else 0
    )
    component_count, largest_fraction = _component_metrics(mask, width, height)

    footer_values = [observed.pixels[index] for index in footer_indices]
    luminance_median = _quantile(footer_values, 1, 2)
    p05 = _quantile(footer_values, 5, 100)
    p25 = _quantile(footer_values, 1, 4)
    p75 = _quantile(footer_values, 3, 4)
    p95 = _quantile(footer_values, 95, 100)
    contrast_iqr = p75 - p25

    gradients: List[int] = []
    for y in range(y0, y1):
        for x in range(x0, x1):
            index = y * width + x
            if x + 1 < x1:
                gradients.append(abs(observed.pixels[index + 1] - observed.pixels[index]))
            if y + 1 < y1:
                gradients.append(abs(observed.pixels[index + width] - observed.pixels[index]))
    edge_sum = sum(gradients)
    edge_energy = (
        (edge_sum * Q16 + len(gradients) * 255 // 2) // (len(gradients) * 255)
        if gradients
        else 0
    )
    high_edge_fraction = (
        (sum(value >= edge_threshold for value in gradients) * Q16 + len(gradients) // 2)
        // len(gradients)
        if gradients
        else 0
    )

    glare_indices = [
        index
        for index in footer_indices
        if observed.pixels[index] >= glare_threshold
        and observed.pixels[index] - clean.pixels[index] >= difference_threshold
    ]
    glare_coverage = (
        (len(glare_indices) * Q16 + len(footer_indices) // 2) // len(footer_indices)
        if footer_indices
        else 0
    )
    glare_centroid = _centroid_q16(glare_indices, width, height)
    return MetricVector(
        geometry_corner_rms_q16=geometry_rms,
        geometry_corner_max_q16=geometry_max,
        damage_centroid_x_q16=damage_centroid[0],
        damage_centroid_y_q16=damage_centroid[1],
        footer_overlap_q16=footer_overlap,
        component_count=component_count,
        largest_component_fraction_q16=largest_fraction,
        luminance_median_u8=luminance_median,
        contrast_iqr_u8=contrast_iqr,
        luminance_p05_u8=p05,
        luminance_p95_u8=p95,
        edge_energy_q16=edge_energy,
        high_edge_fraction_q16=high_edge_fraction,
        glare_coverage_q16=glare_coverage,
        glare_centroid_x_q16=glare_centroid[0],
        glare_centroid_y_q16=glare_centroid[1],
    )


def aggregate_synthetic_metrics(values: Sequence[MetricVector]) -> MetricVector:
    if len(values) != 3:
        raise ValueError("synthetic center requires exactly three realizations")
    fields = MetricVector.__dataclass_fields__
    return MetricVector(
        **{
            name: sorted(getattr(value, name) for value in values)[1]
            for name in fields
        }
    )


def _presence_pair(x: int, y: int) -> Tuple[bool, bool]:
    return x >= 0, y >= 0


def validate_cell_metrics(
    cell: str,
    anchor: MetricVector,
    synthetic_realizations: Sequence[MetricVector],
    config: Optional[Mapping[str, object]] = None,
) -> Tuple[str, ...]:
    active_config = config if config is not None else load_draft()
    validate_draft(active_config)
    if cell not in {row[0] for row in CELLS}:
        raise ValueError("unknown cell")
    center = aggregate_synthetic_metrics(synthetic_realizations)
    criteria = active_config["validation"]["criteria_profiles"]["candidate-shared-v1"]
    failures: List[str] = []

    geometry = criteria["geometry"]
    if abs(center.geometry_corner_rms_q16 - anchor.geometry_corner_rms_q16) > geometry["corner_rms_page_diagonal_q16_max"]:
        failures.append("GeometryCornerRms")
    if abs(center.geometry_corner_max_q16 - anchor.geometry_corner_max_q16) > geometry["corner_max_page_diagonal_q16_max"]:
        failures.append("GeometryCornerMax")

    placement = criteria["damage_mask_placement_and_footer_overlap"]
    anchor_damage_presence = _presence_pair(anchor.damage_centroid_x_q16, anchor.damage_centroid_y_q16)
    center_damage_presence = _presence_pair(center.damage_centroid_x_q16, center.damage_centroid_y_q16)
    if anchor_damage_presence != center_damage_presence:
        failures.append("DamageMaskPresenceMismatch")
    elif anchor_damage_presence == (True, True):
        distance = _diagonal_distance_q16(
            (anchor.damage_centroid_x_q16, anchor.damage_centroid_y_q16),
            (center.damage_centroid_x_q16, center.damage_centroid_y_q16),
        )
        if distance > placement["centroid_distance_page_diagonal_q16_max"]:
            failures.append("DamageMaskPlacement")
    if abs(center.footer_overlap_q16 - anchor.footer_overlap_q16) > placement["footer_overlap_abs_delta_q16_max"]:
        failures.append("FooterOverlap")

    connectedness = criteria["connectedness"]
    if abs(center.component_count - anchor.component_count) > connectedness["component_count_abs_delta_max"]:
        failures.append("ConnectedComponentCount")
    if abs(center.largest_component_fraction_q16 - anchor.largest_component_fraction_q16) > connectedness["largest_component_fraction_abs_delta_q16_max"]:
        failures.append("LargestComponentFraction")

    tone = criteria["contrast_and_luminance"]
    if abs(center.luminance_median_u8 - anchor.luminance_median_u8) > tone["luminance_median_abs_delta_u8_max"]:
        failures.append("LuminanceMedian")
    if abs(center.contrast_iqr_u8 - anchor.contrast_iqr_u8) > tone["contrast_iqr_abs_delta_u8_max"]:
        failures.append("ContrastIqr")
    if max(
        abs(center.luminance_p05_u8 - anchor.luminance_p05_u8),
        abs(center.luminance_p95_u8 - anchor.luminance_p95_u8),
    ) > tone["tail_percentile_abs_delta_u8_max"]:
        failures.append("LuminanceTail")

    blur = criteria["blur_and_edge_spectrum"]
    if anchor.edge_energy_q16 == 0:
        if center.edge_energy_q16 != 0:
            failures.append("EdgeEnergyZeroMismatch")
    else:
        ratio = (center.edge_energy_q16 * Q16 + anchor.edge_energy_q16 // 2) // anchor.edge_energy_q16
        if not blur["edge_energy_ratio_min_q16"] <= ratio <= blur["edge_energy_ratio_max_q16"]:
            failures.append("EdgeEnergyRatio")
    if abs(center.high_edge_fraction_q16 - anchor.high_edge_fraction_q16) > blur["high_edge_fraction_abs_delta_q16_max"]:
        failures.append("HighEdgeFraction")

    glare = criteria["glare"]
    anchor_glare_presence = _presence_pair(anchor.glare_centroid_x_q16, anchor.glare_centroid_y_q16)
    center_glare_presence = _presence_pair(center.glare_centroid_x_q16, center.glare_centroid_y_q16)
    if anchor_glare_presence != center_glare_presence:
        failures.append("GlarePresenceMismatch")
    elif anchor_glare_presence == (True, True):
        distance = _diagonal_distance_q16(
            (anchor.glare_centroid_x_q16, anchor.glare_centroid_y_q16),
            (center.glare_centroid_x_q16, center.glare_centroid_y_q16),
        )
        if distance > glare["specular_centroid_page_diagonal_q16_max"]:
            failures.append("GlareCentroid")
    if abs(center.glare_coverage_q16 - anchor.glare_coverage_q16) > glare["footer_specular_overlap_abs_delta_q16_max"]:
        failures.append("GlareCoverage")
    return tuple(failures)


def require_active_registration(path: Path = ACTIVE_PATH) -> dict:
    if path.resolve() != ACTIVE_PATH.resolve():
        raise ModelFreezeRequired("activation path is not the compiled canonical path")
    if (
        EXPECTED_ACTIVE_REGISTRATION_SHA256 is None
        or EXPECTED_OWNER_DECISION_ID is None
        or EXPECTED_DECISION_LOG_COMMIT is None
    ):
        raise ModelFreezeRequired("this build has no compiled Owner authority binding")
    if not path.exists():
        raise ModelFreezeRequired("active Owner-ratified model-freeze registration is absent")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED_ACTIVE_REGISTRATION_SHA256:
        raise ModelFreezeRequired("activation file does not match the compiled digest")
    value = json.loads(data.decode("ascii"))
    if set(value) != {"schema", "status", "authority", "bindings", "scope"}:
        raise ModelFreezeRequired("activation field set mismatch")
    if value["schema"] != "QK-M19R-MODEL-FREEZE-ACTIVATION-V1":
        raise ModelFreezeRequired("activation schema mismatch")
    if value["status"] != "ACTIVE_OWNER_RATIFIED":
        raise ModelFreezeRequired("model-freeze registration is not active")
    authority = value["authority"]
    if authority != {
        "owner_decision_id": EXPECTED_OWNER_DECISION_ID,
        "parent_decision_id": "QK-DEC-103",
        "decision_log_commit": EXPECTED_DECISION_LOG_COMMIT,
    }:
        raise ModelFreezeRequired("activation authority binding mismatch")
    bindings = value["bindings"]
    if set(bindings) != {
        "draft_sha256",
        "implementation_sha256",
        "clean_render_manifest_sha256",
        "payload_registry_sha256",
    }:
        raise ModelFreezeRequired("activation binding field set mismatch")
    if bindings.get("draft_sha256") != sha256_file(DRAFT_PATH):
        raise ModelFreezeRequired("activation does not bind this exact draft")
    if bindings.get("implementation_sha256") != sha256_file(Path(__file__)):
        raise ModelFreezeRequired("activation does not bind this implementation")
    if bindings.get("clean_render_manifest_sha256") != sha256_file(HERE / "generated" / "CLEAN-RENDERS.json"):
        raise ModelFreezeRequired("activation does not bind the clean renders")
    if bindings.get("payload_registry_sha256") != sha256_file(PAYLOADS_PATH):
        raise ModelFreezeRequired("activation does not bind the payload registry")
    if value["scope"] != {
        "comparison_image_generation": True,
        "fresh_anchor_decode": False,
        "scoring": False,
    }:
        raise ModelFreezeRequired("activation scope mismatch")
    return value


def generate_comparison() -> None:
    require_active_registration()
    raise ModelFreezeRequired(
        "comparison writer intentionally absent; add it only in the later activation change"
    )


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate-draft")
    sub.add_parser("plan")
    sub.add_parser("generate-comparison")
    args = parser.parse_args(list(argv) if argv else None)
    try:
        config = load_draft()
        if args.command == "validate-draft":
            print("status={}".format(config["status"]))
            print("cells={}".format(len(config["validation"]["per_cell"])))
            print("comparison_generation=DISABLED")
            return 0
        if args.command == "plan":
            plan = comparison_plan()
            print("planned_images={}".format(len(plan)))
            print("plan_sha256={}".format(plan_sha256(plan)))
            print("generated_images=0")
            return 0
        generate_comparison()
    except (ConfigurationError, ModelFreezeRequired) as exc:
        print("REFUSED: {}".format(exc), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
