# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The algorithm canon's goldens inside the Lampway suite, read from the canon itself: `docs/canon/goldens/` (the source of truth,
lampway-canon skill: "load a golden's case from docs/canon/goldens/; never copy it elsewhere"). Its generator, reference
implementations (the oracles) and committed cases are used in place. Once per session the generator re-runs into the pytest base
temp and every case file it writes must equal the committed one byte for byte, so a test can never pass on a drifted case
(`check_canon.py` holds the same in CI).
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GOLDENS_SRC = ROOT / "docs/canon/goldens"
EXAMPLES = ROOT / "docs/canon/normalization/canonical-asset.examples.json"
if str(GOLDENS_SRC) not in sys.path:
    sys.path.insert(0, str(GOLDENS_SRC))

import meshgen  # noqa: E402
import reference  # noqa: E402

_CACHE = {}


def generate(out: Path) -> Path:
    import gen_goldens
    out.mkdir(parents=True, exist_ok=True)
    gen_goldens.main(out)
    return out


@pytest.fixture(scope="session")
def goldens(tmp_path_factory):
    """docs/canon/goldens, after a fresh generation was compared with it byte for byte."""
    if "dir" not in _CACHE:
        fresh = generate(tmp_path_factory.mktemp("canon_goldens"))
        files = [p for p in fresh.rglob("*") if p.is_file()]
        bad = [str(p.relative_to(fresh)) for p in files
               if not (GOLDENS_SRC / p.relative_to(fresh)).is_file()
               or hashlib.sha256(p.read_bytes()).digest() != hashlib.sha256((GOLDENS_SRC / p.relative_to(fresh)).read_bytes()).digest()]
        assert files and not bad, f"the generator's output differs from the committed docs/canon/goldens: {bad}"
        _CACHE["dir"] = GOLDENS_SRC
    return _CACHE["dir"]


def J(root: Path, rel: str):
    return json.loads((root / rel).read_text())


def obj(root: Path, rel: str):
    """(V, F, UV, FUV, groups) of a golden OBJ."""
    return meshgen.read_obj(root / rel)


def tris(F):
    return np.asarray(meshgen.triangulate(F))


# Blender-side helper (prepend to a run_script source after test_wave3_weights.PRE): a golden OBJ as a scene object,
# vertices verbatim (no importer axis conversion), its faces and, when it has them, its UVs as the active layer.
LOAD_OBJ = r'''
def load_obj(path, name):
    V, VT, F, FT = [], [], [], []
    for line in open(path):
        w = line.split()
        if not w or w[0].startswith("#"):
            continue
        if w[0] == "v":
            V.append(tuple(float(x) for x in w[1:4]))
        elif w[0] == "vt":
            VT.append((float(w[1]), float(w[2])))
        elif w[0] == "f":
            cs = [c.split("/") for c in w[1:]]
            F.append([int(c[0]) - 1 for c in cs])
            FT.append([int(c[1]) - 1 for c in cs] if all(len(c) > 1 and c[1] for c in cs) else None)
    me = bpy.data.meshes.new(name); me.from_pydata(V, [], F); me.update()
    if VT and all(ft is not None for ft in FT):
        uv = me.uv_layers.new(name="UVMap")
        for poly, ft in zip(me.polygons, FT):
            for li, t in zip(poly.loop_indices, ft):
                uv.data[li].uv = VT[t]
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob

def points(name, pts):
    me = bpy.data.meshes.new(name); me.from_pydata([tuple(p) for p in pts], [], []); me.update()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob
'''
