"""The agent's file tools: dispatch, jail and the MCP instructions built from the same laws."""
import asyncio
import json

import pytest

from lampway_server.agent import files_tools as FT
from lampway_server.agent import tools as AT


def call(root, name, **a):
    out, err = asyncio.run(FT.call(root, name, a))
    return (json.loads(out) if not err else out), err


def test_the_tools_are_registered_and_scaffold_generate_sync_check_pack_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(tmp_path / "state"))
    assert FT.NAMES <= {t.name for t in AT.TOOLS}
    out, err = call(tmp_path, "lampway_agent_files", action="scaffold")
    assert not err and "AGENTS.md" in out["created"]
    out, err = call(tmp_path, "lampway_agent_files", action="generate")
    assert not err and out["uncovered_tools"] == []
    assert call(tmp_path, "lampway_agent_files", action="check")[0]["ok"] is True
    z, err = call(tmp_path, "lampway_agent_files", action="pack_build", out="pack.zip")
    assert not err and call(tmp_path, "lampway_agent_files", action="pack_verify", out="pack.zip")[0]["ok"] is True
    out, err = call(tmp_path, "lampway_agent_files", action="pack_build", out="/etc/pack.zip")
    assert err and "outside the project root" in out
    out, err = call(tmp_path, "lampway_agent_files", action="nope")
    assert err and "action is one of" in out


def test_skills_list_read_and_notes_through_the_tools_with_the_safe_refusals(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    call(tmp_path, "lampway_agent_files", action="generate")
    lst, _ = call(tmp_path, "lampway_skills_list", query="laws")
    assert lst["skills"][0]["name"] == "lampway-laws"
    page, err = call(tmp_path, "lampway_skill_read", path="lampway-laws")
    assert not err and "Lampway laws" in page["text"]
    out, err = call(tmp_path, "lampway_skill_read", path="../x.md")
    assert err and "no '..'" in out
    w, err = call(tmp_path, "lampway_note_write", path="knowledge/a.md", text="one")
    assert not err and w["created"]
    out, err = call(tmp_path, "lampway_note_write", path="knowledge/a.md", text="two", revision="0" * 64)
    assert err and "your draft is kept" in out
    ok, err = call(tmp_path, "lampway_note_write", path="knowledge/a.md", text="two", revision=w["revision"])
    assert not err and (tmp_path / "knowledge" / "a.md").read_text() == "two"
