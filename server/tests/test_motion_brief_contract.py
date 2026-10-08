# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rendered motion briefs must teach JSON examples accepted by the actual scene validators."""
import copy
import json

import pytest

from lampway_server import motion as M
from lampway_server.motion import check as C
from lampway_server.prompts import library as PL
from lampway_server.prompts import render as PR

from .fake_motion import FakeCapture


TEMPLATES = ("mg-site-clip", "mg-tutorial", "mg-release", "mg-facelift-ui-demo", "mg-report-card", "mg-titan-animatic", "mg-titan-ui-motion")


def rendered(tid):
    lib = PL.Library(PL.BUILTIN, None, None)
    template = lib.get(tid, "1.0.0")
    given = {name: "public fixture" for name, spec in template["variables"].items() if "default" not in spec}
    return PR.render(lib, tid, given)["prompt"]


def example(prompt, label):
    assert label in prompt, f"rendered brief must supply {label} JSON for the scene author"
    value, _ = json.JSONDecoder().raw_decode(prompt.split(label, 1)[1].lstrip())
    return value


def ready(setup, tmp_path):
    class BriefCapture(FakeCapture):
        def setup(self):
            return setup  # preserve the exact parsed value, including malformed or empty objects

    capture = BriefCapture()
    M._ready(capture, tmp_path / "index.html", 1920, 1080)


@pytest.mark.parametrize("tid", TEMPLATES)
def test_rendered_motion_brief_examples_pass_runtime_contract(tid, tmp_path):
    prompt = rendered(tid)
    setup = example(prompt, "Setup return example:")
    audit = example(prompt, "Audit return example:")
    ready(setup, tmp_path)
    assert setup["fonts"] and setup["images"], "resource examples must actually exercise both row schemas"
    assert audit["text"] and audit["marks"], "audit examples must actually exercise both row schemas"
    assert C.validate_audit(audit) == audit
    ready(example(prompt, "Empty-resource setup:"), tmp_path)
    empty = example(prompt, "Empty audit:")
    assert C.validate_audit(empty) == {"text": [], "marks": []}


@pytest.mark.parametrize("tid", TEMPLATES)
@pytest.mark.parametrize("plant", ["missing_images", "empty_font", "string_ok", "missing_opacity", "reversed_box", "nonfinite_box", "zero_font", "opacity_outside_range"])
def test_rendered_examples_keep_runtime_refusal_plants(tid, plant, tmp_path):
    prompt = rendered(tid)
    if plant in ("missing_images", "empty_font", "string_ok"):
        setup = copy.deepcopy(example(prompt, "Setup return example:"))
        if plant == "missing_images":
            del setup["images"]
        elif plant == "empty_font":
            setup["fonts"][0]["font"] = ""
        else:
            setup["images"][0]["ok"] = "true"
        with pytest.raises(M.Refused, match="setup"):
            ready(setup, tmp_path)
    else:
        audit = copy.deepcopy(example(prompt, "Audit return example:"))
        text = audit["text"][0]
        if plant == "missing_opacity":
            del text["opacity"]
        elif plant == "reversed_box":
            text["box"] = [500, 100, 100, 160]
        elif plant == "nonfinite_box":
            text["box"][0] = float("inf")
        elif plant == "zero_font":
            text["font_px"] = 0
        else:
            text["opacity"] = 1.1
        with pytest.raises(ValueError, match="audit"):
            C.validate_audit(audit)
