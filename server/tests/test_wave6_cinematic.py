"""cinematic_shot_plan (specs/wiki/cinematic_shot_plan.md): a shot list with one action and one camera move per shot, the wiki's prompt template filled per shot,
the video prices summed WITHOUT generating (each shot priced from the model's own pricing_skus), split of a failing shot into two, typed reviews, and every
generating stage a needs_approval card (the user's click confirms; this tool never does)."""

import json

import pytest

from lampway_server import cinematic as CI

REFS = [{"path": "refs/hero_front.png", "text": "bronze helmet crest; wearer-left pauldron is the larger, wearer-right holds the spear"}]
SHOTS = [{"id": "s01", "action": "draws the sword", "camera": "slow push in", "duration_s": 5, "end": "sword raised"},
         {"id": "s02", "action": "steps forward", "camera": "orbit left", "duration_s": 4, "end": "at the doorway"},
         {"id": "s03", "action": "turns", "camera": "static", "duration_s": 6, "end": "facing the camera"}]
ROW = {"id": "vendor/clip-model", "pricing_skus": {"duration_seconds": "0.10"}, "supported_durations": [4, 5, 6, 8]}


class FakeCatalogue:
    def __init__(self):
        self.calls = []

    def model(self, model_id):
        self.calls.append(("model", model_id))
        return ROW

    def generate(self, *a, **k):  # pragma: no cover - must never be reached
        raise AssertionError("the plan must not generate")


def test_two_actions_in_one_shot_refused(tmp_path):
    for bad in ("draws the sword and turns", "draws the sword, turns", "draws then turns"):
        with pytest.raises(CI.ShotError, match="one action and one camera move per shot"):
            CI.plan(str(tmp_path), "duel", [dict(SHOTS[0], action=bad)], REFS, "vendor/clip-model", FakeCatalogue())
    with pytest.raises(CI.ShotError, match="one action and one camera move per shot"):
        CI.plan(str(tmp_path), "duel", [dict(SHOTS[0], camera="push in and orbit")], REFS, "vendor/clip-model", FakeCatalogue())


def test_character_refs_without_wearer_left_right_text_refused(tmp_path):
    with pytest.raises(CI.ShotError, match="wearer-left/right"):
        CI.plan(str(tmp_path), "duel", SHOTS, [{"path": "refs/a.png", "text": "a warrior"}], "vendor/clip-model", FakeCatalogue())
    with pytest.raises(CI.ShotError, match="wearer-left/right"):
        CI.plan(str(tmp_path), "duel", SHOTS, ["refs/a.png"], "vendor/clip-model", FakeCatalogue())
    with pytest.raises(CI.ShotError, match="wearer-left/right"):                      # one side named is not both sides named
        CI.plan(str(tmp_path), "duel", SHOTS, [{"path": "refs/a.png", "text": "the wearer-left pauldron is larger"}], "vendor/clip-model", FakeCatalogue())


def test_plan_sums_video_prices_without_calling(tmp_path):
    cat = FakeCatalogue()
    out = CI.plan(str(tmp_path), "duel", SHOTS, REFS, "vendor/clip-model", cat)
    assert [s["video"]["estimate_usd"] for s in out["shots"]] == [0.5, 0.4, 0.6]
    assert out["total_video_usd"] == pytest.approx(1.5) and out["price_known"] is True
    assert all(c[0] == "model" for c in cat.calls)                                    # read the catalogue row; never generated
    assert out["first_shot"] == "s02"                                                  # the shortest shot goes first (the cheapest test)
    for s in out["shots"]:
        assert [st["stage"] for st in s["stages"]] == ["playblast_capture", "render_condition_passes", "image_edit", "video_generate", "frame_review"]
        assert {st["stage"]: st["state"] for st in s["stages"]}["video_generate"] == "needs_approval"
    p = out["shots"][0]["prompt"]
    assert p.startswith("Using the supplied start frame, preserve bronze helmet crest; wearer-left pauldron") and "During this 5 s shot, draws the sword." in p
    assert "Camera: slow push in. End with sword raised. Keep the same costume and object count." in p
    assert json.loads((tmp_path / "cinematics" / "duel" / "plan.json").read_text())["shots"][0]["id"] == "s01"


def test_an_unknown_price_is_never_guessed(tmp_path):
    class NoSku(FakeCatalogue):
        def model(self, model_id):
            return {"id": model_id, "pricing_skus": {}}

    out = CI.plan(str(tmp_path), "duel", SHOTS, REFS, "vendor/clip-model", NoSku())
    assert out["price_known"] is False and out["total_video_usd"] is None and all(s["video"]["estimate_usd"] is None for s in out["shots"])
    hf = CI.plan(str(tmp_path), "duel2", SHOTS, REFS, "higgsfield/seedance", None)
    assert hf["price_known"] is False and "read back" in hf["shots"][0]["video"]["basis"]
    nokey = CI.plan(str(tmp_path), "duel3", SHOTS, REFS, "vendor/clip-model", None)
    assert nokey["shots"][0]["video"]["state"] == "needs_key" and nokey["price_known"] is False


def test_split_creates_two_shots_from_one(tmp_path):
    CI.plan(str(tmp_path), "duel", SHOTS, REFS, "vendor/clip-model", FakeCatalogue())
    out = CI.split(str(tmp_path), "duel", "s02", ["steps to the door", "pushes it open"], FakeCatalogue())
    ids = [s["id"] for s in out["shots"]]
    assert ids == ["s01", "s02a", "s02b", "s03"]
    a, b = out["shots"][1], out["shots"][2]
    assert a["action"] == "steps to the door" and b["action"] == "pushes it open" and a["camera"] == b["camera"] == "orbit left"
    assert a["duration_s"] + b["duration_s"] == 4 and b["start"] == "the end frame of s02a" and b["end"] == "at the doorway"
    assert out["total_video_usd"] == pytest.approx(1.5)
    with pytest.raises(CI.ShotError, match="two actions"):
        CI.split(str(tmp_path), "duel", "s01", ["only one"], FakeCatalogue())


def test_a_review_is_typed_and_a_failed_identity_names_the_next_step(tmp_path):
    CI.plan(str(tmp_path), "duel", SHOTS, REFS, "vendor/clip-model", FakeCatalogue())
    with pytest.raises(CI.ShotError, match="identity, doubling, action_order, camera"):
        CI.review(str(tmp_path), "duel", "s01", {"identity": "pass", "vibes": "pass"}, by="agent")
    out = CI.review(str(tmp_path), "duel", "s01", {"identity": "fail", "doubling": "pass", "action_order": "pass", "camera": "pass"}, by="agent")
    assert out["decision"] == "redo" and "identity" in out["next"]
    ok = CI.review(str(tmp_path), "duel", "s01", {"identity": "pass", "doubling": "pass", "action_order": "pass", "camera": "pass"}, by="captain")
    assert ok["decision"] == "chain"
    rec = json.loads((tmp_path / "cinematics" / "duel" / "plan.json").read_text())
    assert [r["by"] for r in rec["shots"][0]["reviews"]] == ["agent", "captain"]


# ---- the agent tool: a server-run tool (it reads the server's video catalogue), dispatched by the agent loop, never sent to Blender

def _hub(video):
    from lampway_server.agent.turns import AgentHub
    hub = AgentHub.__new__(AgentHub)
    hub.video = video
    return hub


def test_the_agent_tool_plans_through_the_agent_loop_and_never_through_blender(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from lampway_server.agent import tools as T
    from lampway_server.agent.providers.base import ToolCall
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    assert "lampway_cinematic_shot_plan" in T.TOOL_NAMES
    with pytest.raises(T.UnknownTool, match="runs on the server"):
        T.script_for("lampway_cinematic_shot_plan", {})
    hub = _hub(SimpleNamespace(client=FakeCatalogue()))
    args = {"action": "plan", "scene": "duel", "shots": SHOTS, "character_refs": REFS, "model": "vendor/clip-model"}
    out, err = asyncio.run(hub._run_tool(None, None, None, ToolCall("c1", "lampway_cinematic_shot_plan", args)))
    assert not err and json.loads(out)["total_video_usd"] == pytest.approx(1.5)
    bad, err = asyncio.run(hub._run_tool(None, None, None, ToolCall("c2", "lampway_cinematic_shot_plan", dict(args, shots=[dict(SHOTS[0], action="runs and jumps")]))))
    assert err and "one action and one camera move per shot" in bad
