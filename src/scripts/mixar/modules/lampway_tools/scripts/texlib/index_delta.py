# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/texlib/index_delta.py, sha256 8af347ac6c7f) on 2026-10-06. The header below, with the measured rules behind
# the code, is the original's; the usage lines name Lampway's script paths.
# SPIKE (2026-10-03): write the Texture Library's next INDEX as a delta (wiki critique round 2, F5b / C2-C11): every
# file on Drive now that the baseline listing (taken right after the previous INDEX was uploaded) did not have, plus any
# baseline file whose sha256 changed, with Drive's sha256 and size. The wiki layer is excluded (it is mutable and pinned
# by the wiki's own pointers); the publisher's input folder is listed but marked mutable.
# Usage: python3 index_delta.py <baseline_listing.json> <current_listing.json> <out INDEX.v####.json> <previous INDEX name> <note>
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = _sys.argv[1:]
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['python3 scripts/texlib/index_delta.py <baseline_listing.json> <current_listing.json> <out INDEX.v####.json> <previous INDEX name> <note>']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 5:
    if not _A: _ax.home(__file__, "Write the Texture Library's next INDEX as a delta against a baseline listing")
    else: print(f'error: {len(_A)} argument(s); at least 5 needed')
    _ax.helps(['python3 scripts/texlib/index_delta.py <baseline_listing.json> <current_listing.json> <out INDEX.v####.json> <previous INDEX name> <note>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import json, os, re, sys

WIKI_LAYER = ('SCHEMA.md', 'index.md', 'log.md', 'entities/', 'concepts/', 'comparisons/', 'queries/', 'raw/')
MUTABLE = ('00 Catalog and Recipes/wiki/',)


def files(p):
    return {x['Path']: x for x in json.load(open(p)) if not x.get('IsDir') and not x['Path'].startswith(WIKI_LAYER)}


def main(base, cur, out, prev, note):
    if os.path.exists(out): _ax.refuse(f'{out} exists; an INDEX is never overwritten', ['python3 scripts/texlib/index_delta.py ... <out INDEX.v<next>.json> ...'])
    ver = re.search(r'INDEX\.(v\d{4})\.json$', out).group(1)
    A, B = files(base), files(cur)
    sha = lambda x: (x.get('Hashes') or {}).get('sha256')
    added = {p: B[p] for p in sorted(set(B) - set(A)) if not p.startswith('INDEX.')}
    changed = {p: B[p] for p in sorted(set(A) & set(B)) if sha(A[p]) != sha(B[p])}
    removed = sorted(set(A) - set(B))
    row = lambda x: {'sha256': sha(x), 'bytes': x['Size'], 'mutable': x['Path'].startswith(MUTABLE)}
    json.dump({'index_version': ver, 'previous_index': prev, 'delta': True, 'note': note,
               'baseline_listing': os.path.basename(base), 'current_listing': os.path.basename(cur),
               'approved_final_release': False, 'added': {p: row(x) for p, x in added.items()},
               'changed': {p: row(x) for p, x in changed.items()}, 'removed': removed},
              open(out, 'w'), indent=1)
    print(json.dumps({'added': len(added), 'changed': len(changed), 'removed': len(removed)}))


if __name__ == '__main__':
    main(*sys.argv[1:6])
