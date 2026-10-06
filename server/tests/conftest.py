"""Shared fixtures: an in-process server and the fake Mixar client that drives it."""

import os

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.config import Settings
from lampway_server.agent.providers.mock import ScriptedProvider

from .fake_client import FakeMixarClient


@pytest.fixture(scope="session", autouse=True)
def _isolated_homes(tmp_path_factory):
    """No server test reads or writes the person's real home: HOME and the XDG dirs point inside the basetemp for the whole session."""
    base = tmp_path_factory.getbasetemp() / "isolated-home"
    names = {"HOME": "home", "XDG_CONFIG_HOME": "config", "XDG_DATA_HOME": "data", "XDG_STATE_HOME": "state", "XDG_CACHE_HOME": "cache"}
    saved = {k: os.environ.get(k) for k in names}
    for var, sub in names.items():
        d = (base / sub).resolve()
        d.mkdir(parents=True, exist_ok=True)
        os.environ[var] = str(d)
    yield base
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(autouse=True)
def _project_root_in_tmp(tmp_path, monkeypatch):
    """Job receipts, the ledger and the studios write under the project root: never the real home during a test."""
    if not os.environ.get("LAMPWAY_PROJECT_ROOT"):
        monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path / "project"))


@pytest.fixture(autouse=True)
def _egress_permissive(tmp_path):
    """The egress hook is installed for the whole test run with a PERMISSIVE manager (every route on, unmapped hosts allowed, log in the test's tmp): existing provider tests drive fake transports at
    invented hosts. tests/test_egress.py swaps in a strict manager to test the gate itself."""
    from lampway_server import egress as E
    E.install()
    E.set_active(E.Egress.permissive(tmp_path / "egress-test-state"))
    yield
    E.set_active(None)


@pytest.fixture(autouse=True)
def _no_real_secret_store(tmp_path, monkeypatch):
    """Connections never touches the person's keyring, ~/.local/state/lampway-secrets or the default server state in a test: no keyring
    backend (the file store is chosen, in the test's tmp), an active hub in the test's tmp, reset after each test."""
    import keyring
    import keyring.backends.fail
    monkeypatch.setenv("LAMPWAY_SECRETS_DIR", str(tmp_path / "secrets"))
    keyring.set_keyring(keyring.backends.fail.Keyring())
    from lampway_server import connections as C
    C.set_active(C.Hub(tmp_path / "connections-state", secrets_dir=tmp_path / "secrets"))   # a consumer outside create_app records here, never in ~/.local/state
    yield
    C.set_active(None)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def settings(tmp_path):
    return Settings(
        host="127.0.0.1",
        port=8787,
        jwt_secret="test-secret-not-for-production",
        access_token_ttl_s=3600,
        user_email="owner@lampway.local",
        user_name="Owner",
        user_password="correct-horse",
        state_dir=tmp_path / "state",
        provider="mock",
    )


@pytest.fixture
def provider():
    """A deterministic provider; tests append turns to ``provider.script``."""
    return ScriptedProvider()


@pytest.fixture
def app(settings, provider):
    return create_app(settings, provider=provider)


@pytest.fixture
def http(app):
    with TestClient(app, base_url="http://127.0.0.1:8787") as client:   # the Host the server answers to
        yield client


@pytest.fixture
def fake(http, settings):
    return FakeMixarClient(http, password=settings.user_password)
