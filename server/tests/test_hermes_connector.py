# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Symbolic Hermes connector authority stays in owned, dynamically read pane files."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

from lampway_server import pane_mcp as C


def write(path, binding="scene-one", desktop=True, direct=()):
    value = {"version": 1, "binding": binding, "desktop": {"command": sys.executable,
             "args": [str(path.parent / "fake_mcp.py")] } if desktop else None, "direct": list(direct)}
    path.write_text(json.dumps(value));path.chmod(0o600)
    return value


@pytest.fixture
def config(tmp_path,monkeypatch):
    root=tmp_path
    tmp_path=root/'panes'/'one';tmp_path.mkdir(parents=True,mode=0o700)
    monkeypatch.setenv(C.ROOT_ENV,str(root))
    (tmp_path / "fake_mcp.py").write_text('''import json,os,sys
for line in sys.stdin:
 r=json.loads(line)
 if 'id' not in r:continue
 m=r['method'];result={}
 if m=='tools/list':result={'tools':[{'name':'scene_summary','inputSchema':{'type':'object'}}]}
 elif m=='tools/call':result={'content':[{'type':'text','text':os.environ.get('LAMPWAY_BOUND_SESSION','')}]}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
''')
    path=tmp_path/'mcp.json';write(path);return path


def test_bound_discovery_call_and_live_rebind(config):
    async def proof():
        connector=C.Connector(str(config))
        try:
            assert [x['name'] for x in (await connector.request('tools/list'))['tools']]==['scene_summary']
            assert (await connector.request('tools/call',{'name':'scene_summary','arguments':{}}))['content'][0]['text']=='scene-one'
            write(config,'scene-two')
            assert (await connector.request('tools/call',{'name':'scene_summary','arguments':{}}))['content'][0]['text']=='scene-two'
            write(config,binding='')
            assert (await connector.request('tools/list'))=={'tools':[]}
            with pytest.raises(PermissionError):await connector.request('tools/call',{'name':'scene_summary'})
        finally:await connector.close()
    asyncio.run(proof())


def test_worker_direct_only_no_desktop(config):
    async def proof():
        write(config,'swarm:one:worker',desktop=False,direct=[{'url':'http://127.0.0.1:9/api/v1/mcp/pane',
            'headers':{'Authorization':'Bearer synthetic','X-Mixar-Session-Id':'swarm:one:worker'}}])
        connector=C.Connector(str(config));calls=[]
        async def http(entry,method,params):
            calls.append((entry,method,params))
            return {'tools':[{'name':'lampway_worker_done','inputSchema':{'type':'object'}}]} if method=='tools/list' else {'content':[]}
        connector.http_request=http
        try:
            assert [x['name'] for x in (await connector.request('tools/list'))['tools']]==['lampway_worker_done']
            await connector.request('tools/call',{'name':'lampway_worker_done','arguments':{}})
            assert calls[-1][0]['headers']['X-Mixar-Session-Id']=='swarm:one:worker'
            assert connector.process is None
        finally:await connector.close()
    asyncio.run(proof())


@pytest.mark.parametrize('mode',[0o644,0o666])
def test_config_permissions_fail_closed(config,mode):
    config.chmod(mode)
    assert C.read_config(str(config)) is None


def test_unbound_missing_malformed_and_worker_desktop_are_closed(config):
    assert C.read_config(None) is None
    assert C.read_config('relative.json') is None
    config.write_text('{invalid')
    assert C.read_config(str(config)) is None
    write(config,'swarm:one:worker',desktop=True)
    assert C.read_config(str(config)) is None


@pytest.mark.parametrize('url',['http://example.com/api/v1/mcp/pane','https://127.0.0.1/api/v1/mcp/pane',
                               'http://127.0.0.1/other','http://user:pass@127.0.0.1/api/v1/mcp/pane'])
def test_direct_authority_is_local_pane_only(config,url):
    write(config,'swarm:one:worker',desktop=False,direct=[{'url':url,'headers':{
        'Authorization':'Bearer synthetic','X-Mixar-Session-Id':'swarm:one:worker'}}])
    assert C.read_config(str(config)) is None


def test_two_connectors_do_not_share_binding_or_forward_login_env(config,monkeypatch):
    async def proof():
        other=config.parent.parent/'two'/'mcp.json';other.parent.mkdir(mode=0o700);write(other,'scene-other');(other.parent/'fake_mcp.py').write_bytes((config.parent/'fake_mcp.py').read_bytes())
        one,two=C.Connector(str(config)),C.Connector(str(other))
        try:
            replies=await asyncio.gather(*(c.request('tools/call',{'name':'scene_summary'}) for c in (one,two)))
            assert [r['content'][0]['text'] for r in replies]==['scene-one','scene-other']
            assert one.process.pid!=two.process.pid
        finally:await asyncio.gather(one.close(),two.close())
        assert one.process is None and two.process is None
    monkeypatch.setenv('ANTHROPIC_API_KEY','synthetic-private')
    monkeypatch.setenv('HERMES_HOME','unreadable-user-home')
    asyncio.run(proof())


def test_symlink_configuration_is_not_read(config):
    alias=config.parent/'alias.json';alias.symlink_to(config)
    assert C.read_config(str(alias)) is None


def test_hermes_main_preserves_native_settings_and_owned_setup(tmp_path):
    from lampway_server.herdr.harnesses.hermes import Hermes
    from lampway_server.herdr.harnesses.base import PaneSpec
    adapter=Hermes();pane=PaneSpec(cwd=str(tmp_path),scene_session_id='scene-one',
        mcp_config_path=str(tmp_path/'pane.json'),launcher=('/opt/lampway/lampway-mcp',))
    wiring=adapter.lampway_tools(pane)
    assert adapter.tools_reachable and adapter.direct_ok and adapter.always_pane_config
    assert wiring.verified is False and wiring.env[C.CONFIG_ENV]==pane.mcp_config_path and C.ROOT_ENV in wiring.env
    assert '--toolsets' not in adapter.launch(pane)
    assert not any(k in wiring.env for k in ('HOME','HERMES_HOME','HERMES_TUI_TOOLSETS'))
    assert adapter.launch(pane,task='synthetic')==['hermes','chat','-q','synthetic']
    assert adapter.resume('native-one',pane)==['hermes','--resume','native-one']
    body=json.loads(wiring.files[pane.mcp_config_path]);assert body['binding']=='scene-one'
    unbound=PaneSpec(cwd=str(tmp_path),mcp_config_path=str(tmp_path/'empty.json'))
    body=json.loads(adapter.lampway_tools(unbound).files[unbound.mcp_config_path])
    assert body=={'version':1,'binding':'','desktop':None,'direct':[]}


def test_normal_direct_uses_host_bearer_without_worker_header(config):
    value=write(config,direct=[{'url':'http://127.0.0.1:9/api/v1/mcp/pane',
                             'headers':{'Authorization':'Bearer synthetic'}}])
    assert C.read_config(str(config))==value


def test_direct_http_transport_forwards_only_owned_headers_and_call(config):
    import httpx
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    async def proof():
        seen=[]
        async def endpoint(request):
            payload=await request.json();seen.append((dict(request.headers),payload))
            result={'tools':[{'name':'lampway_worker_done','inputSchema':{'type':'object'}}]} if payload['method']=='tools/list' else {'content':[]}
            return JSONResponse({'jsonrpc':'2.0','id':payload['id'],'result':result})
        write(config,'swarm:one:worker',desktop=False,direct=[{'url':'http://127.0.0.1/api/v1/mcp/pane',
            'headers':{'Authorization':'Bearer synthetic','X-Mixar-Session-Id':'swarm:one:worker'}}])
        connector=C.Connector(str(config))
        await connector.refresh()
        connector.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=Starlette(routes=[Route('/api/v1/mcp/pane',endpoint,methods=['POST'])])),trust_env=False)
        try:
            await connector.request('tools/call',{'name':'lampway_worker_done','arguments':{'summary':'synthetic'}})
            assert seen[-1][0]['authorization']=='Bearer synthetic'
            assert seen[-1][0]['x-mixar-session-id']=='swarm:one:worker'
            assert seen[-1][1]['params']=={'name':'lampway_worker_done','arguments':{'summary':'synthetic'}}
            assert connector.process is None
        finally:await connector.close()
    asyncio.run(proof())


def test_hermes_worker_refuses_until_native_isolation_policy_is_chosen(tmp_path):
    from lampway_server.herdr.harnesses.hermes import Hermes
    from lampway_server.herdr.harnesses.base import PaneSpec,DirectServer
    pane=PaneSpec(cwd=str(tmp_path),desktop=False,mcp_config_path=str(tmp_path/'worker.json'),
        direct=(DirectServer('lampway','http://127.0.0.1/api/v1/mcp/pane',
            {'X-Mixar-Session-Id':'swarm:one:worker'},'WORKER_TOKEN','synthetic'),))
    for operation in (lambda:Hermes().lampway_tools(pane),lambda:Hermes().launch(pane,task='synthetic')):
        with pytest.raises(ValueError,match='connector-only worker'):
            operation()


def test_connector_refuses_arbitrary_file_before_open(tmp_path,monkeypatch):
    secret=tmp_path/'auth.json';secret.write_text('{"private":true}');secret.chmod(0o600)
    monkeypatch.setenv('LAMPWAY_HERMES_CONNECTOR_ROOT',str(tmp_path))
    opened=[];original=C.os.open
    def watch(path,*args,**kwargs):opened.append(str(path));return original(path,*args,**kwargs)
    monkeypatch.setattr(C.os,'open',watch)
    assert C.read_config(str(secret)) is None
    assert opened==[]


def test_stdio_call_has_no_short_read_deadline_and_cancels_owned_child(config,monkeypatch):
    async def proof():
        connector=C.Connector(str(config));timeouts=[]
        original=asyncio.wait_for
        async def wait(awaitable,timeout):
            timeouts.append(timeout);return await original(awaitable,timeout)
        monkeypatch.setattr(asyncio,'wait_for',wait)
        try:
            await connector.request('tools/call',{'name':'scene_summary'})
            assert timeouts == [30,30], 'only initialize and discovery may impose short read deadlines'
        finally:await connector.close()
    asyncio.run(proof())


def test_stdio_reader_handles_cancellation_while_call_is_active(monkeypatch):
    import io
    seen=[];output=io.StringIO()
    class Waiting:
        def __init__(self,*args):pass
        async def request(self,method,params=None):
            if method=='tools/call':
                seen.append('started')
                try:await asyncio.Event().wait()
                except asyncio.CancelledError:seen.append('cancelled');raise
            return {}
        async def close(self):seen.append('closed')
    monkeypatch.setattr(C,'Connector',Waiting)
    monkeypatch.setattr(sys,'stdin',io.StringIO('\n'.join(json.dumps(x) for x in [
        {'jsonrpc':'2.0','id':7,'method':'tools/call','params':{'name':'synthetic'}},
        {'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':7}},
        {'jsonrpc':'2.0','id':8,'method':'ping'}])+'\n'))
    monkeypatch.setattr(sys,'stdout',output)
    asyncio.run(asyncio.wait_for(C.serve(),0.5))
    assert 'cancelled' in seen and 'closed' in seen
    assert any(json.loads(line).get('id')==8 for line in output.getvalue().splitlines())


def test_cancellation_reaches_stdio_request_and_reaps_owned_child(config):
    import os
    child=config.parent/'fake_mcp.py';trace=config.parent/'trace.jsonl'
    child.write_text('''import json,sys
from pathlib import Path
trace=Path('''+repr(str(trace))+''')
for line in sys.stdin:
 r=json.loads(line)
 with trace.open('a') as log:log.write(json.dumps(r)+'\\n')
 if r['method']=='tools/call' or 'id' not in r:continue
 result={'tools':[{'name':'scene_summary','inputSchema':{'type':'object'}}]} if r['method']=='tools/list' else {}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
''')
    async def proof():
        connector=C.Connector(str(config));task=asyncio.create_task(connector.request('tools/call',{'name':'scene_summary'}))
        try:
            for _ in range(100):
                records=[json.loads(x) for x in trace.read_text().splitlines()] if trace.exists() else []
                calls=[r for r in records if r['method']=='tools/call']
                if calls:break
                await asyncio.sleep(.02)
            assert calls and connector.process is not None
            pid=connector.process.pid;task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            assert connector.process is None
            records=[json.loads(x) for x in trace.read_text().splitlines()]
            cancelled=[r for r in records if r['method']=='notifications/cancelled']
            assert cancelled==[{'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':calls[0]['id']}}]
            with pytest.raises(ProcessLookupError):os.kill(pid,0)
        finally:
            if not task.done():task.cancel()
            await asyncio.gather(task,return_exceptions=True);await connector.close()
    asyncio.run(proof())


def test_cancellation_reaches_direct_http_without_repeating_tool(config):
    import httpx
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.routing import Route
    async def proof():
        seen=[];started=asyncio.Event()
        async def endpoint(request):
            payload=await request.json();seen.append(payload)
            if payload['method']=='tools/call':started.set();await asyncio.Event().wait()
            result={'tools':[{'name':'lampway_worker_done','inputSchema':{'type':'object'}}]}
            return JSONResponse({'jsonrpc':'2.0','id':payload.get('id'),'result':result})
        write(config,'swarm:one:worker',desktop=False,direct=[{'url':'http://127.0.0.1/api/v1/mcp/pane',
            'headers':{'Authorization':'Bearer synthetic','X-Mixar-Session-Id':'swarm:one:worker'}}])
        connector=C.Connector(str(config));await connector.refresh()
        connector.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=Starlette(routes=[Route('/api/v1/mcp/pane',endpoint,methods=['POST'])])),trust_env=False)
        task=asyncio.create_task(connector.request('tools/call',{'name':'lampway_worker_done'}))
        try:
            await asyncio.wait_for(started.wait(),2);task.cancel()
            with pytest.raises(asyncio.CancelledError):await task
            calls=[r for r in seen if r['method']=='tools/call'];assert len(calls)==1
            assert seen[-1]=={'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':calls[0]['id']}}
            assert connector.client is None
        finally:
            if not task.done():task.cancel()
            await asyncio.gather(task,return_exceptions=True);await connector.close()
    asyncio.run(proof())


@pytest.mark.parametrize('resume',[False,True])
def test_hermes_refuses_direct_worker_argv_without_wiring(tmp_path,resume):
    from lampway_server.herdr.harnesses.hermes import Hermes
    from lampway_server.herdr.harnesses.base import PaneSpec
    pane=PaneSpec(cwd=str(tmp_path),desktop=False)
    with pytest.raises(ValueError,match='connector-only worker'):
        Hermes().resume('native-worker',pane) if resume else Hermes().launch(pane,task='synthetic')


@pytest.mark.parametrize('large_method',['tools/list','tools/call'])
def test_owned_stdio_accepts_large_inventory_and_image_without_retry(config,large_method):
    import os
    trace=config.parent/'large-trace.jsonl'
    (config.parent/'fake_mcp.py').write_text('''import json,sys
from pathlib import Path
trace=Path('''+repr(str(trace))+''')
blob='AAAA'*32768
for line in sys.stdin:
 r=json.loads(line)
 if 'id' not in r:continue
 with trace.open('a') as log:log.write(json.dumps(r)+'\\n')
 result={}
 if r['method']=='tools/list':result={'tools':[{'name':'scene_summary','description':blob if '''+repr(large_method)+'''=='tools/list' else 'synthetic','inputSchema':{'type':'object'}}]}
 elif r['method']=='tools/call':result={'content':[{'type':'image','mimeType':'image/png','data':blob}]}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
''')
    async def proof():
        connector=C.Connector(str(config));pid=None
        try:
            if large_method=='tools/list':
                result=await connector.request('tools/list')
                assert result['tools'][0]['description']=='AAAA'*32768
            else:
                result=await connector.request('tools/call',{'name':'scene_summary','arguments':{}})
                assert result=={'content':[{'type':'image','mimeType':'image/png','data':'AAAA'*32768}]}
            pid=connector.process.pid
            records=[json.loads(x) for x in trace.read_text().splitlines()]
            assert len([r for r in records if r['method']==large_method])==1
        finally:
            if connector.process is not None:pid=connector.process.pid
            await connector.close()
            if pid is not None:
                with pytest.raises(ProcessLookupError):os.kill(pid,0)
    asyncio.run(proof())


@pytest.mark.parametrize('overflow',[False,True])
def test_stdio_wire_budget_boundary_and_overflow_never_replays_call(config,overflow):
    import os
    trace=config.parent/'budget-trace.jsonl'
    payload_bytes=C.STDIO_FRAME_LIMIT if overflow else C.STDIO_FRAME_LIMIT-4096
    (config.parent/'fake_mcp.py').write_text('''import json,sys
from pathlib import Path
trace=Path('''+repr(str(trace))+''')
for line in sys.stdin:
 r=json.loads(line)
 if 'id' not in r:continue
 with trace.open('a') as log:log.write(json.dumps(r)+'\\n')
 result={}
 if r['method']=='tools/list':result={'tools':[{'name':'scene_summary','inputSchema':{'type':'object'}}]}
 elif r['method']=='tools/call':result={'content':[{'type':'image','mimeType':'image/png','data':'A'*'''+str(payload_bytes)+'''}]}
 print(json.dumps({'jsonrpc':'2.0','id':r['id'],'result':result}),flush=True)
''')
    async def proof():
        connector=C.Connector(str(config));pid=None
        try:
            await connector.request('tools/list');pid=connector.process.pid
            if overflow:
                with pytest.raises(RuntimeError,match='exceeds the wire-body limit; no automatic tool retry'):
                    await connector.request('tools/call',{'name':'scene_summary','arguments':{}})
                assert connector.process is None  # reaped before fixture cleanup
                with pytest.raises(ProcessLookupError):os.kill(pid,0)
            else:
                result=await connector.request('tools/call',{'name':'scene_summary','arguments':{}})
                assert len(result['content'][0]['data'])==payload_bytes
            records=[json.loads(x) for x in trace.read_text().splitlines()]
            assert len([r for r in records if r['method']=='tools/call'])==1
        finally:
            await connector.close()
            if pid is not None:
                with pytest.raises(ProcessLookupError):os.kill(pid,0)
    asyncio.run(proof())
