# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Source-bound authorization of copied contact pairs, never full-fit review.

The caller supplies actual source authority. This module changes no geometry,
weights, tolerance, bone selection or review flag on the source/prepared object.
"""
import hashlib
import json

import numpy as np


def digest(declaration, plan_parts):
    return hashlib.sha256(json.dumps({'declaration': declaration, 'parts': plan_parts}, sort_keys=True).encode()).hexdigest()


def validate(declaration, *, source_hash, prepared_hash, prepared_identity,
             original_seams, source_ids, parts, plan_parts, measured_pairs):
    """Pure admission using independently validated authored-copy provenance.

    measured_pairs maps each declared unordered part pair to all current copied
    vertex contacts under the existing weld bar, not a sampled subset.
    """
    if declaration is None:
        return None
    fields = {'schema', 'source_sha256', 'prepared_sha256', 'prepared_identity', 'contacts', 'authorization'}
    if not isinstance(declaration, dict) or set(declaration) != fields or declaration['schema'] != 'lampway.articulated-contacts/1':
        raise ValueError('articulated contacts need the exact source/prepared identity, contacts and authorization fields')
    if source_ids is None or not source_hash:
        raise ValueError('articulated contacts require an independently validated authored ownership copy; prepare the unchanged original')
    for field, actual in [('source_sha256', source_hash), ('prepared_sha256', prepared_hash), ('prepared_identity', prepared_identity)]:
        if declaration[field] != actual:
            raise ValueError(f'articulated contacts have stale {field}; review inputs and rerun plan')
    authority = declaration['authorization']
    if (not isinstance(authority, dict) or set(authority) != {'decision', 'scope', 'declaration'}
            or authority['decision'] != 'release_derived_contacts' or authority['scope'] != 'contact_pairs_only'
            or not isinstance(authority['declaration'], str) or not authority['declaration'].strip()):
        raise ValueError('articulated contact authorization must declare release_derived_contacts for contact_pairs_only; full-fit review is separate')
    rows = declaration['contacts']
    if not isinstance(rows, list) or not rows or len(rows) > len(parts)*(len(parts)-1)//2:
        raise ValueError('articulated contacts need a nonempty bounded explicit contact-pair list')
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'parts', 'source_vertices', 'retained_source_vertices'}:
            raise ValueError('each articulated contact names parts, released source_vertices and retained_source_vertices')
        pair = row['parts']
        if (not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(p, str) or p not in plan_parts for p in pair)
                or pair[0] == pair[1]):
            raise ValueError('articulated contact parts must name two distinct planned parts')
        key = tuple(sorted(pair))
        if key in seen:
            raise ValueError('duplicate articulated contact pair')
        seen.add(key)
        if np.intersect1d(parts[key[0]], parts[key[1]]).size:
            raise ValueError('articulated contacts require disjoint prepared part membership')
        rigid = [plan_parts[p] for p in pair if plan_parts[p]['mode'] == 'rigid']
        if not rigid or any(len(p['bones']) != 1 for p in rigid):
            raise ValueError('articulated contact needs an explicit single-bone rigid endpoint')
        if len(rigid) == 2 and rigid[0]['bones'] == rigid[1]['bones']:
            raise ValueError('same-bone rigid contacts need no release; retain their rigid group')
        given = row['source_vertices']
        if (not isinstance(given, list) or not given or any(type(i) is not int or i < 0 for i in given)
                or len(given) != len(set(given))):
            raise ValueError('articulated contact source_vertices must be unique nonnegative integer original IDs')
        retained = row['retained_source_vertices']
        if (not isinstance(retained, list) or any(type(i) is not int or i < 0 for i in retained)
                or len(retained) != len(set(retained)) or set(retained) & set(given)):
            raise ValueError('retained articulated contact IDs must be unique nonnegative integers disjoint from released IDs')
        closure = set(given) | set(retained)
        expected = original_seams.get(key, set())
        if closure != expected:
            raise ValueError('articulated contacts must equal the complete original contact closure for each named pair')
        actual = measured_pairs.get(key, set())
        # Each copied original contact must still have exactly one vertex in each
        # named endpoint; unrelated coincident original IDs are never released.
        expected_pairs = set()
        for i in sorted(closure):
            endpoints = [[int(v) for v in parts[p] if int(source_ids[v]) == i] for p in key]
            if any(len(e) != 1 for e in endpoints):
                raise ValueError('articulated contact source identity/membership is ambiguous or missing')
            expected_pairs.add((endpoints[0][0], endpoints[1][0]))
        if actual != expected_pairs:
            raise ValueError('articulated contacts do not equal complete current contact closure; moved or additional contacts require source review')
    return json.loads(json.dumps(declaration))


def receipt(declaration):
    if declaration is None:
        return None
    return {'schema': declaration['schema'], 'contacts': declaration['contacts'],
            'contact_pairs_checked': sum(len(r['source_vertices']) + len(r['retained_source_vertices']) for r in declaration['contacts']),
            'released_contact_pairs': sum(len(r['source_vertices']) for r in declaration['contacts']),
            'retained_contact_pairs': sum(len(r['retained_source_vertices']) for r in declaration['contacts']),
            'contact_source_vertices': len({i for r in declaration['contacts'] for i in r['source_vertices']}),
            'authorization': declaration['authorization'], 'physical_status': 'unreviewed',
            'full_fit_owner_review_accepted': False}


def released_pairs(declaration):
    return {tuple(sorted(row['parts'])) for row in declaration['contacts'] if not row['retained_source_vertices']} if declaration else set()


def fade_exclusions(declaration, parts, plan_parts, source_ids):
    """Only listed flexible contact vertices ignore the named rigid surface."""
    out = {}
    if not declaration:
        return out
    for row in declaration['contacts']:
        a, b = row['parts']
        for rigid, soft in [(a, b), (b, a)]:
            if plan_parts[rigid]['mode'] == 'rigid' and plan_parts[soft]['mode'] != 'rigid':
                ids = set(row['source_vertices'])
                for v in parts[soft]:
                    if int(source_ids[v]) in ids:
                        out.setdefault(int(v), set()).add(rigid)
    return out
