# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The build-time ``mixar.json`` defaults point at the Lampway server."""

import importlib.util
import pathlib

import pytest

from mixar.config import brand

ROOT = pathlib.Path(__file__).resolve().parents[2]

_BUILD_ENV = (
    "MIXAR_BACKEND_URL", "MIXAR_FRONTEND_URL", "MIXAR_ENV", "MIXAR_VERSION",
    "DEV_BYPASS_ENABLED", "DEV_BYPASS_USERNAME", "DEV_BYPASS_PASSWORD",
)


def _generate_config_module():
    spec = importlib.util.spec_from_file_location(
        "lampway_generate_config", ROOT / "scripts" / "generate_config.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def clean_build_env(monkeypatch):
    for key in _BUILD_ENV:
        monkeypatch.delenv(key, raising=False)


def test_bundle_defaults_point_at_our_server(clean_build_env, tmp_path):
    mod = _generate_config_module()
    config = mod.generate_config(str(tmp_path / "VERSION"))
    assert config["backend_url"] == brand.DEFAULT_BACKEND_URL
    assert config["frontend_url"] == brand.DEFAULT_BACKEND_URL


def test_build_environment_still_overrides(clean_build_env, monkeypatch, tmp_path):
    monkeypatch.setenv("MIXAR_BACKEND_URL", "https://api.example.test")
    monkeypatch.setenv("MIXAR_FRONTEND_URL", "https://www.example.test")
    mod = _generate_config_module()
    config = mod.generate_config(str(tmp_path / "VERSION"))
    assert config["backend_url"] == "https://api.example.test"
    assert config["frontend_url"] == "https://www.example.test"


def test_build_scripts_default_to_our_server():
    """settings.sh / settings.bat / .env.example bake the same default."""
    for rel in ("scripts/unix/settings.sh", "scripts/windows/settings.bat", ".env.example"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert brand.DEFAULT_BACKEND_URL in text, rel
