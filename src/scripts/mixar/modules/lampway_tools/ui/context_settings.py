# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Project Context in the existing agent configuration surface; draw reads a cache only."""
import textwrap

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator

from mixar.modules.lampway_tools import capabilities_state, context_client, context_state as state, human_gate

CLIENT_FACTORY = lambda: context_client.ContextClient()  # noqa: E731
# Keep enum strings alive for Blender's dynamic-property lifetime.
_CHOICE_ITEMS = []
_DEFAULT_CHOICE = '__hermes_default__'


def _choice_items(self, context):
    return _CHOICE_ITEMS


FIELDS = {'context_engine': 'Context engine', 'compression_threshold': 'Compression threshold',
          'protected_recent_turns': 'Protected recent messages', 'summarizing_model': 'Summarising model'}


def _redraw():
    for window in getattr(bpy.context.window_manager, 'windows', []) or []:
        for area in window.screen.areas:
            area.tag_redraw()


def _apply():
    if state.take():
        _redraw()
    return 0.2 if state.STATE['inflight'] else None


def _request(values=None, reset_keys=None):
    project = capabilities_state.STATE['project']
    started = state.request(CLIENT_FACTORY, project, values=values, reset_keys=reset_keys)
    if started and not bpy.app.background and not bpy.app.timers.is_registered(_apply):
        bpy.app.timers.register(_apply, first_interval=0.2)
    _redraw()
    return started


def request_refresh():
    return _request()


def _ready():
    answer = state.STATE['answer']
    if state.STATE['inflight']:
        return 'Context request is still running: wait for it to finish'
    if not answer or state.STATE['project'] != capabilities_state.STATE['project']:
        return 'Refresh Context before editing this project'
    if answer.get('busy'):
        return 'The agent is busy: wait for the turn to finish before changing Context'
    return ''


class LAMPWAY_OT_context_refresh(Operator):
    """Read this project's Hermes context settings without blocking the UI"""
    bl_idname = 'lampway.context_refresh'
    bl_label = 'Refresh Context'
    bl_options = {'INTERNAL'}

    def execute(self, context):
        request_refresh()
        return {'FINISHED'}


class LAMPWAY_OT_context_edit(Operator):
    """Explicitly change one Hermes setting for this project at the native runtime boundary"""
    bl_idname = 'lampway.context_edit'
    bl_label = 'Edit Context setting'
    bl_options = {'INTERNAL'}
    key: StringProperty(options={'SKIP_SAVE'})
    value: StringProperty(name='Value', options={'SKIP_SAVE'})
    choice: EnumProperty(name='Choice', items=_choice_items, options={'SKIP_SAVE'})
    project: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        if human_gate.script_running():
            self.report({'ERROR'}, "this is the user's click: a script cannot press it")
            return {'CANCELLED'}
        error = _ready()
        if error or self.key not in FIELDS:
            self.report({'ERROR'}, error or 'Unknown Context setting')
            return {'CANCELLED'}
        self.project = capabilities_state.STATE['project']
        answer = state.STATE['answer']
        self.value = str(answer['effective'][self.key])
        if self.key in {'context_engine', 'summarizing_model'}:
            names = answer['engine_choices' if self.key == 'context_engine' else 'summarizing_model_choices']
            values = list(dict.fromkeys(names))
            if self.key == 'summarizing_model' and answer['defaults'][self.key] == '':
                values.insert(0, '')
            _CHOICE_ITEMS[:] = [(value or _DEFAULT_CHOICE, _shown(value), _shown(value)) for value in values]
            self.choice = self.value or _DEFAULT_CHOICE
        return context.window_manager.invoke_props_dialog(self, width=440)

    def draw(self, context):
        self.layout.label(text=FIELDS.get(self.key, 'Context'))
        self.layout.prop(self, 'choice' if self.key in {'context_engine', 'summarizing_model'} else 'value')
        if self.key == 'protected_recent_turns':
            self.layout.label(text='Hermes counts recent messages, including tool messages')
        self.layout.label(text='Save changes only this setting for this project')

    def execute(self, context):
        if human_gate.script_running():
            self.report({'ERROR'}, "this is the user's click: a script cannot press it")
            return {'CANCELLED'}
        if getattr(self, 'project', '') != capabilities_state.STATE['project']:
            self.report({'ERROR'}, 'The project changed: close this edit and Refresh Context')
            return {'CANCELLED'}
        error = _ready()
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        try:
            answer = state.STATE['answer']
            if self.key == 'compression_threshold':
                value = float(self.value)
                if not 0 < value <= 1:
                    raise ValueError('Compression threshold must be greater than 0 and at most 1')
            elif self.key == 'protected_recent_turns':
                value = int(self.value)
                if value < 0:
                    raise ValueError('Protected recent messages must be at least 0')
            elif self.key == 'context_engine':
                value = self.choice
                if value not in answer['engine_choices']:
                    raise ValueError('Choose an installed engine: ' + ', '.join(answer['engine_choices']))
            elif self.key == 'summarizing_model':
                value = '' if self.choice == _DEFAULT_CHOICE else self.choice
                if value == '' and answer['defaults'][self.key] != '':
                    raise ValueError('This server has no automatic summarising model choice')
                if value and value not in answer['summarizing_model_choices']:
                    raise ValueError('Choose a server-listed summarising model: ' + ', '.join(answer['summarizing_model_choices']))
            else:
                raise ValueError('Unknown Context setting')
        except (ValueError, KeyError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        return {'FINISHED'} if _request(values={self.key: value}) else {'CANCELLED'}


class LAMPWAY_OT_context_reset(Operator):
    """Remove an explicit project override and return to the displayed Hermes default"""
    bl_idname = 'lampway.context_reset'
    bl_label = 'Use Hermes default'
    bl_options = {'INTERNAL'}
    key: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        if human_gate.script_running():
            self.report({'ERROR'}, "this is the user's click: a script cannot press it")
            return {'CANCELLED'}
        error = _ready()
        if error or self.key not in FIELDS:
            self.report({'ERROR'}, error or 'Unknown Context setting')
            return {'CANCELLED'}
        return {'FINISHED'} if _request(reset_keys=[self.key]) else {'CANCELLED'}


def _shown(value):
    return str(value) if value != '' else 'Automatic (Hermes default)'


def _note(layout, text, icon='NONE'):
    for index, line in enumerate(textwrap.wrap(text, width=64) or ['']):
        layout.label(text=line, icon=icon if index == 0 else 'NONE')


def draw_context(layout, context=None):
    box = layout.box()
    top = box.row()
    top.label(text='Context')
    top.operator('lampway.context_refresh', text='Refresh', icon='FILE_REFRESH')
    box.label(text='Hermes runtime settings for this project')
    st = state.STATE
    if st['error']:
        _note(box, st['error'], icon='ERROR')
    if st['inflight']:
        box.label(text='Saving Context...' if st['operation'] == 'save' else 'Reading Context...')
    answer = st['answer'] if st['project'] == capabilities_state.STATE['project'] else None
    if not answer:
        box.label(text='Open a Lampway project and Refresh Context to read its defaults')
        return
    window = answer['model_window']
    tokens = str(window['tokens']) + ' tokens' if window['tokens'] is not None else 'Unknown'
    box.label(text=f"Model window: {tokens} (source: {window['source']})")
    if answer.get('defaults_source'):
        _note(box, 'Defaults source: ' + answer['defaults_source'])
    if answer.get('apply_note'):
        _note(box, answer['apply_note'])
    if answer.get('busy'):
        box.label(text='Agent busy: wait for the turn to finish', icon='ERROR')
    if answer.get('summarizing_model_note'):
        _note(box, answer['summarizing_model_note'])
    for key, label in FIELDS.items():
        row = box.row()
        row.label(text=label + ': ' + _shown(answer['effective'][key]))
        row.label(text='Project override' if key in answer['overrides'] else 'Hermes default')
        controls = box.row(align=True)
        controls.enabled = not st['inflight'] and not answer.get('busy') and not st['error']
        controls.operator('lampway.context_edit', text='Edit').key = key
        if key in answer['overrides']:
            controls.operator('lampway.context_reset', text='Use Hermes default').key = key
        box.label(text='Hermes default: ' + _shown(answer['defaults'][key]))
        if key == 'context_engine':
            box.label(text='Installed engines: ' + ', '.join(answer['engine_choices']))
        if key == 'summarizing_model':
            _note(box, 'Summarising choices: ' + ', '.join(answer['summarizing_model_choices']))
        if key == 'compression_threshold' and answer.get('threshold_note'):
            _note(box, answer['threshold_note'])


classes = (LAMPWAY_OT_context_refresh, LAMPWAY_OT_context_edit, LAMPWAY_OT_context_reset)
