"""Hashed, immutable Reader v0.2 development-profile contract."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .constants import ALPHABET

_FIELDS = frozenset(
    {
        "profile_format_version",
        "reader_version",
        "status",
        "confidence_floor",
        "margin_floor",
        "locator_id",
        "locator_sha256",
        "classifier_id",
        "classifier_sha256",
        "clean_render_corpus_id",
        "clean_render_source_commit",
        "clean_render_manifest_sha256",
        "training_corpus_id",
        "training_corpus_source_commit",
        "training_corpus_manifest_sha256",
        "training_partition_id",
        "training_partition_sha256",
        "reader_implementation_state",
        "reader_implementation_sha256",
        "alphabet",
    }
)
_STATUS = "DEVELOPMENT / NOT FOR SCORING"
_IMPLEMENTATION_STATE = "PENDING_BEFORE_SCORING"


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate profile field: {key}")
        result[key] = value
    return result


def _lower_hex(value: Any, width: int, field: str) -> str:
    if not isinstance(value, str) or len(value) != width:
        raise ValueError(f"{field} must be {width} lowercase hex characters")
    if any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{field} must be {width} lowercase hex characters")
    return value


@dataclass(frozen=True)
class ReaderProfile:
    raw_sha256: str
    confidence_floor: float
    margin_floor: float
    locator_id: str
    locator_sha256: str
    classifier_id: str
    classifier_sha256: str
    clean_render_corpus_id: str
    clean_render_source_commit: str
    clean_render_manifest_sha256: str
    training_corpus_id: str
    training_corpus_source_commit: str
    training_corpus_manifest_sha256: str
    training_partition_id: str
    training_partition_sha256: str
    reader_implementation_state: str
    reader_implementation_sha256: str

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "ReaderProfile":
        if type(raw) is not bytes or not raw:
            raise ValueError("profile must be non-empty immutable bytes")
        try:
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("profile must be UTF-8 JSON") from exc
        if not isinstance(data, dict) or frozenset(data) != _FIELDS:
            raise ValueError("profile fields must match the frozen schema exactly")
        if data["profile_format_version"] != 1:
            raise ValueError("unsupported profile format")
        if data["reader_version"] != "0.2":
            raise ValueError("profile is not for Reader v0.2")
        if data["status"] != _STATUS:
            raise ValueError("profile must remain development-only")
        if data["reader_implementation_state"] != _IMPLEMENTATION_STATE:
            raise ValueError("implementation state must remain pending before scoring")
        if data["alphabet"] != ALPHABET:
            raise ValueError("profile alphabet does not match QK-DEC-090")
        confidence = data["confidence_floor"]
        margin = data["margin_floor"]
        if type(confidence) not in {int, float} or not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence_floor must be in [0,1]")
        if type(margin) not in {int, float} or not 0.0 <= margin <= 1.0:
            raise ValueError("margin_floor must be in [0,1]")
        text_fields = (
            "locator_id",
            "classifier_id",
            "clean_render_corpus_id",
            "training_corpus_id",
            "training_partition_id",
        )
        if any(
            not isinstance(data[field], str)
            or not data[field]
            or data[field].strip() != data[field]
            for field in text_fields
        ):
            raise ValueError("profile identifiers must be non-empty strings")
        return cls(
            raw_sha256=hashlib.sha256(raw).hexdigest(),
            confidence_floor=float(confidence),
            margin_floor=float(margin),
            locator_id=data["locator_id"],
            locator_sha256=_lower_hex(data["locator_sha256"], 64, "locator_sha256"),
            classifier_id=data["classifier_id"],
            classifier_sha256=_lower_hex(
                data["classifier_sha256"], 64, "classifier_sha256"
            ),
            clean_render_corpus_id=data["clean_render_corpus_id"],
            clean_render_source_commit=_lower_hex(
                data["clean_render_source_commit"], 40, "clean_render_source_commit"
            ),
            clean_render_manifest_sha256=_lower_hex(
                data["clean_render_manifest_sha256"], 64, "clean_render_manifest_sha256"
            ),
            training_corpus_id=data["training_corpus_id"],
            training_corpus_source_commit=_lower_hex(
                data["training_corpus_source_commit"],
                40,
                "training_corpus_source_commit",
            ),
            training_corpus_manifest_sha256=_lower_hex(
                data["training_corpus_manifest_sha256"],
                64,
                "training_corpus_manifest_sha256",
            ),
            training_partition_id=data["training_partition_id"],
            training_partition_sha256=_lower_hex(
                data["training_partition_sha256"], 64, "training_partition_sha256"
            ),
            reader_implementation_state=data["reader_implementation_state"],
            reader_implementation_sha256=_lower_hex(
                data["reader_implementation_sha256"],
                64,
                "reader_implementation_sha256",
            ),
        )
