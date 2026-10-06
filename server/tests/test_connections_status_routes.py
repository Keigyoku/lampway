# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Finding F8 (connections_store.md test 13, connections_migration.md test 8): the old sign-in status routes answered any local
process with the account email and the client id. They now need the bearer and say only whether the sign-in works; the identity is
the Connections row's, masked, and only for the user's own window."""

import pytest


@pytest.fixture
def auth(fake):
    fake.login()
    return fake.rest_headers()


@pytest.mark.parametrize("path", ["/app/chatgpt/status", "/app/higgsfield/status"])
def test_status_routes_need_the_bearer(http, path):
    assert http.get(path).status_code == 401


def test_the_chatgpt_status_is_narrowed(http, auth):
    body = http.get("/app/chatgpt/status", headers=auth).json()
    assert set(body) == {"signed_in", "plan_usage_enabled"}


def test_the_higgsfield_status_is_narrowed(http, auth):
    body = http.get("/app/higgsfield/status", headers=auth).json()
    assert set(body) == {"signed_in"}
