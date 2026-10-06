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
| asset_place | done (P0 and P1 kinds, catalogue export and link); drag-and-drop not built (C++ dropbox) | ac30942c, b4e1f6a8 (NLA strip), 2f2288f7 (brand word) |
| asset_mcp + wiring | done | ac1a3ff8 |
| asset_ui_editor | done for surfaces A, B and E's export verb; C (island tab) and D (chat LIBRARY mode) not built | 335f04e2, 068b6be9 (cards panel in it) |
| asset_ui_views | partial: views drawn from server products; no gpu canvas pan/zoom, no clip-to-clip alignment | 74825a29, b4e1f6a8 |
| mrmak 09 report cards | done except the light theme (P2) and the Workbench-window embed | 5d53f750, 068b6be9, 2f2288f7 (content port without a raw socket) |

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

## Test totals against wave5.md (server 900 passed, 5 skipped; client 753 passed, 46 skipped)
Run on 29319e6b (the same tree as 2f2288f7 but for the two-line test literal below):
- server (`server/`, venv-tools): **1106 passed, 6 skipped, 0 failed** (lp/wave5's own library commits added about 180 tests before this lane; this lane adds the
  library_mcp / vault_tools / e2e / rest / views / cards / cards_routes files). An earlier full run caught `cards/content.py` importing `socket` (the egress door test);
  fixed in 2f2288f7.
- client (`tests/lampway_tools`, real binary `blender-lanes/vault-ui`): **781 passed, 46 skipped, 0 failed**.
- standalone: `tests/asset_library` 29 passed, `tests/test_texturing_space_menu.py` passed.
- `tests/lampway` (brand and gate checks): 4 failures, the SAME 4 on the integration base 00d907d4 (checked in a detached worktree): material_bake_export's and
  mcp_inventory's "Mixar" strings, the allow-list's `/home/x` entry, eight provider hosts in fal.py and studios/rest. This lane's own "Mixar Paint" strings were renamed.
- Pre-publish gate over origin/lp/wave5..HEAD: the first pass found a home-directory path in a test literal in the editor commit; the lane's unpushed commits after the integration
  merge were replayed with the literal changed to `/projects/...` (the only difference, checked by `git diff`); the gate then reported 0 findings.

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
