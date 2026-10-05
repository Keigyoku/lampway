# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_body: the body for fitting, as one hashed package directory every fit tool names (`body=<package dir>`).

build writes ``<out>/<sha8>/``: ``joints.json`` (parents before children, the armature's head, tail and rest axes in metres, Blender frame), ``body.npz`` (V, T of the body mesh when one is given), the
optional ``body.glb`` and ``sidecar.json`` (the NATIVE weights, copied from a file the user's UE editor leg produced), and ``receipt.json`` with the sha256 of every file and the conventions. verify
recomputes every hash. Only the project-native body is accepted (never a GLB copy for weights); the UE editor leg (the sidecar and helpers scripts of the user's project) is not run from here."""

import hashlib
import json
import shutil
from pathlib import Path

import bpy
import numpy as np

from . import common as C

NATIVE_PREFIX = "/Game/MetaHumans/"
NATIVE_DEFAULT = "/Game/MetaHumans/NewMetaHumanCharacter_FullBody"
CONVENTIONS = {"joints": "metres, Blender frame (Z up), head/tail/axes in armature space", "ue": "UE asset/component space is Z up, left-handed, centimetres (not converted here)"}


def _sha(p):
    h = hashlib.sha256()
    h.update(Path(p).read_bytes())
    return h.hexdigest()


def _joints(arm_ob):
    bones = list(arm_ob.data.bones)
    depth = {}
    def d(b):
        if b.name not in depth:
            depth[b.name] = 0 if b.parent is None else d(b.parent) + 1
        return depth[b.name]
    for b in bones:
        d(b)
    order = sorted(bones, key=lambda b: (depth[b.name], bones.index(b)))
    # parents before children, keeping the armature's own order within a depth
    out = []
    for b in order:
        m = (arm_ob.matrix_world @ b.matrix_local)
        rot = m.to_3x3()
        out.append({"name": b.name, "parent": b.parent.name if b.parent else None, "head": [round(x, 6) for x in (arm_ob.matrix_world @ b.head_local)[:]],
                    "tail": [round(x, 6) for x in (arm_ob.matrix_world @ b.tail_local)[:]],
                    "axes": {"x": [round(x, 6) for x in rot.col[0]], "y": [round(x, 6) for x in rot.col[1]], "z": [round(x, 6) for x in rot.col[2]]}})
    return out


def build(armature, mesh, glb, native_asset, uproject, sidecar, out, root):
    if native_asset and not str(native_asset).startswith(NATIVE_PREFIX):
        raise C.FeatureError(f"fit only against the project-native body ({NATIVE_PREFIX}...): {native_asset} is not under it")
    if uproject:
        raise C.FeatureError("the editor leg (the sidecar and helpers scripts run in the user's UE editor) is not run from here: run it on the user's box and pass sidecar=<the file it wrote>")
    if not armature:
        raise C.FeatureError("name the armature object whose bones are the body's joints")
    arm = C.need_object(armature, "ARMATURE")
    joints = _joints(arm)
    files = {}
    tmp = Path(root) / (out or "fit/body") / ".build"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    (tmp / "joints.json").write_text(json.dumps({"units": "m", "frame": "blender", "joints": joints}, indent=1))
    verts = 0
    if mesh:
        ob = C.need_object(mesh)
        bpy.context.view_layer.update()
        ob.data.calc_loop_triangles()
        V = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
        T = np.array([t.vertices[:] for t in ob.data.loop_triangles])
        np.savez(tmp / "body.npz", V=V, T=T, names=np.array([j["name"] for j in joints]), J=np.array([j["head"] for j in joints]))
        verts = len(V)
    if glb:
        src = Path(root) / glb if not Path(glb).is_absolute() else Path(glb)
        if not src.exists():
            raise C.FeatureError(f"{glb} not found")
        shutil.copy(src, tmp / "body.glb")
    sidecar_vertices = 0
    if sidecar:
        src = Path(root) / sidecar if not Path(sidecar).is_absolute() else Path(sidecar)
        data = json.loads(src.read_text())
        sidecar_vertices = int(len(data.get("vertices", data.get("rest_positions", []))))
        shutil.copy(src, tmp / "sidecar.json")
    for f in sorted(tmp.iterdir()):
        files[f.name] = _sha(f)
    pkg_sha = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    receipt = {"package_sha256": pkg_sha, "files": files, "joints": len(joints), "vertices": verts, "sidecar_vertices": sidecar_vertices, "native_asset": native_asset or NATIVE_DEFAULT,
               "conventions": CONVENTIONS, "weights": "native sidecar" if sidecar else "none: weights come from the native asset (pass sidecar=)"}
    (tmp / "receipt.json").write_text(json.dumps(receipt, indent=1))
    final = Path(root) / (out or "fit/body") / pkg_sha[:8]
    if final.exists():
        shutil.rmtree(tmp)
    else:
        tmp.rename(final)
    return {"ok": True, "package": str(final), "joints": len(joints), "vertices": verts, "sidecar_vertices": sidecar_vertices, "package_sha256": pkg_sha}


def verify(package):
    pkg = Path(package)
    rp = pkg / "receipt.json"
    if not rp.exists():
        raise C.FeatureError(f"{package} is not a body package (no receipt.json)")
    receipt = json.loads(rp.read_text())
    bad = [n for n, h in receipt["files"].items() if not (pkg / n).exists() or _sha(pkg / n) != h]
    if bad:
        raise C.FeatureError(f"the body asset changed: rebuild the package (these files no longer match their hash: {bad})")
    return {"ok": True, "package": str(pkg), "files": len(receipt["files"]), "joints": receipt["joints"], "package_sha256": receipt["package_sha256"]}


def need_weights(package):
    pkg = Path(package)
    if not (pkg / "sidecar.json").exists():
        raise C.FeatureError("weights come from the native asset: run `build` with the editor leg on the user's box, or pass sidecar=<existing> (a GLB body carries only the first 4 influences)")
    return verify(package)
