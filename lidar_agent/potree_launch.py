"""Convert the marked LAZ with PotreeConverter (2.x), serve potree_viewer/ locally and open the browser."""
from urllib.parse import quote
import os, sys, shutil, subprocess, threading, webbrowser, functools, socketserver

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIEWER = os.path.join(ROOT, "potree_viewer")


def find_converter():
    cands = [os.environ.get("POTREE_CONVERTER", ""),
             os.path.join(ROOT, "tools", "PotreeConverter", "PotreeConverter.exe"),
             os.path.join(ROOT, "tools", "PotreeConverter.exe"),
             os.path.join(ROOT, "PotreeConverter", "PotreeConverter.exe"),
             shutil.which("PotreeConverter") or ""]
    try:
        from .config import load
        cands.insert(1, load().get("potree_converter", "") or "")
    except Exception:
        pass
    for c in cands:
        if c and os.path.isfile(c): return c
    return None


def _true_bounds(path):
    import numpy as np, laspy
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    with laspy.open(path) as f:
        for ch in f.chunk_iterator(4_000_000):
            for i, d in enumerate((ch.x, ch.y, ch.z)):
                a = np.asarray(d); lo[i] = min(lo[i], a.min()); hi[i] = max(hi[i], a.max())
    return lo, hi


def repaired_copy(src, tmp_dir, log=print):
    """Copy of src whose LAS header bounding box really contains every point (PotreeConverter refuses files whose
    header box is even a fraction of a millimetre too small). The original file is never modified."""
    import struct
    lo, hi = _true_bounds(src)
    pad = 0.001
    os.makedirs(tmp_dir, exist_ok=True)
    dst = os.path.join(tmp_dir, os.path.basename(src))
    log(f"Repairing the bounding box in a temporary copy of {os.path.basename(src)} ...")
    shutil.copyfile(src, dst)
    with open(dst, "r+b") as f:                     # LAS public header: max/min X, Y, Z doubles at byte 179..226
        f.seek(179)
        f.write(struct.pack("<6d", hi[0] + pad, lo[0] - pad, hi[1] + pad, lo[1] - pad, hi[2] + pad, lo[2] - pad))
    return dst


def _convert(conv, files, out, log):
    r = subprocess.run([conv, *files, "-o", out], capture_output=True, text=True)
    text = (r.stdout or "") + (r.stderr or "")
    lp = os.path.join(out, "log.txt")
    if os.path.isfile(lp):
        try: text += open(lp, errors="ignore").read()
        except OSError: pass
    return text


def prepare(laz_for_viewer, markers_json=None, log=print):
    """laz_for_viewer: one file, or a list (this tower + next tower) converted together into one Potree cloud."""
    files = [laz_for_viewer] if isinstance(laz_for_viewer, str) else [f for f in laz_for_viewer if f]
    stems = [os.path.splitext(os.path.basename(f))[0] for f in files]
    if len(stems) <= 2: name = stems[0] + ("" if len(stems) == 1 else "__" + stems[1])
    else:
        import hashlib
        name = f"{stems[0]}__plus{len(stems) - 1}_" + hashlib.md5("|".join(files).encode()).hexdigest()[:6]
    out = os.path.join(VIEWER, "pointclouds", name)
    have = lambda: next((f for f in ("metadata.json", "cloud.js") if os.path.isfile(os.path.join(out, f))), None)
    if not have():
        conv = find_converter()
        if not conv:
            raise RuntimeError("PotreeConverter not found. Download PotreeConverter 2.x for Windows from "
                               "https://github.com/potree/PotreeConverter/releases, unzip it to "
                               "lidar_agent\\tools\\PotreeConverter\\ (so PotreeConverter.exe is inside), or put its path in config.local.json "
                               "(\"potree_converter\") - see config.local.example.json.")
        if os.path.isdir(out): shutil.rmtree(out, ignore_errors=True)         # remove a half-finished earlier attempt
        log(f"Converting {' + '.join(os.path.basename(f) for f in files)} with PotreeConverter (this can take a few minutes) ...")
        text = _convert(conv, files, out, log)
        if not have() and "bounding box" in text.lower():
            log("PotreeConverter: a point lies outside the bounding box written in the LAS header - repairing a copy and retrying.")
            tmp = os.path.join(VIEWER, "_tmp_bbox_fix")
            try:
                fixed = [repaired_copy(f, tmp, log) for f in files]
                shutil.rmtree(out, ignore_errors=True)
                text = _convert(conv, fixed, out, log)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)                            # the copies are only needed for conversion
        log(text[-600:])
        if not have():
            raise RuntimeError("PotreeConverter did not produce metadata.json - see log above.")
    if markers_json is None:      # live mode: the agent streams its measurements into the viewer
        return "tower_viewer.html?cloud=" + quote(f"pointclouds/{name}/{have()}") + "&live=1"
    os.makedirs(os.path.join(VIEWER, "data"), exist_ok=True)
    shutil.copy(markers_json, os.path.join(VIEWER, "data", name + "_markers.json"))
    return ("tower_viewer.html?cloud=" + quote(f"pointclouds/{name}/{have()}") +
            "&markers=" + quote(f"data/{name}_markers.json"))


_server = {}

def serve(page, log=print, port=8765):
    if "port" not in _server:
        from .rangeserver import RangeRequestHandler
        class H(RangeRequestHandler):
            def log_message(self, *a): pass
        Handler = functools.partial(H, directory=VIEWER)
        socketserver.TCPServer.allow_reuse_address = True
        srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        _server["port"] = port
    url = f"http://127.0.0.1:{_server['port']}/{page}"
    log("Opening " + url)
    webbrowser.open(url)
    return url


def open_in_potree(marked_laz, markers_json, log=print):
    return serve(prepare(marked_laz, markers_json, log), log)


if __name__ == "__main__":      # python -m lidar_agent.potree_launch  X_MARKED.laz  X_potree_markers.json
    open_in_potree(sys.argv[1], sys.argv[2])
    input("Viewer running - press Enter to stop.\n")
