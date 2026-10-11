# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-2.0-or-later
"""Model native outside-click consumption while another field keeps editing."""
from types import SimpleNamespace
import pytest
from mixar.modules.common.ui_control.core import input as native_input


@pytest.mark.parametrize('initial', ['other', None, 'target'])
@pytest.mark.parametrize('replacement', ['helmet-suite.mixar', 'héłmet.mixar', ''])
def test_replacement_focuses_target_after_prior_editor_consumes_first_press(monkeypatch, initial, replacement):
    state={'active':initial,'text':'Untitled.mixar','selected':False,'committed':None}
    item={'type':'Text','rect':[0,0,100,20],'_win':SimpleNamespace(cursor_warp=lambda *args:None)}
    monkeypatch.setattr(native_input.observe,'resolve',lambda *args:item)
    monkeypatch.setattr(native_input,'point',lambda item:(50,10))
    monkeypatch.setattr(native_input.ownership,'begin',lambda owner:None)
    monkeypatch.setattr(native_input.ownership,'check',lambda owner:None)
    monkeypatch.setattr(native_input,'bpy',SimpleNamespace(context=SimpleNamespace(window_manager=SimpleNamespace(mixar_ui_pending=lambda:0))))
    def event(owner,item,key,value,xy,mods=None,text=''):
        if value!='PRESS':return
        if key=='LEFTMOUSE':
            # Native do_but_textedit consumes the outside press on the old
            # editor. It does not transfer that press to the new text field.
            state['active']=None if state['active']=='other' else 'target'
        elif state['active']=='target':
            if key=='A' and (mods or {}).get('ctrl'):
                state['selected']=True
            elif key=='BACK_SPACE':
                state['text']='';state['selected']=False
            elif key=='A' and text:
                state['text']=('' if state['selected'] else state['text'])+text
                state['selected']=False
            elif key=='RET':
                state['committed']=state['text']
        elif key=='RET':
            state['committed']='wrong-default.mixar'
    monkeypatch.setattr(native_input,'event',event)
    list(native_input.run('owned',{'context':'fresh','target':'filename','action':'set_text','text':replacement,'enter':True}))
    assert state['committed']==replacement


def test_search_and_numeric_controls_keep_single_activation(monkeypatch):
    for kind in ('SearchMenu','Num','NumSlider'):
        events=[]
        item={'type':kind,'rect':[0,0,100,20],'_win':SimpleNamespace(cursor_warp=lambda *args:None)}
        monkeypatch.setattr(native_input.observe,'resolve',lambda *args:item)
        monkeypatch.setattr(native_input,'point',lambda item:(50,10))
        monkeypatch.setattr(native_input.ownership,'begin',lambda owner:None)
        monkeypatch.setattr(native_input,'bpy',SimpleNamespace(context=SimpleNamespace(window_manager=SimpleNamespace(mixar_ui_pending=lambda:0))))
        monkeypatch.setattr(native_input,'event',lambda *args,**kwargs:events.append(args[2:4]))
        list(native_input.run('owned',{'context':'fresh','target':'field','action':'set_text','text':'1','enter':True}))
        assert events.count(('LEFTMOUSE','PRESS'))==1
