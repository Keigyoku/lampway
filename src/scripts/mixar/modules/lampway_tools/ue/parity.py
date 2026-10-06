# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""ue_parity, the Lampway half (specs/ue_parity/contracts/ue_parity.md): build a standard scene from its description, render it
headless in EEVEE under ``ue_look`` with parity=true to float EXR per view, and write report.json / report.md. The UE half
(the editor leg's SceneCapture2D, SCS_SCENE_COLOR_HDR) is ``needs_box`` until the captain schedules box time; when its EXRs
exist (``ue_captures``: ue_<view>.exr), the same report compares them per class with ``parity_metrics``.

UE's linear capture is k-scaled (lights and emissive go out multiplied by the profile's k), so it is divided by k before the
comparison unless ``ue_linear_scale`` says otherwise; UE's scene-colour pre-exposure (CMP-02) is unmeasured, so that scale is
recorded in the report as an assumption, not a fact."""

import hashlib
import json
from pathlib import Path

import bpy
import numpy as np

from . import look as LK
from . import parity_metrics as PM
from . import parity_scene as PS
from . import profile as PR

SCHEMA = "lampway.ue-parity/1"
CLASSES = ("COL", "SHD", "NRM", "LGT", "GEO", "PST", "TEX")
NEEDS_BOX = ("the UE half captures through the UE editor leg (contracts/ue_editor_leg.md) on a build box: no box time is approved; "
             "pass ue_captures=<dir with ue_<view>.exr> when the captures exist")


class ParityError(ValueError):
    pass


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def parity_refusals(profile):
    """A profile the parity scenes cannot be compared under (§4): engine defaults, auto exposure, and every effect left on."""
    if profile["source"] == "engine-defaults":
        raise ParityError("engine defaults are not the Titan project: run the UE editor leg's profile dump")
    cv, post, ex = profile["project"]["cvars"], profile["post"], profile["exposure"]
    on = [n for n, v in (("auto exposure", ex["method"] != "manual"), ("dynamic GI", cv["r.DynamicGlobalIlluminationMethod"] != 0),
                         ("reflections", cv["r.ReflectionMethod"] != 0), ("SSAO", post["ssao"] != 0), ("bloom", post["bloom"] != 0),
                         ("vignette", post["vignette"] != 0), ("local exposure", any(v != 1 for v in post["local_exposure"].values()))) if v]
    if on:
        raise ParityError(f"parity scenes compare with these off: {', '.join(on)}; the profile for the parity scene sets them off "
                          "(the look profile keeps them)")


def _load_exr(path):
    from .. import canon_io
    img = canon_io.load_image(str(path), check_existing=False)
    try:
        w, h = img.size
        return np.array(img.pixels[:], dtype=np.float64).reshape(h, w, 4)[::-1].copy()
    finally:
        bpy.data.images.remove(img)


def run(scene, profile_path, size, views, out_dir, ue_captures, ue_linear_scale, root) -> dict:
    profile = PR.load(profile_path or PR.DEFAULT_PROFILE)
    parity_refusals(profile)
    if scene.startswith("armour:"):
        d = Path(root) / scene.split(":", 1)[1]
        if not (d / "export.json").is_file():
            raise ParityError(f"{scene}: the armour scene names an asset without an ue_export receipt ({d / 'export.json'} is missing)")
        raise ParityError("the armour scene's Lampway half (the exported piece on the fit_body package, key + fill + sky) is not built in this pass")
    out = Path(root) / out_dir
    if out.exists():
        raise ParityError(f"{out_dir} exists: a parity run never reuses a directory")
    desc = PS.describe(scene, size, tuple(views))
    out.mkdir(parents=True)
    (out / "scene.json").write_text(json.dumps(desc, indent=1), encoding="utf-8")
    k = profile["light_units"]["k"]
    scale = (1.0 / k) if ue_linear_scale is None else float(ue_linear_scale)
    caps = Path(root) / ue_captures if ue_captures and not Path(ue_captures).is_absolute() else (Path(ue_captures) if ue_captures else None)
    rep_views = {}
    for view in views:
        sc = PS.build(desc, view)
        try:
            ap = LK.apply(sc, profile_path, "scene", True)
            try:
                exr = out / f"lampway_{view}.exr"
                sc.render.image_settings.file_format = "OPEN_EXR"
                sc.render.image_settings.color_depth = "32"
                sc.render.filepath = str(exr)
                bpy.ops.render.render(write_still=True, scene=sc.name)
            finally:
                LK.revert(sc, ap["receipt_path"])
        finally:
            PS.discard(sc)
        PM.check_capture(exr, linear=True)
        row = {"lampway": {"exr": str(exr), "sha256": _sha(exr)}, "look_receipt": ap["receipt_path"], "cube": ap["cube"]}
        cap = None
        if caps is not None:
            cap = next(iter(sorted(caps.glob(f"ue_{view}.*"))), None)
        if cap is None:
            row["ue"] = {"state": "needs_box", "why": NEEDS_BOX}
            row["classes"] = {c: "needs_box" for c in CLASSES}
        else:
            PM.check_capture(cap, linear=True)
            ue = _load_exr(cap)
            ue[..., :3] *= scale
            res = PM.compare(_load_exr(exr), ue, desc["regions"][view], display=None)
            row["ue"] = {"state": "captured", "exr": str(cap), "sha256": _sha(cap), "linear_scale": scale,
                         "linear_scale_basis": "1/k: UE lights and emissive are k-scaled; UE scene-colour pre-exposure (CMP-02) unmeasured"}
            row["classes"] = {c: r["verdict"] for c, r in res["classes"].items()}
            row["metrics"] = res["classes"]
        rep_views[view] = row
    rep = {"schema": SCHEMA, "scene": scene, "scene_sha256": PS.scene_sha256(desc), "size": size,
           "versions": {"blender": bpy.app.version_string, "ue": profile["engine"]["version"], "ue_changelist": profile["engine"]["changelist"]},
           "profile_path": str(profile_path), "profile_sha256": PR.sha256(profile), "tolerances": PM.TOLERANCES, "views": rep_views,
           "renderer": "EEVEE, headless, film transparent, float EXR; ue_look parity=true"}
    (out / "report.json").write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    lines = [f"# UE parity: {scene}", "", f"Blender {rep['versions']['blender']}, UE {rep['versions']['ue']} (CL {rep['versions']['ue_changelist']}), "
             f"profile {rep['profile_sha256'][:12]}, scene {rep['scene_sha256'][:12]}.", "", "| view | " + " | ".join(CLASSES) + " |",
             "|---|" + "---|" * len(CLASSES)] + [f"| {v} | " + " | ".join(r["classes"].get(c, "") for c in CLASSES) + " |" for v, r in rep_views.items()]
    if any(r["ue"]["state"] == "needs_box" for r in rep_views.values()):
        lines += ["", "UE half: needs_box. " + NEEDS_BOX]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"out_dir": str(out), "classes": {v: r["classes"] for v, r in rep_views.items()}}
