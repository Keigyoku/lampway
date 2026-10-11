# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Human-consented Grok worker compatibility; pure mocked authority and admission controls."""
import pytest
from lampway_server import capabilities as C
from lampway_server.herdr import harnesses as H
from lampway_server import native_worker_readiness as N

KEY = 'grok.worker_compat'

def test_url_transport_disclosure_invalidates_pre_deny_consent(tmp_path, monkeypatch):
    from lampway_server import grok_worker as G
    effect = ('Inside Grok swarm workers, remote MCP connectors using HTTP or SSE are denied. '
              'The native STDIO lampway_pane connector is retained; this restriction does not '
              'disable model access or built-in network tools and does not establish worker readiness.')
    current = G.COMPAT_EFFECTS
    prior = tuple(row for row in current if row != effect)
    store = C.Store(tmp_path / 'state')
    with monkeypatch.context() as old:
        old.setattr(G, 'COMPAT_EFFECTS', prior)
        displayed = C.grok_compat_disclosure()
        store.set(KEY, enabled=True, options={
            'consent_version': displayed['consent_version'],
            'effects_sha256': displayed['effects_sha256']}, project='/project')
        assert store.effective(KEY, '/project') == (True, '')
    assert not C.Store(store.state_dir).effective(KEY, '/project')[0]
    updated = C.grok_compat_disclosure()
    assert effect in updated['effects']
    assert updated['consent_version'] == displayed['consent_version'] == 1
    assert updated['effects_sha256'] != displayed['effects_sha256']
    with pytest.raises(C.Refused):
        store.set(KEY, enabled=True, options={
            'consent_version': 1, 'effects_sha256': displayed['effects_sha256']}, project='/project')
    store.set(KEY, enabled=True, options={
        'consent_version': 1, 'effects_sha256': updated['effects_sha256']}, project='/project')
    assert C.Store(store.state_dir).effective(KEY, '/project') == (True, '')

def test_default_off_disclosure(tmp_path):
    store = C.Store(tmp_path)
    row = next((row for row in store.view('/project') if row['id'] == KEY), None)
    assert row is not None, 'Grok worker compatibility must have an explicit default-off human consent row'
    assert not row['enabled'] and not row['default']
    assert row['worker_compat']['consent_version'] == 1
    assert not row['worker_compat']['ready']

def test_off_precedes_native_qualification(tmp_path, monkeypatch):
    monkeypatch.setattr(C, 'ACTIVE', C.Store(tmp_path))
    class Adapter:
        id='grok'; direct_ok=True; worker_ok=True
        worker_note='unproved'; tools_note=''
        def worker_compatibility_note(self, **kwargs):
            pytest.fail('OFF must refuse before native qualification')
    assert 'off' in H.worker_problem(Adapter(), project='/project')

def test_readiness_off_precedes_probe(tmp_path, monkeypatch):
    monkeypatch.setattr(C, 'ACTIVE', C.Store(tmp_path))
    monkeypatch.setattr(N.L, 'worker_probe', lambda *a, **k: pytest.fail('OFF must not probe'))
    with pytest.raises(ValueError, match='off'):
        N.grok_worker_description('/fake/grok', project='/project')

@pytest.fixture
def enrolled(tmp_path, monkeypatch):
    from lampway_server import grok_worker as G
    monkeypatch.setattr(G, 'COMPAT_VERSION', 1, raising=False)
    monkeypatch.setattr(G, 'COMPAT_EFFECTS', ('synthetic exact worker-only effect',), raising=False)
    store=C.Store(tmp_path/'state')
    monkeypatch.setattr(C, 'ACTIVE', store)
    return store

@pytest.mark.parametrize('enabled,options', [(True,None),(True,{}),(True,{'consent_version':True}),(True,{'consent_version':2}),('yes',{'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']}),(True,{'consent_version':1,'extra':True})])
def test_no_enable_without_exact_explicit_consent(enrolled,enabled,options):
    with pytest.raises(C.Refused):
        enrolled.set(KEY,enabled=enabled,options=options,project='/project')
    assert not enrolled._path.exists()

def test_persisted_project_consent_and_off_reenable(enrolled):
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},project='/project')
    assert C.Store(enrolled.state_dir).effective(KEY,'/project') == (True,'')
    assert not enrolled.effective(KEY,'/other')[0]
    assert not enrolled.effective(KEY)[0]
    enrolled.set(KEY,enabled=False,project='/project')
    assert not enrolled.effective(KEY,'/project')[0]
    with pytest.raises(C.Refused): enrolled.set(KEY,enabled=True,project='/project')
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},project='/project')
    enrolled.clear(KEY,'/project')
    assert not enrolled.effective(KEY,'/project')[0]

def test_effect_change_invalidates_consent(enrolled,monkeypatch):
    from lampway_server import grok_worker as G
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},project='/project')
    monkeypatch.setattr(G,'COMPAT_EFFECTS',('changed exact effect',))
    assert not enrolled.effective(KEY,'/project')[0]

def test_agent_and_proposal_cannot_record_consent(enrolled):
    with pytest.raises(C.Refused): enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},by='agent')
    pid=enrolled.propose('agent',KEY,{'enabled':True,'options':{'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']}},'please enable')
    with pytest.raises(C.Refused): enrolled.decide(pid,'accept')
    assert not enrolled.effective(KEY)[0]
    assert enrolled.proposals()[0]['state']=='open'

def test_enrollment_does_not_qualify_native(enrolled):
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},project='/project')
    assert H.get('grok').worker_ok is False
    assert H.worker_problem(H.get('grok'),project='/project') == H.get('grok').worker_note

def test_qualified_test_adapter_receives_exact_project(enrolled):
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},project='/project')
    seen=[]
    class Adapter:
        id='grok'; direct_ok=True; worker_ok=True; worker_note=''; tools_note=''
        def worker_compatibility_note(self,**kwargs): seen.append(kwargs); return ''
    assert H.worker_problem(Adapter(),project='/project')==''
    assert seen==[{'project':'/project'}]
    assert 'off' in H.worker_problem(Adapter(),project='/other')

def test_off_worker_adapter_before_locate_and_main_unchanged(enrolled,monkeypatch):
    from lampway_server.herdr.harnesses.base import PaneSpec
    adapter=H.get('grok')
    monkeypatch.setattr(adapter,'locate',lambda:pytest.fail('OFF must not locate native binary'))
    with pytest.raises(ValueError,match='off'): adapter.lampway_tools(PaneSpec(cwd='/project/sub',project_root='/project',desktop=False))
    assert adapter.launch(PaneSpec(cwd='/project',session_id='normal-id')) == ['grok','--session-id','normal-id']

def test_runtime_persisted_consent_helper(enrolled):
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},project='/project')
    assert C.grok_worker_problem('/project',state_dir=enrolled.state_dir)==''
    enrolled.set(KEY,enabled=False,project='/project')
    assert 'off' in C.grok_worker_problem('/project',state_dir=enrolled.state_dir)

@pytest.mark.parametrize('origin',['agent','mcp'])
def test_authenticated_nonhuman_routes_refuse_mutation(enrolled,origin):
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    from lampway_server.capabilities.routes import capabilities_routes
    app=Starlette(routes=capabilities_routes(lambda r:True,lambda r:origin))
    with TestClient(app) as client:
        response=client.put('/app/capabilities/'+KEY,json={'enabled':True,'options':{'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},'project':'/project'})
    assert response.status_code==403
    assert not enrolled._path.exists()

def test_human_route_persists_exact_version_disclosure(enrolled):
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    from lampway_server.capabilities.routes import capabilities_routes
    app=Starlette(routes=capabilities_routes(lambda r:True,lambda r:'user'))
    with TestClient(app) as client:
        response=client.put('/app/capabilities/'+KEY,json={'enabled':True,'options':{'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},'project':'/project'})
    assert response.status_code==200
    assert response.json()['worker_compat']['effects']==['synthetic exact worker-only effect']
    assert response.json()['in_force']

def test_current_owned_worker_call_refuses_after_off_allow_done(enrolled):
    import asyncio
    asyncio.run(_current_owned_worker_call(enrolled))

async def _current_owned_worker_call(enrolled):
    from types import SimpleNamespace as S
    from lampway_server.mcp import McpServer
    from lampway_server.herdr.swarm_brain import WORKER_DONE
    calls=[]
    async def call(name,args): calls.append(name); return 'ok',False
    job=S(meta={'worker_harness':'grok','worker_project_root':'/project'},call_tool=call)
    binding=S(job=job,live=True,name='swarm:s:w',state='active')
    server=object.__new__(McpServer)
    server.workers=S(finish=lambda binding,summary:calls.append('done'))
    specs=[S(name='scene_summary'),WORKER_DONE]
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},project='/project')
    assert await server._worker_call(binding,'scene_summary',{},specs)==('ok',False)
    enrolled.set(KEY,enabled=False,project='/project')
    text,error=await server._worker_call(binding,'scene_summary',{},specs)
    assert error and 'off' in text and calls==['scene_summary']
    assert (await server._worker_call(binding,WORKER_DONE.name,{'summary':'made mesh'},specs))[1] is False
    assert calls==['scene_summary','done']

def test_worker_metadata_uses_exact_project_scope_not_cwd(enrolled,monkeypatch,tmp_path):
    import json
    from lampway_server.herdr.harnesses.grok import Grok
    from lampway_server.herdr.harnesses.base import PaneSpec,DirectServer
    project=tmp_path/'project'; project.mkdir(); cwd=project/'sub'; cwd.mkdir()
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},project=str(project))
    adapter=Grok(); adapter.worker_ok=True
    monkeypatch.setattr(adapter,'locate',lambda:'/synthetic/grok')
    calls=[]
    monkeypatch.setattr(N,'grok_worker_description',lambda binary,**kwargs:(calls.append(kwargs) or {'native':binary}))
    path=str(tmp_path/'panes'/'worker'/'mcp.json')
    pane=PaneSpec(cwd=str(cwd),project_root=str(project),desktop=False,mcp_config_path=path,
                  direct=(DirectServer('lampway','http://127.0.0.1/mcp',{'X-Mixar-Session-Id':'swarm:s:w'},'LAMPWAY_SWARM_TOKEN','synthetic'),))
    wiring=adapter.lampway_tools(pane)
    meta=json.loads(wiring.files[str(tmp_path/'panes'/'worker'/'grok-worker.json')])
    assert calls==[{'cwd':str(cwd),'project':str(project)}]
    assert meta['compat_view']=={'version':1,'home':str(__import__('pathlib').Path.home()),'project_root':str(project),'state_dir':str(enrolled.state_dir)}
    assert not (tmp_path/'panes').exists(), 'Adapter only describes owned files; no writes/native launches'

def test_off_during_qualification_emits_no_metadata(enrolled,monkeypatch,tmp_path):
    from lampway_server.herdr.harnesses.grok import Grok
    from lampway_server.herdr.harnesses.base import PaneSpec,DirectServer
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},project='/project')
    adapter=Grok(); adapter.worker_ok=True
    monkeypatch.setattr(adapter,'locate',lambda:'/synthetic/grok')
    def qualification(*args,**kwargs):
        enrolled.set(KEY,enabled=False,project='/project')
        return {'native':'/synthetic/grok'}
    monkeypatch.setattr(N,'grok_worker_description',qualification)
    pane=PaneSpec(cwd='/project',project_root='/project',desktop=False,mcp_config_path=str(tmp_path/'panes'/'w'/'mcp.json'),
        direct=(DirectServer('lampway','http://127.0.0.1/mcp',{'X-Mixar-Session-Id':'swarm:s:w'},'LAMPWAY_SWARM_TOKEN','synthetic'),))
    with pytest.raises(ValueError,match='off'):adapter.lampway_tools(pane)
    assert not (tmp_path/'panes').exists()

def test_host_off_precedes_local_server_probe(enrolled,monkeypatch,tmp_path):
    from lampway_server.herdr import host
    monkeypatch.setattr(host.EG,'preflight',lambda route:None)
    monkeypatch.setattr(host.L,'server_status',lambda *args:pytest.fail('OFF must precede local/native probes'))
    cockpit=object.__new__(host.Cockpit)
    cockpit.project_root=str(tmp_path); cockpit.root=str(tmp_path/'owned')
    with pytest.raises(host.CockpitError,match='off'):
        cockpit.create_session('grok','worker proof',str(tmp_path),by='swarm',project_root=str(tmp_path),swarm_worker=('swarm:s:w','synthetic'))
    assert not (tmp_path/'owned').exists()

def test_choices_world_passes_job_project_to_readiness(monkeypatch):
    from lampway_server import choices as CH
    from lampway_server.choices import snapshot as S
    seen=[]
    monkeypatch.setattr(CH,'WORLD_FACTORY',None)
    monkeypatch.setattr(S,'live_world',lambda **kwargs:seen.append(kwargs) or 'world')
    assert CH.world('/project')=='world'
    assert seen==[{'project':'/project'}]

def test_real_disclosure_matches_native_effect_digest():
    from lampway_server import grok_worker as G
    disclosure=C.grok_compat_disclosure()
    assert disclosure['effects']==list(G.COMPAT_EFFECTS)
    assert disclosure['effects_sha256']==G.COMPAT_EFFECTS_SHA256
    assert any('HOME directory identity changes' in effect for effect in disclosure['effects'])
    assert any('cannot create or remove immediate HOME names' in effect for effect in disclosure['effects'])
    assert any('new immediate ~/.cursor names' in effect for effect in disclosure['effects'])

@pytest.mark.parametrize('headers',[{'X-Lampway-Origin':'agent'},{'Origin':'https://foreign.example'}])
def test_human_auth_with_nonhuman_headers_refuses(enrolled,headers):
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    from lampway_server.capabilities.routes import capabilities_routes
    with TestClient(Starlette(routes=capabilities_routes(lambda r:True,lambda r:'user'))) as client:
        response=client.put('/app/capabilities/'+KEY,json={'enabled':True,'options':{'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']}},headers=headers)
    assert response.status_code==403 and not enrolled._path.exists()

def test_global_consent_project_off_override_clear(enrolled):
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']})
    assert enrolled.effective(KEY,'/other')[0]
    enrolled.set(KEY,enabled=False,project='/project')
    assert not enrolled.effective(KEY,'/project')[0]
    enrolled.clear(KEY,'/project')
    assert enrolled.effective(KEY,'/project')[0]
    assert enrolled.setting(KEY,'/project')['scope']=='global'

def test_main_wiring_has_no_compat_config_or_environment(enrolled,tmp_path):
    import json
    from lampway_server.herdr.harnesses.grok import Grok
    from lampway_server.herdr.harnesses.base import PaneSpec
    path=str(tmp_path/'panes'/'main'/'mcp.json')
    wiring=Grok().lampway_tools(PaneSpec(cwd=str(tmp_path),mcp_config_path=path,scene_session_id='scene',launcher=('/symbolic','helper')))
    assert set(wiring.files)=={path}
    assert 'compat_view' not in json.loads(wiring.files[path])
    assert not any(key.startswith('GROK_') or key=='HOME' for key in wiring.env)
    assert not (tmp_path/'panes').exists()

def test_same_version_stale_displayed_effect_digest_refuses(enrolled,monkeypatch):
    displayed=C.grok_compat_disclosure()
    from lampway_server import grok_worker as G
    monkeypatch.setattr(G,'COMPAT_EFFECTS',tuple(displayed['effects'])+('new same-version effect',))
    # Captured old descriptor must never be replaced by unseen current server effects.
    with pytest.raises(C.Refused):
        enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':displayed['effects_sha256']},project='/project')
    assert not enrolled._path.exists()
    updated=C.grok_compat_disclosure()
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':updated['effects_sha256']},project='/project')
    assert enrolled.effective(KEY,'/project')[0]

def test_version_only_cannot_consent_to_unseen_same_version_effects(enrolled,monkeypatch):
    from lampway_server import grok_worker as G
    displayed=C.grok_compat_disclosure()
    monkeypatch.setattr(G,'COMPAT_EFFECTS',tuple(displayed['effects'])+('unseen changed effect',))
    with pytest.raises(C.Refused):
        enrolled.set(KEY,enabled=True,options={'consent_version':displayed['consent_version']},project='/project')
    assert not enrolled._path.exists()


def test_disclosure_support_tracks_accepted_adapter_constant_without_probe(monkeypatch):
    adapter=H.get('grok')
    monkeypatch.setattr(adapter,'worker_ok',True)  # Test-only acceptance witness, no production promotion.
    monkeypatch.setattr(adapter,'locate',lambda:pytest.fail('Disclosure must not probe'))
    monkeypatch.setattr(N.L,'worker_probe',lambda *a,**k:pytest.fail('Disclosure must not probe'))
    assert C.grok_compat_disclosure()['ready'] is True

def test_http_stale_disclosure_refuses_before_persistence(enrolled,monkeypatch):
    from starlette.applications import Starlette
    from starlette.testclient import TestClient
    from lampway_server.capabilities.routes import capabilities_routes
    from lampway_server import grok_worker as G
    displayed=C.grok_compat_disclosure()
    monkeypatch.setattr(G,'COMPAT_EFFECTS',tuple(displayed['effects'])+('new same-version exact effect',))
    with TestClient(Starlette(routes=capabilities_routes(lambda r:True,lambda r:'user'))) as client:
        response=client.put('/app/capabilities/'+KEY,json={'enabled':True,'options':{
            'consent_version':displayed['consent_version'],'effects_sha256':displayed['effects_sha256']},'project':'/project'})
    assert response.status_code==400
    assert 'Agent preferences' in response.json()['detail']
    assert not enrolled._path.exists()

def test_unsupported_consented_home_refuses_before_native_lookup(enrolled,monkeypatch):
    from lampway_server import grok_worker as G
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},project='/project')
    monkeypatch.setattr(G,'compat_preflight',lambda *args:(_ for _ in ()).throw(ValueError('unsupported HOME view')),raising=False)
    monkeypatch.setattr(G,'candidate_paths',lambda *args:pytest.fail('Unsupported consented HOME must refuse before native lookup/probes'))
    with pytest.raises(ValueError,match='unsupported HOME view'):
        N.grok_worker_description('/synthetic/grok',cwd='/project',project='/project')

def test_actual_unsupported_cursor_layout_refuses_before_probe(enrolled,monkeypatch,tmp_path):
    from lampway_server import grok_worker as G
    home=tmp_path/'native-home'; home.mkdir(); foreign=tmp_path/'redirect'; foreign.mkdir()
    (home/'.cursor').symlink_to(foreign,target_is_directory=True)
    monkeypatch.setenv('HOME',str(home))
    enrolled.set(KEY,enabled=True,options={'consent_version':1,'effects_sha256':C.grok_compat_disclosure()['effects_sha256']},project=str(tmp_path))
    monkeypatch.setattr(G,'candidate_paths',lambda *args:pytest.fail('Unsupported layout reached native lookup'))
    with pytest.raises(ValueError,match='never a redirect'):
        N.grok_worker_description('/synthetic/grok',cwd=str(tmp_path),project=str(tmp_path))
    assert (home/'.cursor').is_symlink() and list(foreign.iterdir())==[]
