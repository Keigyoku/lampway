# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Client workflows from Stefan's wiki (engine-asset-acceptance, geometry-game-mesh-preparation, rigging-existing-armor): each is a
checklist turned into measured gates on real data, composed from the proven feature code. Nothing here calls a model."""

from features_support import run


def test_mesh_prep_branches_the_source_records_its_hash_and_repairs_only_the_defects_it_reports(tmp_path):
    r = run(tmp_path, '''
src = boxes("helm", [((0, 0, 0), (1, 1, 1)), ((3, 0, 0), (0.2, 0.2, 0.2))])
bm = bmesh.new(); bm.from_mesh(src.data)
bm.verts.new((9, 9, 9))                                    # a loose vertex
dup = bmesh.ops.duplicate(bm, geom=[f for f in bm.faces][:1])  # a doubled face's vertices
bm.to_mesh(src.data); bm.free()
before = (len(src.data.vertices), len(src.data.polygons))
res = call("mesh_prep", object="helm", full=True)
prep = bpy.data.objects.get(res.get("object", ""))
print("RESULT", json.dumps({"res": res, "src_unchanged": (len(src.data.vertices), len(src.data.polygons)) == before,
                            "prep_hash": prep.get("lw_source_hash") if prep else None}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    res = out["res"]
    assert res["ok"] is True and res["object"] == "helm_prep" and out["src_unchanged"] is True
    assert len(res["source_hash"]) == 64 and out["prep_hash"] == res["source_hash"]
    assert res["found"]["loose_vertices"] >= 1 and res["after"]["loose_vertices"] == 0
    assert res["after"]["shells"] <= res["before"]["shells"]
    assert res["dimensions"] and res["pivot_offset_from_bounds_centre"] is not None


def test_asset_acceptance_gates_pass_a_clean_copy_and_fail_a_flipped_and_a_drifting_one(tmp_path):
    r = run(tmp_path, '''
ref = boxes("ref", [((0, 0, 0), (1, 1, 1))])
good = boxes("good", [((0, 0, 0), (1, 1, 1))])
bad = boxes("bad", [((0.8, 0, 0), (1, 1, 1.6))])
bm = bmesh.new(); bm.from_mesh(bad.data); bmesh.ops.reverse_faces(bm, faces=bm.faces[:]); bm.to_mesh(bad.data); bm.free()
a = call("asset_acceptance", object="good", reference="ref")
b = call("asset_acceptance", object="bad", reference="ref")
print("RESULT", json.dumps({"a": a, "b": b}))
''')
    assert r.rc == 0, r.out[-2500:]
    a, b = r.results[0]["a"], r.results[0]["b"]
    assert a["ok"] is True and a["accepted"] is True and set(a["gates"]) == {"identity", "orientation", "geometry", "materials"}
    assert all(g["pass"] for g in a["gates"].values()), a["gates"]
    assert b["ok"] is True and b["accepted"] is False
    assert b["gates"]["geometry"]["pass"] is False and "inverted" in " ".join(b["gates"]["geometry"]["reasons"])
    assert b["gates"]["orientation"]["pass"] is False, "bounds drifted off the reference"


def test_rig_armor_fits_a_rigid_plate_to_one_bone_on_a_copy_and_reports_pose_stretch(tmp_path):
    r = run(tmp_path, '''
body = humanoid("body")
call("auto_rig", object="body", kind="humanoid")
plate = boxes("plate", [((0, -0.2, 1.15), (0.5, 0.06, 0.5))])
res = call("rig_armor", object="plate", armature="body_rig", bone="spine_03")
fit = bpy.data.objects.get(res.get("object", ""))
print("RESULT", json.dumps({"res": res, "plate_vg": [g.name for g in plate.vertex_groups], "fit_vg": [g.name for g in fit.vertex_groups] if fit else None}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    res = out["res"]
    assert res["ok"] is True and res["object"] == "plate_fit" and res["mode"] == "rigid"
    assert out["plate_vg"] == [] and out["fit_vg"] == ["spine_03"], "the original is never bound"
    assert len(res["poses"]) >= 2 and all(p["max_edge_stretch"] < 1.001 for p in res["poses"])
    assert res["accepted"] is True


def test_retopo_uv_lod_weight_chain_records_original_source_and_passes_identity(tmp_path):
    from issue2_native import run_issue_case
    run_issue_case(tmp_path, '''
from mixar.modules.lampway_tools.features import workflows as W
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
source=sphere('approved',4)
r=call('normalize_mesh',input=source.name,turn_deg=0);assert r.get('ok'),r
digest=W.mesh_hash(source)
r=call('retopo',object=source.name,method='voxel',target_faces=1000);assert r.get('ok'),r
ret=bpy.data.objects[r['object']]
r=call('uv_unwrap',object=ret.name,method='smart',texture_size=256);assert r.get('ok'),r
uv=bpy.data.objects[r['object']]
r=call('normalize_mesh',input=uv.name,turn_deg=0);assert r.get('ok'),r
r=call('lod_chain',object=uv.name,ratios=[.5],preserve_uv_seams=False);assert r.get('ok'),r
lod=bpy.data.objects[r['lods'][0]['object']]
arm=bpy.data.armatures.new('Rig');rig=bpy.data.objects.new('Rig',arm);bpy.context.scene.collection.objects.link(rig)
bpy.ops.object.select_all(action='DESELECT');rig.select_set(True);bpy.context.view_layer.objects.active=rig
bpy.ops.object.mode_set(mode='EDIT');b=arm.edit_bones.new('root');b.head=(0,0,0);b.tail=(0,0,1);bpy.ops.object.mode_set(mode='OBJECT')
body=lod.copy();body.data=lod.data.copy();body.name='nativebody';bpy.context.scene.collection.objects.link(body)
g=body.vertex_groups.new(name='root');g.add(list(range(len(body.data.vertices))),1,'REPLACE');m=body.modifiers.new('Armature','ARMATURE');m.object=rig
r=call('weight_transfer',object=lod.name,source=body.name);assert r.get('ok'),r
wt=bpy.data.objects[r['object']]
for ob in (ret,uv,lod,wt):
    assert ob.get('lw_source_hash')==digest,(ob.name,dict(ob.items()))
    r=call('asset_acceptance',object=ob.name,reference=source.name,tolerance=.1)
    assert r.get('ok') and r['gates']['identity']['pass'],r
assert call('asset_acceptance',object=uv.name,reference=source.name,tolerance=.1)['accepted'],r
''')


def test_mesh_prep_default_receipt_is_compact_with_full_shell_pages(tmp_path):
    from issue2_isolated import run as isolated
    out = isolated(tmp_path, '''
a=call('mesh_prep',object='Cube')
b=call('mesh_prep',object='Cube',full=True,limit=1)
print('RESULT '+json.dumps({'a':a,'b':b,'bytes':len(json.dumps(a).encode())}))
''')[0]
    assert out['a']['ok'] and out['bytes'] < 12000, out
    assert 'source_hash' not in out['a'] and 'source_hash' in out['b']
    assert out['a']['before'] == out['b']['before']
    assert len(out['b']['shell_orientation']) == 1
    assert len(out['b']['dimensions']) == 3
    assert out['b']['pages']['shell_orientation']['total'] == 1


def test_mesh_prep_rejects_wrong_presentation_shapes_before_creating_a_branch(tmp_path):
    from issue2_isolated import run as isolated
    out = isolated(tmp_path, '''
before=sorted(bpy.data.objects.keys())
rows=[call('mesh_prep',object='Cube',**opts) for opts in [{'limit':0},{'offset':-1},{'fields':{}},{'full':'yes'}]]
print('RESULT '+json.dumps({'rows':rows,'before':before,'after':sorted(bpy.data.objects.keys())}))
''')[0]
    assert all(not r['ok'] for r in out['rows'])
    assert out['before'] == out['after'], out


def test_public_bunny_retopo_uv_chain_acceptance_receipt(tmp_path):
    from pathlib import Path
    import os
    import pytest
    from issue2_native import run_issue_case
    asset_root=os.environ.get('LAMPWAY_MCP_ACCEPTANCE_ASSETS')
    if not asset_root or not (Path(asset_root)/'bun_zipper.ply').is_file():
        pytest.skip('pinned bun_zipper.ply required; original Tripo input remains separate')
    run_issue_case(tmp_path, '''
import shutil
from mixar.modules.lampway_tools.features import workflows as W
bpy.ops.wm.read_factory_settings(use_empty=True)
shutil.copy2(ASSET,root+'/bunny.ply')
n=call('normalize_mesh',input='bunny.ply',turn_deg=0);assert n.get('ok'),n
source=next(o for o in bpy.data.objects if o.type=='MESH');digest=W.mesh_hash(source)
r=call('retopo',object=source.name,method='voxel',target_faces=2000);assert r.get('ok'),r
u=call('uv_unwrap',object=r['object'],method='smart',texture_size=256);assert u.get('ok'),u
uv=bpy.data.objects[u['object']]
normalized=call('normalize_mesh',input=uv.name,turn_deg=0);assert normalized.get('ok'),normalized
l=call('lod_chain',object=uv.name,ratios=[.5],preserve_uv_seams=False);assert l.get('ok'),l
lod=bpy.data.objects[l['lods'][0]['object']]
arm=bpy.data.armatures.new('Rig');rig=bpy.data.objects.new('Rig',arm);bpy.context.scene.collection.objects.link(rig)
bpy.ops.object.select_all(action='DESELECT');rig.select_set(True);bpy.context.view_layer.objects.active=rig
bpy.ops.object.mode_set(mode='EDIT');bone=arm.edit_bones.new('root');bone.head=(0,0,0);bone.tail=(0,0,1);bpy.ops.object.mode_set(mode='OBJECT')
body=lod.copy();body.data=lod.data.copy();body.name='weighted_reference_body';bpy.context.scene.collection.objects.link(body)
g=body.vertex_groups.new(name='root');g.add(list(range(len(body.data.vertices))),1,'REPLACE')
mod=body.modifiers.new('Armature','ARMATURE');mod.object=rig
wt=call('weight_transfer',object=lod.name,source=body.name);assert wt.get('ok'),wt
# This source-identity acceptance chain records weight quality; acceptance is not a skin-quality gate.
assert 0<wt['matched_fraction']<=1 and wt['groups_written']==1,wt
assert sum(wt['influence_histogram'].values())+wt['unweighted_vertices']==len(lod.data.vertices),wt
outputs=[bpy.data.objects[r['object']],uv,lod,bpy.data.objects[wt['object']]]
assert len({o.as_pointer() for o in [source,*outputs,body]})==6,'each stage must create an independent object'
acceptance=[]
for ob in outputs:
    assert ob.get('lw_source_hash')==digest,(ob.name,dict(ob.items()))
    accepted=call('asset_acceptance',object=ob.name,reference=source.name)
    assert accepted.get('ok') and accepted['accepted'],accepted
    acceptance.append(accepted)
assert W.mesh_hash(source)==digest,'source changed'
assert not source.vertex_groups and not lod.vertex_groups,'weight transfer must preserve its inputs'
print('GEOMETRY_RECEIPT '+json.dumps({'asset':'bun_zipper.ply','source_hash':digest,'retopo':r,'uv':u,'lod':l,'weights':wt,'acceptance':acceptance}))
'''.replace('ASSET',repr(str(Path(asset_root)/'bun_zipper.ply'))))


def test_large_nested_mesh_metrics_are_paged_even_with_selected_fields_and_full(tmp_path):
    from issue2_isolated import run as isolated
    out = isolated(tmp_path, '''
def measured(*args):
    return {'object':'Cube_prep','source':'Cube','before':{'faces':160,'metrics':[{'id':i,'value':i,'samples':list(range(160))} for i in range(160)]},'after':{'faces':160},'found':{}}
api._F_wf.mesh_prep=measured
rows=[call('mesh_prep',object='Cube',fields=['before'],full=full) for full in [False,True]]
print('RESULT '+json.dumps(rows))
''')[0]
    for row in out:
        assert row['ok'], row
        assert len(row['before']['metrics']) == 50
        assert row['pages']['before.metrics']['total'] == 160
    assert 'samples' not in out[0]['before']['metrics'][0]
    assert len(out[1]['before']['metrics'][0]['samples']) == 50
    assert out[1]['pages']['before.metrics.0.samples']['total'] == 160


def test_qa_tag_layers_matches_the_requested_object_and_piece_configuration(tmp_path):
    from issue2_isolated import run as isolated
    out = isolated(tmp_path, '''
from mixar.modules.lampway_tools.meshqa import live
live.save_config(bpy.context.scene,live.QAConfig(object='Cube',piece='helmet',recipe='',owner='',rulings_dir=''))
wrong=call('qa_tag_layers',object='Other',piece='helmet')
right=call('qa_tag_layers',object='Cube',piece='helmet')
empty=call('qa_tag_layers',object='',piece='helmet')
print('RESULT '+json.dumps({'wrong':wrong,'right':right,'empty':empty}))
''')[0]
    assert not out['wrong']['ok'] and 'object' in out['wrong']['error'], out
    assert out['right']['ok'] and out['right']['object'] == 'Cube', out
    assert not out['empty']['ok'] and 'object' in out['empty']['error'], out


def test_many_shell_mesh_prep_receipts_keep_complete_metrics_and_bounded_shell_pages(tmp_path):
    from issue2_isolated import run as isolated
    out = isolated(tmp_path, '''
me=bpy.data.meshes.new('shells'); verts=[]; faces=[]
for i in range(160):
    n=len(verts); verts.extend([(i*2,0,0),(i*2+1,0,0),(i*2,1,0)]); faces.append((n,n+1,n+2))
me.from_pydata(verts,[],faces); ob=bpy.data.objects.new('shells',me); bpy.context.collection.objects.link(ob)
a=call('mesh_prep',object='shells')
b=call('mesh_prep',object='shells',full=True,limit=10,offset=50)
print('RESULT '+json.dumps({'a':a,'b':b,'bytes':len(json.dumps(a).encode())}))
''')[0]
    assert out['a']['ok'] and out['b']['ok'], out
    assert out['bytes'] < 12000
    assert out['a']['before']['shells'] == out['b']['before']['shells'] == 160
    assert out['b']['pages']['shell_orientation']['total'] == 160
    assert len(out['b']['shell_orientation']) == 10
    assert len(out['b']['dimensions']) == 3
