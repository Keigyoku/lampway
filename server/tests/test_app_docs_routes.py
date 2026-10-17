# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Profile helpers resolve locally under the existing Host/CSP boundary."""
import pytest


@pytest.mark.parametrize("route,headline,public_link", [
    ("/app/docs", "Getting started with Lampway", "https://github.com/Keigyoku/lampway"),
    ("/app/bug-report", "Report a Lampway bug", "https://github.com/Keigyoku/lampway/issues/new"),
])
def test_public_profile_helpers_are_local_pages(http, route, headline, public_link):
    response = http.get(route)
    assert response.status_code == 200
    assert headline in response.text and public_link in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "default-src" in response.headers["content-security-policy"]
    assert http.get(route, headers={"host": "lookalike.invalid"}).status_code == 421
    assert http.post(route).status_code == 405
