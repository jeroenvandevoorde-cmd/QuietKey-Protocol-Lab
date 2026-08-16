"""Gate A spike reader — miniature 'intended reader' (Reader B).
Harvests glyph templates from the pristine baseline, classifies every character
cell with a confidence score, marks low-confidence cells as erasures ('?'),
scores against ground truth, and hands erasure-marked tokens to the real
Python decode pipeline.
"""
import cv2, numpy as np, json, sys

CELL_W, CELL_H = 24, 32
LINE_LENS = [48, 48, 46]
GT = json.load(open("/tmp/qkcheck/artifacts/cloakvault/spike/tokens.json"))

def gt_entry(tid):
    def walk(o):
        if isinstance(o, dict) and o.get("id") == tid: return o
        if isinstance(o, dict):
            for v in o.values():
                r = walk(v)
                if r: return r
        if isinstance(o, list):
            for v in o:
                r = walk(v)
                if r: return r
    return walk(GT)

def rectify(path, W=2480, H=3508):
    img = cv2.imread(path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    page = max(cnts, key=cv2.contourArea)
    peri = cv2.arcLength(page, True)
    quad = cv2.approxPolyDP(page, 0.02 * peri, True)
    if len(quad) != 4:  # torn corners etc: fall back to min-area rect
        quad = cv2.boxPoints(cv2.minAreaRect(page)).astype(np.float32).reshape(4, 1, 2)
    pts = quad.reshape(4, 2).astype(np.float32)
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    tl, br = pts[np.argmin(s)], pts[np.argmax(s)]
    tr, bl = pts[np.argmin(d)], pts[np.argmax(d)]
    M = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], np.float32),
                                    np.array([[0, 0], [W, 0], [W, H], [0, H]], np.float32))
    return cv2.warpPerspective(gray, M, (W, H))

def enhance(rect):
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(16, 16))
    return clahe.apply(rect)

def ink_mask(rect):
    # adaptive threshold: ink=1. Blur first to tame paper texture.
    bl = cv2.GaussianBlur(rect, (3, 3), 0)
    bs = max(25, int(rect.shape[1] * 0.0149) | 1)
    th = cv2.adaptiveThreshold(bl, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                               cv2.THRESH_BINARY_INV, bs, 12)
    return th

def find_token_lines(rect):
    """Return 15 (y0,y1,x0,x1) line boxes: 5 blocks x 3 lines, top→bottom."""
    H, W = rect.shape
    mx, my = int(0.035 * W), int(0.02 * H)          # inset: kill border artifacts
    ink_full = ink_mask(rect)
    ink = np.zeros_like(ink_full)
    ink[my:H - my, mx:W - mx] = ink_full[my:H - my, mx:W - mx]
    rowsum = ink.sum(1) / 255
    on = rowsum > (0.008 * W)
    bands = []
    y = 0
    while y < H:
        if on[y]:
            y0 = y
            while y < H and on[y]: y += 1
            bands.append((y0, y))
        else:
            y += 1
    infos = []
    for (y0, y1) in bands:
        if y1 - y0 < 8: continue
        colsum = ink[y0:y1].sum(0) / 255
        win = max(11, int(W * 0.0072) | 1)
        sm = np.convolve(colsum, np.ones(win) / win, mode="same")
        if sm.max() <= 0: continue
        dense = sm > max(0.8, 0.15 * sm.max())
        # widest contiguous dense run = the text line, immune to specks/pencil marks
        best, cur0, x0b, x1b = 0, None, None, None
        for x in range(len(dense)):
            if dense[x] and cur0 is None: cur0 = x
            if (not dense[x] or x == len(dense) - 1) and cur0 is not None:
                x1r = x if not dense[x] else x + 1
                if x1r - cur0 > best: best, x0b, x1b = x1r - cur0, cur0, x1r
                cur0 = None
        if best < int(W * 0.057): continue                      # drops labels, bar ticks, pencil IDs
        infos.append(dict(y0=y0, y1=y1, x0=int(x0b), x1=int(x1b),
                          w=int(x1b - x0b), h=y1 - y0))
    if not infos: return []
    # token lines share one width (15 of them, +/-3%): find the modal width cluster
    widths = sorted(i["w"] for i in infos)
    best_w, best_n = None, 0
    for w in widths:
        n = sum(1 for v in widths if 0.90 * w <= v <= 1.06 * w)
        if n > best_n: best_n, best_w = n, w
    cand = [i for i in infos if 0.90 * best_w <= i["w"] <= 1.06 * best_w]
    x0s = sorted(i["x0"] for i in cand)
    x0m = x0s[len(x0s) // 2]
    cand = [i for i in cand if abs(i["x0"] - x0m) <= int(W * 0.0121)]
    cand.sort(key=lambda i: i["y0"])
    groups, cur = [], [cand[0]]
    for a, b in zip(cand, cand[1:]):
        if b["y0"] - a["y1"] < 2.2 * a["h"]:
            cur.append(b)
        else:
            groups.append(cur); cur = [b]
    groups.append(cur)
    trips = [g for g in groups if len(g) == 3]
    return trips  # list of blocks, each = 3 line-infos

def cells_of_line(rect, li, n):
    y0, y1, x0, x1 = li["y0"], li["y1"], li["x0"], li["x1"]
    pitch = (x1 - x0 + 1) / n
    pad_y = max(3, (y1 - y0) // 5)
    out = []
    for k in range(n):
        cx0 = int(round(x0 + k * pitch)) - 1
        cx1 = int(round(x0 + (k + 1) * pitch)) + 1
        cell = rect[max(0, y0 - pad_y):y1 + pad_y, max(0, cx0):cx1]
        out.append(glyph_norm(cell))
    return out

def glyph_norm(cell):
    """Position/scale-invariant glyph: threshold for bbox only, GRAY content,
    reject border slivers (neighbor bleed). None = blank cell."""
    if cell.size == 0: return None
    m, s = cell.mean(), cell.std()
    th = (cell < (m - 0.8 * s)).astype(np.uint8) * 255
    num, lab, stats, cents = cv2.connectedComponentsWithStats(th)
    if num <= 1: return None
    H, W = th.shape
    keep = []
    for i in range(1, num):
        if stats[i, cv2.CC_STAT_AREA] < 4: continue
        L = stats[i, cv2.CC_STAT_LEFT]; Wd = stats[i, cv2.CC_STAT_WIDTH]
        if (L <= 1 or L + Wd >= W - 1) and Wd <= 3: continue
        if abs(cents[i][0] - W / 2) > W * 0.42: continue
        keep.append(i)
    if not keep: return None
    xs0 = min(stats[i, cv2.CC_STAT_LEFT] for i in keep)
    ys0 = min(stats[i, cv2.CC_STAT_TOP] for i in keep)
    xs1 = max(stats[i, cv2.CC_STAT_LEFT] + stats[i, cv2.CC_STAT_WIDTH] for i in keep)
    ys1 = max(stats[i, cv2.CC_STAT_TOP] + stats[i, cv2.CC_STAT_HEIGHT] for i in keep)
    g = cell[ys0:ys1, xs0:xs1].astype(np.float32)
    if g.size == 0: return None
    gh, gw = g.shape
    scale = min((CELL_H - 2) / gh, (CELL_W - 2) / gw)
    nh, nw = max(1, int(round(gh * scale))), max(1, int(round(gw * scale)))
    g = cv2.resize(g, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.full((CELL_H, CELL_W), float(np.percentile(g, 95)), np.float32)
    oy, ox = (CELL_H - nh) // 2, (CELL_W - nw) // 2
    canvas[oy:oy + nh, ox:ox + nw] = g
    return canvas.astype(np.uint8)

def norm(c):
    c = c.astype(np.float32)
    c = (c - c.mean()) / (c.std() + 1e-6)
    return c

def harvest(paths, tids=("T0", "T1", "T2", "T3", "T4")):
    bank = {}
    for path in paths:
        rect = rectify(path)
        rect_e = enhance(rect)
        blocks = find_token_lines(rect)
        assert len(blocks) == 5, f"{path}: found {len(blocks)} blocks"
        for b, tid in zip(blocks, tids):
            lines = gt_entry(tid)["wrapped_lines"] if gt_entry(tid).get("wrapped_lines") else None
            tok = gt_entry(tid)["token"]
            lines = [tok[0:48], tok[48:96], tok[96:142]]
            for li, gtl, n in zip(b, lines, LINE_LENS):
                for cell, ch in zip(cells_of_line(rect_e, li, n), gtl):
                    if cell is not None:
                        bank.setdefault(ch, []).append(norm(cell))
    means = {}
    for ch, v in bank.items():
        base = np.mean(np.stack(v), 0)
        variants = [base]
        for sig in (1.0, 1.8):
            variants.append(cv2.GaussianBlur(base, (0, 0), sig))
        means[ch] = variants
    last_blocks = find_token_lines(rectify(paths[0]))
    return means, {ch: len(v) for ch, v in bank.items()}, last_blocks

def classify_sheet(path, means, conf_floor, margin_floor, fallback_blocks=None):
    """Return per-token: read string with '?' erasures + per-char (pred, conf, margin)."""
    rect = rectify(path)
    rect_e = enhance(rect)
    blocks = find_token_lines(rect)
    used_fallback = False
    if len(blocks) != 5 and fallback_blocks is not None:
        blocks = fallback_blocks; used_fallback = True
    if len(blocks) != 5:
        return None, f"blocks={len(blocks)}"
    keys, mats = [], []
    for ch, variants in means.items():
        for v in variants:
            keys.append(ch); mats.append(v)
    Mf = np.stack(mats).reshape(len(mats), -1)
    Mf = Mf / (np.linalg.norm(Mf, axis=1, keepdims=True) + 1e-9)
    results = {}
    for b, tid in zip(blocks, ("T0", "T1", "T2", "T3", "T4")):
        chars, details = [], []
        for li, n in zip(b, LINE_LENS):
            for cell in cells_of_line(rect_e, li, n):
                if cell is None:
                    chars.append("?"); details.append((None, 0.0, 0.0)); continue
                v = norm(cell).reshape(-1)
                v = v / (np.linalg.norm(v) + 1e-9)
                scores = Mf @ v
                # best score per CLASS (variants collapse to their class)
                best = {}
                for kk, sc in zip(keys, scores):
                    if kk not in best or sc > best[kk]: best[kk] = sc
                ranked = sorted(best.items(), key=lambda t: -t[1])
                pred, c1 = ranked[0][0], ranked[0][1]
                c2 = ranked[1][1]
                if c1 < conf_floor or (c1 - c2) < margin_floor:
                    chars.append("?")
                else:
                    chars.append(pred)
                details.append((pred, float(c1), float(c1 - c2)))
        results[tid] = ("".join(chars), details)
    return results, ("fallback-layout" if used_fallback else None)

def score_vs_gt(read, tid):
    gt = gt_entry(tid)["token"]
    n = min(len(read), len(gt))
    correct = sum(1 for a, b in zip(read, gt) if a == b)
    erasures = read.count("?")
    silent_wrong = sum(1 for a, b in zip(read, gt) if a != "?" and a != b)
    return dict(len=len(read), correct=correct, erasures=erasures, silent_wrong=silent_wrong)
