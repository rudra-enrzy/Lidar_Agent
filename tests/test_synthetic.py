"""End-to-end regression test on a synthetic line with KNOWN answers (no client data needed).

tests/synth4.py builds 4 towers in one LAZ: T-2 is a tension tower with jumper loops and arcing horns, a grey road
crosses span 2 (a tension span: roads are a T-108 tension-report row) and a distribution line crosses span 3. The agent must find 4 towers, write 3 span reports and
reproduce the clearances built into the cloud.

    pytest -q tests/test_synthetic.py
"""
import json, os, subprocess, sys
import openpyxl
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    d = tmp_path_factory.mktemp("synth")
    laz = str(d / "four_x.laz")
    subprocess.run([sys.executable, os.path.join(HERE, "synth4.py"), laz], check=True, capture_output=True)
    from lidar_agent.__main__ import parser, Run
    import openpyxl as ox
    wb = ox.Workbook(); ws = wb.active
    ws.append(["Sr", "Tower No", "Latitude", "Longitude"])
    for n, (la, lo) in enumerate([(26.61, 78.29), (26.62, 78.30), (26.63, 78.31), (26.64, 78.32)], 1):
        ws.append([n, f"T{n}", la, lo])
    wb.save(str(d / "ll.xlsx"))
    a = parser().parse_args([laz, "--left-tower", "T-4", "--right-tower", "T-1", "--voxel", "0.1", "--no-mark",
                             "--out-dir", str(d / "reports"), "--latlon-file", str(d / "ll.xlsx")])
    r = Run(a, log=lambda *x: None).run()
    return r, json.load(open(laz + ".truth.json"))


def rows(path):
    ws = openpyxl.load_workbook(path).active
    return {str(r[1]).strip(): r[2] for r in ws.iter_rows(values_only=True) if r[1]}


def test_towers_and_spans(run):
    r, _ = run
    assert [t["name"] for t in r.towers] == ["T-1", "T-2", "T-3", "T-4"]
    assert [c["span"] for c in r.spans] == ["T-1 - T-2", "T-2 - T-3", "T-3 - T-4"]
    assert [c["ttype"] for c in r.spans] == ["suspension", "tension", "suspension"]
    for c in r.spans:
        assert os.path.isfile(c["out"])


def test_span_clearances(run):
    r, truth = run
    for i, c in enumerate(r.spans):
        t = truth[f"span{i + 1}"] if i == 0 else None
        res = c["res"]
        assert res["phase_LM"]["value"] == pytest.approx(16.6, abs=0.15)
        assert res["phase_RM"]["value"] == pytest.approx(16.6, abs=0.15)
        if t:
            assert res["gnd_L"]["value"] == pytest.approx(t["gnd"], abs=0.3)


def test_tension_rows(run):
    r, _ = run
    res = r.spans[1]["res"]
    assert res["t_L_arm"]["value"] == pytest.approx(8.0, abs=0.2)
    assert res["t_M_upper"]["value"] == pytest.approx(5.66, abs=0.2)
    assert res["t_M_lower"]["value"] == pytest.approx(6.95, abs=0.2)
    assert res["t_L_horn"]["value"] == pytest.approx(1.92, abs=0.3)


def test_crossings(run):
    r, _ = run
    assert r.spans[1]["res"]["cross_L"]["value"] == pytest.approx(35.0, abs=0.3)      # road under span 2
    assert r.spans[0]["res"]["cross_L"]["conf"] == "na"                                 # nothing crosses span 1
    assert r.spans[2]["res"]["cross_L"]["value"] == pytest.approx(13.2, abs=0.3)      # crossing line under span 3


def test_excel_links_to_screenshots(run):
    r, _ = run
    ws = openpyxl.load_workbook(r.spans[0]["out"]).active
    links = [c.hyperlink.target for row in ws.iter_rows(min_col=4, max_col=4) for c in row if c.hyperlink]
    assert links and all(l.startswith("T-1%20-%20T-2/") for l in links)


def test_hand_edit_changes_report(run):
    r, _ = run
    c = r.spans[0]; m = next(m for m in c["markers"] if m["key"] == "gnd_L")
    v0 = m["value"]; pts = c["sc"].to_world([m["a"], m["b"]]) + r.pc["origin"]
    moved = pts.copy(); moved[1, 2] += 0.5
    v = r.edit(c["folder"], "gnd_L", moved.tolist())
    assert c["res"]["gnd_L"]["conf"] == "manual" and v == pytest.approx(v0 - 0.5, abs=0.02)
    r.edit(c["folder"], "gnd_L", pts.tolist())                      # moving it back restores the agent's value
    assert c["res"]["gnd_L"]["conf"] != "manual" and r.edited() == 0


def test_latlon_sheet(run):
    """each span report carries the lat/long of ITS tower, read from the sheet"""
    r, _ = run
    for c, want in zip(r.spans, ["26.61, 78.29", "26.62, 78.3", "26.63, 78.31"]):
        ws = openpyxl.load_workbook(c["out"]).active
        cells = [str(x) for row in ws.iter_rows(values_only=True) for x in row if x]
        assert want in cells, (c["tower"], want)


def test_latlon_parsing(tmp_path):
    from lidar_agent import latlon
    p = tmp_path / "a.csv"
    p.write_text("Tower,Lat-Long\nT-90,\"26.6137484, 78.2946954\"\nTower 91,26.7 78.3\n")
    t = latlon.load(str(p))
    assert latlon.lookup(t, "T-91") == "26.7, 78.3" and latlon.lookup(t, "T-90") == "26.6137484, 78.2946954"
    p.write_text("T-5,26.1,78.2\n")                           # no header
    assert latlon.lookup(latlon.load(str(p)), "T5") == "26.1, 78.2"


def test_pdf_report(run, tmp_path):
    """a PDF per span next to the Excel; pictures are included once screenshots exist"""
    r, _ = run
    c = r.spans[0]
    assert os.path.getsize(c["pdf"]) > 2000
    from PIL import Image
    d = os.path.join(os.path.dirname(c["out"]), c["folder"]); os.makedirs(d, exist_ok=True)
    Image.new("RGB", (800, 500), (30, 60, 90)).save(os.path.join(d, "GWA_CKT1-1.png"))
    before = os.path.getsize(c["pdf"])
    assert r.write_pdf(c) and os.path.getsize(c["pdf"]) > before


def test_two_files_merged(tmp_path):
    """one line split into two tiles (different files) gives the same towers, and the marked LAZ holds both tiles"""
    import laspy, numpy as np
    laz = str(tmp_path / "whole.laz")
    subprocess.run([sys.executable, os.path.join(HERE, "synth4.py"), laz], check=True, capture_output=True)
    las = laspy.read(laz)
    x = np.asarray(las.x); cut = np.median(x)
    parts = []
    for i, m in enumerate((x <= cut, x > cut)):
        hdr = laspy.LasHeader(point_format=las.header.point_format, version=las.header.version)
        hdr.scales = las.header.scales; hdr.offsets = las.header.offsets + (i * 0.0)
        o = laspy.LasData(hdr); o.points = las.points[m]
        f = str(tmp_path / f"tile{i}.laz"); o.write(f); parts.append(f)
    from lidar_agent.__main__ import parser, Run, all_las
    a = parser().parse_args([parts[0], "--add-las", parts[1], "--left-tower", "T-4", "--right-tower", "T-1", "--voxel", "0.1",
                             "--out-dir", str(tmp_path / "rep")])
    assert all_las(a) == parts
    r = Run(a, log=lambda *x: None).run()
    assert [t["name"] for t in r.towers] == ["T-1", "T-2", "T-3", "T-4"] and len(r.spans) == 3
    n = sum(laspy.open(f).header.point_count for f in parts)
    assert laspy.open(r.marked).header.point_count > n          # both tiles + the marker lines
