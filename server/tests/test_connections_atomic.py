# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""connections_store.md test 9 for the three writers finding F5 names: ``agent_settings._save``, ``provider_prefs.save`` and
``config.resolve_jwt_secret``. A crash mid-write keeps the old file; a file that does not parse is set aside, never emptied."""

import json
import os
import stat

import pytest

from lampway_server import agent_settings as AS
from lampway_server import provider_prefs as PP
from lampway_server.config import Settings
from lampway_server.connections import files as CF


def _kill_replace(monkeypatch):
    def boom(src, dst):
        raise KeyboardInterrupt("killed between the temp write and the replace")
    monkeypatch.setattr(CF.os, "replace", boom)


def test_agent_settings_crash_mid_write_keeps_the_old_file(tmp_path, monkeypatch):
    store = AS.AgentSettingsStore(tmp_path)
    store.save_preference("main", "anthropic", "claude-sonnet-5-5", "Sonnet", None)
    before = (tmp_path / "agent_settings.json").read_text()
    _kill_replace(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        store.save_preference("main", "openai", "llama", "Llama", None)
    monkeypatch.undo()
    assert (tmp_path / "agent_settings.json").read_text() == before
    assert stat.S_IMODE(os.stat(tmp_path / "agent_settings.json").st_mode) == 0o600


def test_provider_prefs_crash_mid_write_keeps_the_old_file(tmp_path, monkeypatch):
    PP.save(tmp_path, {"provider": "openrouter"})
    before = (tmp_path / "provider_prefs.json").read_text()
    _kill_replace(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        PP.save(tmp_path, {"provider": "anthropic"})
    monkeypatch.undo()
    assert (tmp_path / "provider_prefs.json").read_text() == before


def test_an_unparseable_agent_settings_file_is_set_aside_not_emptied(tmp_path):
    (tmp_path / "agent_settings.json").write_text('{"byok": {"provider": "anthropic", "api_key": "sk-ant-FAKE-trunc')
    store = AS.AgentSettingsStore(tmp_path)
    store.save_preference("main", "anthropic", "claude-sonnet-5-5", "Sonnet", None)
    aside = list(tmp_path.glob("agent_settings.json.corrupt-*"))
    assert len(aside) == 1 and "sk-ant-FAKE-trunc" in aside[0].read_text()


def test_an_unparseable_provider_prefs_file_is_set_aside_not_emptied(tmp_path):
    (tmp_path / "provider_prefs.json").write_text('{"provider": "openrou')
    assert PP.load(tmp_path) == {}
    PP.save(tmp_path, {"provider": "anthropic"})
    aside = list(tmp_path.glob("provider_prefs.json.corrupt-*"))
    assert len(aside) == 1 and aside[0].read_text() == '{"provider": "openrou'
    assert json.loads((tmp_path / "provider_prefs.json").read_text()) == {"provider": "anthropic"}


def test_the_jwt_secret_is_written_whole_or_not_at_all(tmp_path, monkeypatch):
    _kill_replace(monkeypatch)
    with pytest.raises(KeyboardInterrupt):
        Settings(state_dir=tmp_path).resolve_jwt_secret()
    monkeypatch.undo()
    assert not (tmp_path / "jwt_secret").exists()
    secret = Settings(state_dir=tmp_path).resolve_jwt_secret()
    assert len(secret) > 40 and (tmp_path / "jwt_secret").read_text() == secret
    assert stat.S_IMODE(os.stat(tmp_path / "jwt_secret").st_mode) == 0o600


def test_an_empty_jwt_secret_file_is_never_used_as_the_secret(tmp_path):
    (tmp_path / "jwt_secret").write_text("")                       # what a crash between touch and write left before
    secret = Settings(state_dir=tmp_path).resolve_jwt_secret()
    assert len(secret) > 40
    assert list(tmp_path.glob("jwt_secret.corrupt-*"))
