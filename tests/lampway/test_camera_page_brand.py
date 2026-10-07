# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The captain's brand pass (2026-10-06): the phone camera page (virtual_camera/webapp, served by the app's camera server to
the phone) is a Lampway page: the lockup in place of the "MIXAR" wordmark, the site's faces and the tokens (brand.css,
generated from server/lampway_server/brand_page.py by scripts/generate_sso_success_page.py), the flame in place of Mixar's
green. Night only: its controls sit over the live picture."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "src/scripts/mixar/modules/virtual_camera/webapp"


def test_the_gate_shows_the_lockup_and_links_the_brand():
    page = (WEB / "index.html").read_text()
    assert "MIXAR" not in page and '<img class="gate-mark" src="lockup.svg" alt="Lampway"' in page
    assert page.index('href="brand.css"') < page.index('href="app.css"'), "the tokens and faces load before the page's own rules"


def test_the_page_uses_the_tokens_not_mixars_colours():
    css = (WEB / "app.css").read_text().lower()
    assert "#6ee7a0" not in css and "var(--lw-accent)" in css and "'ibm plex sans'" in css
    assert not re.search(r"font-family:\s*-apple-system", css), "the site's face, not the phone's"


def test_brand_css_and_the_lockup_are_generated_from_the_template():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/generate_sso_success_page.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0 and (WEB / "brand.css").exists() and (WEB / "lockup.svg").exists(), r.stdout + r.stderr
    assert "prefers-color-scheme" not in (WEB / "brand.css").read_text(), "a viewfinder stays Night"
