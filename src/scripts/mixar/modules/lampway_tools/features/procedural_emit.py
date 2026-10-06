# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The procedural library's script emitter: one node-group script per preset, built from the template the preset names (procedural_presets.py). Plain statements
only (no setattr, no dunders, no ops), so every script passes the sandbox's AST gate. Pure Python: the script runs in Blender, this module does not need bpy."""

import hashlib
import json

from .procedural_presets import PRESETS

LIBRARY_VERSION = "2"
METAL_TEMPLATES = ("metal_base", "hammered", "brushed", "scratched", "pitted", "rust_overlay", "patina_overlay", "damascus")
INPUTS = [("Tint", "NodeSocketColor"), ("Roughness Scale", "NodeSocketFloat"), ("Wear", "NodeSocketFloat"), ("Scale", "NodeSocketFloat"), ("Bump Strength", "NodeSocketFloat"),
          ("Seed", "NodeSocketFloat"), ("Mask", "NodeSocketFloat")]


def _lin(c):
    return tuple(round(x ** 2.2, 5) for x in c)


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
    if q.get("brushed") or q.get("strands"):                    # brushed metal and horsehair stretch along Y
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
    family = "metal" if tmpl in METAL_TEMPLATES else "leather" if tmpl == "leather_grain" else "embroidery" if tmpl == "embroidery" else "cloth"
    height = None
    base_rough = q["rough"]
    colour = (gin, "Tint")
    metallic = 1.0 if family == "metal" else 0.0
    if family == "metal":
        height = s.math("MULTIPLY", (nmic, "Factor"), q["micro"])
        if q["hammer"] > 0:
            vor = s.node("ShaderNodeTexVoronoi", voronoi_dimensions="4D", feature="DISTANCE_TO_EDGE")
            s.put(vor, "Vector", vec)
            s.put(vor, "W", (gin, "Seed"))
            s.put(vor, "Scale", 2.2)
            s.put(vor, "Detail", 0.0)
            ramp = s.math("MULTIPLY", s.math("SQRT", (vor, "Distance"), clamp=True), q["hammer"])
            height = s.math("ADD", height, ramp)
        colour = s.mix(s.math("MULTIPLY", wear_f, 0.5), colour, _dark(q["color"]))
        if q["scratch"] > 0:
            wv = s.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="X")
            s.put(wv, "Vector", vec)
            s.put(wv, "Scale", 18.0)
            s.put(wv, "Distortion", 14.0)
            s.put(wv, "Detail", 2.0)
            line = s.math("MULTIPLY", s.math("SUBTRACT", (wv, "Factor"), 0.82, clamp=True), 5.5 * q["scratch"], clamp=True)
            colour = s.mix(s.math("MULTIPLY", line, s.math("ADD", 0.3, wear_f)), colour, (0.78, 0.78, 0.8, 1.0))
        rough = s.math("ADD", s.math("MULTIPLY", (gin, "Roughness Scale"), base_rough), s.math("MULTIPLY", wear_f, 0.45))
        if q.get("bands", 0) > 0:                                  # damascus: flowing bands in tone and roughness
            dm = s.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Z")
            s.put(dm, "Vector", vec)
            s.put(dm, "Scale", 5.0)
            s.put(dm, "Distortion", 9.0)
            s.put(dm, "Detail", 3.0)
            colour = s.mix(s.math("MULTIPLY", (dm, "Factor"), 0.7 * q["bands"]), colour, _lin((0.80, 0.80, 0.82)) + (1.0,))
            rough = s.math("ADD", rough, s.math("MULTIPLY", s.math("SUBTRACT", (dm, "Factor"), 0.5), 0.25 * q["bands"]))
        if q.get("pits", 0) > 0:                                   # pits: small inverted Voronoi cells, rougher inside
            pv = s.node("ShaderNodeTexVoronoi", voronoi_dimensions="4D", feature="F1")
            s.put(pv, "Vector", vec)
            s.put(pv, "W", seed2)
            s.put(pv, "Scale", 16.0)
            pit = s.math("MULTIPLY", s.math("SUBTRACT", 0.35, (pv, "Distance"), clamp=True), 2.8 * q["pits"], clamp=True)
            height = s.math("SUBTRACT", height, pit)
            rough = s.math("ADD", rough, s.math("MULTIPLY", pit, 0.3))
            colour = s.mix(s.math("MULTIPLY", pit, 0.5), colour, _dark(q["color"], 0.4))
        drops = []
        if q["patina"] > 0:
            pm = s.math("MULTIPLY", s.math("MULTIPLY", s.math("SUBTRACT", (nwear, "Factor"), 0.42, clamp=True), 3.5, clamp=True), q["patina"], clamp=True)
            colour = s.mix(pm, colour, (0.12, 0.45, 0.38, 1.0))
            drops.append(pm)
            rough = s.math("ADD", rough, s.math("MULTIPLY", pm, 0.3))
        if q.get("rust", 0) > 0:                                   # rust: a noise mask of orange-brown oxide that is not metal
            rn = s.node("ShaderNodeTexNoise", noise_dimensions="4D")
            s.put(rn, "Vector", vec)
            s.put(rn, "W", s.math("ADD", (gin, "Seed"), 23.0))
            s.put(rn, "Scale", 7.0)
            s.put(rn, "Detail", 8.0)
            rm = s.math("MULTIPLY", s.math("MULTIPLY", s.math("SUBTRACT", (rn, "Factor"), 0.5 - 0.12 * q["rust"], clamp=True), 4.0, clamp=True), min(1.0, q["rust"]), clamp=True)
            colour = s.mix(rm, colour, _lin((0.45, 0.20, 0.08)) + (1.0,))
            drops.append(rm)
            rough = s.math("ADD", rough, s.math("MULTIPLY", rm, 0.35))
        if drops:
            total = drops[0] if len(drops) == 1 else s.math("ADD", drops[0], drops[1], clamp=True)
            metallic = s.math("SUBTRACT", 1.0, s.math("MULTIPLY", total, 0.8))
    elif family == "leather":
        vor = s.node("ShaderNodeTexVoronoi", voronoi_dimensions="4D", feature="F1")
        s.put(vor, "Vector", vec)
        s.put(vor, "W", (gin, "Seed"))
        s.put(vor, "Scale", 9.0)
        height = s.math("ADD", s.math("MULTIPLY", (vor, "Distance"), q["grain"]), s.math("MULTIPLY", (nmic, "Factor"), 0.25))
        colour = s.mix(s.math("MULTIPLY", wear_f, 0.45), colour, _dark(q["color"]))
        rough = s.math("ADD", s.math("MULTIPLY", (gin, "Roughness Scale"), base_rough), s.math("MULTIPLY", wear_f, 0.2))
        if q.get("stitch", 0) > 0:                                 # a running stitch: dashes along X inside one band of Y
            st = _stitch_mask(s, vec, 40.0, 3.0, 0.82)
            colour = s.mix(s.math("MULTIPLY", st, q["stitch"]), colour, _lin((0.78, 0.70, 0.55)) + (1.0,))
            height = s.math("ADD", height, s.math("MULTIPLY", st, 0.6))
    elif family == "embroidery":                               # a raised thread pattern over a cloth ground
        mask = _thread_mask(s, vec, q["pattern"], q["density"], (nwear, "Factor"))
        colour = s.mix(mask, s.mix(s.math("MULTIPLY", wear_f, 0.3), colour, _dark(q["color"], 0.5)), _lin(q["thread"]) + (1.0,))
        rough = s.math("ADD", s.math("MULTIPLY", (gin, "Roughness Scale"), s.math("ADD", base_rough, s.math("MULTIPLY", mask, 0.45 - base_rough))), s.math("MULTIPLY", wear_f, 0.05), clamp=True)
        height = s.math("ADD", s.math("MULTIPLY", mask, 0.8), s.math("MULTIPLY", (nmic, "Factor"), 0.15))
    else:                                                       # weave: a plain weave from two crossed wave bands; cloth_fold: strands or slow folds
        if tmpl == "cloth_fold":
            fold = s.node("ShaderNodeTexNoise", noise_dimensions="4D")
            s.put(fold, "Vector", vec)
            s.put(fold, "W", (gin, "Seed"))
            s.put(fold, "Scale", 1.6 if q.get("strands") else 0.9)
            s.put(fold, "Detail", 4.0 if q.get("strands") else 1.0)
            if q.get("strands"):
                cross = (nmic, "Factor")
            else:                                               # quilted: a lattice of soft cells
                qv = s.node("ShaderNodeTexVoronoi", voronoi_dimensions="4D", feature="DISTANCE_TO_EDGE")
                s.put(qv, "Vector", vec)
                s.put(qv, "W", (gin, "Seed"))
                s.put(qv, "Scale", 3.0)
                cross = s.math("SQRT", (qv, "Distance"), clamp=True)
            height = s.math("ADD", s.math("MULTIPLY", cross, q["weave"]), s.math("MULTIPLY", (fold, "Factor"), 0.4))
            colour = s.mix(s.math("MULTIPLY", s.math("SUBTRACT", 1.0, (fold, "Factor")), 0.5), colour, _dark(q["color"], 0.55))
        else:
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
        colour = s.mix(s.math("MULTIPLY", wear_f, 0.3), colour, _dark(q["color"], 0.5))
        rough = s.math("ADD", s.math("MULTIPLY", (gin, "Roughness Scale"), base_rough), s.math("MULTIPLY", wear_f, 0.05), clamp=True)
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
    if family in ("cloth", "embroidery"):
        s.put(bsdf, "Sheen Weight", 0.4)
    s.put(gout, "Shader", (bsdf, "BSDF"))
    if probe:
        s.put(gout, "Base Color", colour)
        s.put(gout, "Metallic", metallic)
        s.put(gout, "Roughness", rough)
    return "\n".join(s.lines) + "\n"


def _stitch_mask(s, vec, along, across, cut):
    """Dashes (wave bands along X, thresholded) inside one narrow band of Y: a running stitch."""
    dash = s.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="X")
    s.put(dash, "Vector", vec)
    s.put(dash, "Scale", along)
    band = s.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y")
    s.put(band, "Vector", vec)
    s.put(band, "Scale", across)
    return s.math("MULTIPLY", s.math("GREATER_THAN", (dash, "Factor"), 0.5), s.math("GREATER_THAN", (band, "Factor"), cut))


def _thread_mask(s, vec, pattern, density, slow):
    """0..1 where thread lies: satin (stitches inside noise motifs), key (a brick lattice: a meander-like trim), edge (a running stitch), braid (twisted cord)."""
    if pattern == "satin":
        st = s.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="DIAGONAL")
        s.put(st, "Vector", vec)
        s.put(st, "Scale", 30.0)
        motif = s.math("GREATER_THAN", slow, 1.0 - density)
        return s.math("MULTIPLY", motif, s.math("GREATER_THAN", (st, "Factor"), 0.25))
    if pattern == "key":
        br = s.node("ShaderNodeTexBrick")
        s.put(br, "Vector", vec)
        s.put(br, "Scale", 4.0)
        s.put(br, "Mortar Size", 0.08 + 0.1 * density)
        return s.math("SUBTRACT", 1.0, (br, "Factor"))              # Factor is 1 on the bricks: the thread is the mortar lattice, the bricks are the ground
    if pattern == "edge":
        return _stitch_mask(s, vec, 30.0, 2.0, 1.0 - density * 0.3)
    tw = s.node("ShaderNodeTexWave", wave_type="BANDS", bands_direction="DIAGONAL")
    s.put(tw, "Vector", vec)
    s.put(tw, "Scale", 12.0)
    s.put(tw, "Distortion", 4.0)
    return s.math("GREATER_THAN", (tw, "Factor"), 1.0 - density)


def _dark(c, k=0.35):
    return _lin(tuple(x * k for x in c)) + (1.0,)


def script_sha(preset_id: str) -> str:
    return hashlib.sha256(emit(preset_id).encode()).hexdigest()


def manifest() -> dict:
    return {"library_version": LIBRARY_VERSION, "entries": [{"id": k, "template": v["template"], "params_sha": hashlib.sha256(json.dumps(v["params"], sort_keys=True).encode()).hexdigest()[:16],
                                                            "script_sha": script_sha(k)[:16]} for k, v in sorted(PRESETS.items())]}


def manifest_hash() -> str:
    return hashlib.sha256(json.dumps(manifest(), sort_keys=True).encode()).hexdigest()
