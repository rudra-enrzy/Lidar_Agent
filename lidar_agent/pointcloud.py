import numpy as np, laspy


def _thin(xyz, cls, voxel, base, rgb=None):
    if not voxel: return xyz, cls, rgb
    k = np.floor((xyz - base) / voxel).astype(np.int64)
    key = (k[:, 0] * 2_000_003 + k[:, 1]) * 200_003 + k[:, 2]
    _, idx = np.unique(key, return_index=True)
    return xyz[idx], (cls[idx] if cls is not None else None), (rgb[idx] if rgb is not None else None)


def load(path, voxel=0.08, chunk=4_000_000, log=print):
    """Stream one or more .las/.laz files (e.g. this tower + the next tower) in chunks, drop our own marker points
    (class 31), thin on a voxel grid, shift to a local origin taken from the FIRST file."""
    paths = [path] if isinstance(path, str) else [p for p in path if p]
    xs, cs, rs, n_raw = [], [], [], 0
    origin = primary = None
    for path in paths:
      with laspy.open(path) as f:
        h = f.header
        if origin is None:
            origin = np.array([np.floor((h.mins[0] + h.maxs[0]) / 2), np.floor((h.mins[1] + h.maxs[1]) / 2), np.floor(h.mins[2])])
            primary = np.array([(h.mins[0] + h.maxs[0]) / 2, (h.mins[1] + h.maxs[1]) / 2]) - origin[:2]
        has_cls = "classification" in set(h.point_format.dimension_names)
        has_rgb = "red" in set(h.point_format.dimension_names)
        for ch in f.chunk_iterator(chunk):
            xyz = np.column_stack([np.asarray(ch.x), np.asarray(ch.y), np.asarray(ch.z)]) - origin
            cls = np.asarray(ch.classification).astype(np.int16) if has_cls else None
            rgb = None
            if has_rgb:            # colour (8 bit) - used to find road surfaces under the span
                rgb = np.column_stack([np.asarray(ch.red), np.asarray(ch.green), np.asarray(ch.blue)])
                rgb = (rgb >> 8 if rgb.max() > 255 else rgb).astype(np.uint8)
            n_raw += len(xyz)
            if cls is not None:
                keep = cls != 31
                xyz, cls = xyz[keep], cls[keep]
                if rgb is not None: rgb = rgb[keep]
            xyz, cls, rgb = _thin(xyz, cls, voxel, 0.0, rgb)
            xs.append(xyz); cs.append(cls); rs.append(rgb)
            log(f"    read {n_raw:,} points")
    xyz = np.vstack(xs); cls = np.concatenate(cs) if cs[0] is not None else None
    rgb = np.vstack(rs) if all(r is not None for r in rs) else None
    xyz, cls, rgb = _thin(xyz, cls, voxel, 0.0, rgb)
    return {"xyz": xyz, "cls": cls, "rgb": rgb, "origin": origin, "n_raw": n_raw, "n": len(xyz), "primary_xy": primary,
            "files": len(paths)}
