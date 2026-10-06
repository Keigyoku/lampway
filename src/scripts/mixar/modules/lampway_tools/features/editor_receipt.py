# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""editor_connection_receipt: prove an assistant-to-editor connection with a typed receipt before any agent mutates a project
(specs/wiki/editor_connection_receipt.md).

Blender (native, in this process: the bridge's execute_script lands here): the version, the open file (it must be saved under the project root: an
uncertain identity stops before any mutation), the scene, the objects, then a disposable test: ``TestConnectionCube`` made at ``position``, seen, removed
with its mesh, and the object list compared with the one before. Unity and Godot: the agent reads its own MCP connection and passes the facts; they are
validated and stored (no engine code here). Unreal: the UE editor leg is needs_decision until the Blender-to-UE render parity exploration settles it.
Receipts: <root>/receipts/editor_connection_<editor>_<time>.json."""

import json
import os
import time

import bmesh
import bpy

from . import common as C

EDITORS = ("blender", "unity", "godot", "unreal")
TRANSPORTS = ("bridge", "mcp_stdio", "mcp_http", "other")
FACTS = ("editor_version", "connector_release", "project_path", "scene", "read_tool", "undo_outcome")
CUBE = "TestConnectionCube"


def _save(root, editor, receipt):
    d = os.path.join(root, "receipts")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"editor_connection_{editor}_{time.strftime('%Y%m%dT%H%M%S')}_{int(time.time() * 1000) % 1000:03d}.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=1)
    return os.path.relpath(p, root)


def _blender(root, position, transport, release):
    path = bpy.data.filepath
    real_root = os.path.realpath(root)
    if not path or not (os.path.realpath(path) + os.sep).startswith(real_root + os.sep):
        raise C.FeatureError(f"uncertain project identity: the open file {path or '(unsaved)'} is not a saved copy under the project root {root}; save the disposable "
                             "copy there first (nothing was changed)")
    sc = bpy.context.scene
    before = sorted(o.name for o in bpy.data.objects)
    if CUBE in bpy.data.objects:
        raise C.FeatureError(f"an object named {CUBE} exists already: the test needs a clean name")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=0.2)
    me = bpy.data.meshes.new(CUBE)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(CUBE, me)
    ob.location = [float(x) for x in position]
    sc.collection.objects.link(ob)
    bpy.context.view_layer.update()
    created = CUBE in sc.objects and [round(x, 6) for x in ob.matrix_world.translation] == [round(float(x), 6) for x in position]
    loc = [round(x, 6) for x in ob.matrix_world.translation]
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)
    after = sorted(o.name for o in bpy.data.objects)
    undone = CUBE not in bpy.data.objects and CUBE not in bpy.data.meshes
    return {"editor": "blender", "editor_version": bpy.app.version_string, "connector_release": release, "transport": transport,
            "project_path": os.path.relpath(os.path.realpath(path), real_root), "scene": sc.name, "objects_before": before[:3], "object_count_before": len(before),
            "test": {"created": bool(created), "name": CUBE, "location": loc, "undone": bool(undone), "objects_after_equal_before": after == before}}


def editor_connection_receipt(root, editor="blender", disposable=False, position=(0, 0, 0), transport="bridge", release="", facts=None):
    if editor not in EDITORS:
        raise C.FeatureError(f"editor is {' | '.join(EDITORS)}")
    if transport not in TRANSPORTS:
        raise C.FeatureError(f"transport is {' | '.join(TRANSPORTS)}")
    if disposable is not True:
        raise C.FeatureError("the create-undo test runs in a disposable copy only: duplicate the project, open the copy, then pass disposable=true")
    if editor == "unreal":
        return {"editor": "unreal", "state": "needs_decision",
                "reason": "the UE editor leg waits on the Blender-to-UE render parity exploration: no Unreal receipt is recorded or validated yet"}
    if editor == "blender":
        rec = _blender(root, position, transport, release or "")
    else:
        f = facts if isinstance(facts, dict) else {}
        missing = [k for k in FACTS if not str(f.get(k) or "").strip()]
        if missing:
            raise C.FeatureError(f"not connected: start {editor}'s MCP connector, read the project through it, run the disposable create/undo, and pass the facts "
                                 f"(missing: {', '.join(missing)})")
        rec = {"editor": editor, "transport": transport, **{k: str(f[k]) for k in FACTS}, "source": "the agent's own MCP connection (facts as reported)"}
    rec["when"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    rec["receipt_path"] = _save(root, editor, rec)
    return rec
