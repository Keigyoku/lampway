<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# The normalization door and its enforcement

Two halves. **The normalize tools** are the only writers of a canonical document: one per kind, run at every ingress. **The
door** is the only reader that matters: every consuming tool declares what it needs, and the registry refuses to register a
tool that does not. Contracts: `contracts/` (INDEX.md lists them). Placeholders as in AUDIT.md.

## 1. The ingress funnel: one importer, raw by default

Today the files read call Blender's importers from at least 20 places: `studio_landing.import_file`, `asset_place._import` and
`load_blend`, `catalog_export.py`, `model_io.import_file`, `animation._import`, `mesh_to_npz.py`, `clay_view.py`,
`texlib/uv_score.py`, `render_owner.py`, `delete_caps.py`, `patch_holes.py`, `uv_patches.py`, `mesh_qa.py`, `pose_clearance.py`,
`live_load.load_rebuild`, `export_checks._import_table` and `engine_check`, `fit_export._readback`, `batch_export._import`,
`model_compare._import_merged`, `SRV/library/render_worker.import_input`. After this change exactly one module calls them:

```
LT/canon_io.py
  import_raw(path) -> RawImport          # the ONLY caller of bpy.ops.import_scene.* / bpy.ops.wm.*_import / bpy.data.libraries.load
                                         # for assets; every new datablock gets lw_raw = {sha256, container, importer, settings}
  load_image(path, role) -> Image        # the ONLY caller of bpy.data.images.load for asset images: colour space from the role
  normalize_<kind>(...) -> Canonical     # the bodies of the lampway_normalize_<kind> tools (contracts)
  facts(datablock) -> dict               # the cheap measurements the door re-checks (matrix, scene unit, bounds, geometry hash, ...)
  read_npz(path) / write_npz(path, V, T, canon)   # npz with its canonical header
```

A read-back inside an egress check (`fit_export._readback`, `skeleton_export_check._import_table`) is an import too: it calls
`canon_io.import_raw` and compares raw against raw, which is what a read-back is.

## 2. The door: `api.tool` declares what it consumes

The registry is already single (`LT/api.py:51-67` `_REGISTRY`, :1553-1575 `TOOL_FUNCS`; the orphan and Wave 6 lanes register
through it). The decorator changes from `@tool` to:

```python
@tool(consumes={"object": Need(kind=("mesh", "part"), scale=("real",), welded=True),
                "armature": Need(kind=("skeleton",), convention="blender")},
      produces={"<return>.object": Inherit("object", remeasure=("topology", "uv_sets"))})
def weight_transfer(object, source, ...): ...
```

| element | rule |
|---|---|
| `consumes` | **required keyword.** A bare `@tool`, or `@tool()` without it, raises `TypeError` at import, so `api` does not import and every test fails (closed by construction). A tool that reads no asset says `consumes=NONE("why")` (`settings_get`, `job_status`, `chat_transcript`, ...): the reason is mandatory text. |
| `Need` | names accepted kinds and, per kind, the scale states, the bone convention, whether a weld is required, the texture roles. Scale-free tools say `scale=("real", "generator_normalised", "unknown")` and become legitimately callable on generator-scale seeds |
| resolution | an argument that names a datablock resolves to it; a path resolves to its `<file>.canon.json` (files) or the npz `canon` header |
| the check | `canon_asset.validate(doc)` + `canon_asset.check(doc, canon_io.facts(db))` + `canon_asset.satisfies(doc, need)`. The facts re-measured every call are cheap: object matrix identity (1e-6), scene `unit_settings.scale_length == 1`, bounds equal to `bbox_*_m`, `geometry_sha256` recomputed (foreach_get + sha256), vertex-group names in the skeleton, image colour space equal to the document's |
| refusal | `{"ok": false, "error": "normalize first: <arg> <name> is not canonical: <unmet>", "help": ["lampway_normalize_<kind> <arg>=<name> ...", "<the scale route when scale is the unmet need: lampway_fit_place / lampway_scale_to_measure>"]}`. A raw object (`lw_raw`), an unstamped one and a stamped one whose hash no longer matches are three different messages |
| `produces` | the wrapper stamps every datablock the tool returns: `Inherit(src, remeasure=...)` copies the source document, re-measures the named facts, recomputes hashes and sets `normalized_by` to the producing tool's door record; `Fresh(kind, ...)` for a tool that builds new geometry in the canonical frame (`image_to_3d`); `Raw()` for a tool whose output cannot be characterized (it must then be normalized before use). A tool cannot return a datablock the wrapper did not stamp: the wrapper walks the result for object, armature, action, image and material names |
| `TOOL_DOORS` | `{name: (consumes, produces)}`, derived from the same decorator as `TOOL_FUNCS`, exported for tests and for the agent's tool descriptions (each Def's description gains "needs: canonical mesh, real scale") |

### 2.1 The other registries

| registry | door |
|---|---|
| `runner.TOOLS` (ported batch scripts, `LT/runner.py:48-76`) | `Tool` gains a required field `consumes` (dataclass, no default: a missing one is a `TypeError` at import). `run_tool` checks every path argument's sidecar before the subprocess starts; inside the script, files are read with `canon_io.read_npz` / `import_canonical` |
| server tool families (`SRV/agent/*_tools.py`) and the Vault | server tools that read geometry (`library/embed`, `similar`, `render`, `crosspass`) take a canonical version by default and a raw one only by an explicit `raw: true`; `AssetLibrary.put` of kinds mesh, rig, animation, map, texture_set, material requires either a validated `canonical` document or `subtype: raw` (contract `canon_migration.md`) |
| the agent's raw script path (`execute_script`, `run_blender_python`) | not closable without breaking the escape hatch the captain uses. Its output is unstamped, so every door refuses it until normalized; a forged `lw_canon` must also forge `geometry_sha256`, which the door recomputes. The canon plan's pre-tool reminder (canon IMPLEMENTATION_PLAN §3.3) adds `import_scene`, `transform_apply` and `images.load` to its list. Decision D9 offers signed stamps if the captain wants more |

## 3. The normalize tools

One tool per kind, `lampway_normalize_<kind>`, each registered through the same decorator with
`consumes={"input": Need(kind=..., accept_raw=True)}`. Each produces the canonical form, a receipt, and refuses what it cannot
decide.

### 3.1 The steps (mesh shown; the others in their contracts)

| step | what | decided by | recorded as |
|---|---|---|---|
| 1 import | `canon_io.import_raw`; importer settings pinned per container (glTF: `guess_original_bind_pose=False`; FBX: axis and unit options explicit) | the container | `steps[import]` with the importer's settings and the raw sha256 |
| 2 frame | axis map to `lampway.body/1`. `source_convention` for sources that obey their spec (a glTF exported by Lampway); `declared` from the recipe's per-piece `turn_deg` or the caller; `measured` by **plate silhouette registration**: the piece is rendered orthographically at yaw 0/90/180/270 and each silhouette compared (bbox-fitted IoU) with the approved Front plate; the best yaw wins when it beats the second by the margin (decision D6), else refuse. For a rig: skeleton features (head up, foot -> ball forward; memory measure-frame-axes-from-features) | `conventions{source_frame, axis_map, axis_map_det, turn_deg, frame_decision}` |
| 3 transform | apply the object matrix into the data (reverse winding when det < 0, `batch_export.py:102-113` shows how); a skinned mesh keeps its rig transform with reason `skinned_rig_preserved` | the datablock | `transform`, `steps[apply_transform]` with the matrix |
| 4 units and scale | unit factor from scene `unit_settings.scale_length` and importer metadata; scale state: `real` only with evidence (a vendor's real-scale flag measured once, a captain length, a reference height ratio within 5 % of a known factor, canon 18 B.1), `generator_normalised` when the generator is known to normalize (Tripo Studio, ~0.98 m), else `unknown` | the source table + evidence | `scale`, `steps[unit]` |
| 5 weld | generated meshes: weld by position at `weld_distance_m` (default 1e-5 m, decision D5) after recording `split_by_uv_seam_in_raw`; UVs stay per loop, so islands are unchanged; authored rigs and meshes with shape keys: never (canon 01 D.2) | the generator class | `topology.weld`, `steps[weld]` with the count |
| 6 source face ids | write the face attribute `lw_source_face` (raw face index) before anything renumbers faces | always | `part_map.source_face_attribute` |
| 7 measure | topology flags, UV sets, bounds, material slots | measurement | `body` |
| 8 pivot | `bbox_bottom_centre` for an unplaced asset (the rule upstream Mixar already uses, `model_io._set_origin_bottom_and_center`) | kind | `pivot` |
| 9 stamp and store | `lw_canon` on the datablock; the canonical file + `.canon.json` into the Vault as a new version, relation `normalized_from` to the raw version | always | `canonical_sha256`, `receipt_sha256` |

### 3.2 The receipt: `lampway.normalize-receipt/1`

```json
{"schema": "lampway.normalize-receipt/1", "tool": "lampway_normalize_mesh", "tool_version": "1.0.0", "blender_version": "5.2.1",
 "input": {"sha256": "...", "container": "glb", "path_hint": "studio/<job>/variant1.glb"},
 "output": {"canonical_sha256": "...", "file_sha256": "...", "asset_id": "...", "version": 2},
 "steps": [
   {"op": "import", "importer": "import_scene.gltf", "settings": {"guess_original_bind_pose": false}},
   {"op": "axis_map", "matrix": [[0, 1, 0], [-1, 0, 0], [0, 0, 1]], "turn_deg": -90, "decision": "measured",
    "evidence": {"method": "plate_silhouette_registration", "value": 0.94, "second_best": 0.71, "margin": 0.23, "reference": "<plate sha256>"}},
   {"op": "apply_transform", "matrix": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]], "winding_reversed": false},
   {"op": "unit", "scene_scale_length": 1.0, "factor": 1.0},
   {"op": "scale", "state": "generator_normalised", "longest_side_m": 0.98},
   {"op": "weld", "rule": "position", "distance_m": 1e-05, "vertices_merged": 3100},
   {"op": "source_face_ids", "faces": 25000}],
 "conventions": {"frame": "lampway.body/1", "units": "m", "turn_deg": -90, "bone_direction": "head->child head", "bone_axis_export": "Z/X",
                 "weld_m": 1e-05, "source_frame": "gltf_tripo"},
 "refused": []}
```

The `conventions` block is canon 01 F's shape, extended, so every canon tool's receipt and every normalize receipt share it.
`input.sha256` + `output.canonical_sha256` + the step list make the normalization reproducible: re-running it on the same raw
bytes with the same decisions yields the same canonical bytes (a golden test, contract `normalize_mesh.md` §10).

### 3.3 Refusals (each names the next step)

| kind | refused when | message names |
|---|---|---|
| any | the frame cannot be decided: no recipe turn, no caller turn, no plate, or the registration margin is below the threshold | "frame undecided: pass turn_deg (the piece's facing) or plate=<approved Front plate>" |
| mesh | `want_scale=real` with no evidence | "scale unknown: real scale comes from fit_place (armour) or scale_to_measure (a measured length); normalize with want_scale=any to keep generator scale" |
| mesh | a weld would merge more than 5 % of the vertices (`scene_cleanup.py:192-193` uses the same guard) | "the weld distance is wrong for this mesh: pass weld_distance_m" |
| rigged_mesh, skeleton | a `mixed` bone convention (canon 17 INV-17.1); a non-uniform scale on an animated armature (canon 18 INV-18.2); a unit ratio not within 5 % of a known factor (canon 18 B.1); an incomplete roster against the requested reference (canon 01 C.6) | the bones, the ratio, the missing names |
| animation_clip | a sample schedule that is neither rational nor the source's keys; a bone set that differs from the skeleton's (canon 22 B.6) | the bones |
| texture | a role that cannot be read from the source and was not declared; a normal map whose convention is neither in the source's naming nor declared nor baked by Lampway | "declare role=<...>" / "declare normal_convention=gl|dx" |
| material | a channel bound to a texture whose role contradicts it | the channel and the role |
| part, set | members not in one frame; a pair whose `scale_group` is undecided (decision D4) | the members |

## 4. The Vault keeps both

| what | how |
|---|---|
| the raw file | the asset version the ingest made today, `subtype: raw`, unchanged |
| the canonical file | a new version of the SAME asset (`content_key` differs), files `main` (the canonical file) and `canon` (the `.canon.json`), relation `normalized_from` (new relation type, migration 0004) from the canonical version to the raw version |
| the canonical facts | table `canonical(version_id PK, schema_version, kind, frame, scale_state, scale_decision, canonical_sha256, raw_sha256, receipt_sha256, doc_json)`; `mesh_stats.dim_*` and `bbox_*` are written FROM the canonical document, never from the raw glTF |
| `asset_place` | places the canonical version by default (`raw: true` to place the raw one, which is stamped `lw_raw` and refused by every door) |

## 5. The CI check (closed by construction, not by a list)

`tests/lampway_tools/test_canon_doors.py` (standalone, no bpy) and its Blender twin:

1. **Every tool declares.** An AST scan of `LT/` finds every function decorated with `tool`; each decorator must be a call with
   a `consumes=` keyword. Redundant with the import-time `TypeError` on purpose: the scan also covers modules that are imported
   lazily (feature modules imported inside a tool body).
2. **One importer.** The same scan finds every call whose dotted name starts with `bpy.ops.import_scene.`, matches
   `bpy.ops.wm.*_import`, or is `bpy.data.libraries.load` / `bpy.data.images.load`, across `LT/` and `LT/scripts/`; every one
   must sit inside `LT/canon_io.py`. Nothing is listed by hand: the allowed location is one module path, and any new importer
   call anywhere else fails the test with its file:line.
3. **Every runner tool declares.** `runner.TOOLS` values have a non-empty `consumes` (the dataclass already refuses a missing
   one; the test asserts no `consumes=()` without `NONE("why")`).
4. **The red-team pass (Blender twin).** For every name in `TOOL_DOORS` whose `consumes` names a kind, the test builds a raw
   cube (or a raw armature, a raw image) with `lw_raw`, calls the tool through `api.call`, and expects the "normalize first"
   refusal. The list of tools is `TOOL_DOORS` itself, generated by the decorator, never typed.
5. **The schema self-test** (`selftest_schema.py`) runs in the same job.
6. **Migration ratchet.** During migration a tool may declare `consumes=LEGACY("issue")`, which the door logs and lets through.
   The scan counts `LEGACY(` occurrences and compares with the committed integer in `LT/canon_legacy_count.txt`; CI fails if the
   count rises, and the file may only be edited downward. At zero the `LEGACY` symbol is deleted, and its reappearance fails
   step 1.

Why this is not "enumeration as a gate" (memory enumeration-is-not-a-gate): no test holds a list of tools or files. Steps 1-4
derive their subject from the code (the decorator, the AST, the registry); the only hand-kept number is a ratchet that can only
fall.
