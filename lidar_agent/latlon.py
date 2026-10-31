"""Tower latitude / longitude from an Excel (.xlsx) or CSV sheet: one row per tower.

Accepted layouts (header row optional, found automatically in the first 15 rows):
  Tower | Latitude | Longitude          separate columns
  Tower | Lat-Long                       one column such as "26.6137484, 78.2946954"
Tower names are matched loosely: "T-90", "T90", "t 90", "Tower 90" and 90 all mean the same tower ("90A" keeps its letter).
"""
import csv, os, re


def tower_key(v):
    m = re.search(r"(\d+)\s*([A-Za-z]?)\b", str(v or ""))
    return f"{int(m.group(1))}{m.group(2).upper()}" if m else None


def _num(v):
    try: return float(str(v).strip().replace("°", ""))
    except ValueError: return None


def _rows(path):
    if path.lower().endswith((".csv", ".txt")):
        with open(path, newline="", encoding="utf-8-sig") as f:
            return [r for r in csv.reader(f)]
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _fmt(lat, lon): return f"{lat:.7f}".rstrip("0").rstrip(".") + ", " + f"{lon:.7f}".rstrip("0").rstrip(".")


def load(path):
    """-> {tower_key: "lat, long"}; raises ValueError with a readable message when nothing usable is found."""
    if not os.path.isfile(path): raise ValueError(f"Lat/long file not found: {path}")
    rows = [r for r in _rows(path) if any(c not in (None, "") for c in r)]
    ti = la = lo = both = None
    start = 0
    for i, r in enumerate(rows[:15]):                       # header row
        low = [str(c or "").strip().lower() for c in r]
        t = next((j for j, c in enumerate(low) if re.search(r"tower|loc|^no\.?$|^t\.?no", c)), None)
        a = next((j for j, c in enumerate(low) if c.startswith("lat") and "long" not in c.replace("latitude", "")), None)
        o = next((j for j, c in enumerate(low) if re.match(r"(lon|lng)", c)), None)
        b = next((j for j, c in enumerate(low) if re.search(r"lat.*(lon|lng)", c)), None)
        if t is not None and ((a is not None and o is not None) or b is not None):
            ti, la, lo, both, start = t, a, o, b, i + 1
            break
    out = {}
    for r in rows[start:]:
        r = list(r) + [None] * 4
        if ti is None:                                      # no header: tower, lat, long
            key, lat, lon = tower_key(r[0]), _num(r[1]), _num(r[2])
        elif both is not None:
            key = tower_key(r[ti]); nums = re.findall(r"-?\d+(?:\.\d+)?", str(r[both] or ""))
            lat, lon = (float(nums[0]), float(nums[1])) if len(nums) >= 2 else (None, None)
        else:
            key, lat, lon = tower_key(r[ti]), _num(r[la]), _num(r[lo])
        if key and lat is not None and lon is not None and abs(lat) <= 90 and abs(lon) <= 180:
            out[key] = _fmt(lat, lon)
    if not out: raise ValueError("No tower / latitude / longitude rows found in " + os.path.basename(path))
    return out


def lookup(table, name):
    return (table or {}).get(tower_key(name), "")
