# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native importer and library rollback inventory; every plant follows a completed load."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from issue2_native import run_issue_case


STATE = '''
from types import SimpleNamespace
from contextlib import contextmanager
def state():
    kinds=tuple(dict.fromkeys(canon_io._KINDS+('libraries','shape_keys','movieclips')))
    return ({k:sorted(d.as_pointer() for d in getattr(bpy.data,k)) for k in kinds},
            sorted(o.as_pointer() for o in bpy.context.selected_objects),
            bpy.context.view_layer.objects.active.as_pointer() if bpy.context.view_layer.objects.active else None)
bpy.ops.wm.read_factory_settings(use_empty=True)
source=sphere('authored_fixture',2)
mat=bpy.data.materials.new('authored_material');mat.use_nodes=True
image=bpy.data.images.new('authored_image',width=2,height=2)
mat.node_tree.nodes.new('ShaderNodeTexImage').image=image;source.data.materials.append(mat)
bpy.ops.object.select_all(action='DESELECT');source.select_set(True);bpy.context.view_layer.objects.active=source
'''


@pytest.mark.parametrize('link', [False, True])
def test_partial_library_loader_exception_restores_every_id_and_selection(tmp_path, link):
    run_issue_case(tmp_path, STATE+'''
path=root+'/source.blend';bpy.data.libraries.write(path,{source},fake_user=True)
before=state();native=bpy.data.libraries.load;completed=[]
class FailedLibrary:
    def __init__(self,*args,**kwargs):self.inner=native(*args,**kwargs)
    def __enter__(self):return self.inner.__enter__()
    def __exit__(self,*args):
        result=self.inner.__exit__(*args)
        assert state()[0]!=before[0],'the native loader must create actual IDs'
        completed.append(True)
        raise RuntimeError('planted exception after completed native library load')
class Libraries:
    load=FailedLibrary
    def __iter__(self):return iter(bpy.data.libraries)
    def remove(self,*args,**kwargs):return bpy.data.libraries.remove(*args,**kwargs)
class Data:
    libraries=Libraries()
    def __getattr__(self,name):return getattr(bpy.data,name)
actual=canon_io.bpy;canon_io.bpy=SimpleNamespace(data=Data(),context=bpy.context)
try:
    try:
        with canon_io.load_library(path,link=LINK) as (src,dst):dst.objects=['authored_fixture']
    except RuntimeError as e:assert 'completed native' in str(e)
    else:raise AssertionError('plant was not reached')
finally:canon_io.bpy=actual
assert completed==[True]
assert state()==before,(state(),before)
'''.replace('LINK',repr(link)))


@pytest.mark.parametrize('mode', ['append', 'link'])
def test_library_placement_failure_restores_every_id_and_selection(tmp_path, mode):
    run_issue_case(tmp_path, STATE+'''
from mixar.modules.lampway_tools.features import asset_place as P
path=root+'/source.blend';bpy.data.libraries.write(path,{source},fake_user=True)
before=state();loaded=[];real=canon_io.load_library
@contextmanager
def completed(*args,**kwargs):
    with real(*args,**kwargs) as handles:yield handles
    assert state()[0]!=before[0];loaded.append(True)
canon_io.load_library=completed
failed=[]
def failure(*args,**kwargs):
    assert loaded==[True];failed.append(True)
    raise RuntimeError('planted downstream placement failure')
if MODE=='append':P.place_objects=failure
else:P.stamp=failure
try:
    P.asset_place({'kind':'mesh','name':'authored_fixture','files':[{'role':'main','locations':[{'path':path}]}]},mode=MODE,options={'undo_step':False})
except RuntimeError as e:assert 'downstream placement' in str(e)
else:raise AssertionError('plant was not reached')
assert failed==[True] and loaded==[True]
assert state()==before,(state(),before)
'''.replace('MODE',repr(mode)))


def test_studio_collection_failure_restores_every_imported_id_and_selection(tmp_path):
    run_issue_case(tmp_path, STATE+'''
from mixar.modules.lampway_tools import studio_landing as S
path=root+'/source.glb';bpy.ops.export_scene.gltf(filepath=path,export_format='GLB')
before=state();loaded=[];real=canon_io.import_raw
class Collections:
    def get(self,*args):return bpy.data.collections.get(*args)
    def new(self,*args):
        assert loaded==[True] and state()[0]!=before[0]
        raise RuntimeError('planted downstream collection creation failure')
class Data:
    collections=Collections()
    def __getattr__(self,name):return getattr(bpy.data,name)
def completed(*args,**kwargs):
    result=real(*args,**kwargs);loaded.append(True)
    S.bpy=SimpleNamespace(data=Data(),context=bpy.context)
    return result
canon_io.import_raw=completed
try:S.import_file(path,turn_deg=0)
except RuntimeError as e:assert 'collection creation' in str(e)
else:raise AssertionError('plant was not reached')
assert loaded==[True]
assert state()==before,(state(),before)
''')


FORMATS=[('.glb','addon'),('.gltf','addon'),('.fbx','addon'),('.fbx','native'),('.obj','addon'),('.bvh','addon'),('.usd','addon'),('.usda','addon'),('.usdc','addon'),('.usdz','addon'),('.stl','addon'),('.ply','addon')]


@pytest.mark.parametrize('extension,flavour', FORMATS)
def test_real_importer_formats_restore_every_id_after_downstream_exception(tmp_path, extension, flavour):
    run_issue_case(tmp_path, STATE+'''
ext=EXT;path=root+'/fixture'+ext
if ext in ('.glb','.gltf'):bpy.ops.export_scene.gltf(filepath=path,export_format='GLB' if ext=='.glb' else 'GLTF_SEPARATE')
elif ext=='.fbx':bpy.ops.export_scene.fbx(filepath=path,use_selection=True,object_types={'MESH'},add_leaf_bones=False)
elif ext=='.obj':bpy.ops.wm.obj_export(filepath=path,export_selected_objects=True)
elif ext=='.stl':bpy.ops.wm.stl_export(filepath=path,export_selected_objects=True)
elif ext=='.ply':bpy.ops.wm.ply_export(filepath=path,export_selected_objects=True)
elif ext=='.bvh':
    open(path,'w').write('HIERARCHY\\nROOT root\\n{\\nOFFSET 0 0 0\\nCHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation\\nEnd Site\\n{\\nOFFSET 0 1 0\\n}\\n}\\nMOTION\\nFrames: 1\\nFrame Time: 0.0333333\\n0 0 0 0 0 0\\n')
else:bpy.ops.wm.usd_export(filepath=path,selected_objects_only=True)
before=state();completed=[]
@canon_io.rollback_imports
def consumer():
    result=canon_io.import_raw(path,flavour=FLAVOUR)
    assert result['result']==['FINISHED'] and result['objects'],result
    assert state()[0]!=before[0],result
    completed.append(True)
    raise RuntimeError('planted downstream format failure')
try:consumer()
except RuntimeError as e:assert 'downstream format' in str(e)
else:raise AssertionError('plant was not reached')
assert completed==[True]
assert state()==before,(state(),before)
print('GEOMETRY_RECEIPT '+json.dumps({'container':ext,'flavour':FLAVOUR,'successful_import_before_failure':True,'all_ids_and_selection_restored':True}))
'''.replace('EXT',repr(extension)).replace('FLAVOUR',repr(flavour)))


def test_every_subprocess_import_site_is_canonical_and_process_failure_preserves_parent(tmp_path):
    """Execute each import call's real native settings in an isolated process, then fail after loading.

    This checks import ownership/isolation, not each recipe's unrelated geometry algorithm.
    """
    run_issue_case(tmp_path, STATE+'''
import ast, subprocess, hashlib
from pathlib import Path
from mixar.modules.lampway_tools import runner as RUN
base=Path(OVERLAY)/'mixar/modules/lampway_tools'
paths=sorted((base/'scripts').rglob('*.py'))+sorted((base/'rig_convert/recipes').glob('*.py'))
rows=[]
for file in paths:
    tree=ast.parse(file.read_text())
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call) or not isinstance(node.func,ast.Attribute) or node.func.attr not in ('import_raw','load_library'):continue
        target=ast.unparse(node.func)
        assert target in ('lw_canon.io.import_raw','_lc.io.import_raw','lw_import.import_raw','lw_canon.io.load_library','_lc.io.load_library'),(str(file),target)
        rows.append((file,node,target))
expected={
 'scripts/bake/material_bake.py','scripts/bake/bake_maps.py','scripts/library/catalog_export.py',
 'scripts/texlib/clay_view.py','scripts/texlib/uv_score.py',
 'scripts/proportion/mesh_compare.py','scripts/proportion/pose_clearance.py','scripts/proportion/proportion_fit.py','scripts/proportion/mesh_to_npz.py',
 'scripts/partseg/delete_caps.py','scripts/partseg/mesh_load.py','scripts/partseg/uv_patches.py','scripts/partseg/render_owner.py','scripts/partseg/patch_holes.py',
 'scripts/meshqa/mesh_qa.py','rig_convert/recipes/skin-bind-verify-blender.py','rig_convert/recipes/anim-compare-blender.py','rig_convert/recipes/skin-bind-compare-blender.py'}
assert {str(file.relative_to(base)) for file,_,_ in rows}==expected
for tool in RUN.TOOLS.values():
    if tool.kind!='blender':continue
    command=RUN.command(tool.name,['fixture.blend','args'])
    assert '-b' in command and '--python-exit-code' in command and '-P' in command,command
    assert command[command.index('-P')+1]==str(RUN.SCRIPTS/tool.script),command
assert RUN._env(RUN.S.load())['LAMPWAY_BRIDGE_PORT']=='0'
fbx=root+'/fixture.fbx';glb=root+'/fixture.glb';blend=root+'/fixture.blend'
bpy.ops.export_scene.fbx(filepath=fbx,use_selection=True,object_types={'MESH'},add_leaf_bones=False)
bpy.ops.export_scene.gltf(filepath=glb,export_format='GLB')
bpy.data.libraries.write(blend,{source},fake_user=True)
before=state();files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (fbx,glb,blend)}
verified=[]
for file,node,target in rows:
    # Keep the call's canonical adapter and settings. Only its fixture path changes.
    extension='blend' if node.func.attr=='load_library' else ('fbx' if node.keywords else 'glb')
    fixture={'blend':blend,'fbx':fbx,'glb':glb}[extension]
    node.args=[ast.Constant(fixture),*node.args[1:]]
    # Library calls have no dynamic kwargs; import settings are authored constants.
    assert all(not any(isinstance(n,ast.Name) for n in ast.walk(k.value)) for k in node.keywords),(str(file),ast.unparse(node))
    call=ast.unparse(node)
    setup="import sys;sys.path.insert(0,"+repr(str(base/'scripts'))+");sys.path.insert(0,"+repr(str(base/'rig_convert'))+");import bpy,lw_canon,lw_import;_lc=lw_canon;from pathlib import Path;"+"bpy.ops.wm.read_factory_settings(use_empty=True)\\n"
    if node.func.attr=='load_library':body="with "+call+" as (src,dst): dst.objects=list(src.objects)\\n"
    else:body=call+"\\n"
    body+="assert len(bpy.data.objects)>0,'native import must create IDs'\\nprint('IMPORT_SITE_LOADED',flush=True)\\nraise RuntimeError('planted downstream subprocess failure')\\n"
    script=Path(root)/'import-site.py';script.write_text(setup+body)
    result=RUN.run_exe([os.environ['LAMPWAY_INSPECT_BIN'],'--background','--factory-startup','--disable-autoexec','--python-exit-code','1','--python',str(script)],timeout=45)
    output='\\n'.join(result['log'])
    assert result['rc']==1 and not result['timed_out'] and 'IMPORT_SITE_LOADED' in output and 'planted downstream subprocess failure' in output,(str(file),node.lineno,result)
    assert state()==before,'failed child import mutated the persistent parent'
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in files.items()),'failed child modified input artifacts'
    verified.append({'script':str(file.relative_to(base)),'line':node.lineno,'adapter':target,'native_import_completed':True,'failed_child_rc':1,'parent_ids_selection_unchanged':True})
print('GEOMETRY_RECEIPT '+json.dumps({'subprocess_import_sites':verified,'headless_registry_and_bridge_isolation_verified':True}))
''')


@pytest.mark.parametrize('mode', ['assign_material','assign_maps','add_node_group','set_world','reference_image','add_clip','apply_animation','attach_rig'])
def test_each_remaining_placement_import_mode_restores_ids_after_real_load(tmp_path, mode):
    run_issue_case(tmp_path, STATE+'''
import subprocess
from mixar.modules.lampway_tools.features import asset_place as P, asset_place_shading as SH, asset_place_media as M
mode=MODE;target={'where':'object:'+source.name};role='main';kind='image';name='imported_fixture'
path=root+'/fixture.png';image.filepath_raw=path;image.file_format='PNG';image.save();image.filepath_raw=''  # force a distinct native file load
if mode=='assign_material':
    path=root+'/fixture.blend';bpy.data.libraries.write(path,{mat},fake_user=True);role='blend';kind='material';name=mat.name
elif mode=='add_node_group':
    group=bpy.data.node_groups.new('authored_group','ShaderNodeTree');path=root+'/fixture.blend';bpy.data.libraries.write(path,{group},fake_user=True)
    role='blend';kind='material';name=group.name;target={'where':'node_tree:'+mat.name}
elif mode=='assign_maps':kind='map'
elif mode=='set_world':kind='image'
elif mode=='reference_image':kind='image';target={}
elif mode=='add_clip':
    kind='video';target={};path=root+'/fixture.mp4'
    result=subprocess.run(['ffmpeg','-loglevel','error','-f','lavfi','-i','color=c=red:s=16x16:d=0.2','-c:v','mpeg4','-y',path],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
elif mode=='apply_animation':
    kind='animation';arm=bpy.data.armatures.new('target_rig');rig=bpy.data.objects.new('target_rig',arm);bpy.context.scene.collection.objects.link(rig)
    bpy.ops.object.select_all(action='DESELECT');rig.select_set(True);bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
    b=arm.edit_bones.new('missing_from_source');b.head=(0,0,0);b.tail=(0,0,1);bpy.ops.object.mode_set(mode='OBJECT')
    rig.pose.bones['missing_from_source'].rotation_mode='XYZ';rig.pose.bones['missing_from_source'].keyframe_insert('rotation_euler',frame=1)
    action=rig.animation_data.action;name=action.name;path=root+'/fixture.blend';bpy.data.libraries.write(path,{action},fake_user=True);target={'where':'object:'+rig.name}
elif mode=='attach_rig':
    kind='rig';path=root+'/fixture.glb';bpy.ops.export_scene.gltf(filepath=path,export_format='GLB')
asset={'kind':kind,'name':name,'subtype':'basecolor' if mode=='assign_maps' else '', 'files':[{'role':role,'locations':[{'path':path}]}]}
before=state();reached=[]
def fail_after_load(*args,**kwargs):
    assert state()[0]!=before[0],'failure must follow actual loaded IDs'
    assert args[0].as_pointer() not in {pointer for pointers in before[0].values() for pointer in pointers},'the stamped asset itself must be newly loaded'
    reached.append(True)
    raise RuntimeError('planted downstream '+mode+' failure')
if mode=='attach_rig':
    actual_import=canon_io.import_raw
    def completed_import(*args,**kwargs):
        result=actual_import(*args,**kwargs);assert result['objects'] and state()[0]!=before[0]
        reached.append(True);return result
    canon_io.import_raw=completed_import
if mode=='apply_animation':M.stamp=fail_after_load
elif mode not in ('attach_rig',):
    if mode in ('assign_material','assign_maps','add_node_group','set_world'):SH.stamp=fail_after_load
    else:M.stamp=fail_after_load
try:P.asset_place(asset,mode=mode,target=target,options={'undo_step':False})
except Exception as e:
    assert ('downstream '+mode in str(e)) if mode!='attach_rig' else 'no armature' in str(e),(mode,str(e))
else:raise AssertionError('failure not reached: '+mode)
assert reached==[True]
assert state()==before,(mode,state(),before)
'''.replace('MODE',repr(mode)))
