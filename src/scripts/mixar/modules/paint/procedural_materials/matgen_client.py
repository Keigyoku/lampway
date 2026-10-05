# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The mat-gen client's request headers. Upstream called a hosted, gated mat-gen router with raw requests, bypassing the shared
HTTP client, so it stamped ``X-Client-Version`` itself; that contract is kept (tests/test_api_client_version_header.py pins it)
though Lampway's server has no generation backend: ``matgen_queue.enqueue_matgen_job`` raises ``MatgenUnavailable`` instead of
sending anything."""

from mixar.modules.common.api.client_version import client_version_headers


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", **client_version_headers()}
