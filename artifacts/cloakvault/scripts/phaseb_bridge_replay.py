"""Phase B development replay: Reader v0.2.1 end-to-end on all 19 Bridge
Run 01 images with the NEW real-print calibration bank (cal-run01).

DEVELOPMENT REPLAY ONLY. Bridge Run 01 is permanently seen development
data: it is never training, calibration, or validation material, and this
replay is NOT Gate A1 evidence. The corpus flags are enforced below.

- Profile: reader/profiles/cal-run01-development.json (frozen thresholds
  conf 0.64 / margin 0.02 — reported, never tuned).
- Glyph bank: cal-run01-bank.npz (built exclusively from cal-run01
  captures; Bridge hashes banned at build time).
- Capture-quality gate: REPORT-ONLY, as in the Task 0 baseline replay.
- Comparison target (Task 0 baseline funnel): 13 CAPTURE_QUALITY_REJECT /
  6 RS_BUDGET_EXCEEDED / 0 FOOTER_FAIL categories are NOT expected to be
  matched — either direction of movement is reported, not optimized.

Output: reader/bridge-run01-dev-replay-v021-calbank.json
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "interop" / "python"))

from reader.frame import read_frame  # noqa: E402
from reader.profile import load_profile  # noqa: E402
from reader.provenance import require_flag  # noqa: E402
from reader.spike_bank_classifier import SpikeBank, make_spike_classifier  # noqa: E402
import cloakvault_v3 as cv3  # frozen reference decoder  # noqa: E402

CAPTURES = ROOT / "bridge" / "captures"
PROFILE = ROOT / "reader" / "profiles" / "cal-run01-development.json"
BASELINE = ROOT / "reader" / "task0-spike-2026-08-replay.json"
OUT = ROOT / "reader" / "bridge-run01-dev-replay-v021-calbank.json"

GT = json.loads((ROOT / "spike" / "tokens.json").read_text())
T5 = next(t for t in GT["tokens"] if t["id"] == "T5")
T5_KEY = bytes.fromhex(T5["vault_key_hex"])
T5_ENTROPY = T5["entropy_hex"]


def decode_t5(token: str) -> dict:
    out = cv3.decode_pipeline(token, T5_KEY)
    ent = bytes(out).hex()
    if ent != T5_ENTROPY:
        raise ValueError(f"ENTROPY_MISMATCH:{ent}")
    return {"entropy_hex": ent}


def load_gray(p: Path) -> np.ndarray:
    img = ImageOps.exif_transpose(Image.open(p)).convert("L")
    return np.asarray(img, dtype=np.float64) / 255.0


CACHE_DIR = Path("/tmp/phaseb-replay-cache")
# Cache key covers the profile (which pins the bank sha) AND the reader
# code revision, so behavioral changes to the pipeline invalidate cached
# per-sheet results.
_CODE_SHA = hashlib.sha256(
    b"".join(p.read_bytes() for p in sorted((ROOT / "reader").glob("*.py")))
    + Path(__file__).read_bytes()).hexdigest()[:16]
_worker_classifier = None
_worker_profile = None


def _replay_one(path_str: str) -> dict:
    """Worker: replay one Bridge sheet (cached per sheet + profile sha)."""
    global _worker_classifier, _worker_profile
    p = Path(path_str)
    if _worker_profile is None:
        _worker_profile = load_profile(PROFILE)
        bank_path = ROOT / _worker_profile.data["glyph_bank"]["path"]
        _worker_classifier = make_spike_classifier(SpikeBank(bank_path))
    key = CACHE_DIR / f"{p.name}-{_worker_profile.sha256[:16]}-{_CODE_SHA}.pkl"
    if key.exists():
        with key.open("rb") as f:
            return pickle.load(f)
    r = read_frame(load_gray(p), _worker_profile, decode_payload=decode_t5,
                   classifier=_worker_classifier, quality_gate_blocking=False)
    out = {
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
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = key.with_suffix(".tmp")
    with tmp.open("wb") as f:
        pickle.dump(out, f)
    tmp.replace(key)
    return out


def main() -> None:
    # Bridge Run 01 is development-only; this replay is regression/dev use.
    require_flag("bridge-run01-development", "regression_testing_allowed")

    profile = load_profile(PROFILE)
    bank_meta = profile.data["glyph_bank"]
    bank_path = ROOT / bank_meta["path"]
    bank_sha = hashlib.sha256(bank_path.read_bytes()).hexdigest()
    assert bank_sha == bank_meta["sha256"], "bank SHA-256 mismatch vs profile"
    classifier = make_spike_classifier(SpikeBank(bank_path))

    sheets = sorted(CAPTURES.glob("bridge-*.jpeg"))
    assert len(sheets) == 19, f"expected 19 captures, found {len(sheets)}"

    with ProcessPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(_replay_one, [str(p) for p in sheets]))
    for r in results:
        print(f"{r['sheet']:45s} gate={str(r['gate_verdict']):8s} -> {r['category']}")

    cats: dict[str, int] = {}
    for r in results:
        cats[r["category"]] = cats.get(r["category"], 0) + 1

    baseline_cats = None
    if BASELINE.exists():
        baseline_cats = json.loads(BASELINE.read_text())["category_counts"]

    payload = {
        "experiment": "phaseb-bridge-run01-dev-replay-v021-calbank",
        "development_data": True,
        "status": "DEVELOPMENT REPLAY / NOT GATE-A1 EVIDENCE",
        "profile": {"path": str(PROFILE.relative_to(ROOT)), "sha256": profile.sha256},
        "bank_sha256": bank_sha,
        "quality_gate_mode": "REPORT_ONLY",
        "thresholds": {"confidence_floor": profile.confidence_floor,
                       "margin_floor": profile.margin_floor},
        "category_counts": cats,
        "baseline_category_counts": baseline_cats,
        "sheets": results,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"category_counts": cats,
                      "baseline_category_counts": baseline_cats}, indent=2))
    print("written:", OUT)


if __name__ == "__main__":
    main()
