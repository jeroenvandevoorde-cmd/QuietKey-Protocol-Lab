"""Grouped-holdout evaluation for calibration banks (Reader v0.2.1, Task 9/12).

Leakage rule: glyphs from a capture (or physical copy) that contributed to
the bank must NEVER be scored against that bank. Minimum grouping is
leave-one-capture-out; prefer leave-one-copy-out when copy metadata exists.

Reports, at the FROZEN operating point (conf 0.64 / margin 0.02 — never
tuned here): per-class accuracy, erasure rate, confident-wrong rate, and
confidence/margin distributions. Evaluation NEVER modifies thresholds or
profiles (enforced by test_validation_path-style tests).
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Iterable

import numpy as np

from reader.calibration.bank import sample_feature
from reader.calibration.extract import GlyphSample

FROZEN_CONF_FLOOR = 0.64
FROZEN_MARGIN_FLOOR = 0.02


def _score(train: list[GlyphSample], test: list[GlyphSample],
           conf_floor: float, margin_floor: float) -> dict:
    feats, labels = [], []
    for s in train:
        v = sample_feature(s)
        if v is not None:
            feats.append(v)
            labels.append(s.label)
    if not feats:
        return {"n": 0, "reason": "EMPTY_TRAIN_FOLD"}
    F = np.stack(feats)
    L = np.array(labels)
    classes = sorted(set(labels))
    idx = {c: np.flatnonzero(L == c) for c in classes}

    n = correct = erased = confident_wrong = 0
    confs: list[float] = []
    margins: list[float] = []
    per_class: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "ok": 0, "erased": 0, "wrong": 0})
    for s in test:
        v = sample_feature(s)
        if v is None:
            continue
        sc = F @ v
        per = sorted(((float(sc[i].max()), c) for c, i in idx.items()), reverse=True)
        c1, top = per[0]
        c2 = per[1][0] if len(per) > 1 else -1.0
        n += 1
        confs.append(c1)
        margins.append(c1 - c2)
        pc = per_class[s.label]
        pc["n"] += 1
        if c1 < conf_floor or (c1 - c2) < margin_floor:
            erased += 1
            pc["erased"] += 1
        elif top == s.label:
            correct += 1
            pc["ok"] += 1
        else:
            confident_wrong += 1
            pc["wrong"] += 1
    return {
        "n": n,
        "accuracy_on_decided": (correct / max(1, n - erased)),
        "erasure_rate": erased / max(1, n),
        "confident_wrong_rate": confident_wrong / max(1, n),
        "confidence_percentiles": {p: float(np.percentile(confs, p)) for p in (5, 25, 50, 75, 95)} if confs else {},
        "margin_percentiles": {p: float(np.percentile(margins, p)) for p in (5, 25, 50, 75, 95)} if margins else {},
        "per_class": {k: dict(v) for k, v in sorted(per_class.items())},
    }


def grouped_holdout(
    samples: Iterable[GlyphSample],
    group_key: Callable[[GlyphSample], str] | None = None,
    conf_floor: float = FROZEN_CONF_FLOOR,
    margin_floor: float = FROZEN_MARGIN_FLOOR,
) -> dict:
    """Leave-one-group-out evaluation. Default group = capture SHA-256."""
    key = group_key or (lambda s: s.capture_sha256)
    all_samples = list(samples)
    # Leakage guard: no sample from a corpus banned for classifier training
    # may appear on EITHER side of a holdout fold (Bridge Run 01 ban).
    from reader.provenance import assert_no_banned_hashes
    assert_no_banned_hashes({s.capture_sha256 for s in all_samples})
    groups = sorted({key(s) for s in all_samples})
    if len(groups) < 2:
        return {
            "error": "NEED_AT_LEAST_2_GROUPS",
            "groups": groups,
            "note": "grouped holdout impossible; refusing to report in-sample numbers",
        }
    folds = {}
    for g in groups:
        train = [s for s in all_samples if key(s) != g]
        test = [s for s in all_samples if key(s) == g]
        folds[g] = _score(train, test, conf_floor, margin_floor)
    decided = [f["accuracy_on_decided"] for f in folds.values() if f.get("n")]
    return {
        "grouping": "leave-one-group-out",
        "n_groups": len(groups),
        "operating_point": {"confidence_floor": conf_floor, "margin_floor": margin_floor,
                            "frozen": conf_floor == FROZEN_CONF_FLOOR and margin_floor == FROZEN_MARGIN_FLOOR},
        "folds": folds,
        "mean_accuracy_on_decided": float(np.mean(decided)) if decided else None,
        "status": "DEVELOPMENT / NOT GATE-A1",
    }
