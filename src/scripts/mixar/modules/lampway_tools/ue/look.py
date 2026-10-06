# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The one-click "UE Look" mode: apply / status / revert (specs/ue_parity/contracts/ue_look.md, UE_RENDERER.md §3.1).

``apply`` switches a scene to what the profile describes and writes a receipt holding EVERY original value it changed;
``revert`` sets them back in reverse order and deletes what apply created, so apply + revert leaves the file as it was
(T-LOOK-04 dumps every touched datablock and compares the bytes). Nothing is changed before every refusal has been checked.

What apply changes: the view's exposure (log2 k + Bias - EV100, COL-08), curves and white balance off (UE's grading lives in
the cube, COL-12/13), EEVEE fast GI and screen tracing as the profile's GI and reflection methods say (all off for parity,
LGT-09/10), anisotropic filtering from r.MaxAnisotropy (TEX-03), dither 0 for parity (COL-07), soft falloff off on point and
spot lights (LGT-04), and every material slot in scope swapped to its '<name> [UE]' preview (the UE Default Lit group,
culling = not Two Sided), and the view transform to the UE view. The light values UE needs (k-scaled lux and candela, cones,
radii) and the cube's path, sha256 and engine version go into the receipt. The view needs the profile's cube, generated on the
UE side and validated against its sidecar (``cube``); without a valid cube apply is refused with the fix (docs/ue-look.md)."""

import json
from pathlib import Path

import bpy

from .. import settings as S
from . import cube as CB
from . import lights as LM
from . import material_group as MG
from . import material_map as MM
from . import ocio_view as OV
from . import profile as PR

STATE_KEY = "lampway_ue_look"
RECEIPT_SCHEMA = "lampway.ue-look-receipt/1"
_ANISO = ((16, "FILTER_16"), (8, "FILTER_8"), (4, "FILTER_4"), (2, "FILTER_2"), (0, "FILTER_0"))


class LookError(ValueError):
    pass


def data_dir() -> Path:
    return S.lampway_home() / "ue_look"


def _resolve(ref):
    coll, name, path = ref
    target = getattr(bpy.data, coll)[name]
    for part in filter(None, path.split(".")):
        target = getattr(target, part)
    return target


class _Changes:
    """Set RNA values and remember the originals; ``undo`` restores them in reverse order."""

    def __init__(self):
        self.rows = []

    def set(self, coll, name, path, attr, value):
        target = _resolve((coll, name, path))
        old = getattr(target, attr)
        self.rows.append({"ref": [coll, name, path], "attr": attr, "value": list(old) if hasattr(old, "__len__") and not isinstance(old, str) else old})
        setattr(target, attr, value)


def undo(rows):
    for row in reversed(rows):
        setattr(_resolve(row["ref"]), row["attr"], row["value"])


def _classes(profile):
    return {"COL": "unmeasured", "SHD": "unmeasured", "NRM": "unmeasured",
            "LGT": "unmeasured", "TEX": "not_previewed" if profile["preview"]["texture_compression"] == "source" else "unmeasured",
            "GEO": "gate", "PST": "not_attempted", "ANM": "not_attempted", "CFG": "unmeasured", "CMP": "not_attempted"}


def _objects(scene, scope):
    if scope == "scene":
        return list(scene.objects)
    if scope == "selected":
        return [o for o in scene.objects if o.select_get()]
    raise LookError("scope is scene or selected")


def _light_dict(ld):
    d = {"type": ld.type, "energy": ld.energy, "exposure": getattr(ld, "exposure", 0.0), "use_temperature": bool(getattr(ld, "use_temperature", False))}
    if ld.type == "SUN":
        d["angle_rad"] = ld.angle
    if ld.type in ("POINT", "SPOT"):
        d["radius_m"] = ld.shadow_soft_size
    if ld.type == "SPOT":
        d.update(spot_size_rad=ld.spot_size, spot_blend=ld.spot_blend)
    return d


def check(scene, profile, scope="scene", parity=False):
    """Every refusal of apply, without changing anything. Returns the objects in scope, their light map and the cube's check."""
    active = scene.get(STATE_KEY)
    if active:
        raise LookError(f"the scene is already in a UE look: revert receipt {active} first")
    if profile["tonemap"]["method"] != "Filmic":
        raise LookError("Standard ACES is not replicated yet: judge in UE, or set the volume to Filmic")
    if profile["project"]["working_color_space"] != "sRGB":
        raise LookError(f"the working colour space is {profile['project']['working_color_space']}: regenerate the profile after M-CFG-01 adds this space")
    if parity and profile["exposure"]["method"] != "manual":
        raise LookError("auto exposure adapts per frame: set the volume to Manual for a parity render")
    if parity and profile["source"] == "engine-defaults":
        raise LookError("engine defaults are not the Titan project: run the UE editor leg's profile dump")
    try:
        cube = CB.require(profile)
    except CB.CubeError as exc:
        raise LookError(str(exc)) from None
    obs = _objects(scene, scope)
    k = profile["light_units"]["k"]
    lights = []
    for o in obs:
        if o.type == "LIGHT":
            try:
                lights.append({"name": o.name, "data": o.data.name, "from": _light_dict(o.data), "to": LM.ue_light(_light_dict(o.data), k)})
            except LM.LightMapError as exc:
                raise LookError(f"{o.name}: {exc}") from None
    return obs, lights, cube


def _change(scene, profile, view, obs, lights, parity, rec):
    """Every scene change of apply, each recorded into ``rec`` as it is made (so a failure can be undone)."""
    ch = _Changes()
    ch.rows = rec["changes"]
    sn = scene.name
    cv = profile["project"]["cvars"]
    ch.set("scenes", sn, "view_settings", "view_transform", view["view_name"])
    ch.set("scenes", sn, "view_settings", "look", "None")
    ch.set("scenes", sn, "view_settings", "exposure", PR.exposure_stops(profile))
    ch.set("scenes", sn, "view_settings", "use_curve_mapping", False)
    ch.set("scenes", sn, "view_settings", "use_white_balance", False)
    gi_on = cv["r.DynamicGlobalIlluminationMethod"] != 0 and not parity
    refl_on = cv["r.ReflectionMethod"] != 0 and not parity
    ch.set("scenes", sn, "eevee", "use_fast_gi", gi_on)
    ch.set("scenes", sn, "eevee", "use_raytracing", refl_on)
    if refl_on:
        ch.set("scenes", sn, "eevee", "ray_tracing_method", "SCREEN")
    ch.set("scenes", sn, "render", "anisotropic_filter", next(e for n, e in _ANISO if cv["r.MaxAnisotropy"] >= n))
    if parity:
        ch.set("scenes", sn, "render", "dither_intensity", 0.0)
    for name in sorted({l["data"] for l in lights}):
        if bpy.data.lights[name].type in ("POINT", "SPOT"):
            ch.set("lights", name, "", "use_soft_falloff", False)
    if bpy.data.node_groups.get(MM.GROUP_NAME) is None:
        rec["created"]["node_group"] = MM.GROUP_NAME
    previews = {}
    for o in obs:
        for i, slot in enumerate(o.material_slots):
            m = slot.material
            if m is None or m.name in previews.values():
                continue
            if m.name not in previews:
                try:
                    tr = MM.translate(MG.read_spec(m), profile, mode="preview")
                except MM.TranslationError as exc:
                    previews[m.name] = None
                    rec["materials"].append({"name": m.name, "translated": False, "why": str(exc)})
                else:
                    previews[m.name] = MG.build_preview(m, tr).name
                    rec["created"]["materials"].append(previews[m.name])
                    rec["materials"].append({"name": m.name, "translated": True, "preview": previews[m.name], "two_sided": tr["ue"]["two_sided"],
                                             "blend_mode": tr["ue"]["blend_mode"], "dropped": tr["dropped"], "clamped": tr["clamped"],
                                             "translation_sha256": tr["translation_sha256"]})
            if previews[m.name]:
                rec["swaps"].append({"object": o.name, "slot": i, "material": m.name})
                slot.material = bpy.data.materials[previews[m.name]]


def _restore(r):
    """Undo a receipt's (or a partial apply's) swaps and values, then delete what it created."""
    for s in reversed(r["swaps"]):
        bpy.data.objects[s["object"]].material_slots[s["slot"]].material = bpy.data.materials[s["material"]]
    undo(r["changes"])
    for name in r["created"]["materials"]:
        m = bpy.data.materials.get(name)
        if m is not None:
            bpy.data.materials.remove(m)
    g = r["created"]["node_group"] and bpy.data.node_groups.get(r["created"]["node_group"])
    if g and g.users == 0:
        bpy.data.node_groups.remove(g)


def load_profile(profile_path=None, cube=None, meta=None):
    """The profile, with the panel's cube and sidecar pickers (when given) in place of its own paths."""
    path = Path(profile_path) if profile_path else PR.DEFAULT_PROFILE
    profile = PR.load(path)
    if cube:
        profile["tonemap_cube"] = str(Path(cube).resolve())
    if meta:
        profile["tonemap_cube_meta"] = str(Path(meta).resolve())
    return path, PR.validate(profile)


def apply(scene, profile_path=None, scope="scene", parity=False, cube=None, meta=None) -> dict:
    path, profile = load_profile(profile_path, cube, meta)
    obs, lights, cube_check = check(scene, profile, scope, parity)
    sha = PR.sha256(profile)
    view = OV.view_for(profile, cube_check)
    rec = {"changes": [], "swaps": [], "created": {"materials": [], "node_group": None}, "materials": []}
    try:
        _change(scene, profile, view, obs, lights, parity, rec)
    except Exception:
        _restore(rec)                                                       # a failure part-way leaves the scene as it was
        raise
    exposure = PR.exposure_stops(profile)
    sn = scene.name
    materials = rec["materials"]

    receipts = data_dir() / sha[:8] / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    rp = receipts / f"{sn}-{len(list(receipts.iterdir())) + 1:04d}.json"
    receipt = {"schema": RECEIPT_SCHEMA, "scene": sn, "profile_path": str(path), "profile_sha256": sha, "profile_source": profile["source"],
               "parity": bool(parity), "scope": scope, "exposure_stops": exposure, "view": view, "changes": rec["changes"], "swaps": rec["swaps"],
               "created": rec["created"],
               "lights": lights, "materials": materials, "classes": _classes(profile), "cube": CB.receipt(cube_check)}
    rp.write_text(json.dumps(receipt, indent=1, default=str), encoding="utf-8")
    scene[STATE_KEY] = str(rp)
    return {"receipt_path": str(rp), "profile_sha256": sha, "view_name": view.get("view_name"), "view": view, "exposure_stops": exposure,
            "lights": lights, "materials": materials, "classes": receipt["classes"], "parity": bool(parity), "cube": receipt["cube"]}


def status(scene) -> dict:
    rp = scene.get(STATE_KEY)
    if not rp or not Path(rp).is_file():
        return {"active": False, "profile_sha256": None, "view_name": None, "view_present": None, "classes": None}
    r = json.loads(Path(rp).read_text(encoding="utf-8"))
    name = r["view"].get("view_name")
    return {"active": True, "receipt_path": rp, "profile_sha256": r["profile_sha256"], "view_name": name,
            "view_present": OV.view_present(name) if name else None, "classes": r["classes"], "parity": r["parity"], "cube": r.get("cube")}


def revert(scene, receipt_path=None) -> dict:
    rp = receipt_path or scene.get(STATE_KEY)
    if not rp:
        raise LookError("the scene is not in a UE look and no receipt was given")
    r = json.loads(Path(rp).read_text(encoding="utf-8"))
    if r.get("schema") != RECEIPT_SCHEMA or r["scene"] != scene.name:
        raise LookError(f"{rp} is not a UE look receipt for scene {scene.name}")
    _restore(r)
    if scene.get(STATE_KEY) == rp:
        del scene[STATE_KEY]
    return {"reverted": rp, "restored": len(r["changes"]) + len(r["swaps"]), "deleted": r["created"]["materials"]}
