"""Reader Profile loading — parameters separated from code.

A profile is a machine-readable JSON file. The validation path (validate.py)
requires an existing profile, loads thresholds from it, refuses to tune
them, and records the profile SHA-256. The calibration path (calibrate.py)
may write NEW candidate profiles but never mutates an existing one.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = [
    "profile_format_version",
    "reader_version",
    "status",
    "confidence_floor",
    "margin_floor",
    "capture_quality",
    "classifier_id",
    "registration_model_id",
    "calibration_corpora",
    "created",
    "warning",
]

DEVELOPMENT_STATUS = "DEVELOPMENT / NOT GATE-A1 / NOT PRODUCTION"


@dataclass(frozen=True)
class ReaderProfile:
    path: str
    sha256: str
    data: dict[str, Any]

    @property
    def status(self) -> str:
        return self.data["status"]

    @property
    def confidence_floor(self) -> float:
        return float(self.data["confidence_floor"])

    @property
    def margin_floor(self) -> float:
        return float(self.data["margin_floor"])

    @property
    def quality(self) -> dict[str, Any]:
        return self.data["capture_quality"]


def load_profile(path: str | Path) -> ReaderProfile:
    p = Path(path)
    raw = p.read_bytes()
    data = json.loads(raw)
    missing = [f for f in REQUIRED_FIELDS if f not in data]
    if missing:
        raise ValueError(f"profile {p} missing required fields: {missing}")
    return ReaderProfile(path=str(p), sha256=hashlib.sha256(raw).hexdigest(), data=data)


def default_development_profile_path() -> Path:
    return Path(__file__).parent / "profiles" / "spike-reader-v02-development.json"
