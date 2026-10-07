# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Sign in with ChatGPT in Mode 1, inside OpenAI's developer guidance (docs/reports/agent-modes-spec.md R0a): tell the user when a
request uses their plan, and list only the models the route lists. Mode 1 thinks through the gateway (spec A5), so the usage limit's
recovery text and "nothing else is tried" are pinned where the plan answers the pane's Hermes, in test_engine_gateway.py; the request
shape and the no-proxy route are pinned in test_chatgpt_plan.py and test_chatgpt_routes.py.
"""

import asyncio
import json
import uuid

import httpx

from lampway_server.agent.providers.chatgpt_plan import list_models

from .serve_support import chat, run, stack  # noqa: F401  (stack: the fixture)

NOTICE = "Using your ChatGPT plan"


async def _turn(island, serve, text, session_id):
    serve.scripts.append([("say", "ok")])
    cid, _ = await chat(island, text, session_id)
    await island.ended(cid)
    return island.events(cid)


def test_the_first_turn_on_the_plan_says_so_once(stack, provider):
    provider.name = "chatgpt_plan"                       # the main provider behind the gateway: what the pane's Hermes thinks on

    async def scenario(serve, units, island, front):
        session_id = str(uuid.uuid4())
        return await _turn(island, serve, "hello", session_id), await _turn(island, serve, "again", session_id)

    first, second = run(stack, scenario)
    said = lambda events: [e for e in events if NOTICE in json.dumps(e)]  # noqa: E731
    assert len(said(first)) == 1 and said(second) == []
    notice = said(first)[0]
    assert notice["bubble_id"].endswith(":plan") and "chatgpt.com/settings/usage" in notice["content"]["set"]


def test_no_notice_on_another_provider(stack):
    async def scenario(serve, units, island, front):
        return await _turn(island, serve, "hello", str(uuid.uuid4()))

    events = run(stack, scenario)
    assert events and not [e for e in events if NOTICE in json.dumps(e)]


def test_the_model_chip_says_the_plan_is_in_use(fake, settings):
    from lampway_server import choices as CH
    fake.login()
    CH.active_store().set("agent.main", "global", None, {"preferred": "chatgpt_plan:gpt-6.1-sol"}, by="user")
    item = fake.get("/api/v1/agent/model-preference").json()["data"]["items"][0]
    assert item["provider"] == "chatgpt_plan" and NOTICE in item["label"]


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
