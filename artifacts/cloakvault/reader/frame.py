"""Frame-level orchestration: one image in, one independent result out.

read_frame(image, profile) -> FrameResult

Multi-frame READINESS only: the API is shaped so a later layer can supply
multiple independent frames and fuse their FrameResults. No fusion, no
camera hardware, and no multi-frame validation claims in this milestone.

Stage order (each failure names its stage; no generic "decode failed"):
  CAPTURE -> PAGE -> FOOTER -> REGISTRATION -> CLASSIFICATION
  -> TOKEN_EXTRACTION -> RS -> AEAD

v0.2.1: footer localization enumerates a BOUNDED, deterministic set of
structural candidates (locate_footer_candidates). Downstream stages are
attempted per candidate in structural-score order; the first candidate
producing an RS-valid capsule is accepted. Protocol structure (sentinel,
RS, AEAD) decides between candidates — it never feeds back into geometry
search, and no threshold is tuned by it. If no candidate survives, the
reported result is the deepest honest failure among the attempts.

Protocol decode (RS + checksum + AEAD framing) is delegated to the frozen
reference decoder interop/python/cloakvault_v3.py; this module never
re-implements or alters protocol logic.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .profile import ReaderProfile
from .quality import assess_quality
from .registration import register_line, select_pitch
from .structural_locator import FooterCandidate, locate_footer_candidates
from .synthglyphs import classify_cells
from .taxonomy import FrameResult, ResultCategory, Stage, StageDiagnostic
from .token_extract import extract_token_structural

_INTEROP = Path(__file__).resolve().parents[1] / "interop" / "python"


def _frozen_decoder():
    if str(_INTEROP) not in sys.path:
        sys.path.insert(0, str(_INTEROP))
    import cloakvault_v3  # frozen reference decoder — never modified

    return cloakvault_v3


# stage depth for honest deepest-failure attribution across candidates
_DEPTH = {
    ResultCategory.REGISTRATION_FAIL: 1,
    ResultCategory.RS_BUDGET_EXCEEDED: 2,
}


@dataclass
class _Attempt:
    """Outcome of one footer-candidate decode attempt."""
    index: int
    category: ResultCategory | None  # None = RS-valid (success at RS stage)
    reason: str | None
    metrics: dict = field(default_factory=dict)
    token: str | None = None
    classified: int = 0
    erasures: int = 0
    rs_erasures: int | None = None
    depth: int = 0


def prepare_candidate_lines(
    gray: np.ndarray,
    cand: FooterCandidate,
    profile: ReaderProfile,
) -> list[tuple]:
    """Shared runtime line preparation: crop each candidate line strip and
    select its glyph pitch with the layout-consistent discipline
    (registration.select_pitch) — pass 1 independent per line, pass 2
    neighboring-line pitch agreement. Used by _attempt_candidate and by the
    runtime evaluation scripts so the registration path cannot drift.

    Returns [(line_hypothesis, strip, PitchSelection), ...].
    """
    layout = profile.data.get("production_layout") or {}
    char_counts = layout.get("token_line_char_counts")

    strips: list[np.ndarray] = []
    for l in cand.lines:
        pad_y = max(2, (l.row_end - l.row_start) // 2)
        pad_x = int(round(2 * max(l.pitch, 1.0)))
        s = max(0, l.row_start - pad_y)
        e = min(gray.shape[0], l.row_end + pad_y)
        x0 = max(0, l.x0 - pad_x)
        x1 = min(gray.shape[1], l.x1 + pad_x)
        strips.append(gray[s:e, x0:x1])

    # pass 1: independent layout-consistent selection per line
    sels = [select_pitch(strip, span=float(l.x1 - l.x0),
                         expected_char_counts=char_counts)
            for strip, l in zip(strips, cand.lines)]
    # pass 2: neighboring-line pitch agreement — lines of one footer share
    # the print pitch, so outliers are re-selected against the group median
    # of layout-plausible selections.
    anchor = [s.pitch for s in sels if s.method == "layout" and s.pitch > 0]
    if len(anchor) >= 2:
        med = float(np.median(anchor))
        for i, (strip, l, sel) in enumerate(zip(strips, cand.lines, sels)):
            if sel.pitch <= 0 or abs(sel.pitch / med - 1.0) > 0.15:
                sels[i] = select_pitch(strip, span=float(l.x1 - l.x0),
                                       expected_char_counts=char_counts,
                                       neighbor_pitch=med)

    # layout-consistent cell count: when the pitch was chosen by the layout
    # window, the implied char count is the layout count that window came
    # from — snapping to it removes edge-trim off-by-one jitter that would
    # shift positional alignment of every later cell.
    hints: list[int | None] = []
    for l, sel in zip(cand.lines, sels):
        hint = None
        if sel.method == "layout" and char_counts and sel.pitch > 0:
            span = float(l.x1 - l.x0)
            hint = min(char_counts, key=lambda w: abs(span / w - sel.pitch))
        hints.append(hint)
    return list(zip(cand.lines, strips, sels, hints))


def _attempt_candidate(
    gray: np.ndarray,
    cand: FooterCandidate,
    index: int,
    profile: ReaderProfile,
    classifier: Callable,
) -> _Attempt:
    """Register/classify/extract/RS for ONE footer candidate.

    v0.2.1 harmonic fix: per-line glyph pitch is chosen by the shared
    layout-consistent discipline (registration.select_pitch) using only
    public structural information — candidate line extent, expected footer
    typography char counts from the bound profile, occupancy/harmonic
    consistency, and neighboring-line pitch agreement. No per-image logic.
    """
    lines_text: list[str] = []
    reg_metrics = []
    prepared = prepare_candidate_lines(gray, cand, profile)

    for l, strip, sel, n_hint in prepared:
        try:
            model = register_line(strip, n_cells_hint=n_hint,
                                  pitch_hint=sel.pitch if sel.pitch > 0 else None)
        except ValueError as exc:
            return _Attempt(index, ResultCategory.REGISTRATION_FAIL, str(exc),
                            {"line_rows": [l.row_start, l.row_end],
                             "pitch_selection": sel.diagnostics()},
                            depth=_DEPTH[ResultCategory.REGISTRATION_FAIL])
        centers = model.centers()
        y_mid = float(np.mean(model.y_at(centers)))
        text, confs, _ = classifier(
            strip, centers, y_mid, profile.confidence_floor, profile.margin_floor
        )
        lines_text.append(text)
        reg_metrics.append({"pitch": round(model.pitch, 3), "cells": len(text),
                            "detected": l.detected,
                            "pitch_selection": sel.diagnostics()})
    classified = sum(len(t) for t in lines_text)
    erasures = sum(t.count("?") for t in lines_text)

    ext = extract_token_structural(lines_text)
    if ext.token is None:
        return _Attempt(index, ResultCategory.REGISTRATION_FAIL,
                        "no structural token candidate after classification",
                        {"lines": reg_metrics, "extract": ext.diagnostics},
                        classified=classified, erasures=erasures,
                        depth=_DEPTH[ResultCategory.REGISTRATION_FAIL])

    cv = _frozen_decoder()
    d = cv.decode_token(ext.token)
    if not d.get("extracted"):
        return _Attempt(index, ResultCategory.REGISTRATION_FAIL,
                        "frozen decoder found no token", {"lines": reg_metrics},
                        classified=classified, erasures=erasures,
                        depth=_DEPTH[ResultCategory.REGISTRATION_FAIL])
    rs_era = d.get("erasures")
    if d.get("capsule") is None:
        return _Attempt(index, ResultCategory.RS_BUDGET_EXCEEDED,
                        str(d.get("failure") or "RS budget exceeded"),
                        {"lines": reg_metrics}, token=ext.token,
                        classified=classified, erasures=erasures,
                        rs_erasures=rs_era,
                        depth=_DEPTH[ResultCategory.RS_BUDGET_EXCEEDED])
    return _Attempt(index, None, None, {"lines": reg_metrics, "method": ext.method},
                    token=ext.token, classified=classified, erasures=erasures,
                    rs_erasures=rs_era, depth=3)


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

        # FOOTER — bounded structural candidate enumeration ──────────────
        cands = locate_footer_candidates(image)
        stages.append(
            StageDiagnostic(
                Stage.FOOTER, bool(cands),
                None if cands else "no structural footer candidate",
                {"candidates": len(cands),
                 "summary": [
                     {"score": round(c.score, 4), "pitch": round(c.pitch, 3),
                      "gap": round(c.gap, 2), "n_detected": c.n_detected,
                      "rows": [[l.row_start, l.row_end] for l in c.lines]}
                     for c in cands
                 ]},
            )
        )
        if not cands:
            return FrameResult(ResultCategory.FOOTER_LOCALIZATION_FAIL, stages)

        gray = np.asarray(image, dtype=np.float64)
        if gray.ndim == 3:
            gray = gray.mean(axis=2)
        if gray.max() > 1.5:
            gray = gray / 255.0

        # Per-candidate attempts, structural-score order, first RS-valid
        # wins. Bounded by the locator's MAX_CANDIDATES.
        attempts: list[_Attempt] = []
        winner: _Attempt | None = None
        for i, cand in enumerate(cands):
            a = _attempt_candidate(gray, cand, i, profile, classifier)
            attempts.append(a)
            if a.category is None:
                winner = a
                break
        att_summary = [
            {"candidate": a.index, "outcome": (a.category.name if a.category else "RS_VALID"),
             "reason": a.reason, "erasures": a.erasures}
            for a in attempts
        ]

        if winner is None:
            # deepest honest failure among the bounded attempts
            best = max(attempts, key=lambda a: (a.depth, -a.erasures if a.classified else 0, -a.index))
            stages.append(StageDiagnostic(Stage.REGISTRATION, best.depth >= 2,
                                          None if best.depth >= 2 else best.reason,
                                          {"attempts": att_summary, "chosen": best.index,
                                           **best.metrics}))
            if best.depth < 2:
                return FrameResult(ResultCategory.REGISTRATION_FAIL, stages,
                                   classified_chars=best.classified, erasure_count=best.erasures,
                                   notes=best.reason)
            stages.append(StageDiagnostic(Stage.CLASSIFICATION, True, None,
                                          {"classified": best.classified, "erasures": best.erasures}))
            stages.append(StageDiagnostic(Stage.TOKEN_EXTRACTION, best.token is not None,
                                          None, {}))
            stages.append(StageDiagnostic(Stage.RS, False, best.reason,
                                          {"rs_errors": None, "rs_erasures": best.rs_erasures}))
            return FrameResult(ResultCategory.RS_BUDGET_EXCEEDED, stages,
                               classified_chars=best.classified, erasure_count=best.erasures,
                               rs_error_bytes=None, rs_erasure_bytes=best.rs_erasures)

        stages.append(StageDiagnostic(Stage.REGISTRATION, True, None,
                                      {"attempts": att_summary, "chosen": winner.index,
                                       "lines": winner.metrics.get("lines")}))
        stages.append(StageDiagnostic(Stage.CLASSIFICATION, True, None,
                                      {"classified": winner.classified, "erasures": winner.erasures}))
        stages.append(StageDiagnostic(Stage.TOKEN_EXTRACTION, True, None,
                                      {"method": winner.metrics.get("method")}))
        stages.append(StageDiagnostic(Stage.RS, True, None,
                                      {"rs_errors": None, "rs_erasures": winner.rs_erasures}))

        # AEAD ───────────────────────────────────────────────────────────
        if decode_payload is None:
            # Authentication was NEVER attempted — this must not be
            # reported as a success (cold-storage status integrity).
            stages.append(StageDiagnostic(Stage.AEAD, False, "AEAD_NOT_ATTEMPTED"))
            return FrameResult(ResultCategory.RS_VALID_UNAUTHENTICATED, stages,
                               classified_chars=winner.classified, erasure_count=winner.erasures,
                               rs_error_bytes=None, rs_erasure_bytes=winner.rs_erasures,
                               notes="RS-valid capsule recovered; NOT authenticated (no key hook supplied)")
        try:
            decode_payload(winner.token)
        except Exception as exc:  # authentication failure is explicit
            stages.append(StageDiagnostic(Stage.AEAD, False, type(exc).__name__))
            return FrameResult(ResultCategory.AUTHENTICATION_FAIL, stages,
                               classified_chars=winner.classified, erasure_count=winner.erasures,
                               rs_error_bytes=None, rs_erasure_bytes=winner.rs_erasures)
        stages.append(StageDiagnostic(Stage.AEAD, True, None))
        return FrameResult(ResultCategory.AUTHENTICATED_SUCCESS, stages,
                           classified_chars=winner.classified, erasure_count=winner.erasures,
                           rs_error_bytes=None, rs_erasure_bytes=winner.rs_erasures)
    except Exception as exc:  # never a silent generic failure
        stages.append(StageDiagnostic(Stage.CAPTURE, False, f"INTERNAL:{type(exc).__name__}"))
        return FrameResult(ResultCategory.INTERNAL_ERROR, stages, notes=type(exc).__name__)
