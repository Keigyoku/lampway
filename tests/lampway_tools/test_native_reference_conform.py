# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent native bind frames survive a declared bone-axis conversion."""
import copy
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.rig_tools import core as RC
from mixar.modules.lampway_tools.canon_geom import native_topology as NT

B = np.array([[0., -1., 0.], [1., 0., 0.], [0., 0., 1.]])


def fixture():
    names = list(NT.PARENTS)
    heads = {n: (i * .001, i * .002, i * .003) for i, n in enumerate(names)}
    frames = {n: RC.rot("z", (i * 37) % 180) @ RC.rot("x", 23) for i, n in enumerate(names)}
    src = {"names": names, "parents": dict(NT.PARENTS), "heads": heads,
           "frames": {n: RC.rot("y", 51) for n in names}, "lengths": {n: .1 for n in names}}
    ref = {"names": list(names), "parents": dict(NT.PARENTS), "heads": copy.deepcopy(heads), "frames": frames}
    return src, ref


@pytest.mark.parametrize("convention", ["blender", "ue_axes"])
def test_complete_native_reference_keeps_independent_engine_binds(convention):
    src, ref = fixture()
    before = copy.deepcopy(src)
    plan = RC.conform_plan(src, {n: n for n in src["names"]}, {}, ref, convention)
    bridge = B if convention == "blender" else np.eye(3)
    for b in plan["bones"]:
        assert np.allclose(b["frame"] @ bridge, ref["frames"][b["name"]], atol=1e-12)
        assert b["head"] == before["heads"][b["name"]]
        assert np.array_equal(src["frames"][b["name"]], before["frames"][b["name"]])
    assert plan["reference_scope"] == "independent_native_bind"


@pytest.mark.parametrize("bad", ["missing", "parent", "head", "reflection", "shear", "scale", "offset", "synthesis", "mapping", "ik"])
def test_native_reference_refuses_unsupported_bind_changes(bad):
    src, ref = fixture()
    mapping = {n: n for n in src["names"]}
    synth, offsets, ik = {}, {}, False
    n = src["names"][-1]
    if bad == "missing": ref["names"].remove(n); ref["parents"].pop(n)
    if bad == "parent": ref["parents"][n] = None
    if bad == "head": ref["heads"][n] = (10., 0., 0.)
    if bad == "reflection": ref["frames"][n] = np.diag([-1., 1., 1.])
    if bad == "shear": ref["frames"][n] = np.array([[1., .01, 0.], [0., 1., 0.], [0., 0., 1.]])
    if bad == "scale": ref["scales"] = {n: [1., 100., 1.]}
    if bad == "offset": offsets = {n: {"roll_deg": 1.}}
    if bad == "synthesis": synth = {"spine_03": .5}
    if bad == "mapping": mapping["head"] = "pelvis"
    if bad == "ik": ik = True
    with pytest.raises(RC.RigRefused):
        RC.conform_plan(src, mapping, synth, ref, offsets=offsets, ik_bones=ik)


@pytest.mark.parametrize("bad", [None, "stale", "pin", "hash", "missing", "parent", "rotation", "position", "scale"])
def test_reference_axis_admission_checks_every_independent_bind_bar(bad):
    src, ref = fixture()
    rig = copy.deepcopy(src)
    rig["frames"] = {n: R @ B.T for n, R in ref["frames"].items()}
    binds = {n: {"head_m": ref["heads"][n], "frame_engine": ref["frames"][n].tolist()} for n in ref["names"]}
    receipt = {"schema": "lampway.native-reference-bind/1", "convention": "blender",
               "reference_sha256": "a" * 64, "output_rest": "current",
               "binds": binds, "binds_sha256": RC.sha(binds)}
    n = src["names"][-1]
    if bad == "stale": receipt["output_rest"] = "previous"
    if bad == "pin": receipt["reference_sha256"] = "unknown"
    if bad == "hash": binds[n]["head_m"] = [10., 0., 0.]
    if bad == "missing": rig["names"].remove(n)
    if bad == "parent": rig["parents"][n] = None
    if bad == "rotation": rig["frames"][n] = rig["frames"][n] @ RC.rot("z", .01001)
    if bad == "position": rig["heads"][n] = np.asarray(rig["heads"][n]) + [0., .0001001, 0.]
    if bad == "scale": rig["scales"] = {n: [1., 1.000101, 1.]}
    if bad:
        with pytest.raises(RC.RigRefused):
            RC.reference_bind_convention(rig, receipt, "current")
    else:
        assert RC.reference_bind_convention(rig, receipt, "current") == "blender"
        # Recipe admission does not rewrite the strict joint classifier.
        assert RC.classify_convention([116.43709]) == "mixed"


def test_native_reference_copy_exports_independent_binds_and_refuses_a_changed_rest(tmp_path):
    from isolated_binary import run
    from test_native_complete_topology import BUILD
    result = run(tmp_path, BUILD + r'''
from pathlib import Path
from mixar.modules.lampway_tools.features import rig_tools as RT, rig_export as RE
from mixar.modules.lampway_tools.rig_tools import core as RC
rows=[]
for b in arm.data.bones:
    R=np.array(b.matrix_local.to_3x3()) @ RE.ENGINE_FROM_BLENDER
    q=Matrix(R.tolist()).to_quaternion()
    q.normalize()
    rows.append({'name':b.name,'parent':b.parent.name if b.parent else None,
      'bind':{'translation':[100*b.head_local.x,-100*b.head_local.y,100*b.head_local.z],
              'rotation':[-q.x,q.y,-q.z,q.w],'scale':[1,1,1]}})
path=Path(root)/'independent.json'
path.write_text(json.dumps({'schema':'titan.animation-profile/1','name':'synthetic independent bind',
  'adapter':{'centimeters_per_unit':1},'bones':rows}))
# Source roll is deliberately different from the independent reference.
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT')
for b in arm.data.edit_bones:b.roll+=.4
bpy.ops.object.mode_set(mode='OBJECT')
before=RT._fingerprint(arm,RT.read(arm))
piece=skinned(arm,'probe')
api.rig_inspect(armature=arm.name,profile='metahuman')
api.rig_map(armature=arm.name,profile='metahuman',out='native.map.json')
con=api.rig_conform(armature=arm.name,map='native.map.json',reference='independent.json',out_name='calibrated',dry_run=False)
out=bpy.data.objects.get('calibrated')
export={};changed={};inspected={}
if out:
    inspected=api.rig_inspect(armature=out.name,profile='metahuman')
    export=api.rig_export_ue(armature=out.name,meshes=con['meshes_out'],out='calibrated.fbx')
    bpy.context.view_layer.objects.active=out;bpy.ops.object.mode_set(mode='EDIT')
    out.data.edit_bones['pinky_03_half_l'].roll+=.02
    bpy.ops.object.mode_set(mode='OBJECT')
    changed=api.rig_export_ue(armature=out.name,meshes=con['meshes_out'],out='changed.fbx')
print('RESULT',json.dumps({'conform':con,'inspect':inspected,'export':export,'changed':changed,
  'source_unchanged':before==RT._fingerprint(arm,RT.read(arm)), 'changed_file':(Path(root)/'changed.fbx').exists()}))
''')
    assert result.rc == 0, result.out[-2000:]
    got = result.results[-1]
    assert got['conform']['ok'], got['conform']
    assert got['export']['ok'], got['export']
    assert got['export']['reference'] == 'independent native reference bind'
    assert got['export']['reference_scope'] == 'independent_native_bind'
    assert got['export']['readback']['bones_compared'] == 342
    assert not got['export']['readback']['over_tolerance']
    assert not got['changed']['ok'] and not got['changed_file']
    assert got['source_unchanged']
