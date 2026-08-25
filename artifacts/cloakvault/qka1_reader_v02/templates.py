"""Deterministic synthetic-partition builder and template classifier."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .constants import ALPHABET
from .image import GrayImage
from .interfaces import ClassificationCandidate

_PARTITION_FIELDS = frozenset(
    {"format", "partition_id", "alphabet", "width", "height", "records"}
)
_RECORD_FIELDS = frozenset({"symbol", "variant", "pixels"})
_MODEL_FIELDS = frozenset(
    {
        "format",
        "artifact_id",
        "alphabet",
        "width",
        "height",
        "training_partition_id",
        "training_corpus_manifest_sha256",
        "training_partition_sha256",
        "templates",
    }
)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate template field: {key}")
        result[key] = value
    return result


def _canonical(data: dict[str, Any]) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _ink_scaled(pixels: bytes, numerator: int, denominator: int) -> bytes:
    return bytes(
        255 - min(255, ((255 - value) * numerator + denominator // 2) // denominator)
        for value in pixels
    )


def _shift(patch: GrayImage, dx: int) -> bytes:
    out = bytearray(b"\xff" * len(patch.pixels))
    for y in range(patch.height):
        for x in range(patch.width):
            source = x - dx
            if 0 <= source < patch.width:
                out[y * patch.width + x] = patch.pixels[y * patch.width + source]
    return bytes(out)


def build_synthetic_partition(
    partition_id: str,
    labels: str,
    patches: tuple[GrayImage, ...],
) -> bytes:
    """Build exact deterministic variants from public labelled glyph patches."""

    if (
        not isinstance(partition_id, str)
        or not partition_id
        or partition_id.strip() != partition_id
    ):
        raise ValueError("partition_id must be non-empty")
    if not isinstance(labels, str) or len(labels) != len(patches) or not patches:
        raise ValueError("labels and patches must be non-empty and aligned")
    if any(len(symbol) != 1 or symbol not in ALPHABET for symbol in labels):
        raise ValueError("partition label is outside the exact alphabet")
    width = patches[0].width
    height = patches[0].height
    if any(patch.width != width or patch.height != height for patch in patches):
        raise ValueError("all training patches must share exact dimensions")
    records = []
    for symbol, patch in zip(labels, patches):
        variants = (
            ("contrast-7of8", _ink_scaled(patch.pixels, 7, 8)),
            ("shift-left-1", _shift(patch, -1)),
            ("shift-right-1", _shift(patch, 1)),
        )
        for variant, pixels in variants:
            records.append(
                {"symbol": symbol, "variant": variant, "pixels": pixels.hex()}
            )
    return _canonical(
        {
            "format": "qka1-reader-synthetic-glyphs-v1",
            "partition_id": partition_id,
            "alphabet": ALPHABET,
            "width": width,
            "height": height,
            "records": records,
        }
    )


def _parse_partition(raw: bytes) -> tuple[str, int, int, list[tuple[str, bytes]]]:
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("synthetic partition must be UTF-8 JSON") from exc
    if not isinstance(data, dict) or frozenset(data) != _PARTITION_FIELDS:
        raise ValueError("synthetic partition fields must match the frozen schema")
    if data["format"] != "qka1-reader-synthetic-glyphs-v1":
        raise ValueError("unsupported synthetic partition format")
    if data["alphabet"] != ALPHABET:
        raise ValueError("synthetic partition alphabet mismatch")
    partition_id = data["partition_id"]
    width = data["width"]
    height = data["height"]
    if (
        not isinstance(partition_id, str)
        or not partition_id
        or partition_id.strip() != partition_id
    ):
        raise ValueError("partition_id must be non-empty")
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise ValueError("synthetic partition dimensions must be positive integers")
    raw_records = data["records"]
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("synthetic partition must contain records")
    records = []
    for record in raw_records:
        if not isinstance(record, dict) or frozenset(record) != _RECORD_FIELDS:
            raise ValueError("synthetic record fields must match the frozen schema")
        symbol = record["symbol"]
        variant = record["variant"]
        encoded = record["pixels"]
        if (
            not isinstance(symbol, str)
            or len(symbol) != 1
            or symbol not in ALPHABET
            or not isinstance(variant, str)
            or not variant
        ):
            raise ValueError("invalid synthetic record label")
        if not isinstance(encoded, str):
            raise ValueError("synthetic pixels must be lowercase hex")
        try:
            pixels = bytes.fromhex(encoded)
        except ValueError as exc:
            raise ValueError("synthetic pixels must be lowercase hex") from exc
        if encoded != pixels.hex() or len(pixels) != width * height:
            raise ValueError("synthetic pixel encoding or size mismatch")
        records.append((symbol, pixels))
    if set(symbol for symbol, _ in records) != set(ALPHABET):
        raise ValueError("synthetic partition must cover the exact alphabet")
    return partition_id, width, height, records


def train_template_model(
    artifact_id: str,
    partition_bytes: bytes,
    partition_manifest_sha256: str,
) -> bytes:
    """Average the preregistered deterministic variants into one template."""

    if (
        not isinstance(artifact_id, str)
        or not artifact_id
        or artifact_id.strip() != artifact_id
    ):
        raise ValueError("model artifact_id must be non-empty")
    if not isinstance(partition_bytes, bytes) or not partition_bytes:
        raise ValueError("synthetic partition must be non-empty immutable bytes")
    if (
        not isinstance(partition_manifest_sha256, str)
        or len(partition_manifest_sha256) != 64
        or any(char not in "0123456789abcdef" for char in partition_manifest_sha256)
    ):
        raise ValueError("partition manifest SHA-256 must be lowercase hex")
    partition_id, width, height, records = _parse_partition(partition_bytes)
    sums = {symbol: [0] * (width * height) for symbol in ALPHABET}
    counts = {symbol: 0 for symbol in ALPHABET}
    for symbol, pixels in records:
        counts[symbol] += 1
        for index, value in enumerate(pixels):
            sums[symbol][index] += value
    templates = {}
    for symbol in ALPHABET:
        count = counts[symbol]
        templates[symbol] = bytes(
            (value + count // 2) // count for value in sums[symbol]
        ).hex()
    return _canonical(
        {
            "format": "qka1-reader-template-model-v1",
            "artifact_id": artifact_id,
            "alphabet": ALPHABET,
            "width": width,
            "height": height,
            "training_partition_id": partition_id,
            "training_corpus_manifest_sha256": partition_manifest_sha256,
            "training_partition_sha256": hashlib.sha256(partition_bytes).hexdigest(),
            "templates": templates,
        }
    )


class TemplateClassifier:
    """One best template hypothesis; pipeline thresholds decide erasure."""

    def __init__(self, model_bytes: bytes) -> None:
        if type(model_bytes) is not bytes or not model_bytes:
            raise ValueError("template model must be immutable bytes")
        try:
            data = json.loads(
                model_bytes.decode("utf-8"), object_pairs_hook=_strict_object
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("template model must be UTF-8 JSON") from exc
        if not isinstance(data, dict) or frozenset(data) != _MODEL_FIELDS:
            raise ValueError("template model fields must match the frozen schema")
        if data["format"] != "qka1-reader-template-model-v1":
            raise ValueError("unsupported template model format")
        if data["alphabet"] != ALPHABET:
            raise ValueError("template model alphabet mismatch")
        artifact_id = data["artifact_id"]
        partition_id = data["training_partition_id"]
        partition_manifest = data["training_corpus_manifest_sha256"]
        partition_member = data["training_partition_sha256"]
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or artifact_id.strip() != artifact_id
        ):
            raise ValueError("template artifact_id must be non-empty")
        if (
            not isinstance(partition_id, str)
            or not partition_id
            or partition_id.strip() != partition_id
        ):
            raise ValueError("template training partition must be non-empty")
        for name, value in (
            ("manifest", partition_manifest),
            ("member", partition_member),
        ):
            if not isinstance(value, str) or len(value) != 64 or any(
                char not in "0123456789abcdef" for char in value
            ):
                raise ValueError(f"training partition {name} hash must be lowercase hex")
        width = data["width"]
        height = data["height"]
        if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
            raise ValueError("template dimensions must be positive integers")
        raw_templates = data["templates"]
        if not isinstance(raw_templates, dict) or set(raw_templates) != set(ALPHABET):
            raise ValueError("template model must cover the exact alphabet")
        templates = {}
        for symbol in ALPHABET:
            encoded = raw_templates[symbol]
            if not isinstance(encoded, str):
                raise ValueError("template pixels must be lowercase hex")
            try:
                pixels = bytes.fromhex(encoded)
            except ValueError as exc:
                raise ValueError("template pixels must be lowercase hex") from exc
            if encoded != pixels.hex() or len(pixels) != width * height:
                raise ValueError("template pixel encoding or size mismatch")
            templates[symbol] = pixels
        self.artifact_id = artifact_id
        self.artifact_sha256 = hashlib.sha256(model_bytes).hexdigest()
        self.training_partition_id = partition_id
        self.training_corpus_manifest_sha256 = partition_manifest
        self.training_partition_sha256 = partition_member
        self._width = width
        self._height = height
        self._templates = templates

    def classify(self, cell: GrayImage, position: int) -> ClassificationCandidate:
        if not isinstance(cell, GrayImage):
            raise ValueError("template classifier requires a grayscale glyph patch")
        if type(position) is not int or position < 0:
            raise ValueError("glyph position must be a non-negative integer")
        if cell.width != self._width or cell.height != self._height:
            raise ValueError("glyph patch dimensions differ from the bound model")
        scores = []
        for symbol in ALPHABET:
            template = self._templates[symbol]
            squared = sum(
                (actual - expected) * (actual - expected)
                for actual, expected in zip(cell.pixels, template)
            )
            mse = squared / len(template)
            scores.append((1.0 - mse / 65025.0, symbol))
        scores.sort(reverse=True)
        confidence, symbol = scores[0]
        margin = confidence - scores[1][0]
        if margin == 0.0:
            return ClassificationCandidate(None, max(0.0, confidence), 0.0)
        return ClassificationCandidate(symbol, max(0.0, confidence), max(0.0, margin))
