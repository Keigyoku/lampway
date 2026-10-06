# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Principled BSDF -> UE legacy Default Lit: the deterministic map (specs/ue_parity/contracts/ue_material.md §6).

Pure: the input is plain data read from the material (``material_group.read_spec`` does that in Blender), the output is the
parameter set of one UE material instance plus the loss report, hashed over its canonical JSON (sorted keys, floats to 6
decimals) so the same material always gives the same ``translation_sha256``.

The rules, each with its row in specs/ue_parity/DIFFERENCES.md:
  Base Color   -> BaseColor, clamped to [0, 1] and reported (SHD-22); a texture is sRGB, TC_Default
  Metallic, Roughness -> as is (SHD-23, SHD-07: both GGX with alpha = roughness^2); from ORM.B / ORM.G as merge.json declares
  IOR + Specular IOR Level -> Specular = clamp(2 * level * ((ior - 1) / (ior + 1))^2 / 0.08, 0, 1), the clamp reported (SHD-03)
  Emission Color x Strength -> EmissiveColor, EmissiveStrength x k (the profile's light-unit factor, LGT-01, SHD-16)
  Alpha        -> Blended: Translucent; any other alpha below 1 or a linked alpha: Masked at clip 0.3333 (SHD-17)
  Backface Culling -> Two Sided = not culling (SHD-18)
  Coat         -> ClearCoat only when the profile's material.clear_coat allows that shading model (SHD-11)
  every input Default Lit cannot carry, at a non-default value -> dropped (reported), or refused with on_loss=refuse
"""

import hashlib
import re

import numpy as np

from . import profile as PR

GROUP_NAME = "LW_UE_DefaultLit_v1"
DEFAULT_MASTER = "/Game/Lampway/M_LampwayDefaultLit"
OPACITY_MASK_CLIP = 0.3333          # UE's default OpacityMaskClipValue (SHD-17)
UE_MAX_F0 = 0.08                    # UE dielectric F0 = 0.08 * Specular (SHD-03)

# Blender 5.2's Principled BSDF defaults (read from the node in the binary): an input absent from a spec has this value
PRINCIPLED_DEFAULTS = {
    "Base Color": [0.8, 0.8, 0.8, 1.0], "Metallic": 0.0, "Roughness": 0.5, "IOR": 1.5, "Alpha": 1.0, "Diffuse Roughness": 0.0,
    "Subsurface Weight": 0.0, "Specular IOR Level": 0.5, "Specular Tint": [1.0, 1.0, 1.0, 1.0], "Anisotropic": 0.0,
    "Transmission Weight": 0.0, "Coat Weight": 0.0, "Coat Roughness": 0.03, "Coat IOR": 1.5, "Coat Tint": [1.0, 1.0, 1.0, 1.0],
    "Sheen Weight": 0.0, "Emission Color": [1.0, 1.0, 1.0, 1.0], "Emission Strength": 0.0, "Thin Film Thickness": 0.0,
}

# inputs Default Lit cannot carry, in report order, with why (Coat Weight is handled by the profile's clear_coat choice)
LOSSY = (
    ("Specular Tint", "Default Lit has no specular tint (SHD-05)"),
    ("Sheen Weight", "Default Lit has no sheen (SHD-10)"),
    ("Coat Weight", "the profile does not allow the Clear Coat model (material.clear_coat false) (SHD-11)"),
    ("Coat Tint", "UE ClearCoat has no tint (SHD-11)"),
    ("Coat IOR", "UE ClearCoat has a fixed IOR (SHD-11)"),
    ("Subsurface Weight", "Default Lit has no subsurface (SHD-12)"),
    ("Transmission Weight", "Default Lit has no transmission (SHD-14)"),
    ("Anisotropic", "Default Lit has no anisotropy (SHD-13)"),
    ("Thin Film Thickness", "Default Lit has no thin film (SHD-15)"),
    ("Diffuse Roughness", "UE's Lambert diffuse has no roughness (SHD-09)"),
)

_ORM_WORDS = {"occlusion": "AO", "ao": "AO", "roughness": "Roughness", "metallic": "Metallic", "metalness": "Metallic"}


class TranslationError(ValueError):
    pass


def _r(v):
    return [round(float(x), 6) for x in v] if isinstance(v, (list, tuple)) else round(float(v), 6)


def _differs(a, b):
    if isinstance(b, list):
        return any(abs(float(x) - float(y)) > 1e-6 for x, y in zip(a, b))
    return abs(float(a) - float(b)) > 1e-6


def _orm_channels(decl: str) -> str:
    found = re.findall(r"\b([RGB])\s+(occlusion|ao|roughness|metallic|metalness)\b", decl or "", re.I)
    chans = {c.upper(): _ORM_WORDS[w.lower()] for c, w in found}
    if sorted(chans) != ["B", "G", "R"] or len(set(chans.values())) != 3:
        raise TranslationError(f"merge.json's orm declaration must name R, G and B once each (occlusion, roughness, metallic): got {decl!r}")
    return " ".join(f"{c}={chans[c]}" for c in "RGB")


def _export_textures(merge, files):
    if not merge:
        raise TranslationError("export mode reads the pbr_pack merge.json (merge_json): pack the maps first (lampway_pbr_pack)")
    cs = merge.get("colorspace") or {}
    present = list(files) if files is not None else [f"{k}.png" for k in cs]
    for f in present:
        stem = f.rsplit(".", 1)[0]
        if stem in ("BaseColor", "ORM", "Normal_DX", "Normal_GL") and stem not in cs:
            raise TranslationError(f"{f} has no colour space in merge.json: declare the colour space: pbr_pack writes it")
    out = {}
    if "BaseColor.png" in present:
        out["BaseColor"] = {"file": "BaseColor.png", "srgb": cs["BaseColor"] == "sRGB", "compression": "TC_Default"}
    if "ORM.png" in present:
        out["ORM"] = {"file": "ORM.png", "srgb": cs["ORM"] == "sRGB", "compression": "TC_Masks", "channels": _orm_channels(merge.get("orm", ""))}
    if "Normal_DX.png" in present:
        out["Normal"] = {"file": "Normal_DX.png", "srgb": False, "compression": "TC_Normalmap", "flip_green": False}
    elif "Normal_GL.png" in present:
        out["Normal"] = {"file": "Normal_GL.png", "srgb": False, "compression": "TC_Normalmap", "flip_green": True}
    return out


def _preview_textures(spec):
    out = {}
    for name, tex in sorted((spec.get("linked") or {}).items()):
        key = name.replace(" ", "")
        out[key] = {"file": tex.get("file"), "srgb": tex.get("colorspace") == "sRGB", "compression": "TC_Default" if name == "Base Color" else "TC_Masks"}
    n = spec.get("normal")
    if n:
        out["Normal"] = {"file": n.get("file"), "srgb": False, "compression": "TC_Normalmap", "flip_green": n.get("convention", "OPENGL") != "DIRECTX",
                         "strength": _r(n.get("strength", 1.0))}
    return out


def translate(spec, profile, mode="preview", merge=None, files=None, master=None, on_loss="report"):
    """spec: {material, shader: principled|ue_group|other, surface_render_method, use_backface_culling, inputs {name: value},
    linked {name: {file, colorspace}}, normal {file, colorspace, strength, convention} | None}. Returns the contract §5 dict."""
    if mode not in ("preview", "export", "report"):
        raise TranslationError("mode is preview, export or report")
    if on_loss not in ("report", "refuse"):
        raise TranslationError("on_loss is report or refuse")
    cv = profile["project"]["cvars"]
    if cv["r.Substrate"] != 0 or cv["r.Material.EnergyConservation"] != 0:
        raise TranslationError("this project runs Substrate / energy-conserving materials: the Default Lit group is the wrong model; "
                               "regenerate the translation for that profile")
    if spec.get("shader") not in ("principled", "ue_group"):
        raise TranslationError("translation reads one Principled BSDF per material: bake the node tree first (material_bake_export)")
    v = dict(PRINCIPLED_DEFAULTS, **(spec.get("inputs") or {}))
    linked = spec.get("linked") or {}
    dropped, clamped, notes = [], [], []

    base = [float(x) for x in v["Base Color"]][:4] + [1.0] * (4 - len(v["Base Color"]))
    base_c = [min(max(x, 0.0), 1.0) for x in base[:3]] + [base[3]]
    if _differs(base[:3], base_c[:3]):
        clamped.append({"input": "Base Color", "from": _r(base[:3]), "to": _r(base_c[:3]), "why": "UE BaseColor is stored in [0, 1] (SHD-22)"})
    ior, level = float(v["IOR"]), float(v["Specular IOR Level"])
    f0 = ((ior - 1.0) / (ior + 1.0)) ** 2 * 2.0 * level
    spec_ue = round(f0 / UE_MAX_F0, 6)
    if spec_ue > 1.0:
        clamped.append({"input": "Specular IOR Level", "from": _r(level), "to_ue_specular": 1.0, "why": "UE F0 ≤ 0.08 (SHD-03)", "f0": _r(f0)})
    spec_ue = min(max(spec_ue, 0.0), 1.0)

    coat = profile["material"]["clear_coat"] and float(v["Coat Weight"]) > 0
    for name, why in LOSSY:
        if name == "Coat Weight" and coat:
            continue
        val = v[name]
        if _differs(val, PRINCIPLED_DEFAULTS[name]):
            dropped.append({"input": name, "value": _r(val[:3] if isinstance(val, list) else val), "why": why})
    if on_loss == "refuse" and dropped:
        raise TranslationError("on_loss=refuse: the translation loses " + "; ".join(f"{d['input']} ({d['why']})" for d in dropped))

    method = spec.get("surface_render_method", "DITHERED")
    alpha_linked = "Alpha" in linked
    blend = "Translucent" if method == "BLENDED" else ("Masked" if alpha_linked or float(v["Alpha"]) < 1.0 else "Opaque")
    k = profile["light_units"]["k"]
    scalars = {"Metallic": _r(v["Metallic"]), "Roughness": _r(v["Roughness"]), "Specular": spec_ue, "EmissiveStrength": _r(float(v["Emission Strength"]) * k)}
    if coat:
        scalars.update(ClearCoat=_r(v["Coat Weight"]), ClearCoatRoughness=_r(v["Coat Roughness"]))
    textures = _export_textures(merge, files) if mode == "export" else _preview_textures(spec)
    if "ORM" in textures:
        notes.append("ORM.R (AmbientOcclusion) attenuates UE's indirect light only: Lampway cannot preview it (SHD-19)")
    if coat:
        notes.append("the Lampway preview draws no coat: ClearCoat is judged in UE (SHD-11)")
    ue = {"master": master or DEFAULT_MASTER, "shading_model": "ClearCoat" if coat else "DefaultLit", "blend_mode": blend,
          "two_sided": not bool(spec.get("use_backface_culling", False)), "opacity_mask_clip": OPACITY_MASK_CLIP, "scalars": scalars,
          "vectors": {"BaseColor": _r(base_c), "EmissiveColor": _r(list(v["Emission Color"])[:4])}, "textures": textures}
    body = {"material": spec.get("material"), "ue": ue, "preview_group": GROUP_NAME, "dropped": dropped, "clamped": clamped}
    sha = hashlib.sha256(PR.canonical_json(body).encode("utf-8")).hexdigest()
    return dict(body, translation_sha256=sha, notes=notes, mode=mode)


def normal_strength(texels, strength):
    """A DirectX normal map at Normal Map strength ``strength``, baked: XY scaled, Z rebuilt as UE rebuilds it
    (sqrt(1 - x^2 - y^2), NRM-02). uint8 (H, W, 3) in, uint8 out; strength 1 returns the texels unchanged (SHD-20)."""
    a = np.asarray(texels)
    if float(strength) == 1.0:
        return a.copy()
    n = a.astype(np.float64) / 255.0 * 2.0 - 1.0
    xy = n[..., :2] * float(strength)
    z = np.sqrt(np.clip(1.0 - (xy ** 2).sum(-1), 0.0, 1.0))
    out = np.dstack([xy, z]) * 0.5 + 0.5
    return np.clip(np.round(out * 255.0), 0, 255).astype(np.uint8)
