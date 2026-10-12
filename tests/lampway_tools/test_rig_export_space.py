# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Real writer regressions for explicit disposable centimetre representations."""
import pytest

from blender_run import run_script

PRE = r'''import bpy, json, hashlib, math, tempfile
from pathlib import Path
from mathutils import Matrix
import addon_utils
addon_utils.enable('io_scene_fbx', default_set=False)
from io_scene_fbx import parse_fbx
from mixar.modules.lampway_tools.features import rig_export_space as SPACE
from mixar.modules.lampway_tools import canon_io
def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def snapshot(arm, mesh, scene):
    return {'unit':scene.unit_settings.scale_length,
            'arm_world':[list(row) for row in arm.matrix_world],
            'bones':{b.name:{'matrix':[list(row) for row in b.matrix_local], 'length':b.length,
                                  'parent':b.parent.name if b.parent else None} for b in arm.data.bones},
            'mesh_world':[list(row) for row in mesh.matrix_world],
            'vertices':[list(v.co) for v in mesh.data.vertices],
            'weights':[[[mesh.vertex_groups[g.group].name,g.weight] for g in v.groups] for v in mesh.data.vertices]}

def world_vertices(mesh):
    return [mesh.matrix_world @ v.co for v in mesh.data.vertices]

def dimensions(coords):
    return [max(v[k] for v in coords)-min(v[k] for v in coords) for k in range(3)]

def evaluated_vertices(mesh):
    deps=bpy.context.evaluated_depsgraph_get()
    ob=mesh.evaluated_get(deps);data=ob.to_mesh()
    try:return [ob.matrix_world @ v.co for v in data.vertices]
    finally:ob.to_mesh_clear()

def fbx_metadata(path):
    root,version=parse_fbx.parse(str(path))
    sections={e.id:e for e in root.elems}
    def props(node):
        return {p.props[0].decode():[v.decode(errors='replace') if isinstance(v,bytes) else v for v in p.props[4:]]
                for sub in node.elems if sub.id==b'Properties70' for p in sub.elems}
    models=[]
    for e in sections[b'Objects'].elems:
        if e.id==b'Model':
            models.append({'id':e.props[0],'name':e.props[1].decode().split('\x00')[0],
                           'kind':e.props[2].decode(),'properties':props(e)})
    connections=[list(e.props) for e in sections[b'Connections'].elems if e.id==b'C' and e.props[0]==b'OO']
    parents={row[1]:row[2] for row in connections}
    return {'version':version,'global':props(sections[b'GlobalSettings']),
            'models':models,'parents':{m['name']:parents.get(m['id']) for m in models}}

bpy.ops.wm.read_factory_settings(use_empty=True)
original=bpy.context.scene
original.name='untouched_metre_source'
original.unit_settings.system='METRIC';original.unit_settings.scale_length=1.0
armdata=bpy.data.armatures.new('QA_RigData');arm=bpy.data.objects.new('QA_Rig',armdata)
original.collection.objects.link(arm);bpy.context.view_layer.objects.active=arm;arm.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
specs=[('root',None,(0,0,0),(0,.3,0),0),
       ('child','root',(0,.3,0),(.2,.6,.1),0),
       ('leaf','child',(.2,.6,.1),(.2,.8,.2),math.radians(120))]
for name,parent,head,tail,roll in specs:
    b=armdata.edit_bones.new(name);b.head=head;b.tail=tail;b.roll=roll
    if parent:b.parent=armdata.edit_bones[parent]
bpy.ops.object.mode_set(mode='OBJECT')
meshdata=bpy.data.meshes.new('QA_MeshData')
meshdata.from_pydata([(0,0,0),(.25,0,0),(0,.5,0),(0,0,1.2)],[],[(0,2,1),(0,1,3),(1,2,3),(2,0,3)])
mesh=bpy.data.objects.new('QA_Mesh',meshdata);original.collection.objects.link(mesh)
for name,values in [('root',[1.,0.,.3,.7]),('child',[0.,1.,.7,.3])]:
    g=mesh.vertex_groups.new(name=name)
    for index,weight in enumerate(values):
        if weight:g.add([index],weight,'REPLACE')
mesh.parent=arm;mod=mesh.modifiers.new('Armature','ARMATURE');mod.object=arm
bpy.context.view_layer.update()
before=snapshot(arm,mesh,original);before_sha=digest(before)
source_vertices=world_vertices(mesh)
reference={b.name:arm.matrix_world @ b.matrix_local for b in armdata.bones}
from mixar.modules.lampway_tools.features import rig_tools as RT
recipe_path=Path(RT.__file__).parents[1]/'rig_tools/recipes/cm_native_ue_axes.json'
recipe=json.loads(recipe_path.read_text())['exporter'];recipe['object_types']=set(recipe['object_types'])
from mixar.modules.lampway_tools.features import rig_tools as RT

'''


@pytest.mark.parametrize("system,unit", [("NONE",.01),("NONE",1.),("NONE",100.),("METRIC",.01),("METRIC",1.)])
def test_centimetre_writer_readback_and_source_isolation(system, unit):
    run = run_script(PRE + f"\noriginal.unit_settings.system={system!r}\noriginal.unit_settings.scale_length={unit!r}\n" + r'''
source = digest(snapshot(arm,mesh,original))
path=Path(tempfile.gettempdir())/'candidate.fbx'
legacy=Path(tempfile.gettempdir())/'legacy.fbx'
for ob in original.objects:ob.select_set(ob in (arm,mesh))
bpy.context.view_layer.objects.active=arm
bpy.ops.export_scene.fbx(filepath=str(legacy),use_selection=True,bake_anim=False,**recipe)
legacy_meta=fbx_metadata(legacy)
from io_scene_fbx.fbx_utils import units_blender_to_fbx_factor
scene_factor=units_blender_to_fbx_factor(original)
assert any(m['kind']=='Null' and max(abs(v/scene_factor-1) for v in m['properties'].get('Lcl Scaling',[1.,1.,1.]))<1e-4 for m in legacy_meta['models'])
ids=canon_io.snapshot_ids()
with SPACE.centimetre_copies(arm,[mesh],None,recipe) as copied:
    assert original.unit_settings.scale_length==copied['receipt']['scene_scale_length']
    assert digest(snapshot(arm,mesh,original))==source
    assert copied['exporter']['global_scale']==1./scene_factor
    for ob in original.objects:ob.select_set(ob in [copied['armature'],*copied['meshes']])
    bpy.context.view_layer.objects.active=copied['armature']
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,bake_anim=False,**copied['exporter'])
assert canon_io.snapshot_ids()==ids
metadata=fbx_metadata(path)
assert metadata['global']['UnitScaleFactor']==[1.]
assert all(max(abs(v-1) for v in m['properties'].get('Lcl Scaling',[1.,1.,1.]))<1e-4 for m in metadata['models'] if m['kind']=='Null')
old=set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=str(path),automatic_bone_orientation=False,primary_bone_axis='Y',secondary_bone_axis='X',global_scale=1.)
imported=[o for o in bpy.data.objects if o not in old]
ra=next(o for o in imported if o.type=='ARMATURE');rm=next(o for o in imported if o.type=='MESH')
rest=evaluated_vertices(rm)
assert max(min((v*(scene_factor/100.)-src).length for v in rest) for src in source_vertices)<1e-6
weights=snapshot(ra,rm,original)['weights']
ra.pose.bones['child'].rotation_mode='XYZ';ra.pose.bones['child'].rotation_euler.z=.35
bpy.context.view_layer.update()
posed=evaluated_vertices(rm)
readback_before=digest(snapshot(ra,rm,original))
receipt=SPACE.readback_representation(ra,imported,1.)
assert digest(snapshot(ra,rm,original))==readback_before
assert receipt['translation_to_metres']==scene_factor/100.
assert receipt['scale_divisor']==1./scene_factor
assert max((a-b).length for a,b in zip(posed,evaluated_vertices(rm)))<1e-6
assert snapshot(ra,rm,original)['weights']==weights
ra.pose.bones['child'].rotation_euler.z=0.
bpy.context.view_layer.update()
assert max((a-b).length*(scene_factor/100.) for a,b in zip(rest,evaluated_vertices(rm)))<1e-6
for name,ref in reference.items():
    got=ra.matrix_world @ ra.data.bones[name].matrix_local
    loc,q,scale=got.decompose();rl,rq,rs=ref.decompose()
    delta=q.rotation_difference(rq)
    angle=math.degrees(2*math.atan2(math.sqrt(delta.x**2+delta.y**2+delta.z**2),abs(delta.w)))
    assert (loc*receipt['translation_to_metres']-rl).length*100<.01
    assert angle<.01
    assert max(abs(a/receipt['scale_divisor']-b) for a,b in zip(scale,rs))<1e-4
    assert (ra.data.bones[name].parent.name if ra.data.bones[name].parent else None)==before['bones'][name]['parent']
assert digest(snapshot(arm,mesh,original))==source
carrier=ra.scale.copy();ra.scale*=2.;bpy.context.view_layer.update()
try:SPACE.readback_representation(ra,imported,1.)
except ValueError:pass
else:assert False
ra.scale=carrier;bpy.context.view_layer.update()
assert digest(snapshot(ra,rm,original))==readback_before
print('RESULT '+json.dumps({'wire_unit':1,'legacy_null_scale':scene_factor,'representation':receipt}))
''')
    assert run.rc == 0, run.out
    assert run.results[0]['wire_unit'] == 1


def test_location_keys_shape_keys_and_exception_cleanup():
    run = run_script(PRE + r'''
mesh.shape_key_add(name='Basis');key=mesh.shape_key_add(name='Raised');key.data[3].co.z+=.1
arm.location=(.1,.2,.3);arm.keyframe_insert('location',frame=1)
arm.pose.bones['child'].location=(.03,.04,.05)
arm.pose.bones['child'].keyframe_insert('location',frame=1)
arm.pose.bones['child'].rotation_mode='XYZ';arm.pose.bones['child'].rotation_euler.z=.2
arm.pose.bones['child'].keyframe_insert('rotation_euler',frame=1)
bpy.context.view_layer.update()
action=arm.animation_data.action
channels=lambda a:[(f.data_path,f.array_index,[(list(k.co),list(k.handle_left),list(k.handle_right)) for k in f.keyframe_points]) for f in RT._fcurves(a)]
original_channels=channels(action);source=digest(snapshot(arm,mesh,original));ids=canon_io.snapshot_ids()
source_shape_keys=set(bpy.data.shape_keys)
try:
    with SPACE.centimetre_copies(arm,[mesh],action,recipe) as copied:
        for ob in bpy.context.selected_objects:ob.select_set(False)
        copied['meshes'][0].select_set(True)
        bpy.context.view_layer.objects.active=copied['meshes'][0]
        for old,new in zip(original_channels,channels(copied['action'])):
            factor=100 if old[0]=='location' or old[0].endswith('.location') else 1
            for ok,nk in zip(old[2],new[2]):
                for ov,nv in zip(ok,nk):
                    assert ov[0]==nv[0] and abs(nv[1]-ov[1]*factor)<1e-6
        assert abs(copied['meshes'][0].data.shape_keys.key_blocks['Raised'].data[3].co.z-130)<1e-4
        assert max((v*.01-src).length for v,src in zip(world_vertices(copied['meshes'][0]),world_vertices(mesh)))<1e-6
        raise RuntimeError('injected exporter failure')
except RuntimeError as exc:assert str(exc)=='injected exporter failure'
assert canon_io.snapshot_ids()==ids
assert list(bpy.context.selected_objects)==ids['selection'][0]
assert bpy.context.view_layer.objects.active==ids['selection'][1]
assert set(bpy.data.shape_keys)==source_shape_keys
assert abs(key.data[3].co.z-1.3)<1e-6
assert channels(action)==original_channels and digest(snapshot(arm,mesh,original))==source
mesh.animation_data_create()
try:
    with SPACE.centimetre_copies(arm,[mesh],action,recipe):assert False
except ValueError:pass
else:assert False
assert canon_io.snapshot_ids()==ids
mesh.animation_data_clear()
curve=next(f for f in RT._fcurves(action) if f.data_path=='location')
modifier=curve.modifiers.new('GENERATOR')
try:
    with SPACE.centimetre_copies(arm,[mesh],action,recipe):assert False
except ValueError:pass
else:assert False
assert canon_io.snapshot_ids()==ids
curve.modifiers.remove(modifier)
for bad in [dict(recipe,global_scale=2),dict(recipe,apply_unit_scale=False),dict(recipe,apply_scale_options='FBX_SCALE_UNITS')]:
    try:
        with SPACE.centimetre_copies(arm,[mesh],action,bad):assert False
    except ValueError:pass
    else:assert False
    assert canon_io.snapshot_ids()==ids
print('RESULT '+json.dumps({'source_unchanged':True,'cleanup':True}))
''')
    assert run.rc == 0, run.out
    assert run.results[0]['cleanup']


def test_nonactive_action_slots_bind_to_the_original_owner_and_ambiguity_refuses_before_copies():
    run = run_script(PRE + r'''
requested=bpy.data.actions.new('RequestedMultiSlot')
target=requested.slots.new('OBJECT',arm.name)
requested.slots.new('OBJECT','AnotherOwner')
ambiguous=bpy.data.actions.new('AmbiguousMultiSlot')
ambiguous.slots.new('OBJECT','FirstOwner');ambiguous.slots.new('OBJECT','SecondOwner')
source=digest(snapshot(arm,mesh,original));ids=canon_io.snapshot_ids()
with SPACE.centimetre_copies(arm,[],requested,recipe) as copied:
    assert copied['armature'].animation_data.action_slot.handle==target.handle
assert canon_io.snapshot_ids()==ids and digest(snapshot(arm,mesh,original))==source
try:
    with SPACE.centimetre_copies(arm,[],ambiguous,recipe):assert False
except ValueError as exc:
    assert 'ambiguous or incompatible slots' in str(exc)
else:assert False
assert canon_io.snapshot_ids()==ids and digest(snapshot(arm,mesh,original))==source
print('RESULT '+json.dumps({'original_owner_slot':True,'ambiguous_refused':True}))
''')
    assert run.rc == 0, run.out
    assert run.results[0] == {'original_owner_slot': True, 'ambiguous_refused': True}


def test_metric_100_export_refuses_operator_clamp_before_copies():
    run = run_script(PRE + r'''
original.unit_settings.scale_length=100.
source=digest(snapshot(arm,mesh,original));ids=canon_io.snapshot_ids()
prop=bpy.ops.export_scene.fbx.get_rna_type().properties['global_scale']
assert .0001<prop.hard_min
try:
    with SPACE.centimetre_copies(arm,[mesh],None,recipe):assert False
except ValueError as exc:assert 'operator limits' in str(exc)
else:assert False
assert canon_io.snapshot_ids()==ids and digest(snapshot(arm,mesh,original))==source
path=Path(tempfile.gettempdir())/'clamped.fbx'
for ob in original.objects:ob.select_set(ob in (arm,mesh))
bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,bake_anim=False,**dict(recipe,global_scale=.0001))
metadata=fbx_metadata(path)
assert any(m['kind']=='Null' and max(abs(v-10) for v in m['properties'].get('Lcl Scaling',[1.,1.,1.]))<1e-4 for m in metadata['models'])
# Decode an actual import into this unsupported writer display configuration;
# the identity-carrier file is authored separately in a disposable metre scene.
writer=bpy.data.scenes.new('metre_writer');writer.unit_settings.system='METRIC';writer.unit_settings.scale_length=1.
bpy.context.window.scene=writer
writer.collection.objects.link(arm);writer.collection.objects.link(mesh)
with SPACE.centimetre_copies(arm,[mesh],None,recipe) as copied:
    for ob in writer.objects:ob.select_set(ob in [copied['armature'],*copied['meshes']])
    bpy.context.view_layer.objects.active=copied['armature']
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,bake_anim=False,**copied['exporter'])
bpy.context.window.scene=original
old=set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=str(path),automatic_bone_orientation=False,primary_bone_axis='Y',secondary_bone_axis='X',global_scale=1.)
imported=[ob for ob in bpy.data.objects if ob not in old];ra=next(ob for ob in imported if ob.type=='ARMATURE')
receipt=SPACE.readback_representation(ra,imported,1.)
assert receipt['translation_to_metres']==100. and receipt['scale_divisor']==.0001
for name,ref in reference.items():
    loc,q,scale=(ra.matrix_world @ ra.data.bones[name].matrix_local).decompose();rl,rq,rs=ref.decompose()
    assert (loc*receipt['translation_to_metres']-rl).length*100<.01
    delta=q.rotation_difference(rq)
    assert math.degrees(2*math.atan2(math.sqrt(delta.x**2+delta.y**2+delta.z**2),abs(delta.w)))<.01
    assert max(abs(a/receipt['scale_divisor']-b) for a,b in zip(scale,rs))<1e-4
assert digest(snapshot(arm,mesh,original))==source
print('RESULT '+json.dumps({'clamped_null_falsifier':10,'representation':receipt}))
''')
    assert run.rc == 0, run.out
    assert run.results[0]['clamped_null_falsifier'] == 10


def test_ue_recipe_writes_the_verified_blender_container_name_on_copies_only():
    run = run_script(PRE + r'''
doc=json.loads(recipe_path.read_text())
kwargs={'container_name':doc['ue_armature_container']} if 'ue_armature_container' in doc else {}
source=digest(snapshot(arm,mesh,original));ids=canon_io.snapshot_ids()
path=Path(tempfile.gettempdir())/'named-container.fbx'
with SPACE.centimetre_copies(arm,[mesh],None,recipe,**kwargs) as copied:
    for ob in original.objects:ob.select_set(ob in [copied['armature'],*copied['meshes']])
    bpy.context.view_layer.objects.active=copied['armature']
    bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,bake_anim=False,**copied['exporter'])
nulls=[m for m in fbx_metadata(path)['models'] if m['kind']=='Null']
assert len(nulls)==1 and nulls[0]['name']=='Armature',nulls
assert nulls[0]['properties'].get('Lcl Scaling',[1.,1.,1.])==[1.,1.,1.]
assert digest(snapshot(arm,mesh,original))==source
assert canon_io.snapshot_ids()==ids
print('RESULT '+json.dumps({'container':'Armature','source_unchanged':True}))
''')
    assert run.rc == 0, run.out


@pytest.mark.parametrize('invalid_name', ['Armature.001', 'root', 123])
def test_ue_container_name_refuses_unverified_names_before_copies(invalid_name):
    run = run_script(PRE + f'\ninvalid_name={invalid_name!r}\n' + r'''
ids=canon_io.snapshot_ids();source=digest(snapshot(arm,mesh,original))
try:
    with SPACE.centimetre_copies(arm,[mesh],None,recipe,container_name=invalid_name):assert False
except ValueError as exc:assert 'verified legacy UE container predicate' in str(exc)
else:assert False
assert canon_io.snapshot_ids()==ids and digest(snapshot(arm,mesh,original))==source
print('RESULT '+json.dumps({'refused':True,'source_unchanged':True}))
''')
    assert run.rc == 0, run.out


def test_ue_container_name_collision_preserves_the_existing_object():
    run = run_script(PRE + r'''
occupied=bpy.data.objects.new('Armature',None);original.collection.objects.link(occupied)
ids=canon_io.snapshot_ids();source=digest(snapshot(arm,mesh,original))
try:
    with SPACE.centimetre_copies(arm,[mesh],None,recipe,container_name='Armature'):assert False
except ValueError as exc:assert 'reserved Armature export-copy name is occupied' in str(exc)
else:assert False
assert occupied.name=='Armature' and bpy.data.objects.get('Armature') is occupied
assert canon_io.snapshot_ids()==ids and digest(snapshot(arm,mesh,original))==source
print('RESULT '+json.dumps({'refused':True,'source_unchanged':True}))
''')
    assert run.rc == 0, run.out
