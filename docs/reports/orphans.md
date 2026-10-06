<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Lampway orphans lane report (lp/orphans)

Worktree `<workspace>/wt-orphans`, branch `lp/orphans` from `lp/wave5` at `00d907d4`. origin/lp/wave5 did not move through O1-O39;
it moved during O36 and was merged three ways in all (never rebased): `origin/lp/canon` at `e16b9a3b` (5a993b5), then `origin/lp/wave5`
at `0ad57ab9` (18ac182) and at `704eba50` (e4cc94d). Author: the noreply identity, no trailers. Only `lp/orphans` is pushed. The PII
gate (`prepublish_gate.py --git origin/lp/wave5..HEAD` with the owner patterns) reports 0 findings at every check, the last at the
head below.

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
| normalization rule | done; superseded by the door at the lp/canon merge | a77a11f2, 5a993b5 | consumes= on every orphan tool (orphan_doors.py retired); anim_abs limb axes | test_canon_doors, test_orphans_anim_detect_abs |
| O36 port | done (skin and morph WIP) | a935159 | rig_convert/ (animation_canon, canon, skin_bind), recipes, UE recipe | test_rig_convert_* |
| O36 R1-R3, R5 read-back | done | ab667a7 | rig_inspect, rig_map, rig_normalize, rig_readback | test_rig_core, test_rig_tools |
| O36 R4 | done; rig_skin WIP | ec0529b | rig_convert, rig_skin | test_rig_convert_tool, test_rig_convert_g22 |
| O36 R6 | done | 55adae3 | rig_conform | test_rig_conform, test_rig_core |
| O36 R5 write | done (titan_cm_native refused by the read-back on canon-17 rigs: see notes) | 6ed0e3a | rig_export_ue | test_rig_export_ue |
| O36 R7 | done ('views' / hands refused: no pose environment) | d572b90 | rig_fit_template | test_rig_fit_template, test_rig_core |
| O36 R9 | done | 44b5a1f | rig_game_extract | test_rig_game_extract |
| O36 R10 | done | 444f6c6 | rig_bake | test_rig_bake |
| O36 R8 | done (canonical_agreement_deg not wired per call; G22.2 pinned in core) | 4bf40e4 | rig_retarget | test_rig_retarget, test_rig_core |
| O36 R11 | done (pose 'reference' not built) | 7a79ecf | rig_rest_pose | test_rig_rest_pose, test_rig_core |
| O31 follow-up | done | f52bfc2 | layered_material docstring names mask_invert | test_wave5_layered_material |

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

### The merges (5a993b5, 18ac182, e4cc94d)

- **lp/canon at e16b9a3b (5a993b5)**, on the coordinator's option 1:
  - real `Need`s for the mesh tools, with their real-Blender tests stamping fixtures through canon's `normalize_object`;
  - `NONE` for scribble_read, texture_library_stage, gen_parts_table, libwiki and index_delta;
  - `LEGACY` only for the 10 texture / list tools (six image tools, three list-argument tools, rtmw_detect), each with its reason.
  - scale_to_measure and mesh_local_edit re-stamp what they change (`features/restamp.py`). job_backends, partseg `mesh_load` and
    multi_piece route their imports through canon_io. `orphan_doors.py` is retired: the decorators are the declaration.
  - The ratchet rose 110 -> 120 as a RECORDED one-time rebaseline in the merge commit.
- **For the canon lane.** canon's ratchet test had no notion of a merge rebaseline, so I added the minimum to
  `test_canon_doors.py`:
  - the file's first token is the count, and a `rebaseline <N> merge <p1> <p2>: <reason>` line records a rise;
  - `_ratchet_problems(history)` accepts a rise only at a two-parent commit whose file names that count and both of its parents;
  - the working tree mid-merge counts as a commit whose parents are HEAD and MERGE_HEAD;
  - `test_a_recorded_rebaseline_is_accepted_only_in_the_merge_commit_it_names` refuses a rise in an ordinary commit, at a merge the
    line does not name, without its line, without a reason, and a second rise after the recorded one.
- **lp/wave5 at 0ad57ab9 (18ac182).** wave5's Asset Vault code imported outside canon_io:
  - asset_place, asset_place_media, asset_place_shading, the catalogue worker (`scripts/library/catalog_export.py`, through
    `lw_canon`) and the server's library `render_worker.py` (the Lampway binary, `mixar.modules.lampway_tools.canon_io`).
  - FBX now reads through canon_io's `import_scene.fbx` (wave5 used `wm.fbx_import`). The asset tests read the `lw_raw` stamp.
    A new test drives the catalogue worker's mesh-import branch, which had no test (mutant `lw_canon.import_raw`: red).
  - asset_place and asset_catalog_export (two registrations) carry LEGACY: ratchet 120 -> 123, recorded.
  - The egress launch audit (wave5's) flagged job_backends' two headless launches; they are declared `local` in
    `egress.LAUNCHES`.
- **lp/wave5 at 704eba50 (e4cc94d).**
  - P / Def moved into wave5's `tool_defs.py`; Def gains the rig tools' `wip` there.
  - glb_optimize, lod_chain, motion_generate, terrain and ue/parity import through canon_io (their comments asked for it "once it
    lands"). Images keep no role, so the colour space behaves as before.
  - ue_material, ue_look, ue_export, ue_parity and the 28 wave 6 tools (`api._W6_DOORS`, one LEGACY call each, so the ratchet counts
    every tool still owing its door) carry LEGACY: ratchet 123 -> 155, recorded with this merge's parents.

### O36: the port (a935159), R1-R3 and the read-back (ab667a7), R4 and skin WIP (ec0529b)

- **Port.** Ported from the TITAN project, same author: `animation_canon`, `canon` and `skin_bind`, with their suites, the
  Blender read-back recipes and the measured profiles (`rig_convert/`).
  - Each file names its source and sha256, and NOTICE carries the provenance. Titan paths, names and crews are scrubbed.
  - The wire schema ids are unchanged (`titan.animation/1` etc.), noted as a stable wire contract shared with TITAN.
  - `anim-normalize-ue.py` lives under `ue_recipes/` with its sample config scrubbed. Its tests are `needs_box`
    (`LAMPWAY_UE_EDITOR`) and were not run here.
  - The Titan suites run unchanged against the port.
- **R1-R3.** rig_tools/core holds canon 16-18 and 21 against R01-R03, each upstream falsifier shown failing.
  - rig_inspect stamps the armature. Every later rig tool refuses an unread or changed armature.
  - The mixamo and rigify tables come from MB UE5 Rig Creator Pro 3.1.0 (GPL-3.0-or-later, attributed). The rigify table is
    verified against a Rigify rig generated headless. **The mixamo table is not verified against a real Mixamo rig.**
- **R4.** `rig_convert` covers profile / extract / normalize / adapt / retarget / compare / verify (A1 bars), publishing immutable
  outputs with receipts. G22.2-G22.4 pass on the port.
- **Skin and morph (WIP, as ruled).** `rig_skin` has `wip: true` in its Def, the WIP badge in its receipts and refusals, and cites
  canon 22 B.10 / canon 07 DRAFT.

### O36 R6 rig_conform (55adae3)

- **Built.** `core.conform_plan` (pure) plus `features/rig_conform` (Blender), always on a COPY:
  - UE names come from map.json. A colliding unmapped bone is renamed `<name>_src` first.
  - Torso bones are synthesized at the map's fractions (R01).
  - Each slot hangs from its nearest reference ancestor; unmapped bones keep their renamed parent.
  - Frames are built from head -> next joint plus the reference bone's Z, in one convention. ue_axes is mirrored where the
    reference's X points back.
  - Optional: roll offsets, UE ik bones (with a root when the rig has none), vertex groups in two phases, merge_weights only when
    named.
- **Verified in the tool.**
  - Heads are kept bit for bit.
  - The rest skin is checked against an untouched baseline copy.
  - A world-space test pose is applied to both rigs. A vertex group that did not follow its bone fails it (mutant: 0.13 m).
- **Deviations, recorded.**
  - The spec's rest-drift bar of 1e-9 m is below float32: a pure roll change drifts the skin 1.5e-7 m in Blender's own evaluation
    (probe). The bar is 1e-9 m plus 4 float32 ulps of the coordinates, and both are printed.
  - The spec says unmapped bones go to "their mapped ancestor". They keep their own (renamed) parent instead, so an unmapped chain
    (a tail) stays a chain.
  - The copy carries no animation.
- **Found while testing.** `core.angle_deg` (arccos of the trace) read float32 rest rounding as 0.014 deg, which is above canon 21's
  0.01 deg bar. It now uses the chord formula. On 400 bones, Blender's real edit-bone round trip is a median 4e-5 deg and at most
  1.1e-3 deg (near -Y).
- **RED** observed for the core and Blender tests and the small-angle test.
  - Mutants killed: no vertex-group rename; the up hint from the source frame; the ue_axes sign.
  - The Blender module was drafted before its Blender test. I set it aside, ran the test RED (no tool function), then reinstated
    the module.
  - The merge_weights test found a real defect: the merged bone was posed about its own head.

### O36 R5 rig_export_ue, the write half (6ed0e3a)

- **Recipes** state every exporter argument; a recipe that leaves one to Blender's defaults is refused.
  - `titan_cm_native` is the default, as the brief names it.
  - Two recipes are measured here: `cm_native_blender_convention` (primary X / secondary -Y) and `cm_native_ue_axes` (Y / X).
- **The read-back** imports RAW (automatic bone orientation off, no axis correction) and compares every bone at the bind_mismatch
  bars.
  - The file's own UnitScaleFactor is read with Blender's FBX parser. Blender's importer compensates it (NONE writes 1, UNITS
    writes 100, and both read back as scale 1), so G21.3's x100 shows only in the file.
- **Refused before writing:** mixed convention (G21.1), constraints, leaf bones, vertex groups naming bones the reference lacks, a
  different deform hierarchy, more than one action (one clip per file: a deliberate limit), an existing out, `readback=false`. A
  failing file moves to `export/rejected/` with its rows named.
- **CONCERN (measured, Blender 5.2 headless, 5-bone chain).** `titan_cm_native`'s primary Z / secondary X reads back 120 deg off on
  a canon-17 'blender' rig and 90 deg off on a 'ue_axes' rig. TITAN measured that pair in Unreal on the MetaHuman as its own
  Blender import laid it. Its Blender-side convention was not canon 17's. UE was not run here.
  - The default therefore refuses every canon-17 rig. Pass the measured recipe for the rig's convention.
  - A test records the fact. A UE-side read-back (needs_box) is the open check.
- **RED** observed. Mutants killed: auto orientation on, a constant UnitScaleFactor, no engine turn.
- **Not done:** the spec's "Upgrades" (`skeleton_export_check` frames and `fit_export` calling this read-back).

### O36 R7 rig_fit_template (d572b90)

- **Built.** TITAN rig-axi is the prior art: its `titan.rig-joints/1` schema, its 55 REQUIRED_JOINTS, the provenance sha and the
  six-ray inside check are reused, and the code is re-implemented. The GRT Mannequin is not used.
  - `core.fit_template` writes the measured heads (R06: residual 0, ratios 1.08 / 0.95).
  - Every other Manny bone is placed by its nearest measured segment's similarity. Parentless bones use the similarity of all
    joints (canon_geom.rigid); ik bones sit on their targets. copied_not_fitted fires at 0.1 %.
  - The example is a scene mesh (geometry sha256) or a file (file sha256).
  - Weights cover the body grammar only, from the fitted segments (canon_geom falloff, a 3 cm margin: Lampway's choice), on a
    copy. The armature and the copy are saved to the out .blend.
- **Refused:** 'views' and hands=views (no pose environment here; the detector is the captain's choice, canon 11).
- **Not built:** declaring "the example IS the template body", so INV-20.3's exception cannot be taken.
- **Found while testing.** rig_inspect read the fitted Manny as 'mixed' through ik_hand_root alone, at 24.3 deg: UE's ik roots copy
  the root's frame. The convention measure now skips ik_* bones, in inspect and in export.
- **RED** observed. Mutants killed: no provenance check; an inside check that always passes.

### O36 R9 rig_game_extract (44b5a1f)

- **Built.** GRT 4.3.0's Generate Game Rig and Convert Bendy Bones are re-implemented from their documented behaviour (no code
  copied), with the defects fixed.
  - G19.4: 5 kept, all 5 in the collection (GRT: 1 of 5), the spine's 4 constraints gone, 2 lotrot constraints per bone, follow
    error < 1e-5 m.
  - Hierarchy modes are keep / rigify_fix / flat.
  - root_scale_from=auto copies scale onto the game rig's own root only. On G19.4's probe, a copy onto the top bones would have
    added a third constraint.
  - Blender 5 selects pose bones, so `Bone.select` is gone.
- **Spec vs measurement (the spec governs).**
  - One bone per B-Bone segment leaves the tail joint without a bone. Blender blends joints k and k+1, so the skin drifts 1.87 mm
    on the probe.
  - `rig_game.TAIL_JOINT_BONE = True` adds that joint and is exact (1.2e-7 m). A test pins both.
- **RED** observed.
  - Mutants killed: GRT's in-loop collection reset; all of a bendy bone's weight on segment 0.
  - The second of those first survived. The baseline mesh had been re-pointed by the tool itself, so the comparison was empty. The
    test was rebuilt with an unbound baseline.

### O36 R10 rig_bake (444f6c6)

- **Built.** The sampled evaluated pose is written as LOCAL keys through Blender's space conversion, then played with the
  constraints muted and compared per frame. An action over the bars is removed and reported failed.
  - GRT's naming / ranges / overwrite / offset / NLA semantics are kept.
  - The driver's action is restored.
- **Found by the first green run.** The verifier measured positions on a rotation-only bake. It now measures only the channels that
  were baked.
- **Interpretation, recorded:** `trim:[a, b]` trims a frames from the start and b from the end.
- **RED** observed. Mutant killed: the armature-space matrix keyed as the local one.

### O36 R8 rig_retarget (4bf40e4)

- **Built.** `rig_retarget` sits beside `animation_retarget`, which is unchanged. The alias and the end of per-run preset writing
  are NOT done, to avoid moving its callers.
  - The rule is W_s R_s^-1 R_t, solved parent-first. Bones below the pelvis get rotation only.
  - Pelvis travel scales by the pelvis-height ratio. root_bone (R05) gets yaw none | heading; the facing is the rest's -Y turned by
    the pelvis's change.
- **R04 on armatures:** the golden is met to 2e-6, lengths are unchanged, and the local-copy falsifier measures 55.7 deg.
- **R05 on armatures:** both modes are exact.
- **canonical_agreement_deg** stays null with a pointer to rig_convert. G22.2 is pinned in the core test (and in
  test_rig_convert_g22).
- **RED** observed. Mutants killed: the local copy; a root copying the pelvis's rotation.

### O36 R11 rig_rest_pose (7a79ecf)

- **Built.** The rest change happens on a COPY.
  - The new rest mesh is LBS_P(v0): C02's posed mesh to 5e-8 m. C02 is vendored under `canon_goldens/rig/` as public synthetic data.
  - Actions are copied with keys AND handles re-expressed (an affine map per channel group), so the copy plays exactly between
    keys (mutant: 45 mm).
  - The return cost (R07) is 12.5 mm on 46 vertices against 0.
  - No chaining. No join, UV rename or action deletion.
- **Measured and pinned:** blended vertices differ by 8 mm under the re-expressed animation. A blend over a baked blend is not the
  original blend (canon 04); that is the cost of any rest change.
- **Not built:** pose 'reference' (a profile's reference posture). It is refused and names pose.json / action:<name>:<frame>.
  Euler-keyed rotations are refused (quaternion only).
- **RED** observed. Mutants killed: unmapped handles; keys copied unchanged.

### O36 concerns

- `rig_convert/recipes/anim-profile-manny.json` is a measured UE5 Manny bone table (Epic mannequin measurements) in the public
  repo; flagged for the captain's review.
- I explored this lane's code with `grep` through Bash. The hook did not refuse it, and codebase-memory could not index
  `wt-orphans`: "a pre-coordination or unverified CBM generation is active". No graph receipts back this lane's lookups.

## Test totals against the baseline

### At the end of O36 (this head)

The baseline is origin/lp/wave5 at `704eba50`. It ran on a detached worktree with a copy of the same binary, with its own Python
synced in. The head runs used this lane's binary (`LAMPWAY_BIN`). Each run had its own `--basetemp` under the lane's scratch,
deleted after reading.

The full suites ran on the tree of the second merge before the rail repair below. The repaired head e4cc94d differs from that tree
only in the coding-guidelines skill's anneal row (and its generated copies) and the ratchet file's parent sha. At e4cc94d the door
and rail tests were re-run: 57 passed.

| suite | baseline 704eba50 | head | delta |
|---|---|---|---|
| server (`server/tests`) | 1373 passed, 10 skipped, 0 failed | 1380 passed, 10 skipped, 0 failed | +7 passed |
| client (repo root, `--continue-on-collection-errors`) | 8517 passed, 117 failed, 85 skipped, 20 errors | 8765 passed, 118 failed, 89 skipped, 20 errors | +248 passed |

- The client failure set at the head equals the baseline's plus one row, `tests/rail/test_rail_gate.py::test_this_repository_
  passes_its_own_rail`.
  - That row was mine: RAIL-013 at the first wave5 merge. The merge combined both lanes' launcher lines without the owner skill's
    anneal row.
  - Repaired by re-making that merge with the row and the skill's launcher bullet, worded exactly as the integrator's receipt on
    lp/wave5. The eight lane commits after it were replayed unchanged and the second merge re-made (shas in this report are the
    new ones; nothing had been pushed past ec0529b). `rail.py check`: PASS.
- The 20 collection errors and the other 117 failures are the baseline's. They include five live tests of compiled data (icons,
  themes, the Asset Vault editor type), which need a binary built from the merged C sources; this lane's binary and the baseline's
  copy both predate them.

### Earlier (O1-O39, kept)

Baseline = origin/lp/wave5 `00d907d4`.

| suite | baseline 00d907d4 | HEAD 2dcba1fc | delta |
|---|---|---|---|
| server (`server/tests`) | 1069 passed, 6 skipped, 0 failed | 1164 passed, 6 skipped, 0 failed | +95 passed |
| client | 7904 passed, 123 failed, 75 skipped, 20 errors | 8074 passed, 124 failed, 76 skipped, 20 errors | +170 passed; 1 new failure (export_parts' AXI prelude, fixed in f5713e18) |

## Merge notes for the integrator

- **Shared files with conflict risk.**
  - `lampway_tools/api.py`: the star-imports of orphans_api and rig_api, the `_W6_DOORS` table, the ue_* LEGACY decorators.
  - `agent/tool_defs.py` (Def.wip), `agent/lampway_tools.py`, `agent/tools.py`, `agent/turns.py`, `agent/swarm.py`, `app.py`,
    `egress.py` (LAUNCHES).
  - `runner.py` (consumes on every row), `canon_legacy_count.txt` (three recorded rebaselines), `test_canon_doors.py` (the
    rebaseline rule).
  - wave5's asset_place / catalogue / render worker and the five wave 6 importers, now routed through canon_io.
  - `server/tests/test_prompt_images.py` (the count pin is 32).
- **The ratchet.** It stands at 155: 10 orphan texture/list tools, 3 Asset Vault registrations, 4 UE look tools, 28 wave 6 tools,
  and the rest pre-existing. Each owner lowers it as they declare a real Need/NONE; a rise outside a recorded merge rebaseline is
  refused.
- After lp/docs merges, regenerate `docs/tools.md` with `docs/gen_tools.py`.
- The live client tests of compiled data (icons, themes, the Asset Vault editor type) need a binary built from the merged C
  sources. This lane's binary predates them (see the totals).
- The moodboard templates ship in the public repo, as the captain asked; the PII gate is at 0.
