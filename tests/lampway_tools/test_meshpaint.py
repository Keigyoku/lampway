# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The mesh-paint workflow as one module: prompts and references per view, the generation order that keeps the views
consistent, picking one of four by silhouette IoU against the clay render, the plate set, the projection (4096, no warp) and
the masks. Pure logic here (stubbed runner and image backend); the tools themselves are tested in test_meshpaint_tools.py."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import meshpaint as MP  # noqa: E402
from mixar.modules.lampway_tools import settings as S  # noqa: E402

PROMPTS = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/scripts/texlib/prompts"


def spec(tmp_path, **kw):
    base = dict(piece="chest", mesh=str(tmp_path / "m.fbx"), design_dir=str(tmp_path / "v3"), work_dir=str(tmp_path / "mp"))
    base.update(kw)
    return MP.MeshPaintSpec(**base)


def test_the_generation_order_chains_consistency_from_a_side_through_the_front():
    assert MP.ORDER == ("Left", "Front", "Back", "Right")
    assert MP.consistency_view("Left", []) is None                       # the first view has nothing painted to match yet
    assert MP.consistency_view("Front", ["Left"]) == "Left"              # the front matches a SIDE (prompt_meshpaint_v2_front)
    assert MP.consistency_view("Back", ["Left", "Front"]) == "Front"     # the rest match the FRONT (prompt_meshpaint_v2)
    assert MP.consistency_view("Right", ["Left", "Front", "Back"]) == "Front"
    assert MP.consistency_view("Back", ["Left"]) == "Left"               # no front yet: any painted view will do


def test_the_prompts_are_the_shelfs_two_texts_unchanged_when_a_consistency_view_exists():
    v2 = (PROMPTS / "prompt_meshpaint_v2.txt").read_text()
    front = (PROMPTS / "prompt_meshpaint_v2_front.txt").read_text()
    assert MP.prompt_for("Back", "Front") == v2.strip()
    assert MP.prompt_for("Front", "Left") == front.strip()
    assert "SECOND image is the same armor already painted" in MP.prompt_for("Right", "Front")


def test_without_a_painted_view_the_second_image_sentence_is_dropped_and_the_numbering_closes_up():
    p = MP.prompt_for("Left", None)
    assert "SECOND image is the same armor already painted" not in p and "match its exact colours" not in p
    assert "The SECOND image is the original colour design" in p                   # the design plate moves up from THIRD
    assert "THIRD" not in p and "Paint the FIRST image" in p and "flat ALBEDO texture" in p
    assert "THIRD" not in MP.prompt_for("Front", None)


def test_references_are_the_clay_render_then_the_painted_view_then_the_design_plate(tmp_path):
    s = spec(tmp_path)
    assert MP.refs_for(s, "Back", "Front", picks={"Front": "/x/f.png"}) == [
        str(Path(s.work_dir) / "clay" / "clay_Back.png"), "/x/f.png", str(Path(s.design_dir) / "Back.png")]
    assert MP.refs_for(s, "Left", None, picks={}) == [str(Path(s.work_dir) / "clay" / "clay_Left.png"), str(Path(s.design_dir) / "Left.png")]


def _pair(tmp_path, name, *, shift):
    clay = np.full((64, 64, 3), 255, np.uint8)
    clay[10:50, 20:44] = 180
    painted = np.full((64, 64, 3), 255, np.uint8)
    painted[10 + shift:50 + shift, 20:44] = (120, 50, 40)
    Image.fromarray(clay).save(tmp_path / f"{name}_clay.png")
    Image.fromarray(painted).save(tmp_path / f"{name}.png")
    return tmp_path / f"{name}_clay.png", tmp_path / f"{name}.png"


def test_the_silhouette_iou_is_high_for_a_faithful_paint_and_low_for_a_moved_one(tmp_path):
    clay, good = _pair(tmp_path, "good", shift=0)
    _, bad = _pair(tmp_path, "bad", shift=18)
    assert MP.silhouette_iou(clay, good) > 0.95 and MP.silhouette_iou(clay, bad) < 0.6


def test_the_best_of_four_is_the_one_whose_outline_matches_the_clay(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    clay, _ = _pair(tmp_path, "c", shift=0)
    for i, shift in enumerate((14, 0, 22, 6), start=1):
        _, p = _pair(tmp_path, f"v{i}", shift=shift)
        p.rename(run / f"{i}.png")
    ranked = MP.rank_variants(run, clay)
    assert [Path(f).name for f, _ in ranked][:2] == ["2.png", "4.png"] and ranked[0][1] > ranked[-1][1]
    assert Path(MP.pick_best(run, clay)).name == "2.png"


def test_a_run_directory_without_images_is_refused(tmp_path):
    (tmp_path / "empty").mkdir()
    clay, _ = _pair(tmp_path, "c", shift=0)
    with pytest.raises(FileNotFoundError, match="no variants"):
        MP.pick_best(tmp_path / "empty", clay)


def test_picks_are_recorded_and_read_back(tmp_path):
    s = spec(tmp_path)
    MP.record_pick(s, "Front", "/a/1.png", iou=0.97)
    MP.record_pick(s, "Left", "/a/2.png")
    assert MP.load_picks(s) == {"Front": "/a/1.png", "Left": "/a/2.png"}
    assert json.loads((Path(s.work_dir) / "picks.json").read_text())["iou"] == {"Front": 0.97}


def test_the_plate_set_needs_all_four_picks_unless_told_otherwise(tmp_path):
    s = spec(tmp_path)
    MP.record_pick(s, "Front", "/a/1.png")
    with pytest.raises(ValueError, match="Back, Left, Right"):
        MP.plate_args(s)
    args = MP.plate_args(s, require_all=False)
    assert args == [str(Path(s.work_dir) / "clay"), str(Path(s.work_dir) / "set"), "Front=/a/1.png"]


def test_the_projection_is_4096_without_warp_into_its_own_directory_on_the_existing_rebuild(tmp_path):
    from mixar.modules.lampway_tools import rebuild as RB
    base = RB.RebuildSpec(piece="chest", source_mesh="m", owner="o", recipe="r", candidates="c", decisions="d", deletions="x",
                          relabels_orig="y", texel_overrides="z", relief_dir="/relief", plates_dir="/v3", out_root=str(tmp_path / "out"))
    s = spec(tmp_path)
    proj = MP.projection_spec(base, s)
    assert (proj.res, proj.color_full, proj.no_flow) == (4096, True, True)
    assert proj.plates_dir == str(Path(s.work_dir) / "set") and proj.relief_dir == "/relief"
    assert base.plates_dir == "/v3" and base.res == 2048                              # the rebuild's own spec is untouched
    assert MP.output_name("p17") == "p17_meshpaint"


def test_running_all_stages_calls_clay_then_each_view_in_order_then_plates_then_projection(tmp_path):
    s = spec(tmp_path)
    calls = []

    def clay():
        calls.append("clay")

    def generate(view, prompt, refs, out_dir):
        calls.append(("generate", view, len(refs)))
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        c = Path(s.work_dir) / "clay"
        c.mkdir(parents=True, exist_ok=True)
        clay_png = c / f"clay_{view}.png"
        a = np.full((32, 32, 3), 255, np.uint8)
        a[4:28, 8:24] = 180
        Image.fromarray(a).save(clay_png)
        for i in (1, 2):
            b = np.full((32, 32, 3), 255, np.uint8)
            b[4 + (0 if i == 2 else 6):28 + (0 if i == 2 else 6), 8:24] = (100, 60, 30)
            Image.fromarray(b[:32]).save(out / f"{i}.png")
        return [str(out / "1.png"), str(out / "2.png")]

    def plates():
        calls.append("plates")

    def project():
        calls.append("project")
        return {"ok": True}

    rep = MP.run_all(s, clay=clay, generate=generate, plates=plates, project=project)
    assert calls == ["clay", ("generate", "Left", 2), ("generate", "Front", 3), ("generate", "Back", 3), ("generate", "Right", 3), "plates", "project"]
    assert rep["picks"].keys() == {"Left", "Front", "Back", "Right"} and all(Path(p).name == "2.png" for p in rep["picks"].values())
    assert rep["ok"] is True


def test_a_generation_that_returns_nothing_stops_the_run_with_the_view_named(tmp_path):
    s = spec(tmp_path)
    with pytest.raises(MP.MeshPaintError, match="Left"):
        MP.run_all(s, clay=lambda: None, generate=lambda *a: [], plates=lambda: None, project=lambda: {})
