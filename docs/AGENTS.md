---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: judgment
---

# docs — reports, roadmap and user documentation

Three kinds of document live here: **reports** (`docs/reports/`, one per wave or lane: what was built, how it was measured,
what was not run), the **roadmap**, and the **user documentation** (getting started, providers, privacy, spend, the tool
reference). The root `README.md` and `CONTRIBUTING.md` are the docs lane's too; link them, never copy them. `docs/rail.md`
explains this rail and belongs to `rail/`'s owner. `docs/canon/` is the algorithm canon, with its own contract
([`canon/AGENTS.md`](canon/AGENTS.md)).

## Invariants

1. **Every claim is measured or marked.** A number, a "works", a "live" names the run that showed it; what was never run is
   said plainly. Status words mean what the README defines (built, live, partial, planned).
2. **Generated pages are never hand-edited.** The tool reference is rendered from the live registry (the docs lane's
   `docs/gen_tools.py`, with `--check`); change the tool, then regenerate. A page that cannot be regenerated on your base is
   left alone and the gap reported.
3. **Public paths only.** These files are published: no home paths, hostnames, account names or private documents; a private
   location is written as a placeholder (`<workspace>`), and a link points only at a path in this repository or a public URL.
4. **No media metadata.** Images and videos carry no EXIF, XMP, IPTC, C2PA, GPS, encoder or creation tags
   (`prepublish_gate.py --media docs`).
5. **Never contact the upstream service, in prose too:** documentation never tells a user to sign in to, download from or
   report to the upstream project's hosted services. Attribution uses the brand module's approved wording.
6. **Licences:** every file carries SPDX lines (an HTML comment at the top of Markdown) or a `REUSE.toml` entry.

Native-only diagnostics state their actual source and pinned engine identities, rendered observations and exact owned
cleanup. Historical application binaries remain labelled historical; source controls and diagnostic observer corrections
do not replace matching-build, whole-client or account acceptance. Preserve failed runs when a later repair passes.
Native persistence and rendered transcript are distinct observations: correct stored user rows do not establish that
messages sent from another frontend appear in the pane. A compression diagnostic must commit native compaction before
testing its display, resume and Undo behavior; a native no-op cannot qualify those later steps.
Likewise, configured MCP entries and session-admitted routes are distinct. A native update acknowledgement does not
establish a completed restart; describe actual event ordering and current readiness, keeping source versions separate.

## Test

```bash
python3 scripts/lampway/prepublish_gate.py --tree docs
python3 scripts/lampway/prepublish_gate.py --media docs
server/.venv/bin/python docs/gen_tools.py --check     # once the generator is on your base
python -m pytest -q tests/lampway/test_shipped_metadata.py tests/lampway/test_site_links.py
```

## Owner

The docs lane (`lp/docs` at the time of writing) writes the user documentation and the root README and CONTRIBUTING; each lane
writes its own report; the integration lane lands them. What the product promises is the captain's.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the documentation rules (measured claims, generated pages, public paths, media metadata) were spread across the gate, the README and the reports | six invariants with their gates and the owner | captain ruling, 2026-10-05 |
| 2026-10-06 | the canon beside the docs | coordinator: "GO for rail row 1" | a reader of docs/ could not tell the canon from the user docs | docs/canon named, with its own contract | captain ruling, 2026-10-06 |
| 2026-10-10 | native diagnostics retain their acceptance limits | actual terminal undo/personality failures and valid-YAML observer correction | diagnostic source checks could be confused with matching application or account proof | native diagnostic paragraph: exact identities, failed runs, historical binaries and separate acceptance scopes | actual pinned native observations and process-refusing source controls retained |
| 2026-10-10 | distinguish native persistence from pane display | committed native compaction and resume preserve user rows, but actual scrolling finds only the first external user header | stored history was mistaken for proof of all rendered user turns | native diagnostic paragraph: observe persistence and rendering separately; require committed compaction before later proof | retained native frames and unchanged physical assertions expose the missing user rows |
| 2026-10-10 | distinguish configured MCP metadata and reload acknowledgement from readiness | 9af native CI advances past startup, then fails catalogue and environment-reload checks | disabled configurations were counted as admitted routes and asynchronous update acknowledgement was treated as a completed handshake | native diagnostic paragraph: explicit session admission and actual reload ordering, with source versions separately qualified | retained pinned native CI wire shows resolved blocked entries and progress before acknowledgement; repaired native proof remains required |
