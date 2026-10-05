"""LIVE check of ChatGPT plan usage: runs only once the captain has consented (one click in his browser at
http://127.0.0.1:8787/app/chatgpt) and a token with chatgpt.tokens.use.direct exists in the server's state directory
($LAMPWAY_STATE_DIR, else ~/.local/state/lampway-server). It makes two real requests on HIS plan (usage counts toward his
ChatGPT limits): the model list, and a streamed "Say exactly: Hello, world!". A third, with one tool, settles the open
question of how plain function tools behave on this route (the docs say namespaces or additional_tools).

    LAMPWAY_STATE_DIR=<dir> pytest server/tests/test_chatgpt_live.py -v
"""

import asyncio
import os
from pathlib import Path

import httpx
import pytest

from lampway_server import chatgpt_auth as CA
from lampway_server.agent.providers.base import Message, ModelRequest, Text, ToolCall, ToolSpec
from lampway_server.agent.providers.chatgpt_plan import ChatGPTPlanProvider

STATE = Path(os.environ.get("LAMPWAY_STATE_DIR") or Path.home() / ".local/state/lampway-server")


def _consented() -> bool:
    try:
        st = CA.ChatGPTAuth(STATE).status()
    except Exception:
        return False
    return bool(st["signed_in"] and st["plan_usage_enabled"])


pytestmark = pytest.mark.skipif(not _consented(), reason="no consented ChatGPT token yet: the captain's one-time click at /app/chatgpt")


@pytest.fixture
def auth():
    return CA.ChatGPTAuth(STATE)


def test_the_models_list_answers_with_the_account_token(auth):
    token = asyncio.run(auth.access_token())
    r = httpx.get(f"{CA.RESOURCE}/models", headers={"Authorization": f"Bearer {token}"}, timeout=30)
    assert r.status_code == 200 and r.json().get("models")


def test_a_streamed_hello_completes(auth):
    p = ChatGPTPlanProvider(auth, os.environ.get("LAMPWAY_CHATGPT_MODEL", "gpt-6.1-sol"))

    async def run():
        return "".join([e.text async for e in p.stream(ModelRequest("Answer exactly as asked.", [Message.user_text("Say exactly: Hello, world!")], [])) if isinstance(e, Text)])

    assert "Hello, world!" in asyncio.run(run())


def test_a_function_tool_in_a_namespace_is_called(auth):
    p = ChatGPTPlanProvider(auth, os.environ.get("LAMPWAY_CHATGPT_MODEL", "gpt-6.1-sol"))
    tool = ToolSpec("scene_summary", "Lists the objects in the Blender scene. Always call it first.", {"type": "object", "properties": {}})

    async def run():
        return [e async for e in p.stream(ModelRequest("Use tools when asked.", [Message.user_text("What is in my scene? Use the tool.")], [tool]))]

    calls = [e for e in asyncio.run(run()) if isinstance(e, ToolCall)]
    assert [c.name for c in calls] == ["scene_summary"]
