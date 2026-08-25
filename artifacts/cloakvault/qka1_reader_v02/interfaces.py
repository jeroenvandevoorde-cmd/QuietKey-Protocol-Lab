"""Injected image-facing interfaces for the dependency-free scaffold."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .constants import GridLayout


@dataclass(frozen=True)
class ClassificationCandidate:
    """One classifier hypothesis; policy decides symbol versus erasure."""

    symbol: str | None
    confidence: float
    margin: float

    def __post_init__(self) -> None:
        if self.symbol is not None and len(self.symbol) != 1:
            raise ValueError("a classifier may return at most one symbol")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be in [0,1]")
        if not 0.0 <= self.margin <= 1.0:
            raise ValueError("margin must be in [0,1]")


@dataclass(frozen=True)
class LocatedFooter:
    """An automatically located, rectified grid supplied by a locator.

    `cells` are opaque in-memory samples.  The flags are part of the runtime
    contract: a result that used decoy text, rig-only marks, a manual crop, or
    candidate selection is rejected before classification.
    """

    cells: tuple[Any, ...]
    automatic: bool
    used_decoy_text: bool
    used_rig_marks: bool
    candidate_count: int


class FooterLocator(Protocol):
    artifact_id: str
    artifact_sha256: str

    def locate(self, frame_bytes: bytes, layout: GridLayout) -> LocatedFooter | None:
        """Return one automatic footer grid or None to request recapture."""


class CellClassifier(Protocol):
    artifact_id: str
    artifact_sha256: str

    def classify(self, cell: Any, position: int) -> ClassificationCandidate:
        """Return one hypothesis; uncertainty must survive as an erasure."""
