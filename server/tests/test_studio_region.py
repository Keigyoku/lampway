"""tripo.regen.region (specs/shelf/tripo_reroll.md, PIECE_PIPELINE step 7): the EXACT-box Edit Mesh retry. The approval flag the driver demands
(--approved-exact-region) is the USER's confirm in the Studios panel: the plan reads the state back and proposes an approval at 0 credits; only the confirmed run
carries the flag. An agent passing the flag itself is refused; the box is checked before any driver runs."""

import asyncio

import pytest

from lampway_server.studios.actions import ACTIONS, ActionError
from lampway_server.studios.approvals import ApprovalError

from tests.test_studio_service import STATE_FRESH, svc

pytestmark = pytest.mark.anyio

BOX = "-0.1,-0.2,1.3,0.1,0.0,1.5"
REGION_DONE = "seconds: 140\nfaces_previous: 24000\nfaces_current: 24012\n"


def _plan(s, args, by="agent"):
    return asyncio.run(s.plan("tripo.regen.region", args, by))


def test_the_region_action_exists_and_needs_the_users_approval():
    a = ACTIONS["tripo.regen.region"]
    assert a.needs_approval is True and a.expected_price == 0 and a.driver == "tripo_regen"


def test_the_plan_reads_the_state_back_and_proposes_a_free_approval_without_the_flag(tmp_path):
    s, ex, root = svc(tmp_path, {"state": STATE_FRESH, "region": REGION_DONE})
    out = _plan(s, {"faces": 24000, "bbox_blender": BOX, "pad_m": 0.01})
    assert out["state"] == "needs_approval" and out["approval"]["price"] == 0, out
    assert all("--approved-exact-region" not in c["argv"] for c in ex.calls) and not any(c["armed"] for c in ex.calls)
    assert out["approval"]["settings"]["bbox_blender"] == [-0.1, -0.2, 1.3, 0.1, 0.0, 1.5]
    with pytest.raises(ApprovalError):
        asyncio.run(s.confirm(out["approval"]["id"], 0, "agent"))
    job = asyncio.run(s.confirm(out["approval"]["id"], 0, "captain"))
    run = ex.calls[-1]
    assert run["armed"] is True and "--approved-exact-region" in run["argv"] and "region" in run["argv"] and "-0.1,-0.2,1.3,0.1,0,1.5" in run["argv"], run
    assert job["action"] == "tripo.regen.region"


def test_an_agent_cannot_pass_the_approval_flag_itself():
    with pytest.raises(ActionError, match="the user's confirm in the Studios panel"):
        ACTIONS["tripo.regen.region"].validate({"faces": 24000, "bbox_blender": BOX, "approved_exact_region": True}, lambda p: p)


def test_a_bad_box_or_pad_is_refused_before_any_driver_runs():
    v = ACTIONS["tripo.regen.region"].validate
    with pytest.raises(ActionError, match="x0,y0,z0,x1,y1,z1"):
        v({"faces": 24000, "bbox_blender": "1,2,3"}, lambda p: p)
    with pytest.raises(ActionError, match="min corner"):
        v({"faces": 24000, "bbox_blender": "0.1,0,0,0,0.1,0.1"}, lambda p: p)
    with pytest.raises(ActionError, match="pad_m"):
        v({"faces": 24000, "bbox_blender": BOX, "pad_m": 0.2}, lambda p: p)


def test_a_model_whose_face_count_differs_is_refused_with_the_next_step(tmp_path):
    s, ex, root = svc(tmp_path, {"state": STATE_FRESH})
    out = _plan(s, {"faces": 25000, "bbox_blender": BOX})
    assert out["state"] == "refused" and "24000" in out["reason"] and "tripo.uv.select" in out["reason"], out
