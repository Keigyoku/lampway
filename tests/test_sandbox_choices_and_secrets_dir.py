# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_store.md section 9 and choices_migration.md step 2: ``choices.json`` joins the sandbox's secret names (a relocated copy is caught
by name), and Connections' default secrets directory is denied even when the app's environment does not name it (the launcher exports
LAMPWAY_SECRETS_DIR to the server only)."""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/scripts"))


def _paths(monkeypatch, tmp_path):
    for k in ("LAMPWAY_SECRETS_DIR", "LAMPWAY_KEYRING_FILE", "LAMPWAY_STATE_DIR"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("LAMPWAY_HOME", str(tmp_path / "home"))
    return importlib.import_module("mixar.modules.space_mixie_chat.core.sandbox_paths")


def test_a_choices_file_anywhere_is_a_secret_by_name(monkeypatch, tmp_path):
    sp = _paths(monkeypatch, tmp_path)
    assert sp.is_secret(tmp_path / "home" / "projects" / "copy" / "choices.json")


def test_the_default_secrets_dir_is_denied_without_the_variable(monkeypatch, tmp_path):
    sp = _paths(monkeypatch, tmp_path)
    assert sp.is_secret(tmp_path / "state" / "lampway-secrets" / "openrouter.json")
    assert not sp.is_secret(tmp_path / "home" / "projects" / "scene.blend")
