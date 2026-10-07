# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 13 (canon 03 B, G), lampway_fit: the canonical order as refusals, the role gate, the fit record.
The stage tools are called through a seam (api.call in the tool); here a recording fake answers, so the gates are measured alone.
G03.2 (bind before pose refused, naming lampway_fit_pose) and G03.3 (a part without a role refused) are built here, with the
contract's other refusals (canon 03 G): the body package (verified at intake, its weight sidecar at weights) and a geometry stage
after a recorded texture without texture_discard_ack."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import fit_order as FO  # noqa: E402

ROLES = {"plate": "metal", "skirt": "leather"}
BODY = "fit/body/abcd1234"
INTAKE = {"parts": ["plate", "skirt"], "input": "Chest1_raw", "source": "Chest1_src"}


class Fake:
    def __init__(self, fail=(), body=None, source_pass=True, run_ok=True):
        self.calls, self.fail = [], set(fail)
        self.body = body or {"closed": True, "boundary_edges": 0, "head_included": True, "head_joint": "head"}
        self.source_pass, self.run_ok = source_pass, run_ok

    def __call__(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool in self.fail or (tool, args.get("verb")) in self.fail:
            return {"ok": False, "error": f"{tool} said no"}
        if tool == "fit_body":
            return {"ok": True, "package": args["out"], "package_sha256": "b" * 64, "body": dict(self.body)}
        if tool == "fit_source_check":
            return {"ok": True, "pass": self.source_pass, "reason": None if self.source_pass else "glove is turned 22.0 deg off bracer"}
        if tool == "run_tool":
            return {"ok": True, "rc": 0 if self.run_ok else 1, "ok_run": self.run_ok}
        if tool == "fit_validate":
            return {"ok": True, "summary": {}, "limits": {"status": "adopted"}}
        if tool == "fit_export":
            return {"ok": True, "out_dir": "export/x", "limits": "limits: adopted"}         # fit_export's limits is the README's LINE
        return {"ok": True, "tool": tool, "echo": args}

    def tools(self):
        return [t for t, _a in self.calls if t != "fit_body"]


def _run(tmp_path, stage, call, **kw):
    return FO.run(stage, "Chest1", str(tmp_path), call=call, **kw)


def _through(tmp_path, call, last, roles=ROLES):
    out = None
    for st in FO.STAGES[: FO.STAGES.index(last) + 1]:
        if st == "conform" and not any(r in FO.SOFT for r in roles.values()):
            continue
        kw = {"roles": roles, "body": BODY, "args": dict(INTAKE, parts=list(roles))} if st == "intake" else {}
        if st == "match":
            kw = {"args": {"captain_seen": True, "render_sha256": "a" * 64}, "decider": "captain"}
        if st == "pose_correct":
            kw = {"args": {"segments": []}}
        out = _run(tmp_path, st, call, kind="chest", **kw)
        assert out["ok"], (st, out)
    return out


def test_status_with_no_record_names_intake_as_the_next_stage(tmp_path):
    s = _run(tmp_path, "status", Fake())
    assert s["ok"] and s["done"] == [] and s["next"] == ["lampway_fit stage=intake"], s


def test_g03_2_bind_before_pose_is_refused_naming_lampway_fit_pose(tmp_path):
    call = Fake()
    _through(tmp_path, call, "place")
    r = _run(tmp_path, "bind", call, kind="chest")
    assert r["ok"] is False and "lampway_fit_pose" in r["error"] and "stage=pose_correct" in r["help"][0], r
    assert not any(t == "fit_bind" for t, _a in call.calls), "a refused stage never calls its tool"


def test_g03_3_a_part_without_a_role_is_refused(tmp_path):
    r = _run(tmp_path, "intake", Fake(), roles={"plate": "metal"}, body=BODY, args=dict(INTAKE))
    assert r["ok"] is False and "skirt" in r["error"] and "never the render's colour" in r["error"], r
    bad = _run(tmp_path, "intake", Fake(), roles={"plate": "gold"}, body=BODY, args=dict(INTAKE, parts=["plate"]))
    assert bad["ok"] is False and "gold" in bad["error"], bad


def test_each_stage_delegates_to_its_tool_and_appends_its_receipt(tmp_path):
    call = Fake()
    _through(tmp_path, call, "pose")
    rec = json.loads((tmp_path / "Chest1" / "fit" / "fit.json").read_text())
    assert [s["stage"] for s in rec["stages"]] == list(FO.STAGES[: FO.STAGES.index("pose") + 1])
    assert call.tools() == ["fit_source_check", "normalize_mesh", "run_tool", "fit_place", "fit_pose"], call.calls
    assert call.calls[1] == ("fit_source_check", {"piece": "Chest1_raw", "source": "Chest1_src"}), call.calls[1]
    assert dict(call.calls[2][1]) == {"input": "Chest1_raw"}, "source and parts are the orchestrator's, never normalize_mesh's"
    assert ("fit_pose", {"kind": "chest", "apply": True}) in call.calls, "the closest pose is the fit pose: the armature is put in it (B.9)"
    assert rec["body"] == {"package": BODY, "package_sha256": "b" * 64}, rec.get("body")
    assert all(len(s["receipt_sha256"]) == 64 for s in rec["stages"]) and rec["roles"] == ROLES
    m = next(s for s in rec["stages"] if s["stage"] == "match")
    assert m["decider"] == "captain" and m["tool"] is None


def test_match_needs_the_captains_signed_render(tmp_path):
    call = Fake()
    _through(tmp_path, call, "proportion")
    r = _run(tmp_path, "match", call, args={"captain_seen": False})
    assert r["ok"] is False and "captain" in r["error"], r


def test_a_failing_stage_tool_is_not_recorded_and_the_order_holds(tmp_path):
    call = Fake(fail={"fit_place"})
    _through(tmp_path, call, "match")
    r = _run(tmp_path, "place", call, kind="chest")
    assert r["ok"] is False and "fit_place said no" in r["error"], r
    s = _run(tmp_path, "status", call)
    assert s["next"] == ["lampway_fit stage=place"], s


def test_conform_is_skipped_without_soft_parts_refused_for_metal_and_unbuilt_otherwise(tmp_path):
    call = Fake()
    _through(tmp_path, call, "openings")
    r = _run(tmp_path, "conform", call, args={"parts": ["plate"]})
    assert r["ok"] is False and "metal" in r["error"], r                 # canon 03 INV-03.2: a metal part never conforms
    r = _run(tmp_path, "conform", call, args={"parts": ["skirt"]})
    assert r["ok"] is False and "03-H2" in r["error"], r                  # the soft-part deformer waits on the captain's decision
    t = tmp_path / "metal_only"
    t.mkdir()
    for st in FO.STAGES[: FO.STAGES.index("openings") + 1]:
        kw = {"roles": {"plate": "metal"}, "body": BODY, "args": dict(INTAKE, parts=["plate"])} if st == "intake" else {}
        kw = {"args": {"captain_seen": True, "render_sha256": "a" * 64}, "decider": "captain"} if st == "match" else kw
        kw = {"args": {"segments": []}} if st == "pose_correct" else kw
        assert FO.run(st, "Chest1", str(t), call=call, kind="chest", **kw)["ok"], st
    s = FO.run("status", "Chest1", str(t), call=call)
    assert s["next"] == ["lampway_fit stage=bind"] and "conform" in s["not_applicable"], s


def test_intake_needs_a_body_package_that_verifies(tmp_path):
    r = _run(tmp_path, "intake", Fake(), roles=ROLES, args=dict(INTAKE))
    assert r["ok"] is False and "fit_body" in r["error"], r                # no body: the package is named
    call = Fake(fail={("fit_body", "verify")})
    r = _run(tmp_path, "intake", call, roles=ROLES, body=BODY, args=dict(INTAKE))
    assert r["ok"] is False and "fit_body said no" in r["error"], r
    assert "normalize_mesh" not in call.tools(), "a refused intake never normalizes"


def test_weights_need_the_body_packages_native_sidecar(tmp_path):
    call = Fake(fail={("fit_body", "weights")})
    t = tmp_path
    for st in FO.STAGES[: FO.STAGES.index("bind") + 1]:
        if st == "conform":
            continue
        kw = {"roles": {"plate": "metal"}, "body": BODY, "args": dict(INTAKE, parts=["plate"])} if st == "intake" else {}
        kw = {"args": {"captain_seen": True, "render_sha256": "a" * 64}, "decider": "captain"} if st == "match" else kw
        kw = {"args": {"segments": []}} if st == "pose_correct" else kw
        assert FO.run(st, "Chest1", str(t), call=call, kind="chest", **kw)["ok"], st
    r = FO.run("weights", "Chest1", str(t), call=call)
    assert r["ok"] is False and "fit_body said no" in r["error"], r
    assert ("fit_body", {"verb": "weights", "out": BODY}) in call.calls and "fit_bind" in call.tools()
    assert not any(t_ == "fit_bind" and a.get("stage") == "weights" for t_, a in call.calls), "no weights without the sidecar"
    assert ("fit_bind", {"stage": "plan", "roles": {"plate": "metal"}}) in call.calls, "bind is fit_bind's plan"


def test_a_geometry_stage_after_a_recorded_texture_needs_texture_discard_ack(tmp_path):
    from mixar.modules.lampway_tools.pipeline import armor_piece as AP
    call = Fake()
    _through(tmp_path, call, "pose")
    AP.record(str(tmp_path), "Chest1", AP.TEXTURE, mesh_hash="m1")
    r = _run(tmp_path, "openings", call)
    assert r["ok"] is False and "texture_discard_ack" in r["error"], r
    assert "fit_openings" not in call.tools()
    ok = _run(tmp_path, "openings", call, texture_discard_ack=True)
    assert ok["ok"], ok
    assert call.calls[-1] == ("fit_openings", {"stage": "detect", "texture_discard_ack": True}), call.calls[-1]


def test_the_receipt_and_the_status_view(tmp_path):
    call = Fake()
    r = _through(tmp_path, call, "place")
    assert set(r) >= {"piece", "stage", "ok", "receipt_path", "sha256", "next", "limits_status"}, r
    assert r["receipt_path"] == "Chest1/fit/fit.json" and len(r["sha256"]) == 64 and r["next"] == ["lampway_fit stage=pose_correct"], r
    s = _run(tmp_path, "status", call)
    assert s["refused"]["bind"] == "needs pose_correct first", s["refused"]
    assert "pose_correct" not in s["refused"], "the next stage is allowed"


@pytest.mark.parametrize("body, needle", [({"closed": False, "boundary_edges": 12, "head_included": False, "head_joint": "head"}, "not closed"),
                                          ({"closed": True, "boundary_edges": 0, "head_included": False, "head_joint": None}, "head"),
                                          ({"closed": None, "boundary_edges": None, "head_included": None, "head_joint": None}, "rebuild")])
def test_intake_refuses_a_body_package_that_is_not_closed_with_its_head(tmp_path, body, needle):
    call = Fake(body=body)
    r = _run(tmp_path, "intake", call, roles=ROLES, body=BODY, args=dict(INTAKE))
    assert r["ok"] is False and needle in r["error"] and "normalize_mesh" not in call.tools(), r


def test_intake_runs_the_source_part_check_first_and_refuses_a_detached_part(tmp_path):
    call = Fake(source_pass=False)
    r = _run(tmp_path, "intake", call, roles=ROLES, body=BODY, args=dict(INTAKE))
    assert r["ok"] is False and "22.0 deg" in r["error"] and "normalize_mesh" not in call.tools(), r
    r = _run(tmp_path, "intake", Fake(), roles=ROLES, body=BODY, args={"parts": list(ROLES), "input": "Chest1_raw"})
    assert r["ok"] is False and "source" in r["error"] and "lampway_fit_source_check" in r["error"], r


def test_a_proportion_run_that_exits_non_zero_is_not_recorded(tmp_path):
    call = Fake(run_ok=False)
    _through(tmp_path, call, "intake")
    r = _run(tmp_path, "proportion", call, args={"args": ["waist", "x.json"]})
    assert r["ok"] is False and "rc 1" in r["error"], r
    assert _run(tmp_path, "status", call)["next"] == ["lampway_fit stage=proportion"]


def test_weights_bind_from_the_package_and_return_validate_writes_its_file_and_export_reads_it(tmp_path):
    call = Fake()
    _through(tmp_path, call, "openings", roles={"plate": "metal"})
    assert _run(tmp_path, "bind", call, args={"piece": "p", "armature": "rig"})["ok"]
    assert call.calls[-1] == ("fit_bind", {"stage": "plan", "piece": "p", "armature": "rig", "roles": {"plate": "metal"}}), "the roles are the intake's record"
    w = _run(tmp_path, "weights", call, args={"piece": "p", "armature": "rig"})
    assert w["ok"], w
    assert call.calls[-2] == ("fit_bind", {"stage": "weights", "piece": "p", "armature": "rig", "body": BODY}), call.calls[-2]
    assert call.calls[-1] == ("fit_bind", {"stage": "return", "piece": "p", "armature": "rig"}), call.calls[-1]
    v = _run(tmp_path, "validate", call, args={"bound": "p_rest", "original": "src"})
    assert v["ok"] and v["limits_status"] == "adopted" and call.calls[-1][1]["stage"] == "measure", (v, call.calls[-1])
    assert call.calls[-1][1]["roles"] == {"plate": "metal"}
    vf = tmp_path / "Chest1" / "fit" / "validation.json"
    assert json.loads(vf.read_text())["limits"]["status"] == "adopted"
    e = _run(tmp_path, "export", call, args={"object": "p_rest", "armature": "rig", "out_dir": "export/x", "bind_check": "bc.json"})
    assert e["ok"], e
    assert call.calls[-1] == ("fit_export", {"object": "p_rest", "armature": "rig", "out_dir": "export/x", "bind_check": "bc.json", "body": BODY,
                                             "validation": "Chest1/fit/validation.json"}), call.calls[-1]


def test_a_later_stage_takes_the_kind_recorded_at_intake(tmp_path):
    call = Fake()
    _through(tmp_path, call, "match")
    assert _run(tmp_path, "place", call)["ok"]                      # no kind passed: the intake's record names it
    assert call.calls[-1] == ("fit_place", {"kind": "chest"}), call.calls[-1]


def test_intake_accepts_measured_native_openings_without_claiming_watertightness(tmp_path):
    body = {"closed": False, "boundary_edges": 6, "raw_boundary_edges": 108,
            "non_manifold_edges": 0, "raw_non_manifold_edges": 0,
            "head_included": True, "head_joint": "head", "head_winding": 0.9,
            "inside_method": "generalized_winding_number", "native_openings_accepted": True}
    call = Fake(body=body)
    result = _run(tmp_path, "intake", call, roles=ROLES, body=BODY, args=dict(INTAKE))
    assert result["ok"], result
    assert "normalize_mesh" in call.tools()
