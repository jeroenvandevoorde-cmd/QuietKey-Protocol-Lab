# ============================================================================
# HISTORICAL SPIKE LOCATOR.
# Preserved as-run for evidence reproduction (renamed from locate_reader.py;
# code below is byte-identical to the as-run original).
# Contains current-wrapper-specific assumptions (domain, PREFIX=39, "&v=1",
# fixed line lengths [87, 48, 50], fixed TOKEN_SLICE) and MUST NOT be used
# as the foundation of the formal Gate A reader. The existing 2/2 S26/S27
# result remains valid evidence for that historical wrapper.
# The current structural locator is reader/structural_locator.py.
# ============================================================================
"""Read T5 from the locate pages (S26/S27): full recipe document with the
token dressed as a browser-print footer. Structural extraction: bottom three
wide monospace lines are the token lines; line 1 carries a 39-char URL prefix,
line 3 a 4-char '&v=1' suffix. Footer glyphs are smaller than the token
sheets, so the strip is rescaled to bank pitch before classification."""
import sys, numpy as np, cv2
import spike_reader as sr
import gatea_nn_layer as nn
import robust_locator2 as rl
import sweep_harness2 as h

sys.path.insert(0, '/tmp/qkcheck/artifacts/cloakvault/interop/python')
import cloakvault_v3 as cv

BANK_PITCH = 18.7175
PREFIX = 39            # 'https://arecipeforamaster.com/print?id='
LINE_CHARS = [87, 48, 50]          # printed chars per footer line
TOKEN_SLICE = [(39, 87), (0, 48), (0, 46)]   # payload cells per line
CF, MF = 0.64, 0.02


def read_locate(path, gF, gL):
    rect = sr.rectify(path)
    infos, ink = rl.wide_lines(rect)
    infos = sorted(infos, key=lambda i: i["y0"])
    foot = [li for li in infos if li["x1"] - li["x0"] > 850][-3:]
    heights = [li["y1"] - li["y0"] for li in foot]
    med_h = float(np.median(heights))

    # per-line comb fit at native footer scale
    grids = []
    for li, nchars in zip(foot, LINE_CHARS):
        yc = (li["y0"] + li["y1"]) / 2
        run_w = li["x1"] - li["x0"] + 1
        p0 = run_w / nchars
        xs = np.arange(ink.shape[1], dtype=np.float64)
        a, b = max(0, int(yc - med_h)), int(yc + med_h)
        prof = ink[a:b].sum(0).astype(np.float64) / 255
        ks = np.arange(nchars)
        best = None
        for dp in np.arange(-0.30, 0.301, 0.01):
            p = p0 + dp
            cen = (ks + 0.5) * p
            bnd = np.arange(nchars + 1) * p
            for dx in np.arange(-8, 8.01, 0.25):
                x0 = li["x0"] + dx
                v = np.interp(x0 + cen, xs, prof).mean() - \
                    np.interp(x0 + bnd, xs, prof).mean()
                if best is None or v > best[0]:
                    best = (v, x0, p)
        grids.append((yc, best[1], best[2]))

    pitch_f = float(np.median([g[2] for g in grids]))
    s = BANK_PITCH / pitch_f

    # rescale the footer strip to bank pitch and classify payload cells
    y_top = max(0, foot[0]["y0"] - 60)
    y_bot = min(rect.shape[0], foot[2]["y1"] + 60)
    strip = sr.enhance(rect)[y_top:y_bot, :]
    strip_s = cv2.resize(strip, None, fx=s, fy=s,
                         interpolation=cv2.INTER_CUBIC)

    feats = []
    for (yc, x0, p), (c0, c1) in zip(grids, TOKEN_SLICE):
        ycs_s = (yc - y_top) * s
        for k in range(c0, c1):
            xc = (x0 + (k + 0.5) * p) * s
            y0w = int(round(ycs_s - nn.WIN_H / 2)) - nn.PAD
            x0w = int(round(xc - nn.WIN_W / 2)) - nn.PAD
            win = strip_s[max(0, y0w):y0w + nn.WIN_H + 2 * nn.PAD,
                          max(0, x0w):x0w + nn.WIN_W + 2 * nn.PAD]
            if win.shape != (nn.WIN_H + 2 * nn.PAD, nn.WIN_W + 2 * nn.PAD):
                w2 = np.full((nn.WIN_H + 2 * nn.PAD,
                              nn.WIN_W + 2 * nn.PAD), 255, np.uint8)
                w2[:win.shape[0], :win.shape[1]] = win
                win = w2
            a, blank = nn.centroid_align(win)
            feats.append((None if blank else nn.feat_from_gray(a), blank))

    preds, confs, margs = h.nn_score(feats, gF, gL)
    gt = sr.gt_entry("T5")["token"]
    recs = [dict(gt=gt[i], pred=preds[i], conf=confs[i], margin=margs[i],
                 blank=feats[i][1]) for i in range(142)]
    return recs, dict(pitch_f=round(pitch_f, 3), scale=round(s, 4),
                      grids=[(round(g[0], 1), round(g[1], 1),
                              round(g[2], 3)) for g in grids])


def main():
    canon = rl.CanonicalLayout("baseline-0-std-S01.jpeg")
    gF, gL = h.build_bank(["baseline-0-std-S01.jpeg",
                           "baseline-0-std-S02.jpeg"], canon)
    g5 = sr.gt_entry("T5")
    vk = bytes.fromhex(g5.get("vault_key_hex") or g5.get("vaultKeyHex"))
    out = {}
    for f in ("locate-0-std-S26.jpeg", "locate-1-std-S27.jpeg"):
        recs, diag = read_locate(f, gF, gL)
        raw = sum(1 for r in recs if not r["blank"] and r["pred"] == r["gt"])
        chars, E, e = [], 0, 0
        for r in recs:
            if r["blank"] or r["conf"] < CF or r["margin"] < MF:
                chars.append("?"); e += 1
            else:
                chars.append(r["pred"])
                if r["pred"] != r["gt"]:
                    E += 1
        token = "cv0" + "".join(chars)[3:]
        Eb, eb = 0, 0
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
        Eb, eb = len(err_b), len(era_b)
        try:
            cv.decode_pipeline(token, vk)
            ok = True
        except Exception as ex:
            ok = False
        print(f"{f}: raw {raw}/142 | E={E} e={e} | bytes 2*{Eb}+{eb}="
              f"{2*Eb+eb} | decode {'SUCCESS' if ok else 'FAIL'} | {diag}")
        out[f] = dict(raw=raw, E=E, e=e, Eb=Eb, eb=eb, ok=ok, **diag)
    import json
    json.dump(out, open("locate_results.json", "w"), indent=1)


if __name__ == "__main__":
    main()
