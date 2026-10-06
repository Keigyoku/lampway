# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway's own MCP sign-in, one generic module for every studio (the captain's C4 change, 2026-10-06): discovery from the 401
(RFC 9728), the authorization server's metadata (RFC 8414), dynamic registration as "Lampway" (RFC 7591), S256 PKCE on the server's
loopback port, rotating refresh single-flight across instances, an interrupted refresh named. Hyper3D's tokens live in the Connections
store, never in a state file and never in Claude Code's config. A fake server stands in; nothing here signs anyone in."""

import builtins
import json
import os
import threading
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from lampway_server import mcp_oauth as MO
from lampway_server.connections import store as CS

from .fake_mcp_oauth import AS, MCP, SCOPE, FakeMcpOAuth


@pytest.fixture
def server():
    return FakeMcpOAuth()


@pytest.fixture
def store():
    return CS.MemoryStore()


def make(tmp_path, server, store, clock=None):
    return MO.McpOAuth(MO.HYPER3D, MO.StoreSession(lambda: store, "mcp:hyper3d", tmp_path / "secrets"),
                       http=httpx.Client(transport=server.transport()), redirect_port=8787, **({"clock": clock} if clock else {}))


def sign_in(auth, server):
    attempt = auth.start_login()
    return attempt, auth.complete_login(server.authorize(attempt.url))


def test_discovery_registers_lampway_and_builds_a_pkce_url_from_the_401(tmp_path, server, store):
    auth = make(tmp_path, server, store)
    attempt = auth.start_login()
    assert server.requests[0] == ("POST", MCP), "discovery starts from the MCP server's own 401 (RFC 9728 section 5.1)"
    assert len(server.registered) == 1 and server.registered[0]["client_name"] == "Lampway"
    assert server.registered[0]["redirect_uris"] == ["http://127.0.0.1:8787/auth/hyper3d/callback"]
    assert server.registered[0]["token_endpoint_auth_method"] == "none" and server.registered[0]["scope"] == SCOPE
    u = urlparse(attempt.url)
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    assert f"{u.scheme}://{u.netloc}{u.path}" == AS + "/authorize"
    assert q["scope"] == "rodin:generate rodin:read" and q["code_challenge_method"] == "S256" and q["resource"] == MCP and q["state"]
    auth.start_login()
    assert len(server.registered) == 1, "the registration is kept for this redirect URI"


def test_the_tokens_go_into_the_connections_store_not_a_state_file(tmp_path, server, store):
    auth = make(tmp_path, server, store)
    _, status = sign_in(auth, server)
    assert status["signed_in"] is True
    session = json.loads(store.get("mcp:hyper3d", "session"))
    assert session["access_token"].startswith("h3d-access-") and session["registration"]["client_id"] == "client-1"
    for f in tmp_path.rglob("*"):
        if f.is_file():
            assert "h3d-access-" not in f.read_text(errors="replace") and "h3d-refresh-" not in f.read_text(errors="replace")
    assert server.token_requests[0]["grant_type"] == "authorization_code" and server.token_requests[0]["resource"] == MCP


def test_a_forged_state_a_declined_consent_and_a_bad_verifier_store_nothing(tmp_path, server, store):
    auth = make(tmp_path, server, store)
    auth.start_login()
    with pytest.raises(MO.LoginError, match="state"):
        auth.complete_login({"code": "x", "state": "forged"})
    a = auth.start_login()
    with pytest.raises(MO.LoginDeclined):
        auth.complete_login({"error": "access_denied", "state": a.state})
    b = auth.start_login()
    cb = server.authorize(b.url)
    b.verifier = "tampered"
    with pytest.raises(MO.LoginError, match="exchange"):
        auth.complete_login(cb)
    assert auth.status()["signed_in"] is False


def test_refresh_rotates_and_is_single_flight_across_instances(tmp_path, server, store):
    clock = [1000.0]
    a1 = make(tmp_path, server, store, clock=lambda: clock[0])
    sign_in(a1, server)
    a2 = make(tmp_path, server, store, clock=lambda: clock[0])          # a second instance: its own thread lock, the same file lock
    clock[0] += 4000
    results = []
    threads = [threading.Thread(target=lambda a=a: results.append(a._access_token_sync())) for a in (a1, a2, a1, a2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(set(results)) == 1 and sum(r["grant_type"] == "refresh_token" for r in server.token_requests) == 1


def test_an_interrupted_refresh_is_named_and_not_retried(tmp_path, server, store):
    clock = [1000.0]
    auth = make(tmp_path, server, store, clock=lambda: clock[0])
    sign_in(auth, server)
    data = json.loads(store.get("mcp:hyper3d", "session"))
    data["refresh_started_at"] = data["saved_at"] + 1                   # a refresh began; the process died before the write
    store.put("mcp:hyper3d", {"session": json.dumps(data)})
    server.refresh_tokens.clear()                                        # the provider had rotated
    clock[0] += 4000
    with pytest.raises(MO.NotSignedIn) as exc:
        auth._access_token_sync()
    assert str(exc.value) == "the session was interrupted during a refresh: sign in again"
    n = len(server.token_requests)
    with pytest.raises(MO.NotSignedIn):
        auth._access_token_sync()
    assert len(server.token_requests) == n
    assert auth.connection_state() == {"state": "signed_out", "next_step": "the session was interrupted during a refresh: sign in again"}


def test_sign_out_drops_the_tokens_and_keeps_the_registration_and_re_auth_reuses_it(tmp_path, server, store):
    auth = make(tmp_path, server, store)
    sign_in(auth, server)
    auth.sign_out()
    session = json.loads(store.get("mcp:hyper3d", "session"))
    assert "access_token" not in session and "refresh_token" not in session and session["registration"]["client_id"]
    st = auth.status()
    assert st["signed_in"] is False and st["client_id"] == "client-1"
    sign_in(auth, server)
    assert len(server.registered) == 1 and auth.status()["signed_in"] is True


def test_claude_codes_hyper3d_token_is_never_read(tmp_path, server, store, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    planted = [home / ".claude.json", home / ".claude" / ".credentials.json"]
    for p in planted:
        p.write_text(json.dumps({"mcpServers": {"hyper3d": {"url": MCP}}, "mcpOAuth": {"hyper3d": {"accessToken": "CLAUDE-FAKE-TOKEN"}}}))
        os.chmod(p, 0o600)
    monkeypatch.setenv("HOME", str(home))
    opened, real_open = [], builtins.open
    monkeypatch.setattr(builtins, "open", lambda f, *a, **k: (opened.append(str(f)), real_open(f, *a, **k))[1])
    auth = make(tmp_path, server, store)
    sign_in(auth, server)
    auth._access_token_sync()
    monkeypatch.undo()
    assert not any(str(p) in opened for p in planted)
    assert "CLAUDE-FAKE-TOKEN" not in store.get("mcp:hyper3d", "session")


def test_higgsfield_is_the_same_module_by_configuration(tmp_path):
    from lampway_server import higgsfield_auth as HA
    auth = HA.HiggsfieldAuth(tmp_path / "state")
    assert isinstance(auth, MO.McpOAuth) and auth.config is MO.HIGGSFIELD
    assert MO.HIGGSFIELD.scope == "openid email offline_access" and MO.HIGGSFIELD.callback_path == "/auth/higgsfield/callback"
