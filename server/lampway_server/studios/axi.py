# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# AXI CLI compatibility helpers, rendered through the shared TOON codec.
"""Shared AXI output for Lampway's tools (the shelf's tools/AXI.md). Import with:
    from lampway_server.studios import axi as ax
Output is TOON v4.3 (tools/TOON-SPEC.md). Everything goes to STDOUT (structured data and refusals alike); stderr stays for debug noise.
  ax.home(__file__, 'one-sentence description')        bin path (~ for home) + description, the head of a no-args view
  ax.kv({'key': value, ...})                           compact `key: value` block (nested dicts indent once)
  ax.table('seeds', rows, ['id', 'score', ...])        TOON table when rows are uniform; name: [] when empty
  ax.helps(['tool x <id>', ...])                       help[N]: next-step command templates (placeholders, never guesses)
  ax.refuse('why', ['next command'])                   prints `error: why` + help[], exits 1
  ax.trunc(text, n, hint)                              cut long text with a size hint
"""
import os
import sys

HOME = os.path.expanduser('~')


from ..compute.toon_out import encode, normalize, _scalar, _key

_STREAM = None
_WROTE = False


def _emit(value, indent=''):
    global _STREAM, _WROTE
    if _STREAM is not sys.stdout:
        _STREAM, _WROTE = sys.stdout, False
    text = encode(value)
    if indent:
        text = '\n'.join(indent + line for line in text.split('\n'))
    if _WROTE:
        print('\n', end='')
    print(text, end='')
    _WROTE = True


def _s(v, delim=','):
    return _scalar(normalize(v), delim)


def _k(k):
    return _key(str(k))


def home(path, description):
    p = os.path.realpath(path)
    for h in (os.path.realpath(HOME), HOME):
        if p.startswith(h + os.sep):
            p = '~' + p[len(h):]
            break
    _emit({'bin': p, 'description': description})


def kv(d, indent=''):
    _emit(d, indent)


def table(name, rows, fields, total=None):
    data = {}
    if total is not None:
        data['count'] = f'{len(rows)} of {total} total'
    data[name] = [{f: r[f] for f in fields if f in r} if isinstance(r, dict)
                  else dict(zip(fields, r)) for r in rows]
    _emit(data)


def helps(lines):
    if lines:
        _emit({'help': [f'Run `{line}`' for line in lines]})


def refuse(why, nexts=()):
    data = {'error': why}
    if nexts:
        data['help'] = [f'Run `{line}`' for line in nexts]
    _emit(data)
    sys.stdout.flush()
    sys.exit(1)


def trunc(text, n=200, hint='use --full'):
    text = str(text)
    return text if len(text) <= n else f'{text[:n]}… (truncated, {len(text)} chars total — {hint})'
