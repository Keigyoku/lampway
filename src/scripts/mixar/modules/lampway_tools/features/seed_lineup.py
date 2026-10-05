# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""seed_audit stage lineup: every seed of a piece rendered the same way, front and side, 420 px, Workbench (a LIGHT render: never Cycles, he works live while it runs), so the auditor and
the user compare seeds on one contact sheet. The mesh is built from the seed's npz in a throw-away object and removed afterwards (the scene is left as found)."""

import math
from pathlib import Path

import bpy
import numpy as np

from . import common as C
from . import render as R

SIZE = 420


def run(piece, seeds, root, turn=-90.0, engine="WORKBENCH", out_dir=""):
    if str(engine).upper() != "WORKBENCH":
        raise C.FeatureError("the lineup is a light render: Workbench only, never Cycles (he works live while it runs)")
    if not seeds or len(seeds) < 2:
        raise C.FeatureError("an audit ranks at least two seeds: ingest the variants first (seed_catalog ingest_variants)")
    out = Path(root) / (out_dir or f"{piece}/seed_audit")
    out.mkdir(parents=True, exist_ok=True)
    files = []
    th = math.radians(float(turn))
    rot = np.array([[math.cos(th), -math.sin(th), 0], [math.sin(th), math.cos(th), 0], [0, 0, 1]])
    for s in seeds:
        p = Path(s) if Path(s).is_absolute() else Path(root) / s
        p = p.with_suffix(".npz")
        if not p.exists():
            raise C.FeatureError(f"{p.name} not found: run mesh_to_npz first (the lineup reads the seed as npz)")
        d = np.load(p)
        V = d["V"].astype(float) @ rot.T
        me = bpy.data.meshes.new("lw_lineup")
        me.from_pydata(V.tolist(), [], d["T"].tolist())
        me.update()
        ob = bpy.data.objects.new("lw_lineup", me)
        bpy.context.scene.collection.objects.link(ob)
        try:
            for view, tag in (("Front", "front"), ("Left", "side")):
                target = out / f"lineup_{p.stem}_{tag}.png"
                R.render_view(ob, view, SIZE, str(target))
                files.append(str(target))
        finally:
            bpy.data.objects.remove(ob)
            bpy.data.meshes.remove(me)
    return {"piece": piece, "files": files, "size": SIZE, "engine": "WORKBENCH"}
