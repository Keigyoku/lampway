# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""parts_critique (shelf/parts_critique.md section 10): the deterministic pre-pass, the validation refusals, the class guard and a dry run that equals apply_part_fixes."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import parts_critique as PC  # noqa: E402

SCRIPT = Path(PC.__file__).resolve().parents[1] / "scripts/partseg/apply_part_fixes.py"
PARTS = ["plate_L", "plate_R", "cloth_skirt", "belt"]


@pytest.fixture
def parts(tmp_path):
    """A flat strip of 40 quads (80 triangles), 10 per part left to right: plate_L (x 0-1), plate_R (x 1-2), cloth_skirt (x 2-3), belt (x 3-4); 4 islands of 20 triangles."""
    V, T, POLY = [], [], []
    for q in range(40):
        x0 = q / 10.0
        base = len(V)
        V += [[x0, 0, 0], [x0 + .1, 0, 0], [x0 + .1, 0, 1], [x0, 0, 1]]
        T += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
        POLY += [q, q]
    tri = np.repeat(np.arange(4), 20).astype(np.int32)             # 20 triangles per part
    isl = np.repeat(np.arange(8), 10).astype(np.int32)             # 8 islands of 10 triangles
    td = tmp_path / "transfer"
    td.mkdir()
    np.save(td / "owner_tri.npy", tri)
    np.save(td / "island_tri.npy", isl)
    poly = np.repeat(np.arange(4), 10).astype(np.int32)
    np.save(td / "owner_poly.npy", poly)
    rows = [{"island": i, "part": PARTS[i // 2], "confidence": 0.9, "mean_dist_mm": 5.0, "area_m2": 0.05 + i * 0.001, "runner_up": PARTS[(i // 2 + 1) % 4], "flag": False} for i in range(8)]
    rows[3].update(confidence=0.4)                                  # weak
    rows[5].update(mean_dist_mm=45.0)                               # far
    (td / "islands.json").write_text(json.dumps(rows))
    npz = tmp_path / "piece_uv.npz"
    np.savez(npz, V=np.array(V, float), T=np.array(T), POLY=np.array(POLY))
    rec = tmp_path / "recipe.json"
    rec.write_text(json.dumps({"parts": {"plate_L": {"class": "rigid-metal"}, "plate_R": {"class": "rigid-metal"}, "cloth_skirt": {"class": "cloth-sim"}, "belt": {"class": "rigid-metal"}}}))
    return {"td": str(td), "npz": str(npz), "rec": str(rec), "root": str(tmp_path)}


def test_the_pre_pass_flags_exactly_the_weak_and_far_islands(parts):
    fl = PC.flags(parts["td"], parts["rec"], parts["npz"])
    assert sorted(r["island"] for r in fl["islands"]) == [3, 5]
    assert "weak vote" in fl["islands"][0]["why"][0] and "far transfer" in fl["islands"][1]["why"][0]


def test_raising_the_weak_threshold_to_one_flags_every_island(parts):                 # the falsifier
    assert len(PC.flags(parts["td"], parts["rec"], weak=1.0)["islands"]) == 8


def test_a_part_with_too_few_polygons_is_flagged_and_an_absent_one_says_so(parts):
    fl = PC.flags(parts["td"], parts["rec"], min_faces=11)
    assert {r["part"] for r in fl["parts"]} == set(PARTS)
    poly = np.load(Path(parts["td"]) / "owner_poly.npy")
    poly[poly == 3] = 2
    np.save(Path(parts["td"]) / "owner_poly.npy", poly)
    belt = [r for r in PC.flags(parts["td"], parts["rec"])["parts"] if r["part"] == "belt"][0]
    assert "absent" in belt["why"][0]


def test_asymmetry_and_the_sagittal_plane_are_flagged(parts):
    tri = np.load(Path(parts["td"]) / "owner_tri.npy")
    tri[60:] = 1                                                    # plate_R grows to 20+20 triangles: area ratio L/R = 0.5
    np.save(Path(parts["td"]) / "owner_tri.npy", tri)
    why = " ".join(w for r in PC.flags(parts["td"], parts["rec"], parts["npz"])["parts"] for w in r["why"])
    assert "area ratio to plate_R" in why
    # the strip's bounding-box centre is x=2: plate_L (x 0-1) does not cross it, but a left part that reaches x=3 does
    tri = np.load(Path(parts["td"]) / "owner_tri.npy")
    tri[40:50] = 0
    np.save(Path(parts["td"]) / "owner_tri.npy", tri)
    assert any("crosses the sagittal plane" in w for r in PC.flags(parts["td"], parts["rec"], parts["npz"])["parts"] for w in r["why"])


def test_unknown_part_and_empty_selector_are_refused_with_the_reasons(parts):
    with pytest.raises(PC.CritiqueError, match=r"unknown target_part 'sleeve'; the parts are: \['plate_L'"):
        PC.validate([{"target_part": "sleeve", "islands": [1]}], parts["rec"])
    with pytest.raises(PC.CritiqueError, match="a fix needs islands or bbox_fbx"):
        PC.validate([{"target_part": "belt"}], parts["rec"])


def test_the_class_guard_refuses_metal_to_cloth_and_back_but_allows_metal_to_metal(parts):
    with pytest.raises(PC.CritiqueError, match="material class comes from the user or the recipe, never from a render: ask"):
        PC.validate([{"target_part": "cloth_skirt", "islands": [0]}], parts["rec"], parts["td"], parts["npz"])      # island 0 is plate_L triangles
    with pytest.raises(PC.CritiqueError, match="never from a render"):
        PC.validate([{"target_part": "plate_L", "islands": [4]}], parts["rec"], parts["td"], parts["npz"])           # island 4 is cloth
    ok = PC.validate([{"target_part": "plate_R", "islands": [0], "reason": "mirror"}], parts["rec"], parts["td"], parts["npz"])
    assert ok[0]["target_part"] == "plate_R"


def test_check_reproduces_apply_part_fixes_own_counts_without_writing(parts, tmp_path):
    fixes = {"fixes": [{"target_part": "plate_R", "islands": [0, 1]}, {"target_part": "belt", "bbox_fbx": [[3.05, -1, -1], [4, 1, 2]], "only_from_parts": ["belt"], "reason": "x"}]}
    fx = tmp_path / "fixes.json"
    fx.write_text(json.dumps(fixes))
    out = tmp_path / "owner_out.npy"
    p = subprocess.run([sys.executable, str(SCRIPT), parts["td"], parts["npz"], parts["rec"], str(fx), str(out)], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    theirs = json.loads(out.with_suffix(".json").read_text())
    res = PC.run(parts["root"], "check", "p", recipe=parts["rec"], transfer_dir=parts["td"], piece_uv=parts["npz"], fixes=str(fx))
    assert res["check"] == theirs
    assert res["check"][0]["from"] == {"plate_L": 20}
    assert not (Path(parts["td"]) / "owner_out.npy").exists()


def test_write_fixes_writes_the_exact_consumer_shape_and_judge_limits_its_packet(parts):
    res = PC.run(parts["root"], "write_fixes", "chest", recipe=parts["rec"], transfer_dir=parts["td"], piece_uv=parts["npz"],
                 proposals=[{"target_part": "plate_R", "islands": [0], "reason": "mirror of the right", "evidence": "owner_front.png"}], by="agent")
    written = json.loads(Path(res["path"]).read_text())
    assert written["fixes"][0]["by"] == "agent" and written["fixes"][0]["reason"] == "mirror of the right"
    assert res["path"].endswith("chest/parts/fixes.json")
    j = PC.run(parts["root"], "judge", "chest", recipe=parts["rec"], transfer_dir=parts["td"], piece_uv=parts["npz"], limit=1)
    assert len(j["islands"]) == 1 and j["limit"] == 1 and "propose fixes" in j["ask"]
    assert PC.run(parts["root"], "judge", "chest", recipe=parts["rec"], transfer_dir=parts["td"], limit=99)["limit"] == 20


def test_a_round_trip_changes_only_the_targeted_parts(parts, tmp_path):
    fx = tmp_path / "fixes.json"
    PC.run(parts["root"], "write_fixes", "p", recipe=parts["rec"], transfer_dir=parts["td"], piece_uv=parts["npz"], proposals=[{"target_part": "plate_R", "islands": [0, 1]}])
    fx = Path(parts["root"]) / "p/parts/fixes.json"
    log, tri = PC.dry_run(parts["td"], parts["npz"], parts["rec"], json.loads(fx.read_text())["fixes"])
    before = np.load(Path(parts["td"]) / "owner_tri.npy")
    assert {int(a) for a in np.unique(before[before != tri])} == {0}                  # only plate_L's triangles moved
    assert (tri[before == 2] == 2).all() and (tri[before == 3] == 3).all()
