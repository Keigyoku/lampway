# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""model_compare (specs/mrmak/05-model-compare.md): 2..4 models from different studios in one comparison: file statistics read without Blender, every model normalised into the same 2-unit box
in a scratch scene, interior-aware pair numbers, a blind alias and a user pick recorded as a typed decision.

NOT built here: the live windowed viewer (N synchronised 3D areas, the mode switch, camera sync). It needs the pop-out probe of section 6.4 (use_local_collections, hide_collection per area,
area_split under temp_override) and a display; until that probe has run, the numbers and statistics ship and the 3D view falls back to the flipbook of asset_ui_views.
Blind mode: aliases A..D are assigned by sorting the models' sha256 (the order carries no information); the real labels live only in compare.sealed.json (0600) until the user picks."""

import hashlib
import json
import math
import os
import time
import uuid
from pathlib import Path

import bmesh
import bpy

from .. import canon_io
import numpy as np

from .. import settings as S
from ..pipeline import glb_stats as GS
from . import common as C

SCRATCH_SCENE = "LW_Compare"
ALIASES = "ABCD"


def _set_dir(root, piece, set_id):
    return Path(root) / (piece or "compare") / "compare" / set_id


def _resolve(file, root):
    try:
        return str(S.resolve_in_root(file, root))
    except S.PathOutsideProject as exc:
        raise C.FeatureError(str(exc))


def _validate(models):
    if not isinstance(models, list) or len(models) < 2:
        raise C.FeatureError("compare needs two models: give 2 to 4 files (or objects)")
    if len(models) > 4:
        raise C.FeatureError("compare takes 2..4 models")
    for m in models:
        if not isinstance(m, dict):
            raise C.FeatureError(f'each model is an object {{"file": "a.glb"}} or {{"object": "Name"}} (with rotation_deg), not {m!r}')
        rot = float(m.get("rotation_deg") or 0.0)
        if not -180.0 <= rot <= 180.0:
            raise C.FeatureError("rotation_deg must be between -180 and 180")
        if not (m.get("file") or m.get("object")):
            raise C.FeatureError("each model needs a file or an object name")


def stats(models, root):
    out = []
    for m in models:
        if m.get("file"):
            out.append(GS.read_stats(_resolve(m["file"], root)))
        else:
            ob = C.need_object(m["object"])
            out.append({"file": ob.name, "triangles": sum(len(p.vertices) - 2 for p in ob.data.polygons), "vertices": len(ob.data.vertices), "materials": len(ob.data.materials),
                        "warnings": ["a scene object: file statistics (textures, channels) are not available"]})
    return out


def _scratch():
    sc = bpy.data.scenes.get(SCRATCH_SCENE) or bpy.data.scenes.new(SCRATCH_SCENE)
    return sc


def _import_merged(path, rotation_deg):
    """Import a glTF, return (vertices Nx3 world with yaw applied, triangles, name). The imported objects are removed; only geometry survives."""
    before = canon_io.snapshot_ids()
    bm = None
    try:
        canon_io.import_raw(path)
        meshes = [o for o in bpy.data.objects if o not in before["objects"] and o.type == "MESH"]
        if not meshes:
            raise C.FeatureError(f"{Path(path).name} holds no mesh")
        bm = bmesh.new()
        dg = bpy.context.evaluated_depsgraph_get()
        for o in meshes:
            evaluated = o.evaluated_get(dg)
            me = evaluated.to_mesh()
            try:
                me.transform(o.matrix_world)
                bm.from_mesh(me)
            finally:
                evaluated.to_mesh_clear()
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        verts = np.array([v.co[:] for v in bm.verts], float)
        bm.verts.index_update()
        tris = [[v.index for v in f.verts] for f in bm.faces]
        a = math.radians(float(rotation_deg))
        R = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
        return verts @ R.T, tris
    finally:
        if bm is not None:
            bm.free()
        canon_io.remove_new_ids(before)


def normalise(verts):
    """Scale the longest axis to 2.0 FIRST, then measure again and centre (centring before scaling leaves the box off the origin: the bug named at viewer.ts:265-269)."""
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    scale = 2.0 / max(float((hi - lo).max()), 1e-12)
    v = verts * scale
    lo, hi = v.min(axis=0), v.max(axis=0)
    return v - (lo + hi) / 2


def _make_object(name, verts, tris):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(t) for t in tris])
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    sc = _scratch()
    ob = bpy.data.objects.new(name, me)
    sc.collection.objects.link(ob)
    return ob


def _write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w") as fh:
        fh.write(json.dumps(data, indent=1, sort_keys=True))


def build(set_, blind, root):
    models = set_.get("models")
    _validate(models)
    sid = set_.get("id") if set_.get("id") not in (None, "", "auto") else uuid.uuid4().hex[:8]
    piece = set_.get("piece") or "compare"
    st = stats(models, root)
    for m, s in zip(models, st):
        if s.get("compressed") == "meshopt":
            raise C.FeatureError(f"{s['file']} needs the meshopt decoder: stats are shown, the 3D view is not (run action=stats)")
    order = sorted(range(len(models)), key=lambda i: (st[i].get("sha256") or "", i))
    alias = {i: ALIASES[k] for k, i in enumerate(order)} if blind else {i: (models[i].get("alias") or None) for i in range(len(models))}
    rows, sealed = [], []
    for i, m in enumerate(models):
        if m.get("file"):
            verts, tris = _import_merged(_resolve(m["file"], root), m.get("rotation_deg") or 0.0)
        else:
            ob = C.need_object(m["object"])
            dg = bpy.context.evaluated_depsgraph_get()
            me = ob.evaluated_get(dg).to_mesh()
            me.transform(ob.matrix_world)
            me.calc_loop_triangles()
            verts = np.array([v.co[:] for v in me.vertices], float)
            tris = [list(t.vertices) for t in me.loop_triangles]
            ob.evaluated_get(dg).to_mesh_clear()
        nv = normalise(verts)
        name = f"LWC_{sid}_{i}"
        for old in (bpy.data.objects.get(name),):
            if old is not None:
                bpy.data.objects.remove(old)
        _make_object(name, nv, tris)
        label = m.get("label") or st[i].get("file")
        row = {"index": i, "file": m.get("file"), "object": name, "sha256": st[i].get("sha256"), "alias": alias[i], "rotation_deg": m.get("rotation_deg") or 0.0, "note": m.get("note") if not blind else None,
               "accent": m.get("accent")}
        if blind:
            sealed.append({"index": i, "label": label})
        else:
            row["label"] = label
        rows.append(row)
    d = _set_dir(root, piece, sid)
    manifest = {"schema": "lampway.compare/v1", "id": sid, "piece": piece, "kind": set_.get("kind"), "default_mode": set_.get("default_mode"), "reference": set_.get("reference"),
                "blind": bool(blind), "models": rows}
    _write(d / "compare.json", manifest)
    if blind:
        _write(d / "compare.sealed.json", {"labels": sealed}, 0o600)
    return {"id": sid, "piece": piece, "set_dir": str(d), "blind": bool(blind), "models": rows, "stats": [{k: v for k, v in s.items() if k != "sha256"} | {"sha256": s.get("sha256")} for s in st]}


def _load(set_, root):
    piece = set_.get("piece") or "compare"
    p = _set_dir(root, piece, set_.get("id") or "")
    if not (p / "compare.json").exists():
        raise C.FeatureError(f"no compare set {set_.get('id')!r} for piece {piece!r}: build it first")
    return json.loads((p / "compare.json").read_text()), p


def numbers(set_, views, size, root):
    from . import silhouette as SIL
    man, d = _load(set_, root)
    objs = [m["object"] for m in man["models"]]
    missing = [o for o in objs if bpy.data.objects.get(o) is None]
    if missing:
        raise C.FeatureError(f"the scratch models {missing} are gone from this session: build the set again")
    pairs = []
    for i in range(len(objs)):
        for j in range(i + 1, len(objs)):
            r = SIL.run(objs[i], objs[j], root, f"{man['piece']}/compare_{man['id']}", views, size, 0.9, None, True)
            pairs.append({"a": i, "b": j, "views": r["views"], "worst_iou": r["worst_iou"], "worst_interior": max(v["interior_diff"] for v in r["views"])})
    out = {"id": man["id"], "pairs": pairs}
    _write(d / "numbers.json", out)
    return out


def reveal(set_, require_pick, root):
    man, d = _load(set_, root)
    if not man["blind"]:
        return {"id": man["id"], "models": man["models"]}
    picked = any(json.loads(l).get("question") == "model_pick" and json.loads(l).get("set") == man["id"] for l in _ledger_lines(root))
    if require_pick and not picked:
        raise C.FeatureError("reveal after the pick: this project requires the pick before the names are shown")
    sealed = {s["index"]: s["label"] for s in json.loads((d / "compare.sealed.json").read_text())["labels"]}
    return {"id": man["id"], "picked": picked, "models": [dict(m, label=sealed[m["index"]]) for m in man["models"]]}


def _ledger_lines(root):
    p = Path(root) / "ledger" / "runs.jsonl"
    return p.read_text().splitlines() if p.exists() else []


def record_pick(set_id, piece, model, how, note, by, root):
    """The user's pick as one typed decision row. Only the user (the Compare pick operator) calls this: an agent's pick is refused by the tool."""
    if by != "user":
        raise C.FeatureError("only the user picks: use the Compare pick button; an agent may never choose")
    man, _d = _load({"id": set_id, "piece": piece}, root)
    models = man["models"]
    if not 0 <= int(model) < len(models):
        raise C.FeatureError(f"model is 0..{len(models) - 1}")
    row = {"kind": "decision", "id": uuid.uuid4().hex, "t": time.time(), "question": "model_pick", "set": man["id"], "options": [m["sha256"] for m in models], "answer": models[int(model)]["sha256"],
           "by": "user", "how": how if how in ("blind", "named") else "named", "note": str(note or "")[:300]}
    p = Path(root) / "ledger" / "runs.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        try:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        except ImportError:
            pass
        fh.write(json.dumps(row) + "\n")
    return row


def run(action, set_=None, views=None, size=512, blind=False, pick=None, require_pick=False, root=""):
    set_ = set_ or {}
    if not isinstance(set_, dict):                    # audit F12: refused by name, never "'str' object has no attribute 'get'"
        raise C.FeatureError('set is an object: {"models": [{"file": "a.glb"}, {"file": "b.glb"}]} (each model a file under the root '
                             "or an object name), with id, piece and kind for build")
    if action == "stats":
        _validate(set_.get("models"))
        return {"stats": stats(set_["models"], root)}
    if action == "build":
        return build(set_, blind, root)
    if action == "numbers":
        if not 128 <= int(size) <= 1024:
            raise C.FeatureError("size is 128..1024")
        return numbers(set_, list(views or ["Front", "Left"]), int(size), root)
    if action == "reveal":
        return reveal(set_, require_pick, root)
    if action == "pick":
        raise C.FeatureError("only the user picks: use the Compare pick button; an agent may never choose")
    if action == "close":
        sc = bpy.data.scenes.get(SCRATCH_SCENE)
        if sc is not None:
            for o in list(sc.objects):
                if o.name.startswith("LWC_"):
                    data = o.data
                    bpy.data.objects.remove(o)
                    if data.users == 0:
                        bpy.data.meshes.remove(data)
            bpy.data.scenes.remove(sc)
        return {"closed": True}
    raise C.FeatureError("action is build | stats | numbers | reveal | pick | close")
