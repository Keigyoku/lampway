# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation bounds for large tool receipts; execution and aggregate counts stay complete."""


DEFAULT_LIMIT = 50


def options(fields=None, limit=DEFAULT_LIMIT, offset=0, full=False):
    if fields is not None and (not isinstance(fields, list) or not all(isinstance(f, str) and f for f in fields)):
        raise ValueError('fields must be an array of nonempty field names')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
        raise ValueError('limit must be an integer from 1 to 1000')
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError('offset must be a nonnegative integer')
    if not isinstance(full, bool):
        raise ValueError('full must be a boolean')
    return fields, limit, offset, full


def receipt(result, config, *, tool, defaults=None, tables=(), row_fields=None):
    fields, limit, offset, full = config
    available = set(result)
    if fields is not None and set(fields) - available:
        raise ValueError('unknown fields: ' + ', '.join(sorted(set(fields) - available)))
    chosen = fields if fields is not None else (list(result) if full or defaults is None else defaults)
    pages = {}
    explicit = set(tables)

    def compact(row, path):
        keep = (row_fields or {}).get(path)
        if keep is None:
            keep = [k for k, v in row.items() if not isinstance(v, (list, dict))][:4]
            if not keep:
                keep = list(row)[:4]
        return {k: row[k] for k in keep if k in row}

    def walk(value, path):
        container = isinstance(value, (list, dict))
        wrapper = isinstance(value, dict) and any(isinstance(v, list) for v in value.values())
        vector = isinstance(value, list) and len(value) <= 6 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
        fixed_row = path.startswith('collisions.') and path.count('.') == 1
        auto_table = (isinstance(value, list) and len(value) > limit and not vector and not fixed_row) or (isinstance(value, dict) and len(value) > max(limit, DEFAULT_LIMIT))
        paged = container and ((path in explicit and (not wrapper or len(value) > limit)) or auto_table)
        start = offset if paged else 0
        if paged:
            total = len(value)
            value = dict(list(value.items())[offset:offset+limit]) if isinstance(value, dict) else value[offset:offset+limit]
            pages[path] = {'total': total, 'offset': offset, 'limit': limit, 'returned': len(value),
                           'included': True, 'truncated': offset + len(value) < total}
        if isinstance(value, dict):
            if path in explicit and not paged:
                pages[path] = {'total': len(value), 'offset': 0, 'limit': limit, 'returned': len(value),
                               'included': True, 'truncated': False}
            return {k: walk(v, path + '.' + str(k)) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(compact(v, path) if isinstance(v, dict) and not full else v,
                         path + '.' + str(start + i)) for i, v in enumerate(value)]
        return value

    out = {k: walk(result[k], k) for k in chosen if k in result}
    # Keep the aggregate total for explicitly declared tables omitted by field projection.
    for path in explicit - set(pages):
        source = result
        for key in path.split('.'):
            if not isinstance(source, dict) or key not in source:
                source = None
                break
            source = source[key]
        if isinstance(source, (list, dict)):
            pages[path] = {'total': len(source), 'offset': offset, 'limit': limit, 'returned': 0,
                           'included': False, 'truncated': False}
    if 'truncated' in result and pages:
        out['truncated'] = any(p['truncated'] for p in pages.values())
    out['pages'] = pages
    out['fields'] = list(chosen)
    out['full'] = full
    if any(p['truncated'] for p in pages.values()):
        out['help'] = [f'{tool} limit={limit} offset={offset+limit} (retain the same input arguments); full=true includes detailed fields and keeps pagination']
    return out
