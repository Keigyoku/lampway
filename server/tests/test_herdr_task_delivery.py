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


STALLED_IDLE = ('{"error":{"code":"agent_prompt_stalled","message":"agent prompt produced no observed working or blocked state '
                'within 5000 ms; current status is idle"},"id":"cli:agent:prompt"}')


class ReadyHerdr(FakeHerdr):
    """herdr's start contract: an agent launched with its first prompt is working, not ready, so its start times out."""

    def __init__(self, prompt_error=None, screen="user@box:~$ ", wait_error=None):
        super().__init__()
        self.prompt_error, self.screen, self.wait_error = prompt_error, screen, wait_error

    def __call__(self, root, args, timeout=30, input=None):
        out = super().__call__(root, args, timeout, input)
        args = [str(a) for a in args]
        if args[:2] == ["agent", "start"] and any(TASK in a for a in args[args.index("--") + 1:]):
            raise L.HerdrError(STARTUP_TIMEOUT)
        if args[:2] == ["agent", "prompt"] and self.prompt_error:
            raise L.HerdrError(self.prompt_error)
        if args[:2] == ["agent", "start"]:
            self.started = True
        if args[:2] == ["pane", "read"] and getattr(self, "started", False):    # the harness's own screen once it runs
            return self.screen
        if args[:2] == ["agent", "wait"] and self.wait_error:
            raise L.HerdrError(self.wait_error)
        return out


@pytest.fixture
def herdr(monkeypatch):
    fake = ReadyHerdr()
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    return fake


def agent_calls(fake):
    return [c["args"] for c in fake.calls if c["args"][:1] == ["agent"]]


@pytest.mark.parametrize("agent", ["claude", "codex", "opencode"])   # herdr's own kinds; Claude is a worker harness
def test_the_first_prompt_reaches_a_ready_agent_through_one_agent_prompt(herdr, tmp_path, agent):
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session(agent, "Boots", str(tmp_path), by="swarm", prompt=TASK)
    name = f"lw-{rec['id']}"
    start, *rest = agent_calls(herdr)
    assert start[:3] == ["agent", "start", name] and not any(TASK in a for a in start), "the task is not on the command line"
    # one native submission after the start returned ready, confirmed by herdr seeing the turn start (its five-second stall check)
    assert rest == [["agent", "prompt", name, TASK, "--wait", "--until", "working", "--until", "blocked"]]
    assert not [c for c in herdr.calls if c["args"][:2] in (["pane", "run"], ["pane", "send-text"]) and TASK in " ".join(c["args"])]
    assert {s["id"]: s for s in c.list_sessions()}[rec["id"]]["state"] == "live"


@pytest.mark.parametrize("error", ['{"error":{"code":"agent_blocked","message":"agent is blocked"}}',
                                   '{"error":{"code":"agent_prompt_stalled","message":"no activity observed"}}'])
def test_a_failed_first_prompt_ends_the_start_and_is_never_retried(monkeypatch, tmp_path, error):
    fake = ReadyHerdr(prompt_error=error)
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    c = H.Cockpit(tmp_path / "herdr")
    with pytest.raises(Exception, match=error.split('"code":"')[1].split('"')[0]):
        c.create_session("claude", "Boots", str(tmp_path), by="swarm", prompt=TASK)
    prompts = [a for a in agent_calls(fake) if a[:2] == ["agent", "prompt"]]
    assert len(prompts) == 1 and prompts[0][2:4] == [agent_calls(fake)[0][2], TASK], "never retried"
    assert [s["state"] for s in c.list_sessions()] == ["ended"]
    assert [c_["args"] for c_ in fake.calls if c_["args"][:2] == ["pane", "close"]] == [["pane", "close", "p1"]], "its pane is closed"
    assert c.list_sessions()[0]["end_reason"] == "pane launch failed"


def test_a_start_without_a_first_prompt_sends_none(herdr, tmp_path):
    c = H.Cockpit(tmp_path / "herdr")
    c.create_session("claude", "Boots", str(tmp_path), by="user")
    assert [a[:2] for a in agent_calls(herdr)] == [["agent", "start"]]


def test_a_failed_start_leaves_none_of_the_pane_files_it_wrote(monkeypatch, tmp_path):
    """A rolled-back start removes the pane's own files (its MCP config holds the pane's bearer), not only the pane."""
    fake = ReadyHerdr(prompt_error='{"error":{"code":"agent_prompt_stalled","message":"no activity observed"}}')
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    c = H.Cockpit(tmp_path / "herdr")
    with pytest.raises(Exception, match="agent_prompt_stalled"):
        c.create_session("claude", "Boots", str(tmp_path), by="user", scene_session_id="scene-1", prompt=TASK)
    written = [p for p in (tmp_path / "herdr" / "panes").rglob("*") if p.is_file()] if (tmp_path / "herdr" / "panes").exists() else []
    assert written == [], f"left behind: {written}"
    assert c.list_sessions()[0]["mcp_config_path"], "the start did write a pane config (the case is not vacuous)"


def _composer(text, width=40):
    """A TUI's composer holding text it never submitted, wrapped the way a narrow pane wraps it."""
    return "banner\n" + "\n".join("> " + text[i:i + width] for i in range(0, len(text), width)) + "\n---\n"


@pytest.mark.parametrize("shown", ["whole", "scrolled"])     # a tall worker task scrolls in Hermes's composer: only its end shows
def test_a_confirmed_stall_with_the_task_still_in_the_composer_gets_one_enter(monkeypatch, tmp_path, shown):
    """Captain, 2026-10-13: one Enter on a confirmed stall. Your Hermes 0.21.7 draws its TUI (herdr: interactive_ready) while it is
    still initializing and drops the Enter of the first prompt: the task stayed unsent in its composer and every Hermes worker
    failed to start (real-account run, d8432bcb). Only when herdr reports the prompt stalled with the agent idle AND the pane
    shows the task in its composer is one Enter sent, and herdr must then see the turn start."""
    task = TASK if shown == "whole" else TASK + "".join(f"\nRule {i}: keep every object you add named." for i in range(40))
    fake = ReadyHerdr(prompt_error=STALLED_IDLE, screen=_composer(task if shown == "whole" else task[-120:]))
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session("claude", "Boots", str(tmp_path), by="swarm", prompt=task)
    name = f"lw-{rec['id']}"
    after = [a for a in agent_calls(fake)][1:]
    assert after == [["agent", "prompt", name, task, "--wait", "--until", "working", "--until", "blocked"],
                     ["agent", "send-keys", name, "enter"],
                     ["agent", "wait", name, "--until", "working", "--until", "blocked", "--timeout", "5000"]]
    assert {s["id"]: s for s in c.list_sessions()}[rec["id"]]["state"] == "live"


@pytest.mark.parametrize("why", ["not-in-composer", "not-idle", "still-stalled"])
def test_any_other_stall_is_never_answered_with_an_enter_twice(monkeypatch, tmp_path, why):
    error = STALLED_IDLE.replace("current status is idle", "current status is unknown") if why == "not-idle" else STALLED_IDLE
    fake = ReadyHerdr(prompt_error=error, screen="user@box:~$ " if why == "not-in-composer" else _composer(TASK),
                      wait_error=STALLED_IDLE if why == "still-stalled" else None)
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    c = H.Cockpit(tmp_path / "herdr")
    with pytest.raises(Exception, match="agent_prompt_stalled"):
        c.create_session("claude", "Boots", str(tmp_path), by="swarm", prompt=TASK)
    enters = [a for a in agent_calls(fake) if a[:2] == ["agent", "send-keys"]]
    assert enters == ([] if why != "still-stalled" else [["agent", "send-keys", agent_calls(fake)[0][2], "enter"]])
    assert [s["state"] for s in c.list_sessions()] == ["ended"]
