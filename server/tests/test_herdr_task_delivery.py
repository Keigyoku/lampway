# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A harness herdr starts itself gets its first prompt after it is ready, through herdr's own ``agent prompt``.

herdr 0.9.3's ``agent start`` returns only once the agent is detected ready for interactive input (idle); an agent that starts
working at once is still working when the wait ends, and the start fails with herdr's own error (its agent-automation guide, "Agent
identity and launch"; ``src/cli/agent.rs`` ``wait_for_named_agent``). Lampway put a worker's task on the harness's command line, so
every worker whose first turn outlasted that wait failed to launch: measured with native Grok in byoa-worker-validation run
38320574767, ``{"error":{"code":"timeout","message":"timed out waiting for agent startup"},"id":"cli:agent:start"}``. The
played herdr here answers a start whose arguments carry the task with that same error, as the real one does."""
import pytest

from .launch_notice_support import prior_human_disclosure  # noqa: F401

from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L

from .test_byoa_egress import FakeHerdr

TASK = "You are worker-1, one worker of a swarm. Model the boots."
STARTUP_TIMEOUT = '{"error":{"code":"timeout","message":"timed out waiting for agent startup"},"id":"cli:agent:start"}'


class ReadyHerdr(FakeHerdr):
    """herdr's start contract: an agent launched with its first prompt is working, not ready, so its start times out."""

    def __init__(self, prompt_error=None):
        super().__init__()
        self.prompt_error = prompt_error

    def __call__(self, root, args, timeout=30, input=None):
        out = super().__call__(root, args, timeout, input)
        args = [str(a) for a in args]
        if args[:2] == ["agent", "start"] and any(TASK in a for a in args[args.index("--") + 1:]):
            raise L.HerdrError(STARTUP_TIMEOUT)
        if args[:2] == ["agent", "prompt"] and self.prompt_error:
            raise L.HerdrError(self.prompt_error)
        return out


@pytest.fixture
def herdr(monkeypatch):
    fake = ReadyHerdr()
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    return fake


def agent_calls(fake):
    return [c["args"] for c in fake.calls if c["args"][:1] == ["agent"]]


@pytest.mark.parametrize("agent", ["claude", "codex", "opencode"])
def test_the_first_prompt_reaches_a_ready_agent_through_one_agent_prompt(herdr, tmp_path, agent):
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session(agent, "Boots", str(tmp_path), by="swarm", prompt=TASK)
    name = f"lw-{rec['id']}"
    start, *rest = agent_calls(herdr)
    assert start[:3] == ["agent", "start", name] and not any(TASK in a for a in start), "the task is not on the command line"
    assert rest == [["agent", "prompt", name, TASK]], "exactly one native submission, after the start returned ready"
    assert not [c for c in herdr.calls if c["args"][:2] in (["pane", "run"], ["pane", "send-text"]) and TASK in " ".join(c["args"])]
    assert {s["id"]: s for s in c.list_sessions()}[rec["id"]]["state"] == "live"


def test_a_failed_first_prompt_ends_the_start_and_is_never_retried(monkeypatch, tmp_path):
    fake = ReadyHerdr(prompt_error='{"error":{"code":"agent_blocked","message":"agent is blocked"}}')
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    c = H.Cockpit(tmp_path / "herdr")
    with pytest.raises(Exception, match="agent_blocked"):
        c.create_session("claude", "Boots", str(tmp_path), by="swarm", prompt=TASK)
    assert [a for a in agent_calls(fake) if a[:2] == ["agent", "prompt"]] == [["agent", "prompt", agent_calls(fake)[0][2], TASK]]
    assert [s["state"] for s in c.list_sessions()] == ["ended"]
    assert c.list_sessions()[0]["end_reason"] == "pane launch failed"


def test_a_start_without_a_first_prompt_sends_none(herdr, tmp_path):
    c = H.Cockpit(tmp_path / "herdr")
    c.create_session("claude", "Boots", str(tmp_path), by="user")
    assert [a[:2] for a in agent_calls(herdr)] == [["agent", "start"]]
