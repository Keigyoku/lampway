# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Audit F8 (2026-10-06): replies are bounded. scene_summary answered 203 KB for 1,016 objects (3-7 s). The server's own script,
run in the real binary: a page of objects (default 100) with the totals and the next offset; full=true answers everything."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from blender_run import run_script  # noqa: E402
from lampway_server.agent.tools import SCENE_SUMMARY, script_for  # noqa: E402


def _summary(args):
    setup = "import bpy\nfor _o in list(bpy.data.objects): bpy.data.objects.remove(_o)\n" \
            "for _i in range(150):\n    bpy.context.scene.collection.objects.link(bpy.data.objects.new(f'e{_i:03d}', None))\n"
    r = run_script(setup + script_for(SCENE_SUMMARY, args) + "\nimport json\nprint('RESULT', json.dumps(__RESULT__))\n")
    assert r.rc == 0, r.out[-2000:]
    return r.results[0]


def test_scene_summary_pages_its_objects_with_totals():
    first = _summary({})
    assert first["object_count"] == 150 and len(first["objects"]) == 100 and first["next_offset"] == 100
    rest = _summary({"offset": 100, "limit": 100})
    assert [o["name"] for o in rest["objects"]] == [f"e{i:03d}" for i in range(100, 150)] and rest.get("next_offset") is None
    assert len(_summary({"full": True})["objects"]) == 150
