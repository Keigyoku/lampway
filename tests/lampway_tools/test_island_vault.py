# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The island's Library tab on the Asset Vault (specs/asset_library/asset_ui_editor.md surface C, test 10.4): the pane's file rows (``mixar_generations_files``) gain the
Vault's pictures and clips from ONE query that is the editor's own payload; folder files stay; nothing runs on the main thread; meshes are left to the Vault editor (the C++
tile has no mesh kind)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE = '''
import bpy, json
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.agent_bubble.core import library_media as LM
from mixar.modules.agent_bubble.core import library_vault as LV
from mixar.modules.asset_library.core import session as SES
from mixar.modules.lampway_tools import library_client as LC
calls = []
ROOT = ROOT_DIR
PAGE = {"items": [{"id": "i1", "kind": "image", "name": "greaves_front", "path": ROOT + "/front.png", "thumb": ROOT + "/front.png"},
                  {"id": "v1", "kind": "video", "name": "walk", "path": ROOT + "/walk.mp4", "thumb": None},
                  {"id": "m1", "kind": "mesh", "name": "greaves", "path": ROOT + "/g.glb", "thumb": None},
                  {"id": "x1", "kind": "image", "name": "gone", "path": None, "thumb": None}], "total": 4, "facets": {}, "cursor": None}
def fake(method, path, body=None, timeout=60):
    calls.append([method, path, body])
    return {"data": PAGE}
LC._request = fake
SES.PUMP.spawn = lambda job: job()
'''


def test_the_vault_rows_join_the_island_files_from_the_editors_own_query(tmp_path):
    (tmp_path / "front.png").write_bytes(b"x")
    (tmp_path / "walk.mp4").write_bytes(b"x")
    r = run(tmp_path, PRE.replace("ROOT_DIR", repr(str(tmp_path))) + '''
wm = bpy.context.window_manager
LV.poll(force=True)
before = [f.library for f in wm.mixar_generations_files]
SES.PUMP.tick()
LM.refresh(bpy.context, force=True)
rows = [[f.library, f.name, f.kind, f.path] for f in wm.mixar_generations_files]
again = LV.poll()
print("RESULT", json.dumps({"calls": calls, "editor_payload": SES.VM.payload(), "before": before, "rows": rows, "again": again}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert len(d["calls"]) == 1 and d["calls"][0][:2] == ["POST", "/api/v1/library/query"]
    assert d["calls"][0][2] == d["editor_payload"], "one query: the island asks exactly what the editor asks"
    assert d["before"] == [], "the answer lands on the tick, not in the call"
    assert d["rows"] == [["Asset Vault", "greaves_front", "IMAGE", str(tmp_path / "front.png")], ["Asset Vault", "walk", "VIDEO", str(tmp_path / "walk.mp4")]], d["rows"]
    assert d["again"] is False, "throttled: a second poll right away sends nothing"
