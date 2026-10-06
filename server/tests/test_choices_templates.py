# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""HC11 with the captain's CH5: the purpose's choice wins over a template's model, unless the template pins it with ``pin: true`` and a
``pin_reason``. A template's model stays as a hint the render reports; the image and video paths run the purpose's model."""

import copy
import json

import pytest

from lampway_server.prompts import render as R
from lampway_server.prompts import schema as S
from lampway_server.prompts.library import Library


def _plate():
    lib = Library.from_env()
    t = next(t for t in lib.list("image") if (t.get("defaults") or {}).get("model"))
    return lib, t


def test_an_unpinned_templates_model_is_a_hint_and_the_purpose_decides():
    lib, t = _plate()
    out = R.render(lib, t["id"], {k: v.get("default") for k, v in (t.get("variables") or {}).items()})
    assert out["model"] is None and "model" not in out["params"]
    assert out["template_model"] == t["defaults"]["model"] and out["pinned"] is False


def test_a_pinned_template_keeps_its_model(tmp_path, monkeypatch):
    lib, t = _plate()
    pinned = copy.deepcopy(t)
    pinned.update(pin=True, pin_reason="the upstream rubric says this sheet needs this model")
    monkeypatch.setattr(lib, "get", lambda tid, version=None: pinned)
    out = R.render(lib, t["id"], {k: v.get("default") for k, v in (t.get("variables") or {}).items()})
    assert out["model"] == t["defaults"]["model"] and out["pinned"] is True


def test_a_pin_needs_its_reason():
    _, t = _plate()
    bad = dict(copy.deepcopy(t), pin=True)
    assert any(e["path"] == "pin_reason" for e in S.validate(bad))
    good = dict(copy.deepcopy(t), pin=True, pin_reason="why")
    assert not [e for e in S.validate(good) if e["path"] in ("pin", "pin_reason")]


def test_an_explicit_model_still_wins():
    lib, t = _plate()
    out = R.render(lib, t["id"], {k: v.get("default") for k, v in (t.get("variables") or {}).items()}, model="google/gemini-3.1-flash-image")
    assert out["model"] == "google/gemini-3.1-flash-image"


def test_the_image_tool_runs_the_purposes_model_not_the_templates(tmp_path, monkeypatch):
    """H4: plate-4k-crisper names Sunburst while the Plates choice is Flare; the choice runs it."""
    import asyncio
    from lampway_server.agent import image_tools as IT
    from lampway_server.prompts.runlog import RunLog
    from lampway_server.prompts.service import PromptService
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-" "or-v1-" + "ef90" * 16)
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    svc = PromptService(Library(builtin_dir=Library().dirs["builtin"], user_dir=tmp_path / "u"), RunLog(tmp_path / "runs.jsonl"))
    t = svc.library.get("plate-4k-crisper")
    assert t["defaults"]["model"] == "openai/gpt-image-2.5-sunburst"
    variables = {k: v.get("default") for k, v in (t.get("variables") or {}).items() if v.get("default") is not None}
    (tmp_path / "ref.png").write_bytes(b"\x89PNG\r\n\x1a\nx")
    out, err = asyncio.run(IT.call(svc, "lampway_image_gen", {"template": "plate-4k-crisper", "variables": variables, "references": ["ref.png"]}))
    assert not err, out
    assert json.loads(out)["model"] == "openai/gpt-image-2.5-flare"
