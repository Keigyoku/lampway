# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE Look tonemapper cube, read as DATA (the captain's ruling, 2026-10-06; docs/ue-look.md).

The cube is generated on the UE side, by a generator that lives outside Lampway: nothing of the tonemapper maths is in this
repository. The profile names the cube (``tonemap_cube``) and its JSON sidecar (``tonemap_cube_meta``, schema
lampway.ue-cube-meta/1: engine, tonemapper settings, generator, cube {file, sha256, size, domain_min, domain_max, order},
shaper {base, lin_side_slope, lin_side_offset, log_side_slope, log_side_offset}). ``validate`` answers valid / missing /
mismatch; Lampway keeps the cube's PATH and HASH only, never a copy (not in the repository, the Vault or a receipt).

Checks, in order: both paths named and present; the sidecar's schema; the cube's sha256 equals the sidecar's; the cube's grid
(LUT_3D_SIZE, the sidecar's size and the profile's r.LUT.Size agree, and exactly size^3 finite rows); its domain equals the
sidecar's; the sidecar's engine version equals the profile's; the sidecar's tonemapper settings equal the profile's."""

import hashlib
import json
import math
from pathlib import Path

META_SCHEMA = "lampway.ue-cube-meta/1"
FIX = "generate the cube on the UE side, then point UE Look at it (tonemap_cube and tonemap_cube_meta; docs/ue-look.md)"
TONEMAP_KEYS = ("method", "film", "blue_correction", "expand_gamut", "tone_curve_amount", "white_temp", "white_tint", "grading")
SHAPER_KEYS = ("base", "lin_side_slope", "lin_side_offset", "log_side_slope", "log_side_offset")


class CubeError(ValueError):
    pass


def _sha(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _read(path):
    """(size, domain_min, domain_max, rows, all_finite) of a .cube file; nothing of its data is kept."""
    size, dmin, dmax, rows, finite = None, [0.0, 0.0, 0.0], [1.0, 1.0, 1.0], 0, True
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            t = line.split()
            if not t or t[0].startswith("#") or t[0] == "TITLE":
                continue
            if t[0] == "LUT_3D_SIZE":
                size = int(t[1])
            elif t[0] == "DOMAIN_MIN":
                dmin = [float(x) for x in t[1:4]]
            elif t[0] == "DOMAIN_MAX":
                dmax = [float(x) for x in t[1:4]]
            elif t[0] == "LUT_1D_SIZE":
                raise CubeError("a 1D cube: UE Look needs a 3D cube")
            else:
                rows += 1
                if finite and (len(t) != 3 or not all(math.isfinite(float(x)) for x in t)):
                    finite = False
    return size, dmin, dmax, rows, finite


def _close(a, b):
    return len(a) == len(b) and all(abs(float(x) - float(y)) <= 1e-9 for x, y in zip(a, b))


def _answer(state, why, **facts):
    return {"state": state, "why": why, "fix": "" if state == "valid" else FIX, **facts}


def validate(profile, cube=None, meta=None) -> dict:
    """valid | missing | mismatch, with why and fix; for a valid cube its path, sha256, engine version, generator, grid, domain and
    shaper (the shaper is what the OCIO view needs). ``cube``/``meta`` override the profile's paths (the panel's pickers)."""
    c = cube or profile.get("tonemap_cube")
    m = meta or profile.get("tonemap_cube_meta")
    if not c or not m:
        return _answer("missing", "the profile names no " + ("tonemap_cube" if not c else "tonemap_cube_meta"))
    c, m = Path(c), Path(m)
    if not c.is_file():
        return _answer("missing", f"the cube {c} is not there", cube=str(c), meta=str(m))
    if not m.is_file():
        return _answer("missing", f"the sidecar {m} is not there", cube=str(c), meta=str(m))
    facts = {"cube": str(c), "meta": str(m)}
    try:
        md = json.loads(m.read_text(encoding="utf-8"))
    except ValueError as exc:
        return _answer("mismatch", f"the sidecar {m.name} is not JSON: {exc}", **facts)
    if not isinstance(md, dict) or md.get("schema") != META_SCHEMA:
        return _answer("mismatch", f"the sidecar {m.name} is not {META_SCHEMA}", **facts)
    try:
        mc, shaper, engine = md["cube"], {k: float(md["shaper"][k]) for k in SHAPER_KEYS}, md["engine"]
        want_sha, want_size = mc["sha256"], int(mc["size"])
    except (KeyError, TypeError, ValueError) as exc:
        return _answer("mismatch", f"the sidecar {m.name} lacks {exc}: it must carry engine, tonemapper, generator, cube and shaper", **facts)
    sha = _sha(c)
    if sha != want_sha:
        return _answer("mismatch", f"the cube's sha256 {sha[:12]} is not the sidecar's {str(want_sha)[:12]}: the cube changed or the sidecar is another cube's", **facts)
    try:
        size, dmin, dmax, rows, finite = _read(c)
    except (CubeError, ValueError, IndexError) as exc:
        return _answer("mismatch", f"the cube does not parse: {exc}", **facts)
    grid = profile["project"]["cvars"]["r.LUT.Size"]
    if size != want_size or size != grid:
        return _answer("mismatch", f"the cube's grid is {size}^3, the sidecar says {want_size}, the profile's r.LUT.Size is {grid}", **facts)
    if rows != size ** 3 or not finite:
        return _answer("mismatch", f"the cube has {rows} rows ({'not all finite' if not finite else f'{size ** 3} expected'})", **facts)
    if not (_close(dmin, mc.get("domain_min", [0, 0, 0])) and _close(dmax, mc.get("domain_max", [1, 1, 1]))):
        return _answer("mismatch", f"the cube's domain {dmin}..{dmax} is not the sidecar's", **facts)
    if engine.get("version") != profile["engine"]["version"]:
        return _answer("mismatch", f"the sidecar's engine version {engine.get('version')} is not the profile's {profile['engine']['version']}", **facts)
    tm = {k: profile["tonemap"][k] for k in TONEMAP_KEYS}
    if md.get("tonemapper") != tm:
        diff = sorted(k for k in TONEMAP_KEYS if (md.get("tonemapper") or {}).get(k) != tm[k])
        return _answer("mismatch", f"the sidecar's tonemapper settings differ from the profile's ({', '.join(diff)})", **facts)
    return _answer("valid", "", sha256=sha, engine_version=engine["version"], generator=md.get("generator"), size=size,
                   domain=[dmin, dmax], shaper=shaper, **facts)


def require(profile, cube=None, meta=None) -> dict:
    v = validate(profile, cube, meta)
    if v["state"] != "valid":
        raise CubeError(f"UE Look cube {v['state']}: {v['why']}: {FIX}")
    return v


def receipt(v) -> dict:
    """What a receipt records about the cube: its path, hash, engine and generator, never its data."""
    return {"state": v["state"], "path": v.get("cube"), "sha256": v.get("sha256"), "engine_version": v.get("engine_version"),
            "generator": v.get("generator")}
