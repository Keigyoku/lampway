# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native candidate controls on synthetic native-sidecar body, no owner approval."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script
from canon_fit_support import FIT_PRE


PRE = FIT_PRE + r'''
from mixar.modules.lampway_tools.features import fit_conform as FC, common as C
body, arm = human()
sc = write_sidecar(body, arm, os.path.join(root, 'ue', 'sidecar.json'), root_bone='pelvis')
pkg = api.fit_body('build', armature='rig', mesh='body', sidecar='ue/sidecar.json', out='fit/body')
assert pkg['ok'], pkg
verts=[];faces=[]
for x in (.179, .25):
    offset=len(verts)
    verts += [(x,y,z) for z in (1.05,1.15,1.25) for y in (-.06,0,.06)]
    faces += [(offset+3*r+c,offset+3*r+c+1,offset+3*(r+1)+c+1,offset+3*(r+1)+c) for r in range(2) for c in range(2)]
offset=len(verts)
verts += [(.27,-.04,1.05),(.27,.04,1.05),(.27,0,1.12)]
faces += [(offset,offset+1,offset+2)]
mesh=bpy.data.meshes.new('piece');mesh.from_pydata(verts,[],faces);mesh.update()
ob=bpy.data.objects.new('piece',mesh);bpy.context.scene.collection.objects.link(ob)
for name,ids in [('soft',list(range(9))),('clear',list(range(9,18))),('plate',list(range(18,21)))]:
    ob.vertex_groups.new(name=name).add(ids,1.,'REPLACE')
norm=api.normalize_mesh('piece',turn_deg=0,generator='captain_authored',want_scale='real',
    scale_evidence={'method':'unit_metadata','value':1,'reference':'synthetic metre coordinates'},weld='never')
assert norm['ok'],norm
ob.location=(.2245,0,1.05)
source=C.duplicate(ob,'_source')
if 'lw_canon' in source: del source['lw_canon']
before=FC._identity(ob);body_before=FC._identity(body);source_before=FC._identity(source)
roles={'soft':'cloth','clear':'leather','plate':'metal'}
kw=dict(root=root,out_dir='piece/fit/conform',body=pkg['package'],body_package_sha256=pkg['package_sha256'],
    roles=roles,parts=['soft','clear'],object=ob.name,source=source.name,armature='rig',clearance_m=.002,seam_limit_m=.001)
def refuse(fn):
    try: fn()
    except (ValueError,RuntimeError,OSError) as e:return str(e)
    raise AssertionError('corruption was accepted')
'''


def test_native_clearance_candidate_review_and_stale_controls(tmp_path):
    r = run_script(PRE + r'''
bad={}
raw=C.duplicate(ob,'_raw');del raw['lw_canon']
bad['raw']=refuse(lambda:FC.run(**dict(kw,object=raw.name,out_dir='raw')))
stamp=ob['lw_canon'];doc=json.loads(stamp);doc['conventions']['frame']='invented';ob['lw_canon']=json.dumps(doc)
bad['frame']=refuse(lambda:FC.run(**kw));ob['lw_canon']=stamp
co=ob.data.vertices[0].co.copy();ob.data.vertices[0].co.x+=.01
bad['stale_input']=refuse(lambda:FC.run(**kw));ob.data.vertices[0].co=co
candidate=FC.run(**kw)
assert candidate['candidate_pending_review'],candidate
out=bpy.data.objects[candidate['object']]
P=FC._mesh(ob)[0];O=FC._mesh(out)[0]
assert np.array_equal(O[9:],P[9:]),'clear component or metal moved'
assert np.all(O[:9,0]>P[:9,0]),'colliding soft patch did not move'
accept=dict(kw,action='accept',candidate_sha256=candidate['candidate_sha256'])
bad['review']=refuse(lambda:FC.run(**accept))
accept.update(captain_seen=True,render_sha256='a'*64)
bad['hash']=refuse(lambda:FC.run(**dict(accept,candidate_sha256='b'*64)))
co=out.data.vertices[0].co.copy();out.data.vertices[0].co.x+=.01
bad['output']=refuse(lambda:FC.run(**accept));out.data.vertices[0].co=co
modifier=out.modifiers.new('planted stale display','SUBSURF')
bad['modifier']=refuse(lambda:FC.run(**accept));out.modifiers.remove(modifier)
location=arm.location.copy();arm.location.x+=.001
bad['armature']=refuse(lambda:FC.run(**accept));arm.location=location
receipt=FC.run(**accept)
assert FC._identity(ob)==before and FC._identity(source)==source_before and FC._identity(body)==body_before
res({'candidate':candidate,'accept':receipt,'bad':bad,'clear_and_metal_exact':True,'originals_unchanged':True})
''', env={'LW_KEEP_ROOT': str(tmp_path)}, timeout=180)
    assert r.rc == 0, r.out[-4500:]
    d = r.results[-1]
    assert d['candidate']['clearance']['pass'] and d['candidate']['clearance']['inside_vertices'] == 0
    assert d['accept']['physical_status'] == 'untested'
    assert set(d['bad']) == {'raw', 'frame', 'stale_input', 'review', 'hash', 'output', 'modifier', 'armature'}
    assert 'normalize first' in d['bad']['raw'] and 'frame' in d['bad']['frame']
    assert 'changed' in d['bad']['output']
    assert d['clear_and_metal_exact'] and d['originals_unchanged']


def test_native_receipt_write_failure_cleans_candidate_and_preserves_inputs(tmp_path):
    r = run_script(PRE + r'''
from pathlib import Path
original_write=Path.write_text
def fail_receipt(path,*args,**kwargs):
    if path.name=='candidate.json':raise OSError('planted receipt write failure')
    return original_write(path,*args,**kwargs)
objects=set(bpy.data.objects.keys());meshes=set(bpy.data.meshes.keys())
Path.write_text=fail_receipt
try:error=refuse(lambda:FC.run(**kw))
finally:Path.write_text=original_write
assert set(bpy.data.objects.keys())==objects and set(bpy.data.meshes.keys())==meshes
assert not (Path(root)/'piece/fit/conform').exists()
assert FC._identity(ob)==before and FC._identity(source)==source_before and FC._identity(body)==body_before
res({'error':error,'no_leaks':True,'no_receipt_directory':True,'originals_unchanged':True})
''', env={'LW_KEEP_ROOT': str(tmp_path)}, timeout=180)
    assert r.rc == 0, r.out[-4500:]
    d = r.results[-1]
    assert 'planted receipt write failure' in d['error']
    assert d['no_leaks'] and d['no_receipt_directory'] and d['originals_unchanged']
