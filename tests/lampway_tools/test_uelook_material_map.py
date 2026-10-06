# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""ue_material, the pure half (specs/ue_parity/contracts/ue_material.md §6, §10): the Principled -> UE Default Lit map is a
function of plain data, so it runs here without Blender. T-MAT-01..06 as the contract numbers them; the node group and its
renders are in test_uelook_material_group.py (real binary)."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.ue import material_map as MM  # noqa: E402
from mixar.modules.lampway_tools.ue import profile as PR  # noqa: E402


@pytest.fixture
def profile():
    return PR.load(PR.DEFAULT_PROFILE)


def spec(**inputs):
    s = {"material": "M", "shader": "principled", "surface_render_method": "DITHERED", "use_backface_culling": False, "inputs": {},
         "linked": {}, "normal": None}
    for k, v in inputs.items():
        if k in ("surface_render_method", "use_backface_culling", "linked", "normal", "shader"):
            s[k] = v
        else:
            s["inputs"][k.replace("_", " ")] = v
    return s


MERGE = {"convention": "both", "colorspace": {"BaseColor": "sRGB", "ORM": "Non-Color", "Normal_DX": "Non-Color", "Normal_GL": "Non-Color"},
         "orm": "R occlusion, G roughness, B metallic (Unreal order), linear"}


def test_mat01_translation_is_deterministic(profile):
    a = MM.translate(spec(Metallic=0.3, Roughness=0.42), profile, mode="report")
    b = MM.translate(spec(Metallic=0.3, Roughness=0.42), profile, mode="report")
    assert a["translation_sha256"] == b["translation_sha256"] and len(a["translation_sha256"]) == 64
    c = MM.translate(spec(Metallic=0.3, Roughness=0.43), profile, mode="report")
    assert c["translation_sha256"] != a["translation_sha256"]                         # the hash covers the values
    assert a["preview_group"] == "LW_UE_DefaultLit_v1" and a["ue"]["scalars"]["Metallic"] == 0.3


def test_mat02_orm_channels_follow_merge_json(profile):
    t = MM.translate(spec(), profile, mode="export", merge=MERGE)
    assert t["ue"]["textures"]["ORM"] == {"file": "ORM.png", "srgb": False, "compression": "TC_Masks", "channels": "R=AO G=Roughness B=Metallic"}
    assert t["ue"]["textures"]["Normal"] == {"file": "Normal_DX.png", "srgb": False, "compression": "TC_Normalmap", "flip_green": False}
    assert t["ue"]["textures"]["BaseColor"] == {"file": "BaseColor.png", "srgb": True, "compression": "TC_Default"}
    swapped = dict(MERGE, orm="R roughness, G occlusion, B metallic")
    assert MM.translate(spec(), profile, mode="export", merge=swapped)["ue"]["textures"]["ORM"]["channels"] == "R=Roughness G=AO B=Metallic"
    with pytest.raises(MM.TranslationError, match="merge.json"):
        MM.translate(spec(), profile, mode="export", merge=None)


def test_mat02_export_refuses_a_texture_without_a_declared_colour_space(profile):
    undeclared = dict(MERGE, colorspace={"BaseColor": "sRGB", "Normal_DX": "Non-Color"})
    with pytest.raises(MM.TranslationError, match="declare the colour space: pbr_pack writes it"):
        MM.translate(spec(), profile, mode="export", merge=undeclared, files=["BaseColor.png", "ORM.png", "Normal_DX.png"])


def test_mat03_specular_and_base_clamps(profile):
    assert MM.translate(spec(IOR=1.5, Specular_IOR_Level=0.5), profile, mode="report")["ue"]["scalars"]["Specular"] == 0.5
    t = MM.translate(spec(IOR=1.5, Specular_IOR_Level=1.0), profile, mode="report")
    assert t["ue"]["scalars"]["Specular"] == 1.0 and t["clamped"] == []
    t = MM.translate(spec(IOR=2.0, Specular_IOR_Level=0.5), profile, mode="report")
    assert t["ue"]["scalars"]["Specular"] == 1.0
    assert t["clamped"] == [{"input": "Specular IOR Level", "from": 0.5, "to_ue_specular": 1.0, "why": "UE F0 ≤ 0.08 (SHD-03)", "f0": 0.111111}]
    t = MM.translate(spec(Base_Color=[1.3, 0.5, 0.2, 1.0]), profile, mode="report")
    assert t["ue"]["vectors"]["BaseColor"] == [1.0, 0.5, 0.2, 1.0]
    assert t["clamped"] == [{"input": "Base Color", "from": [1.3, 0.5, 0.2], "to": [1.0, 0.5, 0.2], "why": "UE BaseColor is stored in [0, 1] (SHD-22)"}]


def test_mat04_losses_are_reported_and_refused_on_request(profile):
    lossy = spec(Sheen_Weight=0.3, Coat_Tint=[1.0, 0.0, 0.0, 1.0], Anisotropic=0.5, Thin_Film_Thickness=300.0, Diffuse_Roughness=0.5)
    t = MM.translate(lossy, profile, mode="report")
    assert [d["input"] for d in t["dropped"]] == ["Sheen Weight", "Coat Tint", "Anisotropic", "Thin Film Thickness", "Diffuse Roughness"]
    assert all(d["why"] for d in t["dropped"])
    with pytest.raises(MM.TranslationError) as e:
        MM.translate(lossy, profile, mode="report", on_loss="refuse")
    for name in ("Sheen Weight", "Coat Tint", "Anisotropic", "Thin Film Thickness", "Diffuse Roughness"):
        assert name in str(e.value)
    assert MM.translate(spec(), profile, mode="report")["dropped"] == []              # defaults lose nothing


def test_mat05_alpha_rules(profile):
    assert MM.translate(spec(surface_render_method="BLENDED", Alpha=0.5), profile, mode="report")["ue"]["blend_mode"] == "Translucent"
    t = MM.translate(spec(linked={"Alpha": {"file": "BaseColor.png", "colorspace": "sRGB"}}), profile, mode="report")
    assert t["ue"]["blend_mode"] == "Masked" and t["ue"]["opacity_mask_clip"] == 0.3333
    assert MM.translate(spec(Alpha=0.99), profile, mode="report")["ue"]["blend_mode"] == "Masked"
    assert MM.translate(spec(), profile, mode="report")["ue"]["blend_mode"] == "Opaque"
    assert MM.translate(spec(use_backface_culling=True), profile, mode="report")["ue"]["two_sided"] is False
    assert MM.translate(spec(use_backface_culling=False), profile, mode="report")["ue"]["two_sided"] is True


def test_mat06_normal_strength_halves_xy_and_rebuilds_z():
    rng = np.random.default_rng(3)
    xy = rng.uniform(-0.6, 0.6, (16, 16, 2))
    z = np.sqrt(np.clip(1 - (xy ** 2).sum(-1), 0, 1))
    dx = np.round((np.dstack([xy, z]) * 0.5 + 0.5) * 255).astype(np.uint8)
    half = MM.normal_strength(dx, 0.5)
    got = half.astype(float) / 255 * 2 - 1
    src = dx.astype(float) / 255 * 2 - 1
    assert half.dtype == np.uint8 and half.shape == dx.shape
    assert np.abs(got[..., :2] - src[..., :2] * 0.5).max() <= 1.5 / 255 * 2               # XY halved (to the 8-bit step)
    want_z = np.sqrt(np.clip(1 - (src[..., :2] * 0.5) ** 2 @ np.ones(2), 0, 1))
    assert np.abs(got[..., 2] - want_z).max() <= 1.5 / 255 * 2                              # Z rebuilt, UE style
    assert np.array_equal(MM.normal_strength(dx, 1.0), dx)


def test_emission_scales_by_k_and_the_texture_spaces(profile):
    t = MM.translate(spec(Emission_Color=[1.0, 0.5, 0.25, 1.0], Emission_Strength=2.0), profile, mode="report")
    assert t["ue"]["vectors"]["EmissiveColor"] == [1.0, 0.5, 0.25, 1.0]
    assert t["ue"]["scalars"]["EmissiveStrength"] == 2.0 * profile["light_units"]["k"]


def test_refusals_name_their_fix(profile):
    with pytest.raises(MM.TranslationError, match="bake the node tree first"):
        MM.translate(spec(shader="other"), profile, mode="report")
    sub = json.loads(json.dumps(profile))
    sub["project"]["cvars"]["r.Material.EnergyConservation"] = 1
    with pytest.raises(MM.TranslationError, match="energy-conserving"):
        MM.translate(spec(), sub, mode="report")
    with pytest.raises(MM.TranslationError, match="mode is preview, export or report"):
        MM.translate(spec(), profile, mode="bake")


def test_coat_follows_the_profile_choice(profile):
    coated = spec(Coat_Weight=0.6, Coat_Roughness=0.2)
    t = MM.translate(coated, profile, mode="report")
    assert profile["material"]["clear_coat"] is False
    assert t["ue"]["shading_model"] == "DefaultLit" and [d["input"] for d in t["dropped"]] == ["Coat Weight"]
    allow = json.loads(json.dumps(profile))
    allow["material"]["clear_coat"] = True
    t = MM.translate(coated, allow, mode="report")
    assert t["ue"]["shading_model"] == "ClearCoat" and t["ue"]["scalars"]["ClearCoat"] == 0.6 and t["ue"]["scalars"]["ClearCoatRoughness"] == 0.2
