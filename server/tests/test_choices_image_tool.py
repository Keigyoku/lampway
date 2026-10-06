# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_migration.md 5.4: studio_image_generate's backend is a job override under the purpose's policy (CH3) and, when the agent names
none, the purpose's choice decides the backend."""

import pytest

from lampway_server import choices as CH
from lampway_server import egress as E
from lampway_server.agent import server_tools as ST
from lampway_server.choices import store as CS
from lampway_server.choices.snapshot import World
from lampway_server.connections import registry as CREG


@pytest.fixture
def ran(tmp_path, monkeypatch):
    from lampway_server import imagegen as IG
    CH.set_active(CS.FileStore(tmp_path / "state"), tmp_path / "state")
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(connections={c: "connected" for c in CREG.SPECS}, routes={r: True for r in E.ROUTES}))
    calls = []
    monkeypatch.setattr(IG, "generate", lambda backend, *a, **k: calls.append((backend, a, k)) or {"backend": backend, "files": [], "dry_run": True, "output": ""})
    yield calls
    CH.set_active(None, None)


def args(**kw):
    return {"out_dir": "runs/x", "prompt_file": "p.txt", **kw}


def test_the_purposes_choice_decides_the_backend(ran):
    ST._run_imagegen(args())
    assert ran[-1][0] == "tripo"                                         # the shipped Plates chain: Tripo Studio first
    CH.active_store().set("image.plates", "global", None, {"preferred": "openrouter:openai/gpt-image-2.5-flare"}, by="user")
    ST._run_imagegen(args())
    assert ran[-1][0] == "openrouter"


def test_an_agents_backend_is_an_override_within_the_chain(ran):
    text, err = ST._run_imagegen(args(backend="openrouter"))             # Flare is in the shipped chain: allowed
    assert not err and ran[-1][0] == "openrouter"
    text, err = ST._run_imagegen(args(backend="codex_cli"))
    assert err and text == "codex_cli:imagegen is not one of your choices for image.plates: propose it with lampway_choices"
    assert len(ran) == 1
