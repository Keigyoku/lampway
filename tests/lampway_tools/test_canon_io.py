# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""N1 (specs/canon/normalization DOOR.md section 1): canon_io, the ONLY module that calls Blender's importers.

import_raw stamps every datablock an import made `lw_raw` (the raw bytes' sha256, the container, the importer and its settings);
load_image binds the colour space to the role; facts measures what a door re-checks; the npz carries its canonical header."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402


def run(body):
    r = run_script(PRE + body, timeout=300)
    assert r.rc == 0, r.out[-1500:]
    return r.results[-1]


def test_import_raw_stamps_every_new_datablock_with_the_raw_sha_container_and_settings():
    d = run('''
from mixar.modules.lampway_tools import canon_io
bpy.ops.mesh.primitive_cube_add(size=1.0); cube = bpy.context.active_object
path = os.path.join(root, "box.glb")
bpy.ops.export_scene.gltf(filepath=path, use_selection=True)
bpy.data.objects.remove(cube)
r = canon_io.import_raw(path, guess_original_bind_pose=False)
ob = bpy.data.objects[r["objects"][0]]
res({"r": {k: r[k] for k in ("sha256", "container", "importer", "settings", "objects")}, "stamp": json.loads(ob["lw_raw"]),
     "mesh_stamp": json.loads(ob.data["lw_raw"]) if "lw_raw" in ob.data else None, "path": path})
''')
    raw = Path(d["path"]).read_bytes() if Path(d["path"]).exists() else None
    assert d["r"]["container"] == "glb" and d["r"]["importer"] == "import_scene.gltf" and d["r"]["settings"] == {"guess_original_bind_pose": False}
    assert d["stamp"]["sha256"] == d["r"]["sha256"] and len(d["r"]["sha256"]) == 64 and d["mesh_stamp"] == d["stamp"]
    assert raw is None or d["r"]["sha256"] == hashlib.sha256(raw).hexdigest()


def test_import_raw_refuses_an_unknown_container():
    d = run('''
from mixar.modules.lampway_tools import canon_io
p = os.path.join(root, "x.xyz"); open(p, "w").write("x")
try:
    canon_io.import_raw(p); res({"err": None})
except ValueError as e:
    res({"err": str(e)})
''')
    assert d["err"] and ".xyz" in d["err"]


def test_load_image_binds_the_colour_space_to_the_role_and_stamps_it():
    d = run('''
from mixar.modules.lampway_tools import canon_io
im = bpy.data.images.new("t", 4, 4); p = os.path.join(root, "t.png"); im.filepath_raw = p; im.file_format = "PNG"; im.save()
a = canon_io.load_image(p, role="normal"); b = canon_io.load_image(p, role="basecolor")
res({"normal": a.colorspace_settings.name, "base": b.colorspace_settings.name, "stamp": json.loads(a["lw_raw"])})
''')
    assert d["normal"] == "Non-Color" and d["base"] == "sRGB" and d["stamp"]["role"] == "normal" and len(d["stamp"]["sha256"]) == 64


def test_facts_measure_the_matrix_the_unit_the_bounds_and_the_geometry_hash():
    d = run('''
from mixar.modules.lampway_tools import canon_io
bpy.ops.mesh.primitive_cube_add(size=2.0); ob = bpy.context.active_object
f0 = canon_io.facts(ob)
ob.data.vertices[0].co.x += 0.25; ob.data.update()
f1 = canon_io.facts(ob)
ob.location = (1, 0, 0); bpy.context.view_layer.update()
f2 = canon_io.facts(ob)
res({"f0": f0, "h1": f1["geometry_sha256"], "m2": f2["object_matrix"]})
''')
    f0 = d["f0"]
    assert np.allclose(f0["object_matrix"], np.eye(4)) and f0["scene_scale_length"] == 1.0
    assert np.allclose(f0["bbox_min_m"], [-1, -1, -1]) and np.allclose(f0["bbox_max_m"], [1, 1, 1])
    assert len(f0["geometry_sha256"]) == 64 and d["h1"] != f0["geometry_sha256"] and d["m2"][0][3] == 1.0


def test_npz_carries_its_canonical_header(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
    from mixar.modules.lampway_tools import canon_io
    doc = {"schema": "lampway.canonical-asset", "kind": "mesh"}
    p = tmp_path / "x.npz"
    canon_io.write_npz(p, np.zeros((3, 3)), np.array([[0, 1, 2]]), doc)
    V, T, canon = canon_io.read_npz(p)
    assert canon == doc and V.shape == (3, 3) and T.tolist() == [[0, 1, 2]]
    np.savez(tmp_path / "raw.npz", V=np.zeros((3, 3)), T=np.array([[0, 1, 2]]))
    assert canon_io.read_npz(tmp_path / "raw.npz")[2] is None


def test_partial_native_import_rolls_back_every_new_id(tmp_path):
    from issue2_native import run_issue_case
    run_issue_case(tmp_path, '''
p=os.path.join(root,'triangle.ply');open(p,'w').write('ply\\nformat ascii 1.0\\nelement vertex 3\\nproperty float x\\nproperty float y\\nproperty float z\\nelement face 1\\nproperty list uchar int vertex_indices\\nend_header\\n0 0 0\\n1 0 0\\n0 1 0\\n3 0 1 2\\n')
before=ids();original=bpy.ops.wm.ply_import
class Broken:
    def __call__(self,**kw):
        original(**kw)
        raise RuntimeError('planted native failure')
# Patch the canonical resolver instead of bpy's immutable operator registry.
original_table=canon_io.importers
class Ops:
    broken=Broken()
bpy.ops.issue2_failure=Ops()
canon_io.importers=lambda flavour: {'.ply':('issue2_failure','broken')}
try:
    try:canon_io.import_raw(p)
    except RuntimeError as e:assert 'planted' in str(e)
    else:raise AssertionError('failure not raised')
    assert ids()==before,(ids(),before)
finally:
    canon_io.importers=original_table
    del bpy.ops.issue2_failure
''')


@pytest.mark.parametrize('case', ['rig_example', 'rig_fit', 'live_rebuild', 'motion', 'animation', 'compare_ui', 'studio', 'asset_place'])
def test_downstream_import_refusals_remove_only_imported_ids(case, tmp_path):
    from issue2_native import run_issue_case
    run_issue_case(tmp_path, '''
case=CASE
bpy.ops.wm.read_factory_settings(use_empty=True);ob=sphere('Source');mat=bpy.data.materials.new('Material');mat.use_nodes=True;ob.data.materials.append(mat)
camera=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera'));bpy.context.scene.collection.objects.link(camera)
p=os.path.join(root,'piece.glb');bpy.ops.export_scene.gltf(filepath=p,export_format='GLB')
if case=='rig_example':
    bpy.ops.mesh.primitive_cube_add(location=(3,0,0));bpy.ops.export_scene.gltf(filepath=p,export_format='GLB')
if case=='animation':
    arm=bpy.data.armatures.new('Target');ob=bpy.data.objects.new('Target',arm);bpy.context.scene.collection.objects.link(ob)
    bpy.ops.object.select_all(action='DESELECT');ob.select_set(True);bpy.context.view_layer.objects.active=ob
    bpy.ops.object.mode_set(mode='EDIT');b=arm.edit_bones.new('root');b.head=(0,0,0);b.tail=(0,0,1);bpy.ops.object.mode_set(mode='OBJECT')
if case=='compare_ui':
    from mixar.modules.lampway_tools.features import model_compare as M
    M._scratch()
    bpy.ops.object.select_all(action='DESELECT');bpy.data.objects['Camera'].select_set(True)
    bpy.ops.export_scene.gltf(filepath=p,export_format='GLB',use_selection=True,export_cameras=True)
if case=='motion':
    os.makedirs(root+'/anims');json.dump([{'name':'wave','file':'piece.glb'}],open(root+'/anims/index.json','w'))
before=ids();calls=[];original=canon_io.import_raw
def counted(*args,**kwargs):
    r=original(*args,**kwargs);calls.append(args[0]);return r
canon_io.import_raw=counted
try:
    if case=='rig_example':
        from mixar.modules.lampway_tools.features import rig_fit as R
        if os.environ.get("LAMPWAY_PLANT_IMPORT_GUARD"): R._example=R._example.__wrapped__
        R._example(p,root)
    elif case=='rig_fit':
        from mixar.modules.lampway_tools.features import rig_fit as R
        if os.environ.get("LAMPWAY_PLANT_IMPORT_GUARD"): R.fit=R.fit.__wrapped__
        R.fit(p,'missing-joints.json',root,template='missing-template.blend')
    elif case=='live_rebuild':
        from mixar.modules.lampway_tools import live_load as R
        if os.environ.get("LAMPWAY_PLANT_IMPORT_GUARD"): R.load_rebuild=R.load_rebuild.__wrapped__
        R.load_rebuild(p,root,'rebuild','Material',turn=1000)
    elif case=='motion':
        from mixar.modules.lampway_tools.features import motion_generate as R
        if os.environ.get("LAMPWAY_PLANT_IMPORT_GUARD"): R.generate=R.generate.__wrapped__
        R.generate(root,'wave',root+'/anims')
    elif case=='animation':
        from mixar.modules.lampway_tools.features import animation as R
        if os.environ.get("LAMPWAY_PLANT_IMPORT_GUARD"): R.retarget=R.retarget.__wrapped__
        R.retarget(p,'Target',root=root)
    elif case=='studio':
        from mixar.modules.lampway_tools import studio_landing as R
        def failed_stat(path):raise RuntimeError('planted post-import file-stat failure')
        saved_import=canon_io.import_raw
        def imported_then_stat(*args,**kwargs):
            result=saved_import(*args,**kwargs);R.os.path.getsize=failed_stat;return result
        canon_io.import_raw=imported_then_stat
        R.import_file(p)
    elif case=='asset_place':
        from mixar.modules.lampway_tools.features import asset_place as R
        def failed_place(*args,**kwargs):raise RuntimeError('planted post-import placement failure')
        R.place_objects=failed_place
        R.asset_place({'kind':'mesh','name':'piece','files':[{'role':'main','locations':[{'path':p}]}]},mode='import',options={'undo_step':False})
    elif case=='compare_ui':
        import importlib.util
        spec=importlib.util.spec_from_file_location('native_compare_ui',OVERLAY+'/mixar/modules/lampway_tools/ui/compare.py')
        R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
        R.STATE['manifest']={'id':'invalid','models':[{'file':'piece.glb'}]};R.STATE['root']=root
        if os.environ.get("LAMPWAY_PLANT_IMPORT_GUARD"): R.ensure_textured=R.ensure_textured.__wrapped__
        R.ensure_textured()
except Exception as e:
    refusal=str(e)
    assert refusal,(case,type(e).__name__)
else:raise AssertionError('downstream offender did not refuse: '+case)
assert calls==[p],(case,calls,refusal)
canon_io.import_raw=original
assert ids()==before,(case,ids(),before)
'''.replace('CASE',repr(case)))
