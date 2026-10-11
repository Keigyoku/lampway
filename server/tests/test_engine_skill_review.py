# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Q8: human native skill review, without a model turn or a second pending store."""
import asyncio
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from lampway_server import capabilities as CAP
from lampway_server.agent.turns import AgentHub
from lampway_server.engine.front import HermesFront, Link
from lampway_server.engine.units import UnitInfo

@pytest.fixture
def review(tmp_path, monkeypatch):
    board = CAP.Store(tmp_path / 'state')
    monkeypatch.setattr(CAP, 'ACTIVE', board)
    project, other = str(tmp_path / 'bound-project'), str(tmp_path / 'other-project')
    rec = {'id': 'main', 'unit': 'unit', 'project_root': project, 'cwd': project}
    units = NS(cockpit=NS(list_sessions=lambda: [rec]), settled=AsyncMock())
    front = HermesFront(NS(), units)
    link = Link('unit')
    link.live_id = 'native-live'
    link.info = UnitInfo('unit', 'main', tmp_path / 'owned-home', 1, 'private', 'native-stored')
    link.client = NS(call=AsyncMock(return_value={'output': 'Native review output'}))
    front.links['unit'] = link
    monkeypatch.setattr(front, '_ensure', AsyncMock(return_value=link))
    monkeypatch.setattr(front, '_bookmark', AsyncMock())
    monkeypatch.setattr(front, '_wait', AsyncMock(return_value='completed'))
    stream = NS(emit_quietly=AsyncMock())
    async def drive(text, socket=None):
        return await front.drive(socket or NS(role=''), NS(session_id='unit'), NS(turn_id='turn', conversation_id=''),
                                 stream, 'bubble', [], text)
    return NS(front=front, link=link, board=board, project=project, other=other, drive=drive, stream=stream)

@pytest.mark.parametrize('command', ['/skills pending', '/skills diff 12ab34cd', '/skills reject 12ab34cd'])
def test_read_review_commands_use_native_slash_output_without_prompt_even_with_write_off(review, command):
    assert asyncio.run(review.drive(command)) == 'completed'
    review.link.client.call.assert_awaited_once_with('slash.exec', {'session_id': 'native-live', 'command': command})
    review.front._bookmark.assert_not_awaited()
    review.stream.emit_quietly.assert_awaited_with({'bubble_id': 'bubble', 'content': {'set': 'Native review output'}})

def test_human_approval_obeys_bound_project_instead_of_environment(review, monkeypatch):
    monkeypatch.setenv('LAMPWAY_PROJECT_ROOT', review.other)
    review.board.set('skills.write', enabled=True, project=review.other)
    asyncio.run(review.drive('/skills approve 12ab34cd'))
    review.link.client.call.assert_not_awaited()
    review.board.set('skills.write', enabled=True, project=review.project)
    asyncio.run(review.drive('/skills approve 12ab34cd'))
    review.link.client.call.assert_awaited_once_with('slash.exec', {'session_id': 'native-live', 'command': '/skills approve 12ab34cd'})

@pytest.mark.parametrize('command', ['/skills approve all', '/skills approval off', '/skills mode off',
    '/skills apply 12ab34cd', '/skills deny 12ab34cd', '/skills diff ../../other',
    '/skills approve 12AB34CD', '/skills pending extra', '/skills reject 12ab34cd extra'])
def test_noncanonical_review_never_reaches_native_or_model(review, command):
    asyncio.run(review.drive(command))
    review.link.client.call.assert_not_awaited()
    review.front._ensure.assert_not_awaited()

@pytest.mark.parametrize('role', ['agent', 'worker', 'mcp'])
def test_agent_cannot_review_or_approve_even_an_existing_unit(review, role):
    review.board.set('skills.write', enabled=True, project=review.project)
    asyncio.run(review.drive('/skills approve 12ab34cd', NS(role=role)))
    review.link.client.call.assert_not_awaited()
    review.front._ensure.assert_not_awaited()

@pytest.mark.parametrize('question', [False, True])
def test_review_at_hub_is_refused_before_steer_or_question_answer(review, question):
    review.link.running = not question
    review.link.question = NS(answered=False) if question else None
    hub = NS(engine=review.front, byoa=NS(refusal=lambda *a: None), _message=AsyncMock(return_value={}),
             _session=lambda _: NS(pending_question='unchanged'), _admit=lambda *a, **k: {})
    review.front.answer = lambda *a: pytest.fail('review text answered a native question')
    result = asyncio.run(AgentHub._chat(hub, NS(role=''), {'command_id': 'cmd', 'payload': {
        'session_id': 'unit', 'message': '/skills approve 12ab34cd'}}))
    assert result['result']['ok'] is False
    hub._message.assert_not_awaited()
    review.link.client.call.assert_not_awaited()

@pytest.fixture
def native_helpers(tmp_path, monkeypatch):
    """Pinned modules in-process only; no Hermes serve, provider, or MCP discovery."""
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'third_party/hermes-agent'))
    monkeypatch.setenv('HERMES_HOME', str(tmp_path / 'native-home'))
    from tools import write_approval as wa, skill_manager_tool as sm
    from hermes_cli.write_approval_commands import handle_pending_subcommand
    from hermes_cli import config
    from lampway_server.engine import hermes_config as HC
    board = CAP.Store(tmp_path / 'native-board')
    board.set('skills.write', enabled=True)
    cfg = HC.render(board, None, 'http://127.0.0.1:1', 'test-owned', 'stub')
    monkeypatch.setattr(config, 'load_config', lambda *a, **k: cfg)
    home = tmp_path / 'native-home'
    monkeypatch.setattr(wa, 'get_hermes_home', lambda: home)
    monkeypatch.setattr(sm, 'SKILLS_DIR', home / 'skills')
    content = '---\nname: owned-proof\ndescription: Harmless owned proof.\n---\n\nRead the supplied text.\n'
    return NS(wa=wa, sm=sm, cfg=cfg, home=home, content=content, handle=handle_pending_subcommand)


def test_skills_write_on_still_stages_native_write_until_review(native_helpers):
    import json
    n = native_helpers
    result = json.loads(n.sm.skill_manage(action='create', name='owned-proof', content=n.content))
    assert result.get('staged') is True, result
    assert not (n.home / 'skills' / 'owned-proof' / 'SKILL.md').exists()
    assert n.wa.get_pending(n.wa.SKILLS, result['pending_id'])['payload']['content'] == n.content


def test_island_human_diff_approve_reject_use_pinned_native_pending_helpers(review, native_helpers):
    import json
    n = native_helpers
    staged = json.loads(n.sm.skill_manage(action='create', name='owned-proof', content=n.content))
    assert staged.get('staged') is True, staged
    pid = staged['pending_id']
    async def native_call(method, params):
        assert method == 'slash.exec'
        assert params['session_id'] == 'native-live'
        return {'output': n.handle(n.wa.SKILLS, params['command'].split()[1:])}
    review.link.client.call = AsyncMock(side_effect=native_call)
    asyncio.run(review.drive('/skills pending'))
    assert pid in review.stream.emit_quietly.await_args.args[0]['content']['set']
    asyncio.run(review.drive(f'/skills diff {pid}'))
    assert 'Read the supplied text.' in review.stream.emit_quietly.await_args.args[0]['content']['set']
    asyncio.run(review.drive(f'/skills approve {pid}', NS(role='agent')))
    assert n.wa.get_pending(n.wa.SKILLS, pid) is not None
    asyncio.run(review.drive(f'/skills approve {pid}'))  # off refuses
    assert n.wa.get_pending(n.wa.SKILLS, pid) is not None
    review.board.set('skills.write', enabled=True, project=review.project)
    asyncio.run(review.drive(f'/skills approve {pid}'))
    assert (n.home / 'skills' / 'owned-proof' / 'SKILL.md').read_text() == n.content
    assert n.wa.get_pending(n.wa.SKILLS, pid) is None
    edit = json.loads(n.sm.skill_manage(action='edit', name='owned-proof', content=n.content + 'Unapproved edit.\n'))
    assert edit.get('staged') is True
    review.board.set('skills.write', enabled=False, project=review.project)
    asyncio.run(review.drive(f"/skills reject {edit['pending_id']}"))
    assert n.wa.get_pending(n.wa.SKILLS, edit['pending_id']) is None
    assert (n.home / 'skills' / 'owned-proof' / 'SKILL.md').read_text() == n.content

@pytest.mark.parametrize('kind', ['cross-origin', 'agent-token', 'mcp-token'])
def test_socket_identity_refuses_native_review_without_trusting_body(review, kind):
    headers = {'origin': 'https://outside.invalid'} if kind == 'cross-origin' else {'authorization': 'Bearer fixture'}
    claims = {'origin': 'agent'} if kind == 'agent-token' else {'aud': 'mcp'}
    socket = NS(role='', ws=NS(headers=headers, query_params={}), auth=NS(verify_access=lambda _: claims))
    asyncio.run(review.drive('/skills pending', socket))
    review.front._ensure.assert_not_awaited()
    review.link.client.call.assert_not_awaited()


def test_capability_revoked_during_refresh_cannot_apply(review):
    review.board.set('skills.write', enabled=True, project=review.project)
    async def revoke():
        review.board.set('skills.write', enabled=False, project=review.project)
    review.front.units.settled = revoke
    asyncio.run(review.drive('/skills approve 12ab34cd'))
    review.link.client.call.assert_not_awaited()


@pytest.mark.parametrize('method', [AgentHub._chat, AgentHub._input])
def test_invalid_review_cannot_become_steer_or_question_reply(review, method):
    review.link.running = True
    review.link.question = NS(answered=False)
    hub = NS(engine=review.front, byoa=NS(refusal=lambda *a: None), _message=AsyncMock(return_value={}),
             _session=lambda _: pytest.fail('invalid review reached question state'))
    payload = {'session_id': 'unit', 'message': '/skills approval off', 'text': '/skills approval off'}
    result = asyncio.run(method(hub, NS(role=''), {'command_id': 'cmd', 'payload': payload}))
    assert result['result']['ok'] is False
    hub._message.assert_not_awaited()


def test_native_pending_from_another_home_cannot_be_read_or_applied(review, native_helpers, monkeypatch, tmp_path):
    import json
    n = native_helpers
    result = json.loads(n.sm.skill_manage(action='create', name='owned-proof', content=n.content))
    assert result['staged'] is True
    pid = result['pending_id']
    other = tmp_path / 'other-native-home'
    monkeypatch.setattr(n.wa, 'get_hermes_home', lambda: other)
    monkeypatch.setattr(n.sm, 'SKILLS_DIR', other / 'skills')
    async def native_call(method, params):
        assert method == 'slash.exec'
        return {'output': n.handle(n.wa.SKILLS, params['command'].split()[1:])}
    review.link.client.call = AsyncMock(side_effect=native_call)
    review.board.set('skills.write', enabled=True, project=review.project)
    for command in ['pending', f'diff {pid}', f'approve {pid}']:
        asyncio.run(review.drive('/skills ' + command))
        assert 'Read the supplied text.' not in review.stream.emit_quietly.await_args.args[0]['content']['set']
    assert not (other / 'skills' / 'owned-proof' / 'SKILL.md').exists()
    assert (n.home / 'pending' / 'skills' / f'{pid}.json').exists()


def test_first_island_approval_after_restart_checks_existing_native_binding(review):
    review.board.set('skills.write', enabled=True, project=review.project)
    review.front.links.clear()
    review.front.units.known = lambda unit: review.link.info if unit == 'unit' else None
    async def reconnect(*a, **k):
        review.front.links['unit'] = review.link
        return review.link
    review.front._ensure = AsyncMock(side_effect=reconnect)
    asyncio.run(review.drive('/skills approve 12ab34cd'))
    review.link.client.call.assert_awaited_once_with('slash.exec', {'session_id': 'native-live', 'command': '/skills approve 12ab34cd'})
