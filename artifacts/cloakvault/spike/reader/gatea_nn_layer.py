"""Gate A spike, winning classifier layer (state at handoff).

Imports segmentation from spike_reader.py (rectify, enhance, find_token_lines,
LINE_LENS, gt_entry, GT). This layer replaces spike_reader's bbox-based
glyph_norm/cells_of_line/classify path, which is OBSOLETE for classification.

Proven pipeline:
  rectify (plain, 2480x3508) -> find_token_lines on plain rect
  enhance (CLAHE) -> fixed 19x34 windows on sheet-consensus grid
  centroid alignment (+/-3 px) -> gray + Sobel-magnitude features
  nearest-neighbour over ALL harvested samples (not class means)
  pooled bank: baseline sheets at blur sigmas (0, 0.8, 1.4, 2.0)
               + the target sheet's own T0 control block

Best result at handoff: S02 pristine, zero threshold, T1-T4:
  534/568 correct, 34 wrong (94.0%). Threshold sweep still to do.
Open anomaly: S01 self-cal (T0-only bank) gave only 413/568. T0-only banks
(142 samples) are too thin; pooled banks are the way forward.
"""
import numpy as np, cv2, json, sys
import spike_reader as sr

WIN_W, WIN_H, PAD = 19, 34, 3
BLUR_SIGMAS = (0, 0.8, 1.4, 2.0)


def line_grid(blocks):
    lines = [li for b in blocks for li in b]
    x0c = float(np.median([li["x0"] for li in lines]))
    pc = float(np.median([(li["x1"] - li["x0"] + 1) / n
                          for b in blocks for li, n in zip(b, sr.LINE_LENS)]))
    return x0c, pc


def line_ycenter(rect, li):
    band = rect[li["y0"]:li["y1"], li["x0"]:li["x1"]].astype(np.float64)
    ink = 255 - band
    prof = ink.sum(1)
    ys = np.arange(len(prof))
    return li["y0"] + float((prof * ys).sum() / (prof.sum() + 1e-9))


def cell_windows(rect_e, li, n, x0c, pc):
    yc = line_ycenter(rect_e, li)
    y0 = int(round(yc - WIN_H / 2)) - PAD
    out = []
    for k in range(n):
        xc = x0c + (k + 0.5) * pc
        x0 = int(round(xc - WIN_W / 2)) - PAD
        win = rect_e[max(0, y0):y0 + WIN_H + 2 * PAD, max(0, x0):x0 + WIN_W + 2 * PAD]
        if win.shape != (WIN_H + 2 * PAD, WIN_W + 2 * PAD):
            w2 = np.full((WIN_H + 2 * PAD, WIN_W + 2 * PAD), 255, np.uint8)
            w2[:win.shape[0], :win.shape[1]] = win
            win = w2
        out.append(win)
    return out


def centroid_align(win):
    inner = win[PAD:PAD + WIN_H, PAD:PAD + WIN_W].astype(np.float64)
    ink = np.clip(inner.mean() - inner, 0, None)
    tot = ink.sum()
    if tot < 1e-3:
        return win[PAD:PAD + WIN_H, PAD:PAD + WIN_W], True
    xs = np.arange(WIN_W); ys = np.arange(WIN_H)
    cx = (ink.sum(0) * xs).sum() / tot
    cy = (ink.sum(1) * ys).sum() / tot
    dx = max(-PAD, min(PAD, int(round(cx - (WIN_W - 1) / 2))))
    dy = max(-PAD, min(PAD, int(round(cy - (WIN_H - 1) / 2))))
    return win[PAD + dy:PAD + dy + WIN_H, PAD + dx:PAD + dx + WIN_W], False


def feat_from_gray(g):
    g = g.astype(np.float32)
    gz = (g - g.mean()) / (g.std() + 1e-6)
    sx = cv2.Sobel(g, cv2.CV_32F, 1, 0, 3)
    sy = cv2.Sobel(g, cv2.CV_32F, 0, 1, 3)
    mag = np.sqrt(sx * sx + sy * sy)
    mz = (mag - mag.mean()) / (mag.std() + 1e-6)
    v = np.concatenate([gz.ravel(), mz.ravel()])
    return v / (np.linalg.norm(v) + 1e-9)


def harvest_wins(rect_e, blocks, tids, x0c, pc):
    """Aligned windows + labels from ground truth for the named token blocks."""
    wins, labels = [], []
    for b, tid in zip(blocks, ("T0", "T1", "T2", "T3", "T4")):
        if tid not in tids:
            continue
        tok = sr.gt_entry(tid)["token"]
        for li, gtl, n in zip(b, [tok[0:48], tok[48:96], tok[96:142]], sr.LINE_LENS):
            for win, ch in zip(cell_windows(rect_e, li, n, x0c, pc), gtl):
                a, blank = centroid_align(win)
                if not blank:
                    wins.append(a); labels.append(ch)
    return wins, labels


def build_global_bank(baseline_paths, sigmas=BLUR_SIGMAS):
    """All tokens of the baseline sheets, blur-augmented. Returns (features, labels)."""
    feats, labels = [], []
    for path in baseline_paths:
        rect = sr.rectify(path); rect_e = sr.enhance(rect)
        blocks = sr.find_token_lines(rect)
        assert len(blocks) == 5, f"{path}: blocks={len(blocks)}"
        x0c, pc = line_grid(blocks)
        wins, labs = harvest_wins(rect_e, blocks, ("T0", "T1", "T2", "T3", "T4"), x0c, pc)
        for win, lab in zip(wins, labs):
            for sig in sigmas:
                s = win if sig == 0 else cv2.GaussianBlur(win, (0, 0), sig)
                feats.append(feat_from_gray(s)); labels.append(lab)
    return np.stack(feats), labels


def classify_sheet_nn(path, gF, gL, conf_floor=0.0, margin_floor=0.0,
                      use_own_t0=True, fallback_blocks=None):
    """Classify T0-T4 of one sheet. Pools the global bank with the sheet's own
    T0 block (in-sheet control) unless use_own_t0=False.
    Returns (results dict tid -> (string_with_?_erasures, [(conf, margin), ...]), note)."""
    rect = sr.rectify(path); rect_e = sr.enhance(rect)
    blocks = sr.find_token_lines(rect)
    note = None
    if len(blocks) != 5 and fallback_blocks is not None:
        blocks = fallback_blocks; note = "fallback-layout"
    if len(blocks) != 5:
        return None, f"blocks={len(blocks)}"
    x0c, pc = line_grid(blocks)
    F, L = gF, list(gL)
    if use_own_t0:
        wins, labs = harvest_wins(rect_e, blocks, ("T0",), x0c, pc)
        if wins:
            F = np.vstack([gF, np.stack([feat_from_gray(w) for w in wins])])
            L = list(gL) + labs
    Larr = np.array(L)
    out = {}
    for b, tid in zip(blocks, ("T0", "T1", "T2", "T3", "T4")):
        chars, dets = [], []
        for li, n in zip(b, sr.LINE_LENS):
            for win in cell_windows(rect_e, li, n, x0c, pc):
                a, blank = centroid_align(win)
                if blank:
                    chars.append("?"); dets.append((0.0, 0.0)); continue
                v = feat_from_gray(a)
                sc = F @ v
                per = {}
                for kk, s2 in zip(Larr, sc):
                    if kk not in per or s2 > per[kk]:
                        per[kk] = s2
                rk = sorted(per.items(), key=lambda t: -t[1])
                c1, c2 = rk[0][1], rk[1][1]
                if c1 < conf_floor or (c1 - c2) < margin_floor:
                    chars.append("?")
                else:
                    chars.append(rk[0][0])
                dets.append((float(c1), float(c1 - c2)))
        out[tid] = ("".join(chars), dets)
    return out, note


def score_vs_gt(read, tid):
    gt = sr.gt_entry(tid)["token"]
    return dict(len=len(read),
                correct=sum(1 for a, b in zip(read, gt) if a == b),
                erasures=read.count("?"),
                silent_wrong=sum(1 for a, b in zip(read, gt) if a != "?" and a != b))


def try_decode(read, tid, repo="/tmp/qkcheck/artifacts/cloakvault"):
    """Feed an erasure-marked token to the real decode pipeline. Returns dict."""
    sys.path.insert(0, repo + "/interop/python")
    from cloakvault_v3 import decode_pipeline
    entry = sr.gt_entry(tid)
    vk = entry.get("vault_key_hex")
    if vk is None:
        def walk(o):
            if isinstance(o, dict):
                if "vault_key_hex" in o: return o["vault_key_hex"]
                for v in o.values():
                    r = walk(v)
                    if r: return r
            if isinstance(o, list):
                for v in o:
                    r = walk(v)
                    if r: return r
        vk = walk(sr.GT)
    try:
        out = decode_pipeline(read, bytes.fromhex(vk))
        return dict(ok=True, detail=out)
    except Exception as e:
        return dict(ok=False, detail=repr(e))


if __name__ == "__main__":
    baselines = ["baseline-0-std-S01.jpeg", "baseline-0-std-S02.jpeg"]
    gF, gL = build_global_bank(baselines)
    print("global bank:", gF.shape[0], "samples")
    res, note = classify_sheet_nn("baseline-0-std-S02.jpeg", gF, gL, 0.0, 0.0)
    tot = dict(len=0, correct=0, erasures=0, silent_wrong=0)
    for tid in ("T1", "T2", "T3", "T4"):
        s = score_vs_gt(res[tid][0], tid)
        for k in tot:
            tot[k] += s[k]
    print("S02 sanity:", tot, note or "")
