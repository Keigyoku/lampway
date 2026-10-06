# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""libwiki (STATUS O33): the deterministic library-wiki publisher, ported from the owner's tool shelf with its falsifiers. Each case runs the real CLI on a
throwaway wiki and asserts the refusal by name, or that nothing outside the wiki was harmed (the shelf's test_libwiki.py, wiki critique round 2: C2-N1..N12,
F3), here under pytest with the scratch in tmp_path. PyYAML is not in Blender's python: frontmatter is read by PyYAML when present, else by the JSON-valued
subset the publisher itself writes, which refuses what it cannot read."""

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TOOL = str(Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/scripts/libwiki/libwiki.py")
W = None
MISSES = []

SCHEMA = '# Wiki Schema - test\n\n## Tag Taxonomy\n\n- `material`, `tile`, `cloth`\n'
CONCEPT = ('---\ntitle: "Tiling"\ncreated: "2026-10-01"\ntype: "concept"\ntags: ["tile"]\nsources: []\noneline: "how tiles are made"\n---\n'
           '# Tiling\n\nSee [[entities/a-cloth]] and [[queries/q]].\n')
QUERY = ('---\ntitle: "Q"\ncreated: "2026-10-01"\ntype: "query"\ntags: ["tile"]\nsources: []\noneline: "a question"\n---\n'
         '# Q\n\nSee [[entities/a-cloth]] and [[concepts/tiling]].\n')
SPEC = {'name': 'Test Library', 'drive_path': 'Test', 'pointer_depth': 1, 'entities': [
    {'slug': 'a-cloth', 'title': 'A cloth', 'tags': ['material', 'cloth'], 'raw': ['02 In'], 'status': 'candidate',
     'proposed': True, 'oneline': 'a cloth tile', 'summary': 'A cloth.', 'related': ['concepts/tiling', 'queries/q']}]}
INV = [{'Path': '02 In', 'Name': '02 In', 'Size': -1, 'IsDir': True},
       {'Path': '02 In/a.png', 'Name': 'a.png', 'Size': 10, 'IsDir': False, 'Hashes': {'sha256': 'a' * 64}},
       {'Path': '02 In/b.png', 'Name': 'b.png', 'Size': 20, 'IsDir': False, 'Hashes': {'sha256': 'b' * 64}}]


def setup(spec=SPEC, inv=INV, authored=None):
    if os.path.isdir(W): shutil.rmtree(W)
    os.makedirs(os.path.join(W, 'authored', 'concepts')); os.makedirs(os.path.join(W, 'authored', 'queries'))
    files = {'SCHEMA.md': SCHEMA, 'concepts/tiling.md': CONCEPT, 'queries/q.md': QUERY}
    files.update(authored or {})
    for rel, txt in files.items():
        if txt is None: continue
        os.makedirs(os.path.dirname(os.path.join(W, 'authored', rel)) or '.', exist_ok=True)
        open(os.path.join(W, 'authored', rel), 'w').write(txt)
    json.dump(spec, open(os.path.join(W, 'spec.json'), 'w')); json.dump(inv, open(os.path.join(W, 'inv-2026-10-03.json'), 'w'))


def run(*args):
    p = subprocess.run([sys.executable, TOOL, *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def build(out='wiki', date='2026-10-03', extra=()):
    return run('build', os.path.join(W, 'spec.json'), os.path.join(W, 'inv-2026-10-03.json'), os.path.join(W, 'authored'),
               os.path.join(W, out) if not os.path.isabs(out) else out, '--date', date, '--log', 'test', *extra)


def check(name, ok, detail=''):
    if not ok:
        MISSES.append(f'{name}: {detail[:600]}')


def refused(name, rc_out, needle):
    rc, out = rc_out
    check(name, rc != 0 and 'refused' in out and needle in out, out)




def test_the_shelf_falsifiers_all_hold(tmp_path):
    global W
    W = str(tmp_path / "scratch")
    MISSES.clear()
    # control: a clean build (raw lsjson with directory entries, C2-N3), lint clean, no staging left
    setup(); rc, out = build()
    check('control: clean build from raw lsjson output (dirs skipped)', rc == 0, out)
    check('control: lint clean', run('lint', os.path.join(W, 'wiki'))[0] == 0, run('lint', os.path.join(W, 'wiki'))[1])
    check('control: no staging or previous dir left', not os.path.exists(os.path.join(W, 'wiki.staging')) and not os.path.exists(os.path.join(W, 'wiki.previous')))
    check('control: no staging marker shipped', not os.path.exists(os.path.join(W, 'wiki', '.libwiki-staging')))
    idx = open(os.path.join(W, 'wiki', 'index.md')).read()
    check('control: proposed tile under the proposed heading', '## Proposed for approval' in idx and '[[entities/a-cloth|A cloth]]' in idx, idx)
    # C2-N1: trailing slash keeps the wiki
    log0 = open(os.path.join(W, 'wiki', 'log.md')).read()
    rc, out = build(out=os.path.join(W, 'wiki') + '/', date='2026-10-04')
    check('N1: build into out/ (trailing slash) succeeds and keeps the log history', rc == 0 and open(os.path.join(W, 'wiki', 'log.md')).read().startswith(log0), out)
    # no-op rebuild changes only index.md and log.md
    snap = {r: open(os.path.join(W, 'wiki', r)).read() for r in ('entities/a-cloth.md', 'concepts/tiling.md', 'raw/pointers/02-in.md')}
    build(date='2026-10-05')
    check('no-op rebuild leaves pages and pointers byte-identical', all(open(os.path.join(W, 'wiki', r)).read() == s for r, s in snap.items()))
    # C2-N2: a directory that is not a wiki is never replaced
    os.makedirs(os.path.join(W, 'notawiki', 'raw_stuff')); open(os.path.join(W, 'notawiki', 'raw_stuff', 'KEEP.txt'), 'w').write('keep')
    refused('N2: out = a non-wiki directory is refused', build(out='notawiki'), 'not a wiki')
    check('N2: and its file survives', os.path.exists(os.path.join(W, 'notawiki', 'raw_stuff', 'KEEP.txt')))
    open(os.path.join(W, 'wiki', 'stray.txt'), 'w').write('x')
    refused('N2: a wiki holding a stray file is refused', build(), 'outside the wiki layer')
    os.remove(os.path.join(W, 'wiki', 'stray.txt'))
    # C2-N5: a failing build leaves no staging behind and the next build runs; the previous wiki is untouched
    before = open(os.path.join(W, 'wiki', 'index.md')).read()
    bad = copy.deepcopy(SPEC); del bad['entities'][0]['oneline']; json.dump(bad, open(os.path.join(W, 'spec.json'), 'w'))
    refused('N5: missing spec field is named', build(), "missing 'oneline'")
    check('N5: no staging left after a refusal', not os.path.exists(os.path.join(W, 'wiki.staging')))
    check('N5: previous wiki untouched', open(os.path.join(W, 'wiki', 'index.md')).read() == before)
    json.dump(SPEC, open(os.path.join(W, 'spec.json'), 'w'))
    open(os.path.join(W, 'authored', 'concepts', 'tiling.md'), 'w').write('---\ntitle: [unclosed\n---\nbody\n')
    refused('N5: bad authored YAML names the file', build(), 'concepts/tiling.md')
    check('N5: no staging after a YAML crash', not os.path.exists(os.path.join(W, 'wiki.staging')))
    open(os.path.join(W, 'authored', 'concepts', 'tiling.md'), 'w').write(CONCEPT)
    check('N5: next build runs after the failures', build()[0] == 0)
    # C2-N6: authored pages cannot replace generated entities; type must match folder; duplicate slug named
    setup(authored={'entities/a-cloth.md': CONCEPT.replace('"concept"', '"entity"')})
    refused('N6: an authored entity page is refused', build(), 'entities are generated')
    setup(authored={'concepts/tiling.md': CONCEPT.replace('type: "concept"', 'type: "entity"')})
    refused('N6: authored type != folder is refused', build(), "type 'entity' but it lives in concepts/")
    dup = copy.deepcopy(SPEC); dup['entities'].append(copy.deepcopy(dup['entities'][0])); setup(spec=dup)
    refused('N6: duplicate slug is named', build(), 'duplicate slug')
    # C2-N7: proposals and one-line fields
    for label, mut, needle in [
            ('proposed "yes" (string)', lambda e: e.update(proposed='yes'), 'proposed must be true or false'),
            ('proposed false without a reason', lambda e: e.update(proposed=False), 'not_proposed_reason'),
            ('proposed true on a raw entity', lambda e: e.update(status='raw'), 'only a candidate can be proposed'),
            ('status approved without an approval record', lambda e: (e.pop('proposed'), e.update(status='approved')), 'approval_record'),
            ('newline in title', lambda e: e.update(title='A\n## injected'), 'title must be one'),
            ('newline in oneline', lambda e: e.update(oneline='x\n## Injected heading'), 'oneline must be one'),
            ('typo key', lambda e: e.update(proposd=True), 'unknown key'),
            ('slug with a path', lambda e: e.update(slug='../../escape'), 'slug must be'),
            ('unknown status', lambda e: e.update(status='done'), "status 'done'")]:
        s = copy.deepcopy(SPEC); mut(s['entities'][0]); setup(spec=s)
        refused(f'N7: {label}', build(), needle)
    setup(); refused('N7: --date not a date', build(date='tomorrow'), 'not YYYY-MM-DD')
    s = copy.deepcopy(SPEC); s['entities'][0].update(status='approved', approval_record='09 Approved Textures/Tileable/Cloth/A/v0001/APPROVAL.json')
    s['entities'][0].pop('proposed')
    inv = INV + [{'Path': '09 Approved Textures/Tileable/Cloth/A/v0001/APPROVAL.json', 'Name': 'APPROVAL.json', 'Size': 5, 'IsDir': False, 'Hashes': {'sha256': 'c' * 64}}]
    setup(spec=s, inv=inv); rc, out = build()
    check('N7 control: approved with its APPROVAL.json in the inventory builds', rc == 0 and '## Approved by the owner' in open(os.path.join(W, 'wiki', 'index.md')).read(), out)
    inv = INV + [{'Path': '02-In/c.png', 'Name': 'c.png', 'Size': 5, 'IsDir': False, 'Hashes': {'sha256': 'c' * 64}}]
    setup(inv=inv); refused('two library folders mapping to one pointer page are refused', build(), 'same pointer')
    # C2-N8 / F3: lint catches hand edits
    setup(); build(); L = os.path.join(W, 'wiki')
    def lint_after(rel, old, new, needle, name):
        p = os.path.join(L, rel); s0 = open(p).read(); assert old in s0 and s0.count(old) == 1, (rel, old)
        open(p, 'w').write(s0.replace(old, new)); rc, out = run('lint', L); open(p, 'w').write(s0)
        check(f'N8: lint catches {name}', rc != 0 and needle in out, out)
    lint_after('entities/a-cloth.md', '"status": "candidate"'.replace('"status": ', 'status: '), 'status: "approved"', 'approval_record', 'status approved set by hand')
    lint_after('index.md', 'Wiki pages: 3 ', 'Wiki pages: 99 ', 'header says', 'wrong index totals')
    lint_after('concepts/tiling.md', 'updated: "2026-10-03"', 'updated: "1999-01-01"', 'updated before created', 'updated before created')
    lint_after('raw/pointers/02-in.md', 'a' * 64, '0' * 64, 'differs from the inventory', 'a wrong pointer row hash')
    lint_after('log.md', '- changed:', 'garbage line\n- changed:', 'not a log line', 'a garbage log line')
    lint_after('concepts/tiling.md', 'type: "concept"', 'type: "entity"', "type 'entity' in concepts/", 'type != folder')
    lint_after('raw/pointers/02-in.md', '| Total:', '| Total (edited):', 'pointer_sha256 does not match', 'an edited pointer body')
    # C2-N4: drift after the wiki itself is uploaded is not drift
    up = INV + [{'Path': p, 'Name': os.path.basename(p), 'Size': 1, 'IsDir': False, 'Hashes': {'sha256': 'd' * 64}}
                for p in ('index.md', 'log.md', 'SCHEMA.md', 'entities/a-cloth.md', 'raw/pointers/02-in.md', 'raw/inv-2026-10-03.json')]
    json.dump(up, open(os.path.join(W, 'up.json'), 'w')); rc, out = run('drift', L, os.path.join(W, 'up.json'))
    check('N4: drift ignores the uploaded wiki layer and directory entries', rc == 0, out)
    chg = copy.deepcopy(INV); chg[1]['Hashes']['sha256'] = 'e' * 64; json.dump(chg, open(os.path.join(W, 'chg.json'), 'w'))
    check('N4 control: drift reports a changed raw file', run('drift', L, os.path.join(W, 'chg.json'))[0] == 1)
    # C2-N11: Google-native file (no sha256) is labelled, not blank
    inv = INV + [{'Path': '02 In/notes', 'Name': 'notes', 'Size': 0, 'IsDir': False, 'Hashes': {}}]
    setup(inv=inv); build()
    check('N11: a file without a Drive sha256 is labelled', 'no Drive sha256' in open(os.path.join(W, 'wiki', 'raw/pointers/02-in.md')).read())
    # C2-N12: the log lists changed pointers
    inv = copy.deepcopy(INV); setup(inv=inv); build(); inv[2]['Hashes']['sha256'] = 'f' * 64
    json.dump(inv, open(os.path.join(W, 'inv-2026-10-03.json'), 'w')); build(date='2026-10-06')
    check('N12: a changed raw file shows its pointer under changed', 'raw/pointers/02-in.md' in open(os.path.join(W, 'wiki', 'log.md')).read().split('## [2026-10-06]')[1])
    assert not MISSES, "\n".join(MISSES)


def test_without_pyyaml_a_malformed_value_is_refused_not_read_as_text():
    import importlib.util
    spec = importlib.util.spec_from_file_location("libwiki_port", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    good = '---\ntitle: "Tiling"\ntags: ["tile"]\nplain: hello\n---\nbody'
    assert mod._subset_load(good[4:good.index("\n---\n", 4)]) == {"title": "Tiling", "tags": ["tile"], "plain": "hello"}
    import pytest
    for bad in ('title: [unclosed\ntags: ["tile"]', 'title "no colon"', 'tags: {"a": 1'):
        with pytest.raises(ValueError):
            mod._subset_load(bad)
