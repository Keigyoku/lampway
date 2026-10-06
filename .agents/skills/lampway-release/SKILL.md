---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
name: lampway-release
description: "Before any push, publish, tag or main advance of the public Lampway repository: the pre-publish gate (PII, tokens, signed URLs, media metadata), the owner patterns kept outside the tree, noreply identity, REUSE, the rail and its DOX closeout row, and who may move main."
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: deterministic
---

# Pre-publish and release

The repository is public. Anything committed is published the moment its branch is pushed, so the gate runs before the push,
not after. Load `lampway-coding-guidelines` first.

## 1. Every push

```bash
git config core.hooksPath .githooks                       # once per clone: the pre-push hook runs the gate
python3 scripts/lampway/prepublish_gate.py --self-test     # the gate proves it sees one planted offender of each kind
python3 scripts/lampway/prepublish_gate.py --tree .        # every text file in the working tree
python3 scripts/lampway/prepublish_gate.py --git origin/lp/wave5..HEAD   # your new commits: identities, messages, added lines
python3 scripts/lampway/prepublish_gate.py --media docs    # no EXIF/XMP/C2PA/GPS/encoder tags in shipped media
python3 rail/rail.py check                                 # the rail (also in CI)
```

- The gate blocks personal emails, home paths, owner usernames and paths, account ids, API keys, JWTs, bearer tokens, private
  keys, signed URLs and media metadata. A match prints only the first four characters of a secret.
- **The maintainer's own patterns are never in the repository.** The hook reads `PII_OWNER_EMAIL_RE`, `PII_OWNER_USER_RE` and
  `PII_OWNER_PATH_RE` from a `pii_owner.env` file (mode 0600) in the shared git directory; CI reads repository secrets of the same
  names. Never print, copy or commit that file. Putting an owner value into a tracked file to make a test pass is the defect the
  gate exists for.
- A known-fake value goes in `scripts/lampway/pii_allow.txt`, exactly, with the reason on the same line.
- Commit as your GitHub noreply address; the gate refuses any other author or committer email on a new commit.
- A blocked push is fixed by amending your own unpushed commits; never by `--no-verify`, never by widening the allow-list for a
  real value.

## 2. Licences

Every new file carries SPDX copyright and licence lines: an HTML comment in Markdown, a `#` comment in YAML frontmatter, code
comments elsewhere; a file that cannot carry a comment gets a `REUSE.toml` entry. CI runs `reuse lint`
(`.github/workflows/reuse-lint.yml`); locally `reuse --no-multiprocessing lint`. Upstream-original files keep their upstream
copyright; Lampway's own are `Lampway contributors`.

## 3. Never contact the upstream service, in release artefacts too

Links, update checks and telemetry resolve to Lampway's server or this repository. `tests/lampway` holds the host and brand
gates (`test_lampway_no_mixar_hosts.py`, `test_site_links.py`, the brand-word and shipped-metadata gates); run them before any
release build.

## 4. Branches, main and tags

- Push only your own `lp/<lane>` branch; never force, never `main`, never another lane's branch.
- `main` is fast-forwarded to a gated integration tip only on the captain's word, after the coordinator's final gate.
- Before a tag: add one row to the root `AGENTS.md` DOX closeout table naming the tag, what annealed (the rails and skills the
  increment changed) and the evidence, then `python3 rail/rail.py closeout --tag <tag>`; run the full suites and the gate on
  the exact commit you will tag; read the reports, not the exit codes alone.

## 5. Evidence

A release report states, for each gate, the command and its result, and names every suite that did not run (and why). A
skipped suite is not a pass. Dollar figures and live runs are quoted from their receipts.

Provenance: `scripts/lampway/prepublish_gate.py`, `.githooks/pre-push`, `.github/workflows/pii-gate.yml`, `CONTRIBUTING.md`,
the build order's lanes and main rulings (2026-10-05), Titan's `dox-closeout` directive.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the pre-publish and release steps were spread across the hook, CI, CONTRIBUTING and the build order | one procedure for every push and every tag, with the DOX closeout row read by `rail.py closeout` | captain ruling, 2026-10-05 |
