# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/libwiki/libwiki.py, sha256 4f703ebf3ef7) on 2026-10-06. The header below, with the measured rules behind
# the code, is the original's; the wording addressed to one owner reads 'the owner', the approved folders may come from the spec (approved_under), and
# frontmatter is read by PyYAML when present, else by the JSON-valued subset this publisher writes (Blender's python carries no PyYAML).
# SPIKE (2026-10-03): deterministic publisher for a Drive asset library as LLM wikis (Karpathy pattern,
# per the llm-wiki skill). The library root IS the wiki root on Drive: SCHEMA.md, index.md, log.md,
# entities/ concepts/ comparisons/ queries/ and raw/ are uploaded beside the library's own folders, which are the
# immutable raw layer. raw/pointers/ holds one pointer page per library folder carrying Drive's own sha256 for every
# file, so the raw layer is pinned without downloading it.
# <out_dir> is a LOCAL generated directory holding only the wiki layer; it is never the library itself. Upload it with
# `rclone copy <out_dir> <library root>` and delete the wiki-layer paths it no longer contains (the log's "removed").
# Models (the agent) write judgment into authored pages and the entity spec; this tool performs every write:
#   build  <spec.json> <inventory.json> <authored_dir> <out_dir> --date YYYY-MM-DD --log "message" [--scanned YYYY-MM-DD]
#   lint   <out_dir>
#   drift  <out_dir> <new_inventory.json>      (what changed on Drive since the wiki's inventory)
# Inventory: `rclone lsjson -R --hash --files-only "<remote>:<library root>" > <name>-YYYY-MM-DD<x>.json` (directory
# entries are also accepted and skipped). Pages generated here are never hand-edited; change the spec or the authored
# page and rebuild.
# v2 (wiki critique round 1): created/updated survive rebuilds (updated moves only when a page changes); frontmatter
# values are JSON-quoted and lint validates it as YAML; the tag check cannot be skipped; pointers carry full sha256,
# their own hash under pointer_sha256, the inventory's hash, a per-subfolder summary and an explicit truncation notice;
# the log lists pages added / removed / changed; the index opens with what is ready for the owner's decision.
# v3 (wiki critique round 2): out is normalised and must be a wiki (or absent/empty) before it is replaced, and the
# swap keeps the old wiki until the new one is in place; staging is marked and removed on any failure; the spec and
# authored pages are validated up front with named errors; authored pages cannot overwrite generated ones and their
# type must match their folder; proposals must be booleans with a reason when false and an approval record when
# approved; one inventory loader (directories skipped, wiki layer filtered) serves build and drift; lint checks status,
# dates, index totals, pointer hashes against the inventory, and the log format; the log's changed list covers raw/.
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = _sys.argv[1:]
if __name__ == '__main__' and len(_A) < 1:
    if not _A: _ax.home(__file__, "Deterministic publisher for a Drive asset library as LLM wikis")
    else: print(f'error: {len(_A)} argument(s); at least 1 needed')
    _ax.helps(['python3 scripts/libwiki/libwiki.py --help']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import argparse, hashlib, json, os, re, shutil, sys
from collections import defaultdict
try:
    import yaml
except ImportError:                       # Blender's python: read the JSON-valued subset this publisher writes
    yaml = None

REQ = ('title', 'created', 'updated', 'type', 'tags', 'sources')
LINK = re.compile(r'\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]')
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
SLUG = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
ROWS_MAX = 400
MARK = '.libwiki-staging'
WIKI_LAYER = ('SCHEMA.md', 'index.md', 'log.md', 'entities/', 'concepts/', 'comparisons/', 'queries/', 'raw/')
DIR_TYPE = {'entities': 'entity', 'concepts': 'concept', 'comparisons': 'comparison', 'queries': 'query'}
STATUS = ('raw', 'working', 'candidate', 'approved', 'archived', 'superseded')
CONF = ('high', 'medium', 'low')
E_REQ = ('slug', 'title', 'tags', 'raw', 'oneline', 'summary', 'related')
E_OPT = ('status', 'confidence', 'contested', 'proposed', 'not_proposed_reason', 'approval_record', 'facts', 'table',
         'match', 'open', 'extra_sources', 'created')
APPROVED_UNDER = ('09 Approved Textures/', 'Parts Library/Approved/')   # the default; a spec may name its own (approved_under)


class Refused(Exception):
    pass


def slug(s):
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', s.lower())).strip('-')


def front(meta):
    out = ['---']
    for k, v in meta.items():
        if v is None: continue
        out.append(f'{k}: {json.dumps(v, ensure_ascii=False)}')     # JSON is valid YAML: quoting is never forgotten
    return '\n'.join(out + ['---', ''])


def _subset_load(text):
    """`key: value` lines whose value is JSON (what front() writes) or a bare one-line scalar; anything else is refused, never guessed."""
    out = {}
    for i, line in enumerate(text.split('\n'), 1):
        if not line.strip():
            continue
        k, sep, v = line.partition(':')
        if not sep or not re.fullmatch(r'[A-Za-z_][\w-]*', k.strip()):
            raise ValueError(f'frontmatter line {i} is not `key: value`')
        v = v.strip()
        if v[:1] in '["{' or v in ('true', 'false', 'null') or re.fullmatch(r'-?\d+(\.\d+)?', v or 'x'):
            out[k.strip()] = json.loads(v)              # a JSON value must parse: '[unclosed' is an error, not a string
        else:
            out[k.strip()] = v.strip("'")
    return out


def parse(md):
    if not md.startswith('---\n'): return {}, md
    end = md.index('\n---\n', 4)
    meta = (yaml.safe_load(md[4:end]) if yaml is not None else _subset_load(md[4:end])) or {}
    if not isinstance(meta, dict): raise ValueError('frontmatter is not a mapping')
    return {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in meta.items()}, md[end + 5:]


def human(n):
    for u in ('B', 'KiB', 'MiB', 'GiB'):
        if n < 1024 or u == 'GiB': return f'{n:.1f} {u}' if u != 'B' else f'{n} B'
        n /= 1024


def sha_file(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def sha_cell(x):
    h = (x.get('Hashes') or {}).get('sha256')
    return f'`{h}`' if h else '(no Drive sha256: Google-native document)'


def load_inventory(path):
    """Files only (directory entries skipped), the wiki's own layer filtered out. Shared by build, lint and drift."""
    rows = json.load(open(path))
    if not isinstance(rows, list): raise Refused(f'{path}: inventory is not a JSON list (rclone lsjson output)')
    out = []
    for x in rows:
        if x.get('IsDir'): continue
        if 'Path' not in x or 'Size' not in x: raise Refused(f'{path}: entry without Path/Size: {str(x)[:120]}')
        if x['Path'].startswith(WIKI_LAYER): continue
        out.append(x)
    return out


def one_line(v):
    return isinstance(v, str) and v.strip() and '\n' not in v and '\r' not in v


def validate_spec(spec, inv_paths):
    errs = []
    for k in ('name', 'drive_path', 'entities'):
        if k not in spec: errs.append(f'spec: missing {k!r}')
    if errs: raise Refused('; '.join(errs))
    seen = set()
    for i, e in enumerate(spec['entities']):
        who = f'entity {e.get("slug", f"#{i}")!r}'
        for k in E_REQ:
            if k not in e: errs.append(f'{who}: missing {k!r}')
        unknown = sorted(set(e) - set(E_REQ) - set(E_OPT))
        if unknown: errs.append(f'{who}: unknown key(s) {unknown} (typo?)')
        s = e.get('slug', '')
        if not SLUG.match(str(s)): errs.append(f'{who}: slug must be lowercase-hyphenated with no path parts')
        if s in seen: errs.append(f'{who}: duplicate slug')
        seen.add(s)
        for k in ('title', 'oneline'):
            if k in e and not one_line(e[k]): errs.append(f'{who}: {k} must be one non-empty line')
        if not isinstance(e.get('tags', []), list): errs.append(f'{who}: tags must be a list')
        if not isinstance(e.get('raw', []), list) or not e.get('raw'): errs.append(f'{who}: raw must be a non-empty list of library folders')
        st = e.get('status')
        if st is not None and st not in STATUS: errs.append(f'{who}: status {st!r} not in {STATUS}')
        if e.get('confidence', 'medium') not in CONF: errs.append(f'{who}: confidence not in {CONF}')
        if 'created' in e and not DATE.match(str(e['created'])): errs.append(f'{who}: created must be YYYY-MM-DD')
        if 'proposed' in e:
            p = e['proposed']
            if not isinstance(p, bool): errs.append(f'{who}: proposed must be true or false, not {p!r}')
            elif p is False and not one_line(e.get('not_proposed_reason', '')): errs.append(f'{who}: proposed false needs a one-line not_proposed_reason')
            elif p is True and st not in ('candidate',): errs.append(f'{who}: only a candidate can be proposed (status {st!r})')
        elif 'not_proposed_reason' in e: errs.append(f'{who}: not_proposed_reason without proposed: false')
        if st == 'approved':
            rec = e.get('approval_record')
            if not rec or not rec.startswith(tuple(spec.get('approved_under') or APPROVED_UNDER)) or not rec.endswith('APPROVAL.json') or rec not in inv_paths:
                errs.append(f'{who}: status approved needs approval_record = an APPROVAL.json under {APPROVED_UNDER} that is in the inventory')
    if errs: raise Refused('spec refused:\n  ' + '\n  '.join(errs))


def safe_out(out):
    """out must be absent, empty, or a wiki this tool wrote (SCHEMA.md + index.md + log.md and nothing but the layer)."""
    if not os.path.exists(out): return
    if not os.path.isdir(out): raise Refused(f'{out} exists and is not a directory')
    names = set(os.listdir(out))
    if not names: return
    if not {'SCHEMA.md', 'index.md', 'log.md'} <= names:
        raise Refused(f'{out} is not a wiki written by this tool (no SCHEMA.md + index.md + log.md); refusing to replace it')
    stray = sorted(n for n in names if n not in ('SCHEMA.md', 'index.md', 'log.md', 'entities', 'concepts', 'comparisons', 'queries', 'raw'))
    if stray: raise Refused(f'{out} holds files outside the wiki layer {stray}; refusing to replace it')


def build(a):
    if not DATE.match(a.date): raise Refused(f'--date {a.date!r} is not YYYY-MM-DD')
    out = os.path.normpath(os.path.abspath(a.out)); tmp = out + '.staging'; old = out + '.previous'
    if os.path.commonpath([out, os.path.abspath(a.authored)]) == out: raise Refused('authored dir must not be inside out')
    safe_out(out)
    for p in (tmp, old):
        if os.path.exists(p):
            if not os.path.isfile(os.path.join(p, MARK)): raise Refused(f'{p} exists and is not this tool\'s staging; remove it by hand')
            shutil.rmtree(p)
    spec = json.load(open(a.spec)); inv = load_inventory(a.inventory); inv_paths = {f['Path'] for f in inv}
    validate_spec(spec, inv_paths)
    if a.scanned: SCAN = a.scanned
    else:
        m_ = re.search(r'(\d{4}-\d{2}-\d{2})', os.path.basename(a.inventory))
        if not m_: raise Refused('the inventory file name carries no YYYY-MM-DD scan date; pass --scanned')
        SCAN = m_.group(1)
    if not DATE.match(SCAN): raise Refused(f'--scanned {SCAN!r} is not YYYY-MM-DD')
    os.makedirs(tmp); open(os.path.join(tmp, MARK), 'w').write('staging dir of libwiki.py; removed on success or failure\n')
    try:
        _build(a, spec, inv, out, tmp, SCAN)
        if os.path.exists(out): os.rename(out, old)
        os.rename(tmp, out)
        os.remove(os.path.join(out, MARK))
        if os.path.exists(old): shutil.rmtree(old)
    except BaseException:
        if os.path.isdir(tmp) and os.path.isfile(os.path.join(tmp, MARK)): shutil.rmtree(tmp)
        if os.path.exists(old) and not os.path.exists(out): os.rename(old, out)      # put the previous wiki back
        raise


def _build(a, spec, inv, out, tmp, SCAN):
    D = a.date
    for d in ('raw/pointers', 'entities', 'concepts', 'comparisons', 'queries'): os.makedirs(os.path.join(tmp, d))
    prev = {}                                                  # prior pages: keep created; updated only on change
    if os.path.isdir(out):
        for r, _, fs in os.walk(out):
            for f in fs:
                if f.endswith('.md'):
                    rel = os.path.relpath(os.path.join(r, f), out)
                    try: prev[rel] = parse(open(os.path.join(r, f)).read())
                    except Exception: prev[rel] = ({}, None)     # unparseable prior page: still a prior page (counts as changed)
    written = set()

    def write(rel, meta, body):
        written.add(rel)
        meta = {k: v for k, v in meta.items() if v is not None}   # unset fields are absent, as in the written page
        pm, pb = prev.get(rel, ({}, None))
        meta['created'] = pm.get('created') or meta.get('created') or D
        same = pb is not None and pb == body and {k: v for k, v in pm.items() if k != 'updated'} == {k: v for k, v in meta.items() if k != 'updated'}
        meta['updated'] = pm.get('updated', D) if same else D
        order = ['title', 'created', 'updated'] + [k for k in meta if k not in ('title', 'created', 'updated')]
        open(os.path.join(tmp, rel), 'w').write(front({k: meta[k] for k in order if k in meta}) + body)
    inv_sha = sha_file(a.inventory); inv_name = os.path.basename(a.inventory)
    # ---- raw pointers
    groups = defaultdict(list)
    for f in inv:
        parts = f['Path'].split('/'); depth = spec.get('pointer_depth', 1)
        top = '/'.join(parts[:min(depth, len(parts) - 1)]) if len(parts) > 1 else '(library root files)'
        groups[top].append(f)
    pointers = {}
    for top, files in sorted(groups.items()):
        files = sorted(files, key=lambda x: x['Path']); depth = len(top.split('/'))
        subs = defaultdict(lambda: [0, 0])
        for x in files:
            p = x['Path'].split('/'); key = p[depth] if len(p) > depth + 1 else '(files directly here)'
            subs[key][0] += 1; subs[key][1] += x['Size']
        rows = [f"| `{x['Path']}` | {human(x['Size'])} | {sha_cell(x)} |" for x in files]
        trunc = len(rows) > ROWS_MAX
        body = '\n'.join([f'# Raw pointer: {top}', '', f'Drive path: `{spec["drive_path"]}/{top if top != "(library root files)" else ""}`',
                          f'Files: {len(files)} | Total: {human(sum(x["Size"] for x in files))} | Scanned: {SCAN} via `rclone lsjson -R --hash --files-only` (Drive-side sha256; nothing downloaded)',
                          '', 'Immutable source. Wiki pages cite this pointer; the files themselves are never edited by the wiki.', ''] +
                         (['## Subfolders', '', '| subfolder | files | size |', '|---|---|---|'] + [f'| `{k}` | {v[0]} | {human(v[1])} |' for k, v in sorted(subs.items())] + [''] if len(subs) > 1 else []) +
                         ([f'**TRUNCATED:** the file table below shows the first {ROWS_MAX} of {len(rows)} files; every file and its sha256 is in `raw/{inv_name}`.', ''] if trunc else []) +
                         ['| file | size | sha256 |', '|---|---|---|'] + rows[:ROWS_MAX] + [''])
        meta = {'drive_path': f'{spec["drive_path"]}/{top}', 'scanned': SCAN, 'files': len(files), 'bytes': sum(x['Size'] for x in files),
                'truncated': trunc, 'rows_shown': min(len(rows), ROWS_MAX), 'inventory_file': f'raw/{inv_name}',
                'inventory_sha256': inv_sha, 'pointer_sha256': hashlib.sha256(body.encode()).hexdigest()}
        name = f'raw/pointers/{slug(top)}.md'
        if name in written: raise Refused(f'two library folders map to the same pointer {name}')
        written.add(name); open(os.path.join(tmp, name), 'w').write(front(meta) + body); pointers[top] = name
    shutil.copy(a.inventory, os.path.join(tmp, 'raw', inv_name))
    # ---- generated entity pages
    pages = {}
    for e in spec['entities']:
        miss = [t for t in e['raw'] if t not in pointers]
        if miss: raise Refused(f'entity {e["slug"]}: raw folder(s) not in the inventory: {miss}')
        meta = {'title': e['title'], 'created': e.get('created'), 'type': 'entity', 'tags': e['tags'],
                'sources': [pointers[t] for t in e['raw']] + e.get('extra_sources', []),
                'confidence': e.get('confidence', 'medium'), 'status': e.get('status'), 'proposed_for_approval': e.get('proposed'),
                'not_proposed_reason': e.get('not_proposed_reason'), 'approval_record': e.get('approval_record'),
                'contested': e.get('contested'), 'oneline': e['oneline']}
        files = [f for t in e['raw'] for f in groups[t]]
        lines = [f'# {e["title"]}', '', e['summary'], '']
        if e.get('proposed') is True: lines += ['**Proposed for approval** - ready for the owner\'s decision.', '']
        elif e.get('proposed') is False: lines += [f'**Not proposed for approval:** {e["not_proposed_reason"]}', '']
        if e.get('status') == 'approved': lines += [f'**Approved by the owner** - record: `{e["approval_record"]}`.', '']
        if e.get('facts'): lines += ['## Facts', ''] + [f'- {x}' for x in e['facts']] + ['']
        if e.get('table'): lines += e['table'] + ['']
        lines += ['## Raw layer', ''] + [f'- `{t}/` - {len(groups[t])} files, {human(sum(x["Size"] for x in groups[t]))} - pointer [[{pointers[t][:-3]}]]' for t in e['raw']] + ['']
        if e.get('match'):
            mine = sorted((f for f in files if any(m in f['Path'] for m in e['match'])), key=lambda x: x['Path'])
            if not mine: raise Refused(f'entity {e["slug"]}: match {e["match"]} selects no file')
            lines += ['## Files', '', '| file | size | sha256 |', '|---|---|---|'] + \
                     [f"| `{f['Path']}` | {human(f['Size'])} | {sha_cell(f)} |" for f in mine] + ['']
        else:
            kinds = defaultdict(int)
            for f in files: kinds[os.path.splitext(f['Path'])[1].lower() or '(none)'] += 1
            lines += ['File types: ' + ', '.join(f'{k} x{v}' for k, v in sorted(kinds.items())), '']
        if e.get('open'): lines += ['## Open / unproven', ''] + [f'- {x}' for x in e['open']] + ['']
        lines += ['## Related', ''] + [f'- [[{x}]]' for x in e['related']] + ['']
        name = f'entities/{e["slug"]}.md'; write(name, meta, '\n'.join(lines)); pages[name] = (e['title'], e['oneline'], 'entity')
    # ---- authored pages
    if not os.path.isfile(os.path.join(a.authored, 'SCHEMA.md')): raise Refused(f'{a.authored}: no SCHEMA.md')
    for root, _, fs in os.walk(a.authored):
        for f in sorted(fs):
            if not f.endswith('.md'): continue
            rel = os.path.relpath(os.path.join(root, f), a.authored)
            if rel == 'SCHEMA.md': shutil.copy(os.path.join(root, f), os.path.join(tmp, rel)); continue
            top = rel.split(os.sep)[0]
            if top not in DIR_TYPE or top == 'entities':
                raise Refused(f'authored {rel}: authored pages live in concepts/, comparisons/ or queries/ (entities are generated from the spec)')
            try: meta, body = parse(open(os.path.join(root, f)).read())
            except Exception as ex: raise Refused(f'authored {rel}: frontmatter does not parse ({ex.__class__.__name__}: {str(ex)[:120]})')
            if not meta: raise Refused(f'authored {rel}: no frontmatter')
            if meta.get('type') != DIR_TYPE[top]: raise Refused(f'authored {rel}: type {meta.get("type")!r} but it lives in {top}/ ({DIR_TYPE[top]})')
            for k in ('title', 'oneline'):
                if not one_line(meta.get(k)): raise Refused(f'authored {rel}: {k} must be one non-empty line')
            if not isinstance(meta.get('tags'), list): raise Refused(f'authored {rel}: tags must be a list')
            meta.pop('updated', None)
            os.makedirs(os.path.dirname(os.path.join(tmp, rel)), exist_ok=True)
            write(rel, meta, body.lstrip('\n')); pages[rel] = (meta['title'], meta['oneline'], meta['type'])
    # ---- index
    sec = {'entity': 'Entities', 'concept': 'Concepts', 'comparison': 'Comparisons', 'query': 'Queries'}
    idx = [f'# {spec["name"]} - Wiki Index', '', '> Content catalog: every wiki page under its type with a one-line summary. Read SCHEMA.md first, then this.',
           f'> Last updated: {D} | Wiki pages: {len(pages)} (plus SCHEMA, index, log) | Raw pointers: {len(pointers)} covering {len(inv)} files', '']
    yes = sorted((e['title'], e['slug']) for e in spec['entities'] if e.get('proposed') is True)
    no = sorted((e['title'], e['slug'], e['not_proposed_reason']) for e in spec['entities'] if e.get('proposed') is False)
    appr = sorted((e['title'], e['slug']) for e in spec['entities'] if e.get('status') == 'approved')
    if yes: idx += ['## Proposed for approval - ready for the owner\'s decision', ''] + [f'- [[entities/{s}|{t}]]' for t, s in yes] + ['']
    if no: idx += ['## Not proposed for approval', ''] + [f'- [[entities/{s}|{t}]] - {r}' for t, s, r in no] + ['']
    if appr: idx += ['## Approved by the owner', ''] + [f'- [[entities/{s}|{t}]]' for t, s in appr] + ['']
    for t, title in sec.items():
        items = sorted((v[0], k, v[1]) for k, v in pages.items() if v[2] == t)
        if items: idx += [f'## {title}', ''] + [f'- [[{k[:-3]}|{n}]] - {o}' for n, k, o in items] + ['']
    idx += ['## Raw pointers', ''] + [f'- [[{v[:-3]}|{k}]]' for k, v in sorted(pointers.items())] + ['']
    open(os.path.join(tmp, 'index.md'), 'w').write('\n'.join(idx))
    # ---- log (append-only), with the page delta (pointers included)
    prev_log = os.path.join(out, 'log.md')
    log = open(prev_log).read() if os.path.exists(prev_log) else f'# {spec["name"]} - Wiki Log\n\n> Chronological record of wiki actions. Append-only. Format: `## [YYYY-MM-DD] action | subject`.\n'
    if '\n' in a.log: raise Refused('--log must be one line')
    newp = set(pages) | set(pointers.values()); oldp = {k for k in prev if k not in ('index.md', 'log.md', 'SCHEMA.md')}
    changed = sorted(k for k in newp & oldp if open(os.path.join(tmp, k)).read() != open(os.path.join(out, k)).read())
    log += (f'\n## [{D}] {a.action} | {a.log}\n- pages: {len(pages)} | raw pointers: {len(pointers)} | inventory: {inv_name} ({len(inv)} files, sha256 {inv_sha[:16]})\n'
            f'- added: {", ".join(sorted(newp - oldp)) or "none"}\n- removed: {", ".join(sorted(oldp - newp)) or "none"}\n- changed: {", ".join(changed) or "none"}\n')
    open(os.path.join(tmp, 'log.md'), 'w').write(log)
    problems = lint_dir(tmp)
    if problems:
        raise Refused('\n'.join(problems) + f'\nrefused: {len(problems)} lint problems')
    print(json.dumps({'pages': len(pages), 'pointers': len(pointers), 'out': out}))


def lint_dir(root):
    probs = []; tax = None
    sch = os.path.join(root, 'SCHEMA.md')
    if not os.path.exists(sch): probs.append('SCHEMA.md missing')
    else:
        m = re.search(r'## Tag Taxonomy\n(.*?)(?=\n## |\Z)', open(sch).read(), re.S)
        if not m: probs.append('SCHEMA.md has no "## Tag Taxonomy" section')
        else:
            tax = set(re.findall(r'`([a-z0-9-]+)`', m.group(1)))
            if not tax: probs.append('SCHEMA.md taxonomy declares no tags')
    invs = [p for p in os.listdir(os.path.join(root, 'raw'))] if os.path.isdir(os.path.join(root, 'raw')) else []
    invs = [p for p in invs if p.endswith('.json')]
    inv = {}
    if len(invs) != 1: probs.append(f'raw/ must hold exactly one inventory JSON, found {invs}')
    else:
        try: inv = {x['Path']: x for x in load_inventory(os.path.join(root, 'raw', invs[0]))}
        except Exception as ex: probs.append(f'raw/{invs[0]}: {ex}')
    names = set()
    for r, _, fs in os.walk(root):
        for f in fs:
            if f.endswith('.md'): names.add(os.path.relpath(os.path.join(r, f), root)[:-3])
    inbound = defaultdict(int); idx = open(os.path.join(root, 'index.md')).read() if os.path.exists(os.path.join(root, 'index.md')) else ''
    n_pages = n_ptr = 0; ptr_files = set()
    for n in sorted(names):
        if n in ('index', 'log', 'SCHEMA'): continue
        try: meta, body = parse(open(os.path.join(root, n + '.md')).read())
        except Exception as e: probs.append(f'{n}: frontmatter is not valid YAML ({e.__class__.__name__})'); continue
        if n.startswith('raw/pointers/'):
            n_ptr += 1
            if meta.get('pointer_sha256') != hashlib.sha256(body.encode()).hexdigest(): probs.append(f'{n}: pointer_sha256 does not match its body')
            for path, sha in re.findall(r'^\| `([^`]+)` \| [^|]+ \| `([0-9a-f]{64})` \|$', body, re.M):
                if path in inv:
                    ptr_files.add(path)
                    if (inv[path].get('Hashes') or {}).get('sha256') != sha: probs.append(f'{n}: {path} sha256 differs from the inventory')
                elif inv: probs.append(f'{n}: {path} is not in the inventory')
            continue
        if n.startswith('raw/'): continue
        n_pages += 1
        for k in REQ:
            if k not in meta: probs.append(f'{n}: missing frontmatter {k}')
        top = n.split('/')[0]
        if top in DIR_TYPE and meta.get('type') != DIR_TYPE[top]: probs.append(f'{n}: type {meta.get("type")!r} in {top}/')
        for k in ('created', 'updated'):
            if k in meta and not DATE.match(str(meta[k])): probs.append(f'{n}: {k} {meta[k]!r} is not YYYY-MM-DD')
        if str(meta.get('updated', '')) < str(meta.get('created', '')): probs.append(f'{n}: updated before created')
        for k in ('title', 'oneline'):
            if k in meta and not one_line(meta[k]): probs.append(f'{n}: {k} must be one line')
        if 'status' in meta and meta['status'] not in STATUS: probs.append(f'{n}: status {meta["status"]!r} not in {STATUS}')
        if 'confidence' in meta and meta['confidence'] not in CONF: probs.append(f'{n}: confidence {meta["confidence"]!r}')
        if meta.get('status') == 'approved':
            rec = meta.get('approval_record')
            if not rec or (inv and rec not in inv): probs.append(f'{n}: status approved without an approval_record in the inventory')
        if 'proposed_for_approval' in meta and not isinstance(meta['proposed_for_approval'], bool): probs.append(f'{n}: proposed_for_approval must be a boolean')
        if meta.get('proposed_for_approval') is False and not meta.get('not_proposed_reason'): probs.append(f'{n}: not proposed without a reason')
        tags = meta.get('tags', [])
        if not isinstance(tags, list): probs.append(f'{n}: tags must be a list'); tags = []
        for t in tags:
            if tax is not None and t not in tax: probs.append(f'{n}: tag {t!r} not in SCHEMA taxonomy')
        links = set(LINK.findall(body))
        for l in links:
            if l.strip() not in names: probs.append(f'{n}: broken link [[{l}]]')
            else: inbound[l.strip()] += 1
        if len([l for l in links if not l.startswith('raw/')]) < 2: probs.append(f'{n}: fewer than 2 outbound wiki links')
        if f'[[{n}|' not in idx and f'[[{n}]]' not in idx: probs.append(f'{n}: not in index.md')
        if body.count('\n') > 220: probs.append(f'{n}: over ~200 lines - split it')
    for n in names:
        if n.startswith(('entities/', 'concepts/', 'comparisons/', 'queries/')) and inbound[n] == 0:
            probs.append(f'{n}: orphan (no inbound links)')
    m = re.search(r'Wiki pages: (\d+) \(plus SCHEMA, index, log\) \| Raw pointers: (\d+) covering (\d+) files', idx)
    if not m: probs.append('index.md: header totals line missing')
    elif (int(m.group(1)), int(m.group(2))) != (n_pages, n_ptr) or (inv and int(m.group(3)) != len(inv)):
        probs.append(f'index.md: header says {m.group(1)} pages / {m.group(2)} pointers / {m.group(3)} files; found {n_pages} / {n_ptr} / {len(inv)}')
    lp = os.path.join(root, 'log.md')
    if os.path.exists(lp):
        for i, line in enumerate(open(lp).read().split('\n')[1:], 2):
            if line and not (line.startswith('> ') or line.startswith('- ') or re.match(r'^## \[\d{4}-\d{2}-\d{2}\] \S+ \| ', line)):
                probs.append(f'log.md:{i}: not a log line ({line[:60]!r})')
    else: probs.append('log.md missing')
    return probs


def drift(out, new_inv):
    old = [p for p in os.listdir(os.path.join(out, 'raw')) if p.endswith('.json')]
    if len(old) != 1: raise Refused(f'expected one inventory JSON in {out}/raw, found {old}')
    A = {x['Path']: (x.get('Hashes') or {}).get('sha256') for x in load_inventory(os.path.join(out, 'raw', old[0]))}
    B = {x['Path']: (x.get('Hashes') or {}).get('sha256') for x in load_inventory(new_inv)}
    added = sorted(set(B) - set(A)); removed = sorted(set(A) - set(B)); changed = sorted(p for p in set(A) & set(B) if A[p] != B[p])
    print(json.dumps({'added': len(added), 'removed': len(removed), 'changed': len(changed), 'examples': (added + removed + changed)[:20]}, indent=1))
    return 1 if (added or removed or changed) else 0


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest='cmd', required=True)
    b = sp.add_parser('build'); b.add_argument('spec'); b.add_argument('inventory'); b.add_argument('authored'); b.add_argument('out')
    b.add_argument('--date', required=True); b.add_argument('--log', required=True); b.add_argument('--action', default='update')
    b.add_argument('--scanned', help='scan date of the inventory, when its file name does not carry one')
    l = sp.add_parser('lint'); l.add_argument('out')
    d = sp.add_parser('drift'); d.add_argument('out'); d.add_argument('inventory')
    a = ap.parse_args()
    try:
        if a.cmd == 'build': build(a)
        elif a.cmd == 'lint':
            p = lint_dir(a.out); print('\n'.join(p) or 'lint clean'); sys.exit(1 if p else 0)
        else: sys.exit(drift(a.out, a.inventory))
    except Refused as ex:
        _ax.refuse(f'refused: {ex}', ['python3 scripts/libwiki/libwiki.py --help'])


if __name__ == '__main__':
    main()
