# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
import importlib,sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from test_lampway_capabilities_ui import ui,door,press,load,row,Recorder

CID='grok.worker_compat'
def compat_row():
    return row(CID,label='Grok Swarm-Worker compatibility',risk='acts_outside',
        worker_compat={'consent_version':1,'effects_sha256':'11'*32,'warning':'Synthetic exact worker-only view disclosure.',
            'effects':['Worker native view only; MAIN remains native.'],
            'qualification':'Worker execution not qualified.','ready':False,'reason':'qualification required'})

def test_agent_preferences_displays_server_owned_grok_worker_checkbox(ui,door):
    load(compat_row(), project='/synthetic/project')
    layout=Recorder();ui.draw_agent_features(layout)
    assert any(p[4].cap_id==CID for p in layout.ops('lampway.capability_switch'))
    assert any('Grok' in label for label in layout.labels())
    assert door.calls==[]

def test_clicking_grok_checkbox_opens_separate_consent_without_write(ui,door,monkeypatch):
    load(compat_row(),project='/synthetic/project')
    reviews=[]
    from mixar.modules.lampway_tools import ui as package
    fake=SimpleNamespace(review_enable=lambda:reviews.append(True))
    monkeypatch.setitem(sys.modules,'mixar.modules.lampway_tools.ui.grok_worker_compat',fake)
    monkeypatch.setattr(package,'grok_worker_compat',fake,raising=False)
    press(ui.LAMPWAY_OT_capability_switch,cap_id=CID,enabled=True,confirm=False)
    assert reviews==[True] and door.calls==[]

def test_inline_confirmation_cannot_bypass_grok_native_consent(ui,door,monkeypatch):
    from mixar.modules.lampway_tools import capabilities_state as state
    load(compat_row(),project='/synthetic/project');state.STATE['pending']=CID
    reviews=[]
    from mixar.modules.lampway_tools import ui as package
    fake=SimpleNamespace(review_enable=lambda:reviews.append(True))
    monkeypatch.setitem(sys.modules,'mixar.modules.lampway_tools.ui.grok_worker_compat',fake)
    monkeypatch.setattr(package,'grok_worker_compat',fake,raising=False)
    press(ui.LAMPWAY_OT_capability_switch,cap_id=CID,enabled=True,confirm=True)
    assert door.calls==[] and reviews==[True]

@pytest.mark.parametrize('already_selected',[False,True])
def test_every_main_grok_selection_shows_worker_warning_before_existing_launch_notice(monkeypatch,already_selected):
    from mixar.modules.lampway_tools import human_gate
    monkeypatch.setattr(human_gate,'script_running',lambda:False)
    monkeypatch.setattr(sys.modules['bpy.types'],'Operator',object,raising=False)
    name='mixar.modules.space_mixie_chat.ui.operators.agent_mode_ops'
    monkeypatch.delitem(sys.modules,name,raising=False)
    module=importlib.import_module(name)
    plan={'plan':True,'old':'old','new':'new','mode':'byoa','harness':'grok','pane':'pane','name':'Scene'}
    monkeypatch.setattr(module.AM,'prepare',lambda *a:{'ok':True,'unchanged':True} if already_selected else plan)
    monkeypatch.setattr(module,'CLIENT_FACTORY',lambda:SimpleNamespace())
    reviews=[];launches=[]
    from mixar.modules.lampway_tools import ui as package
    fake=SimpleNamespace(review_main=lambda proceed,validate,failed=None:reviews.append((proceed,validate)))
    notice=SimpleNamespace(request=lambda *a:launches.append(a))
    monkeypatch.setitem(sys.modules,'mixar.modules.lampway_tools.ui.grok_worker_compat',fake)
    monkeypatch.setattr(package,'grok_worker_compat',fake,raising=False)
    monkeypatch.setitem(sys.modules,'mixar.modules.lampway_tools.ui.launch_notice',notice)
    monkeypatch.setattr(package,'launch_notice',notice,raising=False)
    op=module.MIXIE_CHAT_OT_agent_mode_set();op.mode='byoa';op.harness='grok';op.report=lambda *a:None
    assert op.execute(SimpleNamespace(scene=SimpleNamespace(name='Scene'))) == {'FINISHED'}
    assert len(reviews)==1 and launches==[]
    reviews[0][0]()
    assert len(launches)==(0 if already_selected else 1)

@pytest.fixture
def consent(monkeypatch):
    from mixar.modules.lampway_tools import ui as package, capabilities_state as state, human_gate
    monkeypatch.setattr(sys.modules['bpy.types'],'Operator',object,raising=False)
    name='mixar.modules.lampway_tools.ui.grok_worker_compat'
    monkeypatch.delitem(sys.modules,name,raising=False)
    module=importlib.import_module(name)
    monkeypatch.setattr(package,'grok_worker_compat',module,raising=False)
    state.reset();load(compat_row(),project='/synthetic/project',project_only=True)
    calls=[]
    class Client:
        def capabilities(self,project):
            calls.append(('read',project));return {'capabilities':[compat_row()]}
        def set_capability(self,cid,**kw):
            calls.append(('write',cid,kw));return dict(compat_row(),enabled=True,in_force=False)
    monkeypatch.setattr(module,'CLIENT_FACTORY',Client)
    monkeypatch.setattr(human_gate,'script_running',lambda:False)
    from mixar.modules.lampway_tools.ui import launch_notice
    monkeypatch.setattr(module,'launch_notice',launch_notice)
    monkeypatch.setattr(launch_notice,'_background',lambda call,done:done(call(),None))
    monkeypatch.setattr(module.bpy.ops.lampway,'grok_worker_compat_review',Mock(return_value={'RUNNING_MODAL'}),raising=False)
    module._PENDING.clear()
    yield module,calls
    module._PENDING.clear();state.reset()


def modal(module):
    ticket=next(iter(module._PENDING))
    operator=module.LAMPWAY_OT_grok_worker_compat_review();operator.ticket=ticket
    operator.report=lambda *a:None
    return operator


def test_grok_cancel_discards_consent_without_config_or_server_write(consent):
    module,calls=consent;module.review_enable();op=modal(module)
    assert calls==[('read','/synthetic/project')]
    op.cancel(None)
    assert not module._PENDING and op.execute(None)=={'CANCELLED'}
    assert calls==[('read','/synthetic/project')]


def test_grok_main_continue_does_not_enable_workers_or_change_routes(consent):
    module,calls=consent;continued=[]
    module.review_main(lambda:continued.append(True),lambda:True)
    op=modal(module);op.layout=Recorder();op.draw(None)
    text=' '.join(op.layout.labels())
    assert 'normal native configuration' in text and 'only Grok swarm workers' in text
    assert 'Synthetic exact worker-only view disclosure.' in text and 'Worker execution not qualified.' in text
    assert 'does not enable a network route' in text
    assert op.execute(None)=={'FINISHED'} and continued==[True]
    assert calls==[('read','/synthetic/project')]


def test_explicit_grok_enable_sends_exact_integer_version_and_captured_scope(consent,monkeypatch):
    module,calls=consent
    from mixar.modules.lampway_tools.ui import capabilities
    monkeypatch.setattr(capabilities,'request_refresh',lambda:None)
    module.review_enable();op=modal(module)
    assert op.execute(None)=={'FINISHED'}
    assert calls==[('read','/synthetic/project'),('write',CID,{'enabled':True,'options':{'consent_version':1,'effects_sha256':'11'*32},'project':'/synthetic/project'})]
    assert op.execute(None)=={'CANCELLED'}, 'Consumed consent cannot be replayed'


@pytest.mark.parametrize('change',['project','scope','version','effects','read_inflight','stale_read','scene'])
def test_grok_stale_consent_refuses_without_write(consent,change):
    module,calls=consent
    from mixar.modules.lampway_tools import capabilities_state as state
    valid=[True]
    module._review('enable',validate=lambda:valid[0]);op=modal(module)
    if change=='project':state.STATE['project']='/synthetic/another'
    elif change=='scope':state.STATE['project_only']=False
    elif change=='version':state.STATE['rows'][0]['worker_compat']['consent_version']=2
    elif change=='effects':state.STATE['rows'][0]['worker_compat']['effects'].append('Changed native view')
    elif change=='read_inflight':state.STATE['inflight']=True
    elif change=='stale_read':state.STATE['ok']=False
    else:valid[0]=False
    assert op.execute(None)=={'CANCELLED'} and len(calls)==1


def test_scripts_cannot_open_or_confirm_grok_consent(consent,monkeypatch):
    module,calls=consent
    module.review_enable();op=modal(module)
    monkeypatch.setattr(module.human_gate,'script_running',lambda:True)
    assert op.execute(None)=={'CANCELLED'} and len(calls)==1
    module.review_enable()
    assert len(calls)==1 and not module._PENDING


@pytest.mark.parametrize('field,value',[('consent_version',True),('consent_version',2),('effects',[]),('warning',''),('ready','true'),('effects_sha256',None),('effects_sha256','AA'*32),('effects_sha256','ab'*31),('effects_sha256','zz'*32)])
def test_malformed_grok_disclosure_never_opens_consent(consent,field,value):
    module,calls=consent
    class Broken:
        def capabilities(self,project):
            r=compat_row();r['worker_compat'][field]=value;return {'capabilities':[r]}
    module.CLIENT_FACTORY=Broken
    module.review_enable()
    assert not module._PENDING and calls==[]
    assert module._ERROR


def test_enable_binds_displayed_digest_against_same_version_server_race(consent,monkeypatch):
    module,_=consent
    from mixar.modules.lampway_tools import capabilities_state as state
    from mixar.modules.lampway_tools.ui import capabilities
    monkeypatch.setattr(capabilities,'request_refresh',lambda:None)
    calls=[]
    displayed='11'*32
    current='22'*32
    class ChangedServer:
        def set_capability(self,cid,**kw):
            calls.append(kw)
            # Reproduce the old version-only server and the new exact-digest refusal.
            if kw['options'].get('effects_sha256') not in (None,current):
                raise RuntimeError('The Grok disclosure changed: review it again')
            return dict(compat_row(),enabled=True)
    module.review_enable();op=modal(module)
    monkeypatch.setattr(module,'CLIENT_FACTORY',ChangedServer)
    def background(call,done):
        try:answer=call()
        except RuntimeError as exc:done(None,str(exc))
        else:done(answer,None)
    monkeypatch.setattr(module.launch_notice,'_background',background)
    assert op.execute(None)=={'FINISHED'}
    assert calls==[{'enabled':True,'options':{'consent_version':1,'effects_sha256':displayed},'project':'/synthetic/project'}]
    assert not state.STATE['rows'][0]['enabled']
    assert 'disclosure changed' in module._ERROR
