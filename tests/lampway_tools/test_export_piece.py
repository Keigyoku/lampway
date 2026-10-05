# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The export (PIECE_PIPELINE step 15): FBX + Textures/ + README into <out_dir>, from the client, by name. The look is
judged in the engine, so the README says what each map is (ORM order, normal convention) and carries every file's sha256.
REAL binary, the synthetic sphere piece."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_api import PRE  # noqa: E402


def test_export_writes_the_fbx_the_textures_and_a_readme_with_hashes(tmp_path):
    src = PRE.replace("ROOT", repr(str(tmp_path))) + '''
from PIL import Image
import numpy as np
os.makedirs(root + "/maps", exist_ok=True)
for n in ("BaseColor_32.png", "ORM_32.png", "Normal_DX_32.png"):
    Image.fromarray(np.zeros((32, 32, 3), np.uint8)).save(root + "/maps/" + n)
res = api.call("export_piece", json.dumps({"object": "piece", "out_dir": "export/piece1",
    "textures": ["maps/BaseColor_32.png", "maps/ORM_32.png", "maps/Normal_DX_32.png"], "note": "chest, mp_live"}))
bad = api.call("export_piece", json.dumps({"object": "nope", "out_dir": "export/x"}))
out = root + "/export/piece1"
print("RESULT", json.dumps({"res": res, "bad": bad, "files": sorted(os.path.relpath(os.path.join(dp, f), out) for dp, dn, fn in os.walk(out) for f in fn),
                            "readme": open(out + "/README.md").read() if os.path.exists(out + "/README.md") else "",
                            "fbx_bytes": os.path.getsize(out + "/piece.fbx") if os.path.exists(out + "/piece.fbx") else 0}))
'''
    r = run_script(src, env={"LAMPWAY_PROJECT_ROOT": str(tmp_path), "LAMPWAY_HOME": str(tmp_path / "home")})
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["res"]["ok"] is True, res["res"]
    assert res["files"] == ["README.md", "Textures/BaseColor_32.png", "Textures/Normal_DX_32.png", "Textures/ORM_32.png", "piece.fbx"]
    assert res["fbx_bytes"] > 1000
    readme = res["readme"]
    assert "piece.fbx" in readme and "ORM" in readme and "DirectX" in readme and "chest, mp_live" in readme
    assert all(f in readme for f in ("BaseColor_32.png", "ORM_32.png", "Normal_DX_32.png")) and "sha256" in readme
    assert res["bad"]["ok"] is False and "nope" in res["bad"]["error"]
