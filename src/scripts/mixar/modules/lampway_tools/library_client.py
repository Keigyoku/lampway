# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The client's door to the server's Asset Vault (``/api/v1/library/...``, specs/asset_library/asset_query.md section 6.9): read a record, query, record an event. No bpy here; the
server URL and the bearer come from the stored login, as for the job-queue client. Every failure is a ``LibraryClientError`` naming what to do."""

import json
import urllib.error
import urllib.parse
import urllib.request


class LibraryClientError(RuntimeError):
    pass


def _server_url() -> str:
    from mixar.config.config import get_server_url
    return get_server_url().rstrip("/")


def _access_token() -> str:
    from mixar.modules.auth.core.auth import get_access_token
    return get_access_token()


def _request(method, path, body=None, timeout=60):
    token = _access_token()
    if not token:
        raise LibraryClientError("not signed in: log in to the Lampway server first")
    req = urllib.request.Request(_server_url() + path, method=method, data=json.dumps(body).encode("utf-8") if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail") or ""
        except Exception:  # noqa: BLE001
            detail = ""
        raise LibraryClientError(detail or f"the server answered HTTP {exc.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise LibraryClientError(f"the server could not be reached: {exc}") from None


def _data(resp):
    if isinstance(resp, dict) and resp.get("ok") is False:
        raise LibraryClientError(str(resp.get("error") or "the library refused"))
    return resp.get("data") if isinstance(resp, dict) and "data" in resp else resp


def get_asset(asset_id: str, version=None, include=("members",)) -> dict:
    q = {k: v for k, v in (("version", version), ("include", ",".join(include))) if v not in (None, "")}
    return _data(_request("GET", f"/api/v1/library/assets/{urllib.parse.quote(str(asset_id), safe='')}?{urllib.parse.urlencode(q)}"))


def record_event(verb: str, asset_id: str, **payload) -> dict:
    return _data(_request("POST", "/api/v1/library/events", {"verb": verb, "asset_id": asset_id, **payload}))


def query(payload: dict) -> dict:
    return _data(_request("POST", "/api/v1/library/query", payload))


def similar(asset_ids, axes=None, k=12) -> dict:
    return _data(_request("POST", "/api/v1/library/similar", {"asset_ids": list(asset_ids), "axes": axes, "k": k}))


def rate(asset_id: str, **kw) -> dict:
    return _data(_request("POST", f"/api/v1/library/assets/{urllib.parse.quote(str(asset_id), safe='')}/rate", kw))


def collect(**kw) -> dict:
    return _data(_request("POST", "/api/v1/library/collect", kw))


def scan(paths) -> dict:
    return _data(_request("POST", "/api/v1/library/ingest/scan", {"paths": list(paths)}))


def import_scan(scan_id: str) -> dict:
    return _data(_request("POST", "/api/v1/library/ingest/import", {"scan_id": scan_id}))
