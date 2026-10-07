---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: mixed
---

# lampway_tools — the client-side tools

The tools the agent, the panel's buttons, the operators, MCP clients and the live bridge all call inside the running app:
`api.py` is the one door; `features/` and `pipeline/` hold the tool engines (`features/` touches Blender, `pipeline/` is mostly
pure); `meshqa/`, `rebuild.py`, `meshpaint.py`, `jobs.py`, `runner.py` and the `*_client.py` / `*_state.py` pairs talk to the
server. This directory ships inside the app (everything under `src/scripts` is installed), so nothing here may be a scratch file,
a sample asset or a test. Adding a tool: the `lampway-tool-authoring` skill; the algorithms: the `lampway-canon` skill.

## Invariants

1. **One door.** The agent's scripts reach a tool only through `api.call(name, payload)`, and only names registered by `@tool`
   (`TOOL_FUNCS`) are callable; the payload is one JSON object.
2. **Refusals name the next step.** A failure is `{"ok": false, "error": ..., "help": [...]}`, never a traceback into the model
   (the `@tool` wrapper and its `_HELP` table).
3. **The project-root jail.** Every path an argument names resolves under `settings.project_root` (`settings.resolve_in_root`);
   outside it is refused with `PathOutsideProject`. Tools write new files and never overwrite the user's sources; a rebuild tag is
   never overwritten.
4. **Only the user's click confirms a spend.** Anything that runs Python for someone else (the agent's executor, a headless
   worker, the live bridge) runs inside `human_gate.scripting()`, and the confirm operator refuses while one is on the stack.
5. **The scene is touched on the main thread only.** Slow work is a job (`jobs.py`); only its scene-touching tail runs from the
   app's timer. Background threads never touch `bpy`.
6. **The live bridge serves only its own user.** It runs unsandboxed Python, so each connection's peer uid is read from the
   kernel's socket table and only the app's own uid is served; an unattributable connection or an oversize request is refused
   (`bridge.py`).
7. **Egress is the server's.** A route is switched on only by the user's click (`ui/operators/egress_ops.py` through
   `egress_client.py`); no tool here opens an outbound connection of its own to a provider.
8. **Settings resolve environment, then `<lampway home>/settings.json`, then the default** (`settings.py`); the profile lives under
   `LAMPWAY_HOME` and never in the user's stock Blender profile.
9. **MCP inspection and view routing.** Inspection declares read-only `OBSERVE` and accepts raw geometry; `lampway_view` uses raw object/data consumption because explicit focus unhide can edit visibility. The execution pump suppresses automatic undo only for these two tools; view owns its one explicit unhide undo. Only inspection is exempt from the render read-only gate; evaluated inspection still refuses during a render. Inspection adapts caller-owned evaluated geometry into world metres for the shared defect/orientation interfaces, exact uncapped aggregates and precise BVH/parity relations. UV overlap includes triangles within one island while retaining canonical raster semantics. Native admission checks precede cooperative loops and content hashing; the concrete 2M-triangle/100ms refusal is measured, while arbitrary native modifier evaluation remains indivisible. Open-loop rim presentation rounds the full sum once to four metre decimals across inspection and defect candidates.

Body intake measures UV-split topology on analytical positional identities at
1e-5 m, preserving authored vertex/native weight ids. Generalized winding verifies
the head and admits measured native openings without claiming watertightness.
The MetaHuman normalizer retains corrective fan-out authored frames/roll and
records `authored_helper_frame`; unknown branching bones still require a named
continuation. Canon 03/17 and their real-shape covering tests own these rules.

A native weight sidecar and optional GLB preview keep separate source paths and bytes in the body package; supplying both cannot replace engine weights with the preview. Corrective helper endpoints used by weighting come from the validated normalized MetaHuman document and unchanged rest fingerprint; never use a raw imported tail to bypass an unknown branch. Readback imports are transactions over every supported Blender ID collection: both success and partial failure restore pre-import IDs. Independent glove stages use the existing pose and bind engines with recorded labels and body joints; only absent numerical DOF rows stay explicit decisions. The complete canon 08 helmet proposal is accepted and available by name or with scene inputs.

Large receipts from `mesh_defect_scan`, `procedural_library`, `rig_game_extract` and `mesh_prep` use `bounded.py`: compact default fields, `limit=50` (1..1000), zero-based `offset=0`, and per-table `pages` with exact totals. `fields` selects top-level receipt fields; `full=true` restores detailed fields while retaining pagination. Explicit legacy `max_candidates` caps a defect page, while offsets address the complete measured candidate list. Presentation arguments are checked before execution. The covering tests measure default JSON size and verify later pages and full detail.

`anim_multiview_fit` validates panel paths, calibration shape and positive finite scale/rate before reading input files; its refusal includes a callable template. `edit_locality_check` accepts the schema's `{bbox: [x0, y0, z0, x1, y1, z1]}` object as well as the coordinate list, and checks finite coordinates before resolving meshes. `uv_islands.measure_object` reports the tiles touched using the existing `uv_check` tile helper alongside its outside-0..1 warning; utilization still measures the 0..1 tile. These changes preserve the canon 11/13 fitting and scoring algorithms.

AXI renders through the authoritative `common/toon/codec.py`; numpy integer, float and boolean scalars normalize to their native scalar types before TOON formatting. A CLI loading `axi.py` by file path loads that same sibling codec by path when no package namespace exists; it never imports Blender registration or maintains a second codec. Standalone proportion CLI and numpy-table subprocess tests run with Python `-I` to prove this path. Refusals use registry-generated `tool_specs.json` `api_calls` templates (with specific multiview/locality shapes); normalization helpers and proportion CLI next steps name registered tools rather than Python API names or the old tool shelf.

Plate-facing registration uses four cardinal Workbench silhouettes, the shared native-size plate loader, and canon aspect-preserving IoU. Keep the numeric margin explicit or ruled; unset margins and tied winners refuse, and measurements restore temporary IDs and selection before applying a winning turn.

## Test

```bash
python -m pytest -q tests/lampway_tools                     # without a binary, the binary-driven tests SKIP: not a pass
LAMPWAY_BIN=build/<env>/bin/mixar python -m pytest -q tests/lampway_tools   # against a built app (syncs Python first)
python -m pytest -q tests                                   # the standalone suites, bpy mocked
```

`tests/lampway_tools/blender_run.py` runs a script inside the real binary and reads `RESULT {json}` lines; it calls
`scripts/lampway/sync_python.sh` before every run, so a Python change needs no rebuild. The server half of each tool is tested in
`server/tests/test_lampway_tools.py`.

## Owner

The lane whose contract names the tool writes it and its tests; the integration lane lands it. A tool's engine follows its canon
page; the canon's open decisions are the captain's.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the client tools' door, jail, refusal shape and human gate were known only from docstrings | the invariants with their modules, the binary-driven suite and its skip rule | captain ruling, 2026-10-05 |
| 2026-10-07 | MCP wrapper contract receipt | captain: scoped MCP wrapper and migration | new transport, observation, schemas and offline data needed reproducible ownership and evidence | document the scoped implementation, generated checks and explicit limits above | scoped contract evidence in docs/reports/mcp-wrapper-migration.md |
| 2026-10-07 | complete MCP acceptance after re-audit | captain: finish original C0-C2 and T1-T3 scope | skipped geometry and isolated-only evidence left acceptance gaps | document metric shared interfaces, conservative budgets, source-pin backlinks and cloud GUI falsifiers | measured contract checklist and retained receipts |

| 2026-10-07 | real native body and corrective intake | issue 2 G2/G4 | UV seams looked open and corrective fan-outs had no continuation | analytical topology plus generalized winding, authored corrective frames and native shape regressions | issue 2 acceptance receipts |

| 2026-10-07 | issue 2 glove and readback completion | captain requested issue 2 completion | typed stages lacked engine wiring and readback retained importer IDs | route independent recorded labels through existing canon engines; restore all imported IDs; accept the complete helmet proposal without inventing other ranges | issue 2 |

| 2026-10-07 | body package dual input | sidecar plus preview acceptance fixture | reused source path copied GLB bytes into sidecar.json | keep separate native-sidecar source and preserve both byte streams | issue 2 G2 |

| 2026-10-07 | issue 2 bounded receipts and input shapes | captain requested every issue 2 acceptance criterion | large replies lacked pagination; wrong input shapes reached file reads; outside-tile atlas scores omitted tiles | document compact fields and exact page totals, pre-execution shape checks and callable refusals, and shared UV tile reporting | AC46/52/60 real-binary RED/GREEN receipts |

| 2026-10-07 | corrective consumer continuity | native multi-child corrective weight-plan fixture | normalization succeeded but downstream segment weighting still refused the same branch | share normalized helper endpoints and refuse stale frames or unstamped branches | issue 2 G2/G4 |

| 2026-10-07 | shared scalar codec and standalone CLI | issue 2 G1 and full fit-chain intake | numpy constructor repr broke decimal formatting and package-only imports broke standalone proportion workers | normalize explicit numpy scalars in the shared codec; path-loaded AXI loads the same canonical file; prove subprocess isolation and source-file identity | 746 AXI/TOON tests and native 11-stage full-chain receipts |
| 2026-10-07 | registry-backed refusal next steps | issue 2 G19/F13/G20 | Python API names, obsolete shelf commands and invented normalizers were not callable next tools | generate complete API call-name mapping; validate help names against the live registry, with an unknown-tool plant and native refusal checks | server refusal-template and isolated binary tests |

| 2026-10-07 | measured plate facing | issue 2 AC65 remaining implementation | a supplied margin still unconditionally refused the plate path | reuse cardinal silhouette rendering and true-aspect scoring; preserve unset/ambiguous refusals and transient cleanup | normalize_mesh contract golden |
