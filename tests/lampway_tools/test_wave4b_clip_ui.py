# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The animation panel's clip table (specs/mrmak/08 section 6): one row per action, the measured numbers and the proposed name; Apply names is the USER's click and refuses while a script runs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402
from test_wave4b_clip_classify import PRE_CC  # noqa: E402

PRE = PRE_CC + '''
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools import clip_state, human_gate
from mixar.modules.lampway_tools.ui.panels import lampway_panels as PANELS
ob = rig(); walk(ob, "Armature|Action.003")
act(ob, "Armature|Action.004", [(1, (0, 0, 0)), (25, (0, 0, 0))])
bpy.context.view_layer.objects.active = ob; ob.select_set(True)
bpy.context.scene.lampway_tools.clip_height = H
'''


def test_the_table_lists_one_row_per_action_and_apply_is_the_users_click(tmp_path):
    r = run(tmp_path, PRE + '''
res = bpy.ops.lampway.clip_classify()
rows = [dict(a=x["action"], primary=x["primary"], loop=x["loop"], inferred=x["inferred"], label=x["label"]) for x in clip_state.ROWS]
with human_gate.scripting():
    refused = bpy.ops.lampway.clip_apply_names() if False else None
    try:
        bpy.ops.lampway.clip_apply_names(); script_ok = True
    except RuntimeError:
        script_ok = False
names_after_script = sorted(a.name for a in bpy.data.actions)
bpy.ops.lampway.clip_apply_names()
print("RESULT", json.dumps({"op": sorted(res), "rows": rows, "script_ok": script_ok, "after_script": names_after_script, "names": sorted(a.name for a in bpy.data.actions),
                            "msg": bpy.context.scene.lampway_tools.last_message}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert "Error registering class" not in r.out, r.out[r.out.index("Error registering"):][:300]            # a child panel registered before its parent never appears
    d = r.results[0]
    assert d["op"] == ["FINISHED"] and len(d["rows"]) == 2
    walk_row = next(x for x in d["rows"] if x["a"].endswith("003"))
    assert walk_row["primary"] == "walk" and walk_row["loop"] is False and walk_row["inferred"] is False
    assert d["after_script"] == ["Armature|Action.003", "Armature|Action.004"], d                  # a script's apply changed nothing (the user's click only)
    assert "walk" in d["names"], d
