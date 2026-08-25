"""Injected image-facing interfaces for the dependency-free scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .constants import ProfileName


@dataclass(frozen=True)
class ClassificationCandidate:
    """One classifier hypothesis; policy decides symbol versus erasure."""

    symbol: str | None
    confidence: float
    margin: float

    def __post_init__(self) -> None:
        if self.symbol is not None and (
            not isinstance(self.symbol, str) or len(self.symbol) != 1
        ):
            raise ValueError("a classifier may return at most one symbol")
        if (
            type(self.confidence) not in {int, float}
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("confidence must be in [0,1]")
        if (
            type(self.margin) not in {int, float}
            or not 0.0 <= self.margin <= 1.0
        ):
            raise ValueError("margin must be in [0,1]")


@dataclass(frozen=True)
class LocatedFooter:
    """An automatically located, rectified grid supplied by a locator.

    `cells` are opaque in-memory samples.  The flags are part of the runtime
    contract: a result that used decoy text, rig-only marks, a manual crop, or
    candidate selection is rejected before classification.
    """

    profile: ProfileName
    cells: tuple[Any, ...]
    automatic: bool
    used_decoy_text: bool
    used_rig_marks: bool
    candidate_count: int

    def __post_init__(self) -> None:
        if type(self.profile) is not ProfileName:
            raise ValueError("located profile must be an exact ProfileName")
        if type(self.cells) is not tuple:
            raise ValueError("located cells must be an immutable tuple")
        if any(
            type(value) is not bool
            for value in (self.automatic, self.used_decoy_text, self.used_rig_marks)
        ):
            raise ValueError("locator policy attestations must be explicit booleans")
        if type(self.candidate_count) is not int or self.candidate_count < 0:
            raise ValueError("candidate_count must be a non-negative integer")


@dataclass(frozen=True)
class LocationFailure:
    """Fail-closed automatic-location result with a stable reason."""

    reason: str

    def __post_init__(self) -> None:
        if self.reason not in {
            "FOOTER_NOT_LOCATED",
            "FOOTER_GEOMETRY_UNSUPPORTED",
            "PROFILE_AMBIGUOUS",
        }:
            raise ValueError("unknown automatic-location failure")


class FooterLocator(Protocol):
    artifact_id: str
    artifact_sha256: str

    def locate(self, frame_bytes: bytes) -> LocatedFooter | LocationFailure | None:
        """Infer and return one automatic footer grid or a recapture result."""


class CellClassifier(Protocol):
    artifact_id: str
    artifact_sha256: str
    training_corpus_manifest_sha256: str
    training_partition_id: str
    training_partition_sha256: str

    def classify(self, cell: Any, position: int) -> ClassificationCandidate:
        """Return one hypothesis; uncertainty must survive as an erasure."""
