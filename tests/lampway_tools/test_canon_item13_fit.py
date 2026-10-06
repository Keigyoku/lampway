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


class Fake:
    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    def __call__(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool in self.fail or (tool, args.get("verb")) in self.fail:
            return {"ok": False, "error": f"{tool} said no"}
        if tool == "fit_body":
            return {"ok": True, "package": args["out"], "package_sha256": "b" * 64}
        if tool == "fit_validate":
            return {"ok": True, "summary": {}, "limits": {"status": "adopted"}}
        return {"ok": True, "tool": tool, "echo": args}

    def tools(self):
        return [t for t, _a in self.calls if t != "fit_body"]


def _run(tmp_path, stage, call, **kw):
    return FO.run(stage, "Chest1", str(tmp_path), call=call, **kw)


def _through(tmp_path, call, last):
    out = None
    for st in FO.STAGES[: FO.STAGES.index(last) + 1]:
        kw = {"roles": ROLES, "body": BODY, "args": {"parts": list(ROLES)}} if st == "intake" else {}
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
    r = _run(tmp_path, "intake", Fake(), roles={"plate": "metal"}, body=BODY, args={"parts": ["plate", "skirt"]})
    assert r["ok"] is False and "skirt" in r["error"] and "never the render's colour" in r["error"], r
    bad = _run(tmp_path, "intake", Fake(), roles={"plate": "gold"}, body=BODY, args={"parts": ["plate"]})
    assert bad["ok"] is False and "gold" in bad["error"], bad


def test_each_stage_delegates_to_its_tool_and_appends_its_receipt(tmp_path):
    call = Fake()
    _through(tmp_path, call, "pose")
    rec = json.loads((tmp_path / "Chest1" / "fit" / "fit.json").read_text())
    assert [s["stage"] for s in rec["stages"]] == list(FO.STAGES[: FO.STAGES.index("pose") + 1])
    assert call.tools() == ["normalize_mesh", "run_tool", "fit_place", "fit_pose"], call.calls
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
        kw = {"roles": {"plate": "metal"}, "body": BODY, "args": {"parts": ["plate"]}} if st == "intake" else {}
        kw = {"args": {"captain_seen": True, "render_sha256": "a" * 64}, "decider": "captain"} if st == "match" else kw
        kw = {"args": {"segments": []}} if st == "pose_correct" else kw
        assert FO.run(st, "Chest1", str(t), call=call, kind="chest", **kw)["ok"], st
    s = FO.run("status", "Chest1", str(t), call=call)
    assert s["next"] == ["lampway_fit stage=bind"] and "conform" in s["not_applicable"], s


def test_intake_needs_a_body_package_that_verifies(tmp_path):
    r = _run(tmp_path, "intake", Fake(), roles=ROLES, args={"parts": list(ROLES)})
    assert r["ok"] is False and "fit_body" in r["error"], r                # no body: the package is named
    call = Fake(fail={("fit_body", "verify")})
    r = _run(tmp_path, "intake", call, roles=ROLES, body=BODY, args={"parts": list(ROLES)})
    assert r["ok"] is False and "fit_body said no" in r["error"], r
    assert "normalize_mesh" not in call.tools(), "a refused intake never normalizes"


def test_weights_need_the_body_packages_native_sidecar(tmp_path):
    call = Fake(fail={("fit_body", "weights")})
    t = tmp_path
    for st in FO.STAGES[: FO.STAGES.index("bind") + 1]:
        if st == "conform":
            continue
        kw = {"roles": {"plate": "metal"}, "body": BODY, "args": {"parts": ["plate"]}} if st == "intake" else {}
        kw = {"args": {"captain_seen": True, "render_sha256": "a" * 64}, "decider": "captain"} if st == "match" else kw
        kw = {"args": {"segments": []}} if st == "pose_correct" else kw
        assert FO.run(st, "Chest1", str(t), call=call, kind="chest", **kw)["ok"], st
    r = FO.run("weights", "Chest1", str(t), call=call)
    assert r["ok"] is False and "fit_body said no" in r["error"], r
    assert ("fit_body", {"verb": "weights", "out": BODY}) in call.calls and "fit_bind" in call.tools()
    assert not any(t_ == "fit_bind" and a.get("stage") == "weights" for t_, a in call.calls), "no weights without the sidecar"


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


def test_the_tool_through_the_real_door_runs_intake_and_refuses_bind_before_pose(tmp_path):
    """REAL binary: api.fit -> api.call -> fit_body verify and normalize_mesh (the stage tools pass their own doors)."""
    sys.path.insert(0, str(Path(__file__).parent))
    from features_support import run
    r = run(tmp_path, '''
arm = bpy.data.armatures.new("rig"); ob = link(bpy.data.objects.new("rig", arm))
bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
b = arm.edit_bones.new("pelvis"); b.head = (0, 0, 1.0); b.tail = (0, 0, 1.1)
c = arm.edit_bones.new("spine_01"); c.head = (0, 0, 1.1); c.tail = (0, 0, 1.3); c.parent = b
bpy.ops.object.mode_set(mode="OBJECT")
pkg = call("fit_body", verb="build", armature="rig", out="fit/body")
boxes("plate_raw", [((0, 0, 1.2), (0.4, 0.3, 0.5))])
out = {"pkg": pkg["ok"]}
out["no_body"] = call("fit", stage="intake", piece="Chest1", roles={"plate": "metal"}, args={"parts": ["plate"], "input": "plate_raw"})
out["intake"] = call("fit", stage="intake", piece="Chest1", kind="chest", roles={"plate": "metal"}, body=os.path.relpath(pkg["package"], root),
                     args={"parts": ["plate"], "input": "plate_raw", "turn_deg": 0, "generator": "captain_authored", "weld": "never"})
out["stamped"] = "lw_canon" in bpy.data.objects["plate_raw"]
out["bind"] = call("fit", stage="bind", piece="Chest1")
out["status"] = call("fit", piece="Chest1")
out["escape"] = call("fit", piece="../outside")
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["pkg"] and o["no_body"]["ok"] is False and "fit_body" in o["no_body"]["error"], o
    assert o["intake"]["ok"] is True and o["intake"]["receipt_path"] == "Chest1/fit/fit.json", o["intake"]
    assert o["intake"]["result"]["ok"] is True and o["stamped"], o["intake"]["result"]
    assert o["bind"]["ok"] is False and "lampway_fit_pose" in o["bind"]["error"] and o["bind"]["help"] == ["lampway_fit stage=proportion"], o["bind"]
    assert o["status"]["done"] == ["intake"] and o["status"]["next"] == ["lampway_fit stage=proportion"], o["status"]
    assert o["escape"]["ok"] is False, o["escape"]
    rec = json.loads((tmp_path / "Chest1" / "fit" / "fit.json").read_text())
    assert rec["stages"][0]["tool"] == "normalize_mesh" and rec["body"]["package_sha256"], rec
