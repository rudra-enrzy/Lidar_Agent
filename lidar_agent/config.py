"""Settings: config.json (shared, committed) overlaid with config.local.json (this machine only, not committed)."""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _merge(a, b):
    for k, v in b.items():
        a[k] = _merge(dict(a.get(k) or {}), v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
    return a


def load(path=None):
    path = path or os.path.join(ROOT, "config.json")
    cfg = {}
    for p in (path, os.path.join(os.path.dirname(os.path.abspath(path)), "config.local.json")):
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                _merge(cfg, json.load(f))
    return cfg
