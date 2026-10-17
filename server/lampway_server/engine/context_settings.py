# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit per-project Hermes Context overrides, no second context budget.

Defaults transcribed from the read-only v2026.9.24 config_defaults.py (compression,
context.engine, auxiliary.compression). No default is written to a pane. The pin
adopts compression edits on the live agent before each normal turn and reads
auxiliary compression routing per call. Only the already installed compressor
engine is selectable. No cold resume, process restart or history copying occurs.
Status checks refuse observed busy sessions; a concurrent turn start is safe
because whole config files are atomically replaced and Hermes owns adoption.

Named summary selections resolve on the explicitly selected service, with no new
Choices purpose, grant or fallback. Only their exact project-bound wire alias
can select the alternate model at the existing guarded gateway.
"""
from __future__ import annotations

import math
import copy
import hashlib
import re
from pathlib import Path

from starlette.responses import JSONResponse
from starlette.routing import Route

from ..connections import files as CF

DEFAULTS = {'compression_threshold': .50, 'protected_recent_turns': 20,
            'context_engine': 'compressor', 'summarizing_model': ''}
FIELDS = frozenset(DEFAULTS)
SUMMARY_PREFIX = 'lampway-summary-'
MODEL_ALIAS = 'lampway'  # engine.wiring.MODEL_ID; its existing gateway routes the selected service


class Refused(ValueError):
    pass


def project_key(project):
    if not isinstance(project, str) or not project.strip() or not Path(project).is_absolute():
        raise Refused('Context requires an absolute project root')
    return str(Path(project).resolve())


def validate(values, *, allow_wire_alias=False):
    if not isinstance(values, dict) or set(values) - FIELDS:
        raise Refused('Only the four Hermes Context fields can be edited')
    for key, value in values.items():
        if key == 'compression_threshold':
            if type(value) not in (int, float) or not 0 < value <= 1 or not math.isfinite(value):
                raise Refused('Compression threshold must be a finite ratio greater than zero and at most one')
        elif key == 'protected_recent_turns':
            if type(value) is not int or value < 0:
                raise Refused('Protected recent messages must be a nonnegative integer')
        elif key == 'context_engine' and value != 'compressor':
            raise Refused('Only the installed Hermes compressor is available')
        elif key == 'summarizing_model':
            if not isinstance(value, str):
                raise Refused('The summarizing model must be an explicit Choices model name')
            if allow_wire_alias and re.fullmatch(SUMMARY_PREFIX + r'[0-9a-f]{16}', value):
                continue
            if value not in ('', MODEL_ALIAS):
                from ..choices import registry as REG
                if not re.fullmatch(r'[A-Za-z0-9_./:-]+', value) or '*' in value or not REG.offers(REG.get('agent.main'), 'openai:local' if value.startswith('openai:') else value):
                    raise Refused('The summarizing model must be an existing agent.main Choices option')
    return dict(values)


class Store:
    def __init__(self, state_dir):
        self.path = Path(state_dir) / 'agent_context.json'

    def read(self, project):
        doc = CF.read_json(self.path)
        if not isinstance(doc, dict):
            raise Refused('The Context settings file is not a project mapping')
        raw = doc.get(project_key(project), {})
        if not isinstance(raw, dict):
            raise Refused('The Context project entry is not a settings mapping')
        entry = dict(raw)
        entry.pop('_summary_service', None)
        return validate(entry)

    def updated(self, project, values, reset, summary_service=None):
        key = project_key(project)
        values = validate(values)
        if not isinstance(reset, list) or any(not isinstance(k, str) or k not in FIELDS for k in reset):
            raise Refused('Reset must list Hermes Context field names')
        doc = CF.read_json(self.path)
        raw = doc.get(key, {})
        if not isinstance(raw, dict):
            raise Refused('The Context project entry is not a settings mapping')
        entry = dict(raw)
        previous_service = entry.pop('_summary_service', None)
        chosen = validate(entry)
        for field in reset:
            chosen.pop(field, None)
        chosen.update(values)
        if chosen:
            doc[key] = dict(chosen)
            selection = chosen.get('summarizing_model')
            if selection and selection != MODEL_ALIAS:
                service = summary_service if 'summarizing_model' in values else previous_service
                if not isinstance(service, dict):
                    raise Refused('A named summarizer requires the selected service to be recorded by your Client save')
                doc[key]['_summary_service'] = service
        else:
            doc.pop(key, None)
        return doc, chosen

    def update(self, project, values, reset, summary_service=None):
        with CF.locked(self.path.with_suffix('.lock')):
            doc, chosen = self.updated(project, values, reset, summary_service)
            CF.atomic_write_json(self.path, doc)
        return chosen

    def apply(self, project, values, reset, summary_service, records):
        """All reads/validation before writes; own files atomically replaced, rollback on failure."""
        from . import hermes_config as HC
        with HC.CONFIG_WRITER_LOCK, CF.locked(self.path.with_suffix('.lock')):
            existed = self.path.exists()
            old_doc = CF.read_json(self.path)
            doc, chosen = self.updated(project, values, reset, summary_service)
            configs = []
            for rec in records:
                home = Path(rec.get('home') or '')
                if not rec.get('home'):
                    raise Refused('The live pane has no owned Hermes config')
                original = (home / 'config.yaml').read_text(encoding='utf-8')
                cfg = HC.from_yaml(original)
                for root, sub in (('compression', 'threshold'), ('compression', 'protect_last_n'),
                                  ('context', 'engine')):
                    if isinstance(cfg.get(root), dict):
                        cfg[root].pop(sub, None)
                        if not cfg[root]:
                            cfg.pop(root)
                auxiliary = cfg.get('auxiliary', {})
                if isinstance(auxiliary.get('compression'), dict):
                    auxiliary['compression'].pop('model', None)
                    if not auxiliary['compression']:
                        auxiliary.pop('compression')
                HC._merge_context(cfg, config_values(chosen))
                configs.append((home, original, HC.to_yaml(cfg)))
            written = []
            try:
                CF.atomic_write_json(self.path, doc)
                for home, original, rendered in configs:
                    HC._write_private(home, 'config.yaml', rendered)
                    written.append((home, original))
            except Exception:
                for home, original in reversed(written):
                    HC._write_private(home, 'config.yaml', original)
                if existed:
                    CF.atomic_write_json(self.path, old_doc)
                else:
                    self.path.unlink(missing_ok=True)
                raise
        return chosen

    def config(self, project):
        """Only explicit settings, mapped to the actual pinned Hermes schema."""
        return config_values(self.read(project) if project else {})


def config_values(values):
    out = {}
    for field, key in (('compression_threshold', 'threshold'), ('protected_recent_turns', 'protect_last_n')):
        if field in values:
            out.setdefault('compression', {})[key] = values[field]
    if 'context_engine' in values:
        out['context'] = {'engine': values['context_engine']}
    if 'summarizing_model' in values:
        selection = values['summarizing_model']
        out['auxiliary'] = {'compression': {'model': summary_alias(selection) if selection and selection != MODEL_ALIAS else selection}}
    return out


def view(store, project, provider, live=False):
    chosen = store.read(project)
    window = getattr(provider, 'context_length', None)
    known = type(window) is int and window > 0
    return {'project': project_key(project), 'defaults': dict(DEFAULTS), 'overrides': chosen,
            'effective': {**DEFAULTS, **chosen}, 'model_window': {'tokens': window if known else None,
            'source': 'provider' if known else 'unknown'}, 'busy': None if live else False, 'live_pane': live,
            'live_reload_supported': True, 'apply_at': 'native_turn_boundary', 'engine_choices': ['compressor'],
            'summarizing_model_choices': list(dict.fromkeys([MODEL_ALIAS] + summary_options(provider) + ([chosen['summarizing_model']] if chosen.get('summarizing_model') else []))),
            'summarizing_model_patterns': summary_patterns(provider), 'independent_summarizing_model_supported': True,
            'threshold_note': 'Hermes floors this ratio at 0.75 below a 512K window and applies its 256000-token cap.',
            'summarizing_model_note': 'Named Choices models use the explicitly selected service through Lampway; local model IDs use openai:<model>. Changing its service/endpoint requires reselection.',
            'defaults_source': 'hermes_cli/config_defaults.py:compression,context.engine,auxiliary.compression', 'hermes_pin': 'v2026.9.24',
            'apply_note': 'Hermes adopts compression settings before the next normal turn on this same session; /model --once defers them until the following normal turn. '
                          'A manual /compress before that turn may still use the earlier threshold/recent-message settings. The summarizer model is read on each compression call.'}


def routes(store, bearer_ok, agent, caller_origin):
    async def live(project):
        from ..herdr import harnesses as HN
        import asyncio
        recs = await asyncio.to_thread(agent.cockpit.list_sessions)
        return [r for r in recs if HN.is_lampway(r.get('agent')) and r.get('state') == 'live'
                   and r.get('project_root') and project_key(r['project_root']) == project]

    async def endpoint(request):
        if not bearer_ok(request):
            return JSONResponse({'error': 'unauthorized'}, status_code=401)
        if caller_origin(request) != 'user':
            return JSONResponse({'error': 'user_only', 'message': 'Only your own Client may edit Context'}, status_code=403)
        try:
            if request.method == 'GET':
                project = project_key(request.query_params.get('project'))
            else:
                body = await request.json()
                if not isinstance(body, dict) or set(body) - {'project', 'values', 'reset'}:
                    raise Refused('Context accepts project, values, and reset only')
                project = project_key(body.get('project'))
                validate(body.get('values', {}))
            records = await live(project)
            running = bool(records)
            if request.method == 'PUT':
                if records and await panes_busy(request.app, records):
                    return JSONResponse({'error': 'context_busy', 'code': 'context_busy',
                        'message': 'The project’s Hermes session is busy; wait for it to finish. Nothing was changed.'}, status_code=409)
                selection = body.get('values', {}).get('summarizing_model')
                service = None
                if selection and selection != MODEL_ALIAS:
                    settings = request.app.state.settings
                    resolve_summary(settings, project, selection)
                    service = service_identity(settings, selection)
                import asyncio
                await asyncio.to_thread(store.apply, project, body.get('values', {}), body.get('reset', []), service, records)
            result = view(store, project, agent.provider, running)
            observed = observed_window(request.app, records)
            if observed:
                result['model_window'] = {'tokens': observed, 'source': 'Hermes runtime'}
            result['busy'] = await panes_busy(request.app, records) if records and request.method == 'GET' else False
            return JSONResponse(result)
        except (ValueError, OSError) as exc:
            return JSONResponse({'error': 'invalid_context', 'message': str(exc)}, status_code=400)
    return [Route('/app/agent/context', endpoint, methods=['GET', 'PUT'])]


def summary_alias(selection):
    return SUMMARY_PREFIX + hashlib.sha256(selection.encode()).hexdigest()[:16]


def service_identity(settings, selection=None):
    provider = selection.partition(':')[0] if selection else settings.provider
    return {'provider': provider,
            'endpoint': settings.openai_base_url.rstrip('/') if provider == 'openai' else ''}


def summary_options(provider):
    from ..choices import registry as REG
    kind = getattr(provider, 'name', '')
    options = [oid for oid in REG.get('agent.main').options if '*' not in oid and oid != 'openai:local']
    if kind == 'openai':
        options += ['openai:' + provider.model] if getattr(provider, 'model', '') else []
    return options


def resolve_summary(settings, project, selection):
    """A transient agent.main Choices resolution; no stored choice or fallback is changed."""
    from .. import choices as CH
    provider = CH.REG.provider_of(selection)
    doc = copy.deepcopy(CH.document(project))
    parent = CH.BR.chains(settings)['agent.main']
    # User-selected Context model is the sole candidate. Existing lower-scope params/
    # acknowledgements remain, and all seven Choices checks still run.
    option = 'openai:local' if provider == 'openai' else selection
    params = dict(parent.get('params') or {}) if provider == settings.provider else {}
    if provider != settings.provider:
        for scope in doc.values():
            if isinstance(scope, dict) and isinstance(scope.get('agent.main'), dict):
                scope['agent.main']['params'] = {}
    if provider == 'openai':
        params.update(model=selection.partition(':')[2], base_url=settings.openai_base_url)
    doc.setdefault('env', {})['agent.main'] = {**parent, 'preferred': option, 'params': params, 'fallbacks': []}
    try:
        return CH.resolve('agent.main', CH.Job(project=project, content_class='private'), doc=doc)
    except CH.NoChoice as exc:
        raise Refused(str(exc)) from exc


def selected_summary(store, project, settings, alias):
    entry = CF.read_json(store.path).get(project_key(project), {})
    selection = validate({k: v for k, v in entry.items() if k != '_summary_service'}).get('summarizing_model')
    if not selection or selection == MODEL_ALIAS or alias != summary_alias(selection):
        raise Refused('This pane has no explicit project selection for that summarizer alias')
    if entry.get('_summary_service') != service_identity(settings, selection):
        raise Refused('The selected service or endpoint changed; reselect the Context summarizer before using it')
    return resolve_summary(settings, project, selection)


def summary_patterns(provider):
    kind = getattr(provider, 'name', '')
    return [kind + ':<model>'] if kind in ('openrouter', 'chatgpt_plan', 'anthropic', 'openai') else []


async def panes_busy(app, records):
    """Native status snapshot only, not a race-atomic turn lock. Config adoption remains native-owned."""
    from .units import connect_when_up
    units = getattr(getattr(app.state, 'engine_wiring', None), 'units', None)
    if units is None:
        raise Refused('The live Hermes runtime cannot be checked; nothing was changed')
    for rec in records:
        info = units.info(rec)
        if info is None:
            raise Refused('The live Hermes runtime cannot be checked; nothing was changed')
        try:
            client = await connect_when_up(info, timeout=2, server_requests=False)
        except Exception as exc:
            raise Refused('The live Hermes runtime cannot be checked; nothing was changed') from exc
        try:
            result = await client.call('session.active_list', {}, timeout=2)
            rows = result.get('sessions')
            if not isinstance(rows, list) or not rows:
                raise Refused('The live Hermes session state is unavailable; nothing was changed')
            if any(row.get('status') != 'idle' for row in rows):
                return True
        except Exception as exc:
            raise Refused('The live Hermes session state is unavailable; nothing was changed') from exc
        finally:
            await client.close()
    return False


def observed_window(app, records):
    front = getattr(getattr(app.state, 'engine_wiring', None), 'front', None)
    for rec in records:
        link = getattr(front, 'links', {}).get(rec.get('unit'))
        window = getattr(link, 'context_max', None)
        if link and link.live_id and type(window) is int and window > 0:
            return window
    return None
