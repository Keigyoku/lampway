# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression plants for motion template and Vault review findings."""
import json

import pytest

from lampway_server.prompts import library as PL
from lampway_server.prompts import render as PR

from .fake_motion import FakeCapture
from .test_motion_graphics import SMALL, a_vault, put_scene, tool


def test_webm_only_is_the_primary_render_and_qa_parent(tmp_path):
    project, vault = tmp_path / "project", a_vault(tmp_path)
    out, error = tool(project, {"scene": put_scene(project, "webm-only", "<!doctype html>"),
                                **SMALL, "formats": ["webm"]}, vault=vault, capture=FakeCapture)
    assert not error, out
    assets = {a["format"]: vault.lib.get(a["id"]) for a in out["vault"]["assets"]}
    primary = assets["webm"]
    assert primary["subtype"] == "render"
    assert primary["files"][0]["role"] == "main"
    relations = {(r["type"], r["src"], r["dst"]) for r in vault.lib._reader().execute("SELECT type,src,dst FROM relation")}
    for fmt in ("receipt", "contact"):
        assert ("derived_from", assets[fmt]["id"], primary["id"]) in relations


def test_non_motion_template_refused_before_render_writes(tmp_path):
    project = tmp_path / "project"
    scene = put_scene(project, "wrong-purpose", "<!doctype html>")
    out, error = tool(project, {"scene": scene, **SMALL, "template": "anim-motion-transfer@1.0.0"}, capture=FakeCapture)
    assert error and "motion-graphics" in out["error"], out
    assert not (project / "motion" / "out").exists()


def test_effective_defaults_and_resolved_template_persist_in_receipt_and_vault(tmp_path):
    project, vault = tmp_path / "project", a_vault(tmp_path)
    out, error = tool(project, {"scene": put_scene(project, "defaults", "<!doctype html>"), **SMALL,
                                "template": "mg-site-clip", "variables": {"read_s": 2.5}}, vault=vault, capture=FakeCapture)
    assert not error, out
    expected = PR.render(PL.Library(PL.BUILTIN, None, None), "mg-site-clip", {"read_s": 2.5})
    receipt = json.loads((project / out["out_dir"] / "receipt.json").read_text())
    assert receipt["inputs"]["variables"] == expected["variables"]
    assert receipt["inputs"]["template"] == expected["template"]
    video = vault.lib.get(next(a["id"] for a in out["vault"]["assets"] if a["format"] == "mp4"))
    generation = video["generation"][0]
    assert json.loads(generation["params_json"])["vars"] == expected["variables"]
    assert generation["prompt_text"] == expected["prompt"]
    assert expected["template"] == "mg-site-clip@1.0.1" and generation["template_version"] == "1.0.1"        # the newest: a new wording is a new version
    prompt = vault.lib.get(generation["prompt_asset"])
    assert prompt["stats"]["vars_json"] == json.dumps(expected["variables"], sort_keys=True)


@pytest.mark.parametrize("tid,given", [
    ("mg-titan-ui-motion", {"element": "HUD", "states": "idle, active", "tokens_source": "ui/tokens.json"}),
    ("mg-titan-animatic", {"sequence": "intro", "shot_list": "boards/shots.json"}),
])
def test_titan_templates_refuse_unused_palette(tid, given):
    lib = PL.Library(PL.BUILTIN, None, None)
    assert "palette" not in lib.get(tid)["variables"]
    with pytest.raises(PR.RenderError, match="palette: not a variable"):
        PR.render(lib, tid, {**given, "palette": "invented palette"})
