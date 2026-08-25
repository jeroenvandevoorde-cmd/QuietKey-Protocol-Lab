"""In-memory corpus and exact-member boundary for QK-DEC-104."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class CorpusPurpose(str, Enum):
    FROZEN_CLEAN_RENDER = "FROZEN_CLEAN_RENDER"
    PREREGISTERED_SYNTHETIC_TRAINING = "PREREGISTERED_SYNTHETIC_TRAINING"
    OLD_FORMAT_MORPHOLOGY_REFERENCE = "OLD_FORMAT_MORPHOLOGY_REFERENCE"
    FRESH_M19R_ANCHOR = "FRESH_M19R_ANCHOR"
    REAL_M19R_HOLDOUT = "REAL_M19R_HOLDOUT"


_ALLOWED = frozenset(
    {
        CorpusPurpose.FROZEN_CLEAN_RENDER,
        CorpusPurpose.PREREGISTERED_SYNTHETIC_TRAINING,
    }
)
_MANIFEST_FIELDS = frozenset(
    {"format", "corpus_id", "purpose", "source_commit", "members"}
)
_MEMBER_FIELDS = frozenset({"member_id", "byte_length", "sha256"})


class CorpusPolicyError(ValueError):
    pass


def _is_lower_hex(value: str, width: int) -> bool:
    return len(value) == width and all(c in "0123456789abcdef" for c in value)


def _object_without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CorpusPolicyError(f"duplicate manifest field: {key}")
        result[key] = value
    return result


@dataclass(frozen=True)
class FrameInput:
    """One exact in-memory manifest member supplied to the reader."""

    member_id: str
    data: bytes

    def __post_init__(self) -> None:
        if (
            not isinstance(self.member_id, str)
            or not self.member_id
            or self.member_id.strip() != self.member_id
        ):
            raise ValueError("member_id must be a non-empty exact identifier")
        if type(self.data) is not bytes or not self.data:
            raise ValueError("frame data must be non-empty immutable bytes")


@dataclass(frozen=True)
class CorpusMember:
    member_id: str
    byte_length: int
    sha256: str


@dataclass(frozen=True, init=False)
class CorpusDescriptor:
    """A parsed manifest whose exact input bytes are hashed.

    Construction accepts manifest bytes only. Corpus identity, purpose, source
    commit, and members therefore cannot be asserted separately from the
    profile-bound manifest hash.
    """

    def __init__(self, manifest_bytes: bytes) -> None:
        if type(manifest_bytes) is not bytes or not manifest_bytes:
            raise ValueError("manifest must be non-empty immutable bytes")
        try:
            data = json.loads(
                manifest_bytes.decode("utf-8"),
                object_pairs_hook=_object_without_duplicate_keys,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CorpusPolicyError("manifest must be UTF-8 JSON") from exc
        if not isinstance(data, dict) or frozenset(data) != _MANIFEST_FIELDS:
            raise CorpusPolicyError("manifest fields must match the frozen schema exactly")
        if data["format"] != "qka1-reader-corpus-v1":
            raise CorpusPolicyError("unsupported corpus manifest format")
        corpus_id = data["corpus_id"]
        if not isinstance(corpus_id, str) or not corpus_id or corpus_id.strip() != corpus_id:
            raise CorpusPolicyError("corpus_id must be a non-empty exact identifier")
        try:
            purpose = CorpusPurpose(data["purpose"])
        except (TypeError, ValueError) as exc:
            raise CorpusPolicyError("unknown corpus purpose") from exc
        source_commit = data["source_commit"]
        if not isinstance(source_commit, str) or not _is_lower_hex(source_commit, 40):
            raise CorpusPolicyError("source_commit must be 40 lowercase hex characters")
        raw_members = data["members"]
        if not isinstance(raw_members, list) or not raw_members:
            raise CorpusPolicyError("manifest must contain at least one member")
        members: dict[str, CorpusMember] = {}
        for raw in raw_members:
            if not isinstance(raw, dict) or frozenset(raw) != _MEMBER_FIELDS:
                raise CorpusPolicyError("member fields must match the frozen schema exactly")
            member_id = raw["member_id"]
            byte_length = raw["byte_length"]
            member_sha256 = raw["sha256"]
            if not isinstance(member_id, str) or not member_id or member_id.strip() != member_id:
                raise CorpusPolicyError("member_id must be a non-empty exact identifier")
            if member_id in members:
                raise CorpusPolicyError(f"duplicate manifest member: {member_id}")
            if type(byte_length) is not int or byte_length <= 0:
                raise CorpusPolicyError("member byte_length must be a positive integer")
            if not isinstance(member_sha256, str) or not _is_lower_hex(member_sha256, 64):
                raise CorpusPolicyError("member sha256 must be 64 lowercase hex characters")
            members[member_id] = CorpusMember(member_id, byte_length, member_sha256)

        object.__setattr__(self, "corpus_id", corpus_id)
        object.__setattr__(self, "purpose", purpose)
        object.__setattr__(self, "source_commit", source_commit)
        object.__setattr__(
            self, "manifest_sha256", hashlib.sha256(manifest_bytes).hexdigest()
        )
        object.__setattr__(self, "_members", tuple(members.values()))

    corpus_id: str
    purpose: CorpusPurpose
    source_commit: str
    manifest_sha256: str
    _members: tuple[CorpusMember, ...]

    def require_reader_use(self) -> None:
        if self.purpose not in _ALLOWED:
            raise CorpusPolicyError(
                f"{self.purpose.value} is unavailable to Reader v0.2 under QK-DEC-104"
            )

    def require_member(self, frame: FrameInput) -> str:
        """Bind exact member identity, byte count, and hash before image work."""

        if type(frame) is not FrameInput:
            raise CorpusPolicyError("reader input must be an exact FrameInput")
        member = next(
            (item for item in self._members if item.member_id == frame.member_id), None
        )
        if member is None:
            raise CorpusPolicyError("frame member_id is absent from the bound manifest")
        if len(frame.data) != member.byte_length:
            raise CorpusPolicyError("frame byte length differs from the bound manifest")
        actual = hashlib.sha256(frame.data).hexdigest()
        if actual != member.sha256:
            raise CorpusPolicyError("frame SHA-256 differs from the bound manifest")
        return actual
