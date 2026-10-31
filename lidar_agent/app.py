"""One-window app: browser UI (Potree inside) served from localhost.
   python -m lidar_agent.app   ->  opens http://127.0.0.1:8765"""
import os, sys, json, threading, webbrowser, traceback, contextlib, io, subprocess
import socketserver, functools
import numpy as np
from urllib.parse import unquote, urlparse
from .__main__ import parser, Run
from . import potree_launch as pl
from .rangeserver import RangeRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
S = dict(state="idle", step=0, log="", error=None, view=None, files=[], folder=None, flags=[])
EVENTS = []
READY = threading.Event()
ASK = threading.Event()        # set when the user has told which tower is leftmost / rightmost
ANSWER = {}
LOCK = threading.Lock()
FILES = {}


class LogW(io.TextIOBase):
    def write(self, t):
        with LOCK: S["log"] += t
        return len(t)


def log(t):
    with LOCK: S["log"] += t + "\n"


def emit(**ev):
    with LOCK: EVENTS.append(ev)


def world(sc, origin, pts):
    return [[round(float(c), 3) for c in p] for p in (sc.to_world(np.array(pts, float)) + origin)]


SWAPN = {"L": "R", "R": "L", "OPGW_L": "OPGW_R", "OPGW_R": "OPGW_L"}


def pipeline(d):
    try:
        files = d["files"]
        argv = [files[0], *[x for f in files[1:] for x in ("--add-las", f)], "--first-tower", d["tower_no"] or "T-1",
                "--line", d["line"], "--circuit", d["circuit"], "--capacity", d["capacity"], "--latlon", d["latlon"], *(["--latlon-file", d["latlon_file"].strip('" ')] if d.get("latlon_file") else []),
                "--image-prefix", d["prefix"], "--tower-type", d["ttype"]]
        if d["capture"]: argv += ["--capture-date", d["capture"]]
        if d["inspect"]: argv += ["--inspection-date", d["inspect"]]
        if d["bearing"]: argv += ["--forward-bearing", d["bearing"]]
        if d.get("full"): argv += ["--voxel", "0"]
        if d.get("reverse"): argv += ["--reverse"]
        if d.get("swap"): argv += ["--swap-lr"]
        if d["outdir"]: argv += ["--out-dir", d["outdir"]]
        a = parser().parse_args(argv)

        # 1. convert the cloud and open it in Potree first, so every step can be watched live
        S["step"] = 1
        try:
            page = pl.prepare(files if len(files) > 1 else files[0], None, log)
            S["view"] = "/v/" + page
            log("Potree viewer opened - waiting for the point cloud to load ...")
            if not READY.wait(120): log("(viewer did not report ready - continuing anyway)")
        except Exception as e:
            log("Live Potree view skipped: " + str(e))
        ev = emit          # the app page's line profile reads these too, with or without the viewer

        def on_found(r):
            """towers found: show them 1..N from left to right and ask which tower No is leftmost / rightmost"""
            o = r.pc["origin"]; gz = r.pc["_ground"][1]
            tw = []
            for t in r.found:
                x, y = (t["xy"] + o[:2]).tolist(); z0 = float(gz(t["xy"][None, :])[0] + o[2])
                tw.append(dict(key=t["key"], title=f"Tower {t['key']}", x=x, y=y, z0=z0, h=t["height"]))
            n = len(r.found)
            ev(type="stage", text=f"{n} tower(s) found - labelled 1 to {n} from LEFT to RIGHT. Enter the leftmost and "
                                  f"rightmost tower No in the panel on the left.", ms=1200)
            ev(type="towers", towers=tw, sideview=True)
            if n == 1:
                return                                       # one tower: the First tower No is its number
            from .__main__ import tower_names
            guess = tower_names(a.first_tower, n)
            ANSWER.clear(); ASK.clear()
            ANSWER["remove"] = []
            S["ask"] = dict(n=n, left=guess[0], right=guess[-1]); S["state"] = "ask"
            log(f"Waiting for you: which tower No is Tower 1 (leftmost) and which is Tower {n} (rightmost)?")
            ASK.wait()
            S["state"] = "running"; S["ask"] = None
            r.a.left_tower, r.a.right_tower = ANSWER["left"], ANSWER["right"]
            r.a.remove_towers = ",".join(str(k) for k in ANSWER.get("remove", []))
            if ANSWER.get("remove"):
                ev(type="towers_removed", keys=ANSWER["remove"])
            log(f"    leftmost = {r.a.left_tower}, rightmost = {r.a.right_tower}")

        def on_towers(r):
            n = len(r.towers)
            ev(type="tower_names", names=[dict(key=t["key"], name=t["name"]) for t in r.towers])
            ev(type="stage", text=f"{n} tower(s): " + ", ".join(t["name"] for t in r.towers)
               + (f" - {n - 1} span report(s) to write" if n > 1 else " - one report (no next tower in the data)"), ms=1500)

        def on_span(r, c):
            sc, o = c["sc"], r.pc["origin"]
            S["step"] = 3
            S["flags"] = S.get("flags", []) + [f"{c['tower']}: {f}" for f in sc.flags]
            ev(type="tower_type", name=c["tower"], ttype=c["ttype"])
            ev(type="stage", text=f"Span {c['span']}: {c['tower']} is a {c['ttype']} tower - marking ...", ms=900)
            sw = SWAPN if d.get("swap") else {}
            for nme, f in sc.wires.items():
                pts = [(u, f["v0"] + f["kv"] * u, f["z0"] + f["kz"] * u) for u in np.linspace(0, 45, 12)]
                ev(type="wire", name=sw.get(nme, nme), points=world(sc, o, pts))
            from .templates import groups
            done = {m["key"]: m for m in c["markers"]}
            for _g, obs in groups(c["ttype"], c["res"]):
                for label, key in obs:
                    rr = c["res"][key]
                    if key in done:
                        m = done[key]
                        ev(type="measure", m=dict(name=m["name"], label=m["label"], value=m["value"], key=m["key"], vside=m.get("vside", 1), ttype=c["ttype"],
                                                   points=world(sc, o, [m["a"], m["b"]]), span=[float(x) for x in sc.R[0]],
                                                   caption=c["caption"], folder=c["folder"], spanlabel=c["span"]))
                    elif rr["conf"] != "na":
                        ev(type="skip", label=label.strip(), folder=c["folder"], spanlabel=c["span"])
            if "span" in done:
                m = done["span"]
                ev(type="measure", m=dict(name=m["name"], label=m["label"], value=m["value"], key="span",
                                           points=world(sc, o, [m["a"], m["b"]]), span=[float(x) for x in sc.R[0]],
                                           caption=c["caption"], folder=c["folder"], spanlabel=c["span"]))
            ev(type="span", span=c["span"], tower=c["tower"], ttype=c["ttype"])     # this span is fully marked

        # 2.-4. the agent: open -> find/count/classify towers -> span by span -> one Excel per span
        S["step"] = 2
        ev(type="stage", text="Agent: reading the LAZ and looking for towers ...", ms=300)
        run = Run(a, log=log, on_towers=on_towers, on_span=on_span, on_found=on_found)
        with contextlib.redirect_stdout(LogW()):
            run.open(); run.find_towers(); run.measure_spans()
        RUN["run"] = run
        S["step"] = 4; S["edits"] = 0; S["dirty"] = True
        S["span_folders"] = [c["folder"] for c in run.spans]
        S["folder"] = os.path.dirname(run.spans[0]["out"])
        ev(type="done")                      # marking finished: the viewer lets you move lines, then you export
        log("All spans marked. Check the lines in Potree (drag an end point to move it), then press Export.")
        S["state"] = "review"
    except Exception:
        with LOCK: S["log"] += "\nERROR:\n" + traceback.format_exc()
        S["error"] = "Failed - see the log."; S["state"] = "error"


RUN = {}


def export():
    """Excel per span + marked LAZ + markers, from the current (possibly hand-moved) measurements."""
    run = RUN["run"]
    try:
        S["state"] = "exporting"
        with contextlib.redirect_stdout(LogW()):
            run.write()
        S["files"] = []
        for c in run.spans:
            FILES[os.path.basename(c["out"])] = c["out"]
            S["files"].append(dict(label=f"Excel report {c['span']}", url="/files/" + os.path.basename(c["out"])))
            if c.get("pdf") and os.path.isfile(c["pdf"]):
                FILES[os.path.basename(c["pdf"])] = c["pdf"]
                S["files"].append(dict(label=f"PDF report {c['span']}", url="/files/" + os.path.basename(c["pdf"])))
        for label, path in (("Marked LAZ (all spans)", getattr(run, "marked", None)), ("Potree markers (JSON)", run.markers_json)):
            if path and os.path.isfile(path):
                FILES[os.path.basename(path)] = path
                S["files"].append(dict(label=label, url="/files/" + os.path.basename(path)))
        S["dirty"] = False; S["exported"] = S.get("exported", 0) + 1
        log(f"Exported {len(run.spans)} report(s)" + (f" with {run.edited()} line(s) moved by hand." if run.edited() else "."))
        S["state"] = "done"
    except Exception:
        with LOCK: S["log"] += "\nEXPORT ERROR:\n" + traceback.format_exc()
        S["export_error"] = "Export failed - see the agent log. Your moved lines are kept; try Export again."; S["state"] = "review"


class H(RangeRequestHandler):
    # Windows can map .js to text/plain in the registry - module scripts then refuse to load
    extensions_map = {**RangeRequestHandler.extensions_map, ".js": "text/javascript", ".mjs": "text/javascript",
                      ".wasm": "application/wasm", ".json": "application/json"}

    def log_message(self, *a): pass

    def translate_path(self, path):
        p = unquote(urlparse(path).path)
        if p.startswith("/v/"): return os.path.join(pl.VIEWER, *p[3:].split("/"))
        if p.startswith("/files/"): return FILES.get(p[7:], "")
        if p == "/orb.js": return os.path.join(HERE, "orb.js")
        if p == "/logo.png": return os.path.join(HERE, "assets", "logo.png")
        if p.startswith("/vendor/"):                     # front-end packages copied from npm (thinking-orbs)
            f = os.path.normpath(os.path.join(HERE, "vendor", *p[8:].split("/")))
            return f if f.startswith(os.path.join(HERE, "vendor")) else ""
        return os.path.join(HERE, "app.html")

    def _json(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/events"):
            since = int((urlparse(self.path).query or "since=0").split("=")[-1] or 0)
            with LOCK: return self._json(dict(events=EVENTS[since:], next=len(EVENTS)))
        if self.path.startswith("/api/status"):
            with LOCK: return self._json(S)
        if self.path.startswith("/files/") and unquote(self.path[7:]) in FILES:
            self.path = "/files/" + unquote(self.path[7:])
        return super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store"); super().end_headers()

    def _upload(self):
        """a file dragged onto the page: streamed to <app>/data/uploads/<name> (a browser never reveals the real path of a
        dropped file, and a LAS can be several GB - so it is copied in 4 MB pieces, never held in memory)."""
        from urllib.parse import parse_qs
        name = os.path.basename((parse_qs(urlparse(self.path).query).get("name") or [""])[0])
        n = int(self.headers.get("Content-Length") or 0)
        if not name.lower().endswith((".las", ".laz")): return self._json(dict(error="Only .las and .laz files."), 400)
        d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "uploads")
        os.makedirs(d, exist_ok=True); dst = os.path.join(d, name); tmp = dst + ".part"
        left = n
        try:
            with open(tmp, "wb") as f:
                while left > 0:
                    b = self.rfile.read(min(4 << 20, left))
                    if not b: break
                    f.write(b); left -= len(b)
            if left: raise IOError("upload interrupted")
            os.replace(tmp, dst)
        except Exception as e:
            try: os.remove(tmp)
            except OSError: pass
            return self._json(dict(error=f"Upload failed: {e}"), 500)
        return self._json(dict(ok=True, path=dst, name=name, size=n))

    def do_POST(self):
        if self.path.startswith("/api/upload?"): return self._upload()
        n = int(self.headers.get("Content-Length") or 0); body = self.rfile.read(n) if n else b""
        if self.path == "/api/run":
            if S["state"] in ("running", "ask", "exporting"): return self._json(dict(error="Already running."))
            d = json.loads(body)
            files = [str(f).strip('" ') for f in (d.get("files") or [d.get("laz", "")]) if str(f).strip('" ')]
            if not files: return self._json(dict(error="Add at least one LAS or LAZ file."))
            for f in files:
                if not os.path.isfile(f): return self._json(dict(error="File not found: " + f))
            if len({os.path.normcase(os.path.abspath(f)) for f in files}) != len(files):
                return self._json(dict(error="The same file is listed twice."))
            d["files"] = files; d["laz"] = files[0]
            S.update(state="running", step=1, log="", error=None, view=None, files=[], folder=None, flags=[], ask=None,
                     edits=0, dirty=False, exported=0, span_folders=[], export_error=None)
            RUN.clear()
            EVENTS.clear(); READY.clear()
            threading.Thread(target=pipeline, args=(d,), daemon=True).start()
            return self._json(dict(ok=True))
        if self.path.startswith("/api/browse"):
            try:
                import tkinter as tk
                from tkinter import filedialog
                r = tk.Tk(); r.withdraw(); r.attributes("-topmost", True)
                if "kind=sheet" in self.path:
                    p = filedialog.askopenfilename(filetypes=[("Excel or CSV", "*.xlsx *.csv"), ("All", "*.*")]); r.destroy()
                    return self._json(dict(path=p))
                ps = filedialog.askopenfilenames(filetypes=[("Point cloud", "*.laz *.las"), ("All", "*.*")]); r.destroy()
                return self._json(dict(paths=list(ps), path=(ps[0] if ps else "")))
            except Exception:
                return self._json(dict(error="File dialog not available - paste the full path instead."))
        if self.path == "/api/numbers":
            d = json.loads(body or b"{}")
            if not (d.get("left") and d.get("right")): return self._json(dict(error="Enter both tower numbers."))
            n = (S.get("ask") or {}).get("n", 2)
            rem = sorted({int(k) for k in d.get("remove") or [] if str(k).isdigit() and 1 <= int(k) <= n})
            if len(rem) >= n: return self._json(dict(error="Keep at least one tower."))
            from .__main__ import names_from_ends
            names, warn = names_from_ends(d["left"], d["right"], n - len(rem))
            if names is None: return self._json(dict(error=warn))
            ANSWER.update(left=d["left"].strip(), right=d["right"].strip(), remove=rem); ASK.set()
            return self._json(dict(ok=True, names=names, warning=warn))
        if self.path.startswith("/api/shot?"):            # one screenshot (PNG body) -> <reports>/<span folder>/<name>.png
            from urllib.parse import parse_qs
            q = parse_qs(urlparse(self.path).query)
            folder, name = (q.get("folder") or [""])[0], os.path.basename((q.get("name") or [""])[0])
            if not S.get("folder") or folder not in (S.get("span_folders") or []) or not name.lower().endswith(".png"):
                return self._json(dict(error="No finished run to save screenshots into."), 409)
            d = os.path.join(S["folder"], folder); os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "wb") as f: f.write(body)
            return self._json(dict(ok=True))
        if self.path == "/api/shots_zip":                # all screenshots of one span -> one zip, ready to download
            import zipfile
            folder = json.loads(body or b"{}").get("folder", "")
            if not S.get("folder") or folder not in (S.get("span_folders") or []):
                return self._json(dict(error="Unknown span."), 404)
            d = os.path.join(S["folder"], folder)
            pngs = sorted(f for f in os.listdir(d) if f.lower().endswith(".png")) if os.path.isdir(d) else []
            if not pngs: return self._json(dict(error="No screenshots for this span yet."), 404)
            zp = os.path.join(S["folder"], f"{folder}_screenshots.zip")
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:     # PNGs are already compressed
                for f in pngs: z.write(os.path.join(d, f), f"{folder}/{f}")
            FILES[os.path.basename(zp)] = zp
            run = RUN.get("run")                          # the span's PDF again, now with its pictures inside
            for c in (run.spans if run else []):
                if c["folder"] == folder and not run.a.no_pdf: run.write_pdf(c)
            from urllib.parse import quote
            return self._json(dict(ok=True, url="/files/" + quote(os.path.basename(zp)), name=os.path.basename(zp),
                                   saved=d, count=len(pngs)))
        if self.path == "/api/edit":                     # a measurement moved in Potree (or moved back by undo)
            d = json.loads(body or b"{}")
            if not RUN.get("run") or S["state"] not in ("review", "done"):
                return self._json(dict(error="Lines can be moved once the agent has finished marking."), 409)
            try:
                with LOCK: v = RUN["run"].edit(d["folder"], d["key"], d["points"])
            except Exception as e:
                return self._json(dict(error=str(e)), 400)
            S["edits"] = RUN["run"].edited(); S["dirty"] = True
            if S["state"] == "done": S["state"] = "review"
            return self._json(dict(ok=True, value=v, edits=S["edits"]))
        if self.path == "/api/export":
            if not RUN.get("run") or S["state"] not in ("review", "done"):
                return self._json(dict(error="Nothing to export yet."), 409)
            S["state"] = "exporting"; S["export_error"] = None
            threading.Thread(target=export, daemon=True).start()
            return self._json(dict(ok=True))
        if self.path == "/api/ready":
            READY.set(); return self._json(dict(ok=True))
        if self.path == "/api/open" and S["folder"]:
            f = S["folder"]
            (os.startfile(f) if sys.platform.startswith("win") else subprocess.run(["open" if sys.platform == "darwin" else "xdg-open", f]))
            return self._json(dict(ok=True))
        self._json(dict(error="?"), 404)


def main(port=8765, open_browser=True):
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), functools.partial(H, directory=HERE))
    url = f"http://127.0.0.1:{port}/"
    print("LiDAR Tower Clearance Agent running at", url, "(Ctrl+C to stop)")
    if open_browser: webbrowser.open(url)
    try: srv.serve_forever()
    except KeyboardInterrupt: pass


if __name__ == "__main__":
    main()
