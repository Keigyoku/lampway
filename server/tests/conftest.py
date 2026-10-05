"""Shared fixtures: an in-process server and the fake Mixar client that drives it."""

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.config import Settings
from lampway_server.agent.providers.mock import ScriptedProvider

from .fake_client import FakeMixarClient


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
    with TestClient(app) as client:
        yield client


@pytest.fixture
def fake(http, settings):
    return FakeMixarClient(http, password=settings.user_password)
