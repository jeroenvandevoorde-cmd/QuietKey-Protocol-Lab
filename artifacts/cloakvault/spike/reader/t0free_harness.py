"""T0-free reader path over the 27 token sheets.

Production has no known-content control token. This harness removes every
T0 dependency from the spike reader:
  - geometry hypothesis selection uses the 15 sentinel cells only
    ('c','v','0' at the head of each block's first line, a public constant),
  - classification uses the global baseline bank only, no own-T0 pooling,
  - no T0 health gate.
Same frozen operating point (conf 0.64, margin 0.02), same byte-level
budget, same reference decoder. Output compared per token against the
T0-selected results in verdict_tokens.json.
"""
import json, pickle, sys, glob, re
import numpy as np
import spike_reader as sr
import gatea_nn_layer as nn
import robust_locator2 as rl
import sweep_harness2 as h

sys.path.insert(0, '/tmp/qkcheck/artifacts/cloakvault/interop/python')
import cloakvault_v3 as cv

CF, MF = 0.64, 0.02
SENT = "cv0"
SENT_LINES = (0, 3, 6, 9, 12)


def sentinel_score(rect_e, ycs, x0s, ps, gF, gL):
    """Content-free hypothesis score: sentinel hits (alias rejection, the
    only known-content cells) plus mean top-1 confidence over the five
    block-head lines including their line ends (pitch sensitivity)."""
    hits = 0
    confs = []
    for li in SENT_LINES:
        per = h.windows_from_grid(rect_e, [ycs[li]],
                                  np.asarray(x0s)[li:li + 1],
                                  np.asarray(ps)[li:li + 1])
        feats = h.feats_of_line(per[0])
        preds, cf, _ = h.nn_score(feats, gF, gL)
        hits += sum(1 for p, g in zip(preds[:3], SENT) if p == g)
        confs.extend(c for c, (fe, bl) in zip(cf, feats) if not bl)
    return hits, (float(np.mean(confs)) if confs else 0.0)


def process_sheet_t0free(path, canon, gF, gL):
    rect = sr.rectify(path)
    rect_e = sr.enhance(rect)
    hyps, diag = h.geometry_hypotheses(rect, canon)
    best = None
    for name, ycs, x0s, ps in hyps:
        hits, mc = sentinel_score(rect_e, ycs, x0s, ps, gF, gL)
        key = (hits, mc)
        if best is None or key > best[0]:
            best = (key, name, ycs, x0s, ps)
    (s_hits, _), gname, ycs, x0s, ps = best

    per_line = h.windows_from_grid(rect_e, ycs, x0s, ps)
    records = {}
    li = 0
    for tid in h.TIDS:
        gt = sr.gt_entry(tid)["token"]
        feats = []
        for wins in per_line[li:li + 3]:
            feats.extend(h.feats_of_line(wins))
        li += 3
        preds, confs, margs = h.nn_score(feats, gF, gL)
        records[tid] = [dict(gt=gt[i], pred=preds[i], conf=confs[i],
                             margin=margs[i], blank=feats[i][1])
                        for i in range(len(feats))]
    return records, dict(geom=gname, sent=s_hits, matched=diag["matched"])


def byte_budget(recs):
    era_b, err_b = set(), set()
    for idx in range(133):
        r = recs[3 + idx]
        bs = {(idx * 5) // 8} | ({(idx * 5 + 4) // 8}
                                 if (idx * 5 + 4) // 8 < 83 else set())
        if r["blank"] or r["conf"] < CF or r["margin"] < MF:
            era_b |= bs
        elif r["pred"] != r["gt"]:
            err_b |= bs
    err_b -= era_b
    return len(err_b), len(era_b)


def main():
    files = sorted(f for f in glob.glob("*.jpeg") if not f.startswith("locate"))
    canon = rl.CanonicalLayout("baseline-0-std-S01.jpeg")
    bank_both = h.build_bank(["baseline-0-std-S01.jpeg",
                              "baseline-0-std-S02.jpeg"], canon)
    bank_s01 = h.build_bank(["baseline-0-std-S01.jpeg"], canon)
    bank_s02 = h.build_bank(["baseline-0-std-S02.jpeg"], canon)

    prev = {(r["sheet"], r["tid"]): r
            for r in json.load(open("verdict_tokens.json"))}
    out = []
    tot_ok = 0
    for f in files:
        if "-S01" in f:
            gF, gL = bank_s02
        elif "-S02" in f:
            gF, gL = bank_s01
        else:
            gF, gL = bank_both
        records, info = process_sheet_t0free(f, canon, gF, gL)
        m = re.match(r"([a-z]+)-(\d)-", f)
        fam, sev = (m.group(1), int(m.group(2))) if m else ("baseline", 0)
        line = []
        for tid in h.TIDS:
            recs = records[tid]
            g = sr.gt_entry(tid)
            vk = bytes.fromhex(g.get("vault_key_hex") or g.get("vaultKeyHex"))
            token = "cv0" + "".join(
                "?" if (r["blank"] or r["conf"] < CF or r["margin"] < MF)
                else r["pred"] for r in recs)[3:]
            Eb, eb = byte_budget(recs)
            try:
                cv.decode_pipeline(token, vk)
                ok = True
            except Exception:
                ok = False
            tot_ok += ok
            pv = prev[(f, tid)]["ok"]
            out.append(dict(sheet=f, tid=tid, fam=fam, sev=sev,
                            Eb=Eb, eb=eb, ok=ok, prev_ok=pv,
                            geom=info["geom"], sent=info["sent"]))
            line.append(("+" if ok else "-") + ("=" if ok == pv else "!"))
        print(f"{f:32s} sent={info['sent']:2d}/15 geom={info['geom']:10s} "
              f"T0..T4: {' '.join(line)}")
    json.dump(out, open("t0free_tokens.json", "w"), indent=1)
    both = [(r["ok"], r["prev_ok"]) for r in out]
    print(f"\nT0-free decode: {tot_ok}/135  (T0-selected path was "
          f"{sum(p for _, p in both)}/135)")
    flips = [(r["sheet"], r["tid"], r["prev_ok"], r["ok"])
             for r in out if r["ok"] != r["prev_ok"]]
    print("flips (prev -> t0free):")
    for s, t, a, b in flips:
        print(f"  {s:32s} {t}  {a} -> {b}")


if __name__ == "__main__":
    main()
