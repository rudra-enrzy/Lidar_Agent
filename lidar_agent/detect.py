"""Geometry engine: ground, tower, wires and tower-type detection from a (thinned) point cloud.

Frame after detect(): origin = tower centre, +u = forward along the line, +v = LEFT when facing forward,
z = metres above the ground at the tower centre.
"""
from dataclasses import dataclass, field
import numpy as np
from scipy import ndimage

DEFAULTS = dict(
    corridor_v=30.0, min_span=60.0, box_u=16.0, jumper_half_u=12.0, angle_flag_deg=15.0,
    ground_cell=2.0, tower_cell=1.5, slab_u=(12.0, 45.0), near_u=12.0, min_wire_len=15.0,
    voxel=0.3, wire_min_h_frac=0.40, opgw="left",
)


@dataclass
class Scene:
    pts: np.ndarray                    # (N,3) u,v,z in tower frame
    ground: np.ndarray                 # (M,3) ground cell points, same frame
    grid: object = None                # GroundGrid in file coordinates
    H: float = 0.0                     # tower height above ground
    tower: np.ndarray = None           # tower points
    near_wire: np.ndarray = None       # non-tower points near the tower above 0.4H (wires / jumpers / insulators)
    wires: dict = field(default_factory=dict)   # name -> dict(v0,z0,kv,kz,pts,...)
    flags: list = field(default_factory=list)
    info: dict = field(default_factory=dict)
    box: dict = None
    near: dict = field(default_factory=dict)
    R: np.ndarray = None               # rotation used (for exporting markers back to world coords)
    centre_xy: np.ndarray = None
    hP: np.ndarray = None              # height of every point above local ground

    def ground_z(self, uv):
        """ground height (tower frame) under tower-frame positions uv."""
        uv = np.atleast_2d(uv)
        xy = uv[:, :2] @ self.R + self.centre_xy
        return self.grid(xy) - self.info["z0"]

    def to_world(self, p):
        """tower-frame points -> local file coords (add origin from pointcloud.load to get CRS coords)."""
        p = np.atleast_2d(p).astype(float)
        xy = p[:, :2] @ self.R + self.centre_xy
        return np.column_stack([xy, p[:, 2] + self.info["z0"]])


class GroundGrid:
    """Ground height raster (one low point per cell, gaps filled from the nearest cell, 3x3 median).
    Lookups are a simple index, so heights for 20+ million points cost almost no extra memory."""
    def __init__(self, G, cell):
        self.cell = cell
        self.x0, self.y0 = G[:, 0].min() - cell, G[:, 1].min() - cell
        ix = ((G[:, 0] - self.x0) // cell).astype(np.int64); iy = ((G[:, 1] - self.y0) // cell).astype(np.int64)
        self.nx, self.ny = int(ix.max()) + 2, int(iy.max()) + 2
        g = np.full((self.nx, self.ny), np.nan, np.float32); g[ix, iy] = G[:, 2]
        miss = np.isnan(g)
        if miss.any():
            idx = ndimage.distance_transform_edt(miss, return_distances=False, return_indices=True)
            g = g[tuple(idx)]
        self.g = ndimage.median_filter(g, size=3)

    def __call__(self, q, chunk=2_000_000):
        q = np.atleast_2d(q); out = np.empty(len(q), np.float64)
        for s in range(0, len(q), chunk):
            c = q[s:s + chunk]
            ix = np.clip(((c[:, 0] - self.x0) // self.cell).astype(np.int64), 0, self.nx - 1)
            iy = np.clip(((c[:, 1] - self.y0) // self.cell).astype(np.int64), 0, self.ny - 1)
            out[s:s + chunk] = self.g[ix, iy]
        return out


def _ground(xyz, cell, cls=None):
    if cls is not None and (cls == 2).sum() > 500:
        g = xyz[cls == 2]
    else:
        g = xyz
    key = np.floor(g[:, :2] / cell).astype(np.int64)
    k = key[:, 0] * 1_000_003 + key[:, 1]
    order = np.lexsort((g[:, 2], k))
    ks, zs = k[order], g[order]
    starts = np.r_[0, np.flatnonzero(np.diff(ks)) + 1]
    counts = np.diff(np.r_[starts, len(ks)])
    pick = starts + (counts * 0.03).astype(int)
    return zs[pick]          # one low point per cell


def find_towers(xyz, h, cell=1.5):
    """All tower-like structures: XY cells with tall continuous vertical occupancy, grouped into clusters.
    Returns [(centre_xy, score)] sorted by score (number of 1.5 m height bins occupied)."""
    m = h > 4
    key = np.floor(xyz[m, :2] / cell).astype(np.int64)
    zb = np.floor(h[m] / 1.5).astype(np.int64)
    uk = np.unique(np.column_stack([key, zb]), axis=0)
    ck, cnt = np.unique(uk[:, :2], axis=0, return_counts=True)
    mn = ck.min(0)
    grid = np.zeros(ck.max(0) - mn + 1, np.int32); grid[tuple((ck - mn).T)] = cnt
    mask = grid >= 0.5 * cnt.max()
    lab, n = ndimage.label(ndimage.binary_dilation(mask, iterations=3))
    out = []
    for k in range(1, n + 1):
        sel = (lab == k) & mask
        if not sel.any(): continue
        best = grid[sel].max()
        ij = np.argwhere(sel & (grid >= 0.7 * best))
        out.append(((ij.mean(0) + mn + 0.5) * cell, int(best)))
    merged = []                                  # parts of one tower (e.g. separate leg groups) within 25 m -> one tower
    for c, sc_ in sorted(out, key=lambda t: -t[1]):
        for m in merged:
            if np.linalg.norm(m[0] / m[2] - c) < 25:
                m[0] += c; m[2] += 1; m[1] = max(m[1], sc_); break
        else:
            merged.append([c.copy(), sc_, 1])
    return [(m[0] / m[2], m[1]) for m in merged]


def _ground_cache(pc, o):
    if pc.get("_ground") is None:
        xyz = pc["xyz"]
        G = _ground(xyz, o["ground_cell"], pc["cls"])
        gz = GroundGrid(G, o["ground_cell"])
        pc["_ground"] = (G, gz, xyz[:, 2] - gz(xyz))
    return pc["_ground"]


def survey_towers(pc, opts=None):
    """Every tower in the LAZ: [(xy, height_m)], strong vertical structures only (trees and poles are far weaker)."""
    o = {**DEFAULTS, **(opts or {})}
    xyz = pc["xyz"]
    G, gz, h = _ground_cache(pc, o)
    towers = find_towers(xyz, h, o["tower_cell"])
    if not towers:
        return []
    strong = [t for t in towers if t[1] >= 0.6 * towers[0][1]]
    out = []
    for c, _ in strong:
        near = np.linalg.norm(xyz[:, :2] - c, axis=1) < 10
        out.append((c, float(np.percentile(h[near], 99.7)) if near.any() else 0.0))
    hmed = float(np.median([t[1] for t in out]))
    return [t for t in out if t[1] >= 0.75 * hmed]          # poles / small structures / towers cut by the file edge


def line_chain(pc, xys, opts=None):
    """Order the towers of ONE line: two towers are neighbours only if conductors run between them (wire points
    above the segment at 30/50/70 %), they are at least min_span apart and no other tower lies in between.
    Returns (indices in line order, indices of structures that are not on this line)."""
    from scipy.spatial import cKDTree
    o = {**DEFAULTS, **(opts or {})}
    T = np.asarray(xys, float); n = len(T)
    if n <= 1: return list(range(n)), []
    G, gz, h = _ground_cache(pc, o)
    W = pc["xyz"][h > 8.0][:, :2]
    W = W[np.unique(np.floor(W / 0.5).astype(np.int64), axis=0, return_index=True)[1]]
    tree = cKDTree(W)

    def ok(i, j):
        d = np.linalg.norm(T[j] - T[i])
        if d < o["min_span"] or d > 1500: return False
        e = (T[j] - T[i]) / d
        for k in range(n):                                   # nothing standing in between
            if k in (i, j): continue
            t = (T[k] - T[i]) @ e
            if 0 < t < d and abs((T[k] - T[i]) @ np.array([-e[1], e[0]])) < 15: return False
        return all(len(tree.query_ball_point(T[i] + (T[j] - T[i]) * f, 4.0)) >= 3 for f in (0.3, 0.5, 0.7))

    adj = {i: [j for j in range(n) if j != i and ok(i, j)] for i in range(n)}
    best = [0]
    def length(p): return sum(np.linalg.norm(T[p[k + 1]] - T[p[k]]) for k in range(len(p) - 1))
    def dfs(p):
        nonlocal best
        if len(p) > len(best) or (len(p) == len(best) and length(p) < length(best)): best = list(p)
        for j in adj[p[-1]]:
            if j not in p: p.append(j); dfs(p); p.pop()
    for st in range(n): dfs([st])
    return best, [i for i in range(n) if i not in best]


def order_towers(xys, start="north"):
    """Put towers in line order: walk from one end of the line, always stepping to the nearest remaining tower
    (works for lines with angle points). start = the compass end where the numbering begins: north/south/east/west."""
    T = np.array(xys, float)
    if len(T) <= 1:
        return list(range(len(T)))
    d = T - T.mean(0)
    ax = np.linalg.eigh(np.cov(d.T))[1][:, 1] if len(T) > 2 else (T[1] - T[0]) / np.linalg.norm(T[1] - T[0])
    s0 = int(np.argmin(d @ ax))
    order, left = [s0], set(range(len(T))) - {s0}
    while left:
        cur = T[order[-1]]
        nxt = min(left, key=lambda j: np.linalg.norm(T[j] - cur))
        order.append(nxt); left.remove(nxt)
    first, last = T[order[0]], T[order[-1]]
    key = {"north": (1, 1), "south": (1, -1), "east": (0, 1), "west": (0, -1)}.get(str(start).lower(), (1, 1))  # (axis: 0=x/east, 1=y/north, sign)
    if (first[key[0]] - last[key[0]]) * key[1] < 0:      # the first tower must be the one furthest towards `start`
        order = order[::-1]
    return order


def detect(pc, opts=None, forward_bearing=None, reverse=False, main_xy=None, next_xy=None, prev_xy=None):
    o = {**DEFAULTS, **(opts or {})}
    xyz, cls = pc["xyz"], pc["cls"]
    flags, info = [], {}

    G, gz, h = _ground_cache(pc, o)

    # ---- tower(s): XY cells with the tallest continuous vertical occupancy
    towers = [(np.asarray(main_xy, float), 1)] if main_xy is not None else find_towers(xyz, h, o["tower_cell"])
    strong = [t for t in towers if t[1] >= 0.6 * towers[0][1]] if towers else []
    if strong:
        # the report tower = the strong tower nearest the centre of the FIRST file (tiles are cut around their tower)
        ref = pc.get("primary_xy")
        c_xy = min(strong, key=lambda t: np.linalg.norm(t[0] - ref))[0] if ref is not None else strong[0][0]
        info["tower_source"] = "geometry (vertical occupancy)"
    elif cls is not None and (cls == 15).sum() > 200:
        c_xy = np.median(xyz[cls == 15][:, :2], axis=0)
        info["tower_source"] = "classification 15"
    else:
        raise RuntimeError("No tower found in the point cloud.")
    others = [t[0] for t in strong if 60 < np.linalg.norm(t[0] - c_xy) < 1500]
    if main_xy is not None:                       # the caller (multi-tower run) decides the pair
        others = [np.asarray(next_xy, float)] if next_xy is not None else []
    info["towers_found"] = 1 + len(others)
    near = np.linalg.norm(xyz[:, :2] - c_xy, axis=1) < 12
    H = float(np.percentile(h[near], 99.7))
    info["tower_height_m"] = round(H, 1)

    # ---- line direction: PCA of high points 12-70 m from the tower
    r = np.linalg.norm(xyz[:, :2] - c_xy, axis=1)
    hi = (h > 0.5 * H) & (r > 12) & (r < 70)
    if hi.sum() < 200:
        raise RuntimeError("Not enough wire points around the tower - is the tile centred on the tower?")
    d = xyz[hi, :2] - c_xy
    w, vec = np.linalg.eigh(np.cov(d.T))
    ax = vec[:, 1]
    nxt = None
    if others:                                           # a second tower along the line: the span runs towards it
        cand = others if main_xy is not None else [t for t in others if abs((t - c_xy) @ ax) / np.linalg.norm(t - c_xy) > 0.9]
        if cand:
            nxt = min(cand, key=lambda t: np.linalg.norm(t - c_xy))
    if nxt is not None:
        if main_xy is not None:
            # the caller gave the span: measure along the exact tower-to-tower direction (at angle towers the
            # average wire direction around the tower points between the two spans and misses both)
            ax = (nxt - c_xy) / np.linalg.norm(nxt - c_xy)
        if ax @ (nxt - c_xy) < 0: ax = -ax
        if forward_bearing is not None:
            flags.append("Two towers in the data: forward = towards the other tower; the forward bearing was not needed.")
    elif forward_bearing is not None:                      # bearing clockwise from north, degrees
        b = np.radians(forward_bearing)
        want = np.array([np.sin(b), np.cos(b)])
        if ax @ want < 0: ax = -ax
    else:
        if ax[1] < 0 or (abs(ax[1]) < 1e-6 and ax[0] < 0): ax = -ax
        flags.append("Forward direction not given: assumed the northern/eastern end of the tile is 'forward', so "
                     "Left/Right may be swapped. Pass forward_bearing to fix.")
    if reverse:
        ax = -ax
    if nxt is not None:
        D = float((nxt - c_xy) @ ax)
        if D > 0:                                        # measure only inside the span between the two towers
            info["next_tower_m"] = round(D, 1); info["span_end_u"] = D - 8.0
        else:
            flags.append("Reverse direction: measuring the span away from the second tower.")
    left = np.array([-ax[1], ax[0]])
    R = np.vstack([ax, left])                            # rows: u axis, v axis (xy -> uv: xy @ R.T) ; store as R so uv = (xy-c) @ R.T
    uv = (xyz[:, :2] - c_xy) @ R.T
    z0 = float(gz(c_xy[None, :])[0])
    P = np.column_stack([uv, xyz[:, 2] - z0])
    Gu = (G[:, :2] - c_xy) @ R.T
    Gf = np.column_stack([Gu, G[:, 2] - z0])
    info["z0"] = z0
    if nxt is not None:
        info["next_tower_xy"] = [round(float(c), 3) for c in nxt]
    if nxt is not None and prev_xy is not None:          # how much the line turns at this tower
        a1 = c_xy - np.asarray(prev_xy, float); a2 = nxt - c_xy
        cosang = (a1 @ a2) / (np.linalg.norm(a1) * np.linalg.norm(a2))
        info["line_angle_deg"] = round(float(np.degrees(np.arccos(np.clip(cosang, -1, 1)))), 1)
    sc = Scene(pts=P, ground=Gf, grid=gz, H=H, flags=flags, info=info, R=R.copy(), centre_xy=c_xy)
    hP = h                                   # same points, same ground: height above ground is frame-independent
    sc.hP = hP
    sc.rgb = pc.get("rgb")                   # same point order as sc.pts (or None)
    del uv

    # ---- wires in forward / backward slabs -> clusters in (v, z)
    def wire_clusters(sign):
        u0, u1 = o["slab_u"]
        m = ((sign * P[:, 0] > u0) & (sign * P[:, 0] < u1) & (hP > o["wire_min_h_frac"] * H)
             & (np.abs(P[:, 1]) < o["corridor_v"]))          # other lines nearby are ignored
        S = P[m]
        if len(S) < 50: return []
        res = 0.25
        vi = np.floor((S[:, 1] - S[:, 1].min()) / res).astype(int)
        zi = np.floor((S[:, 2] - S[:, 2].min()) / res).astype(int)
        grid = np.zeros((vi.max() + 1, zi.max() + 1), np.int32)
        np.add.at(grid, (vi, zi), 1)
        mask = ndimage.binary_dilation(grid >= 1, structure=np.ones((3, 3)), iterations=2)
        lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
        L = lab[vi, zi]
        out = []
        for k in range(1, n + 1):
            pk = S[L == k]
            if len(pk) < 30: continue
            if np.ptp(pk[:, 0]) < o["min_wire_len"]: continue
            out.append(pk)
        return out

    comps = wire_clusters(+1)
    if len(comps) < 3:
        sc.flags.append(f"Only {len(comps)} wire clusters found in the forward slab (need 3 phases + OPGW).")
    fits = []
    for pk in comps:
        kv, v0 = np.polyfit(pk[:, 0], pk[:, 1], 1)
        kz, z0f = np.polyfit(pk[:, 0], pk[:, 2], 1)
        fits.append(dict(pts=pk, v0=v0, kv=kv, z0=z0f, kz=kz))
    fits.sort(key=lambda f: -f["z0"])
    zs = np.array([f["z0"] for f in fits])
    if len(fits) >= 4:
        gaps = zs[:-1] - zs[1:]
        # shield wires are above the largest z-gap that still leaves exactly 3 phases below
        cand = [i for i in range(len(gaps)) if len(fits) - (i + 1) == 3]
        cut = (cand[0] if cand else int(np.argmax(gaps))) + 1
        shield, phases = fits[:cut], fits[cut:]
    else:
        shield, phases = [], fits
    phases.sort(key=lambda f: -f["v0"])
    names = ["L", "M", "R"] if len(phases) == 3 else [f"P{i}" for i in range(len(phases))]
    for n, f in zip(names, phases): sc.wires[n] = f
    if shield:
        shield.sort(key=lambda f: -f["v0"])
        if len(shield) >= 2:             # twin OPGW: left one pairs with the Left conductor, right one with the Right conductor
            sc.wires["OPGW_L"], sc.wires["OPGW_R"] = shield[0], shield[-1]
        else:
            sc.wires["OPGW"] = shield[0]
    for k, f in sc.wires.items():
        sc.info[f"wire_{k}_at_tower"] = [round(float(f['v0']), 2), round(float(f['z0']), 2)]

    # ---- candidate points around the tower (wire / tower split happens later, once the tower type is known)
    nu = o["box_u"]                                     # tension jumpers reach ~12 m out to the dead-end clamps
    vmax = max([abs(f["v0"]) for f in sc.wires.values()] + [10]) + 6
    m = (np.abs(P[:, 0]) < nu) & (np.abs(P[:, 1]) < vmax) & (hP > 0.3)
    sc.box = dict(P=P[m], h=hP[m], cls=(pc["cls"][m] if cls is not None else None), opts=o)
    sc.info["jumper_loop"] = _loop_test(sc)
    sc.info["through_wire"] = _through_wire(sc)
    return sc


def _quad_ransac(u, z, tol=0.6, iters=1500, seed=0, pool=None, vertex_u=4.0, vertex_zmax=None):
    """robust fit of a SAGGING curve z = a u^2 + b u + c (a > 0: hangs down like a jumper).
    pool: indices to draw the 3 sample points from (e.g. points well below the conductor line)."""
    rng = np.random.default_rng(seed)
    pool = np.arange(len(u)) if pool is None or len(pool) < 3 else pool
    best = None
    for _ in range(iters):
        i = rng.choice(pool, 3, replace=False)
        if len(set(np.round(u[i], 1))) < 3: continue
        c = np.polyfit(u[i], z[i], 2)
        if c[0] < 0.006: continue                        # arches (insulators, cross-arms) are not jumpers
        uv = -c[1] / (2 * c[0])                          # lowest point of the curve
        if abs(uv) > vertex_u: continue                  # a jumper hangs symmetrically across the tower
        if vertex_zmax is not None and np.polyval(c, uv) > vertex_zmax: continue
        inl = np.abs(np.polyval(c, u) - z) < tol
        if best is None or inl.sum() > best.sum(): best = inl
    if best is None or best.sum() < 3: return np.zeros(len(u), bool), None
    c = np.polyfit(u[best], z[best], 2)
    if c[0] < 0.006: return np.zeros(len(u), bool), None
    return np.abs(np.polyval(c, u) - z) < tol, c


def _jumper_pts(sc, k, half_u=None):
    """points of a jumper loop of phase k: a curve spanning u that sags below the phase line."""
    f = sc.wires[k]; B = sc.box["P"]
    if half_u is None: half_u = sc.box["opts"]["jumper_half_u"]
    # at the tower the jumper hangs where the conductor is attached (v0): don't follow the span's slope in v,
    # it bends at angle towers
    dv = B[:, 1] - f["v0"]; dz = B[:, 2] - (f["z0"] + f["kz"] * B[:, 0])
    band = (np.abs(dv) < 3.0) & (dz > -9) & (dz < 0.5) & (np.abs(B[:, 0]) < half_u)   # jumpers can swing ~2 m outboard
    if band.sum() < 30: return np.empty((0, 3)), None
    Bb, dzb = B[band], dz[band]
    inl, c = _quad_ransac(Bb[:, 0], Bb[:, 2], pool=np.flatnonzero(dzb < -1.0), vertex_zmax=f["z0"] - 1.0)
    return Bb[inl], c


def _loop_test(sc):
    """True if some phase has a continuous curve sagging below its line across the tower plane (a jumper loop = tension tower).
    A tower member can fake a curve at one u; a real loop fills every 0.5 m bin from u=-4 to 4."""
    for k in [k for k in ("M", "L", "R") if k in sc.wires]:
        J, c = _jumper_pts(sc, k)
        if c is None or len(J) < 30: continue
        f = sc.wires[k]
        dz = J[:, 2] - (f["z0"] + f["kz"] * J[:, 0])
        loop = J[(dz < -0.8) & (np.abs(J[:, 0]) <= 4.0)]
        if len(loop) < 30: continue
        h, _ = np.histogram(loop[:, 0], bins=np.arange(-4, 4.01, 0.5))
        depth = -dz[np.abs(J[:, 0]) < 1.5].min() if (np.abs(J[:, 0]) < 1.5).any() else 0
        if (h >= 3).mean() >= 0.85 and depth > 1.0 and c[0] > 0:
            return True
    return False


def _through_wire(sc):
    """share of the tower plane (u -2..2) where a phase conductor runs straight through on its own line.
    Suspension tower: the conductor hangs from a vertical I / V string and passes the tower unbroken (about 1.0).
    Tension / dead-end tower: the conductor stops at the horizontal strain strings and only a jumper loop crosses the
    plane, so there is nothing on the line itself (about 0)."""
    B = sc.box["P"]; best = None
    for k in [k for k in ("M", "L", "R") if k in sc.wires]:
        f = sc.wires[k]
        d = np.hypot(B[:, 1] - (f["v0"] + f["kv"] * B[:, 0]), B[:, 2] - (f["z0"] + f["kz"] * B[:, 0]))
        u = B[(d < 0.8) & (np.abs(B[:, 0]) <= 2.0), 0]
        h, _ = np.histogram(u, bins=np.arange(-2, 2.01, 0.5))
        frac = float((h >= 2).mean())
        best = frac if best is None else max(best, frac)
    return best


def separate(sc, ttype):
    """split the box points into tower / wires for the chosen tower type."""
    o = sc.box["opts"]; B, hB, cls = sc.box["P"], sc.box["h"], sc.box["cls"]
    near = {}
    wire = np.zeros(len(B), bool)
    for k in ("L", "M", "R"):
        if k not in sc.wires: continue
        f = sc.wires[k]
        if ttype == "tension":
            J, c = _jumper_pts(sc, k)
            dz = B[:, 2] - (f["z0"] + f["kz"] * B[:, 0])
            # conductor ends beyond the strain insulators (both spans; at angle towers the back span bends, so a wider band)
            cond = (np.abs(B[:, 0]) > 6) & (np.abs(dz) < 1.0) & (np.abs(B[:, 1] - f["v0"]) < 3.0 + 0.15 * np.abs(B[:, 0]))
            wire |= cond
            if c is not None:
                jm = ((np.abs(B[:, 1] - f["v0"]) < 3.0) & (np.abs(B[:, 0]) < o["jumper_half_u"])
                      & (np.abs(B[:, 2] - np.polyval(c, B[:, 0])) < 1.2))
                near[k] = B[jm]; wire |= jm
        else:
            d = np.hypot(B[:, 1] - (f["v0"] + f["kv"] * B[:, 0]), B[:, 2] - (f["z0"] + f["kz"] * B[:, 0]))
            msk = d < 1.6
            near[k] = B[d < 0.8]; wire |= msk       # remove hardware within 1.6 m, measure from the conductor core only
    for kk in [k for k in sc.wires if k.startswith("OPGW")]:      # shield-wire core points (tower peak excluded by u)
        f = sc.wires[kk]
        d = np.hypot(B[:, 1] - (f["v0"] + f["kv"] * B[:, 0]), B[:, 2] - (f["z0"] + f["kz"] * B[:, 0]))
        near[kk] = B[d < 0.6]
    rest, hR = B[~wire], hB[~wire]
    if cls is not None and (cls[~wire] == 15).sum() > 200:
        is_tower = cls[~wire] == 15
    elif len(rest):
        vox = o["voxel"]; mn = rest.min(0)
        ij = np.floor((rest - mn) / vox).astype(int)
        grid = np.zeros(ij.max(0) + 1, bool); grid[tuple(ij.T)] = True
        lab, _ = ndimage.label(grid, structure=np.ones((3, 3, 3)))
        L = lab[tuple(ij.T)]
        low = np.unique(L[hR < 2.5]); low = low[low > 0]
        is_tower = np.isin(L, low)
    else:
        is_tower = np.zeros(0, bool)
    if not is_tower.any():
        sc.flags.append("Could not find a ground-connected tower structure near the centre.")
    sc.tower = rest[is_tower]
    sc.near = near
    sc.near_wire = np.vstack([v for k, v in near.items() if not k.startswith("OPGW")]) if near else np.empty((0, 3))
    sc.info["tower_pts"] = int(len(sc.tower)); sc.info["near_wire_pts"] = {k: int(len(v)) for k, v in near.items()}
    return sc


def _seen_type(sc):
    """what the point cloud itself says, using the tower-type reference sheets:
    - a jumper loop sagging below the line across the tower plane                 -> tension (strain / dead-end)
    - no conductor through the tower plane and the line turns by > 15 deg          -> tension (angle / deviation / terminal)
    - the conductor passes the tower unbroken on a hanging I / V string            -> suspension (tangent)
    returns (type, reason)"""
    thr = sc.info.get("through_wire"); ang = sc.info.get("line_angle_deg") or 0.0
    if sc.info.get("jumper_loop"): return "tension", "jumper loop found"
    if thr is not None and thr < 0.3 and ang > 15:
        return "tension", f"conductor does not pass the tower and the line turns {ang:.0f} deg (angle / dead-end tower)"
    if thr is not None and thr >= 0.6: return "suspension", "conductor passes the tower unbroken"
    return "suspension", "no jumper loop"


def classify_tower_type(sc, forced=None, filename=""):
    """explicit > filename keyword > geometry (see _seen_type)."""
    seen, why = _seen_type(sc)
    if forced and forced != "auto":
        if seen != forced:
            sc.flags.append(f"You chose {forced.upper()} but the agent sees a {seen.upper()} tower here ({why})"
                            " - check the tower type, or set it to auto.")
        return forced, "given"
    low = filename.lower()
    if "tension" in low: return "tension", "filename"
    if "suspension" in low: return "suspension", "filename"
    return seen, f"geometry ({why})"
