# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Disposable native measurements: actual world placement, explicit limits, no defaults."""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[2]


def test_body_context_placement_and_signed_limits_in_native_copy(tmp_path):
    binary=Path(os.environ.get('LAMPWAY_BIN','/workspace/lampway/build/Prod/bin/mixar'))
    if not binary.exists():pytest.skip('isolated native binary unavailable')
    script=tmp_path/'test.py'
    source=os.environ.get('LAMPWAY_DECISION_MEASURE_SOURCE',str(ROOT/'src/scripts/mixar/modules/lampway_tools/pipeline/decision_measure.py'))
    script.write_text(f"import sys, importlib.util\nimport mixar.modules.lampway_tools as lt\nlt.__path__=[{str(ROOT/'src/scripts/mixar/modules/lampway_tools')!r}]\n"
                      "for name in ('canon_io','canon_geom'):\n sys.modules.pop('mixar.modules.lampway_tools.'+name,None)\n if hasattr(lt,name):delattr(lt,name)\n"
                      f"spec=importlib.util.spec_from_file_location('mixar.modules.lampway_tools.pipeline.decision_measure',{source!r})\nD=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)\n"+r'''
import json, hashlib, numpy as np, bpy, os
from pathlib import Path
root=Path(os.environ.get('LAMPWAY_DECISION_RECEIPT_DIR',bpy.app.tempdir));root.mkdir(parents=True,exist_ok=True)
# Outward cube in an offset world frame: a render that recentres each object hides this test.
V=np.array([[2,0,0],[3,0,0],[3,1,0],[2,1,0],[2,0,1],[3,0,1],[3,1,1],[2,1,1]],float)
T=np.array([[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])
np.savez(root/'body.npz',V=V,T=T)
np.savez(root/'context-body.npz',V=V,T=T)
context={'npz':'context-body.npz','views':['Front'],'bounds_m':[[1.5,-.5,-.5],[4,1.5,1.5]]}
B,BT,identity=D._body_context(root,context)
P=np.array([[3.1,.5,.5],[2.9,.5,.5]])
limits={'min_signed_m':.05,'max_below_min_vertices':0}
r=D._vertex_clearance(P,B,BT,limits)
assert not r['pass'] and r['below_min_vertices']==1 and r['inside_vertices']==1,r
assert abs(r['min_signed_m']+.1)<1e-6,r
assert D._vertex_clearance(P,B,BT,{**limits,'max_below_min_vertices':1})['pass']
splitV=B[BT].reshape(-1,3);splitT=np.arange(len(splitV)).reshape(-1,3)
split=D._vertex_clearance(P,splitV,splitT,limits)
assert split['boundary_edges']==0 and split['raw_boundary_edges']>0 and split['below_min_vertices']==1,split
# Real posed/current-copy object must retain evaluated world placement.
me=bpy.data.meshes.new('body_copy');me.from_pydata(V.tolist(),[],T.tolist());me.update()
ob=bpy.data.objects.new('body_copy',me);bpy.context.scene.collection.objects.link(ob);ob.location.x=2
bpy.context.view_layer.update()
BV,_,_=D._body_context(root,{'object':'body_copy','metres_per_unit':1,'views':['Front'],'bounds_m':context['bounds_m']})
assert np.allclose(BV,V+[2,0,0]),BV
try:D._body_context(root,{'object':'absent','views':['Front'],'bounds_m':context['bounds_m']})
except ValueError:pass
else:raise AssertionError('missing requested body context accepted')
try:D._body_context(root,{'npz':'../outside.npz','views':['Front'],'bounds_m':context['bounds_m']})
except ValueError:pass
else:raise AssertionError('path escape accepted')
try:D._vertex_clearance(P,B,BT,{})
except ValueError:pass
else:raise AssertionError('invented acceptance limits')
try:D._vertex_clearance(P,B,BT[:-1],limits)
except ValueError:pass
else:raise AssertionError('open body without band accepted')
band=D._vertex_clearance(np.array([[2,.5,.5]]),B,BT[:-1],{**limits,'body_open_band_m':.01})
assert band['pass'] is None and band['status']=='REFUSED_OPENING_BAND',band
# A small candidate sits to the RIGHT of the body. Both remain visible in the fixed frame.
PV=V*.15+[3.15,.35,.35]
image=root/'context.png'
before=set(bpy.data.objects)
receipt=D._capture_context(PV,T,B,BT,context,128,image)
assert set(bpy.data.objects)==before,'temporary render objects leaked'
from PIL import Image
A=np.asarray(Image.open(image).convert('RGBA'))
body=(A[:,:,2]>A[:,:,0]+30)&(A[:,:,3]>0)
piece=(A[:,:,0]>A[:,:,2]+30)&(A[:,:,3]>0)
assert body.sum()>20 and piece.sum()>5,(body.sum(),piece.sum())
# Front camera uses -Y, so world +X lies to image right.
assert np.nonzero(piece)[1].mean()>np.nonzero(body)[1].mean()
assert receipt['body_and_candidate_visible'] and receipt['camera_bounds_m']==context['bounds_m']
# Public job result: missing requested context is an execution refusal; a measured
# failed acceptance remains execution-ok. Placement is supplied explicitly here.
bad=D.measure({'body_relative_views':True,'jobs':[{'id':'missing','action':'pair','args':{}}]},root)
assert not bad['jobs'][0]['ok'] and 'body_context' in bad['jobs'][0]['error'],bad
from mixar.modules.lampway_tools.pipeline import fit_place
saved=fit_place.place
try:
    fit_place.place=lambda *a,**k:(PV,T,{'fixture':'explicit placed world vertices'}, {})
    np.savez(root/'piece.npz',V=PV,T=T)
    pack=D.measure({'body_context':context,'clearance_acceptance':{'min_signed_m':.5,'max_below_min_vertices':0},
                    'image_size':64,'max_samples':2,'jobs':[{'id':'known','action':'pair','args':{'kind':'gauntlets','body':'body.npz','piece':'piece.npz',
                    'turn':0,'clear_mm':0,'pair_scale_group':'common'}}]},root)
    job=pack['jobs'][0]
    assert job['ok'] and job['acceptance']['pass'] is False and job['acceptance']['full_fit_acceptance'] is None,job
    assert job['placement_inputs']['body']=={'path':'body.npz','source_sha256':hashlib.sha256((root/'body.npz').read_bytes()).hexdigest()},job
    assert job['placement_inputs']['piece']=={'path':'piece.npz','source_sha256':hashlib.sha256((root/'piece.npz').read_bytes()).hexdigest()},job
    assert job['placement_inputs']['args']=={'kind':'gauntlets','turn':0,'clear_mm':0,'sides':'both','pair_scale_group':'common','scale_anchor':None},job
    for c in job['candidates']:
        assert c['body_relative_capture']['body_identity']['npz']=='context-body.npz',c
        assert c['placed_sha256']==hashlib.sha256((root/c['placed']).read_bytes()).hexdigest(),c
    # A changed source must not silently inherit the earlier receipt's identity.
    def changed_source(*args,**kwargs):
        np.savez(root/'piece.npz',V=PV+[1,0,0],T=T)
        return PV,T,{},{}
    fit_place.place=changed_source
    changed=D.measure({'image_size':64,'max_samples':2,'jobs':[{'id':'changed','action':'pair','args':{'kind':'gauntlets','body':'body.npz','piece':'piece.npz'}}]},root)
    assert not changed['jobs'][0]['ok'] and 'changed during measurement' in changed['jobs'][0]['error'],changed
finally:fit_place.place=saved
print('RESULT',json.dumps({'vertex_clearance':r,'body_pixels':int(body.sum()),'candidate_pixels':int(piece.sum()),'capture':receipt}))
(root/'native-body-context-receipt.json').write_text(json.dumps({'vertex_clearance':r,'capture':receipt},indent=2))
''')
    env=dict(os.environ,HOME=str(tmp_path),XDG_CONFIG_HOME=str(tmp_path/'config'),LAMPWAY_HOME=str(tmp_path/'home'),TMPDIR=str(tmp_path))
    run=subprocess.run([str(binary),'--background','--factory-startup','--python',str(script)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
    assert run.returncode==0,run.stdout[-5000:]
    lines=[l[7:] for l in run.stdout.splitlines() if l.startswith('RESULT ')]
    assert lines,run.stdout[-5000:]
    (tmp_path/'receipt.json').write_text(json.dumps(json.loads(lines[-1]),indent=2)+'\n')


def test_cli_summary_keeps_completed_failed_acceptance_separate(tmp_path,monkeypatch,capsys):
    import importlib.util
    import sys
    import types
    config=tmp_path/'config.json'
    config.write_text(json.dumps({'project_root':str(tmp_path)}))
    fake=types.ModuleType('mixar.modules.lampway_tools.pipeline.decision_measure')
    fake.measure=lambda *a:{'schema':'test','jobs':[{'id':'measured','ok':True,'acceptance':{'pass':False,'full_fit_acceptance':None}}]}
    monkeypatch.setitem(sys.modules,fake.__name__,fake)
    spec=importlib.util.spec_from_file_location('measurement_cli',ROOT/'scripts/lampway/measure_fit_decisions.py')
    cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
    assert cli.main(['--config',str(config)])==0
    printed=json.loads(capsys.readouterr().out)
    assert printed['failed']==[] and printed['acceptance']['measured']['pass'] is False
