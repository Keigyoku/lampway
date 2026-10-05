# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""pbr_merge, the engine set (PIECE_PIPELINE step 14): the studio's PBR maps kept, the patch islands filled from our albedo
and the class medians, the live palette baked in linear space, metal forced to 0 on non-metal classes, ORM in UE order.
A synthetic 32 px set under the science python; skipped without one."""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import runner as R  # noqa: E402
from mixar.modules.lampway_tools import settings as S  # noqa: E402

SCI = Path(os.environ.get("LAMPWAY_PYTHON_SCIENCE") or "/nonexistent")


def test_pbr_merge_is_a_registered_science_tool():
    assert R.TOOLS["pbr_merge"].kind == "science" and (R.SCRIPTS / "texlib/pbr_merge.py").exists()


def _inputs(root: Path, res=32):
    masks = root / "masks"
    masks.mkdir()
    y, x = np.mgrid[0:res, 0:res]
    classes = {"gold": x < 8, "plate": (x >= 8) & (x < 16), "red": (x >= 16) & (x < 24), "linen": x >= 24,
               "embroidery": np.zeros((res, res), bool), "leather": np.zeros((res, res), bool)}
    for k, m in classes.items():
        Image.fromarray((m * 255).astype(np.uint8)).save(masks / f"mask_{k}.png")
    # 4 triangles (one per column band), texel -> triangle; triangle 3 (the linen band) is a PATCH (orig_poly -1)
    tf = np.where(x < 8, 0, np.where(x < 16, 1, np.where(x < 24, 2, 3))).astype(np.int32)
    tf[y < 2] = -1                                                          # an uncovered gutter row
    np.save(masks / "texel_face.npy", tf)
    np.savez(root / "mesh.npz", POLY=np.array([0, 1, 2, 3]))
    np.save(root / "orig_poly.npy", np.array([0, 1, 2, -1]))
    grey = lambda v: Image.fromarray(np.full((res, res), v, np.uint8))
    grey(128).convert("RGB").save(root / "base.png")
    Image.fromarray(np.full((res, res, 3), [128, 128, 255], np.uint8)).save(root / "normal.png")
    grey(64).save(root / "rough.png")
    grey(255).save(root / "metal.png")                                       # the studio said "all metal"
    Image.fromarray(np.full((res, res, 3), [200, 30, 30], np.uint8)).save(root / "albedo.png")
    (root / "params.json").write_text(json.dumps({"order": ["gold", "red"], "palette_hsv": {"gold": [0.5, 1.0, 1.0], "red": [0.5, 1.0, 1.0]},
                                                  "metal_zero_on": ["red", "linen"], "normal_strength_live": 0.5}))
    return masks


@pytest.mark.skipif(not SCI.exists(), reason="no science python (LAMPWAY_PYTHON_SCIENCE)")
def test_the_engine_set_is_written_with_metal_zeroed_on_cloth_and_patches_filled_from_the_albedo(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "home"))
    s = S.load()
    s.project_root, s.python_science = tmp_path, SCI
    masks = _inputs(tmp_path)
    out = tmp_path / "engine"
    res = R.run("pbr_merge", [str(out), "--base", "base.png", "--normal", "normal.png", "--rough", "rough.png", "--metal", "metal.png",
                              "--masks", str(masks), "--albedo", "albedo.png", "--mesh-npz", "mesh.npz", "--orig-poly", "orig_poly.npy",
                              "--params", "params.json", "--res", "32", "--base-res", "32"], s, timeout=300, cwd=str(tmp_path))
    assert res.rc == 0, res.stdout[-1500:]
    names = sorted(p.name for p in out.iterdir())
    assert names == ["BaseColor_32.png", "Metallic_32.png", "Normal_DX_32.png", "Normal_GL_32.png", "ORM_32.png", "Roughness_32.png", "merge.json"]
    metal = np.asarray(Image.open(out / "Metallic_32.png"))
    assert metal[16, 4] == 255 and metal[16, 20] == 0, "metal kept on gold, zeroed on the red cloth"
    base = np.asarray(Image.open(out / "BaseColor_32.png"))
    assert tuple(base[16, 28]) == (200, 30, 30), "the patch band takes our albedo"
    orm = np.asarray(Image.open(out / "ORM_32.png"))
    assert orm[16, 4, 0] == 255 and orm[16, 4, 2] == 255, "ORM: R = 1 without an AO map, B = metallic"
    gl, dx = (np.asarray(Image.open(out / n)) for n in ("Normal_GL_32.png", "Normal_DX_32.png"))
    assert (dx[..., 1] == 255 - gl[..., 1]).all(), "DirectX = green flipped"
    rep = json.loads((out / "merge.json").read_text())
    assert rep["normal_strength_baked"] == 0.5 and rep["patch_texels"] > 0
