# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""material_bake_export (specs/mixar_docs/material_bake_export.md): the editable layer-stack material baked to the images a destination needs, in a niced HEADLESS Cycles worker (never the live scene: the object,
its material, node groups and packed images go to a temporary .blend and only the finished images come back). Each channel is baked from the Principled BSDF's input (emission of what feeds it) or, for normal
and AO, with Cycles' own bake types. Base colour and emission are sRGB; every other map is Non-Color. normal_green dx flips the green channel at bake time. pack=orm writes Unreal's occlusion / roughness /
metallic order (R filled with 1.0 and a warning when no AO was baked). The README lists every file with its sha256 and the conventions. The layer stack is untouched."""

import hashlib
import json
import re
from pathlib import Path

import bpy

from . import common as C

CHANNELS = ("base_color", "roughness", "metallic", "normal", "ao", "emission")
FORMATS = ("png", "exr", "tiff", "jpeg")
EXT = {"png": "png", "exr": "exr", "tiff": "tif", "jpeg": "jpg"}


def material_bake_export(root, object, material=None, channels=None, size=1024, format="png", pack="none", normal_green="gl", out_dir="bake_export", samples=8, allow_dirty=False, resolve=None, timeout=1800):  # noqa: A002
    from .. import runner as RUN
    from .. import settings as S
    ob = C.need_object(object)
    chans = list(channels or ("base_color", "roughness", "metallic", "normal"))
    bad = [c for c in chans if c not in CHANNELS]
    if bad:
        raise C.FeatureError(f"{', '.join(bad)} cannot be baked here; the channels are: {', '.join(CHANNELS)} (curvature, cavity and position are not material channels)")
    if format not in FORMATS:
        raise C.FeatureError(f"format is one of {list(FORMATS)}")
    if format == "jpeg" and "normal" in chans:
        raise C.FeatureError("lossy normal maps are refused (use png/exr)")
    if not 1024 <= int(size) <= 8192:
        raise C.FeatureError("size is 1024..8192")
    if int(size) & (int(size) - 1):
        raise C.FeatureError("size must be a power of two")
    if pack not in ("none", "orm"):
        raise C.FeatureError("pack is none | orm")
    if normal_green not in ("gl", "dx"):
        raise C.FeatureError("normal_green is gl | dx")
    if not 1 <= int(samples) <= 512:
        raise C.FeatureError("samples is 1..512")
    if pack == "orm":
        missing = [c for c in ("roughness", "metallic") if c not in chans]
        if missing:
            raise C.FeatureError(f"pack=orm needs {', '.join(missing)} baked too: add them to channels (ao is optional: R is filled with 1.0 and a warning)")
    out = Path(resolve(out_dir)) if resolve else Path(out_dir)
    from mixar.modules.paint.core import agent_tools as AT
    st = AT.inspect_paint_layer_stack(ob.name) if ob.type == "MESH" else {"success": False}
    if not st.get("success"):
        raise C.FeatureError(f"no layer-paint material on {ob.name}: build one first (lampway_layered_material action=init, or action=apply_manifest)")
    if not ob.data.uv_layers:
        raise C.FeatureError(f"{ob.name} has no UV map: unwrap first (lampway_uv_unwrap): a bake writes into UV space")
    if (not bpy.data.filepath or bpy.data.is_dirty) and not allow_dirty:
        raise C.FeatureError("save the project first: the bake does not change it, but you should be able to return to the layers (or pass allow_dirty=true)")
    out.mkdir(parents=True, exist_ok=True)
    for img in bpy.data.images:
        if img.is_dirty or (img.source == "GENERATED"):
            try:
                img.pack()
            except RuntimeError:
                pass
    pair, args, res = out / ".object.blend", out / ".args.json", out / ".result.json"
    bpy.data.libraries.write(str(pair), {ob}, fake_user=False)
    cfg = {"object": ob.name, "channels": chans, "size": int(size), "samples": int(samples), "margin_px": max(2, int(size) // 128), "out_dir": str(out), "format": format, "pack": pack, "normal_green": normal_green}
    args.write_text(json.dumps(cfg))
    r = RUN.run("material_bake", [str(pair), str(args), str(res)], S.load(), timeout=timeout)
    for f in (pair, args):
        f.unlink(missing_ok=True)
    if r.rc != 0 or not res.exists():
        raise C.FeatureError("the bake worker failed: " + re.sub(r"\s+", " ", r.stdout)[-400:])
    data = json.loads(res.read_text())
    res.unlink(missing_ok=True)
    sha = {k: hashlib.sha256(Path(p).read_bytes()).hexdigest() for k, p in data["files"].items()}
    lines = [f"# {ob.name}: baked material textures", "", f"Baked by Lampway from the layer-stack material of `{ob.name}` at {int(size)}x{int(size)} ({format}, {int(samples)} samples, headless Cycles).", ""]
    if data["warnings"]:
        lines += ["Warnings:"] + [f"- {w}" for w in data["warnings"]] + [""]
    lines += ["## Files", ""] + [f"- `{Path(p).name}` ({data['colourspace'][k]}): sha256 {sha[k]}" for k, p in sorted(data["files"].items())]
    lines += ["", "## Conventions", "", "- Base colour and emission are sRGB; every other map is Non-Color (linear).",
              f"- Normal maps: tangent space, {'OpenGL (green up): Unity, Blender, Godot' if normal_green == 'gl' else 'DirectX (green down): Unreal'}. Use one convention, never both.",
              "- ORM packs occlusion / roughness / metallic in R / G / B (Unreal Engine's order, linear).", "- The editable layer stack is unchanged: return to it to change the look.", ""]
    readme = out / "README.md"
    readme.write_text("\n".join(lines), encoding="utf-8")
    return {"ok": True, "files": data["files"], "sizes": [int(size), int(size)], "colour_spaces": data["colourspace"], "normal_green": normal_green, "sha256": sha, "readme": str(readme), "warnings": data["warnings"], "format": format}
