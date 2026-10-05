"""Settings precedence, one rule (the user, 2026-10-05): an explicit call argument > the environment for a session > the saved Providers-dialog choices > the
defaults. It was the other way round: LAMPWAY_OPENROUTER_IMAGE_SIZE=3840x2160 produced 2880x2880 because a saved/default purpose size silently won. The
effective value is logged with where it came from, and the imagegen CLI takes --size / --aspect / --purpose."""

import logging

import pytest

from lampway_server import imagegen as IG
from lampway_server import provider_prefs as PP
from lampway_server.config import Settings


@pytest.fixture
def state(tmp_path):
    PP.save(tmp_path / "state", {"provider": "anthropic", "openrouter_image_size": "2048x2048", "openrouter_image_quality": "high",
                                "image_purposes": {"plates": {"size": "2560x2560"}}})
    return tmp_path / "state"


def test_the_environment_beats_the_saved_choice_which_beats_the_default(state):
    env = {"LAMPWAY_STATE_DIR": str(state)}
    s = PP.effective(env)
    assert s.provider == "anthropic" and s.openrouter_image_size == "2048x2048" and s.sources["provider"] == "saved", "no env: the saved choice"
    s = PP.effective(dict(env, LAMPWAY_PROVIDER="openrouter", LAMPWAY_OPENROUTER_IMAGE_SIZE="3840x2160"))
    assert s.provider == "openrouter" and s.openrouter_image_size == "3840x2160" and s.sources["provider"] == s.sources["openrouter_image_size"] == "env"
    assert s.openrouter_image_quality == "high" and s.sources["openrouter_image_quality"] == "saved", "a field the env does not set keeps the saved one"
    empty = PP.effective({"LAMPWAY_STATE_DIR": str(state / "none")})
    assert empty.provider == "mock" and empty.sources["provider"] == "default"


def test_the_dialogs_view_says_where_each_effective_value_comes_from(state, monkeypatch):
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(state))
    monkeypatch.setenv("LAMPWAY_OPENROUTER_IMAGE_SIZE", "3840x2160")
    s = PP.effective()
    v = PP.view(s)
    assert v["values"]["openrouter_image_size"] == "3840x2160" and v["source"]["openrouter_image_size"] == "env" and v["source"]["openrouter_image_quality"] == "saved"


class _Client:
    pass


def _body(monkeypatch, settings, **kw):
    monkeypatch.setattr(IG, "supported_parameters", lambda client, key, model: {"size", "quality", "resolution", "aspect_ratio"})
    return IG._purpose_body(_Client(), "k", settings, kw.pop("purpose", "plates"), kw.pop("size", ""), kw.pop("aspect", ""))


def test_the_session_size_beats_the_purposes_size_and_an_explicit_size_beats_both(state, monkeypatch, caplog):
    s = PP.effective({"LAMPWAY_STATE_DIR": str(state), "LAMPWAY_OPENROUTER_IMAGE_SIZE": "3840x2160"})
    with caplog.at_level(logging.INFO, logger="lampway.imagegen"):
        assert _body(monkeypatch, s)[1]["size"] == "3840x2160", "env for the session over the saved purpose size (2560x2560)"
        assert _body(monkeypatch, s, size="2160x3840")[1]["size"] == "2160x3840", "an explicit argument over the env"
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "3840x2160" in logged and "env" in logged and "2160x3840" in logged and "argument" in logged, "the effective value and its source are logged"
    saved_only = PP.effective({"LAMPWAY_STATE_DIR": str(state)})
    assert _body(monkeypatch, saved_only)[1]["size"] == "2560x2560"
    default = PP.effective({"LAMPWAY_STATE_DIR": str(state / "none")})
    assert _body(monkeypatch, default)[1]["size"] == "2880x2880"


def test_a_session_size_a_model_cannot_take_is_skipped_and_said_not_silently_sent(state, monkeypatch, caplog):
    s = PP.effective({"LAMPWAY_STATE_DIR": str(state), "LAMPWAY_OPENROUTER_IMAGE_SIZE": "3840x2160"})
    monkeypatch.setattr(IG, "supported_parameters", lambda client, key, model: {"resolution", "aspect_ratio"})
    with caplog.at_level(logging.INFO, logger="lampway.imagegen"):
        model, extra = IG._purpose_body(_Client(), "k", s, "concept", "", "")
    assert "size" not in extra and extra["resolution"] == "2K"
    assert "does not take size" in " ".join(r.getMessage() for r in caplog.records)


def test_the_cli_takes_size_aspect_and_purpose(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "p.txt").write_text("a lamp")
    seen = {}
    monkeypatch.setattr(IG, "_openrouter", lambda *a, **k: seen.update(args=a, kw=k) or {"backend": "openrouter", "files": [], "dry_run": True, "output": "x"})
    rc = IG.main(["--backend", "openrouter", "--prompt-file", "p.txt", "--out", "o", "--size", "3840x2160", "--aspect", "16:9", "--purpose", "mask"])
    assert rc == 0, capsys.readouterr().out
    a = seen["args"]
    assert a[5] == "3840x2160" and a[6] == "16:9" and a[7] == "mask", a
    assert IG.main(["--backend", "openrouter", "--prompt-file", "p.txt", "--out", "o", "--size", "4096x4096"]) == 1
    assert "budget" in capsys.readouterr().out
    assert IG.main(["--backend", "openrouter", "--prompt-file", "p.txt", "--out", "o", "--purpose", "nonsense"]) == 1
    assert "purpose" in capsys.readouterr().out


def test_saving_a_field_the_environment_sets_keeps_the_environments_value_this_session(settings, monkeypatch):
    from starlette.testclient import TestClient
    from lampway_server.app import create_app
    from .fake_client import FakeMixarClient
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(settings.state_dir))
    monkeypatch.setenv("LAMPWAY_OPENROUTER_IMAGE_SIZE", "3840x2160")
    import dataclasses
    settings = dataclasses.replace(settings, openrouter_image_size="3840x2160")          # what Settings.from_env() gives a server started with that variable
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        out = fake.put("/app/provider-settings", json={"values": {"openrouter_image_size": "2048x2048", "openrouter_image_quality": "high"}}).json()
        assert out["values"]["openrouter_image_size"] == "3840x2160" and out["source"]["openrouter_image_size"] == "env", "the session's env still wins"
        assert out["values"]["openrouter_image_quality"] == "high" and out["source"]["openrouter_image_quality"] == "saved"
    assert PP.load(settings.state_dir)["openrouter_image_size"] == "2048x2048", "the choice is saved for the sessions without that env var"
