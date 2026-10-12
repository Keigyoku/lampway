# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The admitted candidate never becomes a completed fit stage without review."""
import json
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src/scripts'))
from mixar.modules.lampway_tools.pipeline import fit_order as F
import numpy as np
import pytest


def setup_record(tmp_path):
    p = tmp_path / 'chest/fit/fit.json'
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({'schema': 'lampway.fit/1', 'piece': 'chest', 'kind': 'chest',
        'roles': {'plate': 'metal', 'sleeve': 'cloth'}, 'body': {'package': 'body', 'package_sha256': 'b'*64},
        'stages': [{'stage': s} for s in F.STAGES[:F.STAGES.index('conform')]]}))
    return p


def test_candidate_solve_is_executable_without_recording_conform_success(tmp_path):
    p = setup_record(tmp_path)
    calls = []
    def engine(**args):
        calls.append(args)
        return {'ok': True, 'candidate_pending_review': True, 'object': 'chest_conform', 'candidate_sha256': 'c'*64}
    seam = {'conform_call': engine} if 'conform_call' in inspect.signature(F.run).parameters else {}
    r = F.run('conform', 'chest', str(tmp_path), lambda *a: {'ok': True},
              args={'object': 'chest', 'source': 'source', 'armature': 'rig', 'parts': ['sleeve'],
                    'clearance_m': .002, 'seam_limit_m': .001}, **seam)
    assert r['ok'] and r['candidate_pending_review'], r
    assert r['next_args']['piece'] == 'chest' and r['next_args']['args']['captain_seen'] is False
    assert calls[0]['roles'] == {'plate': 'metal', 'sleeve': 'cloth'}
    assert calls[0]['body_package_sha256'] == 'b'*64
    assert 'conform' not in [s['stage'] for s in json.loads(p.read_text())['stages']]
    assert F.run('bind', 'chest', str(tmp_path), lambda *a: {'ok': True})['ok'] is False


def test_conform_accept_requires_review_and_binds_only_accepted_candidate(tmp_path):
    p = setup_record(tmp_path)
    def engine(**args):
        return {'ok': True, 'object': 'chest_conform', 'candidate_sha256': 'c'*64}
    args = {'action': 'accept', 'candidate_sha256': 'c'*64}
    r = F.run('conform', 'chest', str(tmp_path), lambda *a: {'ok': True}, args=args, conform_call=engine)
    assert not r['ok'] and 'captain' in r['error']
    args.update(captain_seen=True, render_sha256='a'*64)
    r = F.run('conform', 'chest', str(tmp_path), lambda *a: {'ok': True}, args=args, conform_call=engine)
    assert r['ok'], r
    assert json.loads(p.read_text())['stages'][-1]['object'] == 'chest_conform'
    calls = []
    def call(t, a):
        calls.append((t, a))
        return {'ok': True}
    bad = F.run('bind', 'chest', str(tmp_path), call, args={'piece': 'old_mesh'})
    assert not bad['ok'] and not calls
    assert F.run('bind', 'chest', str(tmp_path), call)['ok']
    assert calls[-1][1]['piece'] == 'chest_conform'


def test_metal_selection_and_unknown_parts_never_reach_candidate_engine(tmp_path):
    setup_record(tmp_path)
    calls = []
    for part in ('plate', 'invented'):
        r = F.run('conform', 'chest', str(tmp_path), lambda *a: {'ok': True},
                  args={'parts': [part]}, conform_call=lambda **a: calls.append(a))
        assert not r['ok']
    assert not calls


def test_validate_and_export_follow_returned_candidate_identity(tmp_path):
    setup_record(tmp_path)
    F.run('conform','chest',str(tmp_path),lambda *a:{'ok':True},
          args={'action':'accept','captain_seen':True,'render_sha256':'a'*64,'candidate_sha256':'c'*64},
          conform_call=lambda **a:{'ok':True,'object':'chest_conform','candidate_sha256':'c'*64})
    calls=[]
    def call(t,a):
        calls.append((t,a))
        if t=='fit_body':return {'ok':True,'package_sha256':'b'*64}
        if t=='fit_bind' and a.get('stage')=='return':return {'ok':True,'object':'chest_conform_rest'}
        return {'ok':True}
    assert F.run('bind','chest',str(tmp_path),call)['ok']
    assert F.run('weights','chest',str(tmp_path),call)['ok']
    calls.clear()
    assert not F.run('validate','chest',str(tmp_path),call,args={'bound':'old_mesh'})['ok'] and not calls
    assert F.run('validate','chest',str(tmp_path),call)['ok']
    assert calls[-1][1]['bound']=='chest_conform_rest'
    calls.clear()
    assert not F.run('export','chest',str(tmp_path),call,args={'object':'old_mesh'})['ok'] and not calls
    assert F.run('export','chest',str(tmp_path),call)['ok']
    assert calls[-1][1]['object']=='chest_conform_rest'


def test_clear_component_anchors_are_identity_and_collision_handles_are_retained():
    from mixar.modules.lampway_tools.features.fit_conform import _anchor_clear_components
    from mixar.modules.lampway_tools.pipeline.soft_conform import solve_arap
    v = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
    t = np.array([[0,1,2],[0,3,1],[0,2,3],[1,3,2]])
    P = np.concatenate([v, v + [3.,0.,0.]])
    T = np.concatenate([t, t + 4])
    handles = {i: P[i] + [0.,0.,.01] for i in range(4)}
    _anchor_clear_components(P, T, np.ones(8, bool), np.empty((0,2),int), handles)
    result, metrics = solve_arap(P, T, np.ones(8,bool), handles)
    np.testing.assert_array_equal(result[4:], P[4:])
    np.testing.assert_allclose(result[:4], P[:4]+[0.,0.,.01], atol=1e-15)
    assert metrics['physical_status'] == 'untested'


@pytest.mark.parametrize('setting', [{'invented': 1}, {'max_iterations': 0}, {'linear_tol': float('nan')},
                                    {'max_handle_updates': False}, {'target_padding_m': 0}])
def test_invalid_solver_settings_refuse_before_native_allocation(tmp_path, setting):
    from mixar.modules.lampway_tools.features import fit_conform as FC
    with pytest.raises(ValueError):
        FC.run(root=str(tmp_path),out_dir='out',body='body',body_package_sha256='b'*64,
               roles={'cloth':'cloth'},parts=['cloth'],clearance_m=.002,seam_limit_m=.001,solver=setting)
    assert not (tmp_path / 'out').exists()
