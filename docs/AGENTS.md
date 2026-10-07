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
2. **Generated pages are never hand-edited.** Inspection schemas under `docs/schemas/inspect/` are rendered by `src/scripts/mixar/modules/lampway_tools/inspect/schema.py --check` and registered in the rail catalog.  The tool reference is rendered from the live registry (the docs lane's
   `docs/gen_tools.py`, with `--check`); the same generator owns the live agent/MCP count paragraph in `lampway/connect-ai-apps.md`. Change the registry, then regenerate both pages; their counts come from `server/lampway_server/agent_files/generate.py:registry_counts`, never a hand-maintained total. A page that cannot be regenerated on your base is
   left alone and the gap reported.
3. **Public paths only.** These files are published: no home paths, hostnames, account names or private documents; a private
   location is written as a placeholder (`<workspace>`), and a link points only at a path in this repository or a public URL.
4. **No media metadata.** Images and videos carry no EXIF, XMP, IPTC, C2PA, GPS, encoder or creation tags
   (`prepublish_gate.py --media docs`).
5. **Never contact the upstream service, in prose too:** documentation never tells a user to sign in to, download from or
   report to the upstream project's hosted services. Attribution uses the brand module's approved wording.
6. **Licences:** every file carries SPDX lines (an HTML comment at the top of Markdown) or a `REUSE.toml` entry.
7. **Authorized external ledgers:** `gen_status_ledger.py` verifies original row identities, order and content against the supplied recount, retains historical verdicts separately from current code/test evidence, and obtains header counts from `registry_counts`. Full identities and per-contract private evidence remain outside the repository; the public report carries original ordinals and source hashes. A registry entry, cited file or refusal is not full-contract verification; retain exact remaining gaps and do not upgrade them from enumeration alone.

Acceptance audits include the complete current issue body and acceptance-bearing comments. Preserve existing criterion identities, append new criteria, and distinguish historical snapshots from the current denominator. A focused or baseline-relative result never substitutes for a missing aggregate gate receipt.

Network and render contract pages cite current public modules and operator behavior, including loopback, trust verification, render refusal, main-thread restoration and device preference ownership. Missing historical private document maps cannot stand in for public links.

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

Recovered public release assets retain exact release/file digests, installed-path provenance, original bytes and upstream licence attribution. Do not replace missing authored translations with fabricated content or force original dub timings into fallback schedules.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the documentation rules (measured claims, generated pages, public paths, media metadata) were spread across the gate, the README and the reports | six invariants with their gates and the owner | captain ruling, 2026-10-05 |
| 2026-10-06 | the canon beside the docs | coordinator: "GO for rail row 1" | a reader of docs/ could not tell the canon from the user docs | docs/canon named, with its own contract | captain ruling, 2026-10-06 |
| 2026-10-07 | MCP wrapper contract receipt | captain: scoped MCP wrapper and migration | new transport, observation, schemas and offline data needed reproducible ownership and evidence | document the scoped implementation, generated checks and explicit limits above | scoped contract evidence in docs/reports/mcp-wrapper-migration.md |
| 2026-10-07 | generated connection catalogue counts | captain: complete issue 2 G13 | the connection guide retained a stale hand-written tool count | generate and check both the tool reference and connection count paragraph from the live registry | generator checks and count falsifiers |
| 2026-10-07 | authoritative external ledger recount | captain: issue 2 AC64 | stale classes and counts could be copied while private source identities leaked into public reports | verify row identity/content, generate live registry counts, retain per-row evidence and gaps privately, publish ordinal-only reconciliation | source-drift, privacy-output and manual-evidence falsifiers |
| 2026-10-07 | complete issue acceptance inventory | captain: include G23 and G24–G26 | body-only review silently omitted comment criteria and overstated aggregate acceptance | preserve original rows, append comment criteria, source-pin all revisions and qualify absent gate evidence | complete73-row source reconciliation |
| 2026-10-07 | public network and render contracts | captain: inherited no-red audit | absent private maps and stale names made documentation checks fail despite current implementations | cite current guarded behavior and public modules, preserve certificate/egress/render controls and observed limitations | full network/render test-contract suite |

| 2026-10-07 | original subtitle release recovery | captain: fix missing bundled originals without private transfer | public source omitted eight authored dub tracks and runtime packs contain no subtitles | verify official archive digest and installer file identities, preserve original bytes/timing and source licence | public release recovery hashes and maintained locale validation |
