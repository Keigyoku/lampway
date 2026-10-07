# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation bounds for large tool receipts; execution and aggregate counts stay complete."""


def options(fields=None, limit=50, offset=0, full=False):
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
    out = {k: result[k] for k in chosen if k in result}
    pages = {}
    # Paths identify logical tables, not coordinate vectors or aggregate count dictionaries.
    for path in tables:
        keys = path.split('.')
        src = result
        for key in keys:
            if not isinstance(src, dict) or key not in src:
                src = None
                break
            src = src[key]
        if not isinstance(src, (list, dict)):
            continue
        total = len(src)
        dst = out
        included = True
        for key in keys[:-1]:
            if key not in dst:
                included = False
                break
            dst[key] = dict(dst[key])
            dst = dst[key]
        key = keys[-1]
        included = included and key in dst
        returned = 0
        if included:
            if isinstance(src, dict):
                dst[key] = dict(list(src.items())[offset:offset+limit])
            else:
                page = src[offset:offset+limit]
                keep = (row_fields or {}).get(path)
                dst[key] = [{k: r[k] for k in keep if k in r} if keep and isinstance(r, dict) and not full else r for r in page]
            returned = len(dst[key])
        pages[path] = {'total': total, 'offset': offset, 'limit': limit, 'returned': returned,
                       'included': included, 'truncated': included and offset + returned < total}
    if 'truncated' in result and pages:
        out['truncated'] = any(p['truncated'] for p in pages.values())
    out['pages'] = pages
    out['fields'] = list(chosen)
    out['full'] = full
    if any(p['truncated'] for p in pages.values()):
        out['help'] = [f'{tool} limit={limit} offset={offset+limit} (retain the same input arguments); full=true includes detailed fields and keeps pagination']
    return out
