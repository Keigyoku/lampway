<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Lampway orphans lane report (lp/orphans)

Worktree `<workspace>/wt-orphans`, branch `lp/orphans` from `lp/wave5` at `00d907d4` (origin/lp/wave5 did not move during the lane;
checked with `git fetch origin` + `git merge-base --is-ancestor origin/lp/wave5 HEAD` at every item boundary). Author: the noreply
identity, no trailers. Only `lp/orphans` is pushed. The PII gate (`prepublish_gate.py --git origin/lp/wave5..HEAD` with the owner
patterns) reports 0 findings at every check, the last at the head below.

Every tool: a contract (its Def description and docstring), tests written first and observed RED (exceptions are listed per item),
registration (client `@tool` in `orphans_api.py`, server `Def` in `agent/orphan_tools.py`, or a ported runner tool with a `batch=`
Def; server-run tools in `agent/orphan_server_tools.py` behind one dispatch line), refusals that name the fix, and receipts.
Network: only the vision judge and the handwriting reader call out (OpenRouter, through the egress hook, ZDR for private content);
every Studio action is a plan the user confirms; no live spend was made (fake transports only).

`docs/tools.md` is NOT regenerated: `docs/gen_tools.py` exists only on `origin/lp/docs`. Regenerate after lp/docs merges.

## Items

| item | status | commit(s) | tools | tests |
|---|---|---|---|---|
| O2-O4 | done | 69c13050 | side_label_check, mirror_pair, scale_to_measure | test_orphans_side_label / mirror_pair / scale_to_measure |
| O8 | done (stub: the client studio_slot does not read the register) | cecc3896 | lampway_slot_register (server) | test_slot_register |
| O18 | done | 6adc5c60 | uv_check | test_orphans_uv_check |
| O19 | done | 8f78d3df | segment_mesh labels mode | test_orphans_island_labels |
| O22 | done (per-material region prompts not built) | 74872b54 | texture_gen additions | test_orphans_texture_gen, test_feature_texture |
| O25 | done | 362bf57e | render_condition_passes | test_orphans_condition_passes |
| O29 | done | f2655cfe | image_material_id | test_orphans_material_id |
| O30 | done | 6cf82d10 | studio action tripo.regen.region | test_studio_region, test_studio_service |
| O31 | done | 14fe3514 | layered_material mask_invert | test_orphans_mask_invert |
| O32 | done | 07feb99d | QA crop cameras, parts_material_slots | test_orphans_qa_renders, test_orphans_parts_slots |
| O7 | done | 3b742ef1 | zone_sheet, mesh_region_extract | test_orphans_zone_sheet, test_orphans_region_extract |
| O1 | done | bda89000 | mesh_local_edit, edit_locality_check | test_orphans_local_edit |
| O5 | done | fcf10cbc | mesh_join_boolean | test_orphans_join_boolean |
| O6 | done | 7a3785e4 | multi_piece_material | test_orphans_multi_piece |
| O9 | done | 6692fd72 | seamless_tile | test_orphans_seamless_tile |
| O10 | done | a6958f66 | studio action tripo.relief, relief_tiles | test_studio_relief, test_orphans_relief_tiles |
| O11 | done | 701b497c | image_upscale | test_orphans_image_upscale |
| O12 | done | 5fcd5dae | lampway_studio_cross_pass (server) | test_cross_pass |
| O20 | done | 8b3365d2 | auto_rig body plans, naming, parts | test_orphans_auto_rig_plans |
| O21 | done | aa0ff61a | image_to_3d detect views, paired, multi-view slots | test_orphans_image_to_3d_views, test_feature_image3d |
| O23 | done | 35995a42 | reference_pack | test_orphans_reference_pack |
| O24 | done; the moodboard chain added | 7734fd7c, b428e92d | workflow_reference_to_asset (+ route moodboard), workflow_graph confirm, prompt_image | test_orphans_ref_to_asset, test_orphans_moodboard_chain |
| O26 | done (the RTMW live leg unverified: rtmlib absent) | 1b4ef4c0, a77a11f2 | anim_multiview_fit detect / refine | test_orphans_anim_detect_abs |
| O28 | deferred to the canon lane (IMPLEMENTATION_PLAN item 4, bind-and-return) | - | - | - |
| O13 | done (9 of 18 job keys backed; the rest carry reasons) | 14ccc7ec | job_backends, job_services reasons | test_job_backends |
| O15 | done (reader confidence fixed at 0.8) | 9c5dba5f | POST /api/v1/handwriting/recognize | test_handwriting |
| O16 | done | 93725973 | marks in the model context, lampway_scribble_read | test_agent_turn (marks), test_scribble_read |
| O17 | done | 37082829 | batched ask_user, the client's answer shapes, Retry failed tasks | test_questions_checkpoints |
| O34 | done | fa1e7cd9 | lampway_image_matte | test_orphans_image_matte |
| O35 | done; the moodboard prompts added | 8599c93b, 120825d6 | 4 process templates + 9 moodboard templates, parity | test_prompt_imagegen_process, test_moodboard_parity |
| O38 | done (live response shapes unverified) | e96f47a3 | lampway_vision_judge (server) | test_vision_judge |
| O39 | done | 177371db | lampway_recon_measure | test_orphans_recon_measure |
| O33 | done | 2dcba1fc | export_parts, verify_set, render_final, judge_pack, gen_parts_table, libwiki, index_delta (runner), texture_library_stage | test_orphans_parts_publish, test_orphans_libwiki, test_orphans_texlib_stage |
| O36 | BLOCKED (see below) | - | - | - |
| normalization rule | done | a77a11f2 | orphan_doors.CONSUMES / EXTENDED / RUNNER; LEGACY(normalize) markers; anim_abs limb axes | test_orphan_doors, test_orphans_anim_detect_abs |

## Notes per item (built, RED evidence, deviations, stubs)

Items O2 to O15 were reported to the coordinator as they landed; their notes are kept short here.

- **O2-O4.** RED: the tools absent. Fixture slips fixed in the tests (gauntlet mirror semantics). Code fix found by the tests: none.
- **O8.** The register is server-side; the client's studio_slot does not consult it yet (stub).
- **O22.** Per-material region prompts are not built (stub). The jobs_client `extra_references` slot was written before its test and
  then mutation-verified.
- **O29.** Fixture: a palette that was too close (dE 57.9 < 60) was corrected in the test.
- **O30.** The approval flag is the user's confirm in the Studios panel at 0 credits, never an argument: an agent-passed flag is
  refused. Recorded for review.
- **O1.** The Studio route uses the original (the driver's law), which contradicts the spec's "a copy"; recorded.
- **O9.** The image_tile spec's "ratio <= 0.5" cannot hold for exact tilings under the shelf ratio: the wrap is checked as a
  non-outlier instead. The "relax any threshold 10 %" property is not reproducible on synthetic tiles (only SHARP_MIN pinned). The
  tone-seam threshold (5.0) is derived from the bake-off tiles (2.05 and 3.26 accepted; 8.59 and 9.37 rejected).
- **O24.** The original chain does not use workflow_graph; the moodboard chain does (below).
- **O26.** The RTMW leg needs rtmlib and weights on disk; unverified live. anim_abs was revised under the normalization rule (below).
- **O28.** Deferred: the canon lane owns bind-and-return (IMPLEMENTATION_PLAN item 4).
- **O13.** Code written before its test and mutation-verified: the ledger_tools reasons, the app wiring.
- **O15.** The reader's confidence is fixed at 0.8 (stub).

### O16 scribble_read (93725973)

- **Built.** The Client's `agent.chat` payload carries `mark_context` (scribble_mark's build_payload). `agent/marks_context.describe`
  restates it as prose, deterministically and with no model, following the Client's own payload.summarize wording: the circled
  object with its coverage, the world points, empty-ground placements, and a sketch with the objects it crosses. The prose is
  appended to the user message, so a follow-up turn still has it in history.
  - The client tool `scribble_read(include_image, include_sent)` re-reads the scene's mark records through `marks.get_marks`.
    It returns kind, resolved object, region (the payload's bottom-up 0..1 bbox), NDC anchor (-1..1, y up), state, mode and the
    Client's summary.
  - `include_image` saves a copy of the frozen annotated frame (else the clean still) under `<root>/scribble/`.
- **RED.** Observed: the server for the right reasons (`marks_context` absent; the model request lacked the object name), the
  client for "no tool function 'scribble_read'".
  - The real-client region convention was confirmed against geometry.py (no y flip). My first expectation guessed a flip and was
    corrected to the code's truth.
  - Mutation: dropping the marks text from the message fails the integration test; taking the last resolved object instead of
    the first fails the client test.
- **Deviations.**
  - The spec says "a text block in the system turn". It is put in the user turn so it survives into later turns.
  - The spec's refusal "include_image with a text-only model" is not built. No provider declares vision today, so the tool cannot
    know.
  - In `-b -P` runs the scribble UI properties register on deferred timers that never fire, so the test registers `mark_props`
    itself.

### O17 batched questions, retry cards (37082829)

- **Built.**
  - `ask_user` takes `questions`: 2 to 4 items, each with options, matching the Client's own `is_valid_batch`. Any other batch is
    refused to the model as a tool error.
  - A batch is ONE `input_required` event carrying the `questions` slot, the first card's content and actions, and Cancel
    (`abort`).
  - The answer is the complete `{question: answer}` map as JSON. A partial map is refused (`ok: false`, naming the missing
    questions) and nothing is resumed.
  - Cancel ends the turn with a "Cancelled" bubble and no model call. A tool_result is still recorded, because providers require
    one per tool call. The spec said "without a tool result"; this is a deviation, recorded.
- **Found while testing.** The real Client answers a single-choice click with `{action: <the option's value>, text: ""}` (the
  generic slot dispatch), and the server answered "(no answer)". It now answers with the clicked value. The old test sent a
  paraphrased `text` and so missed it.
- **Retry failed tasks.** A turn whose swarm_collect left failed or cancelled workers ends with the Client's post-turn chip
  (`retry_failed_tasks`, buttons only, no paused input). The chip sends `continue` (parked_resume.CONTINUE_MESSAGE), which re-runs
  exactly the failed tasks as a new swarm. It is written into the conversation as swarm_start + swarm_collect tool calls, and the
  model then reports on them.
  - "Review unfinished checks" is not built: the Client has no action value for it.
- **RED.** Observed for all new rows except the Plan Mode row, which passed at once (the behaviour existed). I strengthened it
  with an eager script call in the same round and mutation-verified it: making ask_user not end the turn fails six tests. Other
  mutants: accepting partial maps fails the resume test; offering finished tasks for retry fails the retry test.

### Normalization rule (a77a11f2), from the coordinator's rule of the same day

- `orphan_doors.py`:
  - CONSUMES has a row for every orphans_api tool, in `canon_asset.Need`'s fields (kind, scale state, welded, convention, roles),
    or NONE(reason). Tools with absolute thresholds (mm, metres, px/m) accept only `real` scale.
  - EXTENDED covers the modes added to existing tools; RUNNER covers the ported runner tools.
  - The canon lane's N2 turns each row into `consumes=` mechanically; until then the table is the declaration.
  - `test_orphan_doors` fails on an undeclared tool or a parameter the function lacks (mutation-verified).
- **LEGACY(normalize)** marks every importer call this lane added: job_backends' GLB/OBJ/FBX import and partseg `mesh_load.py`.
- **anim_abs (AUDIT T62).**
  - The two searched axes are now perpendicular to the LIMB, head to the continuation child's head (leaf: the parent line), never
    the tail.
  - Poses are written as quaternions (swing applied before the bone's own pose).
  - RED observed first: with a thigh tail turned onto the lateral axis, the old search could not move the limb at all (error 25
    degrees, cost unchanged). After the change the error is within 5 degrees.

### O34 image_matte (fa1e7cd9)

- **Built.** Ported from the astra-1 shelf's image-matte tool v1.2.0 (read from its source commit; no image copied anywhere):
  - the integer soft key with despill and the complementary-green clamp;
  - sheet splitting (2x2 and 3x2; x/y/row cuts; erase rectangles; a recipe that names exactly the inventory);
  - centring by integer shifts;
  - the atomic batch publish with a manifest of settings and hashes.
  - New:
    - The KEY is read from each image's border ring (median colour; clear = min(220, the ring's 5th-percentile score); refused
      under 25 % key in the ring), so a generated magenta that is not #FF00FF is cleared and unmixed against its real colour.
    - Centring takes `canvas_size: common` (the smallest square holding every plate).
    - A verify pass: decode with the CRC walk, file and pixel hashes against the manifest, sources unchanged, every non-key pixel
      preserved, nonzero-alpha borders named, and a light/dark contact sheet.
- **Parity.** In memory only (nothing written), on the shelf's six real samples with the ideal key, RGBA is bit-identical to the
  shelf's outputs. The PNG bytes differ: encoder and zlib runtime, a limit the shelf itself stated.
- **RED.** Observed (module absent). Six mutants each killed by a test (ring clear, ring key colour, common canvas, verify hashes,
  despill, border check).
  - My first despill fixture assumed coverage 0.5 where the score-linear coverage was 0.72. The fixture was corrected to a
    foreground whose score equals `opaque`.

### O35 process templates (8599c93b) and the moodboard prompts (120825d6)

- **Process templates.** `plate-individual-part` (one physical piece and side, a wearer-axis view enum, independent or anchored
  scale, never a mirrored copy), `turnaround-six-view`, `isolate-held-object` and `equip-character-view` (the truthful
  synthetic-character context as a one-value enum; its input says never for photographs of real people).
  - Authored from the astra-1 shelf's ImageGen workflow.
  - References are named in prose order (the renderer substitutes only start/end/references/video roles).
- **Moodboard (the captain's addition).** Nine templates from Prompt1-8 (P8 holds the 3x2 sheet AND the single-piece plates).
  - Image A and Image B are the `character_body` and `design_plate` slots, in order.
  - `asset_name` is a string variable.
  - `view` is an enum of the six wearer-axis views, each carrying P8's own definition.
  - There is no model pin (CH5). The model_adapters block is the library's standard per-family notes, which the render test needs
    and which pins nothing.
- **Nothing lost.**
  - The originals are byte copies in `server/tests/fixtures/moodboard/` (sha256 equal to `specs/prompts/moodboard`).
  - `prompts/parity.py` splits each original into clauses and finds every one in a template field, verbatim or through an alias
    in `prompts/moodboard_parity.json`. An alias names the new wording and the field; a clause split across fields lists parts,
    and every part must hold.
  - Result: P1-P7 verbatim (23, 25, 21, 40, 28, 20, 19 clauses); P8 24 verbatim + 11 aliased (its run-on lines: layout, view
    definitions, the per-view "Now VIEW" lines into the view enum).
  - The test fails on a deleted clause (the planted "no props" is caught), on a dropped alias, on an alias whose wording is not
    where it says, and on an alias for a clause the original lacks. All four were observed failing by mutation.
- The inventory pin in test_prompt_images went 19 -> 23 -> 32 image templates.

### O24 moodboard chain (b428e92d)

- `workflow_reference_to_asset(route="moodboard", piece=<graph name>, reference=<armor design>, body_refs, pieces, example_sheet)`
  defines the workflow graph:
  - P1 anatomy (body_refs) -> P2 adaptation (A anatomy, B armor) -> P3 fit-check (A anatomy, B adaptation) -> P4 breakdown
    (A anatomy, B fit-check) -> P7 cutout (A anatomy, B fit-check).
  - Then per piece: P5 multiview (A anatomy, B breakdown), P6 the four views (A anatomy, B that piece's multiview), and P8 the
    3x2 turnaround (the multiview; the example sheet rides it).
- Every node is a spend node (`studio_action: image_gen`) running the new client tool `prompt_image`. It renders a library template
  on the server (POST /app/prompts/render), sends the references in the template's input order, is dry unless live, and writes a
  ledger row per generation.
- **workflow_graph gains `confirm`.**
  - ONE spend node runs once, and its output is kept for exactly its inputs: a changed upstream needs a new confirm.
  - Plan and run never generate.
  - A whole-argument `{{input}}` now keeps its type (a list stays a list).
- **RED.** Observed (module absent; registry). The real-binary api leg was written after prompt_image, then mutation-verified:
  reversing the reference order and dropping the required-role check each fail.

### O38 vision judge (e96f47a3)

- **Built.** `lampway_vision_judge` (server).
  - Frames or one native video go to an OpenRouter vision model with a per-purpose criteria prompt (judge, locomotion, air,
    combat, moment), ported in behaviour from the TITAN vision tool and its judge prompts and made generic.
  - Strict verdict: PASS | FAIL | INCONCLUSIVE with timestamped findings, criteria and limitations. Anything else is INCONCLUSIVE
    with status failed.
  - INCONCLUSIVE is never upgraded: the verdict is the worse of the model's and every criterion's, re-derived from the raw text
    by `reconcile` (an edited receipt cannot raise it).
- **Routing** follows decisions_model's law: the live /models list filtered by input modality, the live /endpoints/zdr list for
  private content (the default), never ':free', and nothing sent when none is eligible.
- **Receipts and spend.** Identity is the purpose, the prompt hash, the model choice and the media sha256 (no base64), so a repeat
  is answered from the receipt with no call. The session spend ledger is checked before and charged after; the request cap is
  19,000,000 bytes.
- **Agent default.** dry_run returns the plan.
- **Unverified.** Native-video content parts (`video_url` data URI) and the response shapes, until a live run with a key.
- **RED.** Observed (module absent). Six mutants killed (worst-of, receipt reuse, ZDR provider block, reconcile trust, ':free'
  filter, verdict schema). The agent-tool test was written after its wiring.

### O39 recon_measure (177371db)

- **Built.** Ported from the astra-1 shelf's spike measure.py onto the canonical frame and Lampway's own raster (anim_ref):
  - the best of the 24 proper axis orientations by mean silhouette IoU against the front, left and top plates;
  - six-view IoU on the wearer's axes;
  - the cavity and shell ratios through the crown centre (numpy ray against all triangles);
  - the crest-fin ratios from the top view;
  - the albedo's left/right luminance (colour attribute, else the Base Color image at loop UVs).
- The 24 orientations are flips and transposes of three base projections, pinned against direct rasters for all 24 x 6.
- **Deviation.** The shelf's crest code divided by the longest COLUMN (a front-to-back length) while its comment says "the helmet
  width". It is the widest row here. The test pins 0.1 on a fin where the shelf formula reads 0.056; that mutant initially
  survived, and the test was strengthened until it failed.
- **RED.** Observed (module absent). Five mutants killed.

### O33 Parts Library publishing, libwiki, texture staging (2dcba1fc)

- **Ported shelf scripts** (runner tools with provenance headers):
  - export_parts, verify_set, render_final, judge_pack (partseg; a shared `mesh_load.py` opens a .blend as is or imports a
    GLB/FBX, marked LEGACY(normalize));
  - libwiki and gen_parts_table (libwiki/);
  - index_delta (texlib/).
- **Owner-specific defaults** (file names, the scale sentence, a fixed 1 m frame, a reference path) come from the recipe or the
  mesh's own bounds.
  - verify_set's evidence-name check covers every `evidence/` path rather than one set's file names.
  - judge_pack's vote attributes are arguments.
  - libwiki reads frontmatter with PyYAML when present, else the JSON-valued subset it writes (Blender's python has no PyYAML),
    and addresses "the owner".
- **texture_library_stage.** The shelf's staging script was a recorded one-off build; its rules become this tool, driven by a delta
  manifest: versioned immutable files, lineage resolving inside the library, unknowns null, colour spaces declared, no inferred
  PBR, no approved folder, its own staging root only.
- **RED.** Observed for all three (tools absent).
  - libwiki: the shelf's own falsifiers (C2-N1..N12) run under pytest against the port. A parser mutant survived them (a malformed
    value was refused later for a different reason), so a direct parser test was added and kills it.
  - Staging: three rule mutants killed.
  - One real-binary test runs export -> verify (all_ok, 24 faces once) -> unchanged re-export keeps v0001 -> render -> table;
    another runs judge_pack (split + agreed).

### O36 rig conversion (BLOCKED)

- R1 inspect, R2 map, R3 normalize and R5's read-back depend on `canon_geom` (canon item 1).
  - It exists on `origin/lp/canon` (9e3e3e67, with canon_asset/canon_io at 66807e43) but not on `origin/lp/wave5`.
  - The coordinator's rule is to use it once it is on wave5 and never write my own copy, so they wait for that merge.
- R4 `rig_convert` (the O36 core) is a port of Titan's `animation_canon` / `canon` / `skin_bind`. Its spec lists two decisions owed
  to the captain (H.1):
  - port into Lampway, or call Titan's tool as an external process;
  - ship animation first and refuse skin packets until Titan Task 131 closes?

## Test totals against the baseline

(Filled from the HEAD run; see the section below.)

## Merge notes for the integrator

- **Shared files with conflict risk.** `lampway_tools/api.py` (star-import of orphans_api, workflow_graph confirm, segment_mesh,
  texture_gen, auto_rig, image_to_3d, anim_multiview_fit), `agent/lampway_tools.py` (DEFS += ORPHAN_DEFS; workflow_graph Def),
  `agent/tools.py`, `agent/turns.py` (marks, batch questions, retry), `agent/swarm.py`, `app.py`, `studios/actions.py`,
  `features/common.py`, `runner.py` (seven runner tools), `workflow_graph.py`, `server/tests/test_prompt_images.py` (the count pin is
  32).
- After lp/docs merges, regenerate `docs/tools.md` with `docs/gen_tools.py`.
- When lp/canon merges: turn `orphan_doors.CONSUMES` / `EXTENDED` / `RUNNER` into `consumes=` on the decorators and runner rows,
  route the LEGACY(normalize) imports through `canon_io`, and O36 R1-R3 + R5 can start.
- The moodboard templates ship in the public repo, as the captain asked; the PII gate is at 0.
