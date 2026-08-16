"""Stock OCR baseline on the 27 token sheets (blueprint 3.2, Gate A1
reader comparison). Tesseract 5.3.4, line-localized crops using the same
rectification and line geometry as the QuietKey reader, which is generous
to OCR: it gets perfect line localization for free and is measured only on
the reading step.

Variant A: stock, --psm 7 single line.
Variant B: charset whitelist (the 32 Bech32 characters), --psm 7.

Stock OCR has no erasure concept: every mistake is silent. Token assembly
requires three exact-length lines; a single insertion or deletion destroys
the positional structure and the token is unrecoverable before RS even
runs. No sentinel repair is applied: stock means stock.
"""
import subprocess, tempfile, os, sys, glob, json, difflib
import numpy as np, cv2
import spike_reader as sr
import robust_locator2 as rl
import sweep_harness2 as h

sys.path.insert(0, '/tmp/qkcheck/artifacts/cloakvault/interop/python')
import cloakvault_v3 as cv

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
LINE_LENS = [48, 48, 46]


def ocr_line(img, whitelist):
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as t:
        cv2.imwrite(t.name, img)
        path = t.name
    cmd = ["tesseract", path, "stdout", "--psm", "7"]
    if whitelist:
        cmd += ["-c", f"tessedit_char_whitelist={CHARSET}"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=30).stdout
    finally:
        os.unlink(path)
    return "".join(out.split())


def main():
    files = sorted(f for f in glob.glob("*.jpeg")
                   if not f.startswith("locate"))
    canon = rl.CanonicalLayout("baseline-0-std-S01.jpeg")
    res = {"A": dict(match=0, gtlen=0, exact=0, lines=0, dec=0),
           "B": dict(match=0, gtlen=0, exact=0, lines=0, dec=0)}
    per_sheet = []
    for f in files:
        rect = sr.rectify(f)
        hyps, _ = h.geometry_hypotheses(rect, canon)
        _, ycs, x0s, ps = hyps[0]
        crops = []
        for i in range(15):
            n = rl.LINE_N[i]
            y0 = int(ycs[i] - 24); y1 = int(ycs[i] + 24)
            x0 = int(x0s[i] - 8); x1 = int(x0s[i] + n * ps[i] + 8)
            crops.append(rect[max(0, y0):y1, max(0, x0):x1])
        row = {"sheet": f}
        for var, wl in (("A", False), ("B", True)):
            reads = [ocr_line(c, wl) for c in crops]
            dec = 0
            li = 0
            sheet_match = sheet_gtlen = sheet_exact = 0
            for tid in h.TIDS:
                gt = sr.gt_entry(tid)["token"]
                gls = [gt[0:48], gt[48:96], gt[96:142]]
                toklines = reads[li:li + 3]
                li += 3
                ok_shape = all(len(r) == L
                               for r, L in zip(toklines, LINE_LENS))
                for r, g in zip(toklines, gls):
                    sm = difflib.SequenceMatcher(None, r, g)
                    sheet_match += sum(b.size for b in
                                       sm.get_matching_blocks())
                    sheet_gtlen += len(g)
                    sheet_exact += (len(r) == len(g))
                if ok_shape:
                    token = "".join(toklines)
                    g = sr.gt_entry(tid)
                    vk = bytes.fromhex(g.get("vault_key_hex")
                                       or g.get("vaultKeyHex"))
                    try:
                        cv.decode_pipeline(token, vk)
                        dec += 1
                    except Exception:
                        pass
            res[var]["match"] += sheet_match
            res[var]["gtlen"] += sheet_gtlen
            res[var]["exact"] += sheet_exact
            res[var]["lines"] += 15
            res[var]["dec"] += dec
            row[var] = dict(acc=round(sheet_match / sheet_gtlen, 3),
                            exact=sheet_exact, dec=dec)
        per_sheet.append(row)
        print(f"{f:32s} A: acc={row['A']['acc']:.3f} "
              f"exact={row['A']['exact']:2d}/15 dec={row['A']['dec']} | "
              f"B: acc={row['B']['acc']:.3f} "
              f"exact={row['B']['exact']:2d}/15 dec={row['B']['dec']}")
    print()
    for var in ("A", "B"):
        r = res[var]
        print(f"variant {var}: char accuracy {r['match']/r['gtlen']:.3f}, "
              f"exact-length lines {r['exact']}/{r['lines']}, "
              f"decode {r['dec']}/135")
    json.dump(dict(totals=res, per_sheet=per_sheet),
              open("ocr_results.json", "w"), indent=1)


if __name__ == "__main__":
    main()
