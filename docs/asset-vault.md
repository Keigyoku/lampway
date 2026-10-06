<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Asset Vault

The Asset Vault is Lampway's local library for everything you make and collect: meshes, images, materials, maps, UV layouts, rigs, animations, videos, prompts, receipts and boards. It is one deep module behind a small interface: a SQLite database (WAL mode, FTS5 text search) plus a content-addressed blob store. It runs on your machine, uploads nothing by default, and never moves, copies or modifies your own files.

**Honest status.** The library modules are built and tested. They are **not wired into the server yet**: `create_app` does not construct an `AssetLibrary`, does not pass the provenance hook to the job queue, and registers no route or agent tool for it. Generations therefore do **not** land in the Vault today. Two lanes are working on the rest (see section 7). Until they land, treat this page as the description of the library that the wiring will expose.

## 1. What exists today

All code is in `server/lampway_server/library/`, with tests in `server/tests/test_library_*.py`.

| Piece | Module | What it does |
|---|---|---|
| Schema | `schema.py`, `migrations/0001-0003` | 13 closed asset kinds (mesh, image, material, texture_set, map, uv_layout, rig, animation, video, hdri, prompt, receipt, collection), 11 closed relation types (`derived_from`, `variant_of`, `part_of`, `textured_by`, `fits_body`, `rigged_to`, `generated_from`, `drives`, `uses`, `frame_of`, `supersedes`), facets, typed stats tables per kind. A new kind is a migration, not a string |
| Store | `store.py` | one writer (a second process is refused with the holder's pid), any number of read-only readers; versions per asset, dedupe by content hash, soft deletion, a journaled decision log. Needs 5 GB free |
| Ingest | `ingest.py` | classify by magic bytes, hash, extract tier-1 stats in pure Python (GLB, images, video via ffprobe, receipts), propose terms from a committed rules table, poll watch folders. **Scan, then preview, then import after your click** |
| Importers | `importers.py` | the Tripo `seeds.sqlite` (opened read-only) and the mesh-QA `decisions.jsonl`; rows that cannot be resolved go to an `unresolved` list with the reason, and a value that disagrees with the file is a finding, not silence |
| Query | `query.py` | one typed query shape: filters, FTS5 BM25 text (name weighted highest), facets, reciprocal-rank fusion with similarity lists, an offset cursor tied to the database generation, and a read-only SQL view over `v_*` views |
| Curate | `curate.py` | ratings, verdicts (`usable`, `fix`, `reject`, with the shelf's `chosen`/`runner-up`/`fix` kept), relations, boards, smart collections, saved searches, term confirmation, decisions. Append-only wherever a decision is made |
| Embeddings | `vectors.py`, `spaces.py`, `embed.py` | float32 L2-normalised vectors searched by brute-force numpy; deterministic spaces (`image_hist`, `image_dhash`, `shape_d2`) that run locally for anyone; an uploading space only on your click |
| Similar | `similar.py` | find assets like a selection on shape, look and name axes, weights renormalised over the axes both sides have |
| Local models | `localmodels.py` | a CLIP ViT-B/32 image tower and `bge-small-en-v1.5` text model, run by ONNX Runtime on the CPU |
| Provenance | `provenance.py`, `hooks.py` | one capture call every generating tool can make: outputs copied into managed storage, a generation row per output, the prompt as its own asset, relations to resolvable parents, a spooled payload that is retried when the library was closed. `JobQueue(provenance=...)` takes the hook `library.hooks.job_hook` |

## 2. Design rules (enforced in the code)

- **Referenced, not copied.** Your files are opened `rb`, hashed and recorded by `(sha256, path, mtime, size)`. Only bytes the library is handed (generation outputs, which are the only copy) go into `cas/<aa>/<bb>/<sha256>`. Nothing the library did not create is ever unlinked; deletion is a soft flag.
- **Nothing is enrolled automatically.** A source folder is registered when you import from it or add it as a watch root, never before. `scan` reads and reports and writes only `<library>/scans/<id>.json`; `import_` imports exactly the files that scan listed and refuses anyone but you. The planned **Initial import** action is the click: choose one root, several roots or specific paths, preview, then scan.
- **Authority.** Only you rate as the user or confirm terms; an agent rates as `agent:<id>` and its stars never move yours. The effective rating is your latest stars, else the floored mean of the others' stars, else none. Term authority runs user, then rule, then model.
- **Imports are batches.** Rolling one back soft-deletes its assets (rows only, never files).
- **Signed URLs are credentials.** Every URL-looking string loses its query and fragment before it is stored, and secret-looking keys are not stored.
- **Provenance never fails a generation.** `capture` never raises; a failure is spooled and retried.

## 3. Privacy of embeddings

The default is **deterministic, local descriptors**, with nothing uploaded. Embedding with a hosted model is a separate click and follows the privacy rules in [privacy](privacy.md): content without a public licence is private; a private request goes only to a model on OpenRouter's **live ZDR endpoint list** with `provider: {"zdr": true, "data_collection": "deny"}`, never to a `:free` model, and the eligible list is computed live, never hard-coded. With none eligible the request is refused and nothing is sent. A request that timed out after being sent is `submission_unknown` and is never resent.

The bundled local models run on the CPU, offline, with no egress once the files are on disk. **The weights do not ship in this repository.** `localmodels.fetch` is your click: a plain GET of public files through the `model_download` route (nothing of yours is sent), writing a `PROVENANCE.json` (URL, sha256, byte count, and whether the hash was checked against a pinned value or pinned on first fetch). Until the weights are fetched and `onnxruntime` is importable, the status says exactly `needs_weights` or `needs_runtime` and the Vault uses its deterministic descriptors. The download URLs, the ONNX export choice and the checksums are **unverified**: nothing here was downloaded or run against a real model, only against fakes that pin the preprocessing, tokenising, pooling and normalising. See [`THIRD_PARTY.md`](../THIRD_PARTY.md) for the licences.

## 4. Requirements and known defects in the built library

- The library needs **Python 3.14** today: `store.py` takes its default id generator from `uuid.uuid7`, which the standard library gained in 3.14, although `server/pyproject.toml` says 3.11 or newer and the launcher documents 3.12. An injected id generator works on older versions.
- `numpy` is imported by `vectors.py`, `spaces.py`, `embed.py` and `similar.py` but is not declared in `server/pyproject.toml` or the requirements lock, so a clean install from the lock cannot import them. Install `numpy` alongside the lock until this is fixed.
- The legacy asset search (`assetsearch.py`, BM25 plus a colour histogram, seven endpoints used by the client's asset panel, and the `lampway_asset_search` agent tool) is separate and is what answers searches today.

## 5. The agent and MCP surface (planned)

The name is **Asset Vault**; the agent and MCP tools will be named `lampway_vault_*`. They are part of the vault-ui lane (`asset_mcp`) and are not registered yet.

## 6. Data layout

`<library root>/library.sqlite` (WAL), `cas/`, `decisions.jsonl` (the journal), `writer.lock`, `scans/`. Spaces keep one matrix per embedding model; vectors from different models are never mixed.

## 7. Roadmap

| Work | State |
|---|---|
| Schema, store, ingest, shelf importers, query, curate, vectors and deterministic spaces, embedding service, similar, local-model plumbing, provenance and the job-queue hook | built (library only) |
| Wiring into the server (construct the library, pass the hook, REST and agent surface for ingest, query, curate, embed, similar) | **in progress**: the integrator reports lanes are fixing it |
| Thumbnails, turntables, material balls and UV overlays rendered headless and niced (`asset_render`) | in progress, lane `vault-ops` |
| Video as a first-class kind: true motion fps, duplicate frames, derived artefacts (`asset_video`) | in progress, lane `vault-ops` |
| Embedding-model selection per job and the bundled-model completion (`asset_embed_models`) | in progress, lane `vault-ops` |
| Seeds: the rest of your shelf (`asset_seed_captain`), the procedural armour materials (`asset_seed_procedural`, 12 of 55 exist as `lampway_procedural_library`), selective CC0 import (`asset_seed_cc0`) | in progress, lane `vault-ops` |
| The RED-first corpus and gates: 10k-asset latency, coverage, provenance, dedupe, integrity, privacy (`asset_gates`) | in progress, lane `vault-ops` |
| Place into a scene, slot, node tree or world (`asset_place`); the MCP tool family (`asset_mcp`); the dockable editor and pop-out window (`asset_ui_editor`); turntable, ball, UV overlay, map viewer, lineage graph, compare, video player and boards (`asset_ui_views`); report cards | in progress, lane `vault-ui` |

The status of every Vault contract is tracked in the roadmap ([roadmap](roadmap.md)).
