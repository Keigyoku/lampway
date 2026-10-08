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


Native MetaHuman metacarpals follow their named finger01 continuation beside slide helpers. Rig export defaults follow measured normalized frames with recorded recipe selection; explicit Titan stays available and every raw-frame readback bar stays unchanged. Physical UE M-RIG-01 confirmation remains separate and required.

Boot height-anchor scale uses measured knee-to-sole length, independent of world
translation. Verify body-only and both-input translations and retain the
sole-at-zero result; earlier height-anchor candidate measurements require a
rerun on the corrected source. This geometry correction does not select a
physical default among width, height and foot anchors.

Measure unruled fit defaults before recommending them. Explicit pair modes retain side identities/inverse maps; finger search curls TO canon targets including thumb. The decision measurement runner reports and renders candidates without modifying canon settings; experimental tables require caller sign expectations and thresholds.

Decision measurements render the actual evaluated body and placed candidate together in fixed world bounds only when explicit context and clearance limits are supplied. Closed-body pseudonormal and open-body winding signs retain an explicit opening-band refusal. Vertex-clearance acceptance remains separate from execution success and full fit acceptance.

Pose region membership follows actual skeleton ancestry to the nearest configured seed, retaining each sample's weighted bone for transformations and ray origins. Refuse empty requested regions and invalid/ambiguous ancestry before pose evaluation or file writes. Component/native synthetic proofs remain distinct from the original body rerun.

## Invariants

Weight transfer warns below the documented majority-match diagnostic threshold and names `lampway_fit_place`. Validate overrides before creating an output; compare the unrounded fraction and keep this warning separate from export acceptance.

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

Failed persistent import consumers remove only the datablocks they imported and restore caller selection. Canonical import ownership includes Library IDs as well as their loaded dependencies: a partial append/link failure must not leave a Library datablock. Studio ownership also includes replacement meshes created while normalizing the imported asset before landing, so a later collection failure removes that replacement. Successful raw intake and persistent imports remain intentional; temporary readbacks clean up on success too. Verify these rules with completed native loads followed by downstream exceptions, preserving existing IDs and selection; subprocess import checks verify failed child isolation without claiming unrelated recipe algorithms.

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

Recursive receipt presentation also pages large nested arrays and mappings, including B-Bone segment lists and nested mesh metrics; page paths retain original row indices and complete totals. Compact table rows retain their named fields or up to four scalar fields; full detail retains fields while applying the same bounds. Small numeric coordinate vectors remain atomic. QA's external schema requires the actual target object, independently of its optional piece configuration name, and the client verifies that match before creating layers.

Refusal helpers select external API or batch names from generated registry metadata and include the required arguments. Batch failures retain structured refusals even for malformed direct-call names; do not let help generation mask the original error. Cover actual engine validation and recursively inspect nested help/next-step receipts against registered names in the isolated binary, alongside the source-template gate.

Compact `mesh_prep` retains measured shell orientation and source/current content hashes while paging detailed tables. Motion replacement captures the previous tool-owned output before import; name and stamp the validated replacement only after removing that prior output, preserving caller-owned collisions. Runner truncation bounds the output body separately from the full-path log hint; test both short and over200-character temporary paths.

## Test

```bash
python -m pytest -q tests/lampway_tools                     # without a binary, the binary-driven tests SKIP: not a pass
LAMPWAY_BIN=build/<env>/bin/mixar python -m pytest -q tests/lampway_tools   # against a built app (syncs Python first)
python -m pytest -q tests                                   # the standalone suites, bpy mocked
```

`tests/lampway_tools/blender_run.py` runs a script inside the real binary and reads `RESULT {json}` lines; it calls
`scripts/lampway/sync_python.sh` before every run, so a Python change needs no rebuild. The server half of each tool is tested in
`server/tests/test_lampway_tools.py`.

Audit the complete measured342-edge native profile before mutation. Anatomical core terminals use canonical parent-line endpoints; exact verified auxiliaries preserve authored frames and are excluded from anatomical convention classification. Share validated/fingerprint-bound endpoints with weighting and posed openings; unknown/reparented edges refuse. Missing native rows are explicit and cannot publish a full body/export.

Canonical rest-frame serialization may project only positive-determinant float32 producer errors within the documented spectral admission budget and unchanged axis bar. Retain valid values, strict CA validation, raw reads/fingerprints and authored matrices; refuse material shear/reflection and retain the hashed full private receipt with bounded public correction metrics.

## Owner

The lane whose contract names the tool writes it and its tests; the integration lane lands it. A tool's engine follows its canon
page; the canon's open decisions are the captain's.

Engine exports convert metre coordinates on independent centimetre copies and decode only the pinned importer unit carrier. Check raw Null ancestors and direct bone scales before decoding; unchanged bind bars and physical native-reference proof remain mandatory. Never apply a speculative common rotation, mutate source scene units, or hide an authored scale with readback normalization.

The verified native342 conform path requires an explicit reference: source_copy preserves authored rest and skin with an identity map and matching measured convention, while mixed/unknown frames refuse. Default convention exports name only the disposable container Armature under the verified installed UE Blender predicate; occupied names refuse before allocation. For admitted pinned-writer centimetre files, cross-check authored node, BindPose and cluster binds under unchanged shortest-quaternion bars; refuse unsupported layouts without projecting matrices or falling back to inferred display tails. Keep imported display errors visible. Source preservation and authored-file verification never establish independent native UE parity.

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

| 2026-10-07 | native MetaHuman normalization and export defaults | actual owner G4/G5 failures and issue2 default-chain instruction | metacarpal slide fanout lacked continuation and default recipe always rejected normalized frames | Native MetaHuman metacarpals follow their named finger01 continuation beside slide helpers. Rig export defaults follow measured normalized frames with recorded recipe selection; explicit Titan stays available and every raw-frame readback bar stays unchanged. Physical UE M-RIG-01 confirmation remains separate and required. | native metacarpal and both-convention export RED/GREEN; UE proof remains pending |

| 2026-10-07 | strict issue 2 nested receipt and target audit | literal AC46/52/56 audit | full-detail segment lists and nested metrics bypassed table bounds, refinement shapes reached engines, and QA piece IDs were mistaken for object names | document recursive page totals and atomic coordinates, validate all exposed argument forms before work, and verify the configured QA object | strict native RED/GREEN receipts |

| 2026-10-07 | strict callable refusal audit | AC45 full runtime branches | generic argument help and bare batch fallbacks could not be called, and invalid batch names broke help generation | use generated API/batch mappings, explicit model descriptor examples and recursive actual-output name gates | seven isolated Blender cases, including all API preflight refusals and malformed direct batch names |
| 2026-10-07 | complete import ownership and failure inventory | issue 2 AC20 native mode audit | partial append/link loader exits leaked Library IDs and Studio collection refusal leaked a normalized replacement mesh | include Library IDs in canonical snapshots; record imported-asset normalization replacements within Studio ownership; verify native post-load failure and subprocess isolation | native importer/library/placement inventory and public issue-2-import-audit report |
| 2026-10-07 | measured fit decision paths | captain: measure issue2 AC65 before defaults | configurable algorithm gaps and unmeasured proposals obscured required choices | Measure unruled fit defaults before recommending them. Explicit pair modes retain side identities/inverse maps; finger search curls TO canon targets including thumb. The decision measurement runner reports and renders candidates without modifying canon settings; experimental tables require caller sign expectations and thresholds. | native pair, hand and measurement-pack tests |

| 2026-10-07 | low-match weight-transfer diagnostics | issue 2 G10 and native placed/unplaced calibration | inpainting concealed approximately three-percent direct matching on an unplaced piece | warn below the documented majority-match threshold, name placement, validate overrides before output and compare unrounded fractions without gating export | native placed/unplaced and strict-boundary RED/GREEN tests |

| 2026-10-07 | terminal finger helper-only leaf continuity | actual c4e91 native pinky03 fanout refusal | two helpers refused and a single helper silently became the bone direction | Native terminal finger03 joints with only exact same-finger/same-side bulge/half drivers use the canonical0.8 parent-line leaf endpoint, including one-driver cases. Unknown terminal children refuse; normalized stamps and shared weighting endpoints use the same predicate. | native terminal one/two-driver RED and all-ten-joint GREEN with unknown-child falsifiers |

| 2026-10-07 | complete native topology roles and consumers | actual terminal half-driver refusal and full342graph receipt | serial continuation additions missed auxiliary chains, convention classification measured drivers and core minimum claimed full roster | Audit the complete measured342-edge native profile before mutation. Anatomical core terminals use canonical parent-line endpoints; exact verified auxiliaries preserve authored frames and are excluded from anatomical convention classification. Share validated/fingerprint-bound endpoints with weighting and posed openings; unknown/reparented edges refuse. Missing native rows are explicit and cannot publish a full body/export. | complete342native RED/GREEN, unknown/reparented/stale controls and partial-publication refusals |
| 2026-10-07 | body-relative decision receipts | captain: AC65 measured boot handoff | isolated cropped silhouettes and sampled counts hid actual body placement and implied acceptance | require explicit body context, fixed world bounds and limits; report all-vertex clearance separately with opening-band refusal and no default promotion | native body-context placement and threshold falsifiers |
| 2026-10-07 | bounded native rest-frame serialization | actual complete-rig proper-rotation failure | independently normalized float32 columns retained cancellation error beyond the strict validator | Canonical rest-frame serialization may project only positive-determinant float32 producer errors within the documented spectral admission budget and unchanged axis bar. Retain valid values, strict CA validation, raw reads/fingerprints and authored matrices; refuse material shear/reflection and retain the hashed full private receipt with bounded public correction metrics. | actual three-frame external receipt, complete342 oblique graph and material-error falsifiers |
| 2026-10-07 | sole-relative boot height anchor | AC65 candidate measurement audit | absolute knee Z scaled the same boot from1.03 to3.03 after a1m body translation | measure knee-to-sole length, retain body-only and both-input translation covariance and original sole-at-zero behavior; remeasure old candidates before selecting a physical default | boot height RED/GREEN and current placement/pair/fit-chain regressions |
| 2026-10-07 | reference client receipt and object lifetime fixes | actual full-client repros and G23 | compact presentation dropped measured fields, motion import removed its new armature, and total-output assertions depended on path length | retain bounded measurement/hash fields, replace only prior tool-owned objects and bound runner body separately from its log hint | maintained native geometry/motion and long-path regressions |

| 2026-10-07 | nonvacuous anatomical pose sampling | actual chest9f90 returned zero-arm success | exact seed-name membership excluded weighted hand/finger/twist descendants | select nearest actual ancestral region, retain weighted bone rays and refuse empty/invalid ancestry before solving | descendant penetration, empty/ancestry controls and unchanged192sample native golden |

| 2026-10-07 | actual unit-carrier and frame diagnosis | owner UE derived342-row capture | Blender self-readback hid scale100 Null ancestry; applying import object scale violated the existing drift guard | Engine exports convert metre coordinates on independent centimetre copies and decode only the pinned importer unit carrier. Check raw Null ancestors and direct bone scales before decoding; unchanged bind bars and physical native-reference proof remain mandatory. Never apply a speculative common rotation, mutate source scene units, or hide an authored scale with readback normalization. | old-default rawNull100 RED; disposable writer/skin/action/unit-factor and quaternion-order controls |

| 2026-10-08 | actual native conform and container correction | actual source-copy and installed UE predicate evidence | a161-bone implicit reference rewrote native342 frames and a differently named Null became an extra root | Require explicit native reference or bounded source_copy, preserve authored data, and reserve Armature for disposable exports only under the verified predicate. Cross-check redundant authored binds under existing bars and retain display reconstruction errors. Keep native pose calibration and physical acceptance separate. | native default-reference/container RED, source-copy, bind corruption and near-bar controls |
