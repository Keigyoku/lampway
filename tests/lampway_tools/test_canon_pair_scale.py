# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""D4: explicit independent side scales retain proper similarities and vertex identities."""
import numpy as np
import pytest
from test_canon_item5_place import _arm_body_and_gauntlet
from mixar.modules.lampway_tools.pipeline import fit_place as FP


def pair(tmp_path):
    body, piece = _arm_body_and_gauntlet(tmp_path, 15)
    b, p = np.load(body), np.load(piece)
    Vb, Tb, J = b['V'], b['T'], b['J']
    Vp, Tp = p['V'], p['T']
    reflected_body = Vb * [-1, 1, 1]
    reflected_piece = Vp * [-1, 1, 1]
    center = reflected_piece.mean(0)
    reflected_piece = (reflected_piece-center)*1.5+center
    np.savez(body, V=np.r_[Vb, reflected_body], T=np.r_[Tb, Tb[:, ::-1]+len(Vb)],
             J=np.r_[J, J*[-1, 1, 1]], names=np.array(list(b['names'])+[n[:-1]+'r' for n in b['names']]))
    np.savez(piece, V=np.r_[Vp, reflected_piece], T=np.r_[Tp, Tp[:, ::-1]+len(Vp)])
    return body, piece


def test_explicit_independent_pair_scales_are_measured_and_reversible(tmp_path):
    body, piece = pair(tmp_path)
    V, T, meta, report = FP.place('gauntlets', body, piece, pair_scale_group='per_side')
    raw = np.load(piece)
    assert np.array_equal(T, raw['T'])
    assert meta['pair_scale_group'] == 'per_side'
    assert meta['scale'] is None
    assert abs(meta['side_transforms']['l']['scale']-meta['side_transforms']['r']['scale']) > .1
    from mixar.modules.lampway_tools import canon_geom as G
    for side, tr in meta['side_transforms'].items():
        ids = tr['vertex_ids']
        fit = G.similarity_fit(raw['V'][ids], V[ids])
        assert fit['max'] < 1e-8 and fit['s'] == pytest.approx(tr['scale'])
    assert report['round_trip_m'] < 1e-9


def test_explicit_common_pair_scale_is_one_similarity_and_unknown_mode_refuses(tmp_path):
    body, piece = pair(tmp_path)
    V, T, meta, report = FP.place('gauntlets', body, piece, pair_scale_group='common')
    assert meta['pair_scale_group'] == 'common' and meta['scale'] > 0
    with pytest.raises(FP.PlaceError, match='pair_scale_group'):
        FP.place('gauntlets', body, piece, pair_scale_group='guess')


def test_independent_pair_maps_reach_the_real_scene_object(tmp_path):
    import json
    from blender_run import run_script
    from test_wave3_weights import PRE
    body, piece = pair(tmp_path)
    b, p = np.load(body), np.load(piece)
    data = {k: p[k].tolist() for k in ('V','T')}
    body_data = {k: b[k].tolist() for k in ('V','T','J','names')}
    script = PRE + '\nimport numpy as np\npair_data = '+repr(data)+'\nbody_data = '+repr(body_data)+r'''
np.savez(os.path.join(root,'pair.npz'),V=pair_data['V'],T=pair_data['T'])
np.savez(os.path.join(root,'body.npz'),V=body_data['V'],T=body_data['T'],J=body_data['J'],names=body_data['names'])
me=bpy.data.meshes.new('pair');me.from_pydata(pair_data['V'],[],pair_data['T']);me.update()
ob=bpy.data.objects.new('pair',me);bpy.context.scene.collection.objects.link(ob)
r=api.fit_place('gauntlets',piece='pair.npz',body='body.npz',object='pair',pair_scale_group='per_side')
assert r.get('ok'),r
W=np.array([v.co[:] for v in ob.data.vertices]);target=np.load(r['placed'])['V']
res({'max_error':float(np.abs(W-target).max()),'receipt':r})
'''
    result = run_script(script, env={'LW_KEEP_ROOT':str(tmp_path)}, timeout=300)
    assert result.rc == 0,result.out[-3000:]
    got = result.results[-1]
    assert got['max_error'] < 1e-6
    assert got['receipt']['object']['pair_scale_group'] == 'per_side'
    assert set(got['receipt']['object']['groups']) == {'l','r'}
    (tmp_path/'pair-proof.json').write_text(json.dumps(got,indent=2)+'\n')
