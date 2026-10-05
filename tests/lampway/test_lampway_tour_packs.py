# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tour language packs come from our server unless overridden."""

import sys
from unittest.mock import MagicMock

if "requests" not in sys.modules:
    sys.modules["requests"] = MagicMock(name="requests")

from mixar.config import brand  # noqa: E402
from mixar.modules.onboarding.core.tour import config, pack_fetch  # noqa: E402


def test_manifest_defaults_to_the_configured_backend(monkeypatch):
    monkeypatch.delenv(config.ENV_PACKS_MANIFEST_URL, raising=False)
    monkeypatch.setattr(pack_fetch, "get_server_url", lambda: "http://192.168.1.9:8787/")
    assert pack_fetch.manifest_url() == "http://192.168.1.9:8787/tour-packs/manifest.json"


def test_static_default_is_our_server():
    assert config.PACKS_MANIFEST_URL == brand.DEFAULT_BACKEND_URL + brand.TOUR_PACKS_PATH


def test_env_override_still_wins(monkeypatch):
    monkeypatch.setenv(config.ENV_PACKS_MANIFEST_URL, "https://qa.example/manifest.json")
    assert pack_fetch.manifest_url() == "https://qa.example/manifest.json"
