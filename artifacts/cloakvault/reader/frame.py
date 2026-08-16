"""Frame-level orchestration: one image in, one independent result out.

read_frame(image, profile) -> FrameResult

Multi-frame READINESS only: the API is shaped so a later layer can supply
multiple independent frames and fuse their FrameResults. No fusion, no
camera hardware, and no multi-frame validation claims in this milestone.

Stage order (each failure names its stage; no generic "decode failed"):
  CAPTURE -> PAGE -> FOOTER -> REGISTRATION -> CLASSIFICATION
  -> TOKEN_EXTRACTION -> RS -> AEAD

Protocol decode (RS + checksum + AEAD framing) is delegated to the frozen
reference decoder interop/python/cloakvault_v3.py; this module never
re-implements or alters protocol logic.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .profile import ReaderProfile
from .quality import assess_quality
from .registration import register_line
from .structural_locator import locate_footer_lines
from .synthglyphs import classify_cells
from .taxonomy import FrameResult, ResultCategory, Stage, StageDiagnostic
from .token_extract import extract_token_structural

_INTEROP = Path(__file__).resolve().parents[1] / "interop" / "python"


def _frozen_decoder():
    if str(_INTEROP) not in sys.path:
        sys.path.insert(0, str(_INTEROP))
    import cloakvault_v3  # frozen reference decoder — never modified

    return cloakvault_v3


def read_frame(
    image: np.ndarray,
    profile: ReaderProfile,
    decode_payload: Optional[Callable[[str], dict]] = None,
    classifier: Optional[Callable] = None,
    quality_gate_blocking: bool = True,
) -> FrameResult:
    """Process one frame. `decode_payload` optionally performs the final
    authenticated decode given the canonical token text (development hooks
    supply a vault-key-aware callable; None stops after RS accounting).

    `classifier` optionally replaces the default synthetic-template
    classifier; it must have the classify_cells contract. `quality_gate_
    blocking=False` runs the capture gate in REPORT-ONLY mode: its verdict
    is logged in the CAPTURE stage diagnostic but never blocks (diagnosis
    experiments only — production behavior is blocking)."""
    if classifier is None:
        classifier = classify_cells
    stages: list[StageDiagnostic] = []
    try:
        # CAPTURE ────────────────────────────────────────────────────────
        q = assess_quality(image, profile.quality)
        gate_metrics = dict(q.metrics)
        if not quality_gate_blocking:
            gate_metrics["gate_mode"] = "REPORT_ONLY"
            gate_metrics["gate_verdict"] = q.status
        stages.append(
            StageDiagnostic(Stage.CAPTURE, q.status == "ACCEPT", ";".join(q.reasons) or None, gate_metrics)
        )
        if q.status != "ACCEPT" and quality_gate_blocking:
            return FrameResult(ResultCategory.CAPTURE_QUALITY_REJECT, stages,
                               notes="capture rejected before deep decode; counts not meaningful")
        # PAGE (global geometry is folded into capture metrics for now) ──
        stages.append(StageDiagnostic(Stage.PAGE, True, None,
                                      {"page_boundary_confidence": q.metrics.get("page_boundary_confidence")}))

        # FOOTER ─────────────────────────────────────────────────────────
        loc = locate_footer_lines(image)
        stages.append(
            StageDiagnostic(
                Stage.FOOTER, loc.ok, loc.reason,
                {"candidates": len(loc.candidates),
                 "pitches": [round(c.pitch, 3) for c in loc.candidates]},
            )
        )
        if not loc.ok:
            return FrameResult(ResultCategory.FOOTER_LOCALIZATION_FAIL, stages)

        # REGISTRATION + CLASSIFICATION per candidate line ───────────────
        gray = np.asarray(image, dtype=np.float64)
        if gray.ndim == 3:
            gray = gray.mean(axis=2)
        if gray.max() > 1.5:
            gray = gray / 255.0
        lines_text: list[str] = []
        reg_metrics = []
        for cand in loc.candidates:
            pad = int(cand.pitch)
            s = max(0, cand.row_start - pad)
            e = min(gray.shape[0], cand.row_end + pad)
            strip = gray[s:e, :]
            try:
                model = register_line(strip)
            except ValueError as exc:
                stages.append(StageDiagnostic(Stage.REGISTRATION, False, str(exc)))
                return FrameResult(ResultCategory.REGISTRATION_FAIL, stages)
            centers = model.centers()
            y_mid = float(np.mean(model.y_at(centers)))
            text, confs, _ = classifier(
                strip, centers, y_mid, profile.confidence_floor, profile.margin_floor
            )
            lines_text.append(text)
            reg_metrics.append({"pitch": round(model.pitch, 3), "cells": len(text)})
        stages.append(StageDiagnostic(Stage.REGISTRATION, True, None, {"lines": reg_metrics}))
        classified = sum(len(t) for t in lines_text)
        erasures = sum(t.count("?") for t in lines_text)
        stages.append(StageDiagnostic(Stage.CLASSIFICATION, True, None,
                                      {"classified": classified, "erasures": erasures}))

        # TOKEN_EXTRACTION (structural, wrapper-independent) ─────────────
        ext = extract_token_structural(lines_text)
        stages.append(StageDiagnostic(Stage.TOKEN_EXTRACTION, ext.token is not None,
                                      None if ext.token else "no 142-char structural candidate",
                                      {"method": ext.method, **ext.diagnostics}))
        if ext.token is None:
            # Localization succeeded but no token candidate materialized —
            # attribute to registration/classification, not a generic fail.
            return FrameResult(ResultCategory.REGISTRATION_FAIL, stages,
                               classified_chars=classified, erasure_count=erasures,
                               notes="no structural token candidate after classification")

        # RS accounting via the frozen decoder ───────────────────────────
        cv = _frozen_decoder()
        d = cv.decode_token(ext.token)
        if not d.get("extracted"):
            stages.append(StageDiagnostic(Stage.RS, False, "frozen decoder found no token"))
            return FrameResult(ResultCategory.REGISTRATION_FAIL, stages,
                               classified_chars=classified, erasure_count=erasures)
        capsule = d.get("capsule")
        rs_era = d.get("erasures")  # erased RS bytes (frozen decoder accounting)
        rs_err = None  # frozen decoder does not expose error-byte count
        if capsule is None:
            budget = d.get("failure") or "RS budget exceeded"
            stages.append(StageDiagnostic(Stage.RS, False, str(budget),
                                          {"rs_errors": rs_err, "rs_erasures": rs_era}))
            return FrameResult(ResultCategory.RS_BUDGET_EXCEEDED, stages,
                               classified_chars=classified, erasure_count=erasures,
                               rs_error_bytes=rs_err, rs_erasure_bytes=rs_era)
        stages.append(StageDiagnostic(Stage.RS, True, None,
                                      {"rs_errors": rs_err, "rs_erasures": rs_era}))

        # AEAD ───────────────────────────────────────────────────────────
        if decode_payload is None:
            # Authentication was NEVER attempted — this must not be
            # reported as a success (cold-storage status integrity).
            stages.append(StageDiagnostic(Stage.AEAD, False, "AEAD_NOT_ATTEMPTED"))
            return FrameResult(ResultCategory.RS_VALID_UNAUTHENTICATED, stages,
                               classified_chars=classified, erasure_count=erasures,
                               rs_error_bytes=rs_err, rs_erasure_bytes=rs_era,
                               notes="RS-valid capsule recovered; NOT authenticated (no key hook supplied)")
        try:
            decode_payload(ext.token)
        except Exception as exc:  # authentication failure is explicit
            stages.append(StageDiagnostic(Stage.AEAD, False, type(exc).__name__))
            return FrameResult(ResultCategory.AUTHENTICATION_FAIL, stages,
                               classified_chars=classified, erasure_count=erasures,
                               rs_error_bytes=rs_err, rs_erasure_bytes=rs_era)
        stages.append(StageDiagnostic(Stage.AEAD, True, None))
        return FrameResult(ResultCategory.AUTHENTICATED_SUCCESS, stages,
                           classified_chars=classified, erasure_count=erasures,
                           rs_error_bytes=rs_err, rs_erasure_bytes=rs_era)
    except Exception as exc:  # never a silent generic failure
        stages.append(StageDiagnostic(Stage.CAPTURE, False, f"INTERNAL:{type(exc).__name__}"))
        return FrameResult(ResultCategory.INTERNAL_ERROR, stages, notes=type(exc).__name__)
