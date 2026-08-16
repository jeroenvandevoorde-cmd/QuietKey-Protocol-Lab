"""Result taxonomy and stage diagnostics for Reader v0.2 (DEVELOPMENT).

Every frame processed by the reader terminates in exactly one explicit
ResultCategory. There is deliberately no generic "FAIL": a failure must
identify the pipeline stage that produced it, so that a pristine capture
can never disappear into an unexplained downstream decode failure.

For failures occurring before meaningful token classification
(CAPTURE_QUALITY_REJECT, FOOTER_LOCALIZATION_FAIL, REGISTRATION_FAIL) the
apparent character/erasure counts are NOT physical-damage measurements and
are reported as None.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ResultCategory(str, Enum):
    AUTHENTICATED_SUCCESS = "AUTHENTICATED_SUCCESS"
    # RS decode + checksum passed but no AEAD key hook was supplied, so
    # authentication was NEVER attempted. This is NOT a success category:
    # a cold-storage reader must not present unverified ciphertext as a
    # recovery.
    RS_VALID_UNAUTHENTICATED = "RS_VALID_UNAUTHENTICATED"
    CAPTURE_QUALITY_REJECT = "CAPTURE_QUALITY_REJECT"
    FOOTER_LOCALIZATION_FAIL = "FOOTER_LOCALIZATION_FAIL"
    REGISTRATION_FAIL = "REGISTRATION_FAIL"
    RS_BUDGET_EXCEEDED = "RS_BUDGET_EXCEEDED"
    AUTHENTICATION_FAIL = "AUTHENTICATION_FAIL"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class Stage(str, Enum):
    CAPTURE = "CAPTURE"
    PAGE = "PAGE"
    FOOTER = "FOOTER"
    REGISTRATION = "REGISTRATION"
    CLASSIFICATION = "CLASSIFICATION"
    TOKEN_EXTRACTION = "TOKEN_EXTRACTION"
    RS = "RS"
    AEAD = "AEAD"


# Which stage each terminal category is attributed to.
CATEGORY_STAGE: dict[ResultCategory, Stage] = {
    ResultCategory.CAPTURE_QUALITY_REJECT: Stage.CAPTURE,
    ResultCategory.FOOTER_LOCALIZATION_FAIL: Stage.FOOTER,
    ResultCategory.REGISTRATION_FAIL: Stage.REGISTRATION,
    ResultCategory.RS_BUDGET_EXCEEDED: Stage.RS,
    ResultCategory.AUTHENTICATION_FAIL: Stage.AEAD,
    ResultCategory.RS_VALID_UNAUTHENTICATED: Stage.AEAD,
    ResultCategory.AUTHENTICATED_SUCCESS: Stage.AEAD,
}

# Categories reached before meaningful token classification: any apparent
# character counts at that point are not damage measurements.
PRE_CLASSIFICATION_CATEGORIES = frozenset(
    {
        ResultCategory.CAPTURE_QUALITY_REJECT,
        ResultCategory.FOOTER_LOCALIZATION_FAIL,
        ResultCategory.REGISTRATION_FAIL,
        ResultCategory.INTERNAL_ERROR,
    }
)


@dataclass
class StageDiagnostic:
    stage: Stage
    ok: bool
    reason: Optional[str] = None
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "ok": self.ok,
            "reason": self.reason,
            "metrics": self.metrics,
        }


@dataclass
class FrameResult:
    """One image in → one independent result out (multi-frame ready API).

    A later fusion layer may consume several FrameResults; this milestone
    performs no fusion and no multi-frame validation claims.
    """

    category: ResultCategory
    stages: list[StageDiagnostic] = field(default_factory=list)
    # Counts are None whenever they are not meaningful measurements.
    classified_chars: Optional[int] = None
    erasure_count: Optional[int] = None
    rs_error_bytes: Optional[int] = None
    rs_erasure_bytes: Optional[int] = None
    # NOTE: never place token/secret content here; diagnostics only.
    notes: Optional[str] = None

    def failing_stage(self) -> Optional[Stage]:
        for d in self.stages:
            if not d.ok:
                return d.stage
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "stages": [d.to_dict() for d in self.stages],
            "classified_chars": self.classified_chars,
            "erasure_count": self.erasure_count,
            "rs_error_bytes": self.rs_error_bytes,
            "rs_erasure_bytes": self.rs_erasure_bytes,
            "notes": self.notes,
        }
