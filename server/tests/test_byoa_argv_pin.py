# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The herdr command each existing harness pane starts with, pinned before the harness adapters (agent-modes spec B1) take it over:
an unbound Claude Code, Codex CLI or OpenCode pane must start exactly as it did, new or resumed, with and without effort and the
user's bypass. herdr is faked (as strict as herdr 0.9.3 about agent names); nothing is started."""
import uuid

import pytest

from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L

from .test_byoa_egress import FakeHerdr


@pytest.fixture
def herdr(monkeypatch):
    fake = FakeHerdr()
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    return fake


def _start(fake):
    return next(c["args"] for c in fake.calls if c["args"][:2] == ["agent", "start"])


CASES = [
    # agent, effort, bypass, resume_id, the arguments after "--"
    ("codex", None, False, None, ["--no-alt-screen"]),
    ("codex", "high", True, None, ["--no-alt-screen", "--dangerously-bypass-approvals-and-sandbox", "-c", 'model_reasoning_effort="high"']),
    ("codex", None, False, "rollout-123", ["resume", "rollout-123", "--no-alt-screen"]),
    ("claude", "max", True, "c-abc", ["--resume", "c-abc", "--dangerously-skip-permissions", "--effort", "max"]),
    ("claude", None, False, "c-abc", ["--resume", "c-abc"]),
    ("opencode", None, False, None, []),
    ("opencode", None, True, "ses_1", ["--session", "ses_1", "--auto"]),
]


@pytest.mark.parametrize("agent,effort,bypass,resume_id,args", CASES)
def test_an_unbound_pane_starts_with_the_same_herdr_command_as_before(herdr, tmp_path, agent, effort, bypass, resume_id, args):
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session(agent, "Chest fit audit", str(tmp_path), effort=effort, bypass=bypass, resume_id=resume_id, by="user")
    # the agent's name is one herdr 0.9.3 accepts (the display name was refused by the real server: invalid_agent_name)
    assert _start(herdr) == ["agent", "start", f"lw-{rec['id']}", "--kind", agent, "--pane", "p1", "--", *args]


def test_a_new_claude_pane_gets_a_fresh_session_id_lampway_records_as_its_native_id(herdr, tmp_path):
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session("claude", "Chest fit audit", str(tmp_path), by="user")
    args = _start(herdr)
    assert args[:8] == ["agent", "start", f"lw-{rec['id']}", "--kind", "claude", "--pane", "p1", "--"] and args[8] == "--session-id"
    assert str(uuid.UUID(args[9])) == args[9] == rec["native_id"] and len(args) == 10
    assert rec["match"] == ["claude"]
