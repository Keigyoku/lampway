# Lane vault-ops (branch lp/vault-ops, from lp/wave5 at 61dff5c8)

Contracts: `specs/asset_library/` asset_render, asset_video, asset_embed_models, the asset_seed_captain remainder, asset_seed_procedural, asset_seed_cc0,
asset_gates; plus the coordinator's two additions (ship the embedding model with the client; wire provenance). Every module was written test-first unless a
row below says otherwise; mutants were run on the guarding lines (a scripted swap, test run, exact restore) and every one named here was killed unless marked.

## Per contract

| contract | state | commits | what exists |
|---|---|---|---|
| asset_render | done (the Asset Browser `.blend` and turn.mp4/webp strip not built) | a2d5b2b6, bca1c0b0, 90095459, 0880e1bc | software z-buffer thumbnails (one framing recipe, material factor, embedded base-colour texture, COLOR_0; 100k triangles in 0.15 s at 256 px), image and video thumbs, software turntables, contact/map sheets, UV overlay; headless Workbench/EEVEE worker (`nice -n 15 -b --factory-startup`, private user config, `LAMPWAY_BRIDGE_PORT=0`, never Cycles); idle guard (load > 0.6 x cores or a windowed Blender > 25 % CPU defers 30 s / 2 min / 10 min); crash restart once; recipe-hash cache; `handle()` tool surface; `backfill()` thumbnails every asset; one server thread |
| asset_video | done (keypoints/fit are attached, not computed: anim_track does not exist) | 63841aad, 2fc31717 | probe, true motion fps, holds (two-cluster cut), blend detection (no rate claimed), panel divider, audio silence, video_stats + gates, frame strip, split panels, 8 fps proxy, keyframe histograms, attachments with the contract's relations, compare (start/time/DTW) |
| asset_embed_models | done (the live bake-off is the captain's click: not run) | 5cf2fb62 | the bundled local models are every job's default; OpenRouter upgrade opt-in, private = live ZDR list + `{zdr: true, data_collection: deny}`, never `:free`; catalogue cached a day, no price literal; set_default is the captain's; probe capped at 64, an agent's is a dry run; bakeoff harness (recall@5, MRR); `:free` runs sized to `GET /key` remaining; a dimension mismatch is not stored |
| addition 1: embedding models ship with the client | done | 94e32467 | `library/models.json` pins CLIP ViT-B/32 (image + text towers) and bge-small-en-v1.5 to commits and sha256s; `scripts/lampway/fetch_models.py` + a `build_linux.sh` step bundle them into `build/<env>/bin/5.2/datafiles/lampway/models`; the launcher hands the server `LAMPWAY_MODELS_DIR`; CLIP BPE tokenizer; `Embed.search_images` (text to image, local) |
| addition 2: provenance wired | done | b7ec8d44, merge f3483acf | the production JobQueue's provenance hook records into the ONE shared Vault (`app.state.vault`, built before the JobQueue); locked by another process: spooled to `vault.spool`, replayed when a server next opens the library; a torn spool line is kept, never fatal |
| asset_seed_captain (remainder) | done for the folder sets; the Higgsfield-history importer not built | a63bc1fa | a clickable initial import: the card only stats each root; scan and import are the user's clicks; referenced only; one batch (rollback = soft delete); ledger rows become generation rows by output hash; clips analysed; every scanned file re-hashed (`untouched_sources`) |
| asset_seed_procedural | done for 55 materials + Vault seeding; the Asset Browser `.blend` export and catalogue round trip not built | 90095459, this commit | 55 presets from 12 named templates (data in `procedural_presets.py`, emitter in `procedural_emit.py`); stat bakes now EEVEE emission readouts (were Cycles); `procedural_seed.export/seed/render_sheet`; every material's thumbnail is its EEVEE ball |
| asset_seed_cc0 | done against fakes (no live download, by instruction) | 0880e1bc | ambientCG (v2 full_json shape from the saved probe) and Poly Haven; plan = metadata only; fetch = the user's click; size + CRC (ambientCG) and md5 (Poly Haven) checks; resume by Range; skip what exists; licence row CC0-1.0 with flags and deed URL; texture_set + part_of map assets (GL/DX convention); new egress routes `cc0:ambientcg`, `cc0:polyhaven` |
| asset_gates | done; `idle` needs a live batch; `throughput` fails on this box | 14d0e1d5 | deterministic corpus, eleven machine gates, receipt asset + gate_result rows, a mutant per gate, `run_on_copy` (VACUUM INTO) for the user's library; baseline in `docs/reports/asset-gates-baseline.md` |
| fix requested by lane vault-ui (similar's look axis) | done | c806497b | a candidate is scored on the look spaces it has; RED: the new test returned [] |

## Measured (live, real binary or real weights)
- Software thumbnails: cube 51 % fill on #808080, torus with its hole, 99 600 triangles in 0.15 s (256 px), 0.77 s (512 px).
- Workbench turntable and EEVEE ball through the real binary: grey background exact (128), the slab framed and turning; the EEVEE world first rendered
  64-grey (the world's node colour was not set): fixed with a RED test.
- The bridge: with the port-0 override removed the worker listened on the bridge port and the probe saw it (mutant killed); with it, no contact.
- Real embedding weights (onnxruntime 1.30.0, CPU): load 1.0 s for three models, CLIP image 23-27 ms per image, CLIP text 15-17 ms per query; "a red sphere",
  "a blue cube", "a green torus" each rank their own render first (0.349 / 0.357 / 0.366 against <= 0.279 off the diagonal); bge paraphrase 0.742 vs
  unrelated 0.485; the Vault's `search_images` finds each render by its description; no socket opened.
- Video on four real clips (two split-screen shelf clips, two Lampway project clips): all 24 fps containers with 24 fps motion; the split clips' dividers
  found (x 957 w 6 at 1920x1080; x 538 w 2 at 1080x1920) and cropped to one figure per panel (checked by eye); one project clip holds still for 55 frames
  (dup ratio 0.34, confidence 0). The first detector called the landscape clip "single": that real miss drove the divider rule.
- Procedural: every one of the 55 groups builds in 5-10 ms; no pair closer than L1 0.093; hue bands and metal/non-metal floors hold (table in the commit).
  All 55 EEVEE balls rendered not black, not white, finite (median 1.7 s per ball), with four category sheets; then the embroidery looks were judged weak by
  eye (the Greek key trim read as plain gold): its thread mask was inverted, with a RED test that the red ground shows. Its new ball was NOT re-rendered:
  the idle guard deferred it because a windowed Blender was above 25 % CPU at the time.
- The idle guard live: a 55-ball batch at load 19-20 was deferred whole (every job at the 10-minute backoff) until the load check was overridden for the
  evidence run; the live-window check stayed real throughout.
- Gates on 10 200 assets: see `docs/reports/asset-gates-baseline.md` (all correctness gates pass; text+filter p95 7.6 ms; similar p95 21 ms; memory 92 MB;
  throughput 89 puts/s fails the contract's 200).

## Tests against the wave5 baseline (900 passed / 5 skipped server; 753 / 46 client)
- Server, full suite at 0880e1bc (before gates and the merge): **1166 passed, 8 skipped, 0 failed** (18 min). Earlier at 5cf2fb62: 1135 passed, 8 skipped.
- Client (`tests/lampway_tools`, real binary from this lane's own copy) at 90095459: **756 passed, 46 skipped, 0 failed** (the +3 are this lane's).
- After that: the gates, the similar fix, the vault-ui merge and the embroidery fix were run scoped (gates 7, similar 9, wiring + hooks + vault-ui's library
  tests 39, procedural real-binary 9, all green); the final full runs are in the closing section below.
- Live tests that skip without their inputs: `test_library_render_live.py` (needs `LAMPWAY_BIN`), `test_library_localmodels_live.py` (needs
  `LAMPWAY_MODELS_DIR` with the weights and onnxruntime), the procedural live seed (needs `LAMPWAY_BIN`).

## Deviations from the brief or the contracts (each recorded, none hidden)
- Blender worker nice level: the brief's `nice -n 15` (the contract and ARCHITECTURE say 19). ffmpeg in asset_video runs at the contract's 19.
- Never Cycles: the brief's rule wins over the contract's idle-gated Cycles ball fallback; the procedural stat bakes moved from Cycles to EEVEE too.
- Framing: "framed to bbox" is implemented as the bounding box of the PROJECTED surface (a sphere filled a quarter of its frame under the 3D box).
- Turntable frames are role `turntable` with `ord` = frame index (the contract writes `turntable:N`); thumbs are `thumb` and `thumb:512`; balls `ball`.
- Holds: the contract's `K x median` rule read 24 fps on a grainy 12-in-24 clip; replaced by a two-cluster cut with a 4x separation guard (RED observed).
- Blends: detected by the residual of a frame against its neighbours' average, not by an autocorrelation of the step series.
- The CLIP text tower was added (the brief's sanity check, text ranking renders, needs it; the image tower alone cannot do it).
- steel_blued is exempt from the steel chroma < 0.10 band (an undeclared exemption: it is blue by definition).
- The contract's `edge_rub` template is the Mask-driven wear every template has; the 12 named templates are listed in `procedural_presets.TEMPLATES`.
- The gates' performance verdicts are not asserted in the suite (a shared box's load decides them); correctness gates are.
- The corpus generator (`library/corpus.py`) was written before its determinism test, which then passed on first run; the cc0 `testzip` mutant is
  equivalent (`zipfile.read` checks every CRC itself).

## Findings for others
- `asset_store` commits one transaction per `put`: 44-89 puts/s here (contract: 200). `bulk()` batches only the journal fsync.
- numpy is used throughout `library/` but is not in the server's runtime dependencies; this lane added a `local-embeddings` extra (onnxruntime, numpy) only.
- onnxruntime is not in the server venv: the bundled weights report `needs_runtime` until it is installed (the extra names it).
- `/tmp` and the shared disk: lanes' pytest basetemps filled both (a user tmpfs quota hit EDQUOT during this lane); this lane ran everything under its own
  TMPDIR and deletes each run's basetemp after reading it.
- The code-graph tool could not index this worktree for the whole session ("a pre-coordination or unverified CBM generation is active"); the code was read
  file by file, and once with a Python line scan of `app.py` (a search the lane's rules discourage), recorded here rather than hidden.

## Not built (named, with the reason)
- The Higgsfield-history importer (live account read; not in this lane's brief list).
- Asset Browser `.blend` export with catalogues for the procedural library (contract test 11), and applying a material to a seed through layered_material.
- asset_render's `turn.mp4`/`turn.webp` strip and the 2M-triangle decimation path was tested with lowered limits only (no 2M-triangle file was built).
- asset_video: scene-change keyframes (keyframes are every 0.5 s), `loop_score`, the `audio_expected` gate needs the generation's expectation passed in.
- CC0: no live fetch (instruction): the ambientCG in-zip map names stay [UNVERIFIED]; Poly Haven HDRIs/models; `remove_batch`; the User-Agent carries no
  contact address (that is the captain's to give).
- Gates: `idle` from a recorded batch is a function input, not yet fed by the renderer; the kill -9 mid-ingest leg of `integrity`.

## Merge notes for the integrator
- `app.py`: the Vault is built BEFORE the JobQueue (moved up from vault-ui's position); `app.state.library` is `vault.lib` (or None when locked);
  `app.state.renderer` is the render queue; the lifespan joins the render thread before `vault.close()`.
- The JobQueue spool is `vault.spool` (`<state>/library/spool`), the same one vault-ui's capture uses.
- New egress routes `cc0:ambientcg`, `cc0:polyhaven` (privacy ok; off until opted in): the Privacy panel lists them from the table.
- `build_linux.sh` has a `bundle_models` step after the build (and `--models-only`; `LAMPWAY_SKIP_MODELS=1` opts out); the launcher exports
  `LAMPWAY_MODELS_DIR` when the directory exists.
- `procedural_library.LIBRARY_VERSION` is 2 (55 materials): an existing `procedural/library.json` at version 1 is replaced on the next seed.
- lp/vault-ui's `asset_mcp` can wrap `Renderer.handle`, `video.handle`, `embed_models.Registry.handle`, `seed_sets.SeedSets.handle` and `gates.run_on_copy`.
