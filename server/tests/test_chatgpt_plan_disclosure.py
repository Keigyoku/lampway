# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sign in with ChatGPT in Mode 1, inside OpenAI's developer guidance (docs/reports/agent-modes-spec.md R0a): tell the user when a
request uses their plan, stop on a usage limit with its recovery text and never fall back to another billing path, and list
only the models the route lists. The request shape and the no-proxy route are pinned in test_chatgpt_plan.py and
test_chatgpt_routes.py.
"""

import asyncio
import json
import uuid

import httpx

from lampway_server.agent.providers.base import Text
from lampway_server.agent.providers.chatgpt_plan import ChatGPTPlanError, list_models

NOTICE = "Using your ChatGPT plan"


def _events(frames):
    return [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event"]


def _turn(fake, ws, text, session_id):
    cmd = fake.command(ws, "chat", fake.chat_payload(text, session_id))
    return _events(fake.run_turn(ws, cmd, on_script=lambda p: {"success": True}))


def test_the_first_turn_on_the_plan_says_so_once(fake, provider):
    provider.name = "chatgpt_plan"
    provider.script = [[Text("one")], [Text("two")]]
    fake.login()
    session_id = str(uuid.uuid4())
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        first = _turn(fake, ws, "hello", session_id)
        second = _turn(fake, ws, "again", session_id)
    said = lambda events: [e for e in events if NOTICE in json.dumps(e)]  # noqa: E731
    assert len(said(first)) == 1 and said(second) == []
    notice = said(first)[0]
    assert notice["bubble_id"].endswith(":plan") and "chatgpt.com/settings/usage" in notice["content"]["set"]


def test_no_notice_on_another_provider(fake, provider):
    provider.script = [[Text("one")]]
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        events = _turn(fake, ws, "hello", str(uuid.uuid4()))
    assert not [e for e in events if NOTICE in json.dumps(e)]


def test_the_model_chip_says_the_plan_is_in_use(fake, settings):
    from lampway_server import choices as CH
    fake.login()
    CH.active_store().set("agent.main", "global", None, {"preferred": "chatgpt_plan:gpt-6.1-sol"}, by="user")
    item = fake.get("/api/v1/agent/model-preference").json()["data"]["items"][0]
    assert item["provider"] == "chatgpt_plan" and NOTICE in item["label"]


class _UsageLimited:
    name = "chatgpt_plan"

    def __init__(self):
        self.calls = 0

    async def stream(self, request):
        self.calls += 1
        raise ChatGPTPlanError("Your ChatGPT plan usage limit was reached. Review or raise it at https://chatgpt.com/settings/usage",
                               code="subscription_sharing_usage_limit_exceeded")
        yield  # pragma: no cover


def test_a_usage_limit_ends_the_turn_with_its_recovery_and_nothing_else_is_tried(fake, http):
    limited = _UsageLimited()
    http.app.state.agent.provider = limited
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        events = _turn(fake, ws, "hello", str(uuid.uuid4()))
    errors = [e for e in events if e.get("type") == "error"]
    assert errors and "usage limit was reached" in errors[-1]["message"] and "chatgpt.com/settings/usage" in errors[-1]["message"]
    assert limited.calls == 1 and http.app.state.agent.provider is limited


def test_the_model_list_keeps_only_listed_models():
    seen = {}

    def handler(request):
        seen["url"], seen["auth"] = str(request.url), request.headers.get("authorization")
        return httpx.Response(200, json={"models": [
            {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol", "visibility": "list"},
            {"slug": "internal-eval", "visibility": "hide"},
            {"slug": "gpt-6.1-sol-mini", "visibility": "list"}]})

    class Auth:
        async def access_token(self):
            return "tok-A"

    models = asyncio.run(list_models(Auth(), transport=httpx.MockTransport(handler)))
    assert seen == {"url": "https://api.openai.com/v1/models", "auth": "Bearer tok-A"}
    assert models == [{"id": "gpt-6.1-sol", "label": "GPT-6.1 Sol"}, {"id": "gpt-6.1-sol-mini", "label": "gpt-6.1-sol-mini"}]
