---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
name: lampway-agent-tools
description: "Drive Lampway through its own tools instead of improvising: before running any step in the app (as its agent, over MCP, or from a test), find the tool that does it, read its description and refusals, follow the help it returns, respect the spend and egress gates, and keep the armour runbook's order."
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: judgment
---

# Use the tools Lampway already has

Lampway's agent tools are proven code with typed refusals, jails and receipts. A hand-written `run_blender_python` script that
does the same job has none of those, and it is the most common way an agent re-derives something the project already measured.

## Find the tool

1. `lampway_status` first: the project root, the interpreters, what mesh QA has set up, the running jobs and the batch tools.
2. The registry is the reference. Every tool's description, inputs and refusals are quoted from the live registry by the
   generators: `lampway_agent_files` (status, scaffold, generate, check) writes the per-area tool skills and the laws into a
   project; the docs lane's `docs/gen_tools.py` renders `docs/tools.md`. Read those, or `tools/list` over MCP; never a copy kept
   in your notes.
3. For fit, weights, pose, placement, proportion, retopology, UV, bake or clearance, the canon page names the tool and the order:
   load `lampway-canon`.

## Call it the way it expects

- Arguments are one JSON object; paths are relative to the project root, and a path outside it is refused.
- A failure is `{"ok": false, "error": ..., "help": [...]}`: the help names the next command. Follow it; do not retry the same
  call with guessed values, and do not fall back to a raw script.
- A long tool returns a job; poll its status. Do not start a second copy of a running job.
- Tools never overwrite the user's source files; they write new files and tagged results. A rebuild tag is never overwritten.

## The gates you work inside

- **Spending:** a studio or paid tool returns a plan with the price read back. Only the user confirms, from the Client; an agent,
  a swarm worker or an MCP client cannot. Studio tools are not offered over MCP at all. A job whose submission is unknown is never
  resubmitted: the user acknowledges or links it.
- **Egress:** every outbound route is off until the user switches it on in Privacy. A refusal that names a route that is off is
  the user's decision to make, not an error to route around.
- **Decisions:** a proposal is never a ruling. Mesh-QA verdicts, openings, seed audits and part fixes are the user's typed
  decisions; tools propose, record and ask (`ask_user`). Never write a ruling on the user's behalf.

## The armour runbook keeps its order

`src/scripts/mixar/modules/lampway_tools/pipeline/armor_piece.py` `STEPS` is the order: plates, seeds, catalog, seed audit
(proportions first), proportion score, provisional fit and closest pose, region fixes and matched-view audit, clone then Smart UV,
UV score and patches, parts, openings, mesh-paint, studio texture, PBR then palette and pack, export. Texturing comes last; a
geometry step after the texture makes the texture stale; a Studio action works on a saved copy. Read `STEPS` from the file, not
from this list, when they disagree.

## When no tool fits

Say so, name the nearest tool and what it lacks, and raise the gap (a new tool goes through `lampway-tool-authoring`). A one-off
script is acceptable only for read-only inspection, and its result is labelled as such.

Provenance: `server/lampway_server/agent/prompt.py` (the agent's laws), `mcp.py`, `studios/approvals.py`, `jobreceipts.py`,
`egress.py`, `agent/files_tools.py`, `lampway_tools/api.py`, `pipeline/armor_piece.py`; the canon plan §3.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway"; canon plan §3 | agents drove the app with raw scripts, re-deriving what a tool already measured and bypassing its refusals, jails and receipts | find the tool through the generated registry, follow its help, keep the spend, egress and decision gates and the runbook order | captain ruling, 2026-10-05 |
