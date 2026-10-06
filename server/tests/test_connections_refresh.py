# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""connections_store.md tests 8 and 10 (finding F9): a refresh is single-flight ACROSS processes - two processes refreshing one expired
ChatGPT session against a token endpoint that rotates and rejects reuse send exactly one refresh and both get the same token; and a
refresh that a crash interrupted is named, never retried in a loop. A file-backed fake token endpoint stands in; nothing leaves."""

import fcntl
import json
import multiprocessing
import time
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from lampway_server import chatgpt_auth as CA

CID = "oaiapp_FAKECLIENT"


def _session(state: Path, *, refresh_started_at=None, saved_at=1000):
    acct = {"email": "u@example.com", "subject": "user-1", "client_id": CID, "access_token": "at-0", "refresh_token": "rt-0",
            "id_token": "x.y.z", "expires_at": 1.0, "expires_in": 3600, "scopes": sorted(CA.SCOPES.split()), "saved_at": saved_at}
    if refresh_started_at is not None:
        acct["refresh_started_at"] = refresh_started_at
    state.mkdir(parents=True, exist_ok=True)
    (state / "chatgpt_auth.json").write_text(json.dumps({"host_id": "urn:uuid:x", "selected": CID, "accounts": {CID: acct}}))


class FileTokenEndpoint:
    """OpenAI's token endpoint as a file both processes share: refresh tokens rotate, a reused one is refused (refresh_token_reused)."""

    def __init__(self, path: Path, delay: float = 0.0):
        self.path, self.delay = path, delay

    @staticmethod
    def init(path: Path, current="rt-0"):
        path.write_text(json.dumps({"current": current, "n": 0, "requests": 0}))

    def handler(self, request):
        body = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        with open(str(self.path) + ".lock", "w") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            st = json.loads(self.path.read_text())
            st["requests"] += 1
            if body.get("refresh_token") != st["current"]:
                self.path.write_text(json.dumps(st))
                return httpx.Response(400, json={"error": "refresh_token_reused"})
            st["n"] += 1
            st["current"] = f"rt-{st['n']}"
            self.path.write_text(json.dumps(st))
        time.sleep(self.delay)                              # the answer is slow: the other process is waiting at the same moment
        return httpx.Response(200, json={"access_token": f"at-{st['n']}", "refresh_token": st["current"], "expires_in": 3600,
                                         "scope": CA.SCOPES})


def _child(state, endpoint, out, go):
    go.wait(10)
    auth = CA.ChatGPTAuth(Path(state), http=httpx.Client(transport=httpx.MockTransport(FileTokenEndpoint(Path(endpoint), 0.6).handler)))
    try:
        Path(out).write_text(auth._access_token_sync())
    except Exception as exc:  # noqa: BLE001
        Path(out).write_text(f"ERROR {type(exc).__name__}: {exc}")


def test_refresh_is_single_flight_across_processes(tmp_path):
    state, endpoint = tmp_path / "state", tmp_path / "endpoint.json"
    _session(state)
    FileTokenEndpoint.init(endpoint)
    ctx = multiprocessing.get_context("spawn")
    go = ctx.Event()
    procs = [ctx.Process(target=_child, args=(str(state), str(endpoint), str(tmp_path / f"out{i}"), go)) for i in range(2)]
    [p.start() for p in procs]
    go.set()
    [p.join(60) for p in procs]
    outs = [(tmp_path / f"out{i}").read_text() for i in range(2)]
    assert outs == ["at-1", "at-1"], outs
    assert json.loads(endpoint.read_text())["requests"] == 1
    saved = json.loads((state / "chatgpt_auth.json").read_text())["accounts"][CID]
    assert saved["refresh_token"] == "rt-1" and saved["saved_at"] >= saved["refresh_started_at"]


def test_a_refresh_writes_refresh_started_at_before_the_request(tmp_path):
    state, endpoint = tmp_path / "state", tmp_path / "endpoint.json"
    _session(state)
    FileTokenEndpoint.init(endpoint)
    seen = {}

    def spy(request):
        seen.update(json.loads((state / "chatgpt_auth.json").read_text())["accounts"][CID])
        return FileTokenEndpoint(endpoint).handler(request)
    auth = CA.ChatGPTAuth(state, http=httpx.Client(transport=httpx.MockTransport(spy)), clock=lambda: 5000.0)
    assert auth._access_token_sync() == "at-1"
    assert seen["refresh_started_at"] == 5000.0 and seen["saved_at"] == 1000      # on disk before a byte went out


def test_interrupted_refresh_is_named(tmp_path):
    state, endpoint = tmp_path / "state", tmp_path / "endpoint.json"
    _session(state, refresh_started_at=2000, saved_at=1000)                      # a refresh began and the process died before the write
    FileTokenEndpoint.init(endpoint, current="rt-1")                             # the provider had rotated: rt-0 is now a reused token
    auth = CA.ChatGPTAuth(state, http=httpx.Client(transport=httpx.MockTransport(FileTokenEndpoint(endpoint).handler)), clock=lambda: 5000.0)
    try:
        auth._access_token_sync()
        raise AssertionError("the refresh should have been refused")
    except CA.NotSignedIn as exc:
        assert str(exc) == "the session was interrupted during a refresh: sign in again"
    for _ in range(3):                                                           # no retry loop: the next calls never reach the endpoint
        try:
            auth._access_token_sync()
        except CA.NotSignedIn:
            pass
    assert json.loads(endpoint.read_text())["requests"] == 1
    assert auth.connection_state() == {"state": "signed_out", "next_step": "the session was interrupted during a refresh: sign in again"}


def test_the_hub_names_the_interrupted_refresh_on_the_row(tmp_path):
    from lampway_server.connections import hub as H
    from lampway_server.connections import store as CS
    state, endpoint = tmp_path / "state", tmp_path / "endpoint.json"
    _session(state, refresh_started_at=2000, saved_at=1000)
    FileTokenEndpoint.init(endpoint, current="rt-1")
    auth = CA.ChatGPTAuth(state, http=httpx.Client(transport=httpx.MockTransport(FileTokenEndpoint(endpoint).handler)), clock=lambda: 5000.0)
    try:
        auth._access_token_sync()
    except CA.NotSignedIn:
        pass
    hub = H.Hub(state, secrets_dir=tmp_path / "secrets", env={}, store=CS.MemoryStore(), oauth={"chatgpt_plan": auth}, which=lambda b: None,
                home=tmp_path / "home", route_on=lambda r: True)
    v = hub.view(["chatgpt_plan"])[0]
    assert (v["state"], v["next_step"]) == ("signed_out", "the session was interrupted during a refresh: sign in again")
