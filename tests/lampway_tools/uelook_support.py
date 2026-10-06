# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test helpers for the UE Look cube: a SYNTHETIC cube written by the test (never a UE-derived one), its sidecar, and a profile
that points at both. The shaper below is invented for the tests (a 16-stop log2 window), not UE's; the cube is either the
identity (output = the shaper-encoded coordinate) or a known simple curve (the sRGB encoding of the shaper-decoded value)."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = ROOT / "src/scripts/mixar/modules/lampway_tools/ue/profiles/engine_defaults.json"
SHAPER = {"base": 2.0, "lin_side_slope": 1.0, "lin_side_offset": 0.002, "log_side_slope": 1 / 16.0, "log_side_offset": 0.55}
TONEMAP_KEYS = ("method", "film", "blue_correction", "expand_gamut", "tone_curve_amount", "white_temp", "white_tint", "grading")


def lin(enc):
    """The linear value a cube coordinate stands for (the shaper's inverse)."""
    return 2.0 ** ((enc - SHAPER["log_side_offset"]) / SHAPER["log_side_slope"]) - SHAPER["lin_side_offset"]


def enc(x):
    import math
    return min(1.0, max(0.0, math.log2(max(x, 0.0) + SHAPER["lin_side_offset"]) * SHAPER["log_side_slope"] + SHAPER["log_side_offset"]))


def srgb(x):
    x = max(0.0, min(1.0, x))
    return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055


def through_cube(x, curve="srgb", size=32):
    """What the view shows for a grey x: the shaper's coordinate, then the cube sampled linearly between its grid points
    (trilinear on the grey diagonal), exactly as OCIO samples it."""
    e = enc(x) * (size - 1)
    i = min(int(e), size - 2)
    f = e - i
    g = [(k / (size - 1)) if curve == "identity" else srgb(lin(k / (size - 1))) for k in (i, i + 1)]
    return g[0] + (g[1] - g[0]) * f


def write_cube(path, size=32, curve="srgb", domain=((0, 0, 0), (1, 1, 1)), rows=None):
    g = [(i / (size - 1)) if curve == "identity" else srgb(lin(i / (size - 1))) for i in range(size)]
    out = ['TITLE "synthetic test cube"', f"LUT_3D_SIZE {size}", "DOMAIN_MIN " + " ".join(map(str, domain[0])), "DOMAIN_MAX " + " ".join(map(str, domain[1]))]
    for b in range(size):
        for gg in range(size):
            for r in range(size):
                out.append(f"{g[r]:.7f} {g[gg]:.7f} {g[b]:.7f}")
    if rows is not None:
        out = out[:4 + rows]
    Path(path).write_text("\n".join(out) + "\n")
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_meta(path, cube, profile=None, **over):
    p = profile or json.loads(DEFAULT_PROFILE.read_text())
    meta = {"schema": "lampway.ue-cube-meta/1", "engine": dict(p["engine"]),
            "tonemapper": {k: p["tonemap"][k] for k in TONEMAP_KEYS},
            "generator": {"name": "synthetic test generator", "version": "0.0-test"},
            "cube": {"file": Path(cube).name, "sha256": hashlib.sha256(Path(cube).read_bytes()).hexdigest(), "size": 32,
                     "domain_min": [0, 0, 0], "domain_max": [1, 1, 1], "order": "red_fastest"},
            "shaper": dict(SHAPER)}
    for k, v in over.items():
        node = meta
        keys = k.split("__")
        for kk in keys[:-1]:
            node = node[kk]
        node[keys[-1]] = v
    Path(path).write_text(json.dumps(meta))
    return meta


def profile_with_cube(tmp_path, name="profile.json", curve="srgb", source="live-dump", edits=None):
    """A profile file pointing at a fresh synthetic cube and its sidecar under tmp_path/cube_<name>/."""
    d = Path(tmp_path) / f"cube_{Path(name).stem}"
    d.mkdir(parents=True, exist_ok=True)
    cube, meta = d / "test.cube", d / "test.cube.json"
    write_cube(cube, curve=curve)
    p = json.loads(DEFAULT_PROFILE.read_text())
    p["source"] = source
    for k, v in (edits or {}).items():
        node = p
        keys = k.split("__")
        for kk in keys[:-1]:
            node = node[kk]
        node[keys[-1]] = v
    write_meta(meta, cube, p)
    p["tonemap_cube"], p["tonemap_cube_meta"] = str(cube), str(meta)
    q = Path(tmp_path) / name
    q.write_text(json.dumps(p))
    return q
