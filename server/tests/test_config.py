"""Settings come from the environment; the JWT secret survives restarts."""

import stat

from lampway_server.config import Settings


def test_from_env_maps_every_knob(tmp_path):
    env = {
        "LAMPWAY_HOST": "0.0.0.0", "LAMPWAY_PORT": "9999", "LAMPWAY_JWT_SECRET": "s",
        "LAMPWAY_ACCESS_TTL_S": "120", "LAMPWAY_USER_EMAIL": "me@x", "LAMPWAY_USER_NAME": "Me",
        "LAMPWAY_USER_PASSWORD": "pw", "LAMPWAY_FAKE_CREDITS": "7", "LAMPWAY_STATE_DIR": str(tmp_path),
        "LAMPWAY_PROVIDER": "anthropic", "LAMPWAY_ANTHROPIC_MODEL": "claude-opus-5-5",
        "OPENAI_BASE_URL": "http://h:1/v1", "LAMPWAY_OPENAI_MODEL": "m",
    }
    s = Settings.from_env(env)
    assert (s.host, s.port, s.jwt_secret, s.access_token_ttl_s) == ("0.0.0.0", 9999, "s", 120)
    assert (s.user_email, s.user_name, s.user_password, s.fake_credits) == ("me@x", "Me", "pw", 7)
    assert s.state_dir == tmp_path and s.provider == "anthropic" and s.anthropic_model == "claude-opus-5-5"
    assert s.openai_base_url == "http://h:1/v1" and s.openai_model == "m"


def test_defaults_point_at_loopback_8787_sonnet_and_mock(tmp_path):
    s = Settings.from_env({"LAMPWAY_STATE_DIR": str(tmp_path)})
    assert (s.host, s.port, s.provider, s.anthropic_model) == ("127.0.0.1", 8787, "mock", "claude-sonnet-5-5")
    assert s.user_password == ""  # no password: the desktop-login page approves at once


def test_generated_jwt_secret_is_persisted_with_owner_only_permissions(tmp_path):
    first = Settings(state_dir=tmp_path / "st").resolve_jwt_secret()
    second = Settings(state_dir=tmp_path / "st").resolve_jwt_secret()
    assert first and first == second
    mode = stat.S_IMODE((tmp_path / "st" / "jwt_secret").stat().st_mode)
    assert mode == 0o600


def test_configured_secret_wins_over_the_persisted_one(tmp_path):
    Settings(state_dir=tmp_path).resolve_jwt_secret()
    assert Settings(jwt_secret="mine", state_dir=tmp_path).resolve_jwt_secret() == "mine"
