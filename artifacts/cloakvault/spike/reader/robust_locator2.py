"""Registration-based line locator, v2: rigid whole-layout refinement.

Stages:
  1. bottom-up wide-line harvest (unchanged from spike_reader logic, relaxed)
  2. scale-aware ink-profile fit for global (dy, sy), (dx, sx) priors
  3. match found lines to canonical 15, least-squares y/x affine from matches
  4. RIGID refinement against binary ink: grid-search small (dy, sy) for the
     whole 15-line layout at once, then per-line micro-adjust (+/-4 px),
     then grid-search (dx, sx) on the combined text-band column profile.
     A single stain cannot drag one line: 14 other lines anchor the layout.
Line boxes get uniform canonical height; x edges are rigid-mapped, never
locally snapped (monospace print has zero per-line x variation).
"""
import numpy as np
import cv2
import spike_reader as sr

Y_MATCH_TOL = 30
FULL_W_TOL = 0.04
H_MIN, H_MAX = 0.55, 1.9


def wide_lines(rect, min_w_frac=0.030):
    H, W = rect.shape
    mx, my = int(0.035 * W), int(0.02 * H)
    ink_full = sr.ink_mask(rect)
    ink = np.zeros_like(ink_full)
    ink[my:H - my, mx:W - mx] = ink_full[my:H - my, mx:W - mx]
    rowsum = ink.sum(1) / 255
    on = rowsum > (0.008 * W)
    bands, y = [], 0
    while y < H:
        if on[y]:
            y0 = y
            while y < H and on[y]:
                y += 1
            bands.append((y0, y))
        else:
            y += 1
    infos = []
    for (y0, y1) in bands:
        if y1 - y0 < 8:
            continue
        colsum = ink[y0:y1].sum(0) / 255
        win = max(11, int(W * 0.0072) | 1)
        sm = np.convolve(colsum, np.ones(win) / win, mode="same")
        if sm.max() <= 0:
            continue
        dense = sm > max(0.8, 0.15 * sm.max())
        best, cur0, x0b, x1b = 0, None, None, None
        for x in range(len(dense)):
            if dense[x] and cur0 is None:
                cur0 = x
            if (not dense[x] or x == len(dense) - 1) and cur0 is not None:
                x1r = x if not dense[x] else x + 1
                if x1r - cur0 > best:
                    best, x0b, x1b = x1r - cur0, cur0, x1r
                cur0 = None
        if best < int(W * min_w_frac):
            continue
        infos.append(dict(y0=y0, y1=y1, x0=int(x0b), x1=int(x1b),
                          w=int(x1b - x0b), h=y1 - y0))
    return infos, ink


def zprof(p):
    p = p.astype(np.float64)
    hi = np.percentile(p[p > 0], 90) if (p > 0).any() else 1.0
    p = np.clip(p, 0, hi)
    return (p - p.mean()) / (p.std() + 1e-9)


def best_shift(pa, pb, max_shift):
    best_s, best_v = 0, -1e18
    for s in range(-max_shift, max_shift + 1):
        if s >= 0:
            a, b = pa[s:], pb[:len(pb) - s]
        else:
            a, b = pa[:len(pa) + s], pb[-s:]
        n = min(len(a), len(b))
        if n < 100:
            continue
        v = float(np.dot(a[:n], b[:n])) / n
        if v > best_v:
            best_v, best_s = v, s
    return best_s, best_v


def profile_fit(pa, pcanon, max_shift=120, scales=None):
    if scales is None:
        scales = np.arange(0.980, 1.0205, 0.002)
    best = (1.0, 0, -1e18)
    for s in scales:
        pc = cv2.resize(pcanon.reshape(-1, 1).astype(np.float32),
                        (1, max(10, int(round(len(pcanon) * s)))),
                        interpolation=cv2.INTER_LINEAR).ravel().astype(np.float64)
        sh, v = best_shift(pa, pc, max_shift)
        if v > best[2]:
            best = (float(s), sh, v)
    return best


class CanonicalLayout:
    def __init__(self, baseline_path="baseline-0-std-S01.jpeg"):
        rect = sr.rectify(baseline_path)
        blocks = sr.find_token_lines(rect)
        assert len(blocks) == 5
        self.lines = sorted([li for b in blocks for li in b],
                            key=lambda i: i["y0"])
        assert len(self.lines) == 15
        _, ink = wide_lines(rect)
        self.rowp = zprof(ink.sum(1) / 255)
        self.colp = zprof(ink.sum(0) / 255)
        self.med_w = float(np.median([li["w"] for li in self.lines]))
        self.med_h = float(np.median([li["h"] for li in self.lines]))
        self.ycs = np.array([(li["y0"] + li["y1"]) / 2 for li in self.lines])
        # canonical combined column profile over the 15 text bands
        self.bandcol = zprof(self._bandcol(ink, self.ycs))
        self.x0s = np.array([li["x0"] for li in self.lines], dtype=float)
        self.x1s = np.array([li["x1"] for li in self.lines], dtype=float)
        p0 = float(np.median([(a - b + 1) / n for a, b, n in
                              zip(self.x1s, self.x0s, LINE_N)]))
        self.x0c, self.pitch = comb_fit_x(ink, self.ycs, self.med_h,
                                          float(np.median(self.x0s)), p0,
                                          x0_win=15.0, p_win=0.6)

    def _bandcol(self, ink, ycs):
        H, W = ink.shape
        acc = np.zeros(W, np.float64)
        hh = int(self.med_h / 2)
        for yc in ycs:
            a, b = max(0, int(yc) - hh), min(H, int(yc) + hh)
            acc += ink[a:b].sum(0) / 255
        return acc


def rigid_y(ink, ycs_prior, med_h, dy_range=14, sy_range=0.006, sy_step=0.001):
    """Grid-search (sy, dy) maximizing total ink mass inside 15 bands."""
    H = ink.shape[0]
    rowmass = ink.sum(1).astype(np.float64) / 255
    cum = np.concatenate([[0], np.cumsum(rowmass)])
    hh = med_h / 2
    yc_mid = ycs_prior.mean()
    best = (0.0, 1.0, -1)
    for sy in np.arange(1 - sy_range, 1 + sy_range + 1e-9, sy_step):
        base = yc_mid + (ycs_prior - yc_mid) * sy
        for dy in range(-dy_range, dy_range + 1):
            tot = 0.0
            for yc in base + dy:
                a = max(0, min(H - 1, int(round(yc - hh))))
                b = max(0, min(H, int(round(yc + hh))))
                tot += cum[b] - cum[a]
            if tot > best[2]:
                best = (float(dy), float(sy), tot)
    dy, sy, _ = best
    return yc_mid + (ycs_prior - yc_mid) * sy + dy


def micro_y(ink, ycs, xr, med_h, radius=7):
    """Per-line +/-radius px micro-adjust by band-mass argmax in the line's
    own x-range."""
    H = ink.shape[0]
    out = []
    hh = int(round(med_h / 2))
    for yc, (x0, x1) in zip(ycs, xr):
        strip = ink[:, max(0, x0):x1].sum(1).astype(np.float64) / 255
        cum = np.concatenate([[0], np.cumsum(strip)])
        best_d, best_m = 0, -1
        for d in range(-radius, radius + 1):
            a = max(0, min(H - 1, int(round(yc + d - hh))))
            b = max(0, min(H, int(round(yc + d + hh))))
            m = cum[b] - cum[a]
            if m > best_m:
                best_m, best_d = m, d
        out.append(yc + best_d)
    return np.array(out)




LINE_N = [48, 48, 46] * 5

def comb_fit_x(ink, ycs, med_h, x0_prior, pitch_prior,
               x0_win=12.0, p_win=0.35):
    """Fit (x0, pitch) of the monospace comb on the combined band column
    profile: maximize glyph-center mass minus cell-boundary mass."""
    H, W = ink.shape
    hh = int(med_h / 2)
    acc = np.zeros(W, np.float64)
    for yc in ycs:
        a, b = max(0, int(yc) - hh), min(H, int(yc) + hh)
        acc += ink[a:b].sum(0) / 255
    xs = np.arange(W, dtype=np.float64)
    best = (x0_prior, pitch_prior, -1e18)
    ks = np.arange(48)
    for p in np.arange(pitch_prior - p_win, pitch_prior + p_win + 1e-9, 0.005):
        centers_rel = (ks + 0.5) * p
        bounds_rel = np.arange(49) * p
        for x0 in np.arange(x0_prior - x0_win, x0_prior + x0_win + 1e-9, 0.25):
            c = np.interp(x0 + centers_rel, xs, acc)
            g = np.interp(x0 + bounds_rel, xs, acc)
            v = c.mean() - g.mean()
            if v > best[2]:
                best = (float(x0), float(p), float(v))
    return best[0], best[1]


def rigid_x(ink, ycs, canon, dx_prior, sx_prior,
            dx_range=14, sx_range=0.006, sx_step=0.001):
    """Grid-search (sx, dx) on the combined text-band column profile."""
    H, W = ink.shape
    hh = int(canon.med_h / 2)
    acc = np.zeros(W, np.float64)
    for yc in ycs:
        a, b = max(0, int(yc) - hh), min(H, int(yc) + hh)
        acc += ink[a:b].sum(0) / 255
    p = zprof(acc)
    best = (float(dx_prior), float(sx_prior), -1e18)
    for sx in np.arange(sx_prior - sx_range, sx_prior + sx_range + 1e-9, sx_step):
        pc = cv2.resize(canon.bandcol.reshape(-1, 1).astype(np.float32),
                        (1, max(10, int(round(len(canon.bandcol) * sx)))),
                        interpolation=cv2.INTER_LINEAR).ravel().astype(np.float64)
        for dx in range(int(dx_prior) - dx_range, int(dx_prior) + dx_range + 1):
            if dx >= 0:
                a, b = p[dx:], pc[:len(pc) - dx]
            else:
                a, b = p[:len(p) + dx], pc[-dx:]
            n = min(len(a), len(b))
            if n < 100:
                continue
            v = float(np.dot(a[:n], b[:n])) / n
            if v > best[2]:
                best = (float(dx), float(sx), v)
    return best[0], best[1]


def locate_blocks(rect, canon, debug=False):
    infos, ink = wide_lines(rect)
    sy0, dy0, _ = profile_fit(zprof(ink.sum(1) / 255), canon.rowp)
    sx0, dx0, _ = profile_fit(zprof(ink.sum(0) / 255), canon.colp)

    cands = [dict(**i, yc=(i["y0"] + i["y1"]) / 2) for i in infos]
    matches, used = {}, set()
    for ci, cl in enumerate(canon.lines):
        target = sy0 * (cl["y0"] + cl["y1"]) / 2 + dy0
        best_j, best_d = None, Y_MATCH_TOL + 1
        for j, cd in enumerate(cands):
            if j in used:
                continue
            if not (H_MIN * canon.med_h <= cd["h"] <= H_MAX * canon.med_h):
                continue
            d = abs(cd["yc"] - target)
            if d < best_d:
                best_d, best_j = d, j
        if best_j is not None:
            matches[ci] = cands[best_j]
            used.add(best_j)

    if len(matches) >= 2:
        yc_c = np.array([canon.ycs[ci] for ci in matches])
        yc_t = np.array([m["yc"] for m in matches.values()])
        ay, by = np.polyfit(yc_c, yc_t, 1)
    else:
        ay, by = float(sy0), float(dy0)
    ycs_prior = ay * canon.ycs + by

    full = [(canon.lines[ci], m) for ci, m in matches.items()
            if abs(m["w"] - canon.lines[ci]["w"]) <= FULL_W_TOL * canon.med_w]
    if len(full) >= 3:
        xc = np.array([c["x0"] for c, _ in full] + [c["x1"] for c, _ in full],
                      dtype=float)
        xt = np.array([m["x0"] for _, m in full] + [m["x1"] for _, m in full],
                      dtype=float)
        ex, fx = np.polyfit(xc, xt, 1)
    else:
        ex, fx = float(sx0), float(dx0)

    # rigid refinement
    ycs = rigid_y(ink, ycs_prior, canon.med_h)
    xr_prior = [(int(round(ex * a + fx)), int(round(ex * b + fx)))
                for a, b in zip(canon.x0s, canon.x1s)]
    ycs = micro_y(ink, ycs, xr_prior, canon.med_h)
    sxr = ex if abs(ex - 1) < 0.02 else sx0
    x0_prior = float(np.median(canon.x0s)) * sxr + (fx if abs(ex - 1) < 0.02 else dx0)
    pitch_prior = canon.pitch * sxr
    x0f, pf = comb_fit_x(ink, ycs, canon.med_h, x0_prior, pitch_prior)

    hh = canon.med_h / 2
    out_lines = []
    for yc, n in zip(ycs, LINE_N):
        x0 = x0f
        x1 = x0f + n * pf - 1.0
        out_lines.append(dict(y0=int(round(yc - hh)), y1=int(round(yc + hh)),
                              x0=int(round(x0)), x1=int(round(x1)),
                              w=int(round(x1 - x0)), h=int(round(2 * hh))))
    blocks = [out_lines[i:i + 3] for i in range(0, 15, 3)]
    diag = dict(found=len(infos), matched=len(matches),
                dy0=dy0, dx0=dx0, sy0=round(sy0, 4), sx0=round(sx0, 4),
                ay=round(float(ay), 5), ex=round(float(ex), 5),
                x0f=round(x0f, 2), pf=round(pf, 4))
    return blocks, diag
