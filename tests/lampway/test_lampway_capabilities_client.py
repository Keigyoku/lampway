# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Client's door to the server's Capabilities (E2): ``GET /app/capabilities[?project=]`` and ``PUT /app/capabilities/{id}``.

A fake transport stands in for the server (``urllib.request.urlopen``): the tests read the request the client built, so a wrong path, a
missing bearer, a body that carries a key nobody set, or a refusal that is lost on the way is seen without a server."""

import io
import json
import urllib.error

import pytest

from mixar.modules.lampway_tools import capabilities_client as CC
from mixar.modules.lampway_tools import studio_client


class Wire:
    """Records each request and answers with the next canned reply (a dict, or an HTTP status and its JSON detail)."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []

    def urlopen(self, req, timeout=None):
        self.seen.append({"method": req.get_method(), "url": req.full_url, "auth": req.get_header("Authorization"),
                          "body": json.loads(req.data.decode("utf-8")) if req.data else None, "timeout": timeout})
        reply = self.replies.pop(0)
        if isinstance(reply, tuple):
            status, detail = reply
            raise urllib.error.HTTPError(req.full_url, status, "refused", {}, io.BytesIO(json.dumps({"detail": detail}).encode("utf-8")))
        return io.BytesIO(json.dumps(reply).encode("utf-8"))


@pytest.fixture
def wire(monkeypatch):
    def make(*replies):
        w = Wire(*replies)
        monkeypatch.setattr(studio_client.urllib.request, "urlopen", w.urlopen)
        return w
    return make


def client():
    return CC.CapabilitiesClient(base_url="http://127.0.0.1:8787", token_getter=lambda: "tok")


def test_the_listing_is_a_bearer_get(wire):
    w = wire({"capabilities": [{"id": "scene.read"}], "proposals": []})
    out = client().capabilities()
    assert out == {"capabilities": [{"id": "scene.read"}], "proposals": []}
    [req] = w.seen
    assert (req["method"], req["url"], req["auth"], req["body"]) == ("GET", "http://127.0.0.1:8787/app/capabilities", "Bearer tok", None)


def test_the_listing_names_the_project(wire):
    w = wire({"capabilities": [], "proposals": []})
    client().capabilities("/work/My Project")
    assert w.seen[0]["url"] == "http://127.0.0.1:8787/app/capabilities?project=%2Fwork%2FMy+Project"


def test_a_read_never_waits_long(wire):
    """The page reads on open and refresh, never in a draw: a server that hangs must not hold Blender for a minute."""
    w = wire({"capabilities": [], "proposals": []}, {"id": "terminal"})
    c = client()
    c.capabilities()
    c.set_capability("terminal", enabled=True)
    assert [r["timeout"] for r in w.seen] == [5, 5]


def test_a_write_is_a_put_with_only_what_was_set(wire):
    w = wire({"id": "web.browse", "enabled": True})
    client().set_capability("web.browse", enabled=True)
    [req] = w.seen
    assert (req["method"], req["url"], req["body"]) == ("PUT", "http://127.0.0.1:8787/app/capabilities/web.browse", {"enabled": True})
    w = wire({"id": "terminal"})
    client().set_capability("terminal", approval="ask_once_per_session", options={"backend": "docker"}, project="/p")
    assert w.seen[0]["body"] == {"approval": "ask_once_per_session", "options": {"backend": "docker"}, "project": "/p"}


def test_a_false_is_written_not_dropped(wire):
    """Turning something off is ``enabled: false``: a falsy value is a value."""
    w = wire({"id": "terminal"})
    client().set_capability("terminal", enabled=False)
    assert w.seen[0]["body"] == {"enabled": False}


def test_a_family_id_is_one_path_segment(wire):
    w = wire({"id": "messaging.*"})
    client().set_capability("messaging.*", enabled=False)
    assert w.seen[0]["url"].endswith("/app/capabilities/messaging.%2A")


def test_the_servers_refusal_reaches_the_caller_in_its_words(wire):
    wire((403, "only your click in Capabilities can change what an agent may do: an agent may propose a change"))
    with pytest.raises(studio_client.StudioError, match="only your click in Capabilities"):
        client().set_capability("web.browse", enabled=True)
    wire((404, "no capability 'nope'"))
    with pytest.raises(studio_client.StudioError, match="no capability 'nope'"):
        client().set_capability("nope", enabled=True)


def test_an_older_server_reads_as_http_404(wire):
    """The page and the walk tell a server without Capabilities by this word (as the Choices window does)."""
    wire((404, ""))
    with pytest.raises(studio_client.StudioError, match="HTTP 404"):
        client().capabilities()


def test_signed_out_is_said_before_any_request(wire):
    w = wire()
    with pytest.raises(studio_client.StudioError, match="not signed in"):
        CC.CapabilitiesClient(base_url="http://127.0.0.1:8787", token_getter=lambda: "").capabilities()
    assert w.seen == []
