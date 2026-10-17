"""The configurable image backend behind the mesh-paint workflow (4 painted variants of a clay render): the Tripo Studio driver
(free quota; every setting verified before Generate; never spends credits unless armed) or an OpenRouter image model. The Codex CLI
backend ($imagegen) is retired (agent-modes spec R0; tests/test_retired_cli_providers.py)."""

import json
from pathlib import Path

import pytest

from lampway_server import imagegen as IG
from lampway_server.agent import server_tools as ST


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("LAMPWAY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("LAMPWAY_LOCAL_CLI", raising=False)
    monkeypatch.delenv("LAMPWAY_STUDIO_ARMED", raising=False)
    (tmp_path / "p.txt").write_text("paint it flat")
    (tmp_path / "clay.png").write_bytes(b"x")
    return tmp_path


def test_the_backend_defaults_to_tripo_and_comes_from_the_environment(monkeypatch):
    monkeypatch.delenv("LAMPWAY_IMAGE_BACKEND", raising=False)
    assert IG.backend_name() == "tripo"
    monkeypatch.setenv("LAMPWAY_IMAGE_BACKEND", "openrouter")
    assert IG.backend_name() == "openrouter"
    monkeypatch.setenv("LAMPWAY_IMAGE_BACKEND", "dalle")
    with pytest.raises(ValueError, match="unknown image backend"):
        IG.backend_name()


def test_tripo_runs_the_driver_as_a_dry_run_unless_live_and_never_counts_below_four(root, monkeypatch):
    calls = []
    monkeypatch.setattr(ST, "_exec", lambda cmd, env, timeout: calls.append(cmd) or (0, "dry_run: verified\n"))
    r = IG.generate("tripo", "p.txt", ["clay.png"], "runs/Front", count=4)
    assert r["dry_run"] is True and r["files"] == [] and "dry_run: verified" in r["output"]
    assert "--dry-run" in calls[0] and calls[0][calls[0].index("--count") + 1] == "4"
    with pytest.raises(ValueError, match="never fewer than 4"):
        IG.generate("tripo", "p.txt", [], "runs/x", count=2)


def test_tripo_live_returns_the_files_the_driver_wrote(root, monkeypatch):
    def fake(cmd, env, timeout):
        out = Path(cmd[3])
        out.mkdir(parents=True)
        for i in range(1, 5):
            (out / f"{i}.png").write_bytes(b"png")
        return 0, "images: 4\n"

    monkeypatch.setattr(ST, "_exec", fake)
    r = IG.generate("tripo", "p.txt", ["clay.png"], "runs/Front", count=4, live=True)
    assert r["dry_run"] is False and [Path(f).name for f in r["files"]] == ["1.png", "2.png", "3.png", "4.png"]


def test_a_failing_driver_is_an_error_with_its_output(root, monkeypatch):
    monkeypatch.setattr(ST, "_exec", lambda cmd, env, timeout: (1, "error: studio guard is not armed\n"))
    with pytest.raises(IG.ImageGenError, match="not armed"):
        IG.generate("tripo", "p.txt", [], "runs/x", count=4, live=True)


def test_every_path_is_jailed_to_the_project_root(root):
    with pytest.raises(ST.BadToolCall, match="outside the project root"):
        IG.generate("tripo", "/etc/passwd", [], "runs/x", count=4)
    with pytest.raises(ST.BadToolCall, match="outside the project root"):
        IG.generate("tripo", "p.txt", ["../x.png"], "runs/x", count=4)


def test_the_command_line_prints_a_toon_summary_and_exits_nonzero_on_failure(root, monkeypatch, capsys):
    monkeypatch.setattr(ST, "_exec", lambda cmd, env, timeout: (0, "dry_run: verified\n"))
    rc = IG.main(["--backend", "tripo", "--prompt-file", "p.txt", "--out", "runs/F", "--ref", "clay.png"])
    out = capsys.readouterr().out
    assert rc == 0 and "backend: tripo" in out and "dry_run: true" in out
    monkeypatch.setattr(ST, "_exec", lambda cmd, env, timeout: (1, "error: no\n"))
    assert IG.main(["--backend", "tripo", "--prompt-file", "p.txt", "--out", "runs/F", "--live"]) == 1
    assert "error:" in capsys.readouterr().out


# ------------------------------------------------------------------ the OpenRouter backend (image models with reference images)
import base64

import httpx

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image-bytes"
KEY = "sk-or-v1-" + "ef56" * 16


@pytest.fixture
def orouter(root, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.setenv("LAMPWAY_OPENROUTER_BUDGET_USD", "1.0")
    (root / "design.png").write_bytes(b"design-bytes")
    seen = []

    def handler(request):
        if request.method == "GET":                      # the endpoints lookup: the model family decides what it takes
            return httpx.Response(404, json={})
        seen.append({"url": str(request.url), "auth": request.headers.get("authorization"), "body": json.loads(request.content)})
        return httpx.Response(200, json={"created": 1, "data": [{"b64_json": base64.b64encode(PNG).decode(), "media_type": "image/png"}],
                                         "usage": {"cost": 0.04}})

    monkeypatch.setattr(IG, "openrouter_transport", httpx.MockTransport(handler))
    return seen


def test_openrouter_is_a_backend_choice(monkeypatch):
    monkeypatch.setenv("LAMPWAY_IMAGE_BACKEND", "openrouter")
    assert IG.backend_name() == "openrouter" and "openrouter" in IG.BACKENDS


def test_openrouter_dry_run_sends_nothing_and_says_what_it_would_do(root, orouter):
    r = IG.generate("openrouter", "p.txt", ["clay.png", "design.png"], "runs/Front", count=1)
    assert r["dry_run"] is True and r["files"] == [] and orouter == []
    assert "openai/gpt-image-2.5-flare" in r["output"] and "2 reference" in r["output"]       # the plates purpose


def test_openrouter_live_sends_the_prompt_and_the_references_in_order_and_writes_the_image(root, orouter):
    r = IG.generate("openrouter", "p.txt", ["clay.png", "design.png"], "runs/Front", count=1, live=True)
    sent = orouter[0]
    assert sent["url"] == "https://openrouter.ai/api/v1/images" and sent["auth"] == f"Bearer {KEY}"
    body = sent["body"]
    assert body["model"] == "openai/gpt-image-2.5-flare" and body["prompt"] == "paint it flat" and body["size"] == "2880x2880"   # plates
    urls = [ref["image_url"]["url"] for ref in body["input_references"]]
    assert urls == ["data:image/png;base64," + base64.b64encode(b"x").decode(),
                    "data:image/png;base64," + base64.b64encode(b"design-bytes").decode()]
    assert r["dry_run"] is False and len(r["files"]) == 1
    assert Path(r["files"][0]).name == "1.png" and Path(r["files"][0]).read_bytes() == PNG


def test_openrouter_cost_goes_on_the_shared_session_ledger(root, orouter):
    from lampway_server.agent.providers import spend_ledger
    from lampway_server.config import Settings
    IG.generate("openrouter", "p.txt", ["clay.png"], "runs/Front", count=2, live=True)
    ledger = spend_ledger(Settings.from_env())
    assert ledger.spent == pytest.approx(0.08) and ledger.by_label == {"image": pytest.approx(0.08)}
    assert len(orouter) == 2


def test_openrouter_refuses_past_the_ceiling_before_sending(root, orouter):
    from lampway_server.agent.providers import spend_ledger
    from lampway_server.agent.providers.openrouter import SpendCeilingReached
    from lampway_server.config import Settings
    spend_ledger(Settings.from_env()).add(5.0, "earlier")
    with pytest.raises(SpendCeilingReached):
        IG.generate("openrouter", "p.txt", ["clay.png"], "runs/Front", count=1, live=True)
    assert orouter == []


def test_openrouter_never_asks_for_more_than_four_images_and_keeps_paths_in_the_project(root, orouter):
    with pytest.raises(ValueError, match="at most 4"):
        IG.generate("openrouter", "p.txt", [], "runs/x", count=5, live=True)
    with pytest.raises(ST.BadToolCall, match="outside the project root"):
        IG.generate("openrouter", "p.txt", ["/etc/hostname"], "runs/x", count=1, live=True)


def test_openrouter_http_errors_are_redacted(root, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    monkeypatch.setattr(IG, "openrouter_transport", httpx.MockTransport(
        lambda request: httpx.Response(402, json={"error": {"message": f"credits exhausted for {KEY}"}})))
    with pytest.raises(IG.ImageGenError) as raised:
        IG.generate("openrouter", "p.txt", ["clay.png"], "runs/Front", count=1, live=True)
    assert KEY not in str(raised.value) and "402" in str(raised.value)
