<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canonical asset normalization: INDEX

The captain, 2026-10-06: "None of our tools or relevant specs skipped normalization right? That single thing could through a
wrench in everything if we aren't working with a canonical asset, a typed schema if you will..." The answer is in
[`REPORT.md`](REPORT.md); the evidence in [`AUDIT.md`](AUDIT.md).

| file | what |
|---|---|
| [`REPORT.md`](REPORT.md) | the plain answer, the risks, the decisions owed (the auditor's harness refused this file: the coordinator writes it from the auditor's returned text, as for `../REPORT.md`) |
| [`AUDIT.md`](AUDIT.md) | 107 rows (ingress, tools, specs) classified NORMALIZES / ASSUMES / SKIPS with file:line; the SKIPS ranked by blast radius |
| [`SCHEMA.md`](SCHEMA.md) | the canonical asset `lampway.canonical-asset/1`, per kind, with its invariants |
| [`canonical-asset.schema.json`](canonical-asset.schema.json) | the machine schema (JSON Schema 2020-12) |
| [`canonical-asset.examples.json`](canonical-asset.examples.json), [`selftest_schema.py`](selftest_schema.py) | valid and invalid instances; `python3 selftest_schema.py` (0 mismatches on 2026-10-06) |
| [`DOOR.md`](DOOR.md) | the ingress funnel, the normalize tools, the receipt, the Vault's raw + canonical pair, the door and the CI check |
| [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) | the ordered build, aligned with `../IMPLEMENTATION_PLAN.md` |

## Contracts (`CONTRACT_TEMPLATE.md` shape)

| contract | tool | priority | status | depends on |
|---|---|---|---|---|
| [`contracts/canon_asset.md`](contracts/canon_asset.md) | module `canon_asset` + `lampway_canon_status` | P0 | new | none |
| [`contracts/canon_door.md`](contracts/canon_door.md) | `api.tool(consumes=, produces=)` + CI check | P0 | extends `api.tool`, `runner.Tool` | canon_asset |
| [`contracts/normalize_mesh.md`](contracts/normalize_mesh.md) | `lampway_normalize_mesh` | P0 | new (replaces four landings) | canon_asset, canon_door |
| [`contracts/normalize_rig.md`](contracts/normalize_rig.md) | `lampway_normalize_rigged` | P0 | new (ingress face of canon R1, R3) | canon_geom, canon R1/R3 |
| [`contracts/normalize_texture.md`](contracts/normalize_texture.md) | `lampway_normalize_texture`, `lampway_normalize_material` | P1 | new | normalize_mesh |
| [`contracts/normalize_clip.md`](contracts/normalize_clip.md) | `lampway_normalize_clip` | P1 | new (working-frame face of canon R4) | normalize_rigged |
| [`contracts/normalize_part_set.md`](contracts/normalize_part_set.md) | `lampway_normalize_parts` | P1 | new | normalize_mesh |
| [`contracts/canon_migration.md`](contracts/canon_migration.md) | `lampway_canon_migrate` + Vault migration 0004 | P0 | new | all above |

Written 2026-10-06 against the `wt-wave5` worktree at `10ea778c` and the lanes named in AUDIT.md's snapshot table.
