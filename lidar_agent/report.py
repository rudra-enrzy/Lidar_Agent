import json
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Side, Font, PatternFill
from .templates import TOWER_TYPE_TEXT, groups


def _d(x):
    if not x: return None
    return x if not isinstance(x, str) else datetime.strptime(x, "%Y-%m-%d")


def marker_list(ttype, results, image_prefix):
    """same numbering as the report's Reference Image column."""
    n, out = 0, []
    for grp, obs in groups(ttype, results):
        for label, key in obs:
            r = results[key]
            if r["conf"] != "na" and r["value"] is not None:
                n += 1
                if r["a"] and r["b"]:
                    out.append(dict(name=f"{image_prefix}-{n}", label=label.strip(), key=key, a=r["a"], b=r["b"], value=r["value"],
                                    vside=1 if (r["a"][1] + r["b"][1]) >= 0 else -1, ttype=ttype))
    return out


def _link(cell, folder, ref):
    """Reference Image cell -> hyperlink to the screenshot "<span folder>/<ref>.png" next to this workbook
    (Potree viewer > Screenshot all saves them there, and puts the same layout in each span's zip)."""
    if not folder: return
    from urllib.parse import quote
    cell.hyperlink = quote(f"{folder}/{ref}.png", safe="/")
    cell.font = Font(color="0563C1", underline="single")


def build_report(path, meta, ttype, results, remarks, image_prefix, image_folder=None):
    wb = Workbook(); ws = wb.active; ws.title = "Sheet1"
    thin = Side(style="thin"); box = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(wrap_text=True, vertical="center", horizontal="center")
    ws.merge_cells("A1:E1"); ws["A1"] = "Powerline Vegetation and Sag Analysis using Drone LiDAR System"
    ws["A1"].font = Font(bold=True, size=14); ws["A1"].alignment = wrap
    head = [("Client", meta.get("client", "Power Grid Corporation of India Limited (PGCIL)")),
            ("Line Details", meta.get("line", "")), ("Tower No", meta.get("tower_no", "")),
            ("Span", meta.get("span", "")), ("No of Circuit", meta.get("circuit", "")),
            ("Powerline Capacity", meta.get("capacity", "765KV")), ("Tower Lat-Long", meta.get("latlon", "")),
            ("Tower Type", TOWER_TYPE_TEXT[ttype]), ("Tower Structure", meta.get("structure", "Lattice Tower ")),
            ("Date of Data Capture", _d(meta.get("capture_date"))), ("Date of Inspection", _d(meta.get("inspection_date")))]
    for i, (k, v) in enumerate(head, start=2):
        ws.merge_cells(start_row=i, start_column=1, end_row=i, end_column=2)
        ws.merge_cells(start_row=i, start_column=3, end_row=i, end_column=5)
        ws.cell(i, 1, k).font = Font(bold=True); ws.cell(i, 3, v)
        if isinstance(v, datetime): ws.cell(i, 3).number_format = "dd-mm-yyyy"; ws.cell(i, 3).alignment = Alignment(horizontal="left")
        for c in range(1, 6): ws.cell(i, c).border = box
    r0 = len(head) + 2
    for c, t in enumerate(["Clearances Type", "Observation Type", "LiDAR  \nMasurement (m) ", "Reference \nImage", "Sugestion \n/Remarks"], 1):
        x = ws.cell(r0, c, t); x.font = Font(bold=True); x.alignment = wrap; x.border = box
        x.fill = PatternFill("solid", fgColor="D9E1F2")
    row, n = r0 + 1, 0
    refs, markers = [], []
    for grp, obs in groups(ttype, results):
        start = row
        for label, key in obs:
            res = results[key]
            ws.cell(row, 2, label)
            if res["conf"] == "na":
                ws.cell(row, 3, "N/A")
            elif res["value"] is not None:
                ws.cell(row, 3, res["value"]); ws.cell(row, 3).number_format = "0.00"
                n += 1; ref = f"{image_prefix}-{n}"; ws.cell(row, 4, ref); refs.append(ref)
                if res["a"] and res["b"]: _link(ws.cell(row, 4), image_folder, ref)
                if res["a"] and res["b"]:
                    markers.append(dict(name=ref, label=label.strip(), key=key, a=res["a"], b=res["b"]))
            ws.cell(row, 5, remarks.get(key, ""))
            for c in range(2, 6): ws.cell(row, c).alignment = wrap; ws.cell(row, c).border = box
            row += 1
        ws.cell(start, 1, grp).alignment = wrap
        if row - 1 > start: ws.merge_cells(start_row=start, start_column=1, end_row=row - 1, end_column=1)
        for r in range(start, row): ws.cell(r, 1).border = box
    ws.cell(row, 1, "Span").alignment = wrap; ws.cell(row, 4, f"{image_prefix}-Span").alignment = wrap
    _link(ws.cell(row, 4), image_folder, f"{image_prefix}-Span")
    for c in range(1, 6): ws.cell(row, c).border = box
    for col, w in zip("ABCDE", (28, 46, 16, 20, 60)): ws.column_dimensions[col].width = w
    s2 = wb.create_sheet("Sheet2")
    for i, ref in enumerate(refs, 1): s2.cell(i, 1, f"Potree screenshot {i}"); s2.cell(i, 2, ref)
    wb.save(path)
    return markers


def write_markers(path, markers, origin, scene, caption="", folder=""):
    """Measurement lines in the file's CRS (tower frame -> world), ready to load into Potree as measurements."""
    out = []
    for m in markers:
        pts = scene.to_world([m["a"], m["b"]]) + origin
        out.append({"name": m["name"], "label": m["label"], "key": m["key"], "value": m.get("value"), "caption": caption,
                    "vside": m.get("vside", 1), "ttype": m.get("ttype", ""),
                    "folder": folder,
                    "span": [round(float(c), 6) for c in scene.R[0]],
                    "type": "Measure", "showDistances": True, "showCoordinates": False,
                    "points": [[round(float(c), 3) for c in p] for p in pts]})
    json.dump(out, open(path, "w"), indent=1)


def write_marked_las(src, dst, groups, origin, step=0.05, chunk=2_000_000):
    """Copy of the original cloud (streamed chunk by chunk, so memory stays low) + every measurement of every span
    drawn as a straight line of points (class 31, red if the format has colour). groups = [(markers, scene), ...].
    Markers from an earlier run are dropped."""
    import numpy as np, laspy
    lines = []
    for markers, scene in groups:
        for m in markers:
            if m.get("key") == "span": continue             # picture-only marker, not a measurement line
            a, b = np.array(m["a"]), np.array(m["b"])
            n = max(int(np.linalg.norm(b - a) / step), 2)
            lines.append(scene.to_world(a + (b - a) * np.linspace(0, 1, n)[:, None]) + origin)
    srcs = [src] if isinstance(src, str) else list(src)
    with laspy.open(srcs[0]) as first:
        hdr = first.header
    with laspy.open(dst, mode="w", header=hdr) as wr:
        for k, path in enumerate(srcs):
            with laspy.open(path) as rd:
                same = (np.allclose(rd.header.scales, hdr.scales) and np.allclose(rd.header.offsets, hdr.offsets)
                        and rd.header.point_format.id == hdr.point_format.id)
                for ch in rd.chunk_iterator(chunk):
                    if "classification" in ch.point_format.dimension_names:
                        ch = ch[np.asarray(ch.classification) != 31]
                    if same:
                        wr.write_points(ch)
                    else:                                    # another tile: different scale / offset / point format
                        rec = laspy.ScaleAwarePointRecord.zeros(len(ch), header=hdr)
                        rec.x, rec.y, rec.z = np.asarray(ch.x), np.asarray(ch.y), np.asarray(ch.z)
                        for dim in ("intensity", "classification", "red", "green", "blue"):
                            if dim in rec.array.dtype.names and dim in ch.point_format.dimension_names:
                                rec[dim] = np.asarray(ch[dim])
                        wr.write_points(rec)
        if lines:
            W = np.vstack(lines)
            rec = laspy.ScaleAwarePointRecord.zeros(len(W), header=hdr)
            rec.x, rec.y, rec.z = W[:, 0], W[:, 1], W[:, 2]
            rec.classification = np.full(len(W), 31, np.uint8)
            if "red" in hdr.point_format.dimension_names:
                rec.red[:] = 65535; rec.green[:] = 0; rec.blue[:] = 0
            wr.write_points(rec)
    return sum(len(x) for x in lines)
