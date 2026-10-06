# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The captain's rename in the real binary: a file saved while the agent-first workspace was still called "Zen Mode"
reopens with that same workspace named "Lamplight" (its layout and contents kept)."""

from blender_run import run_script

SAVE = r'''
import bpy, json, sys
path = sys.argv[sys.argv.index("--") + 1]
for ws in list(bpy.data.workspaces):
    if ws.name == "Lamplight":
        ws.name = "Zen Mode"          # as Mixar named it
ws = bpy.data.workspaces.get("Zen Mode") or bpy.data.workspaces[0]
ws.name = "Zen Mode"
ws["lampway_probe"] = 7
bpy.ops.wm.save_as_mainfile(filepath=path)
print("RESULT " + json.dumps({"saved": sorted(w.name for w in bpy.data.workspaces)}))
'''

OPEN = r'''
import bpy, json, sys
path = sys.argv[sys.argv.index("--") + 1]
bpy.ops.wm.open_mainfile(filepath=path)
names = sorted(w.name for w in bpy.data.workspaces)
lit = bpy.data.workspaces.get("Lamplight")
print("RESULT " + json.dumps({"names": names, "probe": lit.get("lampway_probe") if lit else None}))
'''


def test_a_file_saved_in_zen_mode_reopens_in_lamplight(tmp_path):
    blend = tmp_path / "old.blend"
    saved = run_script(SAVE, args=(blend,))
    assert saved.rc == 0 and "Zen Mode" in saved.results[0]["saved"], saved.out[-2000:]
    opened = run_script(OPEN, args=(blend,))
    assert opened.rc == 0, opened.out[-2000:]
    found = opened.results[0]
    assert "Zen Mode" not in found["names"] and "Lamplight" in found["names"], found
    assert found["probe"] == 7, "the renamed workspace is the one the file had, not a new one"
