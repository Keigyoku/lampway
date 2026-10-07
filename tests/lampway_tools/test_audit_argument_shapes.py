# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Audit F12 (2026-10-06): malformed arguments are refused by name with the shape the tool wants, never a raw Python exception
(lampway_project_views raised TypeError, lampway_model_compare "AttributeError: 'str' object has no attribute 'get'")."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

RAW = ("TypeError", "AttributeError", "KeyError", "IndexError")


def test_malformed_shapes_are_refused_with_the_shape_wanted(tmp_path):
    r = run(tmp_path, '''
sphere("s")
cases = {
    "views_list": call("project_views", object="s", views=["Front"]),
    "views_none": call("project_views", object="s", views=None),
    "views_path": call("project_views", object="s", views={"Front": 7}),
    "set_list": call("model_compare", action="stats", set=["a.glb", "b.glb"]),
    "models_str": call("model_compare", action="stats", set={"models": ["a.glb", "b.glb"]}),
    "set_str": call("model_compare", action="build", set="a.glb"),
}
print("RESULT", json.dumps(cases))
''')
    assert r.rc == 0, r.out[-2500:]
    for name, out in r.results[0].items():
        assert out["ok"] is False, (name, out)
        assert not out["error"].startswith(RAW), (name, out["error"])
    res = r.results[0]
    assert "views" in res["views_list"]["error"] and "Front" in res["views_list"]["error"]
    assert "set" in res["set_list"]["error"] and "models" in res["set_list"]["error"]
    assert "file" in res["models_str"]["error"]


def test_tag_layers_need_a_piece_set_up_and_add_nothing_without_one(tmp_path):
    """Audit F21: lampway_qa_tag_layers {} added annotation layers to a scene with nothing to tag. It edits only for a piece that
    is set up (the named piece, else the active one), and says how to set one up."""
    r = run(tmp_path, '''
sphere("s")
out = call("qa_tag_layers")
ann = bpy.context.scene.annotation
print("RESULT", json.dumps({"out": out, "layers": [l.info for l in ann.layers] if ann else []}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert d["out"]["ok"] is False and "qa_setup" in d["out"]["error"], d["out"]
    assert d["layers"] == []


def test_a_scene_cleanup_plan_is_a_page_with_totals(tmp_path):
    """Audit F8: a scene_cleanup plan answered 351-369 KB. The plan is a page of objects (limit, default 50, from offset) with the
    object count, the next offset and the scene's totals per issue; full=true answers every object."""
    r = run(tmp_path, '''
for i in range(60):
    bpy.ops.mesh.primitive_cube_add(location=(i * 3, 0, 0)); bpy.context.active_object.name = f"c{i:02d}"
page = call("scene_cleanup")
rest = call("scene_cleanup", offset=50)
full = call("scene_cleanup", full=True)
print("RESULT", json.dumps({"n": len(page["report"]), "count": page.get("object_count"), "next": page.get("next_offset"), "totals": page.get("totals"),
                            "rest": [x["object"] for x in rest["report"]], "rest_next": rest.get("next_offset"), "full": len(full["report"])}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert d["n"] == 50 and d["count"] == 60 and d["next"] == 50 and d["totals"]["ngons"] == 0, d
    assert d["rest"] == [f"c{i:02d}" for i in range(50, 60)] and d["rest_next"] is None and d["full"] == 60
