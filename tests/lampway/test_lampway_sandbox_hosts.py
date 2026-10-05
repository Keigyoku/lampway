# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The sandbox asset allow-list admits our local asset server by default."""

import pytest

from mixar.config import brand
from mixar.modules.space_mixie_chat.core import sandbox_modules


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
