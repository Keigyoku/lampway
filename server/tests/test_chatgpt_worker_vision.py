# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
from types import SimpleNamespace

from lampway_server import chatgpt_vision as V
from lampway_server.engine import wiring as W


def receipt(auth,model,status):
    V.CF.atomic_write_json(V._path(auth,model),{'version':V.VERSION,'status':status,'account_scope':auth.vision_account_scope(),
        'model':model,'route':V.ROUTE,'completed':True,'attempt':'a'*32,'image_sha256':'b'*64,
        'started_at':0,'finished_at':0,'verified_at':0})


def setup(tmp_path):
    auth = SimpleNamespace(dir=tmp_path/'synthetic-auth',vision_account_scope=lambda:'synthetic-scope')
    provider = SimpleNamespace(name='chatgpt_plan',model='pinned-worker',base_url='https://api.openai.com/v1',auth=auth)
    choice = SimpleNamespace(provider='chatgpt_plan',model=provider.model,params={})
    current = [choice]
    agent = SimpleNamespace(provider=SimpleNamespace(name='mock',model='main-with-no-vision'),
        swarm=SimpleNamespace(bindings=SimpleNamespace(choice_for=lambda key:current[0])),
        swarm_provider_factory=lambda label,resolution:provider)
    return auth,provider,choice,current,agent


def test_existing_plan_worker_adopts_own_receipt_false_true_false_true(tmp_path):
    auth,provider,choice,current,agent = setup(tmp_path)
    get = W.provider_getter(agent)
    sid = 'swarm:one:worker'
    assert get(sid) is provider
    assert get.vision_for(sid,provider) is False
    # Parent model and current binding choice change; the existing worker retains its own original model.
    agent.provider = SimpleNamespace(name='anthropic',model='new-main',supports_vision=True)
    current[0] = SimpleNamespace(provider='chatgpt_plan',model='different-worker',params={})
    for status,expected in [('verified',True),('failed',False),('verified',True)]:
        receipt(auth,provider.model,status)
        assert get(sid) is provider and provider.model == 'pinned-worker'
        assert get.vision_for(sid,provider) is expected
    receipt(auth,'different-worker','verified')
    receipt(auth,provider.model,'failed')
    assert get.vision_for(sid,provider) is False


def test_explicit_pinned_false_never_requalifies_from_receipt(tmp_path):
    auth,provider,choice,current,agent = setup(tmp_path)
    choice.params['supports_vision'] = False
    receipt(auth,provider.model,'verified')
    get=W.provider_getter(agent);sid='swarm:one:worker'
    assert get(sid) is provider
    assert get.vision_for(sid,provider) is False
    current[0] = SimpleNamespace(provider='chatgpt_plan',model=provider.model,params={'supports_vision':True})
    assert get.vision_for(sid,provider) is False
    # Resolution and params are mutable: external mutation cannot widen the captured pin.
    choice.params['supports_vision'] = True
    assert get.vision_for(sid,provider) is False
    choice.model = 'different-model'
    assert get.vision_for(sid,provider) is False


def test_other_provider_keeps_captured_selection_capability(tmp_path):
    auth,provider,choice,current,agent = setup(tmp_path)
    provider.name='anthropic';provider.supports_vision=True
    choice.params['supports_vision']=True
    get=W.provider_getter(agent);sid='swarm:one:worker'
    assert get(sid) is provider and get.vision_for(sid,provider) is True
    provider.supports_vision=False
    choice.params['supports_vision']=False
    assert get.vision_for(sid,provider) is True


def test_summary_new_request_wrapper_uses_current_own_receipt(tmp_path):
    auth,provider,choice,current,agent=setup(tmp_path)
    for status,expected in [('failed',False),('verified',True),('failed',False),('verified',True)]:
        receipt(auth,provider.model,status)
        summary=W._SummaryProvider(None,agent,choice,auth)
        assert summary.model == provider.model and summary.supports_vision is expected
