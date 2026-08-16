"""Gate A sweep harness v2: geometry hypothesis ensemble, T0-selected.

Per sheet, build up to 6 grid hypotheses ({rigid+micro y, regression y} x
{comb x, regression x, profile-prior x}), classify the T0 control block under
each with the global bank, and keep the winner. T0 is printed on every sheet
as a known-content control; using it to calibrate capture geometry is its
designed purpose. Sheets whose best T0 read stays poor are flagged
GEOM-UNCERTAIN (damaged T0 and/or unresolved geometry).

Records format is unchanged for the downstream threshold sweep.
"""
import numpy as np, cv2, glob, pickle
import spike_reader as sr
import gatea_nn_layer as nn
import robust_locator2 as rl

TIDS = ("T0", "T1", "T2", "T3", "T4")
T0_HEALTH_MIN = 120
WIN_W, WIN_H, PAD = nn.WIN_W, nn.WIN_H, nn.PAD


def windows_from_grid(rect_e, ycs, x0, pitch):
    """Fixed windows from explicit grid; x0/pitch may be scalars or per-line
    arrays."""
    H, W = rect_e.shape
    x0a = np.broadcast_to(np.asarray(x0, dtype=float), (len(ycs),))
    pa = np.broadcast_to(np.asarray(pitch, dtype=float), (len(ycs),))
    per_line = []
    for yc, n, x0, pitch in zip(ycs, rl.LINE_N, x0a, pa):
        y0 = int(round(yc - WIN_H / 2)) - PAD
        wins = []
        for k in range(n):
            xc = x0 + (k + 0.5) * pitch
            xw0 = int(round(xc - WIN_W / 2)) - PAD
            win = rect_e[max(0, y0):y0 + WIN_H + 2 * PAD,
                         max(0, xw0):xw0 + WIN_W + 2 * PAD]
            if win.shape != (WIN_H + 2 * PAD, WIN_W + 2 * PAD):
                w2 = np.full((WIN_H + 2 * PAD, WIN_W + 2 * PAD), 255, np.uint8)
                w2[:win.shape[0], :win.shape[1]] = win
                win = w2
            wins.append(win)
        per_line.append(wins)
    return per_line


def feats_of_line(wins):
    out = []
    for win in wins:
        a, blank = nn.centroid_align(win)
        out.append((None if blank else nn.feat_from_gray(a), blank))
    return out


def nn_score(feats, F, L):
    """Predictions for a list of (feat|None, blank)."""
    classes = sorted(set(L))
    Larr = np.array(L)
    idx = {c: np.where(Larr == c)[0] for c in classes}
    live = [i for i, (f, b) in enumerate(feats) if not b]
    preds = [None] * len(feats)
    confs = [0.0] * len(feats)
    margs = [0.0] * len(feats)
    if live:
        V = np.stack([feats[i][0] for i in live])
        S = F @ V.T
        CM = np.stack([S[idx[c]].max(0) for c in classes])
        order = np.argsort(-CM, axis=0)
        for j, i in enumerate(live):
            k1, k2 = order[0, j], order[1, j]
            preds[i] = classes[k1]
            confs[i] = float(CM[k1, j])
            margs[i] = float(CM[k1, j] - CM[k2, j])
    return preds, confs, margs




def per_line_comb(ink, ycs, x0g, pg, med_h):
    """Per-line comb (x0, pitch) refinement with smooth-in-y robust fallback.
    Handles y-dependent x residuals (paper curl, homography residual)."""
    H, W = ink.shape
    hh = int(med_h / 2)
    xs = np.arange(W, dtype=np.float64)
    profs, masses = [], []
    for yc in ycs:
        a, b = max(0, int(yc) - hh), min(H, int(yc) + hh)
        p = ink[a:b].sum(0).astype(np.float64) / 255
        profs.append(p)
        masses.append(p.sum())
    med_mass = np.median(masses)
    raw = []
    for prof, mass, n in zip(profs, masses, rl.LINE_N):
        if mass < 0.25 * med_mass:
            raw.append(None)
            continue
        ks = np.arange(n)
        best = None
        for dp in np.arange(-0.12, 0.1201, 0.01):
            p = pg + dp
            cen = (ks + 0.5) * p
            bnd = np.arange(n + 1) * p
            for dx in np.arange(-6, 6.01, 0.25):
                cm = np.interp(x0g + dx + cen, xs, prof).mean()
                bm = np.interp(x0g + dx + bnd, xs, prof).mean()
                v = cm - bm
                if best is None or v > best[0]:
                    best = (v, x0g + dx, p, cm, bm)
        contrast = best[0] / (best[3] + best[4] + 1e-9)
        raw.append((best[1], best[2]) if contrast > 0.08 else None)
    idx = [i for i, v in enumerate(raw) if v is not None]
    if len(idx) >= 4:
        ys = np.array([ycs[i] for i in idx])
        x0v = np.array([raw[i][0] for i in idx])
        pv = np.array([raw[i][1] for i in idx])
        # iterative outlier rejection: the clean-line consensus wins
        keep = np.ones(len(idx), bool)
        for _ in range(3):
            if keep.sum() < 4:
                break
            cx = np.polyfit(ys[keep], x0v[keep], 1)
            resid = np.abs(np.polyval(cx, ys) - x0v)
            new = resid <= 1.2
            if new.sum() >= 4:
                keep = new
        cx = np.polyfit(ys[keep], x0v[keep], 1)
        cp = np.polyfit(ys[keep], pv[keep], 1)
        x0_fit = np.polyval(cx, ycs)
        p_fit = np.polyval(cp, ycs)
        kept = set(np.array(idx)[keep].tolist())
        raw = [raw[i] if i in kept else None for i in range(15)]
    else:
        x0_fit = np.full(15, x0g)
        p_fit = np.full(15, pg)
    x0s, ps = [], []
    for i in range(15):
        if raw[i] is not None and abs(raw[i][0] - x0_fit[i]) <= 1.5 \
                and abs(raw[i][1] - p_fit[i]) <= 0.03:
            x0s.append(raw[i][0])
            ps.append(raw[i][1])
        else:
            x0s.append(float(x0_fit[i]))
            ps.append(float(p_fit[i]))
    return np.array(x0s), np.array(ps)


def geometry_hypotheses(rect, canon):
    """Return list of (name, ycs, x0, pitch)."""
    # margin-zeroed ink from wide_lines is the only ink used anywhere here
    infos, ink = rl.wide_lines(rect)
    sy0, dy0, _ = rl.profile_fit(rl.zprof(ink.sum(1) / 255), canon.rowp)
    sx0, dx0, _ = rl.profile_fit(rl.zprof(ink.sum(0) / 255), canon.colp)
    cands = [dict(**i, yc=(i["y0"] + i["y1"]) / 2) for i in infos]
    matches, used = {}, set()
    for ci, cl in enumerate(canon.lines):
        target = sy0 * (cl["y0"] + cl["y1"]) / 2 + dy0
        best_j, best_d = None, rl.Y_MATCH_TOL + 1
        for j, cd in enumerate(cands):
            if j in used:
                continue
            if not (rl.H_MIN * canon.med_h <= cd["h"] <= rl.H_MAX * canon.med_h):
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
    ycs_reg = ay * canon.ycs + by

    full = [(canon.lines[ci], m) for ci, m in matches.items()
            if abs(m["w"] - canon.lines[ci]["w"]) <= rl.FULL_W_TOL * canon.med_w]
    if len(full) >= 3:
        xc = np.array([c["x0"] for c, _ in full] + [c["x1"] for c, _ in full],
                      dtype=float)
        xt = np.array([m["x0"] for _, m in full] + [m["x1"] for _, m in full],
                      dtype=float)
        ex, fx = np.polyfit(xc, xt, 1)
    else:
        ex, fx = float(sx0), float(dx0)

    xr_prior = [(int(round(ex * a + fx)), int(round(ex * b + fx)))
                for a, b in zip(canon.x0s, canon.x1s)]
    ycs_rig = rl.rigid_y(ink, ycs_reg, canon.med_h)
    ycs_rig = rl.micro_y(ink, ycs_rig, xr_prior, canon.med_h)
    ycs_regm = rl.micro_y(ink, ycs_reg, xr_prior, canon.med_h)

    x_hyps = []
    # comb around regression prior
    x0f, pf = rl.comb_fit_x(ink, ycs_rig, canon.med_h,
                            float(np.median(canon.x0s)) * ex + fx,
                            canon.pitch * ex)
    x_hyps.append(("comb", x0f, pf))
    # regression mapping of canonical comb-calibrated grid
    x_hyps.append(("reg", canon.x0c * ex + fx, canon.pitch * ex))
    # raw profile prior
    x_hyps.append(("prof", canon.x0c * sx0 + dx0, canon.pitch * sx0))

    hyps = []
    for yname, ycs in (("rig", ycs_rig), ("regm", ycs_regm)):
        for xname, x0, p in x_hyps:
            x0s, ps = per_line_comb(ink, ycs, x0, p, canon.med_h)
            hyps.append((f"{yname}+{xname}", ycs, x0s, ps))
    diag = dict(found=len(infos), matched=len(matches))
    return hyps, diag


def process_sheet(path, canon, gF, gL):
    rect = sr.rectify(path)
    rect_e = sr.enhance(rect)
    hyps, diag = geometry_hypotheses(rect, canon)

    gt0 = sr.gt_entry("T0")["token"]
    best = None
    for name, ycs, x0, p in hyps:
        per_line = windows_from_grid(rect_e, ycs[:3], np.asarray(x0)[:3], np.asarray(p)[:3])  # T0 = lines 0..2
        feats = [f for wins in per_line for f in feats_of_line(wins)]
        preds, confs, margs = nn_score(feats, gF, gL)
        correct = sum(1 for pr, g in zip(preds, gt0) if pr == g)
        if best is None or correct > best[0]:
            best = (correct, name, ycs, x0, p, feats, preds, confs, margs)
    t0_correct, gname, ycs, x0, p, t0_feats, t0_preds, t0_confs, t0_margs = best
    t0_ok = t0_correct >= T0_HEALTH_MIN

    # full extraction with winning grid
    per_line = windows_from_grid(rect_e, ycs, x0, p)
    records = {}
    # T0 records from the selection pass
    recs0 = []
    for i, ((f, blank), pr, cf, mg) in enumerate(
            zip(t0_feats, t0_preds, t0_confs, t0_margs)):
        recs0.append(dict(gt=gt0[i], pred=pr, conf=cf, margin=mg, blank=blank))
    records["T0"] = recs0

    # pooled bank for T1-T4 if T0 healthy
    F, L = gF, list(gL)
    if t0_ok:
        own = [(f, gt0[i]) for i, (f, b) in enumerate(t0_feats) if not b]
        if own:
            F = np.vstack([gF, np.stack([f for f, _ in own])])
            L = list(gL) + [c for _, c in own]

    line_i = 3
    for tid in ("T1", "T2", "T3", "T4"):
        gt = sr.gt_entry(tid)["token"]
        feats = []
        for wins in per_line[line_i:line_i + 3]:
            feats.extend(feats_of_line(wins))
        line_i += 3
        preds, confs, margs = nn_score(feats, F, L)
        records[tid] = [dict(gt=gt[i], pred=preds[i], conf=confs[i],
                             margin=margs[i], blank=feats[i][1])
                        for i in range(len(feats))]
    return records, dict(**diag, geom=gname, t0_correct=t0_correct,
                         t0_ok=t0_ok)


def build_bank(paths, canon, sigmas=nn.BLUR_SIGMAS):
    """Bank harvested with the same hypothesis-selected geometry.
    Bootstrap bank for T0-selection: canonical-native grid of the sheet itself
    is fine here because baselines segment cleanly."""
    feats, labels = [], []
    for path in paths:
        rect = sr.rectify(path)
        rect_e = sr.enhance(rect)
        hyps, _ = geometry_hypotheses(rect, canon)
        # score hypotheses by T0 self-consistency via comb objective proxy:
        # baselines are clean, comb+rig is reliable; take first (rig+comb)
        name, ycs, x0, p = hyps[0]
        per_line = windows_from_grid(rect_e, ycs, x0, p)
        li = 0
        for tid in TIDS:
            tok = sr.gt_entry(tid)["token"]
            pos = 0
            for wins in per_line[li:li + 3]:
                for win in wins:
                    a, blank = nn.centroid_align(win)
                    if not blank:
                        for sig in sigmas:
                            s = a if sig == 0 else cv2.GaussianBlur(a, (0, 0), sig)
                            feats.append(nn.feat_from_gray(s))
                            labels.append(tok[pos])
                    pos += 1
            li += 3
    return np.stack(feats), labels


def main():
    files = sorted(glob.glob("*.jpeg"))
    standard = [f for f in files if not f.startswith("locate")]
    canon = rl.CanonicalLayout("baseline-0-std-S01.jpeg")

    print("building banks...")
    bank_both = build_bank(["baseline-0-std-S01.jpeg",
                            "baseline-0-std-S02.jpeg"], canon)
    bank_s01 = build_bank(["baseline-0-std-S01.jpeg"], canon)
    bank_s02 = build_bank(["baseline-0-std-S02.jpeg"], canon)
    print("banks:", bank_both[0].shape[0], bank_s01[0].shape[0],
          bank_s02[0].shape[0])

    results = {}
    for f in standard:
        if "-S01" in f:
            gF, gL = bank_s02
        elif "-S02" in f:
            gF, gL = bank_s01
        else:
            gF, gL = bank_both
        records, info = process_sheet(f, canon, gF, gL)
        results[f] = dict(records=records, note=info["geom"],
                          t0=dict(correct=info["t0_correct"]),
                          t0_ok=info["t0_ok"], matched=info["matched"])
        raw = {}
        for tid in ("T1", "T2", "T3", "T4"):
            rs = records[tid]
            raw[tid] = sum(1 for r in rs if not r["blank"]
                           and r["pred"] == r["gt"])
        rc = sum(raw.values())
        rw = sum(len(records[t]) for t in ("T1", "T2", "T3", "T4")) - rc - \
            sum(1 for t in ("T1", "T2", "T3", "T4")
                for r in records[t] if r["blank"])
        print(f"{f:32s} T0 {info['t0_correct']:3d}/142 "
              f"{'OK ' if info['t0_ok'] else 'DMG'} "
              f"| T1-T4 raw {rc:3d}c {rw:3d}w | m{info['matched']:2d} "
              f"geom={info['geom']}")

    with open("sweep_records.pkl", "wb") as fh:
        pickle.dump(results, fh)
    print("saved sweep_records.pkl")


if __name__ == "__main__":
    main()
