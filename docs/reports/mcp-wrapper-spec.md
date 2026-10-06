<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Lampway MCP: one server for agents — specs and contracts

Status: **planned** (a proposal with the captain's decisions recorded), 2026-10-06, written against `lp/wave5` at `fd0f108`. Nothing here is built. Findings F1–F25 come from the stress-test audit of the same day, whose report is not in this repository; each finding a
contract depends on is restated where it is used. Claims not yet checked on a
running app are marked `[UNVERIFIED]`; the audit run that follows checks the ones it can and says which.

Normative inputs:
- **AXI** (agent eXperience interface, https://axi.md): ten principles for agent-ergonomic tools. Quoted where used as `AXI n`.
- **TOON** (https://toonformat.dev/reference/spec): the site states **Spec v4.1 (2026-07-25)**; `toon-format/spec` main is
  already **4.3 (2026-10-06)**. Quoted as `TOON §n`. Decision below (C0) on which to pin.
- **Lampway's contract template** (`.claude/skills/lampway-tool-authoring/SKILL.md` §1) and its gates
  (`.claude/skills/lampway-agent-tools/SKILL.md`).
- **Blender Lab MCP** (`lab/blender_mcp` v1.0.3, GPL-3.0-or-later, 26 tools): what an agent would otherwise run beside Lampway.

## 0. Why: what an agent needs a second server for today

| Need | Blender Lab tool(s) | Lampway today | Covered by |
|---|---|---|---|
| Blender API / manual lookup | `get_python_api_docs`, `search_api_docs`, `search_manual_docs` | none | T3 `lampway_blender_docs` |
| File facts (data-block counts, missing files, libraries, path, usage guess) | five `get_blendfile_summary_*` | none (`scene_summary` is objects only) | T1 `view=file` |
| One object in depth (modifiers, constraints, collections) | `get_object_detail_summary` | none | T1 `view=object` |
| Collection hierarchy | `get_objects_summary` | `scene_summary` (flat) | T1 `view=scene` |
| Frame an object | `jump_to_view3d_object_by_name`, `..._data_by_name` | none | T2 `action=focus` |
| Screenshot of one editor area | `get_screenshot_of_area_as_image` | `lampway_ui_observe` (whole window, opt-in) | T2 `action=screenshot` |
| Render with current settings / a thumbnail | `render_viewport_to_path`, `render_thumbnail_to_path` | purpose-built renders only | T2 `action=render_still` |
| Window layout as data | `get_screenshot_of_window_as_json` | `lampway_ui_observe` / `lampway_ui_context` | already covered |
| Run Python | `execute_blender_code` | `run_blender_python` (sandboxed) | already covered, safer |
| Headless `--background` file runs | `*_for_cli` | none | **not proposed**: Blender Lab writes `<file>_mcp_NNNN.blend` beside the user's file, which Lampway forbids |

Beyond parity, what neither has: **the minute details as data** — polygon counts, shells, holes, parts, UV islands and
overlap, paint layers, and how objects relate in size and position — in one read-only call (T1 `mesh`, `uv`, `parts`,
`layers`, `relations`).

AXI's benchmark finding that shapes the design: MCP schema overhead scales with tool count (MCP conditions averaged 185K input
tokens per task vs 79K for AXI). Lampway already offers 188 tools over MCP. So the wrapper adds **three** tools, not ten, each
with a `view`/`action` argument, and returns TOON.

## C0. One conformant TOON encoder (cross-cutting, prerequisite)

**Purpose.** Every tool output in this spec is TOON. The tree has two encoders and neither conforms; data can be corrupted.

**Source (measured 2026-10-06 on `lp/wave5`):**

| Input | `lampway_tools/axi.py` | `server/.../compute/toon_out.py` | TOON requires |
|---|---|---|---|
| empty list | `seeds[0]:` | `seeds[0]:` | `seeds: []` (§9.1, MUST NOT emit `[0]:` since 4.1) |
| `1234567.0` (a float count) | `1.235e+06` | `1.23457e+06` | `1234567` (§2: no exponent in [1e-6, 1e21), fewest round-trip digits) |
| `"true"`, `"42"` | quoted (ok) | `true`, `42` unquoted → decodes as bool/number | quoted (§7.2) |
| `"x: y"`, `"-x"`, `"#c"` | quoted (ok) | unquoted; `#c` becomes a **comment line and is dropped** (§5.1) | quoted (§7.2) |
| key `my-key` | quoted (ok) | unquoted | quoted (§7.3) |
| rows `{a:1}`, `{a:2,b:3}` | n/a | `rows[2]{a,b}:` with an invented `null` | list form (§9.4): non-uniform keys disqualify tabular |
| list value in `kv` | `"[1, 2]"` (a string) | n/a | `tags[2]: 1,2` (§9.1) |
| document end | trailing newline (`print`) | none | no trailing newline (§12) |

`tests/lampway_tools/test_axi.py::test_empty_table_is_a_definitive_zero` pins the non-conformant `seeds[0]:`.

**Contract.**
- Name: `lampway_toon` (pure module, no bpy, no third-party deps), one copy shared by client and server (client
  `src/scripts/mixar/modules/common/toon/`; the server imports the same file through the existing `lampway_tools` path or a
  vendored copy kept identical by a test).
- API: `encode(value, *, delimiter=",", indent_size=2) -> str`; `decode(text, *, strict=True)` (for tests and the Studio
  reader); `axi.home/kv/table/helps/refuse` re-implemented on top of `encode` so their call sites do not change.
- Target: **declare `toon-spec: 4.1`** (the version the reference site publishes, and the one the code already claims), and
  emit the 4.2 encoder tightenings as well (shortest round-trip numbers, minimal quoting, lowercase `\u` hex): 4.2/4.3 output is
  valid 4.1 input, and 4.2/4.3 only changed decoder edge cases no conforming encoder emits. Re-pin when the site moves.
- Normalisation (§3): NaN/±Inf → `null`; `-0` → `0`; tuples/sets → arrays; `mathutils.Vector/Matrix/Euler/Quaternion` →
  arrays of numbers; unpaired surrogates → error; everything else not JSON → `null` (documented).
- Form selection exactly per §9 (inline primitive arrays, tabular with nested field groups, keyed tabular for objects of ≥2
  uniform objects, list form otherwise); `key: []` for empty arrays; no comment lines; no trailing spaces or newline.
- The AXI CLI scripts keep printing to stdout; `print(encode(x), end="")` replaces `print`.

**Tests (RED first; each falsifier is one row of the table above).**
- `encode` passes the **official TOON conformance fixtures** (Appendix C, `toon-format/spec` `tests/`, MIT) for encode; vendored
  under `tests/toon/fixtures/` with their licence and REUSE entry.
- Round trip: `decode(encode(x)) == x` under §2 JSON-model equality for a property-based corpus (hypothesis) including the
  table's inputs.
- `test_empty_table_is_a_definitive_zero` changes to expect `seeds: []` (still AXI 5's definitive zero).
- Studio reader (`studios/toon.py`) still parses every driver output after the switch (its fixtures).

**Side effects.** None at runtime beyond output bytes. **Version (Q4, 2026-10-06):** pin TOON 4.1, the published site, and emit
4.2's stricter encoder output.

## C1. The MCP result envelope (AXI applied to Lampway's MCP)

**Purpose.** Make every new tool's reply cheap for the model and typed for programs, and let the server return images.

**Today.** `server/lampway_server/mcp.py` `_result` returns one text block holding `json.dumps` of the client envelope;
no `outputSchema`, no `structuredContent`, no image blocks. Images exist only on the local stdio path
(`common/ui_control/core/observe.py`).

**Contract (for the three new tools; existing tools opt in later).**

| AXI | Rule |
|---|---|
| 1 Token-efficient output | `content[0]` is `{"type": "text", "text": <TOON document>}`. |
| (typed data) | `structuredContent` carries the same data as JSON, validated against the tool's `outputSchema`. **Equivalence is a test:** `toon.decode(text) == structuredContent` (§2 equality). Codex keeps getting text only (`mcp_bridge/core/presentation.py` already strips `structuredContent` for Codex). |
| 2 Minimal default schemas | List rows default to 3–4 fields; `fields: [...]` adds named columns; `fields: ["*"]` gives all. Unknown field names refuse (see AXI 6). |
| 3 Content truncation | Long strings cut at `max_chars` (default 200) with `"... (truncated, 2847 chars total; full=true)"`; lists cut at `limit` (default 50). |
| 4 Pre-computed aggregates | Every list is preceded by `count: <n> of <total> total` when truncated, `count: <n>` otherwise; summaries carry totals (`tris_total`, `holes_total`, `overlap_fraction`). |
| 5 Definitive empty states | An empty list is `holes: []` with `count: 0`; never an omitted key. |
| 6 Structured errors | A refusal is `isError: true` with TOON `error: <why>`, `code: <slug>`, `help[N]:`. Unknown arguments **refuse** (`code: unknown_argument`, the MCP analogue of exit 2), and every input schema sets `additionalProperties: false`. Read-only views are idempotent; the one mutation (`focus` with `unhide`) is idempotent too. Nothing prompts. |
| 7 Ambient context | `lampway_inspect` with no arguments is the dashboard the launcher's guide tells agents to call first (C2). |
| 8 Content first | No-argument call returns live data plus `tool:` and `description:` lines, never a help page. |
| 9 Contextual disclosure | Every reply ends with `help[N]:`, items written as call templates `lampway_inspect view=mesh name=<name>`: fixed arguments carried forward, runtime values as `<placeholders>`, never guessed. |
| 10 Consistent help | `view=help` (T1, T3) / `action=help` (T2) returns the per-view reference: arguments, defaults, fields, refusals. |

Images: a client function may return `{"image_path": <project-relative png>, ...}`; the server reads it (jailed to the project
root, ≤ `max_bytes`, default 750 000 so the base64 stays under the 1 MB MCP message size Blender Lab also targets), appends
`{"type": "image", "mimeType": "image/png", "data": ...}` after the text block, and deletes the temp file.

Call templates in `help[]` use the form `tool key=value key=value` (strings with spaces in double quotes). They contain no `:`,
`{` or `[`, so TOON leaves them unquoted.

**Tests.** Server: `test_mcp_envelope.py` — text decodes to `structuredContent`; `outputSchema` validates it (jsonschema);
unknown argument → `isError` + `code: unknown_argument`; empty result → `key: []` + `count: 0`; truncation hint present;
image block appended and temp file removed; path outside root refused.

## C2. The launcher's guide names only tools that exist (bug fix)

**Source.** `src/scripts/mixar/modules/mcp_bridge/core/stdio_server.py` lines 19–37 and 213 tell AI apps to call
`mixar_guide`, `scene_overview`, `scene_hierarchy`, `get_object_details`, `execute_bpy_script`, `render_viewport`,
`inspect_geometry` and `search_asset_library`. None is in the registry or `docs/tools.md`; the alias table
(`mcp_bridge/core/aliases.py`) maps only the ten `mixar_*` local tools. `[UNVERIFIED on the live tools/list; the audit checks]`

**Contract.** The guide text is generated, not written: the stdio server takes its instructions from the server's
`initialize` result (`agent_files.generate.mcp_instructions()`, already the source for the HTTP endpoint) and falls back to a
generated static copy when the app is closed. The guide's first step becomes `lampway_inspect` (AXI 7).

**Test (falsifier).** Every identifier in the guide that looks like a tool name (`[a-z]+(_[a-z0-9]+)+`) is in `tools/list`;
fails today on the eight names above.

## T1. `lampway_inspect` — the scene as typed data

**Name / purpose.** Agent name `lampway_inspect`, api name `inspect`. Read the open scene as typed data at four levels, from
the dashboard down to a mesh's holes and UV islands and the relations between objects. Never edits anything.

**Source.** User, 2026-10-06: "the minute details of the objects in a scene? Their poly, their UV, their segments/parts/layers,
the holes in an object, size relation etc. You would instantly see the scene in typed JSON as a human does."

**User story.** An agent opens a scene it has never seen. One call shows what is there and what to look at next; three more
show the one object's topology, UV and how it sits on the table — without a screenshot and without writing a script.

**Inputs** (`additionalProperties: false`; every out-of-range value refuses with `code: bad_argument` and the valid range):

| Arg | Type | Default | Bounds / values | Applies to |
|---|---|---|---|---|
| `view` | string | (none → home) | `scene`, `objects`, `object`, `mesh`, `uv`, `parts`, `layers`, `relations`, `file`, `schema`, `help` | all |
| `name` | string | — | an object name in the session's scene tab; `schema`/`help`: a view name | object, mesh, uv, parts, layers, schema, help |
| `names` | string[] | selection, else all | ≤ 200 | objects, relations |
| `collection` | string | — | a collection name; includes children | objects, relations |
| `match` | string | — | case-insensitive substring on object names | objects |
| `fields` | string[] | view default | the view's field names, or `["*"]` | objects, relations, list sections |
| `limit` | integer | 50 | 1..1000 | any list |
| `offset` | integer | 0 | ≥ 0 | any list |
| `full` | boolean | false | disables string truncation | all |
| `evaluated` | boolean | false | measure the evaluated mesh (modifiers applied) instead of the base mesh | object, mesh, uv, parts, relations |
| `method` | string | `shells` | `shells`, `sharp`, `uv_islands`, `materials` | parts |
| `angle` | number | 40 | 1..179 degrees | parts (`sharp`) |
| `deep` | boolean | false | add BVH checks: self-intersections, thin walls (`mesh`); precise contact (`relations`) | mesh, relations |
| `texture_size` | integer | 2048 | power of two, 256..16384 | uv |
| `tolerance_m` | number | 0.005 | 0..1 | relations |
| `budget_ms` | integer | 2000 | 100..60000 | mesh, uv, parts, relations |

**Outputs (TOON text + `structuredContent`; per-view JSON Schemas at `docs/schemas/inspect/<view>.schema.json`, returned by
`view=schema`).** The tool's own `outputSchema` stays small (an envelope: `view`, `scene`, `count`, `total`, `data`,
`skipped`, `help`) so `tools/list` does not grow by the full per-view schemas (AXI's schema-overhead finding).

Units: lengths in metres after the scene's unit scale; areas m²; angles degrees; world space; Z up. Rounding (a data
decision, before encoding): lengths 1e-4, areas 1e-6, ratios and fractions 1e-4, angles 0.01.

- **home** (no `view`) — L0 dashboard, O(objects):
  ```
  tool: lampway_inspect
  description: Read the open scene as typed data; never edits it
  scene: Scene
  file: chess_set.blend
  unsaved: true
  units: m
  counts:
    objects: 412
    meshes: 380
    lights: 3
    cameras: 1
    materials: 24
    images: 61
  tris_total: 1843210
  selected[2]: Pawn.001,Board
  active: Pawn.001
  warnings[1]{kind,count}:
    missing_files,2
  help[3]:
    - lampway_inspect view=objects
    - lampway_inspect view=object name=<name>
    - lampway_inspect view=file
  ```
- **scene** — L0: `collections` tree (keyed tabular where uniform: `name`, `objects`, `children`, `hidden`), `cameras[N]{name,lens_mm,sensor_mm,clip_start,clip_end}`,
  `lights[N]{name,type,energy_w,color,size_m}`, `world` (`hdri` as a project-relative path or basename, `strength`),
  `frames` (`start`, `end`, `current`, `fps`), `render` (`engine`, `resolution`).
- **objects** — L1 list. Default fields `name,type,tris,parent`; optional `collection, location, rotation_deg, scale, size,
  bounds{min,max}, verts, faces, materials, modifiers, hidden, selected, uv_layers, vertex_groups, armature, canon`.
  ```
  count: 3 of 412 total
  objects[3]{name,type,tris,parent}:
    Board,MESH,2048,null
    Pawn.001,MESH,4310,Board
    Camera,CAMERA,0,null
  help[2]:
    - lampway_inspect view=objects offset=3
    - lampway_inspect view=object name=<name>
  ```
- **object** — L1 detail of one object: every `objects` field, plus `modifiers[N]{name,type,show_viewport}`,
  `constraints[N]{name,type,target}`, `materials[N]{slot,name,link}`, `collections[N]`, `children[N]`, `layers` summary
  (`count`, `top`), and `canon` (the stamp's kind and scale, or `raw`).
- **mesh** — L2 topology of one mesh (cached, see Engine):
  `counts{verts,edges,faces,tris,quads,ngons,loose_verts,loose_edges}`, `manifold` (`non_manifold_edges`, `boundary_edges`),
  `shells[N]{id,faces,area_m2,closed}`, `holes[N]{id,edges,rim_length_m,centroid{x,y,z},normal{x,y,z}}` (open boundary loops;
  "hole" is the user's word, `open_loop` the algorithm's), `defects{degenerate,isolated_tri,flipped_shells}`; with `deep=true`
  also `intersections`, `thin_regions`. Each list defaults to its 3–4 fields; `holes` sorted by `rim_length_m` descending.
  ```
  object: Bunny
  counts:
    verts: 34834
    faces: 69451
    tris: 69451
    quads: 0
    ngons: 0
  shells[1]{id,faces,closed}:
    0,69451,false
  count: 5
  holes[5]{id,edges,rim_length_m}:
    0,56,0.0821
    1,23,0.0194
    2,9,0.0061
    3,6,0.0042
    4,4,0.0018
  help[2]:
    - lampway_inspect view=mesh name=Bunny deep=true
    - lampway_mesh_defect_scan object=Bunny
  ```
  (numbers illustrative `[UNVERIFIED]`; the audit measures the real bunny.)
- **uv** — L2 UV of one mesh: `layers[N]{name,active}`, then for the active layer `islands_total`, `utilization`,
  `overlap_fraction`, `flipped_faces`, `seam_length_m`, `density{mean_px_m,cv}`, `tiles[N]`, `crossing_tiles`, and
  `islands[N]{id,faces,uv_area,density_px_m}` (default 50, largest first). A mesh without UVs answers `layers: []` and a
  `help` line naming `lampway_uv_unwrap`.
- **parts** — L2 regions **without splitting** (`segment_mesh` creates objects and hides the source; this does not):
  `method`, `parts[N]{id,faces,area_m2,material}` plus optional `bounds`, `centroid`. `method=materials` groups by material slot.
- **layers** — the paint layer stack of the object's material (`layered_material` `inspect`): `layers[N]{index,name,type,blend}`
  plus optional `opacity, enabled, channels, mask`. No paint project → `layers: []` and a help line naming
  `lampway_layered_material action=init`.
- **relations** — L3, for `names`/`collection`/selection (≤ 200 objects; pairs limited to the `limit` nearest):
  `pairs[N]{a,b,relation,gap_m}` plus optional `size_ratio, height_ratio, overlap_fraction, aligned_axes`.
  `relation` ∈ `inside`, `overlaps`, `on_top_of`, `under`, `touching`, `near`, `apart`, computed from evaluated world AABBs:
  - `gap_m` = distance between the two AABBs (0 when they intersect).
  - `inside`: A's AABB within B's on all axes. `overlaps`: AABBs intersect, not inside.
  - `on_top_of`: |A.min.z − B.max.z| ≤ `tolerance_m` and the XY footprints overlap by ≥ 25 % of A's footprint `[UNVERIFIED
    threshold]`; `under` is the converse.
  - `touching`: `gap_m` ≤ `tolerance_m` and not on_top_of/under. `near`: `gap_m` ≤ 10 % of the larger AABB diagonal
    `[UNVERIFIED threshold]`. `apart`: otherwise.
  - `size_ratio` = diag(A)/diag(B); `height_ratio` = dz(A)/dz(B).
  - `deep=true` replaces AABB tests by BVH surface distance and inside-by-ray-parity for closed meshes.
- **file** — `path` (basename; project-relative when under the root), `unsaved`, `saved_age_s`, `backups`,
  `datablocks{...counts}`, `missing_files[N]{kind,name,path}` (basenames only), `libraries[N]{name,path,indirect}`,
  `usage_guess[N]{use,score}` (Blender Lab's heuristic, vendored).
- **schema** / **help** — the JSON Schema / the reference for `name`.

`skipped[N]{object,section,reason}` appears when `budget_ms` ran out, each with a help line
`lampway_inspect view=<view> name=<object> budget_ms=<more>`.

**Engine (no algorithm re-derived; `lampway-canon`).**
- L0/L1: plain `bpy` reads; counts via `mesh.polygons`/`loop_triangles` lengths and `foreach_get` for ngon/quad histograms.
- `mesh`: `features/defect_scan.py` `_shells`, `_open_loops`, `_descriptor` (the same code `lampway_mesh_defect_scan` runs),
  restricted to the cheap kinds unless `deep`.
- `uv`: `features/uv_islands.py` `measure_object` and `features/uv_check.py` `_island_rows`/`_overlaps` (measure path only).
- `parts`: `features/segment.py` `_labels` and `_merge_small`; the split step is not called.
- `layers`: `features/layered_material.py` inspect.
- `file`: Blender Lab's `get_blendfile_summary_*_toolcode.py` `main()` bodies, vendored (GPL-3.0-or-later; keep the "Blender
  Authors" SPDX lines, add REUSE entries), paths reduced to basenames/project-relative.
- `relations`: new bpy-free module `inspect/relations.py` (pure numpy on AABB arrays) so the standalone suite tests it.
- Cache: L2 results keyed by `(object name, mesh data name, evaluated, sha1 of the vertex and loop arrays)`, LRU 64 entries,
  in memory only (`SKIP_SAVE`-style); a scene edit changes the hash, so stale reads are impossible.
- Layout (500-line rule): `src/scripts/mixar/modules/lampway_tools/inspect/{__init__,home,objects,mesh,uv,parts,layers,
  relations,filemeta,cache}.py`; the `@tool` entry `inspect()` in a new `api_inspect.py`, imported by `api.py` like `api_wave6`.

**Server half.** `server/lampway_server/agent/inspect_tools.py` with one `Def("lampway_inspect", ..., api="inspect")`, appended
to `DEFS` like `_WAVE6_DEFS`; offered over MCP automatically (it is a `DEFS` tool). TOON rendering and `structuredContent` per C1.

**Model slot.** None. **Spend gate.** Not applicable (no paid call). **Egress.** None.

**Preconditions and refusals** (each with its next step):
- App closed or signed out → the launcher's existing "open Lampway / sign in" refusal.
- `name` not found → `code: not_found`, help `lampway_inspect view=objects match=<part of name>`.
- Wrong object type (e.g. `view=mesh` on a camera) → `code: wrong_type`, help `lampway_inspect view=object name=<name>`.
- Render running → read-only views still answer (the executor exempts read-only tools, CLAUDE.md "Render coordination");
  `evaluated=true` refuses with `code: render_in_progress` because evaluating can touch the depsgraph `[UNVERIFIED]`.
- Unknown argument or field → `code: unknown_argument` / `unknown_field`, help `lampway_inspect view=help name=<view>`.

**Canon door.** Inspection must read **raw** imports (the point is to see them before normalising), so `Need(...)` is wrong
(it refuses raw assets with "normalize first", as `uv_check` does), `NONE` is wrong (it reads assets) and `LEGACY` is barred
(the ratchet may only fall). **Decided (Q1, 2026-10-06):** a new declaration `OBSERVE("why")` in `canon_door.py`. It reads any
datablock read-only, reports its canon state, and never refuses a raw asset.

**Side effects.** None: no files, no scene changes, no undo step. The cache is memory only.

**Tests (RED first; falsifier in brackets).**
- Server: Def present with schema, `additionalProperties: false`; script is one `api.call("inspect", ...)`; unknown arg refused
  before Blender is asked. [inspect absent from `tools/list` today]
- Pure: `relations.classify` on hand-built AABBs — cube on table → `on_top_of`; cup inside box → `inside`; two cubes 1 m apart
  → `apart` with `gap_m: 1`. [module absent]
- Pure: TOON/structured equivalence for every view's fixture output (C1).
- Blender (`tests/lampway_tools/blender_run.py`, real binary): a cube with one face deleted reports `holes[1]` with
  `edges: 4`; a cube reports `holes: []` and `count: 0`; two cubes report `shells[2]`; Suzanne's `uv` reports `layers: []`
  until unwrapped; a cube stacked on a plane is `on_top_of`; a raw imported GLB is inspected, not refused (Q1);
  the scene's undo stack length is unchanged after every view. [all fail today: no tool]
- Budget: a 2M-triangle mesh with `budget_ms=100` returns `skipped[1]` and the help line, within 2× the budget.

**Acceptance evidence.** On the audit's assets (DamagedHelmet, Stanford bunny, ABeautifulGame): `home` under 200 ms on the
41 MB chess scene; `mesh`/`uv` for the helmet under 2 s cold, under 50 ms cached; the bunny's holes match
`lampway_mesh_defect_scan`'s `open_loop` candidates one for one; screenshots of the objects beside the TOON replies in the audit.

## T2. `lampway_view` — look at the scene, by name

**Name / purpose.** `lampway_view`, api `view`. Frame an object, capture one editor area, or render a still — and return the
image with the action (AXI's finding: an action that returns no observation forces a second call).

**Inputs** (`additionalProperties: false`):

| Arg | Type | Default | Values | Notes |
|---|---|---|---|---|
| `action` | string | (none → help-style home: editors visible, active camera, last capture) | `focus`, `screenshot`, `render_still`, `help` | |
| `object` / `data` | string | — | an object name / a data-block name (focus the object using it) | focus; one of them |
| `unhide` | boolean | false | | focus: a hidden target refuses unless true |
| `area` | string | `VIEW_3D` | Blender Lab's `AreaUIType` enum (VIEW_3D, IMAGE_EDITOR, ShaderNodeTree, …) or `WINDOW` | screenshot, and focus's returned image |
| `shot` | boolean | true | | focus: return the framed area image |
| `max_bytes` | integer | 750000 | 50 000..900 000 | images are downscaled until they fit |
| `preset` | string | `current` | `current` (scene settings), `thumbnail` (256 px, Eevee, low samples, settings restored) | render_still |
| `out` | string | `renders/still.png` | project-relative; never overwrites (`still-2.png`, …) | render_still |

**Outputs.** TOON text (`action`, `object`, `area`, `image{width,height,bytes}`, `framed_bounds`, `unhidden`, `job`) plus an
image block (C1). `render_still` returns `job: <id>` and help `lampway_job_status id=<id>`; the finished job carries the
project-relative path.

**Engine.** `focus`: `view3d.view_selected` under a `VIEW_3D` override of **the session's bound scene tab** (never
`context.scene`; CLAUDE.md "Parallel scene tabs"); selection is saved and restored, so the user's selection is unchanged.
`screenshot`: `observe.image()` (`win.mixar_ui_capture`, which masks secret fields and refuses with `capture_busy`), cropped to
the area. `render_still`: `common/render_coordinator` reservation and the `scene_render` module's background render, never a
blocking `render.render` on the main thread (Blender Lab's approach would break the `render_in_progress` rule and the
no-render-inside-resize rule).

**Gates.** No spend, no egress. `unhide=true` is a scene edit: one undo step named `Lampway: unhide <object>`, reported in the
reply (`unhidden: true`). `screenshot` needs the UI-control opt-in, like `lampway_ui_observe`. There is one switch for all pixels of the interface (Q2,
2026-10-06; capability `ui.control` in the agent-modes spec E2).

**Refusals.** Hidden target without `unhide` → `code: hidden`, help `lampway_view action=focus object=<name> unhide=true`.
No visible area of that type → `code: no_area`, help `lampway_ui_observe`. Render busy → `code: render_in_progress`, help
`lampway_job_status`. `out` outside the root → `code: path_outside_project`.

**Tests.** Focus changes the 3D view's `view_location` to the object's bounds centre and leaves `selected_objects` unchanged
[fails: no tool]; a hidden object refuses, then `unhide=true` unhides with exactly one undo step; screenshot of `VIEW_3D` is a
PNG ≤ `max_bytes` with masked text fields black; `render_still` twice yields `still.png` and `still-2.png`; a render requested
during another returns `render_in_progress`.

## T3. `lampway_blender_docs` — the Blender manual and API, offline

**Name / purpose.** `lampway_blender_docs`, server-side (`specs()` module, like the vault tools). Look up a `bpy` identifier or
search the API reference or the user manual for the Blender release Lampway is built on (5.2).

**Inputs.** `view` (`get` | `search` | `help`; none → home: versions, index sizes, example calls), `identifier` (get; `X.*`
lists children), `query` (search), `scope` (`api` | `manual`, default `api`), `limit` (1..50, default 10), `context` (0..10
lines), `full`.

**Outputs.** `get`: `identifier`, `kind`, `signature`, `doc` (truncated per AXI 3), `children[N]{name,kind}`. `search`:
`count: n of total`, `results[N]{rank,identifier,title,snippet}`, help `lampway_blender_docs view=get identifier=<id>`.

**Engine.** Vendored Blender Lab `tools_helpers/rst_doc_search.py`, `rst_parse_docs.py` and the lookup in
`get_python_api_docs.py` (GPL-3.0-or-later). Data built from **Lampway's own build**, not Blender Lab's copy: the API RST from
`upstream/doc/python_api/sphinx_doc_gen.py` run by the built binary (`--background --factory-startup`), the manual RST from
`blender/blender-manual` at the matching release tag. Stored in the server's data directory, never under `src/scripts`
(CLAUDE.md installer-size rule).

**Licence.** API RST is generated from GPL code (GPL-2.0-or-later text); the manual is **CC-BY-SA-4.0**, one-way compatible
into GPLv3; both need REUSE annotations. **Decided (Q5, 2026-10-06):** the API RST is generated from the build and ships with the
server. The manual is optional: it is fetched only through an egress route that is off by default.

**Gates.** Read-only; no egress at runtime (a live docs.blender.org fallback would be a new `egress.ROUTES` entry, off by
default — not proposed).

**Tests.** `get bpy.types.Object.location` returns its type and description; `search "bevel modifier"` with `scope=manual`
ranks the Bevel Modifier page first; an unknown identifier returns `count: 0`, `results: []` and help with a `search` template;
the data's Blender version equals the build's (`bpy.app.version_string`).

## 4. Decisions (captain, 2026-10-06: "go with your recs")

1. **Q1 canon door for inspection:** `OBSERVE("why")` in `canon_door.py` (T1).
2. **Q2 screenshots:** one switch for all pixels of the interface, `ui.control` (T2).
3. **Q3 TOON for the in-app agent:** TOON for MCP replies (C1) and for Lampway's own agent.
   - Under the agent-modes spec E1, Lampway's own agent (the Hermes engine) reaches Lampway's tools through the engine MCP
     endpoint, so C1 can reach it with no second code path.
   - **Decided (captain, 2026-10-06):** yes, the agent gets TOON too. Token counts and task success with JSON and with TOON are
     still recorded on the same tasks, as evidence of the change, not as a condition for it.
4. **Q4 TOON version:** pin 4.1 and emit 4.2's stricter encoder output (C0).
5. **Q5 docs data:** the API docs are built from the build and ship with the server. The manual is fetched only through an
   off-by-default egress route (T3).

## 5. Build order

C0 (encoder; everything depends on it) → C1 (envelope) → C2 (guide fix; independent, smallest) → T1 home/scene/objects/object
→ T1 mesh/uv/parts/layers → T1 relations/file → T2 → T3. Each lands with its RED tests, regenerated `docs/tools.md`
(`docs/gen_tools.py`, rail RAIL-018), and a live run on the audit assets.
