"""The online Studios inside the Client: plan (read back, spend nothing) -> the USER's confirm in the Client -> a server job that
runs the shelf's AXI driver -> results for the Client to import. Nothing here touches a browser or a credit: the driver is a fake
executor returning text shaped like the real drivers' AXI/TOON output (shapes read from the shelf sources, 2026-10-05; the live
run against the real Studio is the owner's). Laws (memory tripo-studio-invariants, tripo-hung-job-quirk): read back every setting,
4 variants at maximum polycount, a saved COPY only, texturing last, paired pieces front+back only, a hung job is never re-clicked,
and no agent or worker can confirm a spend."""

import asyncio
import json
import os
from pathlib import Path

import pytest

from lampway_server.studios import toon
from lampway_server.studios.actions import ACTIONS, ActionError
from lampway_server.studios.approvals import Approvals, ApprovalError
from lampway_server.studios.service import StudioService

pytestmark = pytest.mark.anyio

MESH_PLAN = """dry_run: verified
polycount_read_back: 25000
generate_button: Generate 100
privacy: Sharing Only
thumbnails_seen: 4
help[1]:
  - "Run `x`"
"""
STATE_FRESH = """credits: 1450
faces: 24000
utilization: null
history: "[\\"Current Version\\"]"
smart_uv_buttons: "[\\"Unwrap UV 20\\", \\"Cancel\\"]"
"""
STATE_DATED = STATE_FRESH.replace('Current Version', '10-05 03:55')


class Exec:
    """The fake driver process: scripted text per verb; records (argv, armed) for every call."""

    def __init__(self, outputs=None):
        self.outputs, self.calls = dict(outputs or {}), []

    def __call__(self, argv, env, timeout):
        self.calls.append({"argv": list(argv), "armed": env.get("LAMPWAY_STUDIO_ARMED") == "1"})
        key = next((k for k in self.outputs if k in " ".join(argv)), None)
        out = self.outputs.get(key, "")
        if callable(out):
            out = out(argv)
        rc = 1 if out.startswith("error:") else 0
        for i, a in enumerate(argv):                          # a real run leaves files in its --out directory
            if a == "--out" and i + 1 < len(argv) and rc == 0 and "--dry-run" not in argv:
                Path(argv[i + 1]).mkdir(parents=True, exist_ok=True)
                (Path(argv[i + 1]) / "attempt_1.fbx").write_bytes(b"fbx")
        return rc, out


def make_shelf(path):
    (path / "studios" / "tripo").mkdir(parents=True, exist_ok=True)
    for n in ("tripo_mesh", "tripo_uv", "tripo_texture", "tripo_image", "tripo_fetch"):
        (path / "studios" / "tripo" / f"{n}.py").write_text("# driver")
    return path


def svc(tmp_path, outputs=None, shelf=None, **kw):
    """A service over a fake executor; by default with the owner's shelf configured (``shelf=False``: only the bundled ports)."""
    ex = Exec(outputs)
    root = tmp_path / "root"
    (root / "plates").mkdir(parents=True)
    for v in ("front", "left", "right", "back"):
        (root / "plates" / f"{v}.png").write_bytes(b"png")
    if shelf is None:
        shelf = make_shelf(tmp_path / "shelf")
    return StudioService(root, ex, shelf=shelf or None, **kw), ex, root


MESH_ARGS = {"front": "plates/front.png", "left": "plates/left.png", "right": "plates/right.png", "back": "plates/back.png"}


# ------------------------------------------------------------------ the output shape
def test_toon_parses_the_drivers_kv_tables_errors_and_help():
    p = toon.parse('credits: 1450\nmeta:\n  a: 1\n  b: "x: y"\nscores[2]{file,utilization}:\n  a.fbx,76.6\n  b.fbx,70\nhelp[1]:\n  - "Run `x`"\n')
    assert p.kv["credits"] == 1450 and p.kv["meta"] == {"a": 1, "b": "x: y"} and p.tables["scores"] == [
        {"file": "a.fbx", "utilization": 76.6}, {"file": "b.fbx", "utilization": 70}] and p.help == ["x"] and p.error is None
    e = toon.parse('error: Unwrap button does not read "Unwrap UV 20"\nhelp[1]:\n  - "Run `state`"\n')
    assert e.error.startswith("Unwrap button") and e.kv == {}
    assert toon.parse("count: 0 of 0 total\nseeds[0]:\n").tables["seeds"] == []


# ------------------------------------------------------------------ the catalog and its laws
def test_every_action_names_its_studio_its_spend_and_the_engine():
    assert {"tripo.mesh", "tripo.texture", "tripo.pbr", "tripo.image", "tripo.uv.unwrap", "tripo.uv.clone", "tripo.uv.retry",
            "tripo.uv.save", "tripo.state", "tripo.fetch"} <= set(ACTIONS)
    rest = {k for k, a in ACTIONS.items() if a.driver.startswith("rest.")}                  # the REST studios: their price is read by the driver's plan, so none carries an expected price
    assert rest and all(ACTIONS[k].needs_approval and ACTIONS[k].expected_price is None for k in rest)
    spend = {k for k, a in ACTIONS.items() if a.needs_approval} - rest
    assert spend == {"tripo.mesh", "tripo.texture", "tripo.pbr", "tripo.image", "tripo.uv.unwrap"}
    assert ACTIONS["tripo.mesh"].expected_price == 100 and ACTIONS["tripo.texture"].expected_price == 30 \
        and ACTIONS["tripo.pbr"].expected_price == 5 and ACTIONS["tripo.uv.unwrap"].expected_price == 20
    assert not any("privacy" in k for k in ACTIONS), "nothing here changes the privacy setting"


async def test_a_paired_piece_sends_front_and_back_only_and_the_driver_gets_views(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_mesh": MESH_PLAN})
    out = await s.plan("tripo.mesh", {"front": "plates/front.png", "back": "plates/back.png", "paired": True}, by="agent")
    assert out["state"] == "needs_approval"
    argv = ex.calls[0]["argv"]
    assert "--views" in argv and argv[argv.index("--views") + 1] == "front,back" and "--left" not in argv and "--right" not in argv
    with pytest.raises(ActionError, match="front, left, right and back"):
        await s.plan("tripo.mesh", {"front": "plates/front.png", "back": "plates/back.png"}, by="agent")
    bundled, _, _ = svc(tmp_path / "b", {"tripo_mesh": MESH_PLAN}, shelf=False)
    with pytest.raises(ActionError, match="LAMPWAY_STUDIO_SHELF"):
        await bundled.plan("tripo.mesh", {"front": "plates/front.png", "back": "plates/back.png", "paired": True}, by="agent")


async def test_mesh_always_asks_for_four_variants_at_maximum_polycount_never_less(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_mesh": MESH_PLAN})
    for bad in ({"polycount": "12000"}, {"count": 2}, {"variants": 1}):
        with pytest.raises(ActionError, match="maximum|four|4"):
            await s.plan("tripo.mesh", {**MESH_ARGS, **bad}, by="agent")
    await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    argv = ex.calls[0]["argv"]
    assert argv[argv.index("--polycount") + 1] == "max" and "--dry-run" in argv


async def test_paths_must_stay_inside_the_project_root(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_mesh": MESH_PLAN})
    with pytest.raises(ActionError, match="outside"):
        await s.plan("tripo.mesh", {**MESH_ARGS, "front": "/etc/passwd"}, by="agent")
    assert ex.calls == []


# ------------------------------------------------------------------ plan -> approval -> job
async def test_a_spend_plan_runs_a_dry_run_reads_the_price_back_and_waits_for_the_captain(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_mesh": MESH_PLAN})
    out = await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    assert out["state"] == "needs_approval" and out["approval"]["price"] == 100 and out["approval"]["state"] == "pending"
    assert out["approval"]["settings"]["polycount_read_back"] == 25000 and out["approval"]["settings"]["privacy"] == "Sharing Only"
    assert [c["armed"] for c in ex.calls] == [False], "the plan clicks nothing: the guard is not armed"
    assert s.jobs() == [] and len(s.approvals()) == 1


async def test_a_price_that_is_not_the_expected_one_never_becomes_an_approval(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_mesh": MESH_PLAN.replace("Generate 100", "Generate 130")})
    out = await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    assert out["state"] == "refused" and "130" in out["reason"] and "100" in out["reason"] and s.approvals() == []


async def test_a_driver_refusal_is_the_plans_refusal_with_the_drivers_own_words(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_mesh": 'error: polycount 12000 is not the maximum 25000 for Quad\nhelp[1]:\n  - "Run `x`"\n'})
    out = await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    assert out["state"] == "refused" and "not the maximum" in out["reason"]


async def test_confirm_by_the_captain_runs_the_live_driver_armed_for_that_one_run(tmp_path):
    s, ex, root = svc(tmp_path, {"tripo_mesh": MESH_PLAN})
    plan = await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    job = await s.confirm(plan["approval"]["id"], price=100, by="captain")
    done = await s.wait(job["id"])
    live = ex.calls[-1]
    assert live["armed"] is True and "--dry-run" not in live["argv"] and done["state"] == "done"
    assert len(ex.calls) == 2 and [c["armed"] for c in ex.calls] == [False, True]
    out_dir = Path(live["argv"][live["argv"].index("tripo_mesh") + 1]) if "tripo_mesh" in live["argv"] else None
    assert s.approvals()[0]["state"] == "used"


async def test_the_live_run_uses_a_fresh_out_directory_because_drivers_never_overwrite_a_record(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_mesh": MESH_PLAN})
    plan = await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    await s.wait((await s.confirm(plan["approval"]["id"], price=100, by="captain"))["id"])
    plan_out = next(a for a in ex.calls[0]["argv"] if "plan-" in a)
    live_out = next(a for a in ex.calls[1]["argv"] if "job-" in a)
    assert plan_out != live_out


async def test_confirming_with_a_different_price_than_the_one_shown_is_refused(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_mesh": MESH_PLAN})
    plan = await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    with pytest.raises(ApprovalError, match="price"):
        await s.confirm(plan["approval"]["id"], price=99, by="captain")
    assert len(ex.calls) == 1 and s.approvals()[0]["state"] == "pending"


async def test_an_approval_is_one_shot_and_expires(tmp_path):
    clock = [1000.0]
    s, ex, _ = svc(tmp_path, {"tripo_mesh": MESH_PLAN}, now=lambda: clock[0])
    p1 = await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    await s.wait((await s.confirm(p1["approval"]["id"], price=100, by="captain"))["id"])
    with pytest.raises(ApprovalError, match="used"):
        await s.confirm(p1["approval"]["id"], price=100, by="captain")
    p2 = await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    clock[0] += 3600
    with pytest.raises(ApprovalError, match="expired"):
        await s.confirm(p2["approval"]["id"], price=100, by="captain")


async def test_only_the_captain_can_confirm_never_the_agent_or_a_worker(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_mesh": MESH_PLAN})
    plan = await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    for who in ("agent", "worker-2", "swarm", ""):
        with pytest.raises(ApprovalError, match="user"):
            await s.confirm(plan["approval"]["id"], price=100, by=who)
    assert [c["armed"] for c in ex.calls] == [False]


async def test_the_captain_can_reject_and_a_rejected_approval_cannot_be_confirmed(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_mesh": MESH_PLAN})
    plan = await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    s.reject(plan["approval"]["id"], by="captain")
    with pytest.raises(ApprovalError, match="rejected"):
        await s.confirm(plan["approval"]["id"], price=100, by="captain")


# ------------------------------------------------------------------ Smart UV: a saved COPY only, texturing last
async def test_unwrap_plans_from_the_state_and_refuses_on_an_original_with_dated_history_cards(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_uv": STATE_DATED})
    out = await s.plan("tripo.uv.unwrap", {}, by="agent")
    assert out["state"] == "refused" and "saved copy" in out["reason"].lower() and "clone" in out["reason"]
    s2, ex2, _ = svc(tmp_path / "b", {"tripo_uv": STATE_FRESH})
    ok = await s2.plan("tripo.uv.unwrap", {}, by="agent")
    assert ok["state"] == "needs_approval" and ok["approval"]["price"] == 20 and ex2.calls[0]["argv"][-1] == "state"


async def test_unwrap_refuses_when_the_button_does_not_read_the_expected_price(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_uv": STATE_FRESH.replace("Unwrap UV 20", "Unwrap UV 35")})
    out = await s.plan("tripo.uv.unwrap", {}, by="agent")
    assert out["state"] == "refused" and "35" in out["reason"]


async def test_texturing_comes_last_a_texture_plan_needs_a_smart_uv_step_in_the_history(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_texture": 'error: texturing-last guard: no Smart UV step in this model\'s History\n'})
    out = await s.plan("tripo.texture", {}, by="agent")
    assert out["state"] == "refused" and "Smart UV" in out["reason"]


async def test_the_free_steps_run_at_once_with_no_approval(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_uv": "credits: 1450\nfaces: 24000\n"})
    out = await s.plan("tripo.uv.clone", {"version": "Current Version", "expect_faces": 24000}, by="agent")
    assert out["state"] == "running" and out["job"]["action"] == "tripo.uv.clone" and s.approvals() == []
    job = await s.wait(out["job"]["id"])
    assert job["state"] == "done" and job["kv"]["credits"] == 1450


# ------------------------------------------------------------------ results and the hung-job rule
async def test_a_finished_job_lists_its_files_for_the_client_to_import(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_uv": STATE_FRESH, "unwrap": "row: 1\n"})
    plan = await s.plan("tripo.uv.unwrap", {}, by="agent")
    job = await s.wait((await s.confirm(plan["approval"]["id"], price=20, by="captain"))["id"])
    assert job["state"] == "done" and [f["name"] for f in job["files"]] == ["attempt_1.fbx"] and job["files"][0]["size"] == 3
    assert "path" not in job["files"][0], "the Client fetches by name through the server, never a server path"


async def test_a_hung_job_is_never_re_clicked_until_it_is_acknowledged(tmp_path):
    hung = 'error: no UV mesh arrived within 300 s: HUNG (memory tripo-hung-job-quirk) - reload once, check credits, never re-click\n'
    s, ex, _ = svc(tmp_path, {"tripo_uv": lambda argv: STATE_FRESH if argv[-1] == "state" else hung})
    plan = await s.plan("tripo.uv.unwrap", {}, by="agent")
    job = await s.wait((await s.confirm(plan["approval"]["id"], price=20, by="captain"))["id"])
    assert job["state"] == "hung"
    again = await s.plan("tripo.uv.unwrap", {}, by="agent")
    assert again["state"] == "refused" and "hung" in again["reason"].lower() and "never re-click" in again["reason"]
    s.acknowledge_hung(job["id"], by="captain")
    assert (await s.plan("tripo.uv.unwrap", {}, by="agent"))["state"] == "needs_approval"


# ------------------------------------------------------------------ the engine
async def test_the_shelf_driver_is_run_directly_when_the_shelf_is_configured(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_mesh": MESH_PLAN})
    await s.plan("tripo.mesh", MESH_ARGS, by="agent")
    assert str(tmp_path / "shelf" / "studios" / "tripo" / "tripo_mesh.py") in ex.calls[0]["argv"]
    b, bex, _ = svc(tmp_path / "bundled", {"tripo_mesh": MESH_PLAN}, shelf=False)
    await b.plan("tripo.mesh", MESH_ARGS, by="agent")
    assert "lampway_server.studios.tripo.tripo_mesh" in bex.calls[0]["argv"]


async def test_the_uv_driver_needs_the_shelf_because_it_is_not_bundled(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_uv": STATE_FRESH}, shelf=False)
    with pytest.raises(ActionError, match="LAMPWAY_STUDIO_SHELF"):
        await s.plan("tripo.uv.unwrap", {}, by="agent")
    assert ex.calls == []


async def test_another_studios_driver_resolves_under_its_own_shelf_folder(tmp_path, monkeypatch):
    from lampway_server.studios import actions as A
    s, ex, _ = svc(tmp_path, {"meshy_state": "credits: 80\n"})
    (tmp_path / "shelf" / "studios" / "meshy").mkdir(parents=True)
    (tmp_path / "shelf" / "studios" / "meshy" / "meshy_state.py").write_text("# driver")
    monkeypatch.setitem(A.ACTIONS, "meshy.state", A.Action("meshy.state", "meshy", "Read Meshy", "meshy_state", validate=A._v_none,
                                                          run_args=lambda c, o: ["state"]))
    out = await s.plan("meshy.state", {}, by="agent")
    assert out["state"] == "running"
    job = await s.wait(out["job"]["id"])
    assert job["state"] == "done" and str(tmp_path / "shelf" / "studios" / "meshy" / "meshy_state.py") in ex.calls[0]["argv"]
    monkeypatch.setitem(A.ACTIONS, "hi3d.state", A.Action("hi3d.state", "hi3d", "Read Hi3D", "hi3d_state", validate=A._v_none, run_args=lambda c, o: ["state"]))
    with pytest.raises(ActionError, match="LAMPWAY_STUDIO_SHELF"):
        await s.plan("hi3d.state", {}, by="agent")


# ------------------------------------------------------------------ tripo.regen: free seed rerolls on the Studio (Wave 0: the driver was bundled with no action row)
REGEN = ("tripo.regen.retry", "tripo.regen.sift", "tripo.regen.harvest", "tripo.regen.collect", "tripo.regen.apply", "tripo.regen.discard")


def test_the_regen_driver_has_an_action_row_for_every_verb_and_none_of_them_spends():
    assert set(REGEN) <= set(ACTIONS)
    assert not any(ACTIONS[a].needs_approval for a in REGEN), "a whole-piece regen is free on the user's plan"
    assert all(ACTIONS[a].driver == "tripo_regen" and ACTIONS[a].studio == "tripo" for a in REGEN)
    assert "tripo.regen.region" not in ACTIONS, "an exact-region retry needs the user's approval flag: not offered as an action"


async def test_regen_actions_run_the_bundled_driver_with_the_verb_and_validated_arguments(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_regen": "credits: 1450\nfaces: 30000\n"}, shelf=False)
    out = await s.plan("tripo.regen.retry", {"stamp": "10-04 12:00", "faces": 30000}, by="agent")
    assert out["state"] == "running" and s.approvals() == []
    await s.wait(out["job"]["id"])
    argv = ex.calls[-1]["argv"]
    assert argv[1:3] == ["-m", "lampway_server.studios.tripo.tripo_regen"] and argv[3] == "retry" and argv[5:] == ["10-04 12:00", "30000"] and ex.calls[-1]["armed"] is True
    out = await s.plan("tripo.regen.sift", {"faces": 30000, "n": 3}, by="agent")
    await s.wait(out["job"]["id"])
    assert ex.calls[-1]["argv"][3] == "sift" and ex.calls[-1]["argv"][-2:] == ["--n", "3"]
    for verb, args in (("apply", {}), ("discard", {"expect_faces": 30000})):
        await s.wait((await s.plan(f"tripo.regen.{verb}", args, by="agent"))["job"]["id"])
        assert ex.calls[-1]["argv"][3] == verb
    assert ex.calls[-1]["argv"][-2:] == ["--expect-faces", "30000"]


async def test_regen_arguments_are_validated_before_any_driver_runs(tmp_path):
    s, ex, _ = svc(tmp_path, shelf=False)
    for action, args in (("tripo.regen.retry", {"stamp": "10-04 12:00"}), ("tripo.regen.retry", {"stamp": "", "faces": 3}),
                         ("tripo.regen.sift", {"faces": 3, "n": 0}), ("tripo.regen.sift", {"faces": 3, "n": 11}), ("tripo.regen.harvest", {"faces": "x", "stamp": "s"})):
        with pytest.raises(ActionError):
            await s.plan(action, args, by="agent")
    assert ex.calls == []
