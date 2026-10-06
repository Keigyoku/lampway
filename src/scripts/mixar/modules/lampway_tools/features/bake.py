# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""bake_maps: bake a high-poly donor into a UV-mapped low-poly target (tangent normal, colour-only albedo, AO) in a niced headless Cycles worker.

The planner here is pure and decides every refusal before anything runs: no UV (unwrap first), overlapping UV islands, non-uniform unapplied scale, source == target, a pair that is not aligned
(bbox centres further apart than 2 % of the diagonal), an unsupported map, an existing file without ``overwrite``. The live scene is never baked in: the pair is written to a temporary
.blend, the worker bakes it, and only the finished maps come back (plus, when ``attach``, a ``<low>_baked`` material on the target and ``lw_baked_from`` on it)."""

import json
import re
from pathlib import Path

import bpy

from .. import canon_io
import numpy as np

from . import common as C
from . import uv_islands as UI

MAPS = ("normal", "albedo", "ao")
OVERLAP_MAX = 0.001
ALIGN_FRACTION = 0.02          # bbox centre distance as a fraction of the donors' diagonal
SCALE_TOL = 1e-3
RAY_PER_CAGE = 2.0             # canon 14 B.3: the ray must reach the HP's greatest depth below the LP (max_ray >= cage + depth); 0.5x missed a sunk HP (golden C10)
# canon 14 B.3, `auto`: cage = the HP's greatest height above the LP, ray = cage + its greatest depth below, each times AUTO_PAD.
# needs_decision: the canon states the two inequalities and no margin; 1.05 is this lane's placeholder, not a ruled number.
AUTO_PAD = 1.05
MEASURE_MAX = 200_000          # HP vertices measured (a stride beyond that: a bound on the loop, not a sample design)


def measure(h_obs, lo):
    """{height_max_m, depth_max_m, median_m, samples}: each HP vertex's signed distance to the nearest LP point along that face's
    normal (+ above the LP, - below). HP vertices, not LP ones: an LP's few vertices cannot see a cap between them (golden C10's LP is
    four corners)."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from .rig import _body_mesh
    V, T = _body_mesh(lo)
    tree = BVHTree.FromPolygons([tuple(v) for v in V], [tuple(int(i) for i in t) for t in T])
    d = []
    for ob in h_obs:
        P, _ = _body_mesh(ob)
        step = max(1, len(P) // MEASURE_MAX)
        for p in P[::step]:
            loc, nrm, _i, _dist = tree.find_nearest(Vector(p))
            if loc is not None:
                d.append(float((Vector(p) - loc).dot(nrm)))
    if not d:
        raise C.FeatureError("the high-poly has no vertex near the low-poly: align them first")
    d = np.array(d)
    return {"height_max_m": round(float(max(d.max(), 0.0)), 9), "depth_max_m": round(float(max(-d.min(), 0.0)), 9),
            "median_m": round(float(np.median(np.abs(d))), 9), "samples": int(len(d))}


def _bbox(obs):
    pts = np.array([ob.matrix_world @ v for ob in obs for v in [__import__("mathutils").Vector(c) for c in ob.bound_box]])
    return pts.min(0), pts.max(0)


def plan(high, low, maps, size, margin_px, cage_extrusion_m, max_ray_m, samples, normal_green, allow_overlap, out_dir, overwrite, root):
    """Validate everything and return the settings the worker gets. Raises FeatureError naming the fix."""
    if not high or not low:
        raise C.FeatureError("name the high-poly donor(s) (source) and the low-poly target")
    high = [high] if isinstance(high, str) else list(high)
    if low in high:
        raise C.FeatureError("a high-to-low bake needs two objects: the source and the target are the same")
    bad = [m for m in maps if m not in MAPS]
    if bad:
        raise C.FeatureError(f"{', '.join(bad)} cannot be baked here; the supported maps are: {', '.join(MAPS)} (curvature, cavity, dust, bevel, position are not Cycles bake types)")
    if normal_green not in ("gl", "dx"):
        raise C.FeatureError(f"normal_green is gl (OpenGL, +Y: Blender) or dx (DirectX, -Y: Unreal), not {normal_green!r}")
    if not 512 <= int(size) <= 8192 and not 32 <= int(size) <= 8192:
        raise C.FeatureError("size is 32..8192 (a power of two)")
    if int(size) & (int(size) - 1):
        raise C.FeatureError("size must be a power of two")
    h_obs = [C.need_object(n) for n in high]
    lo = C.need_object(low)
    for ob in (*h_obs, lo):
        s = np.array(ob.scale)
        if s.max() / max(s.min(), 1e-12) > 1 + SCALE_TOL and not np.allclose(ob.scale, ob.scale[0]):
            raise C.FeatureError(f"{ob.name} has an unapplied non-uniform scale {tuple(round(x, 3) for x in ob.scale)}: apply scale first (ray distances are in world units)")
    row = UI.measure_object(lo, min(int(size), 2048))      # measured at the bake size: at 256 px neighbouring islands of a dense unwrap share texels and read as overlap
    if "error" in row:
        raise C.FeatureError(f"{lo.name} has no UV layer: unwrap first (lampway_uv_unwrap)")
    if row["overlap"] > OVERLAP_MAX and not allow_overlap:
        raise C.FeatureError(f"overlapping UVs on {lo.name} (overlap {row['overlap']}): the second island overwrites the first; fix them or pass allow_overlap=true")
    (hlo, hhi), (llo, lhi) = _bbox(h_obs), _bbox([lo])
    diag = float(np.linalg.norm(hhi - hlo)) or 1.0
    shift = float(np.linalg.norm((hlo + hhi) / 2 - (llo + lhi) / 2))
    if shift > ALIGN_FRACTION * diag:
        raise C.FeatureError(f"the donor and the target are not aligned (their bbox centres are {shift:.3f} apart, more than {ALIGN_FRACTION:.0%} of the diagonal {diag:.3f}): align them first")
    m = measure(h_obs, lo)
    if cage_extrusion_m in (None, "auto"):
        ext = m["height_max_m"] * AUTO_PAD
        ray = (m["height_max_m"] + m["depth_max_m"]) * AUTO_PAD if max_ray_m is None else float(max_ray_m)
    else:
        ext = float(cage_extrusion_m)
        if not 0 <= ext <= 0.2:
            raise C.FeatureError("cage_extrusion_m is 0..0.2 or 'auto'")
        if ext < m["median_m"]:
            raise C.FeatureError(f"the cage {ext:g} m is below the median LP<->HP distance {m['median_m']:g} m: the cage must enclose the high-poly "
                                 f"(canon 14 B.3); use cage_extrusion_m='auto' or at least {m['height_max_m']:g}")
        ray = RAY_PER_CAGE * ext if max_ray_m is None else float(max_ray_m)
    margin = max(2, int(size) // 128) if margin_px is None else int(margin_px)
    if not 0 <= margin <= 64:
        raise C.FeatureError("margin_px is 0..64")
    if not 1 <= int(samples) <= 512:
        raise C.FeatureError("samples is 1..512")
    out = Path(root) / (out_dir or "bake")
    if not str(out.resolve()).startswith(str(Path(root).resolve())):
        raise C.FeatureError(f"{out_dir} is outside the project root")
    existing = [str(out / f"{lo.name}_{m}.png") for m in maps if (out / f"{lo.name}_{m}.png").exists()]
    if existing and not overwrite:
        raise C.FeatureError(f"{Path(existing[0]).name} exists: a bake overwrites images and the undo story is not great; pass overwrite=true")
    return {"high": [o.name for o in h_obs], "low": lo.name, "maps": list(maps), "size": int(size), "margin_px": margin, "cage_extrusion_m": ext, "max_ray_m": ray,
            "samples": int(samples), "normal_green": normal_green, "out_dir": str(out), "measured": m}


def run(source, target, maps, size, margin_px, cage_extrusion_m, max_ray_m, samples, normal_green, allow_overlap, out_dir, overwrite, attach, root, timeout=1800):
    from .. import runner as RUN
    from .. import settings as S
    maps = list(maps or ("normal", "albedo"))
    cfg = plan(source, target, maps, size, margin_px, cage_extrusion_m, max_ray_m, samples, normal_green, allow_overlap, out_dir, overwrite, root)
    out = Path(cfg["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    pair, args, res = out / ".pair.blend", out / ".args.json", out / ".result.json"
    ids = {bpy.data.objects[n] for n in (*cfg["high"], cfg["low"])}
    bpy.data.libraries.write(str(pair), ids, fake_user=False)
    args.write_text(json.dumps(cfg))
    r = RUN.run("bake_maps", [str(pair), str(args), str(res)], S.load(), timeout=timeout)
    for f in (pair, args):
        f.unlink(missing_ok=True)
    if r.rc != 0 or not res.exists():
        raise C.FeatureError("the bake worker failed: " + re.sub(r"\s+", " ", r.stdout)[-400:])
    data = json.loads(res.read_text())
    res.unlink(missing_ok=True)
    hints = [f"{m}: {f:.1%} of the covered texels are black: the cage is too small or the rays miss; raise cage_extrusion_m / max_ray_m" for m, f in data["black_texel_fraction"].items() if f > 0.005]
    body = {"ok": True, "maps": data["files"], "size": cfg["size"], "cage_used": {"extrusion_m": cfg["cage_extrusion_m"], "max_ray_m": cfg["max_ray_m"]}, "margin_px": cfg["margin_px"],
            "checks": {"black_texel_fraction": data["black_texel_fraction"], "covered_texels": data["covered_texels"]}, "colorspace": data["colorspace"], "albedo_passes": data["albedo_passes"],
            "hints": hints, "material": data["material"]}
    if data.get("normal"):
        body["normal"] = data["normal"]
    if attach:
        lo = bpy.data.objects[cfg["low"]]
        mat = bpy.data.materials.new(data["material"]); mat.use_nodes = True
        nt = mat.node_tree
        bsdf = nt.nodes["Principled BSDF"]
        for m, p in data["files"].items():
            node = nt.nodes.new("ShaderNodeTexImage"); node.image = canon_io.load_image(p); node.image.colorspace_settings.name = data["colorspace"][m]
            if m == "albedo":
                nt.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
            elif m == "normal":
                nm = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(node.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
        lo.data.materials.append(mat)
        lo["lw_baked_from"] = ",".join(cfg["high"])
    return body
