"""3-D preview of the cloud with the measurement lines, so you can check the markings before the report."""
import numpy as np


def draw(ax, ctx, max_pts=60000):
    sc, markers = ctx["sc"], ctx["markers"]
    P = sc.pts
    h = sc.hP if hasattr(sc, "hP") else P[:, 2]
    sel = (np.abs(P[:, 0]) < 60) & (np.abs(P[:, 1]) < 40)
    Q, hq = P[sel], h[sel]
    if len(Q) > max_pts:
        i = np.random.default_rng(0).choice(len(Q), max_pts, replace=False); Q, hq = Q[i], hq[i]
    ax.scatter(Q[:, 0], Q[:, 1], Q[:, 2], c=hq, s=0.4, cmap="viridis", linewidths=0)
    for m in markers:
        a, b = np.array(m["a"]), np.array(m["b"])
        ax.plot([a[0], b[0]], [a[1], b[1]], [a[2], b[2]], color="red", lw=2)
        mid = (a + b) / 2
        ax.text(mid[0], mid[1], mid[2], m["name"].split("-")[-1], color="red", fontsize=8)
    ax.set_xlabel("u (along line, m)"); ax.set_ylabel("v (left, m)"); ax.set_zlabel("height (m)")
    ax.set_box_aspect((np.ptp(Q[:, 0]) or 1, np.ptp(Q[:, 1]) or 1, np.ptp(Q[:, 2]) or 1))
    ax.set_title(f"{ctx['ttype'].title()} tower - red lines = measurements (numbers = Reference Image no.)")
