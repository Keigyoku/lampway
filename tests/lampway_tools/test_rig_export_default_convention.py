# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Default export follows measured normalized frames, keeping every readback bar."""
from test_rig_export_ue import run,CHAIN


def test_default_recipe_follows_measured_frames_and_preserves_corrective_roll(tmp_path):
    r=run(tmp_path,CHAIN+r'''
results={}
for mode in ('y','x'):
    arm=chain('same_unknown_name_'+mode,mode)
    bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT')
    helper=arm.data.edit_bones.new('upperarm_correctiveRoot_l');helper.head=J[1];helper.tail=Vector(J[1])+Vector((0,0,.04));helper.roll=math.radians(120);helper.parent=arm.data.edit_bones['b1']
    bpy.ops.object.mode_set(mode='OBJECT')
    call('rig_inspect',armature=arm.name)
    results[mode]=call('rig_export_ue',armature=arm.name,out='export/default_'+mode+'.fbx')
    if results[mode]['ok']:
        from io_scene_fbx import parse_fbx
        raw,_=parse_fbx.parse(results[mode]['out'])
        scales=[]
        for block in raw.elems:
            if block.id!=b'Objects':continue
            for model in block.elems:
                if model.id!=b'Model' or model.props[2]!=b'Null':continue
                scale=[1.,1.,1.]
                for properties in model.elems:
                    if properties.id!=b'Properties70':continue
                    for prop in properties.elems:
                        if prop.props[0]==b'Lcl Scaling':scale=[float(v) for v in prop.props[4:7]]
                scales.append(scale)
        results[mode]['raw_null_scales']=scales
print('RESULT',json.dumps(results))
''',timeout=600)
    assert r.rc==0,r.out[-3000:]
    for mode,recipe in [('y','cm_native_blender_convention'),('x','cm_native_ue_axes')]:
        row=r.results[0][mode]
        assert row['ok'],row
        assert row['recipe']['name']==recipe
        assert row['recipe_selection']['requested']=='auto'
        assert row['recipe_selection']['measured_convention']==row['convention']
        assert row['readback']['over_tolerance']==[]
        assert row['readback']['bars']=={'position_cm':.01,'rotation_deg':.01,'scale':.0001}
        assert row['readback']['bones_compared']==6
        assert row['raw_null_scales'],row
        assert all(abs(v-1)<.0001 for s in row['raw_null_scales'] for v in s),row['raw_null_scales']


def test_scaled_null_cannot_be_hidden_by_raw_blender_readback(tmp_path):
    r=run(tmp_path,CHAIN+r'''
arm=chain('raw_scale_carrier','y')
call('rig_inspect',armature=arm.name)
doc=json.loads(open(os.path.join(RECIPES,'cm_native_blender_convention.json')).read())
doc.pop('export_coordinates',None)
p=os.path.join(root,'legacy_metres.json');open(p,'w').write(json.dumps(doc))
before={o.name:o.as_pointer() for o in bpy.data.objects}
row=call('rig_export_ue',armature=arm.name,out='export/legacy.fbx',recipe=p)
print('RESULT',json.dumps({'row':row,'original_ids_unchanged':before=={o.name:o.as_pointer() for o in bpy.data.objects},
 'published':os.path.exists(os.path.join(root,'export/legacy.fbx')),
 'rejected':os.path.exists(os.path.join(root,'export/rejected/legacy.fbx'))}))
''',timeout=600)
    assert r.rc==0,r.out[-3000:]
    row=r.results[0]
    assert not row['row']['ok'],row
    assert 'authored nonunit FBX Null ancestors' in row['row']['error'],row
    assert row['rejected'] and not row['published'] and row['original_ids_unchanged'],row


def test_raw_container_audit_refuses_ambiguous_cyclic_and_nonfinite_models(tmp_path):
    r=run(tmp_path,CHAIN+r'''
from types import SimpleNamespace as Node
from unittest.mock import patch
from io_scene_fbx import parse_fbx
from mixar.modules.lampway_tools.features import export_checks as E
arm=chain('audit_container','y')
settings=json.loads(open(os.path.join(RECIPES,'cm_native_blender_convention.json')).read())['exporter']
settings['object_types']=set(settings['object_types'])
for o in bpy.context.view_layer.objects:o.select_set(o is arm)
bpy.context.view_layer.objects.active=arm
p=os.path.join(root,'raw_audit.fbx')
bpy.ops.export_scene.fbx(filepath=p,use_selection=True,bake_anim=False,**settings)
raw,version=parse_fbx.parse(p)
objects=next(b for b in raw.elems if b.id==b'Objects')
connections=next(b for b in raw.elems if b.id==b'Connections')
models=[m for m in objects.elems if m.id==b'Model']
container=next(m for m in models if m.props[2]==b'Null')
bones=[m for m in models if m.props[2]==b'LimbNode']
assert len(E.fbx_container_scale_failures(p))==5
def altered(model_elems,connection_elems):
    return Node(elems=[Node(id=b'Objects',elems=model_elems),Node(id=b'Connections',elems=connection_elems)])
cycle=[c for c in connections.elems if not(c.id==b'C' and c.props[0]==b'OO' and c.props[1]==container.props[0])]
cycle.append(Node(id=b'C',props=(b'OO',container.props[0],bones[0].props[0])))
ambiguous=list(connections.elems)+[Node(id=b'C',props=(b'OO',bones[0].props[0],bones[1].props[0]))]
badscale=Node(id=b'Model',props=container.props,elems=[Node(id=b'Properties70',elems=[Node(props=(b'Lcl Scaling',b'Lcl Scaling',b'',b'A',float('nan'),1.,1.))])])
cases={'cycle':altered(list(objects.elems),cycle),
 'parent':altered(list(objects.elems),ambiguous),
 'scale':altered([badscale if m is container else m for m in objects.elems],list(connections.elems)),
 'identity':altered(list(objects.elems)+[container],list(connections.elems))}
errors={}
for name,tree in cases.items():
    with patch.object(parse_fbx,'parse',return_value=(tree,version)):
        try:E.fbx_container_scale_failures(p)
        except ValueError as exc:errors[name]=str(exc)
print('RESULT',json.dumps(errors))
''',timeout=600)
    assert r.rc==0,r.out[-3000:]
    errors=r.results[0]
    assert 'cyclic' in errors['cycle']
    assert 'ambiguous' in errors['parent']
    assert 'invalid' in errors['scale']
    assert 'duplicate' in errors['identity']
