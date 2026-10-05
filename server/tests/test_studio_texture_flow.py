# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""studio_texture_flow (shelf/studio_texture_flow.md section 10): refs -> texture (plan, confirm) -> restore -> pbr, as catalogued, panel-visible, jobbed Studio actions."""

import hashlib

import pytest

from lampway_server.studios.actions import ACTIONS, ActionError
from lampway_server.studios.tripo import verify
from tests.test_studio_service import Exec, svc  # noqa: F401  (the fake driver and the service factory)

pytestmark = pytest.mark.anyio

TEXTURE_PLAN = 'settings: "{\\"button\\": \\"Generate Texture 30\\", \\"remove_lighting\\": \\"true\\"}"\nverified: true\n'
TEXTURE_PLAN_40 = TEXTURE_PLAN.replace("Texture 30", "Texture 40")
REFS = {"front": "plates/front.png", "left": "plates/left.png", "right": "plates/right.png", "back": "plates/back.png"}


def test_the_three_free_steps_are_catalogued_and_nothing_free_spends():
    assert {"tripo.texture.state", "tripo.texture.refs", "tripo.texture.restore"} <= set(ACTIONS)
    for k in ("tripo.texture.state", "tripo.texture.refs", "tripo.texture.restore"):
        assert not ACTIONS[k].needs_approval and ACTIONS[k].expected_price is None
    assert ACTIONS["tripo.texture"].needs_approval and ACTIONS["tripo.texture"].expected_price == 30
    assert ACTIONS["tripo.pbr"].needs_approval and ACTIONS["tripo.pbr"].expected_price == 5


async def test_refs_runs_as_a_job_with_the_four_paths_and_leaves_a_receipt_dir(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_texture": "refs: placed\n"})
    out = await s.plan("tripo.texture.refs", {"set": "painted", **REFS}, by="agent")
    assert out["state"] == "running" and s.approvals() == []
    job = await s.wait(out["job"]["id"])
    assert job["state"] == "done"
    argv = ex.calls[0]["argv"]
    assert argv[argv.index("refs") + 1:argv.index("refs") + 9:2] == ["--front", "--left", "--right", "--back"] and "--set" in argv and argv[argv.index("--set") + 1] == "painted"
    assert "--out" in argv, "the receipt (refs.json with the sha256 of the files placed) is written into the job's directory"


async def test_a_paired_piece_carries_front_and_back_only_and_a_set_is_one_of_three(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_texture": "refs: placed\n"})
    out = await s.plan("tripo.texture.refs", {"set": "generation", "paired": True, "front": REFS["front"], "back": REFS["back"]}, by="agent")
    await s.wait(out["job"]["id"])
    assert out["state"] == "running" and "--left" not in ex.calls[0]["argv"] and "--views" in ex.calls[0]["argv"]
    with pytest.raises(ActionError, match="front, left, right and back"):
        await s.plan("tripo.texture.refs", {"set": "painted", "front": REFS["front"]}, by="agent")
    with pytest.raises(ActionError, match="set is generation, painted or custom"):
        await s.plan("tripo.texture.refs", {"set": "mine", **REFS}, by="agent")
    with pytest.raises(Exception):
        await s.plan("tripo.texture.refs", {"set": "painted", **{**REFS, "front": "../../etc/passwd"}}, by="agent")     # the jail


async def test_restore_needs_its_stamp_and_is_free(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_texture": "restored: 10-05 03:55\n"})
    with pytest.raises(ActionError, match="stamp"):
        await s.plan("tripo.texture.restore", {}, by="agent")
    out = await s.plan("tripo.texture.restore", {"stamp": "10-05 03:55"}, by="agent")
    await s.wait(out["job"]["id"])
    assert out["state"] == "running" and ex.calls[0]["argv"][-2:] == ["--stamp", "10-05 03:55"] and s.approvals() == []


async def test_a_texture_plan_reads_the_price_and_a_button_reading_40_refuses(tmp_path):
    s, ex, _ = svc(tmp_path, {"tripo_texture": TEXTURE_PLAN})
    ok = await s.plan("tripo.texture", {"res": "8K", "refs_set": "painted"}, by="agent")
    assert ok["state"] == "needs_approval" and ok["approval"]["price"] == 30 and ok["approval"]["settings"]["refs_set"] == "painted"
    s2, _, _ = svc(tmp_path / "b", {"tripo_texture": TEXTURE_PLAN_40})
    bad = await s2.plan("tripo.texture", {"res": "8K"}, by="agent")
    assert bad["state"] == "refused" and "not the expected 30" in bad["reason"]


async def test_the_texturing_last_guard_refuses_and_the_same_plan_proceeds_once_the_driver_reads_a_uv_step(tmp_path):
    s, _, _ = svc(tmp_path, {"tripo_texture": "error: texturing-last guard: no Smart UV step in this model's History\n"})
    out = await s.plan("tripo.texture", {"res": "8K"}, by="agent")
    assert out["state"] == "refused" and "Smart UV step" in out["reason"] and "tripo.uv.unwrap" in out["reason"]
    s2, _, _ = svc(tmp_path / "b", {"tripo_texture": TEXTURE_PLAN})
    assert (await s2.plan("tripo.texture", {"res": "8K"}, by="agent"))["state"] == "needs_approval"


async def test_refs_set_is_validated_on_the_texture_action(tmp_path):
    s, _, _ = svc(tmp_path, {"tripo_texture": TEXTURE_PLAN})
    with pytest.raises(ActionError, match="refs_set is generation or painted"):
        await s.plan("tripo.texture", {"res": "8K", "refs_set": "custom"}, by="agent")


def test_remove_lighting_must_read_back_as_requested():                                 # the incident in the driver's header
    st = {"remove_lighting": "false", "res": [{"t": "8K", "on": True}], "button": "Generate Texture 30", "disabled": False}
    assert any("Remove Lighting reads 'false', wanted true" in p for p in verify.texture_problems(st, res="8K", remove_lighting=True, expect_price=30))
    assert verify.texture_problems({**st, "remove_lighting": "true"}, res="8K", remove_lighting=True, expect_price=30) == []


def test_the_refs_receipt_carries_the_sha256_of_each_file_placed(tmp_path):
    files = {}
    for slot in ("front", "left", "right", "back"):
        p = tmp_path / f"{slot}.png"
        p.write_bytes(slot.encode())
        files[slot] = str(p)
    r = verify.refs_receipt(files, "painted")
    assert r["set"] == "painted" and r["files"]["front"]["sha256"] == hashlib.sha256(b"front").hexdigest() and sorted(r["files"]) == ["back", "front", "left", "right"]
    assert verify.refs_receipt({"front": files["front"], "back": files["back"]}, "generation")["paired"] is True


async def test_a_hung_texture_is_never_re_planned_until_the_captain_acknowledges(tmp_path):
    hung = "error: texture did not finish within 1100 s: HUNG (never re-click)\n"
    s, _, _ = svc(tmp_path, {"tripo_texture": lambda argv: TEXTURE_PLAN if "--go" not in argv else hung})
    plan = await s.plan("tripo.texture", {"res": "8K"}, by="agent")
    job = await s.wait((await s.confirm(plan["approval"]["id"], price=30, by="captain"))["id"])
    assert job["state"] == "hung"
    again = await s.plan("tripo.texture", {"res": "8K"}, by="agent")
    assert again["state"] == "refused" and "never re-click" in again["reason"]
    s.acknowledge_hung(job["id"], by="captain")
    assert (await s.plan("tripo.texture", {"res": "8K"}, by="agent"))["state"] == "needs_approval"
