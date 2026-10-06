# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The mesh-object tools the wave5 merge (704eba5) brought, behind real Needs (the coordinator: "declare consumes= honestly for every tool
you can"): each refuses a RAW mesh with "normalize first" before doing anything, and its Need is the one its own lane stated
(orphan_doors.CONSUMES: absolute thresholds in metres or millimetres need real scale, adjacency needs a welded mesh). REAL binary."""

import pytest

from features_support import run

TOOLS = {
    "uv_check": {"object": "raw"},
    "render_condition_passes": {"objects": ["raw"]},
    "parts_material_slots": {"object": "raw", "recipe": "r.json"},
    "zone_sheet": {"object": "raw"},
    "mesh_region_extract": {"object": "raw", "region": {"kind": "bbox", "min": [-1, -1, -1], "max": [1, 1, 1]}},
    "mesh_local_edit": {"object": "raw", "region": {"kind": "bbox", "min": [-1, -1, -1], "max": [1, 1, 1]}},
    "mesh_join_boolean": {"op": "fuse", "objects": ["raw", "raw"]},
    "multi_piece_material": {"action": "plan", "pieces": ["raw"]},
    "face_rig_validate": {"object": "raw"},
    "lod_chain": {"object": "raw"},
    "platform_budget_check": {"object": "raw", "platform": "roblox_rigid"},
    "print_check": {"object": "raw"},
    "print_prep": {"object": "raw", "target_height_mm": 50},
}


def test_each_converted_tool_refuses_a_raw_mesh_and_names_its_normalizer(tmp_path):
    body = '''
from mixar.modules.lampway_tools import canon_io
ob = boxes("raw", [((0, 0, 0.5), (0.4, 0.3, 1.0))]); ob["lw_raw"] = json.dumps({"sha256": "0" * 64})
out = {}
for name, kw in TOOLS.items():
    r = call(name, **kw)
    out[name] = {"ok": r.get("ok"), "error": str(r.get("error", ""))[:200], "help": (r.get("help") or [""])[0]}
print("RESULT", json.dumps(out))
'''.replace("TOOLS", repr(TOOLS))
    r = run(tmp_path, body)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    bad = {n: v for n, v in d.items() if not (v["ok"] is False and v["error"].startswith("normalize first") and v["help"].startswith("lampway_normalize_mesh"))}
    assert not bad, bad
