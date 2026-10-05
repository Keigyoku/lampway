# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Lampway: the backend is OUR server, resolved at runtime.

Contract:
* with no bundled ``backend_url`` the client talks to the local Lampway
  server, never to the upstream hosted service;
* ``LAMPWAY_BACKEND_URL`` in the environment overrides the bundled value
  for the backend AND the SSO frontend (our server serves both);
* without the override the bundled ``mixar.json`` still wins.
"""

import json

import pytest

from mixar.config import brand
from mixar.config import config as cfg


@pytest.fixture
def paths(tmp_path, monkeypatch):
    """Isolated bundled + user config roots, mirrored onto the bpy stubs."""
    install_root = tmp_path / "install"
    user_root = tmp_path / "user" / "mixar"
    (install_root / "config").mkdir(parents=True)
    user_root.mkdir(parents=True)
    monkeypatch.setattr(cfg.bpy.utils, "resource_path", lambda *_a, **_k: str(install_root))
    monkeypatch.setattr(cfg.bpy.utils, "user_resource", lambda *_a, **_k: str(user_root))
    monkeypatch.setattr(cfg, "_config", None)
    monkeypatch.setattr(cfg, "_user_overrides", {})
    monkeypatch.delenv(brand.ENV_BACKEND_URL, raising=False)
    return install_root / "config" / "mixar.json", user_root / "mixar.json"


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_default_backend_is_the_local_lampway_server(paths):
    assert brand.DEFAULT_BACKEND_URL == "http://127.0.0.1:8787"
    assert cfg.get_server_url() == "http://127.0.0.1:8787"


def test_frontend_falls_back_to_the_backend(paths):
    bundled, _ = paths
    _write(bundled, {"backend_url": "http://192.168.1.9:8787"})
    assert cfg.get_frontend_url() == "http://192.168.1.9:8787"


def test_bundled_urls_win_without_an_override(paths):
    bundled, _ = paths
    _write(bundled, {"backend_url": "https://api.example.test",
                     "frontend_url": "https://www.example.test"})
    assert cfg.get_server_url() == "https://api.example.test"
    assert cfg.get_frontend_url() == "https://www.example.test"


def test_env_override_beats_the_bundled_urls(paths, monkeypatch):
    bundled, _ = paths
    _write(bundled, {"backend_url": "https://api.example.test",
                     "frontend_url": "https://www.example.test"})
    monkeypatch.setenv("LAMPWAY_BACKEND_URL", "http://10.0.0.5:9000/")
    assert cfg.get_server_url() == "http://10.0.0.5:9000"
    assert cfg.get_frontend_url() == "http://10.0.0.5:9000"


def test_blank_override_is_ignored(paths, monkeypatch):
    monkeypatch.setenv("LAMPWAY_BACKEND_URL", "   ")
    assert cfg.get_server_url() == brand.DEFAULT_BACKEND_URL
