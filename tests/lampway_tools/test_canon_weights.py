# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon_geom skin-weight primitives against canon 07 (goldens C03, C04 and G07.3-G07.6).

The remap / dress cases are Titan's tools/test_weight_profile.py, ported with their numbers; falloff is Titan's hand_pose."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from canon_support import J, goldens, obj  # noqa: E402,F401
from mixar.modules.lampway_tools import canon_geom as G  # noqa: E402

PARENTS = {"pelvis": None, "spine_01": "pelvis", "thigh_l": "pelvis", "calf_l": "thigh_l", "foot_l": "calf_l", "thigh_r": "pelvis", "calf_r": "thigh_r"}


# ------------------------------------------------------------------ G07.1 / C04: weld before the fill
def _edges(F):
    return [(a, b) for f in F for a, b in zip(f, list(f[1:]) + [f[0]])]


def test_c04_the_welded_fill_weights_every_vertex_and_duplicates_are_bit_identical(goldens):
    V, F, *_ = obj(goldens, "C04_weld_inpaint/piece.obj")
    mt, exp = J(goldens, "C04_weld_inpaint/matches.json"), J(goldens, "C04_weld_inpaint/expected.json")["welded_fill"]
    keys = G.weld_keys(V, mt["weld_m"])
    W = G.inpaint_harmonic(len(V), _edges(F), np.array(mt["matched"]), np.array(mt["W_matched"]), keys=keys)
    assert int((W.sum(1) < 1e-6).sum()) == exp["unweighted_vertices"]
    dup = [(i, j) for i in range(len(V)) for j in range(i + 1, len(V)) if keys[i] == keys[j]]
    assert len(dup) == exp["duplicate_pairs_bit_identical"] and all(np.array_equal(W[i], W[j]) for i, j in dup)
    assert np.abs(W.sum(1) - 1).max() < exp["sums_to_one_tol"] + 1e-9


def test_c04_falsifier_the_index_graph_fill_leaves_island_b_unweighted(goldens):
    V, F, *_ = obj(goldens, "C04_weld_inpaint/piece.obj")
    mt, exp = J(goldens, "C04_weld_inpaint/matches.json"), J(goldens, "C04_weld_inpaint/expected.json")
    W = G.inpaint_harmonic(len(V), _edges(F), np.array(mt["matched"]), np.array(mt["W_matched"]), keys=None)
    assert int((W.sum(1) < 1e-6).sum()) == exp["unwelded_index_graph_fill"]["unweighted_vertices"]


def test_the_fill_keeps_matched_rows_fixed_and_reaches_the_average_of_its_neighbours():
    edges = [(0, 1), (1, 2)]
    W = G.inpaint_harmonic(3, edges, np.array([True, False, True]), np.array([[1.0, 0], [0, 0], [0, 1.0]]))
    assert np.allclose(W, [[1, 0], [0.5, 0.5], [0, 1]], atol=1e-6)


# ------------------------------------------------------------------ G07.2 / C03: positional weights keep the seam shut
def test_c03_weights_by_position_keep_the_ledger_pairs_together_and_per_part_bones_open_them(goldens):
    V, F, _, _, groups = obj(goldens, "C03_seam_tube/piece.obj")
    rig, exp = J(goldens, "C03_seam_tube/rig.json"), J(goldens, "C03_seam_tube/expected.json")
    pairs = np.array(rig["seam_pairs_source_ledger"])
    head = np.array(rig["bones"]["spine_03"]["head"])
    c, s = np.cos(np.radians(rig["pose"]["spine_03"]["deg"])), np.sin(np.radians(rig["pose"]["spine_03"]["deg"]))
    Mt = np.eye(4)
    Mt[:3, :3] = [[c, -s, 0], [s, c, 0], [0, 0, 1]]
    Mt[:3, 3] = head - Mt[:3, :3] @ head
    mats = np.array([np.eye(4), Mt])
    Wpos = G.band_weights(V, cut_point=head, axis=(0, 0, 1), width=0.10)                # by position only: [behind, ahead]
    posed = G.lbs(V, Wpos, mats)
    assert np.abs(posed[pairs[:, 0]] - posed[pairs[:, 1]]).max() <= exp["positional_weights"]["tol"]
    upper = sorted({v for k in groups["upper"] for v in F[k]})
    Wpart = np.zeros((len(V), 2))
    Wpart[:, 0] = 1
    Wpart[upper] = [0, 1]
    gap = np.linalg.norm(G.lbs(V, Wpart, mats)[pairs[:, 0]] - G.lbs(V, Wpart, mats)[pairs[:, 1]], axis=1).max()
    assert gap == pytest.approx(exp["per_part_bones"]["seam_gap_max_m"], abs=1e-6)


# ------------------------------------------------------------------ G07.4: restrict by the nearest allowed ancestor
def test_an_allowed_bone_keeps_itself_and_the_rest_go_to_their_nearest_allowed_ancestor_else_the_fallback():
    t = G.remap_table(PARENTS, ["thigh_l", "calf_l"], fallback="thigh_l")
    assert t["calf_l"] == "calf_l" and t["foot_l"] == "calf_l" and t["thigh_l"] == "thigh_l"
    assert t["pelvis"] == "thigh_l" and t["calf_r"] == "thigh_l"


def test_without_a_fallback_a_bone_with_no_allowed_ancestor_is_refused_by_name():
    with pytest.raises(ValueError, match="pelvis"):
        G.remap_table(PARENTS, ["thigh_l"])


def test_patterns_expand_and_a_pattern_matching_nothing_or_a_fallback_outside_is_refused():
    assert G.remap_table(PARENTS, ["*_l"], fallback="thigh_l")["foot_l"] == "foot_l"
    with pytest.raises(ValueError, match="hand_"):
        G.remap_table(PARENTS, ["*_l", "hand_*"], fallback="thigh_l")
    with pytest.raises(ValueError):
        G.remap_table(PARENTS, ["calf_l"], fallback="pelvis")


def test_g07_4_the_canon_case():
    parents = {"pelvis": None, "spine_01": "pelvis", "spine_03": "spine_01", "upperarm_l": "spine_03", "lowerarm_l": "upperarm_l"}
    t = G.remap_table(parents, ["spine_0*", "upperarm_*"], fallback="spine_01")
    assert t["lowerarm_l"] == "upperarm_l" and t["pelvis"] == "spine_01"
    with pytest.raises(ValueError):
        G.remap_table(parents, ["spine_0*", "upperarm_*"])


def test_remap_rows_sum_per_target_normalise_and_refuse_a_zero_row_by_vertex():
    names = ["calf_l", "foot_l", "pelvis", "thigh_l"]
    t = G.remap_table(PARENTS, ["thigh_l", "calf_l"], fallback="thigh_l")
    W = np.array([[0.5, 0.3, 0.2, 0.0], [0.2, 0.2, 0.0, 0.0]])
    out, targets = G.remap_rows(W, names, t)
    got = [dict(zip(targets, row)) for row in out]
    assert got[0]["calf_l"] == pytest.approx(0.8) and got[0]["thigh_l"] == pytest.approx(0.2) and got[1]["calf_l"] == pytest.approx(1.0)
    with pytest.raises(G.ZeroWeightError) as e:
        G.remap_rows(np.array([[0.5, 0.5, 0, 0], [0, 0, 0, 0]]), names, t)
    assert e.value.vertices == [1]


# ------------------------------------------------------------------ G07.3: dress by rule
def _dress(pts, follow=0.6):
    return G.dress(pts, top=1.0, hem=0.5, left_x=0.1, right_x=-0.1, follow=follow, names=("pelvis", "thigh_l", "thigh_r"))


def test_g07_3_dress_the_canon_points():
    a, b, c = _dress([(0.1, 0, 0.5), (0, 0, 0.75), (0, 0, 1.2)])
    assert a == pytest.approx({"pelvis": 0.4, "thigh_l": 0.6})
    assert b == pytest.approx({"pelvis": 0.7, "thigh_l": 0.15, "thigh_r": 0.15})
    assert c == {"pelvis": 1.0}


def test_g07_3_falsifier_a_linear_ramp_is_wrong_at_z_0_6():
    w = _dress([(0.1, 0, 0.6)])[0]
    assert w["thigh_l"] == pytest.approx(0.6 * 0.896, abs=1e-12)
    assert abs(w["thigh_l"] - 0.6 * 0.8) > 0.05                      # the linear ramp's value


def test_dress_halfway_is_eased_and_bad_bounds_are_refused():
    assert _dress([(-0.1, 0, 0.875)])[0]["thigh_r"] == pytest.approx(0.6 * 0.15625, abs=1e-12)
    with pytest.raises(ValueError):
        G.dress([], top=0.5, hem=0.5, left_x=0.1, right_x=-0.1, follow=0.5, names=("p", "l", "r"))
    with pytest.raises(ValueError):
        _dress([], follow=1.5)


# ------------------------------------------------------------------ G07.6: continuous falloff
# Three parallel bones: a on the z axis, b at x = 4 mm, c at y = 4 mm. On the line x = y the point is as far from b as from c,
# so the SECOND-nearest bone changes there; a step across it is where the two-nearest rule jumps.
SEGS = {"a": ((0.0, 0, 0), (0.0, 0, 1)), "b": ((0.004, 0, 0), (0.004, 0, 1)), "c": ((0.0, 0.004, 0), (0.0, 0.004, 1))}
P0 = np.array([0.001, 0.001, 0.5])
ACROSS = np.array([1.0, -1.0, 0.0]) / np.sqrt(2)


def _jump(fn, step):
    r0, r1 = fn(tuple(P0 - ACROSS * step / 2)), fn(tuple(P0 + ACROSS * step / 2))
    return max(abs(r1.get(k, 0) - r0.get(k, 0)) for k in SEGS)


def test_g07_6_falloff_is_continuous_where_the_second_nearest_bone_changes():
    f = lambda p: G.falloff_weights(p, SEGS, 0.006)                      # noqa: E731
    assert _jump(f, 1e-6) < 1e-3 and _jump(f, 1e-9) < 1e-6              # the jump shrinks with the step: continuous
    assert len(f(tuple(P0))) == 3 and abs(sum(f(tuple(P0)).values()) - 1) < 1e-12


def test_g07_6_falsifier_the_two_nearest_rule_jumps():
    def two_nearest(p):
        d = {k: float(np.linalg.norm(np.cross(np.subtract(p, s[0]), (0, 0, 1)))) for k, s in SEGS.items()}
        a, b = sorted(d, key=d.get)[:2]
        wa, wb = 1 / d[a], 1 / d[b]
        return {a: wa / (wa + wb), b: wb / (wa + wb)}
    assert _jump(two_nearest, 1e-9) > 0.1


def test_falloff_is_the_nearest_bone_alone_out_of_reach():
    segs = {"a": ((0.0, 0, 0), (0.0, 0, 1)), "b": ((0.1, 0, 0), (0.1, 0, 1))}
    assert G.falloff_weights((0.01, 0, 0.5), segs, 0.006) == {"a": 1.0}


# ------------------------------------------------------------------ canon 07 B.5: rigid parts fused to cloth/leather (Titan hand_pose)
def test_b5_the_rigidity_eases_in_by_smoothstep_over_the_fade():
    w = G.rigid_blend({"index_03": 1.0}, {"index_02": 0.00125}, fade=0.005)          # a quarter of the fade: smoothstep(0.75)
    assert w["index_02"] == pytest.approx(0.84375, abs=1e-12) and w["index_03"] == pytest.approx(0.15625, abs=1e-12)


def test_b5_on_the_plate_and_at_its_seam_the_plates_bone_alone_past_the_fade_the_field():
    assert G.rigid_blend({"spine_03": 0.5, "spine_01": 0.5}, {"spine_01": 0.0}, fade=0.005) == {"spine_01": 1.0}
    assert G.rigid_blend({"spine_03": 0.25, "spine_01": 0.75}, {"pelvis": 0.006}, fade=0.005) == {"spine_01": 0.75, "spine_03": 0.25}


def test_b5_strict_two_different_rigid_anchors_at_one_point_are_refused():
    with pytest.raises(ValueError, match="conflicting rigid anchors"):
        G.rigid_blend({"spine_03": 1.0}, {"spine_01": 0.0, "pelvis": 0.0}, fade=0.005)
    with pytest.raises(ValueError, match="fade"):
        G.rigid_blend({"spine_03": 1.0}, {"spine_01": 0.0}, fade=0.0)


def test_normalized_metahuman_corrective_segments_are_consumable_by_weight_plan(tmp_path):
    from issue2_native import run_issue_case
    from test_canon_normalize_rigged import RIG
    run_issue_case(tmp_path, RIG+'''
bpy.ops.wm.read_factory_settings(use_empty=True)
for side,sign in (('l',1),('r',-1)):
    for i,finger in enumerate(('thumb','index','middle','ring','pinky')):
        for joint in (1,2,3):
            name=f'{finger}_{joint:02d}_{side}';J[name]=(sign*(.40+.025*joint),.015*(i-2),.60)
            P[name]=f'{finger}_{joint-1:02d}_{side}' if joint>1 else f'hand_{side}'
J['upperarm_correctiveRoot_l']=J['upperarm_l'];P['upperarm_correctiveRoot_l']='upperarm_l'
for tag,dy in (('fwd',-.02),('bck',.02)):
    name='upperarm_'+tag+'_l';J[name]=(.13,dy,.86);P[name]='upperarm_correctiveRoot_l'
arm=build('mh_rig')
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT');arm.data.edit_bones['upperarm_correctiveRoot_l'].roll=math.radians(120);bpy.ops.object.mode_set(mode='OBJECT')
r=call('normalize_rigged',armature=arm.name,profile='metahuman',dry_run=False);assert r.get('ok'),r
from mixar.modules.lampway_tools.features import weights as W
segments=W.bone_segments(arm)
rows={b['name']:b for b in json.loads(arm['lw_canon'])['body']['bones']};row=rows['upperarm_correctiveRoot_l']
a,b=segments[row['name']];expected=np.array(row['head_m'])+np.array(row['along'])*row['length_m']
assert np.allclose(b,expected,atol=1e-8),(b,expected)
piece=sphere('garment',2)
r=call('weight_audit',action='plan',object=piece.name,armature=arm.name)
assert r.get('ok'),r
bpy.context.view_layer.objects.active=arm;bpy.ops.object.mode_set(mode='EDIT');arm.data.edit_bones[row['name']].roll+=.2;bpy.ops.object.mode_set(mode='OBJECT')
try:W.bone_segments(arm)
except Exception as e:assert 'rest frames changed' in str(e) and 'normalize_rigged' in str(e),e
else:raise AssertionError('stale corrective frame accepted')
del arm['lw_canon']
try:W.bone_segments(arm)
except ValueError as e:assert 'no named continuation' in str(e),e
else:raise AssertionError('unstamped corrective tail was guessed')
''')
