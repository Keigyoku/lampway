# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""procedural_library (specs/mixar_docs/procedural_library.md, asset_library/asset_seed_procedural.md): a library of procedural node-group materials, built from a few parametric TEMPLATES and a preset table
("build the tool, not the output"). Each material is a script that builds one ShaderNodeTree group named LWP_<id> with a single Shader output and bounded, defaulted inputs (Tint, Roughness Scale, Wear, Scale,
Bump Strength, Seed, Mask). Everything is in Object space, so no UVs are needed, and `Mask` lets a curvature or AO mask drive edge wear. The scripts are registered in the Client's own MaterialRegistry, so its
agent tools, library popup and layer stack read them unchanged, and each script passes the same AST gate matgen applies. Statistics (base colour, metallic, roughness) come from real Cycles bakes of a PROBE
variant of the group that adds those three outputs; the registered group has only the Shader output.

THE FIRST 12 ARE THE AUDITOR'S RECOMMENDATION, WHICH IS NOT WRITTEN IN ANY SPEC: asset_seed_procedural.md says "the captain fixes the first 12", and BUILD_ORDER names "the auditor's recommended 12, as written
in asset_seed_procedural.md", which that file does not contain. This set is chosen from its proposed 55 to cover the captain's armour looks (bronze, gold, brass, steel, iron; charcoal and oiled leather; black
linen and the heavy crimson cloak). Embroidery and the horsehair plume (templates `embroidery`, `cloth_fold`) are the next ones: flagged for the captain, not blocking."""

import hashlib
import json
import math
import time
from pathlib import Path

import bpy

from .. import canon_io

from . import common as C

LIBRARY_VERSION = "1"
CATEGORIES = ("metal", "leather", "cloth")
INPUTS = [("Tint", "NodeSocketColor"), ("Roughness Scale", "NodeSocketFloat"), ("Wear", "NodeSocketFloat"), ("Scale", "NodeSocketFloat"), ("Bump Strength", "NodeSocketFloat"),
          ("Seed", "NodeSocketFloat"), ("Mask", "NodeSocketFloat")]
BOUNDS = {"Roughness Scale": (1.0, 0.2, 2.0), "Wear": None, "Scale": None, "Bump Strength": None, "Seed": (0.0, 0.0, 1000.0), "Mask": (1.0, 0.0, 1.0)}


def _lin(c):
    return tuple(round(x ** 2.2, 5) for x in c)


def _p(**kw):
    return kw


# id -> {template, category, name, description, params}.  Colours are sRGB looks (converted to linear when the script is written).
PRESETS = {
    "bronze_polished": {"template": "metal", "category": "metal", "name": "Bronze, polished", "description": "Warm polished bronze with a faint micro-grain.",
                        "params": _p(color=(0.80, 0.50, 0.20), rough=0.22, micro=0.35, hammer=0.0, brushed=False, patina=0.0, scratch=0.0, wear=0.15, scale=3.0, bump=0.15)},
    "bronze_hammered": {"template": "metal", "category": "metal", "name": "Bronze, hammered", "description": "Hand-hammered bronze: overlapping dimples over a warm base.",
                        "params": _p(color=(0.74, 0.44, 0.18), rough=0.35, micro=0.3, hammer=1.0, brushed=False, patina=0.0, scratch=0.0, wear=0.25, scale=3.0, bump=0.6)},
    "bronze_patina_light": {"template": "metal", "category": "metal", "name": "Bronze, light patina", "description": "Bronze with a verdigris bloom in the recesses.",
                            "params": _p(color=(0.72, 0.45, 0.22), rough=0.4, micro=0.3, hammer=0.4, brushed=False, patina=0.55, scratch=0.0, wear=0.3, scale=3.0, bump=0.4)},
    "gold_polished": {"template": "metal", "category": "metal", "name": "Gold, polished", "description": "Bright polished gold.",
                      "params": _p(color=(1.0, 0.76, 0.34), rough=0.16, micro=0.2, hammer=0.0, brushed=False, patina=0.0, scratch=0.0, wear=0.1, scale=3.0, bump=0.1)},
    "gold_aged": {"template": "metal", "category": "metal", "name": "Gold, aged", "description": "Gold dulled by handling: darker, rougher in the wear.",
                  "params": _p(color=(0.85, 0.64, 0.28), rough=0.3, micro=0.35, hammer=0.0, brushed=False, patina=0.0, scratch=0.5, wear=0.55, scale=3.0, bump=0.25)},
    "brass_antique": {"template": "metal", "category": "metal", "name": "Brass, antique", "description": "Yellow-green antique brass, brushed and tarnished.",
                      "params": _p(color=(0.71, 0.60, 0.25), rough=0.38, micro=0.3, hammer=0.0, brushed=True, patina=0.12, scratch=0.2, wear=0.45, scale=3.0, bump=0.25)},
    "steel_battle_worn": {"template": "metal", "category": "metal", "name": "Steel, battle-worn", "description": "Grey steel scratched and dulled by use.",
                          "params": _p(color=(0.62, 0.63, 0.65), rough=0.35, micro=0.35, hammer=0.0, brushed=False, patina=0.0, scratch=1.0, wear=0.6, scale=3.0, bump=0.3)},
    "iron_forged_dark": {"template": "metal", "category": "metal", "name": "Iron, forged dark", "description": "Dark forged iron with a scaled surface.",
                         "params": _p(color=(0.30, 0.30, 0.31), rough=0.55, micro=0.5, hammer=0.5, brushed=False, patina=0.0, scratch=0.2, wear=0.4, scale=3.0, bump=0.5)},
    "leather_charcoal_glove": {"template": "leather", "category": "leather", "name": "Leather, charcoal glove", "description": "Fine-grained charcoal glove leather.",
                               "params": _p(color=(0.10, 0.10, 0.11), rough=0.55, grain=0.5, wear=0.25, scale=3.0, bump=0.35)},
    "leather_oiled_brown": {"template": "leather", "category": "leather", "name": "Leather, oiled brown", "description": "Oiled brown leather with a soft sheen.",
                            "params": _p(color=(0.30, 0.17, 0.08), rough=0.5, grain=0.6, wear=0.3, scale=3.0, bump=0.4)},
    "cloth_linen_black": {"template": "cloth", "category": "cloth", "name": "Linen, black", "description": "Black plain-weave linen.",
                          "params": _p(color=(0.07, 0.07, 0.08), rough=0.92, weave=0.5, wear=0.2, scale=3.0, bump=0.35)},
    "cloth_cloak_crimson_heavy": {"template": "cloth", "category": "cloth", "name": "Cloak cloth, heavy crimson", "description": "Heavy crimson wool cloak cloth.",
                                  "params": _p(color=(0.50, 0.05, 0.07), rough=0.95, weave=0.8, wear=0.3, scale=2.2, bump=0.5)},
}


# ------------------------------------------------------------------------------------------------ the script emitter
class _S:
    """Writes the node-group script: plain statements only (no setattr, no dunders, no ops), so it passes the sandbox's AST gate."""

    def __init__(self):
        self.lines, self.n = [], 0

    def w(self, line):
        self.lines.append(line)

    def node(self, kind, **props):
        self.n += 1
        v = f"n{self.n}"
        self.w(f"{v} = nodes.new({kind!r})")
        for k, val in props.items():
            self.w(f"{v}.{k} = {val!r}")
        return v

    def put(self, v, sock, val):
        """Set an input: a constant, or a link from a (node, output) pair."""
        if isinstance(val, tuple) and len(val) == 2 and isinstance(val[0], str) and isinstance(val[1], (str, int)):
            self.w(f"links.new({val[0]}.outputs[{val[1]!r}], {v}.inputs[{sock!r}])")
        else:
            self.w(f"{v}.inputs[{sock!r}].default_value = {val!r}")

    def math(self, op, a, b=None, c=None, clamp=False):
        v = self.node("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, x in enumerate((a, b, c)):
            if x is not None:
                self.put(v, i, x)
        return (v, 0)

    def mix(self, fac, a, b):
        v = self.node("ShaderNodeMix", data_type="RGBA")
        self.put(v, 0, fac)
        self.put(v, 6, a)
        self.put(v, 7, b)
        return (v, 2)


def emit(preset_id: str, probe: bool = False) -> str:
    pr = PRESETS[preset_id]
    q = pr["params"]
    gname = ("LWPP_" if probe else "LWP_") + preset_id
    s = _S()
    s.w("import bpy")
    s.w(f"g = bpy.data.node_groups.new({gname!r}, 'ShaderNodeTree')")
    s.w("ifc = g.interface")
    defaults = {"Tint": _lin(q["color"]) + (1.0,), "Roughness Scale": 1.0, "Wear": q["wear"], "Scale": q["scale"], "Bump Strength": q["bump"], "Seed": 0.0, "Mask": 1.0}
    rng = {"Roughness Scale": (0.2, 2.0), "Wear": (0.0, 1.0), "Scale": (0.1, 10.0), "Bump Strength": (0.0, 1.0), "Seed": (0.0, 1000.0), "Mask": (0.0, 1.0)}
    for name, kind in INPUTS:
        s.w(f"s = ifc.new_socket({name!r}, in_out='INPUT', socket_type={kind!r})")
        s.w(f"s.default_value = {defaults[name]!r}")
        if name in rng:
            s.w(f"s.min_value = {rng[name][0]!r}")
            s.w(f"s.max_value = {rng[name][1]!r}")
    s.w("ifc.new_socket('Shader', in_out='OUTPUT', socket_type='NodeSocketShader')")
    if probe:
        s.w("ifc.new_socket('Base Color', in_out='OUTPUT', socket_type='NodeSocketColor')")
        s.w("ifc.new_socket('Metallic', in_out='OUTPUT', socket_type='NodeSocketFloat')")
        s.w("ifc.new_socket('Roughness', in_out='OUTPUT', socket_type='NodeSocketFloat')")
    s.w("nodes = g.nodes")
    s.w("links = g.links")
    gin = s.node("NodeGroupInput")
    gout = s.node("NodeGroupOutput")
    tc = s.node("ShaderNodeTexCoord")
    # mapping scale: Scale on all axes (brushed metal stretches Y)
    sx = s.node("ShaderNodeCombineXYZ")
    s.put(sx, "X", (gin, "Scale"))
    s.put(sx, "Z", (gin, "Scale"))
    if q.get("brushed"):
        y = s.math("MULTIPLY", (gin, "Scale"), 28.0)
        s.put(sx, "Y", y)
    else:
        s.put(sx, "Y", (gin, "Scale"))
    mp = s.node("ShaderNodeMapping")
    s.put(mp, "Vector", (tc, "Object"))
    s.put(mp, "Scale", (sx, "Vector"))
    vec = (mp, "Vector")
    seed2 = s.math("ADD", (gin, "Seed"), 11.0)
    nwear = s.node("ShaderNodeTexNoise", noise_dimensions="4D")
    s.put(nwear, "Vector", vec)
    s.put(nwear, "W", (gin, "Seed"))
    s.put(nwear, "Scale", 4.0)
    s.put(nwear, "Detail", 6.0)
    s.put(nwear, "Roughness", 0.55)
    nmic = s.node("ShaderNodeTexNoise", noise_dimensions="4D")
    s.put(nmic, "Vector", vec)
    s.put(nmic, "W", seed2)
    s.put(nmic, "Scale", 55.0)
    s.put(nmic, "Detail", 2.0)
    wear_f = s.math("MULTIPLY", s.math("MULTIPLY", (gin, "Wear"), (gin, "Mask")), (nwear, "Factor"), clamp=True)
    tmpl = pr["template"]
    height = None
    base_rough = q["rough"]
    colour = (gin, "Tint")
    metallic = 1.0 if tmpl == "metal" else 0.0
    normal_extra = None
    if tmpl == "metal":
        height = s.math("MULTIPLY", (nmic, "Factor"), q["micro"])
        if q["hammer"] > 0:
            vor = s.node("ShaderNodeTexVoronoi", voronoi_dimensions="4D", feature="DISTANCE_TO_EDGE")
            s.put(vor, "Vector", vec)
            s.put(vor, "W", (gin, "Seed"))
            s.put(vor, "Scale", 2.2)
            s.put(vor, "Detail", 0.0)
            ramp = s.math("MULTIPLY", s.math("SQRT", (vor, "Distance"), clamp=True), q["hammer"])
            height = s.math("ADD", height, ramp)
        worn = s.mix(s.math("MULTIPLY", wear_f, 0.55), colour, (0.0, 0.0, 0.0, 1.0)) if False else s.mix(s.math("MULTIPLY", wear_f, 0.5), colour, _dark(q["color"]))
        colour = worn
        if q["scratch"] > 0:
            wv = s.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="X")
            s.put(wv, "Vector", vec)
            s.put(wv, "Scale", 18.0)
            s.put(wv, "Distortion", 14.0)
            s.put(wv, "Detail", 2.0)
            line = s.math("MULTIPLY", s.math("SUBTRACT", (wv, "Factor"), 0.82, clamp=True), 5.5 * q["scratch"], clamp=True)
            colour = s.mix(s.math("MULTIPLY", line, s.math("ADD", 0.3, wear_f)), colour, (0.78, 0.78, 0.8, 1.0))
            base_rough = base_rough + 0.0
        rough = s.math("ADD", s.math("MULTIPLY", (gin, "Roughness Scale"), base_rough), s.math("MULTIPLY", wear_f, 0.45))
        if q["patina"] > 0:
            pm = s.math("MULTIPLY", s.math("MULTIPLY", s.math("SUBTRACT", (nwear, "Factor"), 0.42, clamp=True), 3.5, clamp=True), q["patina"], clamp=True)
            colour = s.mix(pm, colour, (0.12, 0.45, 0.38, 1.0))
            metallic = s.math("SUBTRACT", 1.0, s.math("MULTIPLY", pm, 0.8))
            rough = s.math("ADD", rough, s.math("MULTIPLY", pm, 0.3))
    elif tmpl == "leather":
        vor = s.node("ShaderNodeTexVoronoi", voronoi_dimensions="4D", feature="F1")
        s.put(vor, "Vector", vec)
        s.put(vor, "W", (gin, "Seed"))
        s.put(vor, "Scale", 9.0)
        height = s.math("ADD", s.math("MULTIPLY", (vor, "Distance"), q["grain"]), s.math("MULTIPLY", (nmic, "Factor"), 0.25))
        colour = s.mix(s.math("MULTIPLY", wear_f, 0.45), colour, _dark(q["color"]))
        rough = s.math("ADD", s.math("MULTIPLY", (gin, "Roughness Scale"), base_rough), s.math("MULTIPLY", wear_f, 0.2))
    else:                                                       # cloth: a plain weave from two crossed wave bands
        warp = s.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="X")
        s.put(warp, "Vector", vec)
        s.put(warp, "Scale", 22.0)
        s.put(warp, "Distortion", 1.5)
        weft = s.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y")
        s.put(weft, "Vector", vec)
        s.put(weft, "Scale", 22.0)
        s.put(weft, "Distortion", 1.5)
        cross = s.math("MAXIMUM", (warp, "Factor"), (weft, "Factor"))
        height = s.math("ADD", s.math("MULTIPLY", cross, q["weave"]), s.math("MULTIPLY", (nmic, "Factor"), 0.15))
        vary = s.math("ADD", 0.85, s.math("MULTIPLY", (nwear, "Factor"), 0.3))
        colour = s.mix(s.math("MULTIPLY", wear_f, 0.3), s.mix(1.0, (gin, "Tint"), _dark(q["color"], 0.6)) if False else (gin, "Tint"), _dark(q["color"], 0.5))
        rough = s.math("ADD", s.math("MULTIPLY", (gin, "Roughness Scale"), base_rough), s.math("MULTIPLY", wear_f, 0.05), clamp=True)
        _ = vary
    colour = s.mix(s.math("MULTIPLY", s.math("MULTIPLY", s.math("SUBTRACT", (nwear, "Factor"), 0.38, clamp=True), 3.0, clamp=True), 0.55), colour, _dark(q["color"], 0.6))          # a slow tint drift: what the Seed input moves the most
    rough = s.math("MINIMUM", s.math("MAXIMUM", rough, 0.03), 1.0) if not isinstance(rough, str) else rough
    bump = s.node("ShaderNodeBump")
    s.put(bump, "Strength", (gin, "Bump Strength"))
    s.put(bump, "Distance", 0.02)
    s.put(bump, "Height", height)
    bsdf = s.node("ShaderNodeBsdfPrincipled")
    s.put(bsdf, "Base Color", colour)
    s.put(bsdf, "Metallic", metallic)
    s.put(bsdf, "Roughness", rough)
    s.put(bsdf, "Normal", (bump, "Normal"))
    if tmpl == "cloth":
        s.put(bsdf, "Sheen Weight", 0.4)
    s.put(gout, "Shader", (bsdf, "BSDF"))
    if probe:
        s.put(gout, "Base Color", colour)
        s.put(gout, "Metallic", metallic)
        s.put(gout, "Roughness", rough)
    return "\n".join(s.lines) + "\n"


def _dark(c, k=0.35):
    return _lin(tuple(x * k for x in c)) + (1.0,)


def script_sha(preset_id: str) -> str:
    return hashlib.sha256(emit(preset_id).encode()).hexdigest()


def manifest() -> dict:
    return {"library_version": LIBRARY_VERSION, "entries": [{"id": k, "template": v["template"], "params_sha": hashlib.sha256(json.dumps(v["params"], sort_keys=True).encode()).hexdigest()[:16],
                                                            "script_sha": script_sha(k)[:16]} for k, v in sorted(PRESETS.items())]}


def manifest_hash() -> str:
    return hashlib.sha256(json.dumps(manifest(), sort_keys=True).encode()).hexdigest()


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
    """Three 1-sample Cycles CPU renders of a top-down plane whose emission is the probe's Base Color, Metallic and Roughness outputs."""
    key = (pid, json.dumps(params, sort_keys=True), size)
    if key in _BAKES and out_png is None:
        return _BAKES[key]
    g, _ms = _build(pid, probe=True)
    import tempfile
    scratch = Path(tmp_dir) if tmp_dir else Path(tempfile.mkdtemp(prefix="lw_probe_"))
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
        sc.render.engine = "CYCLES"
        sc.cycles.device, sc.cycles.samples, sc.cycles.use_denoising = "CPU", 1, False
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
