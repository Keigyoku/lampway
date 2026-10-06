"""Shared fixtures: an in-process server and the fake Mixar client that drives it."""

import os

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.config import Settings
from lampway_server.agent.providers.mock import ScriptedProvider

from .fake_client import FakeMixarClient


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
