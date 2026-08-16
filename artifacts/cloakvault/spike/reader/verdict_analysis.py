"""Regenerate verdict_tokens.json from sweep_records.json.

Applies the frozen operating point (conf_floor 0.64, margin_floor 0.02),
computes the byte-level RS budget over the 133 payload characters, repairs
the sentinel positionally (public constant), verifies every token through
the reference decoder (RS + AEAD), and writes one row per token with the
five-class character counts. Output must be byte-identical to the committed
artifacts/cloakvault/spike/results/verdict_tokens.json; any difference means
either the records or this script drifted.
"""
import argparse, json, re, sys

CF, MF = 0.64, 0.02


def cell_class(r):
    if r["blank"] or r["conf"] < CF or r["margin"] < MF:
        return "e"
    return "c" if r["pred"] == r["gt"] else "w"


def byte_budget(recs):
    era_b, err_b = set(), set()
    for idx in range(133):
        r = recs[3 + idx]
        bs = {(idx * 5) // 8}
        if (idx * 5 + 4) // 8 < 83:
            bs.add((idx * 5 + 4) // 8)
        k = cell_class(r)
        if k == "e":
            era_b |= bs
        elif k == "w":
            err_b |= bs
    err_b -= era_b
    return len(err_b), len(era_b)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default="../results/sweep_records.json")
    ap.add_argument("--tokens", default="../tokens.json")
    ap.add_argument("--decoder-path",
                    default="../../interop/python")
    ap.add_argument("--out", default="verdict_tokens_regen.json")
    a = ap.parse_args()

    sys.path.insert(0, a.decoder_path)
    import cloakvault_v3 as cv

    tj = json.load(open(a.tokens))
    toks = {t["id"]: t for t in tj["tokens"]}
    res = json.load(open(a.records))

    rows = []
    for f in sorted(res):
        d = res[f]
        m = re.match(r"([a-z]+)-(\d)-", f)
        fam, sev = (m.group(1), int(m.group(2))) if m else ("baseline", 0)
        for tid in sorted(d["records"]):
            recs = d["records"][tid]
            g = toks[tid]
            vk = bytes.fromhex(g.get("vault_key_hex") or g.get("vaultKeyHex"))
            token = "cv0" + "".join(
                "?" if cell_class(r) == "e" else r["pred"]
                for r in recs)[3:]
            Eb, eb = byte_budget(recs)
            try:
                cv.decode_pipeline(token, vk)
                ok = True
            except Exception:
                ok = False
            cls = [cell_class(r) for r in recs]
            rows.append(dict(sheet=f, tid=tid, fam=fam, sev=sev,
                             C=cls.count("c"), e=cls.count("e"),
                             w=cls.count("w"), Eb=Eb, eb=eb, ok=ok))
    json.dump(rows, open(a.out, "w"), indent=1)
    n_ok = sum(r["ok"] for r in rows)
    print(f"tokens: {len(rows)}  decode success: {n_ok}")


if __name__ == "__main__":
    main()
