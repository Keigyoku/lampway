# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""connections_store.md test 2 (and finding F6): a secret the hub has resolved is never logged, never in a receipt's ``error_text`` or
history, never in the egress log and never in the hub's own write log, even when a provider echoes it back or an exception carries it."""

import json
import logging

import httpx
import pytest

from lampway_server import egress as E
from lampway_server import jobreceipts as JR
from lampway_server import logredact
from lampway_server.connections import hub as H
from lampway_server.connections import store as CS

KEY = "msy-FAKE-SENTINEL-REDACT-9876543210abcdef"


class Grab(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))


@pytest.fixture
def grab():
    logredact.install()
    h, root = Grab(), logging.getLogger()
    h.setFormatter(logging.Formatter("%(message)s"))
    old = root.level
    root.addHandler(h)
    root.setLevel(logging.DEBUG)
    yield h
    root.removeHandler(h)
    root.setLevel(old)


def test_secret_never_logged(tmp_path, grab):
    eg = E.Egress(tmp_path / "state")
    eg.set_route("studio:meshy", True)
    E.set_active(eg)

    def echo(request):                                              # a provider that echoes the key back in a 401
        return httpx.Response(401, json={"detail": f"invalid key {request.headers['authorization']}"})
    hub = H.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", env={}, store=CS.MemoryStore(), transport=httpx.MockTransport(echo),
                which=lambda b: None, home=tmp_path / "home")
    hub.put_secret("studio:meshy", {"key": KEY}, by="user")
    view = hub.test("studio:meshy", by="user")
    assert view["state"] == "expired"
    cred = hub.require("studio:meshy")
    log = logging.getLogger("lampway.test")
    log.warning("the provider said: invalid key %s", H.secret_of(cred))
    log.info(f"Authorization: {cred.headers()['Authorization']}")
    try:
        raise RuntimeError(f"meshy failed for {H.secret_of(cred)}")
    except RuntimeError:
        log.exception("a provider call raised")
    receipts = JR.JobReceipts(tmp_path / "project")
    r, _ = receipts.create("studio:meshy", "meshy-6", {"prompt": "x"}, None, "user")
    receipts.mark_pending(r)
    receipts.mark_unknown(r, "RuntimeError", f"meshy failed for {H.secret_of(cred)}")
    r2, _ = receipts.create("studio:meshy", "meshy-6", {"prompt": "y"}, None, "user")
    receipts.mark_pending(r2)
    receipts.mark_error(r2, f"HTTP 401: invalid key Bearer {H.secret_of(cred)}")

    assert grab.lines and all(KEY not in line for line in grab.lines), grab.lines
    for path in (tmp_path / "state" / "egress" / "log.jsonl", tmp_path / "state" / "connections" / "log.jsonl"):
        assert KEY not in path.read_text()
    for receipt in (tmp_path / "project" / "jobs").rglob("receipt.json"):
        text = receipt.read_text()
        assert KEY not in text, text
    assert "[redacted]" in json.dumps(receipts.get(r2["key"], "studio:meshy")["error_text"])
    assert KEY not in json.dumps(view)


def test_a_registered_value_is_replaced_in_any_text():
    logredact.register_secret("a-FAKE-value-that-has-no-known-shape")
    assert logredact.redact_text("x a-FAKE-value-that-has-no-known-shape y") == "x [redacted] y"


def test_a_short_value_is_never_registered_so_ordinary_words_survive():
    logredact.register_secret("abc")
    assert logredact.redact_text("abc def") == "abc def"
