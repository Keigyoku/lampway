# Lane vault-ui (branch lp/vault-ui, from lp/wave5 at 61dff5c8)

Contracts: asset_place, asset_mcp (+ the wiring the coordinator added), asset_ui_editor, asset_ui_views, mrmak 09 report cards. Each test was written first and seen failing
for the expected reason before the code existed, except where this report says otherwise. Mutants were run on the guarding lines (`scratch/tmp-vault-ui/mut.sh`: one exact
replacement, run, restore); survivors are listed.

The code graph could not be used: `index_repository` on this worktree (and on `server/` alone) refused with "a pre-coordination or unverified CBM generation is active"
three times; the graph only answered for the upstream `mixar-addon` index (used for `is_mp_on_material`, `get_active_mpaint_node`, `_ensure_catalog_entry`). The tree was read
file by file.

## Per contract

| contract | state | commits |
|---|---|---|
| asset_place | done (P0 and P1 kinds, catalogue export and link); drag-and-drop is native work, handed to the facelift lane by the coordinator | ac30942c, b4e1f6a8 (NLA strip), 2f2288f7 (brand word) |
| asset_mcp + wiring | done | ac1a3ff8 |
| asset_ui_editor | done: A docked, B pop-out, C island tab (a8d26a7a), D chat LIBRARY mode (f0e4b99d; the mode listed again on the captain's word, see the decision), hotkeys (87b0790a), E export verb; the label rename is native (facelift lane) | 335f04e2, 068b6be9, a8d26a7a, f0e4b99d, 87b0790a |
| asset_ui_views | done on this lane's side: views, gpu pan/zoom canvas (87b0790a), clip alignment and the board canvas (568fe0ab); turntable, ball and proxy frames wait on vault-ops' asset_render/asset_video (not on origin/lp/wave5 at the last check) | 74825a29, b4e1f6a8, 87b0790a, 568fe0ab |
| mrmak 09 report cards | done, light theme and Workbench frame included; the Workbench window page itself (facelift contract 10, `server/lampway_server/web/workbench/`) does not exist on lp/wave5, so the frame is ready but not mounted | 5d53f750, 068b6be9, 2f2288f7, d55f9ae2 |

### asset_place
- `features/asset_place.py` (record, transaction, drop point, meshes), `asset_place_shading.py` (material onto a slot, PBR/texture sets by role, node groups, HDRI world),
  `asset_place_media.py` (reference image, clip or sequencer strip, action onto a matching armature or as an NLA strip, rig bound to a mesh), `asset_catalog.py` +
  `scripts/library/catalog_export.py` (headless worker, UUID5 catalogue ids, register as a Blender asset library), `library_client.py` (the record from the server, the
  `placed` event). Server Defs `lampway_vault_place`, `lampway_vault_catalog_export`.
- The resumed attempt had written `asset_place.py` and its test with no observed RED. I moved both implementation pieces aside, ran the six tests (all failed: "no tool function
  'asset_place'"), restored, and kept them (6 passed).
- Falsifiers: the DX normal is proven by render (a DX set and its GL twin render alike; the DX map read as GL does not). Mutants killed: no green flip; Mixar Paint guard off;
  outer discard removed (killed by the animation refusal: a refused action stayed behind as `WalkCycle.001`); bone-mismatch guard off; CAS link guard off; UUID5 -> uuid4.
- Choices the contract left open, said here: an image places as a reference empty under mode name `reference_image` (the contract names the behaviour, not a mode); `attach_rig`
  parents the target mesh to the armature with an Armature modifier; texture-set members are assets `part_of` the set (asset_schema line 36); ORM's R (occlusion) is left
  unconnected (Principled has no input for it); FBX actions are refused (only .blend actions place).
- After the captain's naming ruling the refusals name the real tools: "the file moved: re-run lampway_vault {action: verify}" (the contract said `lampway_asset_library verify`)
  and "use lampway_vault_render for an overlay" (vault-ops' tool name under the same ruling, not yet built).

### asset_mcp and the wiring (coordinator's addition)
- Tool names: BUILD_ORDER.md Wave 5b item 3, the captain: "MCP tool names (lampway_vault_*)". The contract says `lampway_asset_*`; the ruling wins. The family, adopting the
  integrator's draft (`scratch/test_library_vault_tools.draft.py`, now `server/tests/test_library_vault_tools.py`, with its embed test corrected: seeded bytes that are not a GLB
  give no shape vector, so it now uses real PNGs): `lampway_vault`, `_search`, `_get`, `_similar`, `_scan`, `_relate`, `_rate`, `_collect`, `_provenance`, `_embed`.
- `agent/vault_tools.py`: an authority table per tool and per origin (agent, worker, mcp); nobody holds `spend`; a worker holds no `write_ingest`; scan only inside the project
  root or a source the user registered; import, watch and an uploading embed run are the user's (the landed `Ingest`/`Embed` already refuse a non-user, kept); unknown
  arguments refused (the rater is never chosen); a limiter (120 calls, 20 writes per minute, sizes [UNVERIFIED] as in the contract).
- `library/vault.py`: ONE `AssetLibrary` per process (the store's flock refuses a second writer in the same process too), opened lazily, closed in the app lifespan;
  `library/rest.py`: status, query (pictures carry their own path as thumbnail), assets/{id} (members via part_of), versions, files/{sha} (FileResponse), sql, events
  (`placed`), ingest scan/import as the user, rate, similar, collect, embed, relate, lineage, views, diff.
- `app.py` builds the Vault and passes it to the AgentHub; the agent's search left `AssetIndex`: `agent/asset_tools.py` and its test were deleted (no test needed a compat
  path). The legacy `/api/v1/asset-search/*` routes still use `AssetIndex` (the Client's Train/Search UI and `test_asset_search.py`).
- MCP offers the family and answers it on the server with no desktop connected; swarm workers get the read and curation tools, attributed `agent:<worker id>`.
- End-to-end: `test_library_e2e.py` - create_app with lifespan, scan and import over REST, a scripted agent turn calls `lampway_vault_search` and finds the asset, MCP finds it
  with no instance, the record and file routes, the `placed` event row.
- Mutants killed: worker granted ingest, import by "captain", jail off, bare `where` not wrapped (needed a new test: the draft only used trees), unknown-argument check off,
  uploading run as captain, limiter off, registered-source rule off, MCP not offering, swarm dispatch off, members off. Equivalent: rating with origin "user" (the rater is
  always `agent:<id>`, so curate's captain check cannot fire).
- RED for the rename was seen by the adopted draft failing on import; the `where` bare-condition test passed on first run and was shown to bite by its mutant.

### asset_ui_editor
- `modules/asset_library/`: `core/viewmodel.py` (pure: debounce, stale answers dropped, paging cursors, selection set/toggle/range, facets, offline, empty text, Initial
  import preview -> confirm, find like this, compare, detail and view products), `core/pump.py` (HTTP off the main thread, answers on the timer tick), `core/present.py`
  (similar chip, dated provenance lines and the one-line glance, the tile bed draw list, stats rows), `core/session.py` (timer, previews LRU), `ui/properties`, `ui/operators`
  (16 operators), `ui/panels/vault_panels.py` (header + facets | results | detail). The paint stub's classes are retired; `tests/test_texturing_space_menu.py` now pins the
  Vault header (title "Asset Vault", after `template_header()`); that pin moved files, its RED was not separately observed.
- Initial import (BUILD_ORDER 5b item 4): a folder is scanned and previewed ("17 files: 12 image, 5 mesh (2 already in the Vault, 2 not imported)"); import only on the
  user's confirm; refused with no preview. One root per scan; several roots and specific files are not built (the landed `scan` takes directories).
- Probe (contract 6.1), windowed under Xvfb in the lampway-build box against a live server (`scratch/vault-ui-live/`, synthetic seed of 15 files -> 13 assets):
  (a) `MIXAR_ASSETS` is in the space enum (headless test); (b) the C++ already lists it in the Editor Type menu (`test_texturing_space_menu.py`); (c) `screen.area_dupli`
  opens the pop-out: FINISHED, windows 3 -> 4, the new window holds one MIXAR_ASSETS area: no C++ needed; (d) region keymaps were NOT probed, so no hotkeys; (e) a Python
  POST_PIXEL draw handler draws over the panel region (the amber square in `vault_popout.png`).
- Acceptance captures: `scratch/vault-ui-live/vault_docked.png`, `vault_popout.png`, `vault_main_after.png`, `probe.json`. The token came from a password login in the probe
  (the SSO browser hop is not part of this check); the theme in the capture is Blender Dark: this lane's binary predates facelift's Night theme.
- Not built: island Library tab and chat LIBRARY mode (P1), C++ drag sources and dropboxes (P1), hotkeys, the editor rename in the C++ enum label (still "Texturing Assets";
  a one-line C++ change for the facelift lane's build), pop-out size memory.

### asset_ui_views
- Server `library/views.py`: lineage layout (layers so parents sit left, ordered by creation then id, depth and node limits, collapsed count), its PNG and hit test, image
  diff (mean abs + windowed SSIM; a 1 px shift gives SSIM < 0.99), per-asset view products by role (`turntable:N`, `ball`, `overlay`, `sheet`, `thumb`, `strip`, proxy frames
  under `derived/<version>/proxy`).
- Client `core/views.py` (flipbook clock 6..24 fps, view status naming the producer, compare refusal, duplicate-frame chip, fps badge, normal stamp) and the detail column's
  mode segments; To timeline = an NLA strip at the current frame.
- Mutants killed: layering off, depth limit off, hit test on x only, SSIM without the variance term, within-layer order by id (a layer-only order needed a wider fixture and
  ids that descend against time before it died under three hash seeds).
- Headless fact: preview `icon_id` is 0 in `-b`, so the panel names the frame file when there is no icon; pictures are a windowed check.
- Not built: the gpu canvas with pan/zoom and click-to-select on the lineage picture (the probe shows the handler composes; the drawing is not written), clip alignment
  modes (asset_video's), the overlay stack, boards as a free canvas, the winner button. Products come from vault-ops' asset_render/asset_video, which are not on lp/wave5
  yet: every view shows its "queued (asset_render)" line until they land.

### mrmak 09 report cards
- Server `cards/`: `registry.py` (unknown fields kept, fcntl + thread lock, atomic replace, step bounds), `archive.py` (7-day rule, pinned, search into the archive),
  `build.py` (design rounds, motion tests, receipt; deterministic bytes; escaped prompts in `<details>`; media copied into the card), `content.py` (own origin and port,
  GET/HEAD, Host 421, grants, jail, private names, ranges), `activity.py`, `assets.py` (css and a lightbox written for Lampway, not a copy of upstream), `service.py`,
  `routes.py` (/app/cards...), agent tool `lampway_cards`; Blender `modules/cards` (Project cards panel in the Vault, refresh, pin, status, rebuild, open in the browser).
- Mutants killed: lock off, private names off, escaping off, unknown fields dropped, archive at 5 days, jail off.
- The routes test was written before the wiring but first run after it; its RED was then observed by removing the wiring (3 failed) and restoring (3 passed).
- Open questions kept as the contract's defaults: cards under the project root; one card per piece.

## Remainders (second pass, after the coordinator's list)

1. **Island Library tab** (a8d26a7a). `agent_bubble/core/library_vault.py`: the pane's `mixar_generations_files` rows gain the Vault's pictures and clips under the
   library name "Asset Vault", from ONE query whose payload is the editor's own (`session.VM.payload()`, now with `include: path`); run off the main thread from the island's
   pump at most every 10 s. Meshes and other kinds stay in the Vault editor: the C++ tile has only image and video kinds (a mesh tile is native work). A page can carry each
   asset's main file path (`include: path`, server). Tests: `test_island_vault.py` (one request equal to the editor's payload, answer lands on the tick, rows exact,
   throttled), mutants on the kind filter and the throttle killed.
2. **Chat LIBRARY mode** (f0e4b99d). `space_mixie_chat/core/library_vault_chat.py`: browse and text search ask the Vault off the main thread with a token; a picture is its
   own thumbnail; a click places through `asset_place`; an attached image still goes to the trained index (the old path). The mode was retired upstream; the captain brought it back (see the
   decision below). The "never opens a .blend" claim is proven against an enrolled library
   holding a real .blend: the spy sees the old scan open it, then sees nothing on the Vault path; a mutant that reruns the old scan is killed.
3. **Hotkeys** (87b0790a). `core/hotkeys.py` (pure table and plan) and `ui/operators/vault_keys.py` (one operator, poll = mouse over a Vault area) in the add-on
   keyconfig's **User Interface** keymap. Windowed probe (Xvfb in lampway-build, Blender's own `--enable-event-simulate`): 4, X, F, C and P reached the operator and the
   rating 4 landed on the live server. Two facts measured on the way: xdotool events did not reach the Xvfb window at all, and in the **Zen Mode** workspace no keyboard
   shortcut fired, Blender's own ctrl+Space included (the Layout workspace works). The first attempt used the "Window" keymap and was never polled in Zen; whether it
   would work in Layout was not measured.
4. **Pan/zoom canvas** (87b0790a). `core/canvas.py` (pure mapping: fit, zoom about the cursor, pan, top-left image pixels for the hit test), `core/canvas_view.py` (gpu
   POST_PIXEL handler, scissored to the canvas), `ui/operators/vault_canvas.py` (modal: wheel, middle-drag, click a lineage node, Esc). While open, the body is only the
   canvas bar. Windowed: two wheel steps took the zoom 5.90 -> 9.22 (x1.25 twice), a click selected the clicked node, Esc closed it; capture `canvas_zoomed.png`.
5. **Clip alignment and the board canvas** (568fe0ab). Server `views.clip_align` (start, time at the faster rate, motion = the last still frame before each clip first
   moves; the motion threshold is chosen, not calibrated) over the proxy frames asset_video will write, route `/clip_align` (refuses "no proxy frames yet: queued
   (asset_video)"); `Vault.board_move` and `/boards/{board}/items/{asset}` (order and note kept); board tiles carry their picture. Client: two clips as one flipbook of
   pairs with Start/Time/Motion; boards listed in the facet column and opened on the canvas, tiles drawn with gpu and blf, dragged and saved. Windowed: a tile dragged
   by simulated events moved (16,16) -> (114,53) and the server returned the same place; the dragged tile drew under its neighbour (`board_after.png`), so it is now raised
   on press (test written from that capture).
6. **Report cards' light theme and Workbench embed** (d55f9ae2). The light theme is a serve-time prelude (`?theme=light` adds `data-lw-theme="light"` to a report marked
   `data-lw-report="document"`; unmarked pages and images are served as they are; the file on disk never changes); Blender opens a card in its own UI's light. The
   Workbench frame (`/app/cards/{id}/frame`) is the card in the contract's sandboxed iframe on the cards' origin.

Normalization rule (coordinator, during this pass): the two raw importer calls this lane owns are marked `# LEGACY(normalize)`: `asset_place.py` `_import` and the catalogue
worker `scripts/library/catalog_export.py`. No new raw landing was added: the island, the chat and the editor all place through `asset_place`. `canon_io` was not on
`origin/lp/wave5` at the last check, so the switch to `lampway_normalize_mesh` is still owed.

Not done, and why: the turntable / ball / proxy-frame switch to real products waits on vault-ops (`origin/lp/wave5` had none of it at each item boundary); the Workbench
window page and the C++ items are other lanes'. The clip-pair view was not driven in a window (the live Vault has no proxy frames until asset_video lands).

## Decision: Library mode is back (the captain, 2026-10-06: "yeah bring LIBRARY mode back")

- `scene.mixie_chat_mode` lists `('LIBRARY', "Library", ..., 'ASSET_MANAGER', 4)` again, on its old value 4, so a .blend saved in Library mode before the retirement opens
  in Library mode; value 2 (the old ASK) stays reserved. The load sanitizer keeps LIBRARY. Every dropdown (C++ chat footer, bubble footer, bubble menu) binds the one
  property, so it shows everywhere; the quick-prompt operators still only enter AGENT and GENERATE.
- Switching into the mode schedules the Vault's first page (`library_browse._show_all`, a named timer so it can be checked); Enter runs the Vault search.
- Found while testing: the composer's `can_send` refused Library sends whenever no agent session was connected ("Not Connected"). Library talks to the Vault over REST,
  so `can_send` now allows a send in LIBRARY mode (pending video attachments are still refused first).
- Tests: `tests/test_library_mode_retired.py` became `tests/test_library_mode_available.py` (listed on value 4, value 2 reserved, one property for every dropdown,
  quick prompts unchanged, files load in Library mode, send and switch reach the Vault; RED observed on the two contract changes); `test_chat_library_vault.py` no longer
  re-lists the item itself and gains `test_selecting_library_mode_shows_the_vault_and_enter_searches_it` (RED observed: "enum LIBRARY not found", then "Not Connected").
  Mutants killed: the can_send exemption, the first-page timer, LIBRARY dropped from the load sanitizer.
- Suites after this change: server 1113 passed, 6 skipped; client (`tests/lampway_tools`) 788 passed, 46 skipped, 0 failed; the standalone suite (`tests/` without
  lampway_tools; 5 tests/mcp modules fail to import `mcp.Client` in venv-tools) 87 failed and 20 errors, the SAME 108 ids as the integration base 00d907d4 run the same
  way (diffed: none new, none gone).

## Test totals against wave5.md (server 900 passed, 5 skipped; client 753 passed, 46 skipped)
Second pass, run on d55f9ae2 plus the two LEGACY comment lines:
- server: **1113 passed, 6 skipped, 0 failed**.
- client (`tests/lampway_tools`, this lane's binary): **786 passed, 46 skipped, 1 failed**. The failure was `test_wave2_bake_maps.py::test_a_bake_never_overwrites_an_existing_map_and_the_live_scene_is_untouched`
  (`TypeError: argument of type 'NoneType' is not a container`); it passed alone right after (6 of 6 in that file) and in the first pass's full run; this lane does not touch
  bake_maps. Treated as a flake under load, not explained.
- standalone: `tests/asset_library` 43 passed with the menu, retirement, folder-media and browse-hardening tests; `tests/lampway` keeps the same 4 failures as the integration
  base 00d907d4 (offender lists unchanged: material_bake_export, mcp_inventory, the `/home/x` allow-list entry, eight provider hosts).
- First pass (29319e6b): server 1106 passed, 6 skipped; client 781 passed, 46 skipped.
- Pre-publish gate: see the push.

## Merge notes
- `app.py`: separate hunks (imports, the Vault next to `AssetIndex`, two route spreads, `vault.close()` in the lifespan, `app.state.vault`). Lane vault-ops's provenance hook
  must use THIS Vault (`vault.lib`, `vault.spool`): a second `AssetLibrary` on the same state dir is refused by the store's writer lock, even in the same process. The Vault
  is created after the JobQueue today; their hook will need it created first.
- `agent/asset_tools.py` is deleted; anything importing it must move to `agent/vault_tools.py`.
- The paint module's `assets_panel.py` now registers nothing; the MIXAR_ASSETS space belongs to `modules/asset_library`.
- Needs a decision (integrator / facelift): the Editor Type label "Texturing Assets" -> "Asset Vault" is a C++ string in `rna_space.cc` and needs a native build.
- Files over the 500-line rule that this lane touched were already over it (app.py 1035, api.py 1574, lampway_tools.py 585, turns.py 542); each gained only a few lines.
  Every new file is under 500.
- Finding for the library owner: `similar`'s look axis intersects image_hist and image_dhash; with only one space indexed, the probe's on-demand vector empties the result.
