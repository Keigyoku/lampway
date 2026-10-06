# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""No test may read the person's real home. Found the hard way: a test passed ``LAMPWAY_HOME="@RUN_TMP@/home"`` to a harness that did not expand it
yet; the binary took the relative path against the repository, ran the first-run migration from the real ~/.mixar into it, and 436 private files
were committed (purged from history before any push). Three guards: every home-shaped variable points inside the session's basetemp for every
test (conftest), an unexpanded placeholder or a relative home is refused loudly, and the migration refuses a source outside the test root."""
import os
from pathlib import Path

import pytest

from mixar.config import paths

HOME_VARS = ("HOME", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "LAMPWAY_HOME", "LAMPWAY_LEGACY_HOME", "LAMPWAY_TEST_ROOT")


def test_every_home_shaped_variable_points_inside_the_basetemp(tmp_path_factory):
    base = Path(tmp_path_factory.getbasetemp()).resolve()
    for var in HOME_VARS:
        val = os.environ.get(var)
        assert val, f"{var} is not set for the tests"
        assert base in Path(val).resolve().parents or Path(val).resolve() == base, f"{var}={val} is outside the test basetemp {base}"
    assert base in Path.home().resolve().parents


@pytest.mark.parametrize("value", ["@RUN_TMP@/home", "relative/home", "home"])
def test_an_unexpanded_placeholder_or_a_relative_home_is_refused_loudly(monkeypatch, value):
    monkeypatch.delenv("LAMPWAY_APP_HOME", raising=False)
    monkeypatch.setenv("LAMPWAY_HOME", value)
    with pytest.raises(ValueError, match="LAMPWAY_HOME"):
        paths.app_home()


def test_the_migration_refuses_a_source_outside_the_test_root(tmp_path, monkeypatch):
    root, elsewhere = tmp_path / "root", tmp_path / "elsewhere"
    (elsewhere / "chat_history").mkdir(parents=True)
    (elsewhere / "chat_history" / "a.json").write_text("{}")
    monkeypatch.setenv("LAMPWAY_TEST_ROOT", str(root))
    monkeypatch.setenv("LAMPWAY_APP_HOME", str(root / "app"))
    monkeypatch.setenv("LAMPWAY_LEGACY_HOME", str(elsewhere))
    with pytest.raises(PermissionError, match="outside the test root"):
        paths.migrate_from_mixar()
    assert not (root / "app" / "chat_history").exists()
    monkeypatch.setenv("LAMPWAY_LEGACY_HOME", str(root / "legacy"))            # inside the root: allowed (the migration's own tests)
    (root / "legacy" / "chat_history").mkdir(parents=True)
    assert paths.migrate_from_mixar()["copied"] == ["chat_history"]
