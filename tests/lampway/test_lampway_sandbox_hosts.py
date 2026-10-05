# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The sandbox asset allow-list admits our local asset server by default."""

import importlib.util
import pathlib

import pytest

from mixar.config import brand

# ``sandbox_modules.py`` itself imports only ``builtins`` and ``types``, but
# reaching it through its package runs ``space_mixie_chat.core.__init__``,
# which pulls in the connection manager, auth and the platform keyring. This
# directory collects early, and importing all of that here changed the
# outcome of later test files in a box with a real keyring. Load the file
# directly instead; the allow-list code has no package dependencies.
_SANDBOX_MODULES = (
    pathlib.Path(__file__).resolve().parents[2]
    / "src/scripts/mixar/modules/space_mixie_chat/core/sandbox_modules.py"
)
_spec = importlib.util.spec_from_file_location("lampway_sandbox_modules", _SANDBOX_MODULES)
sandbox_modules = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sandbox_modules)


@pytest.fixture
def no_env(monkeypatch):
    monkeypatch.delenv("MIXAR_ASSET_HOSTS", raising=False)


def test_local_asset_server_is_allowed_by_default(no_env):
    hosts = set(sandbox_modules._allowed_asset_hosts())
    assert {"127.0.0.1", "localhost", "amazonaws.com", "cloudflarestorage.com"} <= hosts
    assert hosts == set(brand.DEFAULT_ASSET_HOSTS)


def test_restricted_urllib_accepts_loopback_and_refuses_the_rest(no_env):
    gate = sandbox_modules.RestrictedUrllib()
    gate._check_url("http://127.0.0.1:8787/assets/a.glb")
    gate._check_url("http://localhost:8787/assets/a.glb")
    with pytest.raises(PermissionError):
        gate._check_url("http://evil.example/a.glb")
    with pytest.raises(PermissionError):
        gate._check_url("http://127.0.0.1.evil.example/a.glb")


def test_env_override_still_replaces_the_default(monkeypatch):
    monkeypatch.setenv("MIXAR_ASSET_HOSTS", "assets.example")
    assert sandbox_modules._allowed_asset_hosts() == ("assets.example",)
