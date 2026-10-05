# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rebuild loop (the shelf's meshqa/rebuild_textured.sh, in Python): source mesh + the captain's rulings ->
patch (deletions, refills, holes, relabels) -> patch UVs -> npz -> per-face texel overrides -> colour projection
-> material masks. The plan is pure and tested as data; the maps step on synthetic arrays; the whole chain on his
real chest when the shelf is present."""

import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import rebuild as RB  # noqa: E402


def spec(tmp_path, **kw):
    base = dict(piece="chest", source_mesh="/src/mesh.fbx", owner="/src/owner.npy", recipe="/src/recipe.json",
                candidates="/rul/cands.json", decisions="/rul/decisions.jsonl", deletions="/rul/del.json",
                relabels_orig="/rul/rel.json", texel_overrides="/rul/texo.json",
                relief_dir="/in/relief", plates_dir="/in/plates", out_root=str(tmp_path / "out"))
    base.update(kw)
    return RB.RebuildSpec(**base)


def test_the_plan_is_the_shell_scripts_five_steps_in_order(tmp_path):
    steps = RB.plan(spec(tmp_path), "p10")
    assert [s.name for s in steps] == ["patch_holes", "uv_patches", "mesh_to_npz", "maps", "relief_project", "material_masks"]
    assert [s.tool for s in steps] == ["patch_holes", "uv_patches", "mesh_to_npz", None, "relief_project", "material_masks"]


def test_patch_holes_gets_the_rulings_as_the_shell_script_passed_them(tmp_path):
    s = spec(tmp_path, relabel_rules=["waist_sash_layers:cuirass_back_plate:cuirass_back_plate"])
    a = RB.plan(s, "p10")[0].args
    P = str(tmp_path / "out" / "patched")
    assert a[:6] == ["/src/mesh.fbx", "/src/owner.npy", "/src/recipe.json", "/rul/cands.json", "/rul/decisions.jsonl", f"{P}/chest_p10"]
    assert a[6:] == ["--deletions", "/rul/del.json", "--relabel", "waist_sash_layers:cuirass_back_plate:cuirass_back_plate",
                     "--relabel-orig", "/rul/rel.json"]


def test_the_later_steps_chain_their_outputs(tmp_path):
    P = str(tmp_path / "out" / "patched")
    steps = {s.name: s for s in RB.plan(spec(tmp_path), "p10")}
    assert steps["uv_patches"].args == [f"{P}/chest_p10.fbx", f"{P}/chest_p10_orig_poly.npy", f"{P}/chest_p10_uv.fbx"]
    assert steps["mesh_to_npz"].args == [f"{P}/chest_p10_uv.npz", "piece_uv", f"{P}/chest_p10_uv.fbx"]
    O = str(tmp_path / "out" / "p10")
    assert steps["relief_project"].args == [f"{P}/chest_p10_uv_front-y.npz", "/in/relief", "/in/plates", O, "2048"]
    assert steps["material_masks"].args == [O, f"{P}/chest_p10_owner_tri.npy", "/src/recipe.json", O, f"{P}/chest_p10_uv_front-y.npz"]


def test_the_recipe_flags_become_the_environment_the_shell_script_set(tmp_path):
    s = spec(tmp_path, res=4096, color_full=True, ornament="600:24:0.25")
    steps = {x.name: x for x in RB.plan(s, "p10")}
    assert steps["relief_project"].env == {"RP_COLOR_FULL": "1", "RP_MESH_HEIGHT": "0"}
    e = steps["material_masks"].env
    assert e["MM_BLUR"] == "2.0" and e["MM_EMB_MIN_BLOB"] == "240" and e["MM_CLOTH_MEDIAN"] == "5"      # K = 2 at 4096
    assert e["MM_PLATE_GOLD_MIN_BLOB"] == "32" and e["MM_PLATE_GOLD_CLOSE"] == "4" and e["MM_RIM_CLOSE"] == "6"
    assert e["MM_PART_GOLD_BLOB"] == "cuirass_*:160,tasset_*:160"
    assert e["MM_ORNAMENT_GOLD"] == "600:24:0.25" and e["MM_GOLD_FROM_MESH"] == ""
    assert e["MM_NO_VOTE_CLASSES"] == "rigid-metal dangle" and e["MM_SOFTEN_GOLD"] == "0.9"
    assert e["MM_FORCE_CLASS"].endswith("chest_p10_force_class_tri.json")


def test_mesh_gold_turns_on_the_mesh_height_inputs(tmp_path):
    steps = {x.name: x for x in RB.plan(spec(tmp_path, res=2048, mesh_gold=True), "p10")}
    assert steps["relief_project"].env["RP_MESH_HEIGHT"] == "25"
    assert steps["material_masks"].env["MM_GOLD_FROM_MESH"] == "0.6:10"


def test_a_tag_that_would_overwrite_is_refused(tmp_path):
    s = spec(tmp_path)
    (Path(s.out_root) / "patched").mkdir(parents=True)
    (Path(s.out_root) / "patched" / "chest_p10.fbx").write_text("x")
    with pytest.raises(RB.TagExists):
        RB.check_fresh(s, "p10")
    RB.check_fresh(s, "p11")


def test_tags_are_plain_names(tmp_path):
    for bad in ("", "../x", "a/b", "p 1"):
        with pytest.raises(ValueError):
            RB.plan(spec(tmp_path), bad)


# ---- the maps step

def test_maps_turns_the_mesh_to_the_front_and_converts_the_texel_overrides(tmp_path):
    P = tmp_path / "patched"
    P.mkdir()
    V = np.array([[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0], [1, 1, 1]])
    T = np.array([[0, 1, 2], [1, 2, 3], [0, 2, 3]])
    np.savez(P / "chest_t_uv.npz", V=V, T=T, P=V[T], UV=np.zeros((3, 3, 2)), POLY=np.array([0, 1, 1]))
    np.save(P / "chest_t_owner_poly.npy", np.array([5, 7]))
    np.save(P / "chest_t_orig_poly.npy", np.array([40, 41]))
    texo = tmp_path / "texo.json"
    texo.write_text(json.dumps({"force_class": [{"faces_orig": [41], "class": "red", "why": "w"}]}))
    rep = RB.make_maps(str(P), "chest", "t", str(texo), turn=-90.0)
    d = np.load(P / "chest_t_uv_front-y.npz")
    th = math.radians(-90)
    R = np.array([[math.cos(th), -math.sin(th), 0], [math.sin(th), math.cos(th), 0], [0, 0, 1]])
    assert np.allclose(d["V"], V @ R.T) and np.allclose(d["P"], d["V"][T]) and (d["POLY"] == [0, 1, 1]).all()
    assert (np.load(P / "chest_t_owner_tri.npy") == [5, 7, 7]).all()
    assert json.loads((P / "chest_t_force_class_tri.json").read_text()) == {"red": [1, 2]}
    assert rep == {"polys": 2, "force_class_triangles": {"red": 2}}


def test_maps_refuses_when_the_per_polygon_arrays_disagree(tmp_path):
    P = tmp_path / "patched"
    P.mkdir()
    V = np.zeros((3, 3))
    np.savez(P / "chest_t_uv.npz", V=V, T=np.array([[0, 1, 2]]), P=V[[[0, 1, 2]]], UV=np.zeros((1, 3, 2)), POLY=np.array([0]))
    np.save(P / "chest_t_owner_poly.npy", np.array([1, 2, 3]))
    np.save(P / "chest_t_orig_poly.npy", np.array([1, 2, 3]))
    (tmp_path / "t.json").write_text(json.dumps({"force_class": []}))
    with pytest.raises(ValueError, match="polygon"):
        RB.make_maps(str(P), "chest", "t", str(tmp_path / "t.json"))


# ---- running it

def test_run_executes_the_steps_in_order_and_stops_at_the_first_failure(tmp_path):
    calls = []

    class Res:
        def __init__(self, rc):
            self.rc, self.stdout, self.log = rc, "out", None

    def fake_run(tool, args, settings, **kw):
        calls.append(tool)
        return Res(1 if tool == "uv_patches" else 0)

    s = spec(tmp_path)
    rep = RB.run(s, "p10", settings=object(), runner=fake_run, maps=lambda *a, **k: {})
    assert calls == ["patch_holes", "uv_patches"]
    assert rep["ok"] is False and rep["failed"] == "uv_patches"


def test_run_with_resume_skips_steps_whose_outputs_exist(tmp_path):
    s = spec(tmp_path)
    P = Path(s.out_root) / "patched"
    P.mkdir(parents=True)
    for n in ("chest_p10.fbx", "chest_p10_orig_poly.npy", "chest_p10_owner_poly.npy", "chest_p10_patch.json"):
        (P / n).write_text("x")
    calls = []

    class Res:
        rc, stdout, log = 0, "", None

    rep = RB.run(s, "p10", settings=object(), runner=lambda tool, *a, **k: calls.append(tool) or Res(), resume=True, maps=lambda *a, **k: {})
    assert "patch_holes" not in calls and calls[0] == "uv_patches"
    assert rep["skipped"] == ["patch_holes"]


SHELF = Path("/path/to/shelf/scratch/scratch-tmp")
SCI = Path("/path/to/boxes")


@pytest.mark.skipif(not ((SHELF / "meshqa" / "patched" / "chest_p17_patch.json").exists() and SCI.exists()),
                    reason="the shelf's chest data or a science python is not on this machine")
def test_the_whole_loop_reproduces_the_captains_recorded_rebuild(tmp_path):
    """Source mesh + his current rulings, run through the REAL Lampway binary and a science python at 2048: the
    patch holes (fill, faces, area) and the per-polygon owner map equal his recorded rebuild chest_p17."""
    sys.path.insert(0, str(Path(__file__).parent))
    from blender_run import lampway_bin, require_binary
    require_binary()
    from mixar.modules.lampway_tools import settings as S
    Q, X = SHELF / "meshqa", SHELF / "parts_transfer"
    s = S.load()
    s.blender, s.python_science = lampway_bin(), SCI
    s.project_root = tmp_path
    sp = RB.RebuildSpec(
        piece="chest", source_mesh=str(SHELF / "tripo_mesh/smartuv_9c052d49/uv1_nobowl.fbx"), owner=str(X / "owner_poly_r7e.npy"),
        recipe=str(X / "recipe_r7e.json"), candidates=str(Q / "chest_9c052d49_candidates_merged.json"), decisions=str(Q / "decisions.jsonl"),
        deletions=str(Q / "chest_9c052d49_deletions.json"), relabels_orig=str(Q / "chest_9c052d49_relabels_orig.json"),
        texel_overrides=str(Q / "chest_9c052d49_texel_overrides_orig.json"), relief_dir=str(SHELF / "relief_runs/chest1_4k"),
        plates_dir=str(SHELF / "plates_4k_alpha"), out_root=str(tmp_path / "out"),
        relabel_rules=["waist_sash_layers:cuirass_back_plate:cuirass_back_plate"], res=2048)
    rep = RB.run(sp, "t1", s, log_dir=tmp_path / "logs", timeout=900)
    assert rep["ok"], rep
    mine = json.load(open(tmp_path / "out/patched/chest_t1_patch.json"))
    rec = json.load(open(Q / "patched/chest_p17_patch.json"))
    key = lambda h: (h["hole"], h.get("fill"), h.get("faces"), h.get("area_cm2"))
    assert [key(h) for h in mine["holes"]] == [key(h) for h in rec["holes"]]
    assert (mine["faces_out"], mine["patch_faces"], mine["relabelled"]) == (rec["faces_out"], rec["patch_faces"], rec["relabelled"])
    assert (np.load(tmp_path / "out/patched/chest_t1_owner_poly.npy") == np.load(Q / "patched/chest_p17_owner_poly.npy")).all()
    assert json.load(open(tmp_path / "out/t1/masks.json"))                      # the masks step produced its shares


# ---- projection into an existing rebuild (mesh-paint plates): no flow warp, a separate output directory, only two steps

def test_no_flow_sets_the_projection_flag(tmp_path):
    steps = {x.name: x for x in RB.plan(spec(tmp_path, no_flow=True, color_full=True), "p10")}
    assert steps["relief_project"].env == {"RP_COLOR_FULL": "1", "RP_NO_FLOW": "1", "RP_MESH_HEIGHT": "0"}
    assert "RP_NO_FLOW" not in {x.name: x for x in RB.plan(spec(tmp_path), "p10")}["relief_project"].env


def test_an_output_name_separates_the_projection_from_the_rebuilds_own_directory(tmp_path):
    steps = {x.name: x for x in RB.plan(spec(tmp_path), "p10", out_name="p10_meshpaint")}
    O = str(tmp_path / "out" / "p10_meshpaint")
    assert steps["relief_project"].args[3] == O and steps["material_masks"].args[0] == O
    P = str(tmp_path / "out" / "patched")
    assert steps["relief_project"].args[0] == f"{P}/chest_p10_uv_front-y.npz"           # still the rebuild's own mesh
    assert steps["material_masks"].env["MM_FORCE_CLASS"] == f"{P}/chest_p10_force_class_tri.json"


def test_only_runs_just_the_named_steps_on_an_existing_tag(tmp_path):
    s = spec(tmp_path)
    calls = []

    class Res:
        rc, stdout, log = 0, "", None

    rep = RB.run(s, "p10", settings=object(), runner=lambda tool, *a, **k: calls.append(tool) or Res(), resume=True,
                 only=("relief_project", "material_masks"), out_name="p10_mp", maps=lambda *a, **k: {})
    assert calls == ["relief_project", "material_masks"] and rep["ok"] and rep["out"].endswith("p10_mp")


def test_only_with_an_unknown_step_is_refused(tmp_path):
    with pytest.raises(ValueError, match="unknown step"):
        RB.run(spec(tmp_path), "p10", settings=object(), only=("nope",), resume=True, runner=lambda *a, **k: None)
