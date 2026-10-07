# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon 03 F.6 / 07 INV-07.3: the native weight sidecar read as the body package carries it.

The sidecar is the file Titan's `armour-validate.py sidecar` writes from the engine (schema titan.native-weight-sidecar/1, the
result titan.native-weight-sidecar-result/1): render vertices in UE asset/component space (cm, Z up, left-handed; the wearer's
left is UE +X, canon 01 B), their normals, the triangles touching them and every named bone weight. Read into the BODY FRAME
(metres, Z up, front -Y, wearer's left +X): (x, -y, z) / 100, all influences kept. A triangle's winding is not assumed across
the handedness change: it is ORIENTED by the engine's own vertex normals (the face normal must agree with them)."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.features import native_sidecar as NS  # noqa: E402

BONES = {"pelvis": None, "spine_01": "pelvis", "spine_03": "spine_01"}


def doc(vertices=None, triangles=None, errors=None, bones=None, units="cm", schema="titan.native-weight-sidecar/1"):
    """A sidecar as the editor leg writes it (one front-facing triangle in UE space: +Y is the wearer's front)."""
    vertices = vertices if vertices is not None else {
        "10": {"position": [0.0, 10.0, 100.0], "normal": [0.0, 1.0, 0.0], "uv0": [0, 0], "weights": {"spine_01": 1.0}},
        "11": {"position": [10.0, 10.0, 100.0], "normal": [0.0, 1.0, 0.0], "uv0": [1, 0], "weights": {"spine_01": 0.25, "spine_03": 0.75}},
        "12": {"position": [0.0, 10.0, 110.0], "normal": [0.0, 1.0, 0.0], "uv0": [0, 1], "weights": {"spine_03": 1.0}}}
    return {"schema": schema, "tool": "armour-validate sidecar", "version": "test",
            "conventions": {"units": units, "space": "UE asset/component space (Z up, left-handed), the rest the engine skins"},
            "result": {"schema": "titan.native-weight-sidecar-result/1", "errors": errors or {}, "root_bone": "pelvis",
                       "bones": bones or BONES, "vertices": vertices,
                       "triangles": triangles if triangles is not None else [[7, 10, 11, 12], [8, 11, 12, 99]],
                       "quantum": {}, "totals": {}}}


def test_the_sidecar_reads_into_the_body_frame_in_metres():
    b = NS.read(doc())
    assert b.ids.tolist() == [10, 11, 12]
    assert np.allclose(b.V, [[0, -0.1, 1.0], [0.1, -0.1, 1.0], [0, -0.1, 1.1]])          # UE front +Y -> body front -Y
    assert np.allclose(b.N, [[0, -1, 0]] * 3)
    assert sorted(b.T[0].tolist()) == [0, 1, 2] and b.dropped_triangles == 1                                                          # vertex 99 is outside the sidecar
    assert b.names == ["pelvis", "spine_01", "spine_03"] and np.allclose(b.W[1], [0, 0.25, 0.75])
    assert b.parents == BONES and b.root_bone == "pelvis"


@pytest.mark.parametrize("bad, needle", [
    (doc(schema="titan.armour-helpers/1"), "titan.native-weight-sidecar/1"),
    (doc(errors={"fatal": "Traceback"}), "fatal"),
    (doc(units="m"), "cm"),
    (doc(vertices={"1": {"position": [0, 0, 0], "normal": [0, 1, 0], "weights": {"spine_01": 0.7}}}, triangles=[]), "sum"),
    (doc(vertices={"1": {"position": [0, 0, 0], "normal": [0, 1, 0], "weights": {"clavicle_r": 1.0}}}, triangles=[]), "clavicle_r"),
    (doc(vertices={}, triangles=[]), "no vertices"),
])
def test_a_sidecar_that_is_not_the_engines_weights_is_refused_by_name(bad, needle):
    with pytest.raises(NS.SidecarError, match=needle):
        NS.read(bad)


@pytest.mark.parametrize("winding", [[7, 10, 11, 12], [7, 10, 12, 11]])
def test_each_triangle_is_oriented_by_the_engines_vertex_normals_whatever_its_stored_winding(winding):
    b = NS.read(doc(triangles=[winding]))
    face = np.cross(b.V[b.T[0, 1]] - b.V[b.T[0, 0]], b.V[b.T[0, 2]] - b.V[b.T[0, 0]])
    assert face @ b.N[b.T[0]].sum(0) > 0, (winding, b.T.tolist())


def test_the_file_form_reads_the_same(tmp_path):
    p = tmp_path / "sidecar.json"
    p.write_text(json.dumps(doc()))
    assert np.allclose(NS.read(str(p)).V, NS.read(doc()).V)


def test_skin_poses_the_native_body_with_all_its_influences():
    b = NS.read(doc())
    up = np.eye(4)
    up[2, 3] = 0.5                                                                           # spine_03 lifted 0.5 m
    mats = {"pelvis": np.eye(4), "spine_01": np.eye(4), "spine_03": up}
    V, N = NS.skin(b, mats)
    assert np.allclose(V[:, 2] - b.V[:, 2], [0.0, 0.375, 0.5]) and np.allclose(N, b.N)
    with pytest.raises(NS.SidecarError, match="spine_03"):
        NS.skin(b, {"pelvis": np.eye(4), "spine_01": np.eye(4)})                              # a weighted bone the skeleton lacks
