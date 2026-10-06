# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The algorithm canon's goldens inside the Lampway suite.

`canon_goldens/` is a verbatim copy of the canon's generator (`gen_goldens.py`, `meshgen.py`), its reference
implementations (`reference.py`, the oracle) and its self-test. The goldens are generated once per session into the
pytest base temp and every written file is checked against `goldens.sha256` (the canon tree's own bytes), so a test can
never pass on a drifted fixture. The OBJ/JSON are never committed here: the generator is the artefact.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
GOLDENS_SRC = HERE / "canon_goldens"
if str(GOLDENS_SRC) not in sys.path:
    sys.path.insert(0, str(GOLDENS_SRC))

import meshgen  # noqa: E402
import reference  # noqa: E402

_CACHE = {}


def pinned_hashes():
    out = {}
    for line in (GOLDENS_SRC / "goldens.sha256").read_text().splitlines():
        if line and not line.startswith("#"):
            h, name = line.split(maxsplit=1)
            out[name] = h
    return out


def generate(out: Path) -> Path:
    import gen_goldens
    out.mkdir(parents=True, exist_ok=True)
    gen_goldens.main(out)
    return out


@pytest.fixture(scope="session")
def goldens(tmp_path_factory):
    """The generated canon goldens directory, byte-checked against the pinned hashes."""
    if "dir" not in _CACHE:
        out = generate(tmp_path_factory.mktemp("canon_goldens"))
        bad = []
        for name, h in pinned_hashes().items():
            p = out / name
            if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest() != h:
                bad.append(name)
        assert not bad, f"the golden generator's bytes changed: {bad}"
        _CACHE["dir"] = out
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
