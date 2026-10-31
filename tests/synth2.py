"""Two suspension towers 380 m apart (span 1: sag 12 m). Beyond the second tower the next span sags 25 m -
lower than span 1 - so a tool that does not stop at the second tower picks the wrong sag point.
Writes: <out>_both.laz (one file), <out>_A.laz (u<200) and <out>_B.laz (u>=200), plus truth json.
usage: python tests/synth2.py /tmp/t/two"""
import sys, json, numpy as np, laspy
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from synth import line
rng = np.random.default_rng(2)
L1, S1, S2 = 380.0, 12.0, 25.0
za = 44.0

def tower(u0, add):
    for sx in (-1, 1):
        for sy in (-1, 1):
            add(line([u0 + sx * 5, sy * 5, 0], [u0 + sx * 2, sy * 2, 30]), 15)
    for z in range(0, 31, 5):
        w = 5 - 3 * z / 30
        for a_, b_ in (([-w, -w], [w, -w]), ([w, -w], [w, w]), ([w, w], [-w, w]), ([-w, w], [-w, -w])):
            add(line([u0 + a_[0], a_[1], z], [u0 + b_[0], b_[1], z]), 15)
    for s in (-1, 1):
        add(line([u0, s * 6.3, za + 2], [u0, s * 17, za + 2]), 15)
        add(line([u0, s * 8.4, 0], [u0, s * 8.4, za + 2]), 15)
        add(line([u0, s * 6.3, 30], [u0, s * 6.3, za - 6.55]), 15)
    add(line([u0, -6.3, za - 6.55], [u0, 6.3, za - 6.55]), 15); add(line([u0, -6.3, za + 6.17], [u0, 6.3, za + 6.17]), 15)
    add(line([u0, -6.3, za - 6.55], [u0, -6.3, za + 6.17]), 15); add(line([u0, 6.3, za - 6.55], [u0, 6.3, za + 6.17]), 15)

def zw(u, z_att, s1, s2):
    z = np.empty_like(u)
    a = u < 0; z[a] = z_att - 4 * s1 * (-u[a] / L1) * (1 + u[a] / L1)
    b = (u >= 0) & (u <= L1); z[b] = z_att - 4 * s1 * (u[b] / L1) * (1 - u[b] / L1)
    c = u > L1; uu = u[c] - L1; z[c] = z_att - 4 * s2 * (uu / L1) * (1 - uu / L1)
    return z

if __name__ == "__main__":
    pts, cl = [], []
    def add(p, c): pts.append(p); cl.append(np.full(len(p), c, np.uint8))
    gx, gy = np.meshgrid(np.arange(-120, 600, 1.0), np.arange(-60, 60, 1.0))
    g = np.column_stack([gx.ravel(), gy.ravel()]); add(np.column_stack([g, rng.normal(0, 0.05, len(g))]), 2)
    tower(0.0, add); tower(L1, add)
    u = np.arange(-110, 590, 0.12)
    for v in (17.0, 0.0, -17.0):
        for sub in (-0.2, 0.2):
            add(np.column_stack([u, np.full_like(u, v + sub), zw(u, za, S1, S2)]), 14)
    for v in (8.5, -8.5):
        add(np.column_stack([u, np.full_like(u, v), zw(u, za + 17.8, 5.0, 10.0)]), 13)
    P = np.vstack(pts); C = np.concatenate(cl)
    th = np.radians(200.0)          # line runs SSW: the default 'north/east = forward' guess would be WRONG here
    ux = np.array([np.sin(th), np.cos(th)]); lx = np.array([-ux[1], ux[0]])
    xy = np.outer(P[:, 0], ux) + np.outer(P[:, 1], lx)
    W = np.column_stack([xy[:, 0] + 500000, xy[:, 1] + 2950000, P[:, 2] + 170])
    def write(path, m):
        hdr = laspy.LasHeader(point_format=3, version="1.2"); hdr.scales = [0.001] * 3; hdr.offsets = W.min(0)
        las = laspy.LasData(hdr); las.x, las.y, las.z = W[m, 0], W[m, 1], W[m, 2]; las.classification = np.zeros(m.sum(), np.uint8)
        las.write(path)
    out = sys.argv[1]
    write(out + "_both.laz", np.ones(len(W), bool)); write(out + "_A.laz", P[:, 0] < 200); write(out + "_B.laz", P[:, 0] >= 200)
    z_c, z_o = za - S1, za + 17.8 - 5.0
    truth = dict(gnd=z_c, phase=17.0 - 0.4, opgw=float(np.hypot(17 - 8.5 - 0.2, z_o - z_c)), sag_u=190.0,
                 gnd_if_wrong_span=za - S2, next_tower_m=L1)
    json.dump(truth, open(out + "_truth.json", "w")); print(truth)
