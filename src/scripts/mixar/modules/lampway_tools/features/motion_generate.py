# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""motion_generate, the Blender layer (specs/resources/motion_generate.md): index a folder of owned clips into <library>/index.json, and import the clip the
ranker (pipeline/motion_library.py) picks: the file is imported, its armature renamed ``motion_src`` (a previous one this tool made is replaced) and its
action named after the clip; frames and fps are read back from the imported action and the scene. Every pick appends one typed row to
<root>/motion/decisions.jsonl. The model engines answer needs_provider; there is never a silent fallback to the library."""

import json
import os

import bpy

from ..meshqa import decisions as D
from ..pipeline import motion_library as ML
from .. import canon_io
from . import common as C
from .. import canon_io

CLIP_EXT = (".fbx", ".glb", ".gltf", ".bvh")
ARMATURE = "motion_src"


def _index_path(lib):
    return os.path.join(lib, "index.json")


def index(root, lib):
    if not os.path.isdir(lib):
        raise C.FeatureError(f"no library folder {os.path.relpath(lib, root)} under the project root")
    found = [(os.path.splitext(f)[0], os.path.relpath(os.path.join(lib, f), root)) for f in sorted(os.listdir(lib)) if f.lower().endswith(CLIP_EXT)]
    p = _index_path(lib)
    existing = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else []
    rows = ML.index_rows(found, existing)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=1)
    return {"clips": rows, "index": os.path.relpath(p, root), "note": "tag the clips in index.json (the captain's words rank first with the names)"}


def _import(path):
    before = set(bpy.data.objects.keys())
    ext = os.path.splitext(path)[1].lower()
    # a raw clip enters the scene with its own frame and bone names, through canon_io (stamped raw)
    if ext == ".fbx":
        canon_io.import_raw(path, use_anim=True)
    else:
        canon_io.import_raw(path)
    return [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in before]


@canon_io.rollback_imports
def generate(root, prompt, lib, duration=3.0):
    p = _index_path(lib)
    if not os.path.exists(p):
        raise C.FeatureError(f"no clip index at {os.path.relpath(p, root)}: run motion_generate action=index first")
    rows = json.load(open(p, encoding="utf-8"))
    best, ranked = ML.pick(prompt, rows, duration)
    full = os.path.join(root, best["file"])
    if not os.path.isfile(full):
        raise C.FeatureError(f"the index names {best['file']}, which is missing: run action=index again")
    new = _import(full)
    arm = next((o for o in new if o.type == "ARMATURE"), None)
    if arm is None:
        for o in new:
            bpy.data.objects.remove(o)
        raise C.FeatureError(f"{best['file']} holds no armature: a clip is an armature with an action")
    arm.name = ARMATURE
    arm["lw_motion_generate"] = best["name"]
    act = arm.animation_data.action if arm.animation_data else None
    if act is None:
        raise C.FeatureError(f"{best['file']} has no action on its armature")
    old = bpy.data.objects.get(ARMATURE)
    if old is not None and old.get("lw_motion_generate"):
        for child in list(old.children):
            bpy.data.objects.remove(child)
        bpy.data.objects.remove(old)
    act.name = best["name"]
    f0, f1 = act.frame_range
    sc = bpy.context.scene
    fps = sc.render.fps / sc.render.fps_base
    row = ML.decision_row(prompt, ranked, best["name"], os.path.relpath(lib, root))
    D.append_rows(os.path.join(root, "motion", "decisions.jsonl"), [row])
    return {"engine": "library", "clip": {"name": best["name"], "file": best["file"], "frames": int(round(f1 - f0)) + 1, "fps": int(round(fps)),
            "score": best["score"]}, "armature": arm.name, "action": act.name,
            "alternatives": [{"name": r["name"], "score": r["score"]} for r in ranked[1:4]], "decisions": "motion/decisions.jsonl"}
