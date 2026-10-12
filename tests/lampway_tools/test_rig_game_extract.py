# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_game_extract (specs/canon/rig_tools/rig_game_extract.md; canon 19 B.4), REAL binary, golden G19.4: the 9-bone probe rig (5 deform, 4
control, one spine bone carrying 4 constraints) gives a 5-bone game rig with ALL 5 in the Deform collection (GRT 4.3.0 left 1 of 5: the
collection reset ran inside the per-bone loop), the hierarchy per mode (keep / rigify_fix / flat), the spine's four constraints gone and the
two lotrot constraints on every bone, the meshes re-pointed with their world matrix kept, and the game rig following the control (world
error ~0). B-Bones are refused, or converted to one bone per segment with the bendy bone's weights split between its segments."""

from features_support import run

PROBE = '''
def probe(name="ctl", bbone=False):
    rows = [("root", None, (0, 0, 0), (0, 0.2, 0), False), ("ORG-hips", "root", (0, 0, 0.95), (0, 0, 1.05), False),
            ("ctrl-spine", "root", (0, 0.3, 1.1), (0, 0.4, 1.1), False), ("ORG-chest", "root", (0, 0, 1.25), (0, 0, 1.40), False),
            ("DEF-hips", "ORG-hips", (0, 0, 0.95), (0, 0, 1.05), True), ("DEF-spine", "DEF-hips", (0, 0, 1.05), (0, 0, 1.25), True),
            ("DEF-chest", "DEF-spine", (0, 0, 1.25), (0, 0, 1.40), True), ("DEF-neck", "ORG-chest", (0, 0, 1.40), (0, 0, 1.50), True),
            ("DEF-head", "DEF-neck", (0, 0, 1.50), (0, 0, 1.70), True)]
    arm = bpy.data.armatures.new(name); ob = link(bpy.data.objects.new(name, arm))
    bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
    for n, p, h, t, d in rows:
        e = arm.edit_bones.new(n); e.head, e.tail, e.use_deform = h, t, d
        if p: e.parent = arm.edit_bones[p]
    if bbone:
        arm.edit_bones["DEF-spine"].bbone_segments = 4
    bpy.ops.object.mode_set(mode="OBJECT")
    sp = ob.pose.bones["DEF-spine"]
    for kind in ("COPY_ROTATION", "DAMPED_TRACK", "LIMIT_ROTATION", "STRETCH_TO"):
        c = sp.constraints.new(kind)
        if hasattr(c, "target"): c.target = ob; c.subtarget = "ctrl-spine" if kind == "COPY_ROTATION" else "ORG-chest"
    sp.constraints["Copy Rotation"].influence = 0.3
    me = bpy.data.meshes.new(name + "_skin"); vs = []
    for k, (n, p, h, t, d) in enumerate(rows):
        if d:
            for f in (0.125, 0.375, 0.625, 0.875):
                z = h[2] + f * (t[2] - h[2]); vs += [(0.05, 0, z), (-0.05, 0, z), (0, 0.05, z)]
    me.from_pydata(vs, [], [(i, i + 1, i + 2) for i in range(0, len(vs), 3)]); m = link(bpy.data.objects.new(name + "_skin", me))
    for k, n in enumerate([r[0] for r in rows if r[4]]):
        g = m.vertex_groups.new(name=n); g.add(list(range(12 * k, 12 * k + 12)), 1.0, "REPLACE")
    mod = m.modifiers.new("Armature", "ARMATURE"); mod.object = ob; m.parent = ob
    return ob, m
def world(o):
    return {b.name: o.matrix_world @ b.matrix for b in o.pose.bones}
'''


def test_g19_4_all_five_deform_bones_kept_in_the_collection_constrained_and_meshes_repointed(tmp_path):
    r = run(tmp_path, PROBE + '''
ctl, skin = probe()
mw0 = [list(r) for r in skin.matrix_world]
cold = call("rig_game_extract", full=True, control="ctl")
call("rig_inspect", armature="ctl")
dry = call("rig_game_extract", full=True, control="ctl", dry_run=True)
g = call("rig_game_extract", full=True, control="ctl", hierarchy="rigify_fix")
game = bpy.data.objects.get("ctl_game")
ctl.pose.bones["ctrl-spine"].location = (0, 0.05, 0.02); ctl.pose.bones["ORG-hips"].rotation_quaternion = (0.966, 0.259, 0, 0)
bpy.context.view_layer.update()
wc, wg = world(ctl), world(game)
err = max((wc[n].translation - wg[n].translation).length for n in wg)
rot = max(wc[n].to_quaternion().rotation_difference(wg[n].to_quaternion()).angle for n in wg)
cols = {c.name: sorted(b.name for b in c.bones) for c in game.data.collections_all}
cons = {pb.name: sorted(c.type for c in pb.constraints) for pb in game.pose.bones}
par = {b.name: b.parent.name if b.parent else None for b in game.data.bones}
k = call("rig_game_extract", full=True, control="ctl", name="ctl_keep", hierarchy="keep", rebind_meshes=False)
f = call("rig_game_extract", full=True, control="ctl", name="ctl_flat", hierarchy="flat", constraint="transform", rebind_meshes=False)
pk = {b.name: b.parent.name if b.parent else None for b in bpy.data.objects["ctl_keep"].data.bones}
pf = {b.name: b.parent.name if b.parent else None for b in bpy.data.objects["ctl_flat"].data.bones}
cf = {pb.name: sorted(c.type for c in pb.constraints) for pb in bpy.data.objects["ctl_flat"].pose.bones}
taken = call("rig_game_extract", full=True, control="ctl", name="ctl_skin")
print("RESULT", json.dumps({"cold": cold, "dry": dry, "g": g, "err": err, "rot": math.degrees(rot), "cols": cols, "cons": cons, "par": par, "pk": pk, "pf": pf,
    "cf": cf, "taken": taken, "mod": skin.modifiers["Armature"].object.name, "parent": skin.parent.name, "mw": [list(r) for r in skin.matrix_world], "mw0": mw0,
    "ctl_cons": len(ctl.pose.bones["DEF-spine"].constraints), "anim": bool(game.animation_data)}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["cold"]["ok"] is False and "rig_inspect" in o["cold"]["error"], o["cold"]
    assert o["dry"]["ok"] and o["dry"]["dry_run"] is True and o["dry"]["bones"]["kept"] == ["DEF-chest", "DEF-head", "DEF-hips", "DEF-neck", "DEF-spine"], o["dry"]
    g = o["g"]
    assert g["ok"] and g["collection_members"] == g["bones"]["kept"] and len(g["bones"]["kept"]) == 5, g
    assert o["cols"] == {"Deform": ["DEF-chest", "DEF-head", "DEF-hips", "DEF-neck", "DEF-spine"]}, "all five in the collection (GRT: 1 of 5)"
    assert all(v == ["COPY_LOCATION", "COPY_ROTATION"] for v in o["cons"].values()), o["cons"]
    assert o["par"] == {"DEF-hips": None, "DEF-spine": "DEF-hips", "DEF-chest": "DEF-spine", "DEF-neck": "DEF-chest", "DEF-head": "DEF-neck"}, o["par"]
    assert o["pk"]["DEF-neck"] is None and o["pk"]["DEF-head"] == "DEF-neck", "keep: the nearest kept ancestor (none above ORG-chest)"
    assert set(o["pf"].values()) == {None} and all(v == ["COPY_TRANSFORMS"] for v in o["cf"].values()), (o["pf"], o["cf"])
    assert o["err"] < 1e-5 and o["rot"] < 0.01, "the game rig follows the control"
    assert g["follow"]["max_position_m"] < 1e-5 and g["follow"]["max_rotation_deg"] < 0.01, g["follow"]
    assert o["mod"] == "ctl_game" and o["parent"] == "ctl_game" and o["mw"] == o["mw0"] and g["meshes_repointed"] == ["ctl_skin"]
    assert o["ctl_cons"] == 4 and o["anim"] is False, "the control keeps its constraints; the game rig carries no animation"
    assert o["taken"]["ok"] is False and "ctl_skin" in o["taken"]["error"], o["taken"]


def test_bbones_are_refused_or_converted_with_their_weights_split_between_segments(tmp_path, tail=False):
    r = run(tmp_path, PROBE + f"from mixar.modules.lampway_tools.features import rig_game as _RG; _RG.TAIL_JOINT_BONE = {tail}\n" + '''
ctl, skin = probe(bbone=True); call("rig_inspect", armature="ctl")
base = skin.copy(); base.data = skin.data.copy(); base.name = "baseline"; base.parent = None; base.matrix_world = skin.matrix_world
base.modifiers.remove(base.modifiers["Armature"]); bpy.context.scene.collection.objects.link(base)   # unbound: the tool leaves it alone
refused = call("rig_game_extract", full=True, control="ctl", rebind_meshes=False)
sb = ctl.data.bones["DEF-spine"]                      # a curve to follow: the spine's handles are the hips and the chest
sb.bbone_handle_type_start = sb.bbone_handle_type_end = "ABSOLUTE"
sb.bbone_custom_handle_start, sb.bbone_custom_handle_end = ctl.data.bones["DEF-hips"], ctl.data.bones["DEF-chest"]
conv = call("rig_game_extract", full=True, control="ctl", bbones="convert", constraint="transform")
game = bpy.data.objects["ctl_game"]
base.modifiers.new("Armature", "ARMATURE").object = ctl                                              # the baseline: the bendy bone itself
par = {b.name: b.parent.name if b.parent else None for b in game.data.bones}
groups = sorted(g.name for g in skin.vertex_groups)
for b, q in (("DEF-hips", (0.985, 0.174, 0, 0)), ("DEF-chest", (0.985, -0.122, 0.122, 0))):
    ctl.pose.bones[b].rotation_quaternion = q
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
def ev(o):
    e = o.evaluated_get(dg); m = e.to_mesh(); out = [tuple(o.matrix_world @ v.co) for v in m.vertices]; e.to_mesh_clear(); return out
after, before = ev(skin), ev(base)
drift = max(max(abs(a - b) for a, b in zip(p, q)) for p, q in zip(before, after))
print("RESULT", json.dumps({"refused": refused, "conv": conv, "par": par, "groups": groups, "drift": drift}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["refused"]["ok"] is False and "DEF-spine" in o["refused"]["error"] and "convert" in o["refused"]["error"], o["refused"]
    c = o["conv"]
    last = 4 if tail else 3
    assert c["ok"] and c["bbones_converted"] == {"DEF-spine": [f"DEF-spine_seg{i}" for i in range(last + 1)]}, c
    assert o["par"]["DEF-spine_seg1"] == "DEF-spine_seg0" and o["par"]["DEF-chest"] == f"DEF-spine_seg{last}" and "DEF-spine" not in o["par"], o["par"]
    assert "DEF-spine_seg2" in o["groups"] and "DEF-spine" not in o["groups"], o["groups"]
    if tail:
        assert o["drift"] < 1e-6, "with the tail joint as a bone the conversion is exact (Blender blends joints k and k+1)"
    else:
        # the spec's one bone per segment: the tail joint's share rides the last segment (measured 1.87 mm on this probe)
        assert 1e-4 < o["drift"] < 2.5e-3, o["drift"]


def test_the_tail_joint_bone_makes_the_bbone_conversion_exact(tmp_path):
    """The reversal seam (rig_game.TAIL_JOINT_BONE): one more bone at the tail joint and the skin is Blender's own B-Bone deformation."""
    test_bbones_are_refused_or_converted_with_their_weights_split_between_segments(tmp_path, tail=True)


def test_large_rig_default_receipt_is_bounded_and_detailed_pages_keep_totals(tmp_path):
    from issue2_isolated import run as isolated
    out = isolated(tmp_path, '''
arm=bpy.data.armatures.new('many'); ob=bpy.data.objects.new('many',arm); bpy.context.collection.objects.link(ob)
bpy.context.view_layer.objects.active=ob; ob.select_set(True); bpy.ops.object.mode_set(mode='EDIT')
for i in range(160):
    b=arm.edit_bones.new('bone_%03d'%i); b.head=(i*.01,0,0); b.tail=(i*.01,0,1)
bpy.ops.object.mode_set(mode='OBJECT')
assert call('rig_inspect',armature='many')['ok']
a=call('rig_game_extract',control='many',dry_run=True)
b=call('rig_game_extract',control='many',dry_run=True,full=True,offset=50,limit=10)
print('RESULT '+json.dumps({'a':a,'b':b,'bytes':len(json.dumps(a).encode())}))
''')[0]
    assert out['a']['ok'] and out['bytes'] < 12000, out
    assert len(out['a']['bones']['kept']) == 50
    assert out['a']['pages']['bones.kept']['total'] == 160
    assert out['b']['ok'] and len(out['b']['bones']['kept']) == 10
    assert 'hierarchy_changes' in out['b']


def test_bbone_conversion_segment_lists_stay_paged_with_full_detail(tmp_path):
    from issue2_isolated import run as isolated
    out = isolated(tmp_path, '''
from mixar.modules.lampway_tools.features import rig_game
rig_game.extract=lambda *args: {'control':'ctl','game':'game','bones':{'kept':[],'dropped':[]},'bbones_converted':{'bend':['segment_%03d'%i for i in range(160)]}}
a=call('rig_game_extract',control='ctl',full=True)
b=call('rig_game_extract',control='ctl',full=True,offset=50,limit=10)
print('RESULT '+json.dumps({'a':a,'b':b}))
''')[0]
    assert out['a']['ok'] and out['b']['ok'], out
    assert len(out['a']['bbones_converted']['bend']) == 50
    assert out['a']['pages']['bbones_converted.bend']['total'] == 160
    assert out['b']['bbones_converted']['bend'][0] == 'segment_050'
    assert len(out['b']['bbones_converted']['bend']) == 10
