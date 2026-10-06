# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""motion_generate (specs/resources/motion_generate.md): a motion clip for a short prompt. The library engine is a deterministic ranker over an index of owned clips
(no model, no network) that refuses a poor match; the model engines (kimodo, unimate) are slots that answer needs_provider and send nothing. Each pick is a
typed decision row. The ranker is pure python; the import runs in the real binary."""

import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
sys.path.insert(0, str(Path(__file__).parent))
from mixar.modules.lampway_tools.pipeline import motion_library as ML  # noqa: E402

SHELF = ["MM_Idle", "MM_Attack_01", "MM_Jump", "MF_Unarmed_Jog_Fwd", "MF_Unarmed_Walk_Fwd", "MF_Unarmed_Walk_Left"]


def index():
    return [{"name": n, "file": f"anims/{n}.fbx", "fps": 30, "frames": 30 + 10 * i, "tags": [], "root_motion": None} for i, n in enumerate(SHELF)]


def test_the_prompts_rank_the_right_clip_whatever_the_index_order():
    rows = index()
    for prompt, want in (("walk forward", "MF_Unarmed_Walk_Fwd"), ("attack", "MM_Attack_01"), ("jump", "MM_Jump"), ("a heavy sword attack", "MM_Attack_01")):
        assert ML.rank(prompt, rows, duration=3)[0]["name"] == want, prompt
        assert ML.rank(prompt, list(reversed(rows)), duration=3)[0]["name"] == want, prompt          # the falsifier: shuffle the index, the ranks hold


def test_a_prompt_nothing_matches_is_refused_naming_the_library():
    with pytest.raises(ML.MotionError, match="no clip matches 'dance the macarena'; the library has 6 clips"):
        ML.pick("dance the macarena", index(), duration=3)


def test_model_engines_answer_needs_provider_and_open_no_socket(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a socket was opened")
    monkeypatch.setattr(socket, "create_connection", boom)
    for engine in ("model:kimodo", "model:unimate"):
        out = ML.model_slot(engine)
        assert out["ok"] is False and out["needs_provider"] is True and out["engine"] == engine
        assert "nothing was run and nothing was sent" in out["error"]
    with pytest.raises(ML.MotionError, match="library | model:kimodo | model:unimate"):
        ML.model_slot("model:hymotion")


def test_the_decision_row_has_the_meshqa_shape():
    row = ML.decision_row("attack", ML.rank("attack", index(), duration=3), "MM_Attack_01", "anims")
    assert set(row) >= {"session", "source", "descriptor", "descriptor_sha256", "question", "options", "answer", "decider"}
    assert row["decider"] == "model" and row["answer"] == "MM_Attack_01" and row["options"][0] == "MM_Attack_01"


def test_prompt_and_duration_bounds():
    with pytest.raises(ML.MotionError, match="1..300"):
        ML.pick("", index(), duration=3)
    with pytest.raises(ML.MotionError, match="0.5..10"):
        ML.pick("jump", index(), duration=12)


def test_the_api_indexes_a_folder_and_imports_the_ranked_clip(tmp_path):
    from wave6_support import go, one
    d = one(go(tmp_path, '''
def clip(name, frames):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    rig = armature(name="Armature", bones=(("hips", (0, 0, 0.9), (0, 0, 1.1)), ("leg", (0, 0, 0.9), (0, 0, 0.1))))
    pb = rig.pose.bones["leg"]; pb.rotation_mode = "XYZ"
    for f, a in ((1, 0.0), (frames, 0.6)):
        pb.rotation_euler = (a, 0, 0); pb.keyframe_insert("rotation_euler", frame=f)
    rig.animation_data.action.name = name
    bpy.context.scene.frame_end = frames
    os.makedirs(os.path.join(root, "anims"), exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.fbx(filepath=os.path.join(root, "anims", name + ".fbx"), use_selection=True, bake_anim=True, add_leaf_bones=False)
bpy.context.scene.render.fps = 30
clip("MM_Jump", 24); clip("MF_Unarmed_Walk_Fwd", 40)
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
idx = call("motion_generate", action="index", library="anims")
res = call("motion_generate", prompt="jump", library="anims", duration=1)
miss = call("motion_generate", prompt="dance the macarena", library="anims")
model = call("motion_generate", prompt="jump", engine="model:kimodo")
arms = sorted(o.name for o in bpy.data.objects if o.type == "ARMATURE")
rows = [json.loads(l) for l in open(os.path.join(root, "motion", "decisions.jsonl"))]
print("RESULT", json.dumps({"idx": idx, "res": res, "miss": miss, "model": model, "arms": arms, "rows": len(rows)}))
'''))
    assert d["idx"]["ok"] and sorted(r["name"] for r in d["idx"]["clips"]) == ["MF_Unarmed_Walk_Fwd", "MM_Jump"]
    res = d["res"]
    assert res["ok"], res
    assert res["clip"]["name"] == "MM_Jump" and res["clip"]["frames"] == 24 and res["clip"]["fps"] == 30 and res["armature"] == "motion_src"
    assert d["arms"] == ["motion_src"] and d["rows"] == 1
    assert d["miss"]["ok"] is False and "no clip matches" in d["miss"]["error"]
    assert d["model"]["ok"] is False and d["model"]["needs_provider"] is True
