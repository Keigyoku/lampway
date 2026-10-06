# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 10 in Blender: the Sessions panel's rows wear the same Spark states as the cards (contract 14's previews), and
the cockpit window opens the page with the bearer in the fragment, never in the query."""

from mixar.modules.lampway_tools import workbench_state as W


def test_each_session_wears_its_spark():
    assert W.spark({"state": "live", "activity": "working"}) == "agent_working"
    assert W.spark({"state": "live", "activity": "waiting"}) == "agent_blocked"
    assert W.spark({"state": "live", "unread": True}) == "agent_unread"
    assert W.spark({"state": "live"}) == "agent_idle"
    assert W.spark({"state": "ended"}) == "agent_done"


def test_the_page_url_carries_the_bearer_in_the_fragment_only():
    url = W.page_url("http://127.0.0.1:8787/", "tok en")
    assert url == "http://127.0.0.1:8787/app/workbench/page#t=tok%20en"
    assert "?" not in url


def test_the_terminal_opens_beside_blender():
    """Contract 16 section 6.6: --position at launch from Blender's window rect (later moves are the user's)."""
    assert W.beside(10, 40, 1600) == "1618,40"


def test_the_terminal_fonts_are_generated_from_the_vendored_woff2():
    """scripts/dev/brand_art/fonts_ttf.py --check: the add-on's TTFs decode from the repository's own woff2 (no other source)."""
    import subprocess
    import sys
    from pathlib import Path

    import pytest
    pytest.importorskip("fontTools", reason="fontTools with brotli decodes woff2: pip install 'fonttools[woff]'")
    root = Path(__file__).resolve().parents[2]
    done = subprocess.run([sys.executable, str(root / "scripts/dev/brand_art/fonts_ttf.py"), "--check"], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
