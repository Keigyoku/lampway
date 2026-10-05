# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""seed_audit (specs/shelf/seed_audit.md + specs/wiki/seed_audit_brief.md): deterministic measures and the ranking law (proportions first, defects second, fidelity third); a model only
judges, the user records. The shelf auditors' RECORDED Boots1 audit is the oracle."""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import seed_audit as SA  # noqa: E402

SHELF = Path(os.environ.get("LAMPWAY_SHELF_DIR") or "/nonexistent-shelf")
SCR = Path(os.environ.get("LAMPWAY_SHELF_SCRATCH") or SHELF / "scratch")
B = SCR / "tripo_mesh/Boots1_g1"
REAL = (B / "variant1.npz").exists()
real = pytest.mark.skipif(not REAL, reason="the shelf's Boots1 seeds are not on this machine")
RMS = {"variant1": 0.1402, "variant2": 0.1407, "variant3": 0.1444, "variant4": 0.1457}      # pieces_g1/Boots1.json


@real
def test_the_fold_counts_reproduce_the_recorded_audit_and_do_not_depend_on_rotation():
    got = [SA.folds(*SA.load_mesh(B / f"variant{k}.npz"))["folds_gt120"] for k in (1, 2, 3, 4)]
    assert got == [493, 96, 282, 185], got
    V, T = SA.load_mesh(B / "variant1.npz")
    th = np.radians(37)
    R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    assert SA.folds(V @ R.T, T)["folds_gt120"] == 493, "a rotation must not change a dihedral count"
    assert SA.folds(*SA.load_mesh(B / "variant1.npz"))["folds_gt90"] == 2536
    t = SA.topology(*SA.load_mesh(B / "variant1.npz"))
    assert t["edges_bnd"] == 7111 and t["edges_nm"] == 80 and t["components"] == 559, t


def _measure(tmp_path, scores):
    return SA.run(tmp_path, "measure", "Boots1", seeds=[str(B / f"variant{k}.npz") for k in (1, 2, 3, 4)], scores=scores)


@real
def test_proportions_first_then_defects_equal_proportions_pick_the_cleanest_and_a_real_gap_wins(tmp_path):
    tied = _measure(tmp_path, RMS)
    assert tied["ranking"][0] == "variant2" and "tie" in tied["why"] and tied["confidence"] == "low", tied["ranking"]
    gap = dict(RMS, variant4=0.11)                                                       # variant 4 genuinely 22 % closer to the body
    ranked = _measure(tmp_path / "gap", gap) if (tmp_path / "gap").mkdir() is None else None
    assert ranked["ranking"][0] == "variant4" and "differ" in ranked["why"], "proportions trump defects"
    assert (tmp_path / "Boots1/seed_audit/meas.json").exists()


@real
def test_the_closed_bowl_in_the_real_boot_is_found_and_the_body_self_test_has_none():
    V, T = SA.load_mesh(B / "variant1.npz")
    th = np.radians(-90)
    R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    found = SA.caps(V @ R.T, T)
    assert len(found) == 1 and found[0]["floor_z"] == pytest.approx(0.396, abs=0.03) and 0.05 < found[0]["depth_frac"] < 0.2, found
    sv, st = SA.load_mesh(SCR / "proportion/piece_selftest/boots.npz")
    assert SA.caps(sv, st) == [], "the body's own leg region offset 15 mm has no bowl"


def test_refusals_and_the_record_rules(tmp_path):
    with pytest.raises(SA.AuditError, match="at least two seeds"):
        SA.run(tmp_path, "measure", "P", seeds=["a.npz"])
    with pytest.raises(SA.AuditError, match="run mesh_to_npz first"):
        SA.run(tmp_path, "measure", "P", seeds=["a.fbx", "b.fbx"])
    with pytest.raises(SA.AuditError, match="run stage measure first"):
        SA.run(tmp_path, "judge", "P")
    out = tmp_path / "P" / "seed_audit"
    out.mkdir(parents=True)
    many = {f"s{i}": {"faces": 10} for i in range(7)}
    (out / "meas.json").write_text(json.dumps({"per_seed": many, "ranking": list(many), "recommend": {}, "scorer_notes": [], "confidence": "low"}))
    with pytest.raises(SA.AuditError, match="at most six"):
        SA.run(tmp_path, "judge", "P")
    (out / "meas.json").write_text(json.dumps({"per_seed": {"s1": {"faces": 10}}, "ranking": ["s1"], "recommend": {"seed": "s1"}, "scorer_notes": [], "confidence": "low"}))
    props = {"s1": {"verdict": "usable", "defects": []}}
    m = SA.run(tmp_path, "record", "P", proposals=props, by="model")
    assert m["verdict_written"] is False and not (tmp_path / "seeds" / "decisions.jsonl").exists() and (out / "audit.json").exists()
    c = SA.run(tmp_path, "record", "P", proposals=props, by="captain")
    rows = [json.loads(line) for line in (tmp_path / "seeds" / "decisions.jsonl").read_text().splitlines()]
    assert c["verdict_written"] is True and rows[0]["question"] == "seed_pick" and rows[0]["decider"] == "captain"


def test_the_lineup_renders_two_420_px_views_per_seed_and_refuses_cycles_inside_the_app(tmp_path):
    from features_support import run as brun
    import shutil
    seeds = []
    for k, name in enumerate(("a", "b")):
        V = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1 + 0.5 * k]], float)
        T = np.array([[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]])
        np.savez(tmp_path / f"{name}.npz", V=V, T=T)
        seeds.append(f"{name}.npz")
    r = brun(tmp_path, f"""
from PIL import Image
before = sorted(o.name for o in bpy.data.objects)
res = call("seed_audit", stage="lineup", piece="P", seeds={seeds!r})
bad = call("seed_audit", stage="lineup", piece="P", seeds={seeds!r}, engine="CYCLES")
sizes = [Image.open(f).size for f in res["files"]]
print("RESULT", json.dumps({{"res": res, "bad": bad, "sizes": sizes, "left_alone": sorted(o.name for o in bpy.data.objects) == before}}))
""")
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["res"]["ok"] is True and len(o["res"]["files"]) == 4 and o["left_alone"] is True
    assert all(max(s) <= 420 and max(s) >= 100 for s in o["sizes"]), o["sizes"]
    assert o["bad"]["ok"] is False and "never Cycles" in o["bad"]["error"]
