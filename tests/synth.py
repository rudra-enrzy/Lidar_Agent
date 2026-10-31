"""Synthetic 765 kV tower tiles with KNOWN clearances, to regression-test the engine.
usage: python tests/synth.py suspension|tension out.laz"""
import sys, numpy as np, laspy
rng = np.random.default_rng(1)

def line(a, b, step=0.1):
    a, b = np.array(a, float), np.array(b, float)
    n = max(int(np.linalg.norm(b - a) / step), 2)
    return a + (b - a) * np.linspace(0, 1, n)[:, None]

def make(kind, rot_deg=30, cx=500000.0, cy=2950000.0, cz=170.0):
    pts, cl = [], []
    def add(p, c): pts.append(p); cl.append(np.full(len(p), c, np.uint8))
    # ground: gentle slope + noise, + trees
    gx, gy = np.meshgrid(np.arange(-120, 260, 1.0), np.arange(-120, 120, 1.0))
    gxy = np.column_stack([gx.ravel(), gy.ravel()])
    gz = 0.01 * gxy[:, 0] + rng.normal(0, 0.05, len(gxy))
    add(np.column_stack([gxy, gz]), 2)
    trees = rng.uniform([60, -60], [180, 60], (40, 2))
    for tx, ty in trees:
        n = 300; tz = 0.01 * tx + rng.uniform(0, 12, n)
        add(np.column_stack([tx + rng.normal(0, 1.2, n), ty + rng.normal(0, 1.2, n), tz]), 1)
    # tower body (u,v,z): 4 legs 10 m square at base narrowing to 4 m at 40 m, then mast to 55
    for sx in (-1, 1):
        for sy in (-1, 1):
            add(line([sx * 5, sy * 5, 0], [sx * 2, sy * 2, 30]), 15)
    for z in range(0, 31, 5):
        w = 5 - 3 * z / 30
        for a_, b_ in (([-w, -w], [w, -w]), ([w, -w], [w, w]), ([w, w], [-w, w]), ([-w, w], [-w, -w])):
            add(line([*a_, z], [*b_, z]), 15)
    za = 44.0; truth = {}
    if kind == "suspension":
        # side arms with main legs hung off at v=+-8.4 (tower legs of an outer frame), cage around middle phase
        for s in (-1, 1):
            add(line([0, s * 6.3, za + 2], [0, s * 17, za + 2]), 15)       # cross arm (above conductor)
            add(line([0, s * 8.4, 0], [0, s * 8.4, za + 2]), 15)         # outer main leg
        zm = za
        for s in (-1, 1):
            add(line([0, s * 6.3, 30], [0, s * 6.3, zm - 6.55]), 15); add(line([0, s * 6.3, 30], [s * 2, s * 2, 30]), 15); add(line([0, s * 6.3, 30], [-s * 2, s * 2, 30]), 15)
        add(line([0, -6.3, zm - 6.55], [0, 6.3, zm - 6.55]), 15)         # cage bottom
        add(line([0, -6.3, zm + 6.17], [0, 6.3, zm + 6.17]), 15)         # cage top
        add(line([0, -6.3, zm - 6.55], [0, -6.3, zm + 6.17]), 15)        # cage left
        add(line([0, 6.3, zm - 6.55], [0, 6.3, zm + 6.17]), 15)          # cage right
        for v_, ztop in ((17, za + 2), (-17, za + 2), (0, zm + 6.17)):
            add(line([0, v_, ztop], [0, v_, za], 0.05), 15)      # insulator string: joins each conductor to the tower
        phases = {"L": 17.0, "M": 0.0, "R": -17.0}
        truth = {"phase_LM": 17.0, "phase_RM": 17.0, "s_M_top": 6.17, "s_M_bot": 6.55, "s_M_left": 6.3, "s_M_right": 6.3,
                 "s_L_leg": 17 - 8.4, "s_R_leg": 17 - 8.4}
    else:
        for s in (-1, 1):
            add(line([0, s * 6, za + 4], [0, s * 17, za + 4]), 15)       # cross arms
            add(line([0, s * 6, 30], [0, s * 6, za + 4]), 15); add(line([0, s * 6, 30], [2, s * 2, 30]), 15); add(line([0, s * 6, 30], [-2, s * 2, 30]), 15)
        add(line([0, -6, za - 3.0 + 5.66], [0, 6, za - 3.0 + 5.66]), 15)             # middle upper cage arm
        add(line([0, -6, za - 3.0 - 6.95], [0, 6, za - 3.0 - 6.95]), 15)               # middle lower cage arm
        add(line([0, -9, 0], [0, -9, za + 4]), 15); add(line([0, 9, 0], [0, 9, za + 4]), 15)
        phases = {"L": 17.0, "M": 0.0, "R": -17.0}
    # wires: parabolic sag, span 400 m, lowest point at u=+200 (beyond the +-230 tile? tile to 250)
    s_f = 12.0
    def zwire(u, z_att):
        uu = np.abs(u)
        return z_att - 4 * s_f * (uu / 400) * (1 - uu / 400)
    for name, v in phases.items():
        for sub in (-0.2, 0.2):
            u = np.arange(-230 if kind == "suspension" else 6, 250, 0.12)
            if kind == "tension":
                for sgn in (-1, 1):
                    uu = sgn * np.arange(6, 250, 0.12)
                    add(np.column_stack([uu, v + sub + 0 * uu, zwire(uu, za)]), 14)
                # jumper loop between strain ends at u=-6..6, dips 4 m
                uj = np.linspace(-6, 6, 120)
                zj = za - 4.0 * (1 - (uj / 6) ** 2)
                if name == "M": zj = za - 3.0 * (1 - (uj / 6) ** 2) - 0.0
                add(np.column_stack([uj, np.full_like(uj, v + sub), zj]), 14)
                if sub == -0.2: truth[f"null_{name}"] = (v, za - (3.0 if name == "M" else 4.0))
            else:
                add(np.column_stack([u, v + sub + 0 * u, zwire(u, za)]), 14)
    # OPGW above centre
    u = np.arange(-230, 250, 0.12); uu = np.abs(u); add(np.column_stack([u, 0 * u, za + 17.8 - 4 * 5.0 * (uu / 400) * (1 - uu / 400)]), 13)   # OPGW sags less (5 m)
    truth["gnd_L"] = za - s_f + 0  # relative to local ground; fixed below
    if kind == "tension": truth.update(t_L_arm=8.0, t_R_arm=8.0, t_M_upper=5.66, t_M_lower=6.95, t_L_leg=7.8, t_R_leg=7.8)
    truth["opgw_R"] = float(np.hypot(17, 17.8)); truth["opgw_L"] = truth["opgw_R"]
    truth["opgw_R_sag"] = float(np.hypot(17, (17.8 + 12 - 5)))   # at mid-span (u=200): conductor sags 12, OPGW 5
    P = np.vstack(pts); C = np.concatenate(cl)
    th = np.radians(rot_deg)
    # u axis points to bearing = rot (so +u -> north-east-ish), v = left
    ux = np.array([np.sin(th), np.cos(th)]); lx = np.array([-ux[1], ux[0]])
    xy = np.outer(P[:, 0], ux) + np.outer(P[:, 1], lx)
    W = np.column_stack([xy[:, 0] + cx, xy[:, 1] + cy, P[:, 2] + cz])
    # ground clearance truth: lowest wire (u=200) - ground at its xy (0.01*u in tower frame)
    truth["gnd_L"] = (za - s_f) - 0.01 * 200
    truth["gnd_R"] = truth["gnd_L"]
    return W, C, truth

if __name__ == "__main__":
    kind, out = sys.argv[1], sys.argv[2]
    strip = len(sys.argv) > 3 and sys.argv[3] == "strip" 
    W, C, truth = make(kind)
    hdr = laspy.LasHeader(point_format=3, version="1.2"); hdr.scales = [0.001] * 3; hdr.offsets = W.min(0)
    las = laspy.LasData(hdr); las.x, las.y, las.z = W[:, 0], W[:, 1], W[:, 2]
    las.classification = np.zeros_like(C) if strip else C
    las.write(out)
    import json; json.dump({k: v for k, v in truth.items()}, open(out + ".truth.json", "w"), default=float)
    print(out, len(W), "pts")
