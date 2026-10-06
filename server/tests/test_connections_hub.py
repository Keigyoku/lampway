# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""connections_store.md section 10, tests 4, 5, 6 and 7, and the resolution rules of CONNECTIONS.md section 4 with the captain's C1, C3 and
C8: the environment wins (the conflict shown), a pointer must be owner-only, the record never holds a value, a test with the route off sends
nothing, and connecting a service never opens its route. Every secret here is a fake sentinel."""

import json
import os

import httpx
import pytest

from lampway_server.connections import hub as H
from lampway_server.connections import store as CS

OR_ENV = "sk-" "or-v1-FAKE-ENV-000000000000000000000000"
OR_FILE = "sk-" "or-v1-FAKE-FILE-11111111111111111111111"
OR_MANUAL = "sk-" "or-v1-FAKE-MANUAL-222222222222222222222"
MESHY = "msy-FAKE-SENTINEL-33333333333333333333"


class Net:
    """A fake transport: records every request, answers from a table of (method, url-prefix) -> (status, json)."""

    def __init__(self, answers=None):
        self.requests, self.answers = [], answers or {}

    def handler(self, request):
        self.requests.append(request)
        for (method, prefix), (status, body) in self.answers.items():
            if request.method == method and str(request.url).startswith(prefix):
                return httpx.Response(status, json=body)
        return httpx.Response(404, json={})


@pytest.fixture
def routes():
    return {}


@pytest.fixture
def net():
    return Net()


@pytest.fixture
def make(tmp_path, routes, net):
    def build(env=None, store=None, **kw):
        return H.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", env=env if env is not None else {}, store=store or CS.MemoryStore(),
                     route_on=lambda r: routes.get(r, False), transport=httpx.MockTransport(net.handler), which=lambda b: None,
                     home=tmp_path / "home", **kw)
    return build


def _owner_only(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.chmod(path, 0o600)
    return path


# ------------------------------------------------------------------------------------------------ test 5: auto order, C3
def test_auto_order_preserves_todays_precedence(make, tmp_path):
    key_file = _owner_only(tmp_path / "keys" / "or.env", f"OPENROUTER_API_KEY={OR_FILE}\n")
    hub = make({"OPENROUTER_API_KEY": OR_ENV, "LAMPWAY_OPENROUTER_KEY_FILE": str(key_file)})
    assert H.secret_of(hub.credential("openrouter")) == OR_ENV
    v = hub.view(["openrouter"])[0]
    assert v["active_source"]["mode"] == "env" and "OPENROUTER_API_KEY" in v["active_source"]["label"]


def test_the_key_file_is_read_when_the_environment_has_no_key(make, tmp_path):
    for text in (f"OPENROUTER_API_KEY={OR_FILE}\n", OR_FILE + "\n"):          # a dotenv line, or the bare key (openrouter.py:58-64)
        key_file = _owner_only(tmp_path / "keys" / "or.env", text)
        hub = make({"LAMPWAY_OPENROUTER_KEY_FILE": str(key_file)})
        assert H.secret_of(hub.credential("openrouter")) == OR_FILE


def test_a_manual_key_with_the_environment_also_set_shows_the_conflict_and_the_environment_wins(make):
    hub = make({"OPENROUTER_API_KEY": OR_ENV})
    hub.put_secret("openrouter", {"key": OR_MANUAL}, by="user")
    hub.set_source("openrouter", "manual", by="user")
    v = hub.view(["openrouter"])[0]
    assert v["conflict"] and "OPENROUTER_API_KEY" in v["conflict"]
    assert H.secret_of(hub.credential("openrouter")) == OR_ENV, "C3: the environment wins over the chosen source"
    assert OR_ENV not in json.dumps(v) and OR_MANUAL not in json.dumps(v)


def test_with_no_environment_the_manual_key_is_used(make):
    hub = make({})
    hub.put_secret("openrouter", {"key": OR_MANUAL}, by="user")
    assert H.secret_of(hub.credential("openrouter")) == OR_MANUAL
    assert hub.view(["openrouter"])[0]["conflict"] is None


# ------------------------------------------------------------------------------------------------ test 4: pointers
def test_pointer_must_be_owner_only(make, tmp_path):
    key_file = tmp_path / "keys" / "meshy.txt"
    key_file.parent.mkdir(parents=True)
    key_file.write_text(MESHY)
    os.chmod(key_file, 0o644)
    hub = make({})
    with pytest.raises(H.Refused) as exc:
        hub.set_source("studio:meshy", "pointer", {"path": str(key_file)}, by="user")
    assert str(exc.value) == f"{key_file} must be owner-only (chmod 600)"


def test_an_env_named_key_file_readable_by_others_is_an_error_not_a_key(make, tmp_path):
    key_file = tmp_path / "keys" / "meshy.txt"
    key_file.parent.mkdir(parents=True)
    key_file.write_text(MESHY)
    os.chmod(key_file, 0o640)
    hub = make({"MESHY_API_KEY_FILE": str(key_file)})                 # C8: refused now, for the variables that did not check it too
    v = hub.view(["studio:meshy"])[0]
    assert v["state"] == "error" and "chmod 600" in v["next_step"]
    with pytest.raises(H.NotConnected):
        hub.credential("studio:meshy")


def test_env_pointer_never_read_into_record(make, tmp_path):
    hub = make({"MY_MESHY": MESHY})
    hub.set_source("studio:meshy", "pointer", {"env": "MY_MESHY"}, by="user")
    record = (tmp_path / "state" / "connections.json").read_text()
    assert "MY_MESHY" in record and MESHY not in record
    assert H.secret_of(hub.credential("studio:meshy")) == MESHY
    key_file = _owner_only(tmp_path / "keys" / "meshy.txt", MESHY)
    hub2 = make({})
    hub2.set_source("studio:meshy", "pointer", {"path": str(key_file)}, by="user")
    record = (tmp_path / "state" / "connections.json").read_text()
    assert str(key_file) in record and MESHY not in record
    assert H.secret_of(hub2.credential("studio:meshy")) == MESHY


def test_a_pointer_to_a_missing_variable_is_refused_with_the_fix(make):
    hub = make({})
    with pytest.raises(H.Refused) as exc:
        hub.set_source("studio:meshy", "pointer", {"env": "NOPE_KEY"}, by="user")
    assert str(exc.value) == ("the environment of the Lampway server has no NOPE_KEY: set it before starting Lampway, or paste the key instead")


# ------------------------------------------------------------------------------------------------ writes
def test_a_secret_that_does_not_look_like_the_service_key_is_refused_and_nothing_is_saved(make):
    store = CS.MemoryStore()
    hub = make({}, store=store)
    for bad in ("", "x" * 9000, "sk-" "or-v1-abc\ndef", "not-an-openrouter-key"):
        with pytest.raises(H.Refused) as exc:
            hub.put_secret("openrouter", {"key": bad}, by="user")
        assert str(exc.value) == "this does not look like a OpenRouter key: nothing was saved"
    assert store.items == {}


def test_an_unknown_id_names_the_connections(make):
    with pytest.raises(H.Refused) as exc:
        make({}).view(["nope"])
    assert str(exc.value).startswith("no connection nope: the connections are ") and "openrouter" in str(exc.value)


def test_a_declared_agent_cannot_write(make):
    hub = make({})
    with pytest.raises(H.Refused) as exc:
        hub.put_secret("openrouter", {"key": OR_MANUAL}, by="agent")
    assert str(exc.value) == "only your click in Connections can change a credential"


def test_put_answers_a_fingerprint_never_the_value(make):
    hub = make({})
    v = hub.put_secret("openrouter", {"key": OR_MANUAL}, by="user")
    assert OR_MANUAL not in json.dumps(v)
    assert v["fingerprint"]["last4"] == OR_MANUAL[-4:] and len(v["fingerprint"]["sha8"]) == 8
    assert v["state"] == "not_checked"


def test_forget_on_a_host_login_names_the_cli(make):
    hub = make({})
    with pytest.raises(H.Refused) as exc:
        hub.forget("codex_cli", "host", by="user")
    assert str(exc.value) == "this login belongs to codex: sign out there (`codex logout`)"


def test_forget_removes_the_manual_key(make):
    store = CS.MemoryStore()
    hub = make({}, store=store)
    hub.put_secret("studio:meshy", {"key": MESHY}, by="user")
    hub.forget("studio:meshy", "manual", by="user")
    assert store.items == {} and hub.view(["studio:meshy"])[0]["state"] == "missing"


# ------------------------------------------------------------------------------------------------ test 6: route off; C1
def test_route_off_test_sends_nothing(make, net):
    hub = make({"MESHY_API_KEY": MESHY})
    with pytest.raises(H.Refused) as exc:
        hub.test("studio:meshy", by="user")
    assert str(exc.value) == "testing sends your key to api.meshy.ai: switch Meshy on in Privacy first"
    assert net.requests == []


def test_a_test_with_the_route_on_records_the_shown_fields_only(make, net, routes):
    routes["studio:meshy"] = True
    net.answers[("GET", "https://api.meshy.ai/openapi/v1/balance")] = (200, {"balance": 1240, "account_email": "someone@example.com"})
    hub = make({"MESHY_API_KEY": MESHY})
    v = hub.test("studio:meshy", by="user")
    assert v["state"] == "connected" and v["identity"]["balance"]["amount"] == 1240 and v["check_kind"] == "remote"
    assert "someone@example.com" not in (hub.state_dir / "connections.json").read_text()
    assert net.requests[0].headers["authorization"] == f"Bearer {MESHY}"


def test_a_refused_key_is_expired(make, net, routes):
    routes["studio:meshy"] = True
    net.answers[("GET", "https://api.meshy.ai/openapi/v1/balance")] = (401, {"detail": f"bad key {MESHY}"})
    v = make({"MESHY_API_KEY": MESHY}).test("studio:meshy", by="user")
    assert v["state"] == "expired" and MESHY not in json.dumps(v)


def test_a_row_with_no_free_check_says_so(make, routes):
    routes["compute:runpod"] = True
    with pytest.raises(H.Refused) as exc:
        make({"RUNPOD_API_KEY": "rp-FAKE"}).test("compute:runpod", by="user")
    assert str(exc.value) == "RunPod has no check that costs nothing: its status is read on this machine only"


def test_poller_never_checks_a_route_that_is_off(make, net, routes):
    clock = [1_000_000.0]
    hub = make({"MESHY_API_KEY": MESHY}, clock=lambda: clock[0])
    hub.report_use("studio:meshy", ok=True)
    clock[0] += 3600
    hub.poll()
    assert net.requests == []


def test_poller_rechecks_only_used_connections_with_their_route_on_every_30_minutes(make, net, routes):
    routes["studio:meshy"] = routes["studio:tripo"] = True
    net.answers[("GET", "https://api.meshy.ai/openapi/v1/balance")] = (200, {"balance": 5})
    clock = [1_000_000.0]
    hub = make({"MESHY_API_KEY": MESHY, "TRIPO_API_KEY": "tsk-FAKE"}, clock=lambda: clock[0])
    hub.report_use("studio:meshy", ok=True)                     # used; tripo_api was never used: never polled
    hub.poll()
    assert len(net.requests) == 1                               # due: no remote check on record
    clock[0] += 600
    hub.poll()
    assert len(net.requests) == 1                               # 10 min later: not yet
    clock[0] += 1300
    hub.poll()
    assert len(net.requests) == 2                               # past 30 min
    clock[0] += 2 * 86400
    hub.poll()
    assert len(net.requests) == 2                               # not used in the last day: no more checks
    assert all(str(r.url).startswith("https://api.meshy.ai") for r in net.requests)


# ------------------------------------------------------------------------------------------------ test 7
def test_credential_does_not_enable_route(make, tmp_path):
    from lampway_server import egress as E
    eg = E.Egress(tmp_path / "state")
    eg.set_route("openrouter", False)
    before = (tmp_path / "state" / "egress.json").read_bytes()
    hub = H.Hub(tmp_path / "state", secrets_dir=tmp_path / "secrets", env={}, store=CS.MemoryStore(), route_on=eg.enabled,
                which=lambda b: None, home=tmp_path / "home")
    hub.put_secret("openrouter", {"key": OR_MANUAL}, by="user")
    hub.put_secret("studio:meshy", {"key": MESHY}, by="user")
    hub.put_secret("studio:hi3d", {"client_id": "cid-FAKE", "client_secret": "csec-FAKE"}, by="user")
    hub.view()
    assert (tmp_path / "state" / "egress.json").read_bytes() == before
    v = hub.view(["openrouter"])[0]
    assert v["route"] == {"id": "openrouter", "on": False}


# ------------------------------------------------------------------------------------------------ the consumer interface
def test_require_refuses_with_the_fixed_texts(make, routes):
    hub = make({})
    with pytest.raises(H.NotConnected) as exc:
        hub.require("studio:meshy")
    assert str(exc.value) == "Meshy is not connected: connect it in Connections" and exc.value.needs_connection == "studio:meshy"
    hub2 = make({"MESHY_API_KEY": MESHY})
    with pytest.raises(H.NotConnected) as exc:
        hub2.require("studio:meshy")
    assert str(exc.value) == "Meshy is connected but its route is off: switch it on in Privacy"
    routes["studio:meshy"] = True
    cred = hub2.require("studio:meshy")
    assert cred.headers() == {"Authorization": f"Bearer {MESHY}"} and cred.env() == {"MESHY_API_KEY": MESHY}


def test_a_credential_never_shows_its_value(make):
    import pickle
    cred = make({"MESHY_API_KEY": MESHY}).credential("studio:meshy")
    assert MESHY not in repr(cred) and MESHY not in str(cred) and MESHY not in f"{cred}"
    with pytest.raises(TypeError):
        pickle.dumps(cred)
    with pytest.raises(TypeError):
        json.dumps(cred)
    assert not any(MESHY == getattr(cred, a, None) for a in dir(cred) if not a.startswith("__"))


def test_env_for_gives_a_child_only_its_connections(make):
    hub = make({"MESHY_API_KEY": MESHY, "OPENROUTER_API_KEY": OR_ENV, "PATH": "/usr/bin", "HOME": "/home/x", "LAMPWAY_JWT_SECRET": "jwt-FAKE",
                "GH_TOKEN": "gh-FAKE", "SOME_SECRET": "s-FAKE"})
    env = hub.env_for(["studio:meshy"])
    assert env["MESHY_API_KEY"] == MESHY and env["PATH"] == "/usr/bin" and env["HOME"] == "/home/x"
    for gone in ("OPENROUTER_API_KEY", "LAMPWAY_JWT_SECRET", "GH_TOKEN", "SOME_SECRET"):
        assert gone not in env
    assert "MESHY_API_KEY" not in hub.env_for([])


def test_a_failed_real_use_turns_the_status_expired(make, routes):
    routes["studio:meshy"] = True
    hub = make({"MESHY_API_KEY": MESHY})
    hub.report_use("studio:meshy", ok=False, status=401)
    v = hub.view(["studio:meshy"])[0]
    assert v["state"] == "expired" and hub.one("studio:meshy")["history"][-1]["by"] == "use"
