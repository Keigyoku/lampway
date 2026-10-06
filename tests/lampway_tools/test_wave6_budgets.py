# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""part_budget_plan and platform_budget_check (specs/wiki/part_budget_plan.md, platform_budget_check.md) in the real binary: parts checked against the CAPTAIN's
budget table (none is built in), and an asset against a named platform's documented limits from a dated data table (stale after 90 days)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

TABLE = [{"role": "hero", "camera_distance_m": [0, 5], "max_tris": 30000, "texture_px": 2048},
         {"role": "prop", "camera_distance_m": [0, 50], "max_tris": 2000, "texture_px": 512},
         {"role": "accessory", "camera_distance_m": [0, 10], "max_tris": 500, "texture_px": 256}]

TEX = '''
def textured(ob, px):
    img = bpy.data.images.new(ob.name + "_tex", px, px)
    mat = bpy.data.materials.new(ob.name + "_mat"); mat.use_nodes = True
    n = mat.node_tree.nodes.new("ShaderNodeTexImage"); n.image = img
    ob.data.materials.append(mat)
'''


def test_an_over_budget_part_fails_and_the_rest_pass(tmp_path):
    d = one(go(tmp_path, TEX + f'''
sphere("helmet", 0.3, subdiv=5)                                     # 5120 triangles (Blender counts subdivisions from 1 = 20 faces)
sphere("cup", 0.1, subdiv=3); textured(bpy.data.objects["cup"], 1024)  # 320 triangles, a 1024 px texture for a 512 px budget
boxes("ring", [((0, 0, 0), (0.1, 0.1, 0.02))])                      # 12 triangles
res = call("part_budget_plan", table={TABLE!r}, parts=[{{"object": "helmet", "role": "hero", "camera_distance_m": 2}},
                                                       {{"object": "cup", "role": "prop", "camera_distance_m": 20}},
                                                       {{"object": "ring", "role": "accessory", "camera_distance_m": 3}}])
over = call("part_budget_plan", table={TABLE!r}, parts=[{{"object": "helmet", "role": "accessory", "camera_distance_m": 3}}])
print("RESULT", json.dumps({{"res": res, "over": over}}))
'''))
    rows = {r["object"]: r for r in d["res"]["parts"]}
    assert rows["helmet"]["tris"] == 5120 and rows["helmet"]["budget"] == 30000 and rows["helmet"]["pass"] is True
    assert rows["cup"]["texture_px"] == 1024 and rows["cup"]["budget_px"] == 512 and rows["cup"]["pass"] is False and rows["cup"]["over_by"] == 0
    assert rows["ring"]["tris"] == 12 and rows["ring"]["pass"] is True and rows["ring"]["texture_px"] is None
    o = d["over"]["parts"][0]
    assert o["pass"] is False and o["over_by"] == 5120 - 500 and d["over"]["pass"] is False


def test_a_missing_table_role_or_distance_is_refused(tmp_path):
    d = one(go(tmp_path, f'''
sphere("ball", 0.2, subdiv=2)
none = call("part_budget_plan", parts=[{{"object": "ball", "role": "prop", "camera_distance_m": 1}}])
role = call("part_budget_plan", table={TABLE!r}, parts=[{{"object": "ball", "role": "background", "camera_distance_m": 1}}])
far = call("part_budget_plan", table={TABLE!r}, parts=[{{"object": "ball", "role": "hero", "camera_distance_m": 30}}])
print("RESULT", json.dumps({{"none": none, "role": role, "far": far}}))
'''))
    assert d["none"]["ok"] is False and "the budget table is the captain's: none is built in (the wiki gives examples only)" in d["none"]["error"]
    assert d["role"]["ok"] is False and "background" in d["role"]["error"] and "hero" in d["role"]["error"]
    assert d["far"]["ok"] is False and "30" in d["far"]["error"]


def test_roblox_rigid_over_4k_tris_fails_and_a_small_watertight_mesh_passes(tmp_path):
    d = one(go(tmp_path, '''
sphere("big", 0.3, subdiv=5)
sphere("small", 0.3, subdiv=2)
canon("big")
big = call("platform_budget_check", object="big", platform="roblox_rigid")
canon("small")
small = call("platform_budget_check", object="small", platform="roblox_rigid")
print("RESULT", json.dumps({"big": big, "small": small}))
'''))
    big = {c["name"]: c for c in d["big"]["checks"]}
    assert big["tris"]["value"] == 5120 and big["tris"]["limit"] == 4000 and big["tris"]["pass"] is False and d["big"]["pass"] is False
    assert d["small"]["pass"] is True and d["small"]["limits_retrieved"] == "2026-10-05" and d["small"]["stale"] is False
    assert {c["name"] for c in d["small"]["checks"]} >= {"tris", "texture_px", "watertight", "single_mesh"}


def test_custom_table_works_stale_limits_are_flagged_and_unknown_platforms_list_the_known(tmp_path):
    d = one(go(tmp_path, '''
ob = sphere("ball", 0.3, subdiv=2)
bm = bmesh.new(); bm.from_mesh(ob.data); bm.faces.ensure_lookup_table(); bmesh.ops.delete(bm, geom=[bm.faces[0]], context="FACES"); bm.to_mesh(ob.data); bm.free()   # one hole
canon("ball")
custom = call("platform_budget_check", object="ball", platform="custom", limits={"max_tris": 1000, "max_texture_px": 1024, "watertight": True, "max_weights": 4, "retrieved": "2026-09-30"})
canon("ball")
stale = call("platform_budget_check", object="ball", platform="custom", limits={"max_tris": 1000, "retrieved": "2025-01-01"})
canon("ball")
nolimits = call("platform_budget_check", object="ball", platform="custom")
canon("ball")
unknown = call("platform_budget_check", object="ball", platform="steam_workshop")
print("RESULT", json.dumps({"custom": custom, "stale": stale, "nolimits": nolimits, "unknown": unknown}))
'''))
    c = {x["name"]: x for x in d["custom"]["checks"]}
    assert c["tris"]["pass"] is True and c["watertight"]["pass"] is False and d["custom"]["pass"] is False and d["custom"]["stale"] is False
    assert d["stale"]["stale"] is True and "re-read" in d["stale"]["stale_note"]
    assert d["nolimits"]["ok"] is False and "limits" in d["nolimits"]["error"]
    assert d["unknown"]["ok"] is False and "roblox_rigid" in d["unknown"]["error"] and "roblox_layered" in d["unknown"]["error"]
