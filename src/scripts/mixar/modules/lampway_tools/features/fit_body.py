# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_body: the body for fitting, as one hashed package directory every fit tool names (`body=<package dir>`).

build writes ``<out>/<sha8>/``: ``joints.json`` (parents before children, the armature's head, tail and rest axes in metres, Blender frame), ``body.npz`` (V, T of the body mesh when one is given), the
optional ``body.glb`` and ``sidecar.json`` (the NATIVE weights, copied from a file the user's UE editor leg produced), and ``receipt.json`` with the sha256 of every file and the conventions. verify
recomputes every hash. Only the project-native body is accepted (never a GLB copy for weights); the UE editor leg (the sidecar and helpers scripts of the user's project) is not run from here.

The sidecar is READ at build (features/native_sidecar: titan.native-weight-sidecar/1, the engine's weights): a file that is not the
engine's weights, or one weighted to a bone the package's skeleton lacks, is refused before anything is written; the receipt records
its summary. The receipt also records the body mesh's state for the fit order (canon 03 G): ``closed`` on position-welded analysis topology and
``head_included`` by generalized winding number > 0.5, including native facial openings.
Authored source vertices and native weight identities are never welded in the package."""

import hashlib
import json
import shutil
from pathlib import Path

import bpy
import numpy as np

from . import common as C
from . import native_sidecar as NS
from .. import canon_geom as G

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



def _topology_counts(T):
    T = np.asarray(T, int).reshape(-1, 3)
    edges = np.sort(np.concatenate((T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]])), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int((counts == 1).sum()), int((counts > 2).sum())


def body_state(V, T, head):
    """Analyze seam identities only; preserve source arrays for native weights.

    Canon 01 D's 1e-5m positional identity joins UV-split render vertices for
    topology measurement. Jacobson's generalized winding tolerates native
    openings without pretending they are closed or inventing a cap.
    """
    raw_boundary, raw_nonmanifold = _topology_counts(T)
    welded = G.weld_keys(V, tol=1e-5)[T]
    boundary, nonmanifold = _topology_counts(welded)
    winding = float(G.winding_numbers(V, T, np.array([head["head"]]))[0]) if head is not None else None
    included = winding is not None and winding > 0.5
    return {"closed": boundary == 0, "boundary_edges": boundary, "non_manifold_edges": nonmanifold,
            "raw_boundary_edges": raw_boundary, "raw_non_manifold_edges": raw_nonmanifold,
            "topology_weld_m": 1e-5, "head_included": included, "head_joint": head and head["name"],
            "head_winding": winding, "inside_method": "generalized_winding_number",
            "native_openings_accepted": boundary > 0 and included}


def build(armature, mesh, glb, native_asset, uproject, sidecar, out, root):
    if native_asset and not str(native_asset).startswith(NATIVE_PREFIX):
        raise C.FeatureError(f"fit only against the project-native body ({NATIVE_PREFIX}...): {native_asset} is not under it")
    if uproject:
        raise C.FeatureError("the editor leg (the sidecar and helpers scripts run in the user's UE editor) is not run from here: run it on the user's box and pass sidecar=<the file it wrote>")
    if not armature:
        raise C.FeatureError("name the armature object whose bones are the body's joints")
    arm = C.need_object(armature, "ARMATURE")
    joints = _joints(arm)
    side = None
    if sidecar:
        sidecar_src = Path(root) / sidecar if not Path(sidecar).is_absolute() else Path(sidecar)
        try:
            side = NS.read(str(sidecar_src))
        except NS.SidecarError as e:
            raise C.FeatureError(f"the sidecar is refused: {e}")
        have = {j["name"] for j in joints}
        foreign = [side.names[j] for j in range(len(side.names)) if side.W[:, j].any() and side.names[j] not in have]
        if foreign:
            raise C.FeatureError(f"the sidecar weights bones the package's skeleton ({armature}) does not have: {foreign[:10]} - "
                                 "the armature must be the native skeleton")
    files = {}
    tmp = Path(root) / (out or "fit/body") / ".build"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    (tmp / "joints.json").write_text(json.dumps({"units": "m", "frame": "blender", "joints": joints}, indent=1))
    verts = 0
    state = {"closed": None, "boundary_edges": None, "head_included": None, "head_joint": None}
    if mesh:
        ob = C.need_object(mesh)
        bpy.context.view_layer.update()
        ob.data.calc_loop_triangles()
        V = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
        T = np.array([t.vertices[:] for t in ob.data.loop_triangles])
        np.savez(tmp / "body.npz", V=V, T=T, names=np.array([j["name"] for j in joints]), J=np.array([j["head"] for j in joints]))
        verts = len(V)
        head = next((j for j in joints if j["name"] == "head"), None)
        state = body_state(V, T, head)
    if glb:
        src = Path(root) / glb if not Path(glb).is_absolute() else Path(glb)
        if not src.exists():
            raise C.FeatureError(f"{glb} not found")
        shutil.copy(src, tmp / "body.glb")
    sidecar_vertices = 0
    side_summary = None
    if side is not None:
        sidecar_vertices = int(len(side.ids))
        side_summary = {"schema": NS.SCHEMA, "vertices": sidecar_vertices, "triangles": int(len(side.T)), "bones": len(side.names),
                        "root_bone": side.root_bone, "dropped_triangles": side.dropped_triangles, "reoriented": side.reoriented}
        shutil.copy(sidecar_src, tmp / "sidecar.json")
    for f in sorted(tmp.iterdir()):
        files[f.name] = _sha(f)
    pkg_sha = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    receipt = {"package_sha256": pkg_sha, "files": files, "joints": len(joints), "vertices": verts, "sidecar_vertices": sidecar_vertices, "native_asset": native_asset or NATIVE_DEFAULT,
               "sidecar": side_summary, "body": state,
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
    return {"ok": True, "package": str(pkg), "files": len(receipt["files"]), "joints": receipt["joints"], "package_sha256": receipt["package_sha256"],
            "body": receipt.get("body"), "sidecar": "sidecar.json" in receipt["files"]}


def need_weights(package):
    pkg = Path(package)
    if not (pkg / "sidecar.json").exists():
        raise C.FeatureError("weights come from the native asset: run `build` with the editor leg on the user's box, or pass sidecar=<existing> (a GLB body carries only the first 4 influences)")
    return verify(package)
