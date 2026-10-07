# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_migration.md steps 0-1 and test 3: every consumer logs what the resolver would pick beside what ran (`<state>/choices/
shadow.jsonl`), and the shadow report lists every purpose where they differ. Nothing in the log changes what runs."""

import base64
import json
import subprocess
import sys

import httpx
import pytest

from lampway_server import choices as CH
from lampway_server import egress as E
from lampway_server.choices import shadow as SH
from lampway_server.choices import store as CS
from lampway_server.choices.snapshot import World
from lampway_server.connections import registry as CREG

KEY = "sk-" "or-v1-" + "5e4f" * 16
PNG = b"\x89PNG\r\n\x1a\nx"


@pytest.fixture
def live(tmp_path, monkeypatch):
    CH.set_active(CS.FileStore(tmp_path / "state"), tmp_path / "state")
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(connections={c: "connected" for c in CREG.SPECS}, routes={r: True for r in E.ROUTES}))
    yield tmp_path / "state"
    CH.set_active(None, None)


def test_shadow_finds_the_known_disagreements(live, monkeypatch):
    from lampway_server import imagegen as IG
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)

    def handler(request):
        if request.method == "GET":
            return httpx.Response(404, json={})
        return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode()}], "usage": {"cost": 0.01}})
    monkeypatch.setattr(IG, "openrouter_transport", httpx.MockTransport(handler))
    IG.openrouter_images("a helmet", [], 1, purpose="plates", model="google/gemini-3.1-flash-image")       # a caller's model, not the choice
    IG.openrouter_images("a helmet", [], 1, purpose="plates")
    rows = [json.loads(l) for l in (live / "choices" / "shadow.jsonl").read_text().splitlines()]
    assert [(r["purpose"], r["ran"], r["same"]) for r in rows] == [
        ("image.plates", "openrouter:google/gemini-3.1-flash-image", False), ("image.plates", "openrouter:openai/gpt-image-2.5-flare", True)]
    rep = SH.report(live)
    assert rep["differences"] == [{"purpose": "image.plates", "resolved": "openrouter:openai/gpt-image-2.5-flare",
                                   "ran": "openrouter:google/gemini-3.1-flash-image", "count": 1}]


def test_the_report_is_a_command(live):
    SH.record("agent.main", "mock", CH.Job(content_class="public"))
    out = subprocess.run([sys.executable, "-m", "lampway_server.choices.shadow", "--report", "--state", str(live)], capture_output=True, text=True,
                         timeout=60, cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]))
    assert out.returncode == 0 and "rows: 1" in out.stdout and "differences: []" in out.stdout      # TOON 4 empty array (audit F9)


def test_a_failing_shadow_never_breaks_the_call(live, monkeypatch):
    monkeypatch.setattr(CH, "resolve", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    SH.record("image.plates", "openrouter:x", CH.Job())
    assert not (live / "choices" / "shadow.jsonl").exists() or "boom" not in (live / "choices" / "shadow.jsonl").read_text()
