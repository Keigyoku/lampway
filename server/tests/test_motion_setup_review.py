# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Setup reports must prove readiness through typed font and image rows."""
import pytest

from lampway_server import motion as M
from .fake_motion import FakeCapture


class ReportCapture(FakeCapture):
    def __init__(self, report):
        super().__init__(duration_s=0.1)
        self.report = report

    def setup(self):
        return self.report


@pytest.mark.parametrize("report", [
    None, {}, [], False, "ready",
    {"fonts": []}, {"images": []},
    {"fonts": None, "images": []}, {"fonts": [], "images": None},
    {"fonts": {}, "images": []}, {"fonts": [], "images": {}},
    {"fonts": "loaded", "images": []}, {"fonts": [], "images": "loaded"},
    {"fonts": [None], "images": []}, {"fonts": [], "images": [None]},
    {"fonts": [{"ok": True}], "images": []}, {"fonts": [], "images": [{"ok": True}]},
    {"fonts": [{"font": 42, "ok": True}], "images": []}, {"fonts": [], "images": [{"src": 42, "ok": True}]},
    {"fonts": [{"font": "", "ok": True}], "images": []}, {"fonts": [], "images": [{"src": "", "ok": True}]},
    {"fonts": [{"font": "16px Test"}], "images": []}, {"fonts": [], "images": [{"src": "asset.svg"}]},
    {"fonts": [{"font": "16px Test", "ok": "false"}], "images": []}, {"fonts": [], "images": [{"src": "asset.svg", "ok": "false"}]},
    {"fonts": [{"font": "16px Test", "ok": 1}], "images": []}, {"fonts": [], "images": [{"src": "asset.svg", "ok": 1}]},
])
def test_setup_requires_both_arrays_and_typed_asset_rows(tmp_path, report):
    cap = ReportCapture(report)
    with pytest.raises(M.Refused, match="__setup"):
        M._ready(cap, tmp_path / "index.html", 32, 32)
    assert cap.frames_asked == []


@pytest.mark.parametrize("report", [
    {"fonts": [], "images": []},
    {"fonts": [{"font": "16px Test", "ok": True}], "images": [{"src": "asset.svg", "ok": True}]},
])
def test_valid_setup_reports_are_accepted(tmp_path, report):
    M._ready(ReportCapture(report), tmp_path / "index.html", 32, 32)


@pytest.mark.parametrize("report,asset", [
    ({"fonts": [{"font": "16px Test", "ok": False}], "images": []}, "16px Test"),
    ({"fonts": [], "images": [{"src": "asset.svg", "ok": False}]}, "asset.svg"),
])
def test_boolean_false_remains_a_named_readiness_refusal(tmp_path, report, asset):
    with pytest.raises(M.Refused, match=asset):
        M._ready(ReportCapture(report), tmp_path / "index.html", 32, 32)


def test_malformed_setup_refuses_render_before_capture_and_receipt(tmp_path):
    made = []
    def fresh():
        cap = ReportCapture({})
        made.append(cap)
        return cap
    with pytest.raises(M.Refused, match="__setup"):
        M.render(tmp_path, {"html": "<!doctype html>", "name": "bad-setup", "width": 32, "height": 32, "fps": 10}, fresh)
    assert len(made) == 1 and made[0].closed and not made[0].frames_asked
    assert not list(tmp_path.rglob("receipt.json"))


def test_fresh_probe_must_validate_its_own_setup_report(tmp_path):
    made = []
    def fresh():
        cap = ReportCapture({"fonts": [], "images": []} if not made else {})
        made.append(cap)
        return cap
    with pytest.raises(M.Refused, match="__setup"):
        M.render(tmp_path, {"html": "<!doctype html>", "name": "bad-probe-setup", "width": 32, "height": 32, "fps": 10}, fresh)
    assert len(made) == 2 and all(cap.closed for cap in made)
    assert made[0].frames_asked == [0] and made[1].frames_asked == []
    assert not list(tmp_path.rglob("receipt.json"))


@pytest.mark.parametrize("report", [None, {}, {"fonts": []}, {"fonts": [], "images": [{"src": "asset.svg", "ok": "false"}]}])
def test_real_chromium_cannot_bypass_setup_report_validation(tmp_path, monkeypatch, report):
    import json
    import os
    from lampway_server.motion import frames as F
    binary = os.environ.get("LAMPWAY_CHROMIUM")
    if not binary or not os.path.isfile(binary):
        pytest.skip("set LAMPWAY_CHROMIUM; real-browser setup validation UNVERIFIED")
    monkeypatch.setattr(F, "CHROME_FLAGS", [*F.CHROME_FLAGS, "--no-sandbox"])
    scene = tmp_path / "scene"
    scene.mkdir()
    entry = scene / "index.html"
    entry.write_text("<script>window.__frame=()=>{};window.__audit=()=>({text:[],marks:[]});"
                     "window.__setup=()=> (" + json.dumps(report) + ");</script>")
    cap = F.Chromium(binary, tmp_path / "browser")
    try:
        with pytest.raises(M.Refused, match="__setup"):
            M._ready(cap, entry, 32, 32)
    finally:
        cap.close()
