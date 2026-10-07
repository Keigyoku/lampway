# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure TOON codec shared by the client and server.

Python integers are lossless, floats use binary64 shortest round-trip decimals.
Nonfinite floats and unsupported host values become null. Tuples, sets and the
four mathutils sequence types become arrays; set encounter order is host-defined.
Surrogates are rejected. No serialization hooks or third-party imports are used.
The server's compute/toon_out.py is a byte-identical vendored copy, tested in CI.
"""
from __future__ import annotations

import math
import numbers
import re
from decimal import Decimal

_KEY = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')
_NUMERIC = re.compile(r'^[+-]?[0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$', re.I)
_NUMBER = re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?$', re.I)


def _check_string(value):
    if any(0xd800 <= ord(c) <= 0xdfff for c in value):
        raise ValueError('TOON strings cannot contain surrogates')
    return value


def normalize(value):
    # numpy 2 repr includes the scalar's constructor. Convert only explicit
    # numeric scalar types; arrays and arbitrary serialization hooks stay out.
    if type(value).__module__ == 'numpy':
        if type(value).__name__ in ('bool_', 'bool'):
            value = bool(value)
        elif isinstance(value, numbers.Integral):
            value = int(value)
        elif isinstance(value, numbers.Real):
            value = float(value)
    if value is None or isinstance(value, (bool, int, str)):
        return _check_string(value) if isinstance(value, str) else value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {_check_string(str(k)): normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)) or (
        type(value).__module__ == 'mathutils' and type(value).__name__ in ('Vector', 'Matrix', 'Euler', 'Quaternion')):
        return [normalize(v) for v in value]
    return None


def _quote(value):
    _check_string(value)
    escapes = {'\\': '\\\\', '"': '\\"', '\n': '\\n', '\r': '\\r', '\t': '\\t'}
    return '"' + ''.join(escapes.get(c, f'\\u{ord(c):04x}' if ord(c) < 32 else c) for c in value) + '"'


def _key(value):
    return value if _KEY.fullmatch(value) else _quote(value)


def _scalar(value, delimiter=',', root=False):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return 'null'
        if value == 0:
            return '0'
        token = repr(value).lower()
        if 1e-6 <= abs(value) < 1e21:
            return format(Decimal(token), 'f').rstrip('0').rstrip('.') if '.' in format(Decimal(token), 'f') else format(Decimal(token), 'f')
        mantissa, _, exponent = token.partition('e')
        mantissa = mantissa.removesuffix('.0')
        return mantissa + ('e' + f'{int(exponent):+d}' if exponent else '')
    need = (not value or value != value.strip(' \t') or value in ('true', 'false', 'null')
            or _NUMERIC.fullmatch(value) or any(c in value for c in ':"\\[]{}')
            or any(ord(c) < 32 for c in value) or delimiter in value
            or value.startswith(('-', '#')) or (root and value.startswith('\ufeff')))
    return _quote(value) if need else value


def _shape(rows):
    if not rows or not all(isinstance(r, dict) and r for r in rows):
        return None
    keys = list(rows[0])
    if any(set(r) != set(keys) for r in rows):
        return None
    shape = []
    for key in keys:
        values = [r[key] for r in rows]
        if all(not isinstance(v, (dict, list)) for v in values):
            shape.append((key, None))
        else:
            nested = _shape(values)
            if nested is None:
                return None
            shape.append((key, nested))
    return shape


def _fields(shape, delimiter):
    return delimiter.join(_key(k) + ('{' + _fields(sub, delimiter) + '}' if sub else '') for k, sub in shape)


def _leaves(row, shape):
    for key, sub in shape:
        if sub:
            yield from _leaves(row[key], sub)
        else:
            yield row[key]


def encode(value, *, delimiter=',', indent_size=2):
    """Encode normalized JSON-shaped data, without a final newline."""
    if delimiter not in (',', '\t', '|'):
        raise ValueError('delimiter must be comma, tab, or pipe')
    if isinstance(indent_size, bool) or not isinstance(indent_size, int) or indent_size < 1:
        raise ValueError('indent_size must be a positive integer')
    value = normalize(value)
    marker = '' if delimiter == ',' else delimiter
    pad = lambda depth: ' ' * (depth * indent_size)

    def render(v, key, depth, item=False):
        prefix = _key(key) if key is not None else ''
        if isinstance(v, dict):
            shape = _shape(list(v.values())) if len(v) >= 2 and not item else None
            if shape:
                lines = [pad(depth) + prefix + f'[{len(v)}:{marker}]' + '{' + _fields(shape, delimiter) + '}:']
                lines.extend(pad(depth + 1) + _key(k) + ': ' + delimiter.join(_scalar(c, delimiter) for c in _leaves(row, shape)) for k, row in v.items())
                return lines
            lines = [pad(depth) + prefix + ':'] if key is not None else []
            for k, val in v.items():
                lines.extend(render(val, k, depth + (key is not None)))
            return lines
        if isinstance(v, list):
            if not v and not item:
                return [pad(depth) + (prefix + ': ' if key is not None else '') + '[]']
            header = pad(depth) + prefix + f'[{len(v)}{marker}]'
            if all(not isinstance(x, (dict, list)) for x in v):
                return [header + ':' + (' ' + delimiter.join(_scalar(x, delimiter) for x in v) if v else '')]
            shape = _shape(v) if not item else None
            if shape:
                return [header + '{' + _fields(shape, delimiter) + '}:'] + [pad(depth + 1) + delimiter.join(_scalar(c, delimiter) for c in _leaves(row, shape)) for row in v]
            lines = [header + ':']
            for x in v:
                if isinstance(x, dict):
                    if not x:
                        lines.append(pad(depth + 1) + '-')
                        continue
                    fields = list(x.items())
                    first = render(fields[0][1], fields[0][0], depth + 2)
                    first[0] = pad(depth + 1) + '- ' + first[0].lstrip(' ')
                    lines.extend(first)
                    for k, val in fields[1:]:
                        lines.extend(render(val, k, depth + 2))
                else:
                    sub = render(x, None, depth + 1, item=isinstance(x, list))
                    sub[0] = pad(depth + 1) + '- ' + sub[0].lstrip(' ')
                    lines.extend(sub)
            return lines
        return [pad(depth) + (prefix + ': ' if key is not None else '') + _scalar(v, delimiter, root=key is None and depth == 0)]

    return '\n'.join(render(value, None, 0))


def dumps(value, indent=0, *, delimiter=',', indent_size=2):
    """Compatibility name for the compute CLI."""
    text = encode(value, delimiter=delimiter, indent_size=indent_size)
    return '\n'.join(' ' * (indent * indent_size) + line for line in text.split('\n')) if indent else text

SPEC_VERSION = '4.3'


def _split(text, delimiter, groups=False):
    """Split only outside quotes (and field groups, when requested)."""
    parts, start, quoted, escaped, depth = [], 0, False, False, 0
    for i, c in enumerate(text):
        if escaped:
            escaped = False
        elif quoted and c == '\\':
            escaped = True
        elif c == '"':
            quoted = not quoted
        elif not quoted:
            if groups and c == '{':
                depth += 1
            elif groups and c == '}':
                depth -= 1
            elif c == delimiter and depth == 0:
                parts.append(text[start:i])
                start = i + 1
    if groups and depth != 0:
        raise ValueError('unbalanced quoted token or field group')
    parts.append(text[start:])
    return parts


def _unquote(token):
    if not token.startswith('"'):
        return _check_string(token)
    if not token.endswith('"') or len(token) < 2:
        raise ValueError('unterminated quoted string')
    result, i = [], 1
    escapes = {'n': '\n', 'r': '\r', 't': '\t', '\\': '\\', '"': '"'}
    while i < len(token) - 1:
        c = token[i]
        if c == '"':
            raise ValueError('unexpected quote')
        if c != '\\':
            result.append(c)
        else:
            i += 1
            if i >= len(token) - 1:
                raise ValueError('incomplete escape')
            c = token[i]
            if c == 'u':
                code = token[i + 1:i + 5]
                if len(code) != 4 or not re.fullmatch('[0-9a-fA-F]{4}', code):
                    raise ValueError('invalid Unicode escape')
                result.append(chr(int(code, 16)))
                i += 4
            elif c in escapes:
                result.append(escapes[c])
            else:
                raise ValueError('invalid escape')
        i += 1
    return _check_string(''.join(result))


def _primitive(token, empty_array=False):
    token = token.strip(' ')
    if token.startswith('"'):
        return _unquote(token)
    if token == '[]' and empty_array:
        return []
    if token in ('true', 'false', 'null'):
        return {'true': True, 'false': False, 'null': None}[token]
    if _NUMBER.fullmatch(token):
        if not any(c in token.lower() for c in '.e'):
            return int(token)
        number = float(token)
        if not math.isfinite(number):
            raise ValueError('number exceeds binary64 range')
        return number
    return _check_string(token)


def _parse_fields(text, delimiter, strict):
    fields = []
    for entry in _split(text, delimiter, groups=True):
        # Find an opening group outside quotes.
        pieces = _split(entry, '{')
        name = pieces[0].strip(' ')
        if not name:
            raise ValueError('invalid field name')
        if len(pieces) > 1:
            if pieces[0] != pieces[0].rstrip(' '):
                raise ValueError('space before nested field group')
            nested = '{'.join(pieces[1:]).strip(' ')
            if not nested.endswith('}'):
                raise ValueError('invalid field group')
            sub = _parse_fields(nested[:-1], delimiter, strict)
        else:
            sub = None
        name = _unquote(name)
        if strict and any(name == key for key, _ in fields):
            raise ValueError('duplicate field name')
        fields.append((name, sub))
    return fields


def decode(text, *, strict=True, indent_size=2):
    """Decode TOON; strict mode rejects structural, width and count defects.

    Numeric domain: Python lossless integers and binary64 decimals; overflowing
    decimal/exponent input is rejected. Bytes are UTF-8, malformed bytes error in
    strict mode and use replacement characters otherwise.
    """
    if isinstance(text, bytes):
        text = text.decode('utf-8', errors='strict' if strict else 'replace')
    text = _check_string(text.removeprefix('\ufeff'))
    if not isinstance(indent_size, int) or indent_size < 1:
        raise ValueError('indent_size must be positive')
    lines, positions, blanks = [], [], set()
    for lineno, raw in enumerate(text.split('\n')):
        raw = raw.removesuffix('\r')
        spaces = len(raw) - len(raw.lstrip(' '))
        content = raw[spaces:]
        if not content.strip(' '):
            blanks.add(lineno)
            continue
        if content.startswith('#'):
            continue
        if content.startswith('\t'):
            if strict:
                raise ValueError('tabs cannot indent')
            spaces += (len(content) - len(content.lstrip('\t'))) * indent_size
            content = content.lstrip('\t')
            if not content.strip(' '):
                continue
        if strict and spaces % indent_size:
            raise ValueError('invalid indentation')
        lines.append((spaces if strict else spaces // indent_size * indent_size, content.rstrip(' ')))
        positions.append(lineno)
    if not lines:
        return {}
    if strict and lines[0][0] != 0:
        raise ValueError('root must not be indented')

    def pair(content):
        parts = _split(content, ':')
        if len(parts) < 2:
            return None
        return parts[0], ':'.join(parts[1:]).lstrip(' ')

    def header(content):
        # A bracket inside a quoted key is literal, so locate after the quote.
        quoted = escaped = False
        opening = None
        for i, c in enumerate(content):
            if escaped:
                escaped = False
            elif quoted and c == '\\':
                escaped = True
            elif c == '"':
                quoted = not quoted
            elif c == '[' and not quoted:
                opening = i
                break
        if opening is None or pair(content) is None or pair(content[:opening]) is not None:
            return None
        key = content[:opening]
        m = re.fullmatch(r'\[(0|[1-9][0-9]*)(:)?([|\t]?)\](?:\{(.*)\})?: *(.*)', content[opening:])
        if not m or key and key[-1].isspace():
            if strict:
                raise ValueError('malformed header')
            return None
        n, keyed, delim, fields, inline = m.groups()
        delim = delim or ','
        if keyed and fields is None or fields is not None and inline:
            if strict:
                raise ValueError('invalid keyed or tabular header')
            return None
        if fields is not None and any(len(_split(fields, other, groups=True)) > 1 for other in (',', '|', '\t') if other != delim):
            if strict:
                raise ValueError('field delimiter mismatch')
            return None
        shape = _parse_fields(fields, delim, strict) if fields is not None else None
        return (_unquote(key) if key else None, int(n), bool(keyed), delim, shape, inline)

    def put(obj, key, value):
        if strict and key in obj:
            raise ValueError('duplicate object key')
        obj[key] = value

    def row_value(shape, cells):
        iterator = iter(cells)
        missing = object()
        def build(fields):
            result = {}
            for key, sub in fields:
                if sub:
                    result[key] = build(sub)
                else:
                    cell = next(iterator, missing)
                    if cell is missing:
                        if strict:
                            raise ValueError('too few row cells')
                    else:
                        result[key] = cell
            return result
        try:
            value = build(shape)
        except StopIteration as exc:
            raise ValueError('too few row cells') from exc
        if strict and next(iterator, missing) is not missing:
            raise ValueError('too many row cells')
        return value

    def value_line(content, depth, index, allow_keyless=False):
        h = header(content)
        if h and h[0] is None and not allow_keyless:
            if strict:
                raise ValueError('keyless header outside root or list item')
            h = None
        if h:
            key, n, keyed, delim, shape, inline = h
            if key is None and not allow_keyless:
                raise ValueError('keyless header outside root or list item')
            if inline:
                values = [_primitive(v) for v in _split(inline, delim)]
                if strict and len(values) != n:
                    raise ValueError('inline array count mismatch')
                return key, values, index
            result = {} if keyed else []
            count = 0
            start_index = index
            adopted = lines[index][0] if index < len(lines) and lines[index][0] > depth else depth + indent_size
            while index < len(lines) and lines[index][0] > depth:
                rowdepth, content2 = lines[index]
                if strict and rowdepth != depth + indent_size:
                    raise ValueError('incorrect row or item depth')
                if not strict and rowdepth != adopted:
                    if pair(content2) is None and not content2.startswith('- '):
                        raise ValueError('orphan scalar line')
                    index += 1
                    continue
                if shape:
                    entry = pair(content2) if keyed else None
                    if keyed and entry is None:
                        if strict:
                            raise ValueError('keyed row needs colon')
                        index += 1
                        continue
                    if not keyed and pair(content2) is not None:
                        # An earlier delimiter makes this a row, not a field.
                        colonparts = _split(content2, ':')
                        if len(_split(colonparts[0], delim)) == 1:
                            break
                    celltext = entry[1] if keyed else content2
                    cells = [_primitive(c) for c in _split(celltext, delim)] if celltext.strip(' ') else []
                    value = row_value(shape, cells)
                    if keyed:
                        put(result, _unquote(entry[0]), value)
                    else:
                        result.append(value)
                    index += 1
                else:
                    if content2 != '-' and not content2.startswith('- '):
                        break
                    item = content2[2:] if content2.startswith('- ') else ''
                    index += 1
                    if not item:
                        value = {}
                    elif item.startswith('[') and header(item):
                        if header(item)[4] is not None:
                            if strict:
                                raise ValueError('keyless table list item')
                            value = {}
                            k, v, index = value_line(item, rowdepth + indent_size, index)
                            put(value, k, v)
                        else:
                            _, value, index = value_line(item, rowdepth, index, True)
                    elif pair(item) is not None:
                        # First field sits at virtual depth d+1; sibling fields
                        # follow at that same depth, children at depth d+2.
                        obj = {}
                        k, v, index = value_line(item, rowdepth + indent_size, index)
                        put(obj, k, v)
                        while index < len(lines) and lines[index][0] > rowdepth:
                            d, c = lines[index]
                            if strict and d != rowdepth + indent_size:
                                raise ValueError('incorrect object field depth')
                            if not strict and d != rowdepth + indent_size:
                                if pair(c) is None and not c.startswith('- '):
                                    raise ValueError('orphan scalar line')
                                index += 1
                                continue
                            k, v, index = value_line(c, d, index + 1)
                            put(obj, k, v)
                        value = obj
                    else:
                        value = _primitive(item, True)
                    result.append(value)
                count += 1
            if strict and index > start_index and any(positions[start_index] < b < positions[index - 1] for b in blanks):
                raise ValueError('blank line inside array span')
            if strict and count != n:
                raise ValueError('table or list count mismatch')
            return key, result, index
        p = pair(content)
        if p is None:
            if not allow_keyless:
                raise ValueError('object field needs a colon')
            return None, _primitive(content, True), index
        key, rest = p
        key = _unquote(key.strip(' '))
        if rest:
            return key, _primitive(rest, True), index
        obj = {}
        adopted = lines[index][0] if index < len(lines) and lines[index][0] > depth else depth + indent_size
        while index < len(lines) and lines[index][0] > depth:
            d, c = lines[index]
            if strict and d != depth + indent_size:
                raise ValueError('incorrect object field depth')
            if not strict and d != adopted:
                if pair(c) is None and not c.startswith('- '):
                    raise ValueError('orphan scalar line')
                index += 1
                continue
            k, v, index = value_line(c, d, index + 1)
            put(obj, k, v)
        return key, obj, index

    first = lines[0][1]
    h = header(first)
    if h and h[0] is None or pair(first) is None:
        if lines[0][0] != 0:
            raise ValueError('root value must not be indented')
        _, result, index = value_line(first, 0, 1, True)
        if index != len(lines):
            raise ValueError('unexpected lines after root value')
        return result
    result, index = {}, 0
    while index < len(lines):
        d, content = lines[index]
        if d != 0:
            if strict or pair(content) is None:
                raise ValueError('orphaned line')
            index += 1
            continue
        key, value, index = value_line(content, d, index + 1)
        put(result, key, value)
    return result
