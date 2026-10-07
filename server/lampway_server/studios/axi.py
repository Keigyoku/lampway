# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/axi_out.py, sha256 374531468df2) on 2026-10-05; the same module the client side ships as
# mixar/modules/lampway_tools/axi.py (the server must not import the app's package).
"""Shared AXI output for the shelf's tools (tools/AXI.md). Import with:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), <'..' per level>)); import axi_out as ax
Output is TOON v4.1 (tools/TOON-SPEC.md). Everything goes to STDOUT (structured data and refusals alike); stderr stays for debug noise.
  ax.home(__file__, 'one-sentence description')        bin path (~ for home) + description, the head of a no-args view
  ax.kv({'key': value, ...})                           compact `key: value` block (nested dicts indent once)
  ax.table('seeds', rows, ['id', 'score', ...])        TOON: name[N]{fields}: then one comma row per item; '0 seeds' when empty
  ax.helps(['tool x <id>', ...])                       help[N]: next-step command templates (placeholders, never guesses)
  ax.refuse('why', ['next command'])                   prints `error: why` + help[], exits 1
  ax.trunc(text, n, hint)                              cut long text with a size hint
"""
import os, sys

HOME = os.path.expanduser('~')


NUMERIC = __import__('re').compile(r'^[+-]?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$', __import__('re').I)


def _num(v):
    """A TOON 4 canonical number: the shortest round-trip digits, no exponent for 1e-6 <= |v| < 1e21, no trailing zeros, -0 -> 0, a
    non-finite float -> null (audit F9: `.4g` printed 1234567.0 as 1.235e+06 and the value was lost)."""
    if isinstance(v, int): return str(v)
    if v != v or v in (float('inf'), float('-inf')): return 'null'
    if v == 0: return '0'
    if 1e-6 <= abs(v) < 1e21:
        t = format(__import__('decimal').Decimal(repr(v)), 'f')
        return t.rstrip('0').rstrip('.') if '.' in t else t
    m, e = repr(v).lower().split('e')
    return f"{m}e{'+' if int(e) >= 0 else '-'}{abs(int(e))}"


def _s(v, delim=','):
    """one TOON primitive per spec v4.1 (tools/TOON-SPEC.md): null/true/false, canonical numbers, and strings quoted per §7.2
    (empty, edge whitespace, true/false/null, numeric-like, : " \\ [ ] { }, control chars, the delimiter, leading - or #)"""
    if v is None: return 'null'
    if isinstance(v, bool): return 'true' if v else 'false'
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return _num(v)
    s = str(v)
    need = (s == '' or s != s.strip(' \t') or s in ('true', 'false', 'null') or NUMERIC.match(s) or any(c in s for c in ':"\\[]{}')
            or any(ord(c) < 32 for c in s) or delim in s or s.startswith(('-', '#')))
    if not need: return s
    e = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
    e = ''.join(c if ord(c) >= 32 else f'\\u{ord(c):04x}' for c in e)
    return f'"{e}"'


def home(path, description):
    p = os.path.realpath(path)
    for h in (os.path.realpath(HOME), HOME):                               # /home is a symlink on some Linux systems
        if p.startswith(h + os.sep): p = '~' + p[len(h):]; break
    print(f'bin: {p}'); print(f'description: {description}')


KEY = __import__('re').compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')


def _k(k): return k if KEY.fullmatch(str(k)) else _s(str(k), delim='\x00') if _s(str(k), delim='\x00').startswith('"') else f'"{k}"'


def kv(d, indent=''):
    for k, v in d.items():
        k = _k(k)
        if isinstance(v, dict): print(f'{indent}{k}:'); kv(v, indent + '  ')
        else: print(f'{indent}{k}: {_s(v)}')


def table(name, rows, fields, total=None):
    if total is not None: print(f'count: {len(rows)} of {total} total')
    name = _k(name); head = [_k(f) for f in fields]                      # quoted for the header only; rows are read by the raw names
    if not rows: print(f'{name}: []'); return                              # TOON 4's empty array, a definitive zero (AXI 5); the legacy name[0]: MUST NOT be emitted
    print(f'{name}[{len(rows)}]{{{",".join(head)}}}:')
    for r in rows: print('  ' + ','.join(_s(r.get(f) if isinstance(r, dict) else r[i]) for i, f in enumerate(fields)))


def helps(lines):
    if not lines: return
    print(f'help[{len(lines)}]:')                                           # TOON §9.4 list form: one '- ' item per line, quoted per §7.2
    for l in lines: print(f'  - {_s(f"Run `{l}`")}')


def refuse(why, nexts=()):
    print(f'error: {why}'); helps(list(nexts)); sys.stdout.flush(); sys.exit(1)


def trunc(text, n=200, hint='use --full'):
    text = str(text)
    return text if len(text) <= n else f'{text[:n]}… (truncated, {len(text)} chars total — {hint})'
