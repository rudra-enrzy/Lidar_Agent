"""Four towers in ONE file: T at u = 0, 380, 730, 1130 m. Tower 2 is a TENSION tower (dead-ended conductors +
jumper loops), the others are suspension. Each span has its own sag, so every span report has different answers.
+ T-108 extras: arcing horns on the tension tower, and a crossing power line under span 3.
usage: python tests/synth4.py /tmp/t/four_x.laz   (writes the LAZ + <out>.truth.json)"""
import sys, json, numpy as np, laspy
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from synth import line
from synth2 import tower
rng = np.random.default_rng(3)
U = [0.0, 380.0, 730.0, 1130.0]
SAG = [12.0, 9.0, 15.0]                 # conductor sag per span
SAG_OPGW = 5.0
TENSION = {1}
za = 44.0

def tension_tower(u0, add):
    for sx in (-1, 1):
        for sy in (-1, 1):
            add(line([u0 + sx * 5, sy * 5, 0], [u0 + sx * 2, sy * 2, 30]), 15)
    for z in range(0, 31, 5):
        w = 5 - 3 * z / 30
        for a_, b_ in (([-w, -w], [w, -w]), ([w, -w], [w, w]), ([w, w], [-w, w]), ([-w, w], [-w, -w])):
            add(line([u0 + a_[0], a_[1], z], [u0 + b_[0], b_[1], z]), 15)
    for s in (-1, 1):
        add(line([u0, s * 6, za + 4], [u0, s * 17, za + 4]), 15)
        add(line([u0, s * 6, 30], [u0, s * 6, za + 4]), 15)
        add(line([u0, s * 9, 0], [u0, s * 9, za + 4]), 15)
    add(line([u0, -6, za - 3.0 + 5.66], [u0, 6, za - 3.0 + 5.66]), 15)
    add(line([u0, -6, za - 3.0 - 6.95], [u0, 6, za - 3.0 - 6.95]), 15)

def z_wire(u, z_att, sags):
    z = np.full_like(u, z_att)
    for i in range(3):
        m = (u >= U[i]) & (u <= U[i + 1]); L = U[i + 1] - U[i]; x = u[m] - U[i]
        z[m] = z_att - 4 * sags[i] * (x / L) * (1 - x / L)
    m = u < U[0]; z[m] = z_att - 0.03 * (U[0] - u[m])
    m = u > U[-1]; z[m] = z_att - 0.03 * (u[m] - U[-1])
    return z

pts, cl = [], []
def add(p, c): pts.append(p); cl.append(np.full(len(p), c, np.uint8))
gx, gy = np.meshgrid(np.arange(-60, 1190, 1.0), np.arange(-50, 50, 1.0))
g = np.column_stack([gx.ravel(), gy.ravel()]); add(np.column_stack([g, rng.normal(0, 0.05, len(g))]), 2)
for i, u0 in enumerate(U):
    (tension_tower if i in TENSION else tower)(u0, add)
u = np.arange(-60, 1190, 0.12)
for v in (17.0, 0.0, -17.0):
    for sub in (-0.2, 0.2):
        uu = u.copy()
        keep = np.ones_like(uu, bool)
        for i in TENSION: keep &= np.abs(uu - U[i]) >= 6          # dead-ended: the conductor stops at the strain clamps
        uu = uu[keep]
        add(np.column_stack([uu, np.full_like(uu, v + sub), z_wire(uu, za, SAG)]), 14)
        for i in TENSION:                                         # jumper loop across the tension tower
            uj = np.linspace(U[i] - 6, U[i] + 6, 140); dip = 3.0 if v == 0 else 4.0
            add(np.column_stack([uj, np.full_like(uj, v + sub), za - dip * (1 - ((uj - U[i]) / 6) ** 2)]), 14)
# arcing horns: short rods hanging 1 m below the strain string at the tower end (u0 +-2.5)
for i in TENSION:
    for v in (17.0, 0.0, -17.0):
        for su in (-1, 1):
            zz = np.linspace(za - 1.0, za, 15)
            add(np.column_stack([np.full(15, U[i] + su * 2.5), np.full(15, v), zz]), 15)
# crossing line under span 3: crosses at u=930, v=0, 60 deg; 3 wires at 12 m + earth wire at 15 m
tt = np.arange(-55, 55, 0.2); cx = np.array([np.cos(np.radians(60)), np.sin(np.radians(60))]); nx = np.array([-cx[1], cx[0]])
for off, zc in ((-3, 12.0), (0, 12.0), (3, 12.0), (0, 15.0)):
    q = np.array([930.0, 0.0]) + np.outer(tt, cx) + off * nx
    ok = np.abs(q[:, 1]) < 49
    add(np.column_stack([q[ok], np.full(ok.sum(), zc) + 0.002 * tt[ok] ** 2]), 1)
# some trees (should not be taken for a crossing line)
for cu, cv in ((500, 20), (520, -25), (600, 10), (1000, 30)):
    tp = rng.normal(0, 2.5, (3000, 3)); tp[:, 2] = np.abs(tp[:, 2]) * 2 + 3
    add(tp + [cu, cv, 0], 1)
for v in (8.5, -8.5):
    add(np.column_stack([u, np.full_like(u, v), z_wire(u, za + 17.8, [SAG_OPGW] * 3)]), 13)
P = np.vstack(pts)
th = np.radians(200.0)
ux = np.array([np.sin(th), np.cos(th)]); lx = np.array([-ux[1], ux[0]])
xy = np.outer(P[:, 0], ux) + np.outer(P[:, 1], lx)
W = np.column_stack([xy[:, 0] + 500000, xy[:, 1] + 2950000, P[:, 2] + 170])
out = sys.argv[1]
hdr = laspy.LasHeader(point_format=3, version="1.2"); hdr.scales = [0.001] * 3; hdr.offsets = W.min(0)
las = laspy.LasData(hdr); las.x, las.y, las.z = W[:, 0], W[:, 1], W[:, 2]; las.classification = np.zeros(len(W), np.uint8)
# colours: brown fields, a grey asphalt road (8 m, 70 deg) crossing span 2 (after the tension tower) at u=555
col = np.tile(np.array([150, 150, 150], np.uint16), (len(P), 1))
CL = np.concatenate(cl); g_ = CL == 2
col[g_] = [115, 95, 75]
rd = np.array([np.cos(np.radians(70)), np.sin(np.radians(70))]); rn = np.array([-rd[1], rd[0]])
off = (P[:, :2] - [555.0, 0.0]) @ rn
col[g_ & (np.abs(off) < 4)] = [88, 88, 90]
along = (P[:, :2] - [555.0, 0.0]) @ rd
col[g_ & (np.abs(off) < 0.15) & ((along % 6) < 3)] = [230, 230, 230]
col[CL == 1] = [60, 120, 50]
las.red, las.green, las.blue = col[:, 0] * 256, col[:, 1] * 256, col[:, 2] * 256
las.write(out)
truth = {}
for i in range(3):
    truth[f"span{i + 1}"] = dict(mid_u=(U[i + 1] - U[i]) / 2, gnd=za - SAG[i], phase=16.6,
                                 opgw=float(np.hypot(17 - 8.5 - 0.2, 17.8 + SAG[i] - SAG_OPGW)),
                                 first_tower_type="tension" if i in TENSION else "suspension")
truth["road_span2"] = 35.01
truth["cross_span3"] = float(za - 4 * SAG[2] * 0.25 - 0.0 - 15.0)
truth["horn"] = "outer ~%.2f, middle ~%.2f" % (4.0 * (1 - (2.5 / 6) ** 2) - 1.0, 3.0 * (1 - (2.5 / 6) ** 2) - 1.0)
json.dump(truth, open(out + ".truth.json", "w"), indent=1); print(json.dumps(truth))
