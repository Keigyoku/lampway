# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""procedural_library (specs/mixar_docs/procedural_library.md, asset_library/asset_seed_procedural.md): a library of procedural node-group materials, built from a few parametric TEMPLATES and a preset table
("build the tool, not the output"). Each material is a script that builds one ShaderNodeTree group named LWP_<id> with a single Shader output and bounded, defaulted inputs (Tint, Roughness Scale, Wear, Scale,
Bump Strength, Seed, Mask). Everything is in Object space, so no UVs are needed, and `Mask` lets a curvature or AO mask drive edge wear. The scripts are registered in the Client's own MaterialRegistry, so its
agent tools, library popup and layer stack read them unchanged, and each script passes the same AST gate matgen applies. Statistics (base colour, metallic, roughness) come from real Cycles bakes of a PROBE
variant of the group that adds those three outputs; the registered group has only the Shader output.

The library is the contract's proposed 55 (40 metals, 5 leathers, 6 cloths, 4 embroideries) from 12 templates; the data is procedural_presets.py. The first 12 were
an auditor's pick the captain never fixed (asset_seed_procedural.md section 13): the full 55 is the coordinator's order, and the looks remain the captain's call.
The stat bakes are EEVEE emission readouts: never Cycles beside the captain's live work."""

import hashlib
import json
import math
import time
from pathlib import Path

import bpy

from .. import canon_io

from . import common as C
from .procedural_emit import INPUTS, LIBRARY_VERSION, _lin, emit, manifest, manifest_hash, script_sha  # noqa: F401  (re-exported: the tool's surface)
from .procedural_presets import CATEGORIES, PRESETS, TEMPLATES  # noqa: F401  (TEMPLATES is read by the tests and the Vault seeder)
BOUNDS = {"Roughness Scale": (1.0, 0.2, 2.0), "Wear": None, "Scale": None, "Bump Strength": None, "Seed": (0.0, 0.0, 1000.0), "Mask": (1.0, 0.0, 1.0)}


# ------------------------------------------------------------------------------------------------ registry
def _registry():
    from mixar.modules.paint.procedural_materials import material_registry as MR
    return MR


def _ok_script(script: str):
    from mixar.modules.space_mixie_chat.core.sandbox_validator import validate_script_ast
    err = validate_script_ast(script)
    if err:
        raise C.FeatureError(f"a library script was blocked by the sandbox gate: {err}")


def seed(root, upgrade=False) -> dict:
    MR = _registry()
    path = Path(root) / "procedural" / "library.json"
    cur = manifest()
    if path.exists() and not upgrade:
        old = json.loads(path.read_text())
        if old.get("library_version") == cur["library_version"] and old != cur:
            raise C.FeatureError("library manifest changed: bump library_version or run seed with upgrade=true")
    registered = unchanged = 0
    for pid, pr in PRESETS.items():
        script = emit(pid)
        _ok_script(script)
        existing = MR.get_material(pid)
        sha = hashlib.sha256(script.encode()).hexdigest()
        if existing is not None and hashlib.sha256((existing.script or "").encode()).hexdigest() == sha:
            unchanged += 1
            continue
        MR.register_material(MR.ProceduralMaterial(material_id=pid, name=pr["name"], category=pr["category"], script=script, node_group_name="LWP_" + pid, description=pr["description"]))
        registered += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cur, indent=1))
    return {"ok": True, "registered": registered, "unchanged": unchanged, "count": len(PRESETS), "library_version": LIBRARY_VERSION, "manifest_sha256": manifest_hash()}


def _summary(pid: str) -> dict:
    pr = PRESETS[pid]
    q = pr["params"]
    inputs = [{"name": "Tint", "default": list(_lin(q["color"])) + [1.0], "min": None, "max": None}, {"name": "Roughness Scale", "default": 1.0, "min": 0.2, "max": 2.0},
              {"name": "Wear", "default": q["wear"], "min": 0.0, "max": 1.0}, {"name": "Scale", "default": q["scale"], "min": 0.1, "max": 10.0},
              {"name": "Bump Strength", "default": q["bump"], "min": 0.0, "max": 1.0}, {"name": "Seed", "default": 0.0, "min": 0.0, "max": 1000.0}, {"name": "Mask", "default": 1.0, "min": 0.0, "max": 1.0}]
    return {"material_id": pid, "name": pr["name"], "category": pr["category"], "description": pr["description"], "template": pr["template"], "inputs": inputs}


def _need(pid: str):
    if pid not in PRESETS:
        raise C.FeatureError(f"no material {pid!r}; categories: {list(CATEGORIES)}, {len(PRESETS)} materials")
    return pid


def _tokens(text):
    import re
    return [t for t in re.split(r"[^a-z0-9]+", str(text).lower()) if t]


def _score(pid, q):
    pr = PRESETS[pid]
    toks = _tokens(q)
    idw, namew, descw = set(_tokens(pid)), set(_tokens(pr["name"])), set(_tokens(pr["description"] + " " + pr["category"]))
    return sum(3 * (t in idw) + 2 * (t in namew) + (t in descw) for t in toks)


# ------------------------------------------------------------------------------------------------ build and verify
def _build(pid: str, probe=False):
    name = ("LWPP_" if probe else "LWP_") + pid
    old = bpy.data.node_groups.get(name)
    if old is not None:
        bpy.data.node_groups.remove(old)
    script = emit(pid, probe)
    _ok_script(script)
    t0 = time.perf_counter()
    exec(compile(script, f"<material:{pid}>", "exec"), {"__name__": "__material__"})  # noqa: S102  (our own template output, already through the sandbox gate)
    ms = (time.perf_counter() - t0) * 1000.0
    return bpy.data.node_groups[name], ms


def _group_facts(g) -> dict:
    ins, shader_outs = [], 0
    for it in g.interface.items_tree:
        if getattr(it, "item_type", "") != "SOCKET":
            continue
        if it.in_out == "OUTPUT" and it.socket_type == "NodeSocketShader":
            shader_outs += 1
        if it.in_out == "INPUT":
            dv = it.default_value
            ins.append({"name": it.name, "default": list(dv) if hasattr(dv, "__len__") else float(dv), "min": getattr(it, "min_value", None), "max": getattr(it, "max_value", None)})
    return {"inputs": ins, "shader_outputs": shader_outs}


_BAKES: dict = {}


def _render_probe(pid: str, params: dict, size: int, out_png=None, tmp_dir=None):
    """Three 1-sample EEVEE renders of a top-down plane whose emission is the probe's Base Color, Metallic and Roughness outputs."""
    key = (pid, json.dumps(params, sort_keys=True), size)
    if key in _BAKES and out_png is None:
        return _BAKES[key]
    g, _ms = _build(pid, probe=True)
    import tempfile
    own = None if tmp_dir else tempfile.TemporaryDirectory(prefix="lw_probe_")      # a probe's EXRs are deleted one by one; its folder goes with the probe
    scratch = Path(tmp_dir) if tmp_dir else Path(own.name)
    scratch.mkdir(parents=True, exist_ok=True)
    sc = bpy.data.scenes.new("lw_probe")
    mat = bpy.data.materials.new("lw_probe_mat")
    me = bpy.data.meshes.new("lw_probe_plane")
    me.from_pydata([(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("lw_probe_plane", me)
    cam = bpy.data.objects.new("lw_probe_cam", bpy.data.cameras.new("lw_probe_cam"))
    try:
        sc.collection.objects.link(ob)
        sc.collection.objects.link(cam)
        cam.data.type, cam.data.ortho_scale = "ORTHO", 1.0
        cam.location = (0, 0, 2)
        sc.camera = cam
        me.materials.append(mat)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        grp = nt.nodes.new("ShaderNodeGroup")
        grp.node_tree = g
        for k, v in (params or {}).items():
            if k in grp.inputs:
                grp.inputs[k].default_value = v
        em = nt.nodes.new("ShaderNodeEmission")
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        sc.render.engine = "BLENDER_EEVEE"                        # an emission readout: EEVEE renders it exactly; never Cycles beside the user's live work
        sc.eevee.taa_render_samples = 1
        sc.render.resolution_x = sc.render.resolution_y = size
        sc.render.resolution_percentage = 100
        sc.view_settings.view_transform = "Standard"
        sc.world = bpy.data.worlds.new("lw_probe_world")
        sc.world.color = (0, 0, 0)
        sc.render.image_settings.file_format = "OPEN_EXR"
        sc.render.image_settings.color_depth = "32"
        sc.render.film_transparent = False
        res = {}
        import numpy as np
        for name in ("Base Color", "Metallic", "Roughness"):
            for l in list(nt.links):
                if l.to_node is em:
                    nt.links.remove(l)
            nt.links.new(grp.outputs[name], em.inputs["Color"])
            exr = scratch / f"probe_{name.replace(' ', '_')}.exr"
            sc.render.filepath = str(exr)
            bpy.ops.render.render(write_still=True, scene=sc.name)
            img = canon_io.load_image(str(exr))
            w, h = img.size
            res[name] = np.array(img.pixels[:], dtype=np.float32).reshape(h, w, 4)[:, :, :3]
            bpy.data.images.remove(img)
            exr.unlink()
    finally:
        bpy.data.objects.remove(ob)
        bpy.data.objects.remove(cam)
        bpy.data.scenes.remove(sc)
        bpy.data.materials.remove(mat)
        bpy.data.meshes.remove(me)
        g2 = bpy.data.node_groups.get("LWPP_" + pid)
        if g2 is not None:
            bpy.data.node_groups.remove(g2)
        if own is not None:
            own.cleanup()
    base = res["Base Color"]
    srgb = np.clip(base, 0, 1) ** (1 / 2.2)
    m = srgb.mean(axis=(0, 1))
    mx, mn = float(m.max()), float(m.min())
    r, gg, b = (float(x) for x in m)
    if mx == mn:
        hue = 0.0
    elif mx == r:
        hue = (60 * ((gg - b) / (mx - mn))) % 360
    elif mx == gg:
        hue = 60 * ((b - r) / (mx - mn)) + 120
    else:
        hue = 60 * ((r - gg) / (mx - mn)) + 240
    stats = {"base_color_mean": [round(x, 4) for x in m.tolist()], "hue_deg": round(float(hue), 2), "chroma": round(mx - mn, 4), "value_mean": round(float(srgb.mean()), 4),
             "metallic_mean": round(float(res["Metallic"][:, :, 0].mean()), 4), "roughness_mean": round(float(res["Roughness"][:, :, 0].mean()), 4), "base_variance": round(float(srgb.var()), 5),
             "_png": _png_bytes(np.clip(base, 0, 1) ** (1 / 2.2))}
    if out_png is None:
        _BAKES[key] = stats
    return stats


def _png_bytes(arr) -> bytes:
    import io

    from PIL import Image
    b = io.BytesIO()
    Image.fromarray((arr * 255 + 0.5).astype("uint8")).save(b, "PNG")
    return b.getvalue()


def _fingerprint(m: dict) -> list:
    return list(m["base_color_mean"]) + [m["roughness_mean"], m["metallic_mean"], m["base_variance"] * 10]


def fingerprint_distance(a: str, b: str, res: dict) -> float:
    by = {m["material_id"]: m for m in res["materials"]}
    return float(sum(abs(x - y) for x, y in zip(_fingerprint(by[a]), _fingerprint(by[b]))))


def verify(root, bake=False, size=64) -> dict:
    out, broken = [], []
    for pid in PRESETS:
        try:
            g, ms = _build(pid)
            f = _group_facts(g)
            row = {**_summary(pid), "inputs": f["inputs"], "shader_outputs": f["shader_outputs"], "build_ms": round(ms, 2), "generator": f"{PRESETS[pid]['template']}@{script_sha(pid)[:16]}"}
            if bake:
                st = _render_probe(pid, {}, size)
                row.update({k: v for k, v in st.items() if not k.startswith("_")})
            out.append(row)
        except Exception as exc:  # noqa: BLE001  (a template that fails to build is listed broken and not offered)
            broken.append({"material_id": pid, "error": f"template {PRESETS[pid]['template']!r} failed to build: {type(exc).__name__}: {exc}"})
    res = {"ok": True, "materials": out, "broken": broken, "collisions": [], "min_pairwise_l1": None}
    if bake and len(out) > 1:
        dists = []
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                d = sum(abs(x - y) for x, y in zip(_fingerprint(out[i]), _fingerprint(out[j])))
                dists.append(d)
                if d < 0.02:
                    res["collisions"].append([out[i]["material_id"], out[j]["material_id"], round(d, 4)])
        res["min_pairwise_l1"] = round(min(dists), 4)
    return res


def bake(root, material_id, params=None, size=64, compare_to=None) -> dict:
    _need(material_id)
    d = Path(root) / "procedural" / "bakes"
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / f".{material_id}.tmp.png"
    st = _render_probe(material_id, params or {}, size, out_png=str(tmp), tmp_dir=str(d))
    data = st["_png"]
    sha = hashlib.sha256(data).hexdigest()
    path = d / f"{material_id}_{sha[:12]}.png"
    path.write_bytes(data)
    if tmp.exists():
        tmp.unlink()
    res = {"ok": True, "material_id": material_id, "path": str(path), "sha256": sha, **{k: v for k, v in st.items() if not k.startswith("_")}}
    if compare_to:
        import numpy as np
        from PIL import Image
        a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
        b = np.asarray(Image.open(compare_to).convert("RGB"), dtype=np.float32) / 255.0
        res["mean_abs_diff"] = round(float(np.abs(a - b).mean()), 5)
    return res


def procedural_library(root, action="list", category=None, query=None, material_id=None, object=None, layer_name=None, params=None, size=64, bake_stats=False, compare_to=None, upgrade=False):  # noqa: A002
    if action == "seed":
        return seed(root, upgrade)
    if action == "verify":
        seed(root, upgrade)
        return verify(root, bake_stats, size)
    if action == "bake":
        seed(root, upgrade)
        return bake(root, material_id, params, size, compare_to)
    if action in ("list", "find"):
        seed(root, upgrade)
        if category is not None and category not in CATEGORIES:
            raise C.FeatureError(f"unknown category {category!r}; categories: {list(CATEGORIES)}")
        ids = [p for p in PRESETS if category in (None, PRESETS[p]["category"])]
        if action == "find":
            if material_id:
                ids = [_need(material_id)]
            elif query:
                ids = sorted((p for p in ids if _score(p, query) > 0), key=lambda p: (-_score(p, query), p))
            else:
                raise C.FeatureError("find needs a query or a material_id")
        return {"ok": True, "materials": [_summary(p) for p in ids], "total": len(PRESETS)}
    if action == "add_to_layer":
        if not object:
            raise C.FeatureError("name the object to add the layer to (object)")
        _need(material_id or "")
        seed(root, upgrade)
        from mixar.modules.paint.core import agent_tools as AT
        r = AT.add_procedural_material_layer(material_id=material_id, object_names=[object], layer_name=layer_name or "")
        if not r.get("success"):
            raise C.FeatureError(f"the layer could not be added: {r.get('error') or r.get('errors') or 'unknown error'}; initialise a layer paint project first (lampway_layered_material action=init)")
        return {"ok": True, "added": {"object": object, "material_id": material_id, "layer": layer_name or PRESETS[material_id]["name"], "detail": r.get("applied")}}
    raise C.FeatureError("action is list | find | add_to_layer | seed | verify | bake")
