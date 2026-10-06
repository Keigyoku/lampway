# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""reference_pack (specs/wiki/reference_pack.md): the four-stage reference method as a GATED sequence over view_verify, plate_pick's silhouette measure and the
ledger: one technical sheet (anatomical left and right named), an audit against the approved source, then parts and only the missing views; a failed audit
stops the run. Dry runs call no backend; every live stage leaves a run record with seed not_exposed. Pure python with a recording fake backend."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import reference_pack as RP  # noqa: E402


def figure(path, w=900, h=1200, arms=True, shift=0, half=120):
    a = np.full((h, w, 4), 255, np.uint8); a[..., 3] = 0
    cx = w // 2 + shift
    a[200:1000, cx - half:cx + half] = (150, 120, 70, 255)
    a[1000:1150, cx - 110:cx - 20] = (150, 120, 70, 255); a[1000:1150, cx + 20:cx + 110] = (150, 120, 70, 255)
    a[80:200, cx - 60:cx + 60] = (150, 120, 70, 255)
    if arms:
        a[260:330, cx - 330:cx - 120] = (150, 120, 70, 255); a[260:330, cx + 120:cx + 330] = (150, 120, 70, 255)
    Image.fromarray(a, "RGBA").save(path)
    return str(path)


class Backend:
    def __init__(self, src):
        self.calls, self.src = [], src

    def __call__(self, prompt, reference_png, count=1, params_extra=None):
        self.calls.append({"prompt": prompt, "count": count, "params": params_extra})
        return [Path(self.src).read_bytes()] * count


@pytest.fixture
def setup(tmp_path):
    ref = figure(tmp_path / "approved.png")
    return tmp_path, ref


def test_sheet_prompt_names_left_and_right_and_a_dry_run_calls_no_backend(setup):
    root, ref = setup
    be, rows = Backend(ref), []
    with pytest.raises(RP.ReferenceRefused, match="anatomical left"):
        RP.run_stage("sheet", str(root), "Knight", ref, generate=be, record=rows.append)
    dry = RP.run_stage("sheet", str(root), "Knight", ref, left_description="a shield on the left forearm", right_description="a sword in the right hand",
                       generate=be, record=rows.append)
    assert dry["dry_run"] is True and be.calls == [] and rows == [], dry
    text = Path(dry["prompt_files"][0]).read_text()
    assert "anatomical LEFT: a shield on the left forearm" in text and "anatomical RIGHT: a sword in the right hand" in text and "white" in text, text


def test_extract_and_views_are_refused_before_a_passing_sheet(setup):
    root, ref = setup
    be = Backend(ref)
    with pytest.raises(RP.ReferenceRefused, match="needs a sheet that passed its audit"):
        RP.run_stage("extract", str(root), "Knight", ref, components=["shield"], generate=be)
    with pytest.raises(RP.ReferenceRefused, match="needs a sheet that passed its audit"):
        RP.run_stage("views", str(root), "Knight", ref, views=["Back"], generate=be)


def test_a_live_sheet_records_seed_not_exposed_and_a_passing_audit_unlocks_the_parts(setup):
    root, ref = setup
    be, rows = Backend(ref), []
    live = RP.run_stage("sheet", str(root), "Knight", ref, left_description="shield", right_description="sword", live=True, count=2, generate=be, record=rows.append)
    assert len(live["files"]) == 2 and live["run_record"]["seed"] == "not_exposed" and live["run_record"]["selected"] is None, live
    assert rows and rows[0]["seed"] == "not_exposed" and rows[0]["stage"] == "image" and rows[0]["by"] == "agent" and rows[0].get("decision") is None
    audit = RP.run_stage("audit", str(root), "Knight", ref, image=live["files"][0])
    assert audit["passed"] is True and audit["audit"]["silhouette_iou"] > 0.95, audit
    ext = RP.run_stage("extract", str(root), "Knight", ref, components=["shield"], generate=be)
    assert ext["dry_run"] is True and "shield" in Path(ext["prompt_files"][0]).read_text()


def test_a_failed_audit_stops_the_run_and_names_the_fix(setup):
    root, ref = setup
    bad = figure(root / "drift.png", arms=False, shift=100, half=200)            # the arms lost and the body widened: another design
    audit = RP.run_stage("audit", str(root), "Knight", ref, image=bad)
    assert audit["passed"] is False and "identity failed at sheet" in audit["stop"] and "not the batch size" in audit["stop"], audit
    with pytest.raises(RP.ReferenceRefused, match="needs a sheet that passed its audit"):
        RP.run_stage("extract", str(root), "Knight", ref, components=["shield"])


def test_views_already_in_the_sheet_are_refused(setup):
    root, ref = setup
    be = Backend(ref)
    live = RP.run_stage("sheet", str(root), "Knight", ref, left_description="shield", right_description="sword", live=True, count=1, generate=be,
                        sheet_views=["Front", "Left"])
    RP.run_stage("audit", str(root), "Knight", ref, image=live["files"][0])
    with pytest.raises(RP.ReferenceRefused, match="already in the approved sheet"):
        RP.run_stage("views", str(root), "Knight", ref, views=["Front", "Back"])
    ok = RP.run_stage("views", str(root), "Knight", ref, views=["Back"])
    assert ok["dry_run"] is True and json.loads(Path(root / "Knight" / "reference" / "state.json").read_text())["sheet"]["passed"] is True
