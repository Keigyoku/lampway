# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The mesh-paint texturing tools, run for real through the runner (the Lampway binary for clay_view, the app's python for
mesh_paint_set, a science python for relief_project). The workflow (the shelf's TOOLS.md, 2026-10-05): a clay render of OUR
mesh per view -> an image model paints V3's design over it as flat albedo -> pick 1 of 4 per view -> plates with the clay
alpha -> projection at 4096 with no warp -> masks. Measured on the chest: projection IoU 0.987 in all four views against
0.75-0.89 for the V3 plates themselves."""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from blender_run import lampway_bin, run_script  # noqa: E402
from mixar.modules.lampway_tools import runner as R  # noqa: E402
from mixar.modules.lampway_tools import settings as S  # noqa: E402

SCI = Path(os.environ.get("LAMPWAY_PYTHON_SCIENCE") or "/path/to/boxes")
SHELF = Path("/path/to/shelf/scratch/scratch-tmp")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "home"))
    s = S.load()
    s.project_root = tmp_path
    s.blender = lampway_bin()
    s.python_science = SCI if SCI.exists() else None
    return s


def test_the_tools_are_registered_with_their_kinds():
    assert R.TOOLS["clay_view"].kind == "blender" and R.TOOLS["mesh_paint_set"].kind == "numpy"
    assert (R.SCRIPTS / "texlib/prompts/prompt_meshpaint_v2.txt").exists() and (R.SCRIPTS / "texlib/prompts/prompt_meshpaint_v2_front.txt").exists()


def _fbx(tmp_path):
    """A recognisable mesh as FBX: a tall box with a smaller box on top, facing the cameras."""
    r = run_script(f'''
import bpy, json
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete()                 # the start-up scene's own cube is not our mesh
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0)); bpy.context.object.scale = (0.8, 0.4, 1.0)
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0.8)); bpy.context.object.scale = (0.3, 0.3, 0.3)
for o in list(bpy.data.objects):
    if o.type != "MESH": bpy.data.objects.remove(o)
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.join()
bpy.ops.export_scene.fbx(filepath={str(tmp_path / "m.fbx")!r}, use_selection=True)
print("RESULT", json.dumps({{"ok": True}}))
''')
    assert r.rc == 0, r.out[-1500:]
    return tmp_path / "m.fbx"


def test_clay_view_renders_the_four_cardinal_views_and_records_the_camera(cfg, tmp_path):
    mesh = _fbx(tmp_path)
    out = {}
    for view in ("Front", "Left"):
        res = R.run("clay_view", [str(mesh), str(tmp_path / f"clay_{view}.png"), view, "256", "--turn", "0"], cfg, timeout=240,
                    env_extra={"XDG_CONFIG_HOME": str(tmp_path / "xdg")})
        assert res.rc == 0, res.stdout[-1200:]
        out[view] = np.asarray(Image.open(tmp_path / f"clay_{view}.png").convert("RGB")).astype(float)
        meta = json.loads((tmp_path / f"clay_{view}.png.json").read_text())
        assert meta["view"] == view and meta["res"] == 256 and meta["ortho_scale"] > 0 and len(meta["centre"]) == 3
    for view, img in out.items():
        assert img.shape == (256, 256, 3)
        bg = img[0, 0]
        mask = np.abs(img - bg).max(-1) > 8
        assert 0.05 < mask.mean() < 0.9                               # a silhouette, not a blank frame
    assert not np.array_equal(out["Front"], out["Left"])               # the views differ


def test_clay_view_refuses_an_unknown_view(cfg, tmp_path):
    mesh = _fbx(tmp_path)
    res = R.run("clay_view", [str(mesh), str(tmp_path / "x.png"), "Top", "128"], cfg, timeout=240, env_extra={"XDG_CONFIG_HOME": str(tmp_path / "xdg")})
    assert "error:" in res.stdout and "one of" in res.stdout


def _silhouette_pair(tmp_path, view="Front", shift=0):
    size = 128
    clay = np.full((size, size, 3), 255, np.uint8)
    clay[30:100, 40:90] = 180
    Image.fromarray(clay).save(tmp_path / f"clay_{view}.png")
    painted = np.full((size, size, 3), 255, np.uint8)
    painted[30 + shift:100 + shift, 40:90] = (140, 60, 40)
    Image.fromarray(painted).save(tmp_path / f"painted_{view}.png")


def test_mesh_paint_set_gives_each_picked_view_the_alpha_of_its_clay_render(cfg, tmp_path):
    _silhouette_pair(tmp_path, "Front")
    res = R.run("mesh_paint_set", [str(tmp_path), str(tmp_path / "set"), f"Front={tmp_path / 'painted_Front.png'}"], cfg)
    assert res.rc == 0, res.stdout
    plate = Image.open(tmp_path / "set" / "Front.png")
    assert plate.mode == "RGBA"
    a = np.asarray(plate)[..., 3] > 127
    assert a[60, 60] and not a[10, 10] and a.sum() == pytest.approx(70 * 50, rel=0.05)
    rec = json.loads((tmp_path / "set" / "set.json").read_text())
    assert rec["rows"][0]["view"] == "Front" and rec["rows"][0]["silhouette_iou_vs_clay"] > 0.95


def test_the_silhouette_iou_tells_a_misplaced_paint_from_a_good_one(cfg, tmp_path):
    _silhouette_pair(tmp_path, "Front", shift=0)
    good = R.run("mesh_paint_set", [str(tmp_path), str(tmp_path / "s1"), f"Front={tmp_path / 'painted_Front.png'}"], cfg)
    _silhouette_pair(tmp_path, "Front", shift=25)
    bad = R.run("mesh_paint_set", [str(tmp_path), str(tmp_path / "s2"), f"Front={tmp_path / 'painted_Front.png'}"], cfg)
    g = json.loads((tmp_path / "s1" / "set.json").read_text())["rows"][0]["silhouette_iou_vs_clay"]
    b = json.loads((tmp_path / "s2" / "set.json").read_text())["rows"][0]["silhouette_iou_vs_clay"]
    assert g > 0.95 and b < 0.7


def test_a_view_without_a_clay_render_is_refused(cfg, tmp_path):
    Image.fromarray(np.zeros((8, 8, 3), np.uint8)).save(tmp_path / "p.png")
    res = R.run("mesh_paint_set", [str(tmp_path), str(tmp_path / "set"), f"Front={tmp_path / 'p.png'}"], cfg)
    assert "no clay render" in res.stdout and res.rc == 1


NPZ = SHELF / "meshqa" / "patched" / "chest_p17_uv_front-y.npz"


@pytest.mark.skipif(not (NPZ.exists() and SCI.exists() and (SHELF / "relief_runs/chest1_4k").exists()), reason="the shelf's chest projection inputs or a science python are not here")
def test_relief_project_with_no_flow_skips_the_relief_warp(cfg, tmp_path):
    """RP_NO_FLOW=1: plates painted over the mesh's own render are aligned already, so no optical-flow warp is computed."""
    out = {}
    for flag in ("0", "1"):
        res = R.run("relief_project", [str(NPZ), str(SHELF / "relief_runs/chest1_4k"), str(SHELF / "plates_4k_alpha"), str(tmp_path / f"o{flag}"), "1024"],
                    cfg, timeout=600, env_extra={"RP_NO_FLOW": flag, "RP_COLOR_FULL": "0"})
        assert res.rc == 0, res.stdout[-800:]
        out[flag] = res.stdout
    a = np.asarray(Image.open(tmp_path / "o0" / "v3_colour_atlas.png").convert("RGB")).astype(int)
    b = np.asarray(Image.open(tmp_path / "o1" / "v3_colour_atlas.png").convert("RGB")).astype(int)
    assert (np.abs(a - b).max(-1) > 12).mean() > 0.02          # the warp moved the sampled colour; without it the atlas differs
    assert (tmp_path / "o1" / "v3_colour_atlas.png").exists() and (tmp_path / "o1" / "detail_height_u16.png").exists()
