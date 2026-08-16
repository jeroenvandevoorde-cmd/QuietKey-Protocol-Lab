#!/usr/bin/env python3
"""Convert artifacts/cloakvault/spike/results/sweep_records.pkl to JSON.

Loads the pickle (dict keyed by capture filename), rounds floats to 6
decimals, writes sweep_records.json (indent 1, sorted keys) next to it,
verifies the expected structure, and only on success deletes the .pkl.
"""
import json
import pickle
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "artifacts" / "cloakvault" / "spike" / "results"
PKL = RESULTS / "sweep_records.pkl"
OUT = RESULTS / "sweep_records.json"

CHARSET = set("qpzry9x8gf2tvdw0s3jn54khce6mua7l")
TOKEN_IDS = ["T0", "T1", "T2", "T3", "T4"]


def convert(obj):
    if isinstance(obj, dict):
        return {k: convert(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [convert(v) for v in obj]
    if isinstance(obj, float):
        return round(obj, 6)
    return obj


def fail(msg):
    print(f"VERIFICATION FAILED: {msg}")
    sys.exit(1)


def main():
    with PKL.open("rb") as f:
        data = pickle.load(f)

    converted = convert(data)
    OUT.write_text(json.dumps(converted, indent=1, sort_keys=True) + "\n")

    # ── Verification (against the written JSON) ──
    loaded = json.loads(OUT.read_text())

    if len(loaded) != 27:
        fail(f"expected 27 sheets, got {len(loaded)}")

    total = 0
    for sheet, sheet_data in loaded.items():
        records = sheet_data.get("records")
        if not isinstance(records, dict):
            fail(f"{sheet}: missing 'records' dict")
        if sorted(records.keys()) != sorted(TOKEN_IDS):
            fail(f"{sheet}: token ids {sorted(records.keys())} != {TOKEN_IDS}")
        for tid, recs in records.items():
            if len(recs) != 142:
                fail(f"{sheet}/{tid}: expected 142 records, got {len(recs)}")
            for i, r in enumerate(recs):
                gt, pred = r["gt"], r["pred"]
                if not (isinstance(gt, str) and len(gt) == 1 and gt in CHARSET):
                    fail(f"{sheet}/{tid}[{i}]: bad gt {gt!r}")
                if pred is not None and not (
                    isinstance(pred, str) and len(pred) == 1 and pred in CHARSET
                ):
                    fail(f"{sheet}/{tid}[{i}]: bad pred {pred!r}")
                total += 1

    if total != 19170:
        fail(f"expected 19170 records total, got {total}")

    print("VERIFICATION PASSED:")
    print("  sheets: 27")
    print("  tokens per sheet: 5")
    print("  records per token: 142")
    print(f"  records total: {total}")
    print("  all gt and all non-null pred chars in Bech32 charset: yes")


if __name__ == "__main__":
    main()
