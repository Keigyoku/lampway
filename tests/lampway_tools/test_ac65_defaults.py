# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Authorized starting defaults execute, while retaining their physical proof limit."""
import copy
import numpy as np
import pytest
from mixar.modules.lampway_tools import canon_asset as CA, posing
from mixar.modules.lampway_tools.pipeline import fit_place as FP, fit_glove as FG
from test_canon_pair_scale import pair


def test_default_settings_are_values_with_explicit_untested_provenance():
    for key, value in [('facing_margin', .05), ('pair_scale_group', 'per_side'),
                       ('collar_depth_mm', 20.), ('boots_scale_anchor', 'width')]:
        row = CA.SETTINGS[key]
        assert row['value'] == value
        assert row['physical_status'] == 'untested'
        assert not row.get('needs_decision') and row['source'] and row['why']


def test_omitted_pair_mode_executes_independent_reversible_scales(tmp_path):
    body, piece = pair(tmp_path)
    placed, triangles, meta, report = FP.place('gauntlets', body, piece)
    assert meta['pair_scale_group'] == 'per_side'
    assert meta['defaults']['pair_scale_group']['physical_status'] == 'untested'
    assert not meta.get('pair_scale_needs_decision')
    assert abs(meta['side_transforms']['l']['scale']-meta['side_transforms']['r']['scale']) > .1
    assert np.array_equal(triangles, np.load(piece)['T'])
    assert np.max(np.abs(FP.undo_placement(placed, meta)-np.load(piece)['V'])) < 1e-9


@pytest.mark.parametrize('kind', ['waist', 'boots', 'gauntlets'])
@pytest.mark.parametrize('side', ['l', 'r'])
def test_default_pose_tables_are_complete_bounded_and_side_specific(kind, side):
    result = posing.fit_pose(kind, side=side)
    assert result['ok'] and result['route'] == 'pose_solve'
    table = result['table']
    assert table['physical_status'] == 'untested'
    assert table['dofs'][0]['expect']['joint']
    for row in table['dofs'] + table['chain']:
        assert row['range'][0] <= 0 <= row['range'][1]
        assert 0 < row['step'] <= row['range'][1]-row['range'][0] <= 90
    assert all(r['bones'] and r['threshold_m'] == .002 for r in table['regions'].values())
    if kind != 'waist':
        assert all(b.endswith('_'+side) for r in table['regions'].values() for b in r['bones'])
    if kind == 'gauntlets':
        assert table['curl_side'] == side and table['curl_fractions'] == [0, 1/3, 1/2, 2/3, 1]
        assert 'thumb_03_'+side in table['regions']['piece']['bones']
    changed = copy.deepcopy(table)
    changed['dofs'][0]['range'][0] = -999
    assert posing.fit_pose(kind, side=side)['table'] != changed


def test_unlabelled_glove_still_refuses_default_pose(tmp_path):
    with pytest.raises(FG.GloveError, match='labels'):
        FG.pose(tmp_path, 'glove', 'r', 'arm', 'body', [], [], None, 'fit')


def test_labelled_glove_without_dofs_executes_right_default_and_writes_receipt(tmp_path, monkeypatch):
    FG.labels(tmp_path, 'glove', 'r', ['cap'], {'cap':'index_01_r'}, {'cap':'metal'})
    calls = []
    def solve(kind, piece, body, armature, dofs, chain, regions, **kwargs):
        calls.append((kind, dofs, chain, regions, kwargs))
        return {'ok': True, 'entries': [], 'schema':'lampway.fit-pose/1'}
    monkeypatch.setattr(posing, 'solve_scene', solve)
    result = FG.pose(tmp_path, 'glove', 'r', 'arm', 'body', [], [], None, 'fit')
    assert len(calls) == 1 and calls[0][1][0]['bone'] == 'hand_r'
    assert calls[0][4]['curl_side'] == 'r'
    assert result['defaults']['physical_status'] == 'untested'
    assert result['keypoints']['labels'] == 'independent'
    assert (tmp_path/'fit/glove_pose.json').is_file()


def test_omitted_boot_anchor_runs_real_width_measurement(tmp_path):
    v = np.array([(.1+.04*np.cos(a),.04*np.sin(a),z)
                  for z in np.linspace(0,.5,11) for a in np.arange(16)*2*np.pi/16])
    t = []
    for i in range(10):
        for j in range(16):
            a=i*16+j; b=i*16+(j+1)%16; c=b+16; d=a+16
            t.extend(((a,b,c),(a,c,d)))
    body, piece = tmp_path/'body.npz', tmp_path/'boot.npz'
    np.savez(body, V=v, T=t, J=[[.1,0,.7],[.1,0,.5],[.1,0,.08],[.1,-.06,.02]],
             names=['thigh_l','calf_l','foot_l','ball_l'])
    np.savez(piece, V=v, T=t)
    placed, _, meta, _ = FP.place('boots', body, piece, sides='l')
    explicit, _, chosen, _ = FP.place('boots', body, piece, sides='l', scale_anchor='width')
    assert meta['scale_anchor'] == 'width' and meta['scale'] == chosen['scale']
    assert np.allclose(placed, explicit, atol=1e-12)
    assert meta['defaults']['boots_scale_anchor']['physical_status'] == 'untested'
    with pytest.raises(FP.PlaceError, match='scale_anchor'):
        FP.place('boots', body, piece, sides='l', scale_anchor='guess')


def test_default_facing_registers_actual_plate_and_labels_default_untested(tmp_path):
    from blender_run import run_script
    from test_wave3_weights import PRE
    from test_canon_normalize_facing import FACING
    result = run_script(PRE+FACING+r'''
result = api.normalize_mesh(input="raw",plate=plate,generator="captain_authored",weld="never")
assert result.get('ok'), result
doc = json.loads(raw['lw_canon'])
receipt = json.load(open(os.path.join(root,result['receipt_path'])))
res({'decision':doc['conventions']['frame_decision'], 'setting':receipt['settings']['facing_margin']})
''', env={'LW_KEEP_ROOT':str(tmp_path)}, timeout=300)
    assert result.rc == 0, result.out[-2500:]
    decision = result.results[-1]
    assert decision['decision']['evidence']['margin'] == .05
    assert decision['setting']['physical_status'] == 'untested'


def test_default_table_sign_falsifiers_keep_native_anatomical_direction():
    from mixar.modules.lampway_tools import canon_geom as G
    frame = {'up':[0,0,1], 'forward':[0,-1,0], 'lateral':[1,0,0]}
    for kind in ('waist','boots','gauntlets'):
        for side in ('l','r'):
            expect = posing.fit_pose(kind,side=side)['table']['dofs'][0]['expect']
            direction = np.asarray(G.resolve_axis(expect['along'],{},frame))
            rest = {expect['joint']:[0,0,0]}
            assert G.check_expect(expect, rest, {expect['joint']:direction*.01}, frame)[0]
            assert not G.check_expect(expect, rest, {expect['joint']:-direction*.01}, frame)[0]


def default_skeleton(side):
    """Synthetic straight anatomical hand/leg; no owner-source acceptance claim."""
    ref = {}
    def bone(name, pos, parent=None):
        ref[name] = {'pos':pos, 'parent':parent, 'rot':(0,0,0,1)}
    bone('pelvis',(0,0,1))
    bone('spine_01',(0,0,1.2),'pelvis'); bone('head',(0,0,1.6),'spine_01')
    for s, sign in [('l',1),('r',-1)]:
        bone('thigh_'+s,(sign*.1,0,1),'pelvis')
        bone('calf_'+s,(sign*.1,0,.5),'thigh_'+s)
        bone('foot_'+s,(sign*.1,0,.1),'calf_'+s)
        bone('ball_'+s,(sign*.1,-.15,.1),'foot_'+s)
    sign = 1 if side == 'l' else -1
    bone('lowerarm_'+side,(sign*.5,0,1.3))
    bone('hand_'+side,(sign*.5,0,1.1),'lowerarm_'+side)
    for f,x in zip(('index','middle','ring','pinky','thumb'),(-.03,0,.015,.03,-.05)):
        parent = 'hand_'+side
        for n in (1,2,3):
            name=f'{f}_{n:02d}_{side}'
            bone(name,(sign*(.5+x),0,1.1-.04*n),parent)
            parent=name
    return ref


@pytest.mark.parametrize('side',['l','r'])
@pytest.mark.parametrize('kind',['waist','boots','gauntlets'])
def test_adopted_defaults_drive_real_sweeps_and_reversed_sign_refuses(kind, side):
    from mixar.modules.lampway_tools.pipeline import pose_solve as PS
    ref=default_skeleton(side)
    table=posing.fit_pose(kind,side=side)['table']
    samples=[(np.asarray(t['pos'])+[.005,0,0], b) for b,t in ref.items()]
    piece=(np.asarray([[3,3,3],[4,3,3],[3,4,3]]),np.asarray([[0,1,2]]))
    frame={'up':(0,0,1),'forward':(0,-1,0),'lateral':(1,0,0)}
    kwargs={'curl_side':table.get('curl_side',''),'curl_fractions':table.get('curl_fractions')}
    result=PS.solve(ref,frame,samples,piece,table['dofs'],table['chain'],table['regions'],**kwargs)
    assert result['sign_check']['moved_cm']>0
    assert result['posed']['piece']['samples']>0
    bad=copy.deepcopy(table['dofs'])
    along=bad[0]['expect']['along']
    bad[0]['expect']['along']=along[1:] if along.startswith('-') else '-'+along
    with pytest.raises(PS.PoseError,match='sign check failed'):
        PS.solve(ref,frame,samples,piece,bad,table['chain'],table['regions'],**kwargs)


def test_native_independently_labelled_glove_executes_default_pose(tmp_path):
    import json
    from blender_run import run_script
    from test_wave3_weights import PRE
    ref=default_skeleton('r')
    script=PRE+'\nimport numpy as np\nref=json.loads('+repr(json.dumps(ref))+')\n'+r'''
arm=armature('default_rig',[(n,t['pos'],tuple(np.asarray(t['pos'])+[0,0,.015]),t['parent']) for n,t in ref.items()])
me=bpy.data.meshes.new('skin');points=[];faces=[];bones=[]
for name,t in ref.items():
    k=len(points); p=np.asarray(t['pos'])
    points.extend([p+(.005,0,0),p+(.005,.005,0),p+(.005,0,.005)])
    faces.append((k,k+1,k+2));bones.extend([name]*3)
me.from_pydata(points,[],faces);me.update();skin=bpy.data.objects.new('skin',me);bpy.context.scene.collection.objects.link(skin)
for name in ref:
    skin.vertex_groups.new(name=name).add([i for i,n in enumerate(bones) if n==name],1,'REPLACE')
skin.modifiers.new('rig','ARMATURE').object=arm
me=bpy.data.meshes.new('glove');me.from_pydata([(3,3,3),(4,3,3),(3,4,3)],[],[(0,1,2)]);me.update()
piece=bpy.data.objects.new('glove',me);bpy.context.scene.collection.objects.link(piece)
piece.vertex_groups.new(name='cap').add([0,1,2],1,'REPLACE')
from mixar.modules.lampway_tools import posing as PO
PO.stamp_placement(piece,{'scale':1.,'translation':[0,0,0],'turn_deg':0.})
labels=api.fit_glove('labels',piece='glove',side='r',labels={'cap':'index_01_r'},roles={'cap':'metal'})
assert labels.get('ok'),labels
before=[list(b.matrix_basis) for b in arm.pose.bones]
glove=api.fit_glove('pose',piece='glove',side='r',body_object='skin',armature='default_rig')
public=api.fit_pose('gauntlets',piece='glove',body='skin',armature='default_rig',side='r')
res({'glove':glove,'public':public,'unchanged':before==[list(b.matrix_basis) for b in arm.pose.bones]})
'''
    result=run_script(script,env={'LW_KEEP_ROOT':str(tmp_path)},timeout=300)
    assert result.rc==0,result.out[-2500:]
    result=result.results[-1]
    for name in ('glove','public'):
        receipt=result[name]
        assert receipt.get('ok'),receipt
        assert receipt['sign_check']['moved_cm']>0
        assert receipt['defaults']['physical_status']=='untested'
        assert any(s['stage']=='finger_curl_to' for s in receipt['sweeps'])
    assert result['glove']['keypoints']=={'source':'body_joints','side':'r','labels':'independent'}
    assert result['unchanged']


def test_generated_ac65_judgment_golden_pins_production_defaults_and_tables():
    import json
    from pathlib import Path
    case_path=Path(__file__).resolve().parents[2]/'docs/canon/goldens/C15_ac65_defaults/case.json'
    assert case_path.is_file(), 'AC65 selected defaults need a committed generated golden'
    case=json.loads(case_path.read_text())
    assert case['physical_status']=='untested'
    for key,value in case['settings'].items():
        assert CA.SETTINGS[key]['value']==value
        assert CA.SETTINGS[key]['physical_status']==case['physical_status']
    for kind,sides in case['tables'].items():
        for side,expected in sides.items():
            actual=posing.fit_pose(kind,side=side)['table']
            assert {k:actual[k] for k in expected}==expected
            if kind=='gauntlets':
                from mixar.modules.lampway_tools.pipeline import finger_pose
                entries=finger_pose.entries(default_skeleton(side),side,1)
                assert len(entries)==15
                for row in entries:
                    segment=int(row['bone'].split('_')[1])
                    assert row['target_deg']==case['finger_curl_target_deg'][segment-1]
