# Line Clearance Agent

Turns a drone LiDAR point cloud (LAS/LAZ) of a transmission line into PGCIL-style
**Sag and Vegetation Clearance** reports — one Excel per span — and shows every measurement live in
[Potree](https://github.com/potree/potree) while it works.

Open one or more LAS/LAZ files (drop them on the page, Browse, or paste a path; several files are merged into one cloud) with any number of towers. The agent:

1. converts the cloud and opens it in Potree;
2. finds and counts the towers, numbers them left to right and asks you for the tower numbers at both ends
   (you can leave out a false detection with the × on its label);
3. classifies each tower (suspension / tension) and marks every *Clearances Type / Observation Type* span by span,
   the way the reference reports are measured;
4. stops for review: drag any line in Potree to correct it (Ctrl+Z / Ctrl+Y undo and redo);
5. on **Export**, writes one Excel per span, a marked LAZ, the Potree markers and one zip of screenshots per span.
   Each report's *Reference Image* cells link to its screenshots.

## Requirements

- Windows 10/11 (the app also runs on Linux/macOS for development)
- Python 3.10+
- [PotreeConverter 2.x](https://github.com/potree/PotreeConverter/releases) for the live 3-D view
  (reports are still written without it)
- Chrome or Edge

## Install

```bat
git clone <this repository>
cd <repository>
pip install -r requirements.txt
copy config.local.example.json config.local.json
```

Edit `config.local.json` and set `potree_converter` to your `PotreeConverter.exe`
(or unzip PotreeConverter into `tools\PotreeConverter\`, which is found automatically).

No Node.js is needed to run the app. The loading indicator (the `thinking-orbs` npm package) is already copied
into `lidar_agent/vendor`; run `npm install` only to update it.

## Run

**Desktop app (recommended):** double-click `run_desktop.bat` (or `python run_desktop.py`). It opens the app in its own
window with no browser. Install the window component once: `pip install -r requirements-desktop.txt` (pywebview; it
uses Edge WebView2, which is already part of Windows 10/11). Files dropped on the window are used where they are, with
no copy. Without pywebview, `run_desktop.bat` falls back to your browser.

**One .exe for other PCs:** run `build_exe.bat` on Windows. It writes `dist\LineClearanceAgent\LineClearanceAgent.exe`
(a folder of about 250 MB; zip it and send it, no Python needed on the other PC). Put `PotreeConverter.exe` in
`tools\PotreeConverter\` next to the exe, or set `potree_converter` in `config.local.json` there. Unzip it to a normal,
writable folder (not *Program Files*): the app writes the converted point clouds beside itself.

**Browser version:**

Double-click `run_app.bat`, or:

```bat
python -m lidar_agent.app
```

A page opens at `http://127.0.0.1:8765`. Choose the LAS/LAZ, fill in the report header and press **Run agent**.

Command line (no viewer, writes the reports straight away):

```bat
python -m lidar_agent "G:\LAS\Gwalior Bina C2 T-1 to T-4.las" --left-tower T-1 --right-tower T-4 ^
    --line "765KV-GWALIOR-AGRA-ACL-C2" --circuit "Circuit 2" --image-prefix GWA_CKT2 --voxel 0 --swap-lr
```

Tower positions: give an Excel (.xlsx) or CSV with one row per tower (`Tower | Latitude | Longitude`, or one
`Lat-Long` column) in the app's *More options*, or with `--latlon-file towers.xlsx`. Each span report's *Tower Lat-Long*
cell then holds the position of its own tower; tower names match loosely (`T-90`, `T90`, `90`).

`python -m lidar_agent --help` lists every option (`--no-pdf`, `--add-las other.laz` (repeat for more files), `--remove-towers 2`, `--tower-type`, `--no-mark`, …).

## Outputs

Written next to the LAS/LAZ in `<file name> reports\` (or `--out-dir`):

| File | What it is |
|---|---|
| `T-1 - T-2_Sag and Vegetation Clearance Report.xlsx` | one report per span, in the client layout |
| `T-1 - T-2_Sag and Vegetation Clearance Report.pdf` | the same report as a PDF; after *Screenshot all* it also carries every picture, and the Reference Image cells jump to them |
| `T-1 - T-2\GWA_CKT1-1.png …` | screenshots; the report's Reference Image cells link here |
| `T-1 - T-2_screenshots.zip` | the same screenshots, one zip per span |
| `<file>_MARKED.laz` | the cloud plus every measurement as a red line (class 31) |
| `<file>_potree_markers.json` | the measurement lines in file coordinates |

## How the measurements are taken

- **Suspension towers** follow the reference folders from the earlier reports; **tension towers** follow the T-108
  reference pictures (jumper drop straight up/down, jumper to leg horizontal, arcing horn to jumper, road and
  power-line crossings).
- Phase-to-phase, OPGW-to-conductor and ground clearances are taken at **mid-span**, between the nearest points of
  the wires; ground clearance from the lowest sub-conductor.
- With two OPGWs, the left OPGW pairs with the Left conductor and the right one with the Right conductor.
- The tower type is found automatically from the point cloud, using the usual tower-type rules: a **jumper loop** hanging
  in a U across the tower, or **no conductor passing the tower on a line that turns more than 15°** (angle, deviation and
  terminal towers), means *tension*; a conductor that **passes the tower unbroken** on a hanging I/V string means
  *suspension*. A type you choose by hand is kept, and a flag is raised if the cloud disagrees.
- Each value carries a confidence. Low-confidence rows (angle towers, arcing horns, road crossings) say
  "verify in Potree" in the Remarks column; rows moved by hand say "Adjusted by hand in Potree".

## Configuration

`config.json` (committed) holds shared settings: minimum clearances per measurement (fill in from the spec you work
to; `null` = not checked) and detection options. `config.local.json` (not committed) overrides it on one machine.

## Project layout

```
lidar_agent/           Python package
  desktop.py           native window (pywebview) around the same local server
  __main__.py          command line + the run (open -> towers -> spans -> export); several input files are merged
  app.py, app.html     browser app (local server, live events, drag and drop, review / export)
  pointcloud.py        streams one or more LAS/LAZ files, thinning, colour
  detect.py            ground, towers, line chaining, wires, tower type (jumper loop / through-conductor / line angle)
  measure.py           every Observation Type, crossings, arcing horns
  validate.py          remarks and checks on the values
  report.py            Excel, markers, marked LAZ
  pdf_report.py        PDF copy of each report, with the screenshots
  latlon.py            tower lat/long from an Excel or CSV sheet
  templates.py         report rows (exact client wording)
  config.py            config.json + config.local.json
  potree_launch.py, rangeserver.py   PotreeConverter, viewer server with Range requests
  assets/logo.png      logo (app header, tab icon, PDF)
  vendor/thinking-orbs loading indicator (copied from npm)
run_desktop.py, run_desktop.bat, build_exe.bat   desktop app and its Windows build script
potree_viewer/         Potree 1.8 build + tower_viewer.html (live marking, screenshots, line editing)
tests/                 synthetic lines with known answers + pytest end-to-end tests
scripts/               npm postinstall helper
graphify-out/          code map built with graphify (see below)
```

## Code map (graphify)

`graphify-out/` holds a map of this code made with [graphify](https://pypi.org/project/graphifyy/):

| File | What it is |
|---|---|
| `graph.html` | interactive graph: search, click a node, filter by community (loads its viewer library from the internet) |
| `GRAPH_REPORT.md` | the most connected functions, surprising links between files, communities |
| `graph.json` | the graph itself, for tools and scripts |

The most connected pieces are `_measure()` (every measurement row), `pipeline()` (the app's run) and the `Run` class
(the main flow). There are no circular imports. The map covers this repository's own code, not the bundled Potree.

Rebuild it after code changes (code is read directly, no API key or model needed):

```bat
pip install graphifyy
graphify update .
```

The PyPI package is `graphifyy` (two y's); the unrelated `graphify` on npm is a different tool. Ask questions of the
graph from the command line with `graphify explain "Run"` or `graphify path "pipeline" "_measure"`.

## Tests

```bat
pip install -r requirements-dev.txt
python -m pytest -q
```

`tests/test_synthetic.py` builds a 4-tower line (one tension tower, a road and a crossing line) with known
clearances and checks the agent against them, and also covers the lat/long sheet, the PDF report and a line split
across two files. No client data is used; please don't commit LAS/LAZ files or reports
(they are in `.gitignore`).

## Third-party software

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Potree is BSD-2-Clause, thinking-orbs is MIT.
