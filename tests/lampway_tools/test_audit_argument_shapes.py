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
