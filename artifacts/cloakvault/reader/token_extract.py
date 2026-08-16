"""Structural token extraction — wrapper-independent by construction.

Visual localization (structural_locator/registration) and protocol
extraction are separate layers. This module is the protocol-visible
structural layer: it receives already-transcribed footer text lines
(uncertain cells preserved as '?') and locates the 142-character token
candidate using ONLY protocol-visible structure:

  * Bech32 charset compatibility;
  * public sentinel "cv0";
  * expected token length 142;
  * erasure ('?') structure.

It must tolerate arbitrary ordinary text before and after the token and
arbitrary line wrapping. It has NO knowledge of any wrapper: no domain
names, no fixed prefix/suffix lengths, no fixed line lengths, no fixed
token slices, no document genre.

Semantics match the frozen reference decoder's structural extraction
(spec §4.4): sentinel rule first, then length-run fallback. The frozen
decoder itself is not modified or re-implemented here for protocol work —
final decode is always delegated to it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
SENTINEL = "cv0"
TOKEN_LEN = 142
ERASURE = "?"
_TOKEN_ALPHABET = set(CHARSET) | {ERASURE}


@dataclass
class ExtractionResult:
    token: Optional[str]  # canonical 142-char candidate (may contain '?')
    method: Optional[str]  # "sentinel" | "length-run" | None
    runs_considered: int
    diagnostics: dict


def _runs(compact: str) -> list[str]:
    runs, cur = [], []
    for c in compact + "\x00":
        if c in _TOKEN_ALPHABET:
            cur.append(c)
        else:
            if cur:
                runs.append("".join(cur))
            cur = []
    return runs


def _sentinel_positions(run: str) -> Iterable[int]:
    """Exact sentinel matches, then erasure-tolerant matches ('?' wildcards).

    The sentinel is public framing: it is used as structural evidence and
    candidate scoring, never as license to guess payload characters.
    """
    exact = [i for i in range(len(run) - 2) if run[i : i + 3] == SENTINEL]
    if exact:
        return exact
    tol = []
    for i in range(len(run) - 2):
        window = run[i : i + 3]
        if all(w == s or w == ERASURE for w, s in zip(window, SENTINEL)):
            # require at least one non-erased sentinel char as evidence
            if any(w == s for w, s in zip(window, SENTINEL)):
                tol.append(i)
    return tol


def extract_token_structural(lines: list[str]) -> ExtractionResult:
    """Join transcribed lines structurally and locate the token candidate.

    Wrapping is presentation-only: all whitespace is stripped and runs of
    token-alphabet characters are joined across line boundaries. Any
    wrapping width (48/48/46, 40, 52, uneven) yields the same canonical
    token for the same underlying character sequence.
    """
    compact = "".join(c for c in "\n".join(lines).lower() if not c.isspace())
    runs = _runs(compact)
    diagnostics = {"run_lengths": [len(r) for r in runs]}

    # Sentinel rule first (public structural evidence).
    for r in runs:
        for at in _sentinel_positions(r):
            if len(r) - at >= TOKEN_LEN:
                return ExtractionResult(r[at : at + TOKEN_LEN], "sentinel", len(runs), diagnostics)

    # Length-run fallback: trailing TOKEN_LEN chars of a long-enough run.
    for r in runs:
        if len(r) >= TOKEN_LEN:
            return ExtractionResult(r[-TOKEN_LEN:], "length-run", len(runs), diagnostics)

    return ExtractionResult(None, None, len(runs), diagnostics)
