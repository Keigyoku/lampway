# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import asyncio
import time
import httpx
import pytest
from .test_chatgpt_vision import stack, verified, IMAGE
from .test_chatgpt_auth import auth, fake, start, callback
from lampway_server import capabilities as C
from lampway_server.agent.providers.base import Message, ModelRequest
from lampway_server.agent.providers.chatgpt_plan import ChatGPTPlanProvider, ChatGPTPlanError


@pytest.fixture
def observe():
    seen = []
    C.subscribe(seen_callback := lambda: seen.append('refresh'))
    yield seen
    C.unsubscribe(seen_callback)


def test_verified_login_and_relogin_notify_after_durable_scope(auth, fake, observe):
    auth.complete_login(callback(start(auth, fake)))
    scope = auth.vision_account_scope()
    assert scope and observe == ['refresh']
    observe.clear()
    auth.complete_login(callback(start(auth, fake)))
    assert auth.vision_account_scope() != scope and observe == ['refresh']


def test_signout_notifies_and_cannot_admit_old_receipt(stack, observe):
    auth, V = stack; verified(auth, V)
    auth.http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    auth.sign_out()
    assert not V.admitted(auth, 'synthetic-model') and observe == ['refresh']
    observe.clear(); auth.sign_out()
    assert not observe


@pytest.mark.parametrize('result', ['scope_loss', 'invalid_refresh', 'same_scope'])
def test_refresh_only_notifies_scope_invalidation(stack, observe, result):
    auth, V = stack; verified(auth, V)
    data = auth._read(); data['accounts'][data['selected']].update(expires_at=0,refresh_token='synthetic-refresh'); auth._write(data)
    scope = auth.vision_account_scope()
    def reply(request):
        if result == 'invalid_refresh': return httpx.Response(400,json={'error':'invalid_grant'})
        from lampway_server.chatgpt_auth import DIRECT_SCOPE
        return httpx.Response(200,json={'access_token':'new-synthetic','scope':'openid' if result == 'scope_loss' else DIRECT_SCOPE,'expires_in':3600})
    auth.http = httpx.Client(transport=httpx.MockTransport(reply))
    if result == 'same_scope':
        assert asyncio.run(auth.access_token_for_scope(scope)) == 'new-synthetic'
        assert V.admitted(auth, 'synthetic-model') and not observe
    else:
        from lampway_server.chatgpt_auth import NotSignedIn, PlanUsageDisabled
        with pytest.raises((NotSignedIn, PlanUsageDisabled)): asyncio.run(auth.access_token_for_scope(scope))
        assert not V.admitted(auth, 'synthetic-model') and observe == ['refresh']


def test_failed_image_stream_notifies_after_durable_invalidation(stack, observe):
    auth, V = stack; verified(auth, V)
    p = ChatGPTPlanProvider(auth,'synthetic-model',transport=httpx.MockTransport(lambda r: httpx.Response(400,json={'error':{'code':'invalid_request'}})))
    req = ModelRequest('system',[Message('user',[IMAGE])],[])
    async def run():
        try:
            with pytest.raises(ChatGPTPlanError): [e async for e in p.stream(req)]
        finally: await p.client.aclose()
    asyncio.run(run())
    assert V._read(auth,'synthetic-model')['status'] == 'failed' and observe == ['refresh']
    observe.clear(); V.invalidate(auth,'synthetic-model',scope=auth.vision_account_scope())
    assert not observe
