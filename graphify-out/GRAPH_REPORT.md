# Graph Report - gcode  (2026-10-31)

## Corpus Check
- 24 files · ~29,062 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 290 nodes · 616 edges · 12 communities (11 shown, 1 thin omitted)
- Extraction: 98% EXTRACTED · 2% INFERRED · 0% AMBIGUOUS · INFERRED: 12 edges (avg confidence: 0.87)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- __main__.py
- measure.py
- detect.py
- app.py
- numpy
- report.py
- test_synthetic.py
- H
- latlon.py
- Line Clearance Agent
- vendor-orbs.mjs
- orb.js

## God Nodes (most connected - your core abstractions)
1. `_measure()` - 20 edges
2. `pipeline()` - 18 edges
3. `Run` - 17 edges
4. `_pair_sag()` - 12 edges
5. `_res()` - 11 edges
6. `_manual()` - 11 edges
7. `_ground_clearance()` - 11 edges
8. `line()` - 11 edges
9. `groups()` - 10 edges
10. `Line Clearance Agent` - 10 edges

## Surprising Connections (you probably didn't know these)
- `run()` --uses--> `Run`  [INFERRED]
  tests/test_synthetic.py → lidar_agent/__main__.py
- `run()` --calls--> `parser()`  [EXTRACTED]
  tests/test_synthetic.py → lidar_agent/__main__.py
- `test_two_files_merged()` --calls--> `all_las()`  [EXTRACTED]
  tests/test_synthetic.py → lidar_agent/__main__.py
- `test_two_files_merged()` --calls--> `parser()`  [EXTRACTED]
  tests/test_synthetic.py → lidar_agent/__main__.py
- `test_two_files_merged()` --calls--> `Run`  [EXTRACTED]
  tests/test_synthetic.py → lidar_agent/__main__.py

## Import Cycles
- None detected.

## Communities (12 total, 1 thin omitted)

### Community 0 - "__main__.py"
Cohesion: 0.08
Nodes (21): log(), pipeline(), on_found(), order_towers(), all_las(), display_order(), load_cfg(), main() (+13 more)

### Community 1 - "measure.py"
Cohesion: 0.11
Nodes (25): _arm_steel(), _assign_near(), _bundle(), _cross_clear(), _crossing_line(), _cut_off(), _ground_clearance(), _horn() (+17 more)

### Community 2 - "detect.py"
Cohesion: 0.07
Nodes (17): classify_tower_type(), detect(), find_towers(), _ground(), _ground_cache(), GroundGrid, _jumper_pts(), line_chain() (+9 more)

### Community 3 - "app.py"
Cohesion: 0.09
Nodes (13): emit(), export(), LogW, main(), load(), _merge(), _convert(), find_converter() (+5 more)

### Community 4 - "numpy"
Cohesion: 0.14
Nodes (18): load(), _thin(), add(), tower(), write(), zw(), add(), tension_tower() (+10 more)

### Community 5 - "report.py"
Cohesion: 0.13
Nodes (10): on_span(), world(), build_pdf(), pic(), png(), build_report(), _d(), _link() (+2 more)

### Community 6 - "test_synthetic.py"
Cohesion: 0.20
Nodes (8): rows(), run(), test_crossings(), test_excel_links_to_screenshots(), test_hand_edit_changes_report(), test_latlon_sheet(), test_span_clearances(), test_tension_rows()

### Community 8 - "latlon.py"
Cohesion: 0.30
Nodes (7): _fmt(), load(), lookup(), _num(), _rows(), tower_key(), test_latlon_parsing()

### Community 9 - "Line Clearance Agent"
Cohesion: 0.18
Nodes (10): Configuration, How the measurements are taken, Install, Line Clearance Agent, Outputs, Project layout, Requirements, Run (+2 more)

### Community 10 - "vendor-orbs.mjs"
Cohesion: 0.29
Nodes (3): dst, root, src

### Community 11 - "orb.js"
Cohesion: 0.60
Nodes (3): hexTint(), orb(), reduced()

## Knowledge Gaps
- **1 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Run` connect `__main__.py` to `app.py`, `test_synthetic.py`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `pipeline()` (e.g. with `.do_POST()` and `emit()`) actually correct?**
  _`pipeline()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Should `__main__.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07922705314009662 - nodes in this community are weakly interconnected._
- **Why does `H` connect `H` to `app.py`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Should `measure.py` be split into smaller, more focused modules?**
  _Cohesion score 0.11265969802555169 - nodes in this community are weakly interconnected._
- **Why does `pipeline()` connect `__main__.py` to `app.py`, `report.py`, `H`?**
  _High betweenness centrality (0.031) - this node is a cross-community bridge._
- **Should `detect.py` be split into smaller, more focused modules?**
  _Cohesion score 0.06923076923076923 - nodes in this community are weakly interconnected._