"""One LAZ with 4 towers (suspension, suspension, TENSION angle tower turning 12 deg, suspension).
Spans 380 m, 370 m, 360 m. Wires sag 12 m (OPGW 5 m). usage: python tests/synth_multi.py /tmp/t/multi.laz"""
import sys, json, numpy as np, laspy
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from synth import line
rng = np.random.default_rng(3)
za = 44.0
PH = {"L": 17.0, "M": 0.0, "R": -17.0}; OP = {"OL": 8.5, "OR": -8.5}

def frame(c, th):
    u = np.array([np.cos(th), np.sin(th)]); v = np.array([-u[1], u[0]])
    return lambda p: np.column_stack([c[0] + p[:, 0] * u[0] + p[:, 1] * v[0], c[1] + p[:, 0] * u[1] + p[:, 1] * v[1], p[:, 2]])

def tower(T, kind, add):
    loc = []
    L = lambda a, b: loc.append(line(a, b))
    for sx in (-1, 1):
        for sy in (-1, 1): L([sx * 5, sy * 5, 0], [sx * 2, sy * 2, 30])
    for z in range(0, 31, 5):
        w = 5 - 3 * z / 30
        for a_, b_ in (([-w, -w], [w, -w]), ([w, -w], [w, w]), ([w, w], [-w, w]), ([-w, w], [-w, -w])): L([*a_, z], [*b_, z])
    if kind == "S":
        for s in (-1, 1):
            L([0, s * 6.3, za + 2], [0, s * 17, za + 2]); L([0, s * 8.4, 0], [0, s * 8.4, za + 2]); L([0, s * 6.3, 30], [0, s * 6.3, za - 6.55])
        L([0, -6.3, za - 6.55], [0, 6.3, za - 6.55]); L([0, -6.3, za + 6.17], [0, 6.3, za + 6.17])
        L([0, -6.3, za - 6.55], [0, -6.3, za + 6.17]); L([0, 6.3, za - 6.55], [0, 6.3, za + 6.17])
    else:
        for s in (-1, 1):
            L([0, s * 6, za + 4], [0, s * 17, za + 4]); L([0, s * 6, 30], [0, s * 6, za + 4]); L([0, s * 9, 0], [0, s * 9, za + 4])
        L([0, -6, za - 3 + 5.66], [0, 6, za - 3 + 5.66]); L([0, -6, za - 3 - 6.95], [0, 6, za - 3 - 6.95])
        for v in PH.values():                                  # jumper loops between the strain ends at u = +-6
            for sub in (-0.2, 0.2):
                uj = np.linspace(-6, 6, 150); zj = za - (3.0 if v == 0 else 4.0) * (1 - (uj / 6) ** 2)
                loc.append(np.column_stack([uj, np.full_like(uj, v + sub), zj]))
    for p in loc: add(T(p), 15)
    for k in ("OL", "OR"): add(T(line([0, OP[k] - 0.5, za + 17.8], [0, OP[k] + 0.5, za + 17.8])), 15)   # earth-wire peaks

pts, cl = [], []
def add(p, c): pts.append(p); cl.append(np.full(len(p), c, np.uint8))
spans = [380.0, 370.0, 360.0]; turn = np.radians(12)
C = [np.array([0.0, 0.0])]; dirs = [0.0, 0.0, turn]
for L_, th in zip(spans, dirs): C.append(C[-1] + L_ * np.array([np.cos(th), np.sin(th)]))
kinds = ["S", "S", "T", "S"]
tdir = [0.0, 0.0, turn / 2, turn]                              # tower cross-arms on the bisector
for c, k, th in zip(C, kinds, tdir): tower(frame(c, th), k, add)
def attach(i, ph, side):                                       # wire attachment point at tower i (side = +1 forward, -1 back)
    T = frame(C[i], tdir[i]); v = {**PH, **OP}[ph]; z = za + (17.8 if ph in OP else 0.0)
    u = 6.0 * side if (kinds[i] == "T" and ph not in OP) else 0.0
    return T(np.array([[u, v, z]]))[0]
for i in range(3):
    for ph in list(PH) + list(OP):
        a, b = attach(i, ph, +1), attach(i + 1, ph, -1)
        s_ = 5.0 if ph in OP else 12.0
        subs = (0.0,) if ph in OP else (-0.2, 0.2)
        for sub in subs:
            t = np.linspace(0, 1, int(np.linalg.norm(b[:2] - a[:2]) / 0.12))
            P = a + (b - a) * t[:, None]; P[:, 2] -= 4 * s_ * t * (1 - t)
            d = (b - a)[:2] / np.linalg.norm((b - a)[:2]); P[:, :2] += np.array([-d[1], d[0]]) * sub
            add(P, 14)
# 60 m of wire before the first tower and after the last
for i, side in ((0, -1), (3, +1)):
    th = tdir[i]; d = np.array([np.cos(th), np.sin(th)]) * side
    for ph in list(PH) + list(OP):
        a = attach(i, ph, side); t = np.linspace(0, 60, 500)
        add(np.column_stack([a[0] + d[0] * t, a[1] + d[1] * t, a[2] - 0.02 * t]), 14)
xs = np.vstack([c for c in C]); lo, hi = xs.min(0) - 120, xs.max(0) + 120
gx, gy = np.meshgrid(np.arange(lo[0], hi[0], 1.0), np.arange(lo[1] - 40, hi[1] + 40, 1.0))
g = np.column_stack([gx.ravel(), gy.ravel()]); add(np.column_stack([g, rng.normal(0, 0.05, len(g))]), 2)
P = np.vstack(pts); Cc = np.concatenate(cl)
rot = np.radians(200.0); R = np.array([[np.cos(rot), -np.sin(rot)], [np.sin(rot), np.cos(rot)]])
XY = P[:, :2] @ R.T
W = np.column_stack([XY[:, 0] + 600000, XY[:, 1] + 2900000, P[:, 2] + 300])
hdr = laspy.LasHeader(point_format=3, version="1.2"); hdr.scales = [0.001] * 3; hdr.offsets = W.min(0)
las = laspy.LasData(hdr); las.x, las.y, las.z = W[:, 0], W[:, 1], W[:, 2]; las.classification = np.zeros(len(W), np.uint8)
las.write(sys.argv[1])
centres = (np.vstack(C) @ R.T + [600000, 2900000]).round(1).tolist()
json.dump(dict(kinds=kinds, spans=spans, centres=centres, gnd_mid=za - 12), open(sys.argv[1] + ".truth.json", "w"))
print(sys.argv[1], len(W), "points; towers", kinds, "centres", centres)
