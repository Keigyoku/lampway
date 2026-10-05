# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Telemetry is opt-in and only ever goes to the configured backend."""

import pathlib

from mixar.modules.common.analytics import preferences

ROOT = pathlib.Path(__file__).resolve().parents[2]
ANALYTICS = ROOT / "src/scripts/mixar/modules/common/analytics"


def test_usage_analytics_defaults_off(monkeypatch):
    monkeypatch.setattr(preferences, "get_config", lambda: {})
    assert preferences.is_enabled() is False


def test_an_explicit_opt_in_is_honoured(monkeypatch):
    monkeypatch.setattr(preferences, "get_config", lambda: {"share_usage_data": True})
    assert preferences.is_enabled() is True


def test_an_explicit_opt_out_is_honoured(monkeypatch):
    monkeypatch.setattr(preferences, "get_config", lambda: {"share_usage_data": False})
    assert preferences.is_enabled() is False


def test_events_post_to_a_relative_backend_path_only():
    """The batch goes through the shared HTTP client (base = get_server_url),
    never to a host of its own."""
    source = (ANALYTICS / "capture.py").read_text(encoding="utf-8")
    assert '"api/v1/telemetry/events"' in source
    assert "http://" not in source and "https://" not in source
