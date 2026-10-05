"""The OpenRouter provider: wire shape, the hard budget, and that the key never leaks.

Everything here uses a fake key and a fake transport; no network."""

import json
import logging

import httpx
import pytest

from lampway_server.agent.providers.base import Message, ModelRequest, Text, ToolCall
from lampway_server.agent.tools import TOOLS
from lampway_server.config import Settings

pytestmark = pytest.mark.anyio

FAKE_KEY = "sk-or-v1-" + "ab12" * 16          # shaped like a real key, worth nothing


def chunks(items):
    return "".join(f"data: {json.dumps(c)}\n\n" for c in items) + "data: [DONE]\n\n"


def reply(text="ok", cost=0.0123, tool=None):
    delta = {"role": "assistant", "content": text}
    items = [{"choices": [{"index": 0, "delta": delta}]}]
    if tool:
        items.append({"choices": [{"index": 0, "delta": {"tool_calls": [
            {"index": 0, "id": "call_1", "type": "function",
             "function": {"name": tool, "arguments": '{"script": "import bpy"}'}}]}}]})
    items.append({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                  "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "cost": cost}})
    return chunks(items)


def make(handler, **kw):
    from lampway_server.agent.providers.openrouter import OpenRouterProvider, SpendLedger
    ledger = kw.pop("ledger", None) or SpendLedger(ceiling_usd=1.0)
    return OpenRouterProvider(model=kw.pop("model", "anthropic/claude-sonnet-5.5"), api_key=FAKE_KEY, ledger=ledger,
                              transport=httpx.MockTransport(handler), **kw), ledger


REQUEST = ModelRequest("You are Lampway.", [Message.user_text("hi")], list(TOOLS))


async def test_request_goes_to_openrouter_with_attribution_headers_a_token_cap_and_usage_accounting():
    seen = {}

    def handler(request):
        seen.update(url=str(request.url), headers=dict(request.headers), body=json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=reply().encode())

    provider, _ = make(handler, max_tokens=1234)
    events = [e async for e in provider.stream(REQUEST)]
    assert seen["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert seen["headers"]["authorization"] == f"Bearer {FAKE_KEY}"
    assert seen["headers"]["x-title"] == "Lampway" and seen["headers"]["http-referer"].startswith("https://")
    body = seen["body"]
    assert body["model"] == "anthropic/claude-sonnet-5.5" and body["stream"] is True
    assert body["max_tokens"] == 1234
    assert body["usage"] == {"include": True}
    assert body["tools"][0]["function"]["name"] == "run_blender_python"
    assert events == [Text("ok")]


async def test_tool_calls_stream_through_the_shared_openai_translation():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=reply(tool="run_blender_python").encode())

    provider, _ = make(handler)
    events = [e async for e in provider.stream(REQUEST)]
    assert events[-1] == ToolCall(id="call_1", name="run_blender_python", arguments={"script": "import bpy"})


async def test_the_reported_cost_is_added_to_the_ledger_under_the_providers_label():
    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=reply(cost=0.25).encode())

    provider, ledger = make(handler, label="main")
    [e async for e in provider.stream(REQUEST)]
    [e async for e in provider.stream(REQUEST)]
    assert ledger.spent == pytest.approx(0.5)
    assert ledger.by_label == {"main": pytest.approx(0.5)}


async def test_past_the_session_ceiling_the_next_call_is_refused_before_any_request_is_sent():
    from lampway_server.agent.providers.openrouter import SpendCeilingReached, SpendLedger
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=reply(cost=0.6).encode())

    provider, ledger = make(handler, ledger=SpendLedger(ceiling_usd=1.0))
    [e async for e in provider.stream(REQUEST)]          # 0.6 spent
    [e async for e in provider.stream(REQUEST)]          # 1.2 spent: over the ceiling
    with pytest.raises(SpendCeilingReached) as raised:
        [e async for e in provider.stream(REQUEST)]
    assert len(calls) == 2, "the refused call must not reach the network"
    assert "1.00" in str(raised.value)


async def test_an_http_error_that_echoes_the_key_is_redacted_in_the_exception():
    def handler(request):
        return httpx.Response(401, content=json.dumps({"error": {"message": f"bad key {FAKE_KEY}"}}).encode())

    provider, _ = make(handler)
    with pytest.raises(RuntimeError) as raised:
        [e async for e in provider.stream(REQUEST)]
    assert FAKE_KEY not in str(raised.value)
    assert "[redacted]" in str(raised.value) and "401" in str(raised.value)


def test_redact_removes_the_configured_key_and_anything_shaped_like_one():
    from lampway_server.agent.providers.openrouter import redact
    other = "sk-or-v1-" + "cd34" * 16
    text = f"a {FAKE_KEY} b {other} c Bearer {FAKE_KEY}"
    out = redact(text, FAKE_KEY)
    assert FAKE_KEY not in out and other not in out and "sk-or-v1-" not in out
    assert out.startswith("a [redacted] b [redacted] c")


def test_the_log_filter_redacts_a_key_in_the_message_and_in_its_arguments(caplog):
    from lampway_server.agent.providers.openrouter import install_log_redaction
    install_log_redaction(FAKE_KEY)
    logger = logging.getLogger("lampway.test.redaction")
    with caplog.at_level(logging.DEBUG, logger="lampway.test.redaction"):
        logger.warning("sent %s then %s", FAKE_KEY, {"authorization": f"Bearer {FAKE_KEY}"})
        logger.warning(f"literal {FAKE_KEY}")
    rendered = "\n".join(r.getMessage() for r in caplog.records)
    assert FAKE_KEY not in rendered and rendered.count("[redacted]") >= 3


def test_the_provider_and_ledger_reprs_do_not_contain_the_key():
    provider, ledger = make(lambda request: httpx.Response(200))
    assert FAKE_KEY not in repr(provider) and FAKE_KEY not in repr(vars(provider).get("_api_key", "")[:0])
    assert FAKE_KEY not in repr(ledger)


def test_the_key_comes_from_the_environment_or_a_file_reference_never_from_a_value_in_settings(tmp_path):
    from lampway_server.agent.providers.openrouter import KeyMissing, resolve_api_key
    assert resolve_api_key({"OPENROUTER_API_KEY": FAKE_KEY}) == FAKE_KEY
    dotenv = tmp_path / "keys.env"
    dotenv.write_text(f"OTHER=1\nOPENROUTER_API_KEY=\"{FAKE_KEY}\"\n")
    assert resolve_api_key({"LAMPWAY_OPENROUTER_KEY_FILE": str(dotenv)}) == FAKE_KEY
    raw = tmp_path / "raw"
    raw.write_text(FAKE_KEY + "\n")
    assert resolve_api_key({"LAMPWAY_OPENROUTER_KEY_FILE": str(raw)}) == FAKE_KEY
    with pytest.raises(KeyMissing) as raised:
        resolve_api_key({"LAMPWAY_OPENROUTER_KEY_FILE": str(tmp_path / "nope")})
    assert "OPENROUTER_API_KEY" in str(raised.value)
    with pytest.raises(KeyMissing):
        resolve_api_key({})


def test_make_provider_builds_the_main_and_the_swarm_models_from_settings(monkeypatch, tmp_path):
    from lampway_server.agent.providers import make_provider, make_swarm_provider
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)
    settings = Settings.from_env({"LAMPWAY_PROVIDER": "openrouter", "LAMPWAY_STATE_DIR": str(tmp_path)})
    assert settings.openrouter_model == "anthropic/claude-sonnet-5.5"
    assert settings.openrouter_swarm_model == "stealth/space-bunny-alpha"
    main = make_provider(settings)
    worker = make_swarm_provider(settings, label="worker-1")
    assert (main.model, worker.model) == ("anthropic/claude-sonnet-5.5", "stealth/space-bunny-alpha")
    assert main.ledger is worker.ledger, "one session ceiling covers main and swarm"
    assert worker.label == "worker-1" and main.label == "main"


def test_budget_settings_have_small_defaults_and_come_from_the_environment(tmp_path):
    base = Settings.from_env({"LAMPWAY_STATE_DIR": str(tmp_path)})
    assert 0 < base.openrouter_max_tokens <= 8192 and 0 < base.openrouter_budget_usd <= 5
    custom = Settings.from_env({"LAMPWAY_STATE_DIR": str(tmp_path), "LAMPWAY_OPENROUTER_MAX_TOKENS": "999",
                                "LAMPWAY_OPENROUTER_BUDGET_USD": "0.5"})
    assert (custom.openrouter_max_tokens, custom.openrouter_budget_usd) == (999, 0.5)


def test_ledgers_on_one_log_file_see_each_others_spend_so_a_subprocess_cannot_dodge_the_ceiling(tmp_path):
    from lampway_server.agent.providers.openrouter import SpendCeilingReached, SpendLedger
    log = tmp_path / "spend.jsonl"
    server, child = SpendLedger(1.0, log_path=log), SpendLedger(1.0, log_path=log)
    server.add(0.7, "main")
    child.add(0.4, "image")
    assert server.spent == pytest.approx(1.1) and child.spent == pytest.approx(1.1)
    with pytest.raises(SpendCeilingReached):
        child.check()
    assert server.by_label == {"main": pytest.approx(0.7), "image": pytest.approx(0.4)}


def test_the_spend_log_path_can_be_named_by_the_environment_for_child_processes(tmp_path, monkeypatch):
    from lampway_server.agent.providers import spend_ledger
    monkeypatch.setenv("LAMPWAY_SPEND_LOG", str(tmp_path / "shared.jsonl"))
    ledger = spend_ledger(Settings.from_env({"LAMPWAY_STATE_DIR": str(tmp_path / "state")}))
    assert ledger.log_path == tmp_path / "shared.jsonl"
