<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contract: `canon_asset` (the schema module) and `lampway_canon_status`

Status: **new**. Priority P0 (every other contract here imports it). Placeholders as in `../AUDIT.md`.

## 1. Name and one-line purpose
Module `LT/canon_asset.py` (pure, no bpy) with the JSON Schema `LT/canon/canonical-asset.schema.json` beside it; agent tool
`lampway_canon_status` / api.tool `canon_status` (read-only): is this datablock or file canonical, and if not, why.

## 2. Source
- The captain, 2026-10-06: "That single thing could through a wrench in everything if we aren't working with a canonical asset, a typed schema if you will".
- Canon 01 F: "Every canon tool's receipt carries a `conventions` block ... A tool that cannot fill a field refuses with the field's name."
- `../AUDIT.md` ranks 1-2: no ingress records a canonical form; the Vault cannot tell raw from canonical.

## 3. User story
Every door (contract `canon_door.md`) calls `validate`, `check` and `satisfies`; the agent calls `lampway_canon_status` before a
chain to see what is missing; the Vault validates a document before storing it.

## 4. Inputs
Module: `validate(doc) -> [str]`, `check(doc, facts) -> [str]`, `satisfies(doc, need: Need) -> [str]`, `digest(bytes) -> str`,
`load_schema() -> dict` (version-pinned). Tool: `{"target": "<object, armature, image, material or action name> | <project path>"}`.

## 5. Outputs
Tool: `{ok, canonical: bool, kind, scale_state, frame_decision, missing: [str], document?}`. A raw datablock answers
`{canonical: false, raw: {sha256, container}}`; an unstamped one `{canonical: false, missing: ["no lw_canon"]}`.

## 6. Engine (proven code)
`jsonschema` Draft 2020-12 validator when the interpreter has it; else a vendored minimal validator for the subset the schema
uses (type, const, enum, required, properties, additionalProperties, items, minItems, maxItems, pattern, minimum, maximum,
exclusiveMinimum, if/then, allOf, $ref). Blender's bundled python lacks `jsonschema` [UNVERIFIED for 5.2.1: the first test
imports it and records the answer], so the vendored path is the default inside Blender. The (code) invariants of SCHEMA.md §4
are plain numpy. Licence GPL-3.0-or-later.

## 7. Model slot
None.

## 8. Preconditions and refusals
An unknown `schema_version` -> "document version N is newer than this Lampway: update" (never a silent pass). A document whose
`frame` is not `lampway.body/1` -> "not a working-canonical document (interchange documents are adapter output)".

## 9. Side effects and safety
None; pure.

## 10. Tests (RED first)
1. `test_schema_selftest`: the `selftest_schema.py` cases (3 valid, 7 invalid) run through BOTH validators; RED: the module does not exist.
2. `test_vendored_validator_matches_jsonschema`: 200 randomized mutations of the valid examples get the same accept/reject from both validators. Falsifier: drop `if/then` support from the vendored one; the scale-evidence case passes wrongly.
3. `test_code_invariants`: a skeleton with a left-handed bone frame, a non-unit `along`, a child before its parent: each refused by name.
4. `test_satisfies`: a `generator_normalised` mesh satisfies `Need(scale=("real","generator_normalised"))` and not `Need(scale=("real",))`.

## 11. Acceptance evidence
The test file green in the standalone suite and in Blender's python; `lampway_canon_status` on a Studio import shows
`raw` before and `canonical` after `lampway_normalize_mesh`.

## 12. Dependencies and order
None. First.

## 13. Open questions
None for the module. The schema's open choices are REPORT.md D1-D5.
