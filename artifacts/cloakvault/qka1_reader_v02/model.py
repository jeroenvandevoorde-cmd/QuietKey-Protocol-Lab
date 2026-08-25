"""Strict transcript and result types for Reader v0.2."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .constants import ALPHABET, ERASURE, ProfileName, layout_for


class ReadOutcome(str, Enum):
    TRANSCRIPT_READY = "TRANSCRIPT_READY"
    RECAPTURE_REQUIRED = "RECAPTURE_REQUIRED"


@dataclass(frozen=True)
class Transcript:
    profile: ProfileName
    positions: tuple[str, ...]

    def __post_init__(self) -> None:
        expected = layout_for(self.profile).symbol_count
        if len(self.positions) != expected:
            raise ValueError(f"expected {expected} fixed positions")
        allowed = set(ALPHABET) | {ERASURE}
        if any(len(value) != 1 or value not in allowed for value in self.positions):
            raise ValueError("transcript contains a non-canonical position")

    @property
    def text(self) -> str:
        return "".join(self.positions)

    @property
    def erasure_count(self) -> int:
        return self.positions.count(ERASURE)


@dataclass(frozen=True)
class ReaderResult:
    outcome: ReadOutcome
    profile: ProfileName
    profile_sha256: str
    corpus_id: str
    corpus_source_commit: str
    corpus_manifest_sha256: str
    input_member_id: str
    input_sha256: str
    transcript: Transcript | None = None
    reason: str | None = None
    manual_intervention: bool = False
    authenticated: bool = False

    def __post_init__(self) -> None:
        if self.authenticated:
            raise ValueError("Reader v0.2 cannot report authentication")
        if self.manual_intervention:
            raise ValueError("Reader v0.2 cannot accept manual intervention")
        if self.outcome is ReadOutcome.TRANSCRIPT_READY and self.transcript is None:
            raise ValueError("ready result requires an exact transcript")
        if self.outcome is ReadOutcome.RECAPTURE_REQUIRED and self.transcript is not None:
            raise ValueError("recapture result cannot contain a transcript")

    def to_dict(self) -> dict[str, Any]:
        return {
            "reader": "QKA1 Reader v0.2",
            "outcome": self.outcome.value,
            "profile": self.profile.value,
            "profile_sha256": self.profile_sha256,
            "corpus_id": self.corpus_id,
            "corpus_source_commit": self.corpus_source_commit,
            "corpus_manifest_sha256": self.corpus_manifest_sha256,
            "input_member_id": self.input_member_id,
            "input_sha256": self.input_sha256,
            "symbol_count": len(self.transcript.positions) if self.transcript else None,
            "erasure_count": self.transcript.erasure_count if self.transcript else None,
            "transcript": self.transcript.text if self.transcript else None,
            "reason": self.reason,
            "manual_intervention": self.manual_intervention,
            "authenticated": self.authenticated,
        }
