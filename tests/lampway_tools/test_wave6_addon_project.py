# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""addon_project (specs/mixar_docs/addon_project.md) in the real binary: the agent reads and stages patches to a linked add-on project through the Client's own
AddonProjectService; a patch is committed only after the user's click approves that proposal (human_gate refuses the approval from any script), then
checked and installed; rollback restores it; a project outside the linked folder is refused."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

LINK = '''
import bootstrap
for _ in range(100000):                                                     # the UI auto-discovery, as the app does it in batches: registers the operator
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.addon_project.service import get_addon_project_service
from mixar.modules.lampway_tools import human_gate
proj = os.path.join(root, "addons", "lw_hello")
os.makedirs(proj, exist_ok=True)
open(os.path.join(proj, "__init__.py"), "w").write('bl_info = {"name": "LW Hello", "blender": (4, 2, 0), "category": "Object"}\\n\\ndef register():\\n    pass\\n\\ndef unregister():\\n    pass\\n')
svc = get_addon_project_service()
desc = svc.link(proj, name="lw_hello")
PID = desc["project_id"]
OP = """import bpy
class LW_OT_hello(bpy.types.Operator):
    bl_idname = "lw.hello"
    bl_label = "Hello"
    def execute(self, context):
        return {'FINISHED'}
"""
'''


def test_a_patch_needs_the_users_approval_then_commits_installs_and_rolls_back(tmp_path):
    d = one(go(tmp_path, LINK + '''
read = call("addon_read", project="lw_hello", path="__init__.py")
st = call("addon_stage_patch", project="lw_hello", files=[{"path": "hello_op.py", "content": OP}], message="a hello operator")
early = call("addon_commit", project="lw_hello", patch_id=st["patch_id"])
try:
    with human_gate.scripting():                                            # what an agent script sees: the click refuses (an ERROR report raises here)
        scripted = list(bpy.ops.lampway.addon_approve(project_id=PID, proposal_id=st["patch_id"]))
except RuntimeError as exc:
    scripted = ["REFUSED: " + str(exc)]
still = call("addon_commit", project="lw_hello", patch_id=st["patch_id"])
clicked = bpy.ops.lampway.addon_approve(project_id=PID, proposal_id=st["patch_id"])
done = call("addon_commit", project="lw_hello", patch_id=st["patch_id"])
exists = os.path.exists(os.path.join(proj, "hello_op.py"))
tx = done["committed"].get("transaction_id") if done.get("ok") else None
rb = call("addon_rollback", project="lw_hello", to=tx)
print("RESULT", json.dumps({"read": read, "st": st, "early": early, "scripted": scripted, "still": still, "clicked": list(clicked), "done": done,
                            "exists": exists, "rb": rb, "after": os.path.exists(os.path.join(proj, "hello_op.py"))}, default=str))
'''))
    assert d["read"]["ok"] and "bl_info" in d["read"]["files"][0]["content"]
    assert d["st"]["ok"] and d["st"]["patch_id"]
    for k in ("early", "still"):
        assert d[k]["ok"] is False and "only after the captain approves it" in d[k]["error"], k
    assert d["scripted"][0].startswith("REFUSED") and "user's click" in d["scripted"][0] and d["clicked"] == ["FINISHED"]
    assert d["done"]["ok"] and d["exists"] and d["done"]["checks"]["success"] is True
    assert d["rb"]["ok"] and d["after"] is False


def test_a_project_outside_the_linked_folder_is_refused(tmp_path):
    d = one(go(tmp_path, LINK + '''
res = call("addon_read", project="/etc", path="passwd")
other = call("addon_stage_patch", project="not_linked", files=[{"path": "a.py", "content": "x = 1"}])
print("RESULT", json.dumps({"res": res, "other": other}))
'''))
    for k in ("res", "other"):
        assert d[k]["ok"] is False and "inside the Client's add-on projects folder only" in d[k]["error"] and "lw_hello" in d[k]["error"]
