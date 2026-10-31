"""LiDAR tower clearance agent - one LAS/LAZ with 1..n towers:

    1. open the LAS/LAZ
    2. find the towers, count them, put them in line order and number them (from the first tower number given)
    3. classify every tower (suspension / tension)
    4. for every span between two neighbouring towers: measure (tower rows at the first tower, span rows at mid-span)
    5. one Excel report per span ("T-90 - T-91"), one marked LAZ, Potree markers

    N towers -> N-1 span reports. With only one tower the span rows use the lowest sag point instead of mid-span.
"""
import argparse, json, os, re
import numpy as np
from .pointcloud import load
from . import latlon, pdf_report
from .detect import detect, classify_tower_type, separate, survey_towers, order_towers, line_chain
from .measure import measure
from .validate import remarks
from .report import build_report, write_markers, write_marked_las, marker_list


def all_las(a):
    """every input file, first one first (it sets the local origin and the default output name)"""
    return [a.laz] + ([a.next_las] if a.next_las else []) + list(a.add_las or [])


def parser():
    ap = argparse.ArgumentParser(prog="lidar_agent", description="LAS/LAZ with 1..n towers -> one clearance report per span")
    ap.add_argument("laz")
    ap.add_argument("--next-las", help="optional second LAS/LAZ (e.g. the next tower) merged with the first")
    ap.add_argument("--add-las", action="append", default=[], metavar="FILE",
                    help="another LAS/LAZ merged into the same cloud (repeat for more files, e.g. the tiles of one line)")
    ap.add_argument("--out-dir", help="folder for the reports (default: '<LAZ name> reports' next to the LAZ)")
    ap.add_argument("--out", help=argparse.SUPPRESS)                 # old single-report option, kept for scripts
    ap.add_argument("--first-tower", "--tower-no", dest="first_tower", default="T-1",
                    help="number of the FIRST tower in line order, e.g. T-90 (the next ones become T-91, T-92 ...)")
    ap.add_argument("--left-tower", help="tower No of the LEFTMOST tower (towers are shown 1..N from left to right in the "
                    "viewer; left = the west end, or the south end for a north-south line)")
    ap.add_argument("--remove-towers", default="",
                    help="towers to leave out, by their number in the left-to-right view, e.g. '2' or '2,5' "
                         "(a false detection: not used in any measurement or report)")
    ap.add_argument("--right-tower", help="tower No of the RIGHTMOST tower; with --left-tower this numbers every tower")
    ap.add_argument("--start", default="north", choices=["north", "south", "east", "west"],
                    help="if --left/--right-tower are not given: the end where the numbering starts")
    ap.add_argument("--line", default=""); ap.add_argument("--span", default="", help=argparse.SUPPRESS)
    ap.add_argument("--circuit", default="Circuit 1"); ap.add_argument("--capacity", default="765KV")
    ap.add_argument("--latlon", default="", help="lat, long of a single tower (only for a one-tower file)")
    ap.add_argument("--latlon-file", default="", help="Excel (.xlsx) or CSV with one row per tower: Tower | Latitude | Longitude")
    ap.add_argument("--client", default="Power Grid Corporation of India Limited (PGCIL)")
    ap.add_argument("--capture-date", help="YYYY-MM-DD"); ap.add_argument("--inspection-date", help="YYYY-MM-DD")
    ap.add_argument("--tower-type", default="auto", choices=["auto", "suspension", "tension"],
                    help="auto = classify every tower from its geometry (recommended)")
    ap.add_argument("--forward-bearing", type=float, help="only used when the LAZ has a single tower")
    ap.add_argument("--image-prefix", default="GWA_CKT1", help="prefix for the Reference Image names")
    ap.add_argument("--config", default=os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json"))
    ap.add_argument("--potree", action="store_true", help="open the result in the Potree viewer")
    ap.add_argument("--reverse", action="store_true", help="single-tower LAZ only: measure the other span")
    ap.add_argument("--wire-ref", choices=["mid", "sag", "tower"],
                    help="where phase/OPGW/ground clearances are taken (default mid-span)")
    ap.add_argument("--swap-lr", action="store_true", help="swap the Left/Right labels (mirror of 'facing forward')")
    ap.add_argument("--no-pdf", action="store_true", help="skip the PDF copy of each report")
    ap.add_argument("--no-mark", action="store_true", help="skip writing the marked LAZ")
    ap.add_argument("--voxel", type=float, default=0.08, help="thinning grid in metres (0 = every point)")
    return ap


def load_cfg(a):
    from .config import load
    cfg = load(a.config)
    d = cfg.setdefault("detect", {})
    if a.wire_ref: d["wire_ref"] = a.wire_ref
    if a.swap_lr: d["swap_lr"] = True
    return cfg


def tower_names(first, n):
    """'T-90' and 4 towers -> T-90, T-91, T-92, T-93 (keeps the prefix and any leading zeros)."""
    m = re.match(r"^(.*?)(\d+)\s*$", (first or "").strip())
    if not m:
        base = (first or "T").strip() or "T"
        return [f"{base}-{i + 1}" for i in range(n)]
    pre, num, w = m.group(1), int(m.group(2)), len(m.group(2))
    return [f"{pre}{str(num + i).zfill(w)}" for i in range(n)]


def parse_no(t):
    m = re.match(r"^(.*?)(\d+)\s*$", (t or "").strip())
    return (m.group(1), int(m.group(2)), len(m.group(2))) if m else None


def names_from_ends(left, right, n):
    """Leftmost and rightmost tower No -> a name for every tower from left to right (numbers may run up or down).
    Returns (names, warning)."""
    L, R = parse_no(left), parse_no(right)
    if not L or not R:
        return None, f"could not read the tower numbers '{left}' / '{right}'"
    step = 1 if R[1] >= L[1] else -1
    warn = None
    if abs(R[1] - L[1]) + 1 != n:
        warn = (f"you gave {left} ... {right} = {abs(R[1] - L[1]) + 1} towers, but {n} were found in the LAZ - "
                f"numbered {n} towers from {left}; check for a missing or extra tower")
    names = [f"{L[0]}{str(L[1] + step * i).zfill(L[2])}" for i in range(n)]
    return names, warn


def display_order(xys):
    """xys are already in line order (along the conductors). Left -> right as the viewer shows them: start at the
    west end (south end for a mostly north-south line)."""
    import numpy as np
    T = np.array(xys, float)
    if len(T) < 2: return list(range(len(T)))
    ext = np.ptp(T, axis=0); ax = 0 if ext[0] >= ext[1] else 1
    idx = list(range(len(T)))
    return idx if T[0, ax] <= T[-1, ax] else idx[::-1]


def out_dir(a):
    if a.out_dir: return a.out_dir
    if a.out: return os.path.dirname(os.path.abspath(a.out))
    return os.path.splitext(a.laz)[0] + " reports"


def safe(s):
    return re.sub(r'[\\/:*?"<>|]+', "_", s).strip()


class Run:
    """The whole job for one LAZ. Callbacks let the app show every step live."""

    def __init__(self, a, log=print, on_towers=None, on_span=None, on_found=None):
        self.a, self.cfg, self.log = a, load_cfg(a), log
        self.on_towers, self.on_span = on_towers or (lambda r: None), on_span or (lambda r, c: None)
        self.on_found = on_found or (lambda r: None)      # app: shows towers 1..N left->right and asks for the numbers
        self.spans, self.towers = [], []
        self.marked = None

    # 1. open
    def open(self):
        a = self.a
        self.log("1/4 opening the point cloud ...")
        self.pc = load(all_las(a), a.voxel, log=lambda s: None)
        self.log(f"    {self.pc['n_raw']:,} points ({self.pc['n']:,} used)")

    # 2. towers: find, count, order, number
    def find_towers(self):
        a = self.a
        self.log("2/4 finding and counting the towers ...")
        found = survey_towers(self.pc, self.cfg.get("detect"))
        if not found:
            raise RuntimeError("No tower found in this LAS/LAZ.")
        chain, off = line_chain(self.pc, [t[0] for t in found], self.cfg.get("detect"))
        for i in off:
            self.log(f"    ignored a structure {found[i][1]:.0f} m tall: not joined to this line by conductors "
                     "(another line, a pole, or a tower cut by the edge of the file)")
        found = [found[i] for i in chain]
        disp = display_order([t[0] for t in found])
        self.found = [dict(key=k + 1, xy=found[j][0], height=round(found[j][1], 1)) for k, j in enumerate(disp)]
        self.log(f"    {len(found)} tower(s) found (shown 1..{len(found)} from left to right)")
        self.on_found(self)                                # may set a.left_tower / a.right_tower / removals (asks the user)
        drop = {int(x) for x in re.split(r"[,\s]+", str(a.remove_towers or "")) if x.strip().isdigit()}
        if drop:
            kept = [t for t in self.found if t["key"] not in drop]
            if not kept: raise RuntimeError("Every tower was removed - keep at least one.")
            self.log("    removed by you: " + ", ".join(f"Tower {k}" for k in sorted(drop)) + " (not used in any measurement)")
            self.found = kept
        self.removed = sorted(drop)
        found = self.found
        names = None
        if a.left_tower and a.right_tower:
            names, warn = names_from_ends(a.left_tower, a.right_tower, len(found))
            if warn: self.log("FLAG: " + warn); self.flags_run = getattr(self, "flags_run", []) + [warn]
        if names:                                          # numbered from the user's leftmost / rightmost tower
            tw = [dict(t, name=names[i]) for i, t in enumerate(self.found)]
            tw.sort(key=lambda t: parse_no(t["name"])[1])  # spans always run from the lower to the higher number
            self.towers = tw
            how = f"leftmost = {a.left_tower}, rightmost = {a.right_tower}"
        else:
            order = order_towers([t["xy"] for t in self.found], a.start)
            names = tower_names(a.first_tower, len(found))
            self.towers = [dict(self.found[j], name=names[i]) for i, j in enumerate(order)]
            how = f"numbered from the {a.start} end"
        self.log(f"    {len(self.towers)} tower(s): " + ", ".join(t["name"] for t in self.towers) + f" ({how})")
        if len(self.towers) == 1:
            self.log("    only one tower: one report; the span rows use the lowest sag point (the next tower is not in the data)")
        else:
            self.log(f"    {len(self.towers) - 1} span report(s) will be written: " +
                     ", ".join(f"{t['name']} - {u['name']}" for t, u in zip(self.towers, self.towers[1:])))
        self.on_towers(self)

    # 3. every span: classify the first tower, measure
    def measure_spans(self):
        a, opts = self.a, self.cfg.get("detect")
        pairs = list(zip(self.towers, self.towers[1:])) or [(self.towers[0], None)]
        os.makedirs(out_dir(a), exist_ok=True)
        for i, (t, u) in enumerate(pairs):
            span = f"{t['name']} - {u['name']}" if u else (a.span or f"{t['name']} - {tower_names(t['name'], 2)[1]}")
            self.log(f"3/4 span {i + 1}/{len(pairs)}: {span}")
            prev = self.towers[i - 1]["xy"] if i > 0 else None
            sc = detect(self.pc, opts, a.forward_bearing if u is None else None, a.reverse if u is None else False,
                        main_xy=t["xy"], next_xy=u["xy"] if u else None, prev_xy=prev)
            ttype, how = classify_tower_type(sc, a.tower_type, "")
            separate(sc, ttype)
            res = measure(sc, ttype, opts)
            rem = remarks(res, self.cfg.get("min_clearance_m"))
            t["type"] = ttype
            self.log(f"    {t['name']}: {ttype} tower ({how}), height {sc.info['tower_height_m']} m"
                     + (f", next tower {sc.info.get('next_tower_m')} m away" if u else ""))
            for f in sc.flags: self.log("FLAG: " + f)
            for k, r in res.items():
                if r["conf"] != "na": self.log(f"      {k:10s} {r['value']!s:>8}  [{r['conf']}] {r['note']}")
            ctx = dict(sc=sc, ttype=ttype, how=how, res=res, rem=rem, tower=t["name"], span=span,
                       folder=safe(span), out=os.path.join(out_dir(a), safe(span) + "_Sag and Vegetation Clearance Report.xlsx"))
            ctx["markers"] = marker_list(ttype, res, a.image_prefix)
            D = sc.info.get("next_tower_m")
            if D:     # the "Span" picture: side view of the whole span, both towers in frame (no measurement line)
                hz = 0.6 * sc.info["tower_height_m"]
                gB = float(sc.ground_z(np.array([[D, 0.0]]))[0])
                ctx["markers"].append(dict(name=f"{a.image_prefix}-Span", label=f"Span {span}", key="span",
                                           a=[0.0, 0.0, hz], b=[float(D), 0.0, gB + hz], value=round(float(D), 2),
                                           ttype=ttype))
            ctx["caption"] = "  |  ".join(x for x in (a.line, f"Tower {t['name']}", f"Span {span}", a.circuit) if x)
            sc.pts = sc.hP = sc.box = sc.near_wire = sc.rgb = None          # free the big per-span arrays
            sc.__dict__.pop("_tracks", None)
            self.spans.append(ctx)
            self.on_span(self, ctx)

    # 3b. a measurement moved by hand in Potree (world coordinates of both ends) -> report value, marker, remark
    def edit(self, folder, key, pts_world):
        import numpy as np
        c = next((c for c in self.spans if c["folder"] == folder), None)
        if c is None or key not in c["res"]: raise KeyError(f"no measurement {key} in span {folder}")
        sc = c["sc"]
        P = np.asarray(pts_world, float) - self.pc["origin"]
        loc = np.column_stack([(P[:, :2] - sc.centre_xy) @ sc.R.T, P[:, 2] - sc.info["z0"]])
        orig = c.setdefault("orig", {}).setdefault(key, dict(c["res"][key]))
        if orig["a"] and np.allclose(np.array([orig["a"], orig["b"]], float), loc, atol=0.005):
            c["res"][key] = dict(orig); c["orig"].pop(key)          # moved back to where the agent put it
        else:
            c["res"][key] = dict(value=round(float(np.linalg.norm(loc[1] - loc[0])), 2),
                                 a=[round(float(x), 3) for x in loc[0]], b=[round(float(x), 3) for x in loc[1]],
                                 conf="manual", note="moved by hand in Potree (agent value: "
                                                     f"{orig['value'] if orig['value'] is not None else 'none'})")
        r = c["res"][key]
        for m in c["markers"]:
            if m["key"] == key: m.update(a=r["a"], b=r["b"], value=r["value"])
        return r["value"]

    def edited(self):
        return sum(len(c.get("orig", {})) for c in self.spans)

    def write_pdf(self, c):
        """PDF copy of one span's report; screenshots in <reports>/<span folder>/ are included when they exist
        (called again after 'Screenshot all' so the PDF then carries the pictures)."""
        def build():
            pdf_report.build_pdf(c["pdf"], c["meta"], c["ttype"], c["res"], c["rem"], self.a.image_prefix,
                                 image_dir=os.path.join(os.path.dirname(c["out"]), c["folder"]))
        try:
            try:
                build()
            except ImportError:                              # reportlab / pillow not installed on this machine yet
                self.log("    PDF needs the 'reportlab' package - installing it (one time) ...")
                import subprocess, sys
                r = subprocess.run([sys.executable, "-m", "pip", "install", "reportlab"], capture_output=True, text=True)
                if r.returncode: raise RuntimeError("pip install reportlab failed - run: pip install reportlab\n" + r.stderr[-300:])
                import importlib; importlib.invalidate_caches()
                build()
            return True
        except Exception as e:
            self.log(f"FLAG: PDF not written for {c['span']}: {e}")
            return False

    # 4. outputs: one Excel per span, one marked LAZ, markers
    def write(self):
        a, pc = self.a, self.pc
        for c in self.spans:                                  # remarks again: values may have been moved by hand
            c["rem"] = remarks(c["res"], self.cfg.get("min_clearance_m"))
        d = out_dir(a)
        stem = os.path.join(d, safe(os.path.splitext(os.path.basename(a.laz))[0]))
        allm = []
        for c in self.spans:
            mj = os.path.splitext(c["out"])[0] + "_potree_markers.json"
            write_markers(mj, c["markers"], pc["origin"], c["sc"], c["caption"], folder=c["folder"])
            allm += json.load(open(mj))
        self.markers_json = stem + "_potree_markers.json"
        json.dump(allm, open(self.markers_json, "w"), indent=1)
        if not a.no_mark:
            ml = stem + "_MARKED.laz"
            n = write_marked_las(all_las(a), ml, [(c["markers"], c["sc"]) for c in self.spans], pc["origin"])
            self.marked = ml
            self.log(f"    marked LAZ written: {ml} ({n} marker points, all spans)")
        table = {}
        if a.latlon_file:
            try:
                table = latlon.load(a.latlon_file)
                self.log(f"    lat/long: {len(table)} towers read from {os.path.basename(a.latlon_file)}")
                miss = [t["name"] for t in self.towers if not latlon.lookup(table, t["name"])]
                if miss: self.log("FLAG: no lat/long in the sheet for " + ", ".join(miss))
            except Exception as e:
                self.log(f"FLAG: lat/long file not used: {e}")
        for c in self.spans:
            meta = dict(client=a.client, line=a.line, tower_no=c["tower"], span=c["span"], circuit=a.circuit,
                        capacity=a.capacity, latlon=latlon.lookup(table, c["tower"]) or (a.latlon if len(self.spans) == 1 else ""),
                        capture_date=a.capture_date, inspection_date=a.inspection_date)
            build_report(c["out"], meta, c["ttype"], c["res"], c["rem"], a.image_prefix, image_folder=c["folder"])
            c["meta"] = meta; c["pdf"] = os.path.splitext(c["out"])[0] + ".pdf"
            if not a.no_pdf: self.write_pdf(c)
            sc = c["sc"]
            json.dump(dict(file=os.path.basename(a.laz),
                           towers=[dict(name=t["name"], type=t.get("type"), height=t["height"]) for t in self.towers],
                           span=c["span"], tower_type=c["ttype"], tower_type_basis=c["how"], flags=sc.flags,
                           info={k: v for k, v in sc.info.items() if not k.startswith("_")}, results=c["res"]),
                      open(os.path.splitext(c["out"])[0] + "_debug.json", "w"), indent=1, default=float)
            self.log(f"4/4 report written: {c['out']}")

    def run(self):
        self.open(); self.find_towers(); self.measure_spans(); self.write()
        return self


def main(argv=None):
    a = parser().parse_args(argv)
    r = Run(a).run()
    if a.potree:
        from .potree_launch import open_in_potree
        open_in_potree(a.laz, r.markers_json)
    return [c["out"] for c in r.spans]


if __name__ == "__main__":
    main()
