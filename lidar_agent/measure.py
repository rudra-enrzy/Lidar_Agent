"""Turns a Scene into one value per Observation Type.  Every result:
   dict(value=float|None, a=[u,v,z], b=[u,v,z], conf='high|medium|low', note=str)
a/b are the two end points of the measured line (tower frame) -> used to draw Potree markers."""
import numpy as np
from scipy.spatial import cKDTree


def _min_dist(A, B):
    if A is None or B is None or len(A) == 0 or len(B) == 0:
        return None
    t = cKDTree(B)
    d, i = t.query(A)
    j = int(np.argmin(d))
    return float(d[j]), A[j], B[i[j]]


def _res(v, a=None, b=None, conf="high", note=""):
    return dict(value=None if v is None else round(float(v), 2),
                a=None if a is None else [round(float(x), 3) for x in a],
                b=None if b is None else [round(float(x), 3) for x in b],
                conf=conf, note=note)


def _manual(why):
    return _res(None, conf="none", note=why)


def _ref(sc, k, u0):
    """ONE point on wire k at along-line position u0: mean of the real wire points within 0.6 m of u0
    (falls back to the fitted wire line).  Never a tower point."""
    f = sc.wires[k]
    P = sc.near.get(k)
    if P is not None and len(P):
        m = np.abs(P[:, 0] - u0) < 0.6
        if m.sum() >= 5:
            return P[m].mean(0)
    return np.array([u0, f["v0"] + f["kv"] * u0, f["z0"] + f["kz"] * u0])


def _track(sc, k, o):
    """Follow wire k along the forward span from the tower down to its sag.  Returns array (u, v, z) of real wire
    points, one per metre of u (median of the bundle snapped to an actual return)."""
    cache = sc.__dict__.setdefault("_tracks", {})
    if k in cache: return cache[k]
    f = sc.wires[k]; u0 = o.get("near_u", 12.0)
    m = (sc.pts[:, 0] > u0) & (sc.hP > 5.0)
    Q = sc.pts[m]; bins = np.floor(Q[:, 0]).astype(int)
    order = np.argsort(bins, kind="stable"); Q, bins = Q[order], bins[order]
    z_pred, v_pred, slope = f["z0"] + f["kz"] * u0, f["v0"] + f["kv"] * u0, f["kz"]
    out, miss = [], 0
    last = int(bins.max()) if len(bins) else int(u0)
    if sc.info.get("span_end_u"): last = min(last, int(sc.info["span_end_u"]))   # stop before the next tower
    for b in range(int(u0), last):
        i0, i1 = np.searchsorted(bins, b), np.searchsorted(bins, b + 1)
        C = Q[i0:i1]
        ok = (np.abs(C[:, 1] - v_pred) < 1.5) & (np.abs(C[:, 2] - z_pred) < 1.2) if len(C) else np.zeros(0, bool)
        if ok.sum() >= 3:
            C = C[ok]; zc, vc = np.median(C[:, 2]), np.median(C[:, 1])
            pt = np.array([np.median(C[:, 0]), vc, zc])          # centre of the conductor bundle at this u
            if out: slope = 0.7 * slope + 0.3 * (pt[2] - out[-1][2]) / max(pt[0] - out[-1][0], 0.5)
            out.append(pt); z_pred, v_pred = pt[2] + slope, vc; miss = 0
        else:
            z_pred += slope; miss += 1
            if miss > 15: break
    cache[k] = np.array(out) if out else np.empty((0, 3))
    return cache[k]


def _bundle(sc, c, u, half_u=0.5):
    """real points of the conductor bundle around centre c, in a thin slab at u."""
    P = sc.pts
    m = (np.abs(P[:, 0] - u) < half_u) & (np.abs(P[:, 1] - c[1]) < 1.0) & (np.abs(P[:, 2] - c[2]) < 1.0)
    return P[m]


def _cut_off(sc, tr, u):
    """True if the sag point found is just where the wire data runs out (the real sag point is probably beyond)."""
    end = tr[-1, 0]
    se = sc.info.get("span_end_u")
    if se and end >= se - 2: return False            # the track stopped at the next tower: the whole span was seen
    return u >= end - 3


def _pt_at(tr, u):
    j = int(np.argmin(np.abs(tr[:, 0] - u)))
    return tr[j] if abs(tr[j, 0] - u) < 3.0 else None


def _span_mid(sc, o):
    """u of the middle of the span: half way to the next tower when it is in the data; otherwise ONE estimate for all
    rows = the median lowest-sag point of the three conductors (on level ground the sag is lowest at mid-span)."""
    if o.get("wire_ref", "mid") != "mid": return None
    D = sc.info.get("next_tower_m")
    if D: return D / 2.0
    if "_mid_est" not in sc.info:
        us = []
        for k in ("L", "M", "R"):
            if k in sc.wires:
                tr = _track(sc, k, o)
                if len(tr) >= 20 and not _cut_off(sc, tr, tr[np.argmin(tr[:, 2]), 0]):
                    us.append(float(tr[np.argmin(tr[:, 2]), 0]))
        sc.info["_mid_est"] = float(np.median(us)) if us else None
    return sc.info["_mid_est"]


def _pair_sag(sc, a, b, o):
    """Wire-to-wire clearance in one span cross-section: at MID-SPAN (half way between the two towers) when the next
    tower is known, otherwise through the lowest (null) point of the wire that sags most (= mid-span on level ground)."""
    if a not in sc.wires or b not in sc.wires:
        return _manual(f"wire {a}/{b} not detected")
    ta, tb = _track(sc, a, o), _track(sc, b, o)
    if len(ta) < 20 or len(tb) < 20:
        return _res(None, conf="none", note="could not follow the wire down to its sag point")
    na, nb = ta[np.argmin(ta[:, 2])], tb[np.argmin(tb[:, 2])]
    um = _span_mid(sc, o)
    ustar = um if um is not None else (na if na[2] < nb[2] else nb)[0]
    A, B = _pt_at(ta, ustar), _pt_at(tb, ustar)
    if A is None or B is None:
        return _res(None, conf="none", note="wire not continuous at " + ("mid-span" if um else "the sag point"))
    BA, BB = _bundle(sc, A, ustar), _bundle(sc, B, ustar)
    if len(BA) >= 3 and len(BB) >= 3:            # closest sub-conductors: the real air gap between the two wires
        r = _min_dist(BA, BB)
        if r is not None: A, B = r[1], r[2]
    if um is not None:
        how = "half way to the next tower" if sc.info.get("next_tower_m") else "estimated from the conductors' lowest sag points - next tower not in the data"
        note, conf = f"nearest wire points at mid-span, {ustar:.0f} m from the tower ({how})", "high"
        return _res(np.linalg.norm(A - B), A, B, conf, note)
    note, conf = (f"nearest wire points at the highest-sag point, {ustar:.0f} m from the tower (next tower not in the data, "
                  "so mid-span = lowest sag point)"), "high"
    if _cut_off(sc, ta if na[2] < nb[2] else tb, ustar):
        note, conf = note + " - the wire data ends here: the real sag point is probably beyond this file (add the next tower's LAS)", "low"
    return _res(np.linalg.norm(A - B), A, B, conf, note)


def _pair(sc, a, b, u0, conf="high"):
    if a not in sc.wires or b not in sc.wires:
        return _manual(f"wire {a}/{b} not detected")
    A, B = _ref(sc, a, u0), _ref(sc, b, u0)
    return _res(np.linalg.norm(A - B), A, B, conf, f"wire-to-wire at u={u0:g} m beside the tower")


def _assign_near(sc):
    return {k: v for k, v in sc.near.items() if len(v)}


def _ground_clearance(sc, k, o):
    """lowest wire point at the sag (null) point -> ground straight below it."""
    if k not in sc.wires: return _manual(f"phase {k} not detected")
    tr = _track(sc, k, o)
    if len(tr) < 20: return _manual("could not follow the conductor along the forward span")
    um = _span_mid(sc, o)
    n = _pt_at(tr, um) if um is not None else None
    if n is None:
        um = None; n = tr[np.argmin(tr[:, 2])]
    B = _bundle(sc, n, n[0])
    p = B[np.argmin(B[:, 2])] if len(B) >= 3 else n          # bottom sub-conductor, not the bundle centre
    g = float(sc.ground_z(p[None, :2])[0])
    if um is not None:
        how = "" if sc.info.get("next_tower_m") else ", mid-span estimated from the sag - next tower not in the data"
        return _res(p[2] - g, p, [p[0], p[1], g], "high",
                    f"lowest conductor point at mid-span ({um:.0f} m from the tower{how}) to the ground below")
    note, conf = "lowest conductor point at the sag point (next tower not in the data) to the ground below", "high"
    if _cut_off(sc, tr, n[0]):
        note, conf = (f"lowest point is where the wire data ends (u={n[0]:.0f} m): the sag point is probably beyond "
                      "this file - true clearance may be smaller (add the next tower's LAS)", "low")
    return _res(p[2] - g, p, [p[0], p[1], g], conf, note)


def _arm_steel(T, n, above, du=5.0, dz_max=12.0, dv_near=4.5, min_len=4.0, gap=0.8):
    """tower points that belong to horizontal ARM members above (or below) point n - see arm() in _measure."""
    dz = T[:, 2] - n[2]
    sel = (np.abs(T[:, 0] - n[0]) < du) & ((dz > 0.5) if above else (dz < -0.5)) & (np.abs(dz) < dz_max)
    S = T[sel]
    if not len(S): return S
    keep = np.zeros(len(S), bool)
    zb = np.floor(S[:, 2] / 0.3).astype(int)
    for z in np.unique(zb):
        ii = np.flatnonzero(zb == z); ii = ii[np.argsort(S[ii, 1])]
        v = S[ii, 1]; cut = np.flatnonzero(np.diff(v) > gap) + 1
        for g in np.split(ii, cut):
            vg = S[g, 1]
            if np.ptp(vg) >= min_len and np.min(np.abs(vg - n[1])) < dv_near: keep[g] = True
    return S[keep]


def _horn(sc, k, J, why):
    """Lower arcing horn -> jumper: the horn hangs just below the TOWER end of the strain insulator string
    (1-4.5 m out from the tower plane, a little below the attachment height).  Distance = nearest jumper point to the
    hardware there.  The pilot string straight above the jumper (|u| < 1 m) and the jumper itself are skipped."""
    if why: return _manual(why)
    if J is None or len(J) < 20 or k not in sc.wires: return _manual(f"jumper {k} not found")
    f = sc.wires[k]; B = sc.box["P"]; za = f["z0"]
    au = np.abs(B[:, 0])
    sel = ((au > 1.0) & (au < 4.5) & (np.abs(B[:, 1] - f["v0"]) < 2.5)
           & (B[:, 2] < za - 0.2) & (B[:, 2] > za - 2.5))
    H = B[sel]
    if len(H) < 5: return _manual("no arcing-horn / string hardware found at the tower end of the strain string")
    d, _ = cKDTree(J).query(H)
    H = H[d > 0.5]                                        # not the jumper's own points
    if len(H) < 5: return _manual("arcing horn not separable from the jumper - measure in Potree")
    r = _min_dist(J, H)
    if r is None or r[0] < 0.8: return _manual("arcing horn not separable from the jumper - measure in Potree")
    return _res(r[0], r[1], r[2], "low",
                "from the lower arcing horn (tower end of the strain string) to the nearest jumper point - small part, verify in Potree")


def _crossing_line(sc, o):
    """Another power line (or telephone/distribution line) crossing UNDER this span: a straight line in plan, at
    >= 20 deg to our line, whose highest wire follows a smooth curve.  Returns its points or None."""
    D = sc.info.get("next_tower_m")
    if not D or D < 60: return None
    tr = [t for t in (_track(sc, k, o) for k in ("L", "M", "R") if k in sc.wires) if len(t) >= 20]
    if not tr: return None
    P = sc.pts
    m = (P[:, 0] > 12) & (P[:, 0] < D - 12) & (np.abs(P[:, 1]) < 60) & (sc.hP > 4.0)
    Q = P[m]
    if len(Q) < 30: return None
    zlow = np.min([np.interp(Q[:, 0], t[:, 0], t[:, 2]) for t in tr], axis=0)
    Q = Q[Q[:, 2] < zlow - 1.5]                           # below our conductors: not our own wires
    if len(Q) < 30: return None
    _, iu = np.unique(np.floor(Q / 0.5).astype(np.int64), axis=0, return_index=True)
    S = Q[iu]                                             # 0.5 m thinned copy for the search
    best = None
    for deg in range(30, 151, 2):
        th = np.radians(deg); d = np.array([np.cos(th), np.sin(th)]); nrm = np.array([-d[1], d[0]])
        s = S[:, :2] @ nrm
        b = np.floor(s / 1.0).astype(np.int64); bu, cnt = np.unique(b, return_counts=True)
        for bi in bu[np.argsort(-cnt)[:4]]:
            ux = (bi + 0.5) / nrm[0]                      # where it crosses our line: must be inside this span
            if not (12 < ux < D - 12): continue
            W = S[np.abs(s - (bi + 0.5)) < 1.0]
            t = W[:, :2] @ d; tb = np.floor(t / 2.0).astype(np.int64)
            ub, first = np.unique(tb, return_index=True)
            if len(ub) < 15: continue                     # must run >= 30 m across the corridor
            oi = np.argsort(tb, kind="stable"); _, first = np.unique(tb[oi], return_index=True)
            top = np.column_stack([(ub + 0.5) * 2.0, np.maximum.reduceat(W[oi, 2], first)])   # highest wire per 2 m
            c = np.polyfit(top[:, 0], top[:, 1], 2)
            res = np.abs(top[:, 1] - np.polyval(c, top[:, 0]))
            if np.median(res) > 0.35 or (res < 0.6).mean() < 0.75: continue      # trees / roofs are not smooth
            score = len(ub) * (res < 0.6).mean()
            if best is None or score > best[0]: best = (score, deg, bi + 0.5, d, nrm, ux, c)
    if best is None: return None
    _, deg, s0, d, nrm, ux, c = best
    X = Q[np.abs(Q[:, :2] @ nrm - s0) < 1.5]
    X = X[np.abs(X[:, 2] - np.polyval(c, X[:, :2] @ d)) < 0.6]     # the top wire only (no trees / poles in the strip)
    sc.info["crossing_line"] = dict(angle_deg=deg if deg <= 90 else 180 - deg, u=round(float(ux), 1), points=int(len(X)))
    return X


def _cross_clear(sc, k, X, o):
    """our conductor -> crossing line's top wire, measured VERTICALLY where our conductor passes over it (T-108)."""
    if X is None or len(X) < 10:
        return _res(None, conf="na", note="N/A - no crossing line found under this span")
    if k not in sc.wires: return _manual(f"conductor {k} not detected")
    tr = _track(sc, k, o)
    if len(tr) < 20: return _manual("could not follow the conductor along the span")
    t = cKDTree(X[:, :2]); d, _ = t.query(tr[:, :2])
    j = int(np.argmin(d))
    near = tr[np.abs(tr[:, 0] - tr[j, 0]) < 25]
    C = np.vstack([_bundle(sc, p, p[0]) for p in near] + [near])
    dh, ix = t.query(C[:, :2])
    ok = dh < 0.5                                         # crossing wire straight below this conductor point
    ang = sc.info["crossing_line"]["angle_deg"]
    if ok.any():
        gap = C[ok, 2] - X[ix[ok], 2]; m = int(np.argmin(gap))
        a, b = C[ok][m], X[ix[ok][m]]
        return _res(gap[m], a, [a[0], a[1], b[2]], "medium",
                    f"Power-line crossing: conductor straight down to the crossing line's top wire (crosses at {ang} deg, "
                    f"{a[0]:.0f} m from the tower)")
    Xn = X[np.hypot(X[:, 0] - tr[j, 0], X[:, 1] - tr[j, 1]) < 40]
    r = _min_dist(C, Xn)
    if r is None: return _manual("crossing line not found near this conductor")
    return _res(r[0], r[1], r[2], "medium", f"Power-line crossing: nearest conductor point to the crossing line's top wire ({ang} deg)")


def _road(sc, o):
    """A road crossing under the span, from the point colours: a straight strip 4-20 m wide of grey asphalt
    (low colour saturation) with clearly NOT-grey ground on both sides, crossing our line at >= 30 deg.
    Returns (s0, nrm, d, width) of the road centre line in the tower frame, or None."""
    D = sc.info.get("next_tower_m"); C = getattr(sc, "rgb", None)
    if not D or D < 60 or C is None: return None
    P = sc.pts
    m = (P[:, 0] > 5) & (P[:, 0] < D - 5) & (np.abs(P[:, 1]) < 60) & (sc.hP < 0.3)
    if m.sum() < 2000: return None
    Q, c = P[m, :2], C[m].astype(np.int16)
    cell = np.floor(Q / 0.5).astype(np.int64)
    key, inv = np.unique(cell[:, 0] * 1_000_003 + cell[:, 1], return_inverse=True)
    n = np.bincount(inv)
    mc = np.column_stack([np.bincount(inv, c[:, i]) / n for i in range(3)])
    G = np.column_stack([np.bincount(inv, Q[:, 0]) / n, np.bincount(inv, Q[:, 1]) / n])   # one sample per 0.5 m cell
    sat = mc.max(1) - mc.min(1); val = mc.mean(1)
    grey = (sat < 14) & (val > 35) & (val < 160)
    if grey.sum() < 200: return None
    best = None
    for deg in range(30, 151, 2):
        th = np.radians(deg); d = np.array([np.cos(th), np.sin(th)]); nrm = np.array([-d[1], d[0]])
        sN = G @ nrm; b = np.floor(sN).astype(np.int64); b0 = b.min()
        tot = np.bincount(b - b0); gr = np.bincount(b - b0, grey.astype(int), minlength=len(tot))
        frac = np.where(tot > 20, gr / np.maximum(tot, 1), 0)
        i = 0
        while i < len(frac):
            if frac[i] < 0.7: i += 1; continue
            j = i
            while j + 1 < len(frac) and frac[j + 1] >= 0.7: j += 1
            w = j - i + 1
            side = np.r_[frac[max(0, i - 6):max(0, i - 2)], frac[j + 3:j + 7]]
            if 4 <= w <= 20 and len(side) >= 6 and side.mean() < 0.3:
                s0 = b0 + (i + j + 1) / 2.0
                ux = s0 / nrm[0]
                if 8 < ux < D - 8:
                    inn = np.abs(sN - s0) < w / 2
                    t = G[inn & grey] @ d
                    cov = len(np.unique(np.floor(t / 2.0)))
                    if cov >= 15:                              # >= 30 m of road seen across the corridor
                        score = cov * frac[i:j + 1].mean()
                        if best is None or score > best[0]: best = (score, deg, s0, nrm, d, w, ux)
            i = j + 1
    if best is None: return None
    _, deg, s0, nrm, d, w, ux = best
    sc.info["road_crossing"] = dict(angle_deg=deg if deg <= 90 else 180 - deg, width_m=int(w), u=round(float(ux), 1))
    return (s0, nrm, d, w)


def _road_clear(sc, k, rd, o):
    """our conductor straight down to the road surface, over the road centre line (T-108 'Crossing Clearances')."""
    if k not in sc.wires: return _manual(f"conductor {k} not detected")
    tr = _track(sc, k, o)
    if len(tr) < 20: return _manual("could not follow the conductor along the span")
    s0, nrm, d, w = rd
    off = np.abs(tr[:, :2] @ nrm - s0); j = int(np.argmin(off))
    if off[j] > 2.0: return _manual("conductor does not pass over the road inside this span")
    B = _bundle(sc, tr[j], tr[j, 0])
    p = B[np.argmin(B[:, 2])] if len(B) >= 3 else tr[j]
    g = float(sc.ground_z(p[None, :2])[0])
    ri = sc.info["road_crossing"]
    return _res(p[2] - g, p, [p[0], p[1], g], "low",
                f"Road crossing: lowest conductor point over the road centre line straight down to the road surface "
                f"(road ~{ri['width_m']} m wide, crosses at {ri['angle_deg']} deg, {p[0]:.0f} m from the tower) - found from "
                "point colours, verify in Potree")


SWAP = [("phase_LM", "phase_RM"), ("opgw_L", "opgw_R"), ("s_L_leg", "s_R_leg"), ("s_M_left", "s_M_right"),
        ("gnd_L", "gnd_R"), ("cross_L", "cross_R"), ("cross2_L", "cross2_R"), ("t_L_arm", "t_R_arm"), ("t_L_horn", "t_R_horn"),
        ("t_L_leg", "t_R_leg"), ("t_M_left", "t_M_right")]


def measure(sc, ttype, o=None):
    o = o or {}
    R = _measure(sc, ttype, o)
    ang = sc.info.get("line_angle_deg")
    if ang is not None and ang > o.get("angle_flag_deg", 15.0):
        # sharp angle towers: jumpers swing round the tower body - keep the values but ask for a check
        for k, r in R.items():
            if k.startswith(("t_", "s_")) and r["value"] is not None:
                r["conf"] = "low"
                r["note"] = f"angle tower (line turns {ang:.0f} deg here) - verify in Potree. " + r["note"]
    if o.get("swap_lr"):
        for a, b in SWAP:
            if a in R and b in R: R[a], R[b] = R[b], R[a]
    return R


def _measure(sc, ttype, o=None):
    o = o or {}
    nw = _assign_near(sc)
    T = sc.tower if sc.tower is not None else np.empty((0, 3))
    R = {}
    u_ref = o.get("ref_u", 4.0 if ttype == "suspension" else 9.0)
    if o.get("wire_ref", "mid") in ("mid", "sag"):
        pr = lambda a, b: _pair_sag(sc, a, b, o)
    else:
        pr = lambda a, b: _pair(sc, a, b, u_ref)
    R["phase_LM"] = pr("L", "M"); R["phase_RM"] = pr("R", "M")
    R["opgw_R"] = pr("OPGW_R" if "OPGW_R" in sc.wires else "OPGW", "R"); R["opgw_L"] = pr("OPGW_L" if "OPGW_L" in sc.wires else "OPGW", "L")
    found = []
    if ttype == "tension":                       # T-108 (tension) report: road crossing first, then a crossing line
        rd = _road(sc, o)
        if rd is not None: found.append(("road", rd))
    # suspension report (earlier references): one set, conductor to a crossing line only
    X = _crossing_line(sc, o)
    if X is not None: found.append(("line", X))
    for i, pre in enumerate(("cross", "cross2")):
        for k in ("L", "R"):
            if i < len(found):
                kind, obj = found[i]
                R[f"{pre}_{k}"] = _road_clear(sc, k, obj, o) if kind == "road" else _cross_clear(sc, k, obj, o)
            else:
                R[f"{pre}_{k}"] = _res(None, conf="na", note="N/A - no crossing under this span")
    R["structures"] = _res(None, conf="na", note="N/A")
    R["gnd_L"] = _ground_clearance(sc, "L", o)
    R["gnd_R"] = _ground_clearance(sc, "R", o)

    if len(T) < 50:
        why = "tower structure not isolated"
    else:
        why = None
    vM = sc.wires["M"]["v0"] if "M" in sc.wires else 0

    def md(A, B, conf="medium", note=""):
        r = _min_dist(A, B)
        if r is None: return _manual(why or "no points")
        return _res(r[0], r[1], r[2], conf, note)

    if ttype == "suspension":
        for k, key, vmid, sgn in (("L", "s_L_leg", vM, -1), ("R", "s_R_leg", vM, +1)):
            if k in nw and why is None:
                zc = sc.wires[k]["z0"]
                side = T[(T[:, 1] > vmid) & (T[:, 2] <= zc + 1)] if k == "L" else T[(T[:, 1] < vmid) & (T[:, 2] <= zc + 1)]
                R[key] = md(_ref(sc, k, 0.0)[None, :], side, "medium", "from one point on the conductor (tower plane) to the nearest main-leg point")
            else:
                R[key] = _manual(why or f"conductor {k} near tower not found")
        if "M" in nw and why is None:
            a = nw["M"]; c = np.array([0, vM, sc.wires["M"]["z0"]])
            dv, dz = T[:, 1] - vM, T[:, 2] - c[2]
            a = _ref(sc, "M", 0.0)[None, :]            # ONE point on the middle conductor, shared by all four distances
            def ray(dirv, dirz, note):
                # hangers / V-strings sit within ~2 m of the conductor: look past them along a narrow tube for the frame member
                t = dv * dirv + dz * dirz; p = np.abs(-dv * dirz + dz * dirv)
                sel = (t > 2.0) & (p < 0.8) & (np.abs(T[:, 0]) < 3.0)
                if dirz == 1: sel &= ~((np.abs(dv) < 0.6) & (np.abs(T[:, 0]) < 0.6))     # a vertical insulator string straight above is not the frame
                return md(a, T[sel], "medium", note)
            R["s_M_top"] = ray(0, 1, "first frame member straight above the middle conductor (hanger/V-string skipped)")
            R["s_M_bot"] = ray(0, -1, "first frame member straight below")
            R["s_M_left"] = ray(1, 0, "first frame member beside the middle conductor (horizontal)")
            R["s_M_right"] = ray(-1, 0, "first frame member beside the middle conductor (horizontal)")
        else:
            for k in ("s_M_top", "s_M_bot", "s_M_left", "s_M_right"): R[k] = _manual(why or "middle conductor near tower not found")
    else:  # tension
        nulls = {}
        for k in ("L", "M", "R"):
            J = nw.get(k)
            if J is not None and len(J) > 20:
                nulls[k] = J[np.argmin(J[:, 2])]
        def attach_z(k):
            return sc.wires[k]["z0"] if k in sc.wires else None

        def arm(k, above):
            """Jumper drop (T-108): from the jumper null point to the cross arm / cage arm above it (or the lower cage arm
            below). Only real arm steel counts: a horizontal member - in a 0.3 m height slice it is a connected run of
            steel at least 4 m long across the line - whose nearest end is within 4.5 m sideways of the jumper.
            Insulator strings, pilot (V) strings, yokes and counterweights are narrow across the line and are skipped,
            and so is the tower body further in. Straight above/below when the arm is there (vertical line, as in the
            reference pictures), otherwise to the nearest point of that arm."""
            if k not in nulls or why: return _manual(why or f"jumper {k} not found")
            n = nulls[k]
            A = _arm_steel(T, n, above)
            if not len(A): return _manual("no cross arm / cage arm found " + ("above" if above else "below") + " the jumper null point")
            col = A[np.hypot(A[:, 0] - n[0], A[:, 1] - n[1]) < 1.0]
            if len(col):                                     # the arm is straight above / below: vertical line
                p = col[np.argmin(np.abs(col[:, 2] - n[2]))]; b = [n[0], n[1], p[2]]; d = abs(p[2] - n[2]); how = "straight " + ("up" if above else "down")
            else:
                r = _min_dist(n[None, :], A); d, b = r[0], r[2]; how = "to the nearest point of the arm (the arm is not straight " + ("above" if above else "below") + " the jumper)"
            if d < 1.0: return _manual("jumper touches steel in the data (hardware not separable) - measure in Potree")
            what = "cross arm" if k != "M" else ("upper cage arm" if above else "lower cage arm")
            return _res(d, n, b, "medium", f"from the jumper null point (lowest point of the loop) {how} to the {what}")

        R["t_L_arm"] = arm("L", True); R["t_R_arm"] = arm("R", True)
        R["t_M_upper"] = arm("M", True); R["t_M_lower"] = arm("M", False)
        for k in ("L", "M", "R"):
            R[f"t_{k}_horn"] = _horn(sc, k, nw.get(k), why)
        for k, key in (("L", "t_L_leg"), ("R", "t_R_leg")):
            if k in nulls and why is None:
                n = nulls[k]; za = attach_z(k)
                inward = (T[:, 1] < n[1] - 2.0) if n[1] > vM else (T[:, 1] > n[1] + 2.0)   # towards the tower body, >2 m sideways
                flat = inward & (np.abs(T[:, 2] - n[2]) < 0.8) & (np.abs(T[:, 0] - n[0]) < 3.0)
                if flat.sum() >= 3:      # horizontal line from the null point across to the main leg (T-108)
                    R[key] = md(n[None, :], T[flat], "medium", "horizontal line from the jumper null point to the main leg / tower body")
                else:
                    sel = T[inward & (T[:, 2] < za - 0.5)]
                    R[key] = md(n[None, :], sel, "medium", "from the jumper null point to the nearest main-leg / body steel (hanging hardware skipped)")
            else:
                R[key] = _manual(why or f"jumper {k} not found")
        if "M" in nulls and why is None:
            n = nulls["M"]; dv, dz = T[:, 1] - n[1], T[:, 2] - n[2]
            def hray(sgn):
                t = dv * sgn; p = np.abs(dz)
                sel = (t > 2.0) & (p < 0.8) & (np.abs(T[:, 0] - n[0]) < 5.0)
                return md(n[None, :], T[sel], "medium", "first tower member beside the middle jumper null point (horizontal, hardware skipped)")
            R["t_M_left"] = hray(+1); R["t_M_right"] = hray(-1)
        else:
            R["t_M_left"] = _manual(why or "middle jumper not found"); R["t_M_right"] = _manual(why or "middle jumper not found")
    return R
