"""Task 0 diagnosis experiment: Reader v0.2 end-to-end on all 19 Bridge Run 01
images with the frozen historical profile "spike-2026-08".

- Glyph bank: spike S01+S02 pooled bank (built by build_spike_2026_08_bank.py;
  SHA-256 recorded in the profile). No Bridge image used for training.
- Thresholds: conf_floor 0.64 / margin_floor 0.02 (frozen, unchanged).
- Capture-quality gate: REPORT-ONLY (verdict logged, never blocks).
- AEAD: real authenticated decode via the frozen reference decoder with the
  T5 vault key from spike/tokens.json (the printed production page carries T5).
  "Authenticated" means AEAD verification passed AND the recovered entropy
  equals T5 ground truth.

Outputs: reader/task0-spike-2026-08-replay.json (full stage funnel per sheet).
Either outcome is reported, not optimized.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "interop" / "python"))

from reader.frame import read_frame  # noqa: E402
from reader.profile import load_profile  # noqa: E402
from reader.spike_bank_classifier import SpikeBank, make_spike_classifier  # noqa: E402
import cloakvault_v3 as cv3  # frozen reference decoder  # noqa: E402

CAPTURES = ROOT / "bridge" / "captures"
PROFILE = ROOT / "reader" / "profiles" / "spike-2026-08.json"
OUT = ROOT / "reader" / "task0-spike-2026-08-replay.json"

GT = json.loads((ROOT / "spike" / "tokens.json").read_text())
T5 = next(t for t in GT["tokens"] if t["id"] == "T5")
T5_KEY = bytes.fromhex(T5["vault_key_hex"])
T5_ENTROPY = T5["entropy_hex"]


def decode_t5(token: str) -> dict:
    out = cv3.decode_pipeline(token, T5_KEY)  # raises on AEAD failure; returns entropy bytes
    ent = bytes(out).hex()
    if ent != T5_ENTROPY:
        raise ValueError(f"ENTROPY_MISMATCH:{ent}")
    return {"entropy_hex": ent}


def load_gray(p: Path) -> np.ndarray:
    img = Image.open(p)
    img = ImageOps.exif_transpose(img).convert("L")
    return np.asarray(img, dtype=np.float64) / 255.0


def main() -> None:
    profile = load_profile(PROFILE)
    bank_meta = profile.data["glyph_bank"]
    bank_path = ROOT / bank_meta["path"]
    bank_sha = hashlib.sha256(bank_path.read_bytes()).hexdigest()
    assert bank_sha == bank_meta["sha256"], "bank SHA-256 mismatch vs profile"
    classifier = make_spike_classifier(SpikeBank(bank_path))

    sheets = sorted(CAPTURES.glob("bridge-*.jpeg"))
    assert len(sheets) == 19, f"expected 19 captures, found {len(sheets)}"

    results = []
    for p in sheets:
        img = load_gray(p)
        r = read_frame(img, profile, decode_payload=decode_t5,
                       classifier=classifier, quality_gate_blocking=False)
        results.append({
            "sheet": p.name,
            "category": r.category.name,
            "gate_verdict": next((s.metrics.get("gate_verdict") for s in r.stages
                                  if s.stage.name == "CAPTURE" and s.metrics), None),
            "gate_reasons": next((s.reason for s in r.stages if s.stage.name == "CAPTURE"), None),
            "classified_chars": r.classified_chars,
            "erasures": r.erasure_count,
            "rs_erasure_bytes": r.rs_erasure_bytes,
            "stages": [{"stage": s.stage.name, "ok": s.ok, "reason": s.reason,
                        "metrics": s.metrics} for s in r.stages],
            "notes": r.notes,
        })
        print(f"{p.name:45s} gate={results[-1]['gate_verdict']:8s} -> {r.category.name}")

    cats = {}
    for r in results:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    stage_reached = {}
    for r in results:
        for s in r["stages"]:
            stage_reached[s["stage"]] = stage_reached.get(s["stage"], 0) + 1
    auth = cats.get("AUTHENTICATED_SUCCESS", 0)
    decision = (
        "AUTH >= 10: primary defects are quality gate and locator; Phase B proceeds as foundation work"
        if auth >= 10 else
        "AUTH < 5: bank/feature incompatibility confirmed as a primary defect; Task 3 + Phase B are the fix"
        if auth < 5 else
        "AUTH in [5,10): between decision thresholds; reported as-is, no rule fires"
    )
    payload = {
        "experiment": "task0-diagnosis",
        "development_data": True,
        "profile": {"path": str(PROFILE.relative_to(ROOT)), "sha256": profile.sha256},
        "bank_sha256": bank_sha,
        "quality_gate_mode": "REPORT_ONLY",
        "thresholds": {"confidence_floor": profile.confidence_floor,
                       "margin_floor": profile.margin_floor},
        "category_counts": cats,
        "stage_funnel_reached": stage_reached,
        "authenticated_decodes": auth,
        "decision_rule_outcome": decision,
        "sheets": results,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({k: payload[k] for k in
                      ("category_counts", "authenticated_decodes", "decision_rule_outcome")},
                     indent=2))
    print("written:", OUT)


if __name__ == "__main__":
    main()
