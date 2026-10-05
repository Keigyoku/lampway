# Lampway hardening pass (lp/harden)

Worktree `<workspace>/wt-harden`, branch `lp/harden` from `lp/tools` (`6aae41bc`). Author Keigyoku, no trailers, one concern per commit, the RED line in each body. 23 commits; head `2dce9fcb` (the push is recorded at the end of this file). `main-fork`, `main`, `lp/tools` untouched. The shelf was read only.

Every claim below names its evidence: a test file and count, a log in `<workspace>/scratch/harden/`, or a file under `reports/harden-shots/`. Where I could not verify something, it says so.

## Review of prior commits

Method: the 59 commits on `lp/*` since `main-fork` (`scratch/harden/commit_table.txt` lists each with its source and test files). For each I read the diff's claim against its tests, ran the suites that cover it (server: 281 passed, 3 skipped; client sets below), and probed the risky ones live or by mutation. "Verdict" is about the commit as landed on `lp/tools`; "Fix" names the commit on `lp/harden` that changed it, or says what was left.

| Commit | Claim | Verdict | Fix / note |
|---|---|---|---|
| e5e26a67 | single-user login, HS256 JWT, /auth/me | does what it says; JWT verified with constant-time HMAC | refresh tokens lived in memory: every server restart signed the client out an hour later (seen live) → `387dc589` persists them (0600) |
| 66f446b6 | PKCE desktop SSO, idempotent refresh | correct; PKCE S256 + one-time codes | the Idempotency-Key replay cache was unbounded → capped (`6090cc89`) |
| 0fc66a91 | house envelope, ETag, stubs, agent settings | correct; BYOK keys stored 0600 | the empty generation catalog was the client's kill switch: every generation tab hidden → `03d3dc75` |
| 200450ba | agent WebSocket system layer | correct; bearer checked before accept | job.sync/job.get answered empty stubs → wired to the job queue (`03d3dc75`) |
| d181de36, 6649a3f9, 764cb567, 4805a3ca | build script, baked URLs, GCC gate, LFS | tests pass (`tests/lampway/test_build_linux.py`) | none |
| 419a88c4 | agent loop, slot stream, execute_script | correct; the turn contract matches the client | no questions / plan mode / checkpoints → `e3590586` |
| 0265343e | entrypoint, README, config, live socket | correct | none |
| 0ccdf4c5, 04dbb999, 29036afb, 8174b986 | identity module, hosts through configuration | correct; `tests/lampway/test_lampway_no_mixar_hosts.py` | the sandbox asset allow-list still admitted every S3 and R2 bucket in the world → `16a79922` |
| 83c71441 | compile out the native login gate | `tests/lampway/test_lampway_cpp_gate.py` pins the CMake option; not rebuilt here | none |
| d597d6cb | telemetry off by default | tests pin the preference default and the endpoint | none |
| 32f96d35, cef1789b | product names, README/NOTICE | correct | none |
| c200d8f1 | placeholder brand art | deterministic generator, tests pin formats | the splash said "Placeholder splash" in the accent colour on every start → `ce9f3b94` (needs a rebuild to show: datafile) |
| a94fcc6f, c7b0190f | Lampway tests must not change later files' outcomes | the claim was false in the other direction: a dozen upstream files stub `requests` and broke `test_lampway_brand.py` in any combined run (also on `lp/tools`) → `2dce9fcb` |
| 0c7f6a21, 48791bba, 7bfdb27a | merges, BUILD-LAMPWAY.md | n/a | none |
| 8a184af6 | local `procedural_materials` replaces the withheld one | registry/persistence fine; generation refused honestly | `_run_script` had no `__import__`, so `import bpy` in any material script failed (found live on the first generated material) → `81b6c879`; generation rebuilt → `8f05bc5b` |
| de9e44a6 | the live bridge as an add-on | works (used for every live step here) | unauthenticated loopback exec: any local process could run Python in the app → `cc037e11` (peer uid from the socket table, size cap) |
| bd42471b | file keyring | tests pass | none |
| 45cb5486 | mock provider runs `py:` | correct | none |
| efd92773, d35615e9 | mesh QA candidates, marks, rulings, live | reproduced live on the real chest (91 candidates; the owner's recorded strokes replayed and read) | none |
| 31cadcba | settings, runner, first batch tools | runner tests pass | `run_tool`'s path jail missed `--flag=path` and `name=path:turn` tokens and bare names resolved against the app's cwd → `c8059378` |
| 76f8f5fa, 56a898fa, 4aa7a3cb | Linux run.sh / desktop entry | `tests/lampway_tools/test_linux_scripts.py` passes | none |
| f6d08d02 | X11 backend for the bubble | minimise/restore by real clicks reproduced; **drag: the operator emits `_NET_WM_MOVERESIZE` (window = the pill, direction 8, button 1) — captured by a listener in the WM's seat**; neither openbox nor xfwm4 under Xvfb/XTEST moves even a plain window on that message, so the WM side cannot be judged here | none; one real-desktop check still owed |
| 454897f0 | no-X11 stubs | parity test passes | none |
| dd3ab48a, 5bfbcb43, e4c65c88 | rebuild loop, API, jobs, panel | the whole loop ran live in the app on the real piece (`rebuild-2`: patch_holes, uv_patches, mesh_to_npz, maps, relief_project, material_masks, loaded beside the old) | `test_api_meshpaint.py` hard-coded `build/Dev/bin/mixar` (red in a Prod-only tree) → fixed in `03d3dc75` |
| 553f1359 | server agent tools | tests pass; live (a) by the previous crew | `ask_user` added; the dunder walk skips it (`1a8691e2`) |
| e95e9f21 | Tripo drivers, fixtures, guard | guard tests pass; **live read-only state call ran against the real tool browser** (credits 9290, no click); dry runs were not run live because the image/mesh dry run reloads the owner's Studio tab | Texture + PBR driver was missing → `b34fd617` |
| 0e469685 | chatgpt_plan + Sign in with ChatGPT | PKCE/JWKS/scope logic tested with a fake OpenAI; consent not clickable here | `/app/chatgpt/start` began a sign-in on a GET (a sandbox script's `urlopen` to loopback could start one) → POST + loopback Origin (`6090cc89`) |
| f351ce08 | local CLI adapters | argv lists with `--` separators; no shell; off by default; terms note | none |
| 14895406, b1dac940 | mesh-paint texturing | the pipeline ran live end to end this time (4 views, picks 0.990-0.994 IoU, plates, projection, load, albedo toggle) | the backend came from the launcher's env only → setting (`117e3cb8`); the app's Python env leaked into the server python → cleaned (`26108763`); projection without its rebuild died on a numpy error minutes later → refused up front (`d9ca8342`) |
| a811ff19, 2eaaa79a, 155fe37e, ad8737a3 | launcher | tests pass; used for the previous live runs | none |
| 36715b31 | websockets a runtime dep | packaging test | pinned lock added (`b557fc3c`) |
| 631e8455, 85d1ce96, 66632561 | OpenRouter provider, budget, redaction, image backend | redaction and ceiling tested, mutants killed by the previous crew; re-verified | redaction covered OpenRouter only → every OpenAI-compatible provider (`4cae26a3`) |
| 04369b79, 2970c770, fa8dfb0c | the swarm | lane isolation was prompt-only; the rename false positive was known | the lane guard (`47964233`): server-side snapshot + check per worker script, restore or fail; **caught live** (`sw2 worker-2`: alpha_cube renamed and moved, put back) |
| 34d4a308 | one-view image stage | correct | none |
| 20afa3a4, 6aae41bc | test hygiene | correct as far as they go | see c7b0190f |

Tests that pass on a revert: none found among the files I ran mutants on (sandbox gate, lane guard, run_tool jail, host guard, matgen check). Tautologies: `test_every_tool_script_passes_the_clients_sandbox_dunder_rules` walks every tool's script, which is real; `test_the_swarm_tools_have_specs_and_are_recognised` only pins names (weak but honest).

## Security

Severity: H = runs code or reads/writes files outside the sandbox or spends money; M = reachable by a local process or a web page; L = hygiene.

| # | Surface | Finding | Severity | Fix |
|---|---|---|---|---|
| 1 | `blender.execute_script` sandbox | `open()` limited writes to the temp dir by a string prefix on the resolved path (a `/tmp/rootx` collision passed) and did not limit reads at all; `bpy.ops.wm.save_as_mainfile(filepath=...)` wrote a .blend anywhere; `numpy.load(allow_pickle=True)` on a file the script wrote ran a pickle; `bpy.ops.script.python_file_run` / `text.run_script` ran Python from a file; `numpy.save/tofile`, `Image.save_render`, `bpy.data.libraries.write` wrote anywhere | H | `0d527168`: `sandbox_paths.py`, one gate (realpath + `os.path.commonpath`), behind `open()`, every `bpy.ops.<mod>.<op>` reached through the proxy, numpy's file functions (by identity; `load` refuses `allow_pickle`; `numpy.lib.format/npyio`, `DataSource`, `memmap` unreachable), and the path-taking datablock methods via an AST pass + the wrapped getattr. Read roots: temp, Lampway home, open blend's dir, Blender's install; write roots: temp, Lampway home, the open blend. `LAMPWAY_SANDBOX_{READ,WRITE}_ROOTS` extend. Tests: 12 pure + 6 in the real binary; mutant (containment removed) 14 failed. **Residual:** `bpy.ops.render.render(write_still=True)` is gated on `scene.render.filepath`, but RNA methods not in the list (e.g. `Sound`/`MovieClip` loads, `image.unpack` to `//`) and `bpy.data.images[...].filepath_raw` assignment followed by `save()` are gated only when `save` is called through the guard; a determined script can still name a path through an RNA property the AST pass does not see. The gate is the right seam; the list of methods is open. |
| 2 | Bridge socket (9876) | Unsandboxed Python with all of bpy on loopback, no token: any local process (another user on the box, a container sharing the netns) could drive the app | M | `cc037e11`: the peer's uid is read from `/proc/net/tcp{,6}` (its own row); only the app's uid is served; unattributable connections refused; 16 MiB request cap. No wire change, so the shelf's clients keep working. Tests: 6. **Residual:** a process of the same uid is trusted by design (the shelf's clients). |
| 3 | Server Host header | Any Host accepted → DNS rebinding could reach the loopback API from a web page | M | `6090cc89`: `HostGuard` 421 for HTTP, close 1008 for WebSocket unless Host is loopback or the bind host. |
| 4 | `/app/chatgpt/start` | GET began an OAuth attempt; a sandbox script's `urlopen` to loopback, or a cross-site navigation, could start one; pending attempts unbounded | M | POST with a loopback Origin; attempts capped at 16 (`6090cc89`). |
| 5 | Sandbox network | Default asset hosts `amazonaws.com`, `cloudflarestorage.com` = every bucket in the world as a GET target: a one-way channel out of the sandbox (query strings) | M | `16a79922`: default loopback only; `MIXAR_ASSET_HOSTS` adds hosts. |
| 6 | `run_tool` path jail | `--out=/etc/x`, `name=../p.npz:12`, and bare file names escaped the jail (resolved against the app's cwd) | H | `c8059378`: every path-like token jailed; the tool runs with the project root as cwd. |
| 7 | Keys | OpenRouter: never printed, redacted (re-verified: `server/tests/test_openrouter.py`); the key file is read for the one variable only; `git log -S` finds no key-shaped literal; **OpenAI-compatible/BYOK providers** formatted the server's error body into the message, which can echo the Authorization value | M | `4cae26a3`: configured key and any bearer value redacted in `OpenAICompatProvider`. BYOK key stored 0600 (`agent_settings.json`) — unchanged. |
| 8 | Session storage | Refresh tokens in memory only (restart = sign-out); replay cache unbounded; JWT secret persisted 0600 (fine) | L | `387dc589` (tokens in `<state>/refresh_tokens.json`, 0600, atomic), `6090cc89` (cap). |
| 9 | CLI adapters | `codex exec`/`claude -p` run as argv lists with `--` before the prompt and `-` for stdin; references are jailed paths; off unless `LAMPWAY_LOCAL_CLI=1`; no shell anywhere | — | none needed. The `TOOL_CALL` text protocol parses only the model's last line. |
| 10 | SSRF | Server-side fetches go to fixed hosts (OpenRouter, OpenAI auth); the image backend takes file bytes, never URLs; the client downloads job results from URLs the server mints under its own host | — | none needed. Note: with `LAMPWAY_HOST=0.0.0.0` the minted file URLs would carry `0.0.0.0`; bind to an address the client can reach. |
| 11 | Tripo drivers | A dry run sets and reads back settings and refuses on mismatch; Generate is clicked only after the dry-run return and only when `LAMPWAY_STUDIO_ARMED=1` is in the **server's** environment (no tool argument can set it); count < 4 refused; price must match | — | the new Texture/PBR driver follows the same shape (`b34fd617`). Live: only the read-only state call was run (credits 9290; no click). |
| 12 | Dependency pins | `pyproject.toml` ranges only | L | `b557fc3c`: `server/requirements-lock.txt` (32 pins from the verified Python 3.12 venv). |
| 13 | Public repo | gitleaks over the whole history: 2 findings, both upstream (`edaeb32f`, `tests/test_error_helpers_sanitize.py` fake API keys in a sanitiser test, Mixar author) — not ours, not real; the `lp/*` history: 0. Personal paths: 10 files at HEAD carried the owner's shelf, venv and Blender paths | L | `e241d4f7`: 0 hits in the tree (scan of every tracked file for `/home/<name>`, `<shelf>`, the box paths, the owner's names). They remain in earlier commits: history is not rewritten on a pushed branch. |
| 14 | Lane isolation (swarm) | Prompt-only; a worker could delete or move another lane's object; a worker's own rename read as a loss | M | `47964233`: the lane guard. |

Not fixed, reported: the residual in #1; the stock `blender-mcp` add-on the owner runs on 9876 in his own Blender has the same unauthenticated-socket shape as #2 (its README says so under "Limitations & Security Considerations") — outside this repo.

## Mixar docs coverage

Source: every page of `https://www.mixar.app` (59 URLs from the sitemap, crawled to `scratch/harden/docs/pages/*.txt`; the docs page is 51 KB). Features as the docs name them; status in Lampway before this pass → what I did. "Present" means the client code exists and our server backs it; "broken" means the client surface exists but our server did not back it; "missing" means neither.

| Docs section → feature | Before | What I did |
|---|---|---|
| Getting started: Zen / Engine, workspace, cat pill, Moodboard drawer | present (client-only) | — |
| Working with the Agent: requests, inspect, History, New chat | present | — |
| Questions and planning (the Agent asks; "Explain first and wait for my approval") | missing (no question event; input ran a new turn) | **`e3590586`: `ask_user` tool, choice/text bubbles with `interrupt_id`, answers resume the model. Live through the real client.** |
| Plan Mode (toggle) | missing (flag ignored) | **`e3590586`: `plan_required` drives a Plan Mode prompt; live: plan → Approve → done.** |
| Progress and follow-up instructions (task cards, Retry failed tasks) | partly (steps shown; interjection accepted) | — (retry cards not rebuilt) |
| Go back with checkpoints (rewind the conversation) | broken (`rewind` answered `ok:false`) | **`e3590586`: mark/rewind with `has_conversation`.** |
| Stop, reconnect, recover | present (cancel, attach) | — |
| Scribble: point at a part, sketch, handwriting, voice | point/sketch present (client, marks in the payload); handwriting server fallback and dictation WS missing | — (dictation `/api/v1/dictation/ws` still 403; macOS on-device handwriting is client-side) |
| Moodboard: references, connect steps, generate images | board present; **Generate images broken** (catalog empty) | **`03d3dc75`: job queue + catalog + `image_gen` on OpenRouter; live: the real client generated `lw_live_helmet` (1408×768) onto the board, $0.067.** |
| AI Render (look dev from a viewport capture), Generate video | missing | — (video needs a backend we do not have; AI Render is `depth_to_image`, not built) |
| 3D generation: Image to 3D, multi-view | missing | — (Tripo Studio drivers exist server-side for the owner's account; the client's job type is not wired to them: a job that spends credits must not be a catalog default) |
| Segments and character parts; Mesh Segment | missing | — (candidates listed under Research) |
| Retopology, AI UV unwrap, Auto Rig | missing | — |
| Scenes and Gaussian Splats | missing | — |
| Follow jobs in Queue | broken (empty stubs) | **`03d3dc75`: job.update/job.sync/job.get real.** |
| Asset Library: connect, search by meaning, reuse | library browse present (client); semantic search/train missing | — |
| Materials and layer painting: PBR channels, layer stack, masks, paint | present (client-only) | — |
| Procedural layers (the withheld `procedural_materials`), AI Generate box, Texture Gen | library present, **generation missing** | **`8f05bc5b` + `81b6c879`: `POST /api/v1/matgen`, the model writes a checked node-group script; live: "worn copper with green patina" → a 10-node group with 7 exposed inputs built under the sandbox guard.** Texture Gen (whole-mesh) not built. |
| Bake mesh information, bake and export materials | present (client-only Blender bakes) | — |
| Cinema Mode | present (client-only) | — |
| Models and settings: hosted models, BYOK, local model | present (OpenRouter/Anthropic/ChatGPT plan/local CLI; BYOK stored) | — |
| Connect AI apps (MCP launcher, Claude Code/Codex/Cursor...) | client connector present; our server's `/api/v1/mcp` eligibility missing | — (the live bridge is the MCP-shaped door Lampway has; secured in `cc037e11`) |
| Shortcuts, troubleshooting | n/a | — |
| Credits / referrals / telemetry | stubbed (local, free) | — |

## Research

Primary sources read in full: the two arXiv abstracts and HTML full texts, the UniMate README, and the READMEs of TRELLIS, TRELLIS.2, Hunyuan3D-2 / 2.1 / Omni / Part, UniRig, HoloPart, PartField, MV-Adapter, TripoSG, Hi3DGen, Step1X-3D, SAM 3D Body, blender-mcp (`scratch/harden/research/`). Web search engines refused automated queries after one page; I went to the projects directly.

| Source | Key idea | What I built from it / why not |
|---|---|---|
| arXiv 2609.39709 BTC3D | Training-free, inference-time *blended tile conditioning*: split the reference into tiles, blend tile embeddings into the global one on a schedule that favours tiles late (low-noise), to stop "detail attenuation" in image-to-3D diffusion; applied to TRELLIS, TRELLIS.2, Hunyuan3D-2.1 | Nothing built: no code released ("will release the implementation details"); it needs an open image-to-3D backbone running locally. Recorded as the first thing to try once a local backbone exists (below). |
| arXiv 2609.34900 Filigree3D | Sparse latent flow matching for image-to-3D at 2048³ (extensible to 4096³): structure-aware sparse scaling, multi-scale image features, visibility-aware voxel regularisation; ~1 min per asset on "contemporary hardware" | Nothing built: no code or weights. Noted as the resolution target for armour detail. |
| UniMate (Friedrich-M/UniMate, SIGGRAPH Asia 2026) | One flow-matching model animates arbitrary skeletons from text, graph attention over joints × time; UniML3D dataset; preview checkpoints released 2026-09-27 | Not buildable today for our rigs: inference takes the target skeleton "from the dataset", and the README's own TODO says the preprocessing pipeline for out-of-distribution rigs (ours: the MetaHuman skeleton) is not yet released. Left as the animation candidate to revisit when that pipeline lands. |
| Mixar docs (all pages) | The feature list above | The rebuilds in the coverage table: job queue + catalog + image generation, questions + Plan Mode, checkpoints, MatGen. |
| ahujasid/blender-mcp | Socket server in Blender executing code; its README's security section admits the unauthenticated loopback | The bridge's peer-uid check is the answer to the same shape in our tree. |
| microsoft/TRELLIS.2 (MIT) | 4B-parameter sparse-latent generator, 512³–1536³, textured output, MIT weights | Candidate local image-to-3D backend; **not installed: the README requires ≥ 24 GB GPU memory (this box: RTX 4070 Ti SUPER, 16 GB)**. |
| Tencent-Hunyuan/Hunyuan3D-2 / 2.1 / Omni | 2.0: 6 GB VRAM shape, 16 GB shape + texture, a Blender add-on; 2.1: 10 GB shape / 21 GB with PBR texture; Omni: 10 GB, multi-modal control (point/bbox/pose/voxel) | The realistic local backend for this box: 2.0 (shape 6 GB) or Omni (10 GB) fit; 2.1 texture does not. Not installed in this pass (hours of CUDA builds; no credits or box time were authorised for a model install), listed under "left" with the sizes. |
| VAST-AI-Research/TripoSG | 1.5B rectified-flow image-to-shape, ≥ 8 GB VRAM, auto-downloaded weights | The lightest local shape backend that fits; same note. |
| VAST-AI-Research/UniRig | Autoregressive skeleton prediction + skinning weights, Blender export | The auto-rig candidate (Mixar's Auto Rig); not installed. |
| nv-tlabs/PartField, Hunyuan3D-Part (P3-SAM + X-Part), HoloPart | Part segmentation of meshes: feature field + clustering; native 3D part detection + decomposition; amodal part completion | Candidates for Mesh Segment / Segments; the shelf already has part transfer and relief split; not installed. (The owner's notes: P3-SAM seam/vertex issues are known; model licences are not a blocker.) |
| huanngzh/MV-Adapter (ICCV 2025) | Multi-view consistent generation and geometry-conditioned texture generation; SD2.1 adapters < 10 GB | The open alternative to the Tripo Texture step for this box; not installed. |
| facebookresearch/sam-3d-body | Full-body human mesh from one image (MHR), hand refinement | The fit/pose reference the owner already named as the commercial candidate; nothing to build in the client yet. |

## New features

All on `lp/harden`, each with tests and, where it reaches a model, a live run:

1. **The file-system gate** for the sandbox (`sandbox_paths.py`) — see Security #1.
2. **The lane guard** for the swarm (`server/lampway_server/agent/lane_guard.py`): every worker script wrapped (AST splice), objects outside the lane fingerprinted before and checked after in the same main-thread slot; moves/renames/re-parents/visibility/collection links put back, deletions and geometry edits fail the worker (lane discarded at collect); renames of its own objects follow the name (the false positive is gone). Live: caught `worker-2` renaming and moving `alpha_cube`; the cube came back to (6, 0, 0).
3. **Job queue + generation catalog + image generation** (`jobqueue.py`, `imagegen.openrouter_image_backend`): the client's Media/Moodboard image generation works against our server; per-job unguessable file URLs; spend on the shared ledger.
4. **Questions (`ask_user`), Plan Mode, conversation checkpoints** in the agent loop.
5. **MatGen rebuilt** (`matgen.py` + the client's `matgen_queue.py`): the model writes a node-group script, the server checks it (parse, imports, dunders, forbidden calls, `bpy.ops`, the named group), the client registers/saves it and the node group builds under the sandbox guard.
6. **Tripo Texture + PBR driver** as five server tools (dry run by default, the guard for `--go`), with its checks tested against the owner's recorded dry run.
7. **`pbr_merge`** as a science batch tool and the agent tool `lampway_pbr_merge` (synthetic end-to-end test under the science python).
8. **`export_piece`** (FBX + Textures/ + README with sha256 and conventions) as `lampway_export_piece`.
9. **Bridge peer-uid authentication**, **Host guard**, **persisted refresh tokens**, **image backend as a setting**, **clean Python environment for the server python**, **OpenAI-compatible redaction**, **the splash label**, **the requirements lock**.

## Tests

RED was observed for every behaviour before its code; the counts are from the runs in the commit bodies.

| Suite | Result | RED → GREEN (this pass) |
|---|---|---|
| `server/tests` (venv-tools, Python 3.14) | **281 passed, 3 skipped** (the 3 are the ChatGPT live test, waiting for a consent token) | job queue 6 → 8; questions/checkpoints 4 → 5; matgen 8; hardening 6 → 7; lane guard 7 → 7 (+ 16 swarm tests adjusted to the wrapper); refresh persistence 1 → 1; providers redaction 1 → 1; studios texture checks 4 → 5 (+ guard); server tools 2 → 2; auth/ws unchanged |
| `tests/lampway_tools` + `tests/lampway` + sandbox/executor set + X11 stub parity + bubble controls (host Python 3.14, real Prod binary, shelf recordings and science python available) | see `scratch/harden/client_final.log` (the run was in progress when this file was written; the result is appended at the end of this file) | sandbox gate 12 + 6; lane guard in-app 7; bridge peer 6; run_tool jail 2; settings backend 1; api image backend 2; env hygiene 1; projection refusal 1; export 1; pbr_merge 2; matgen client 4; procedural materials import 1 |
| Earlier runs of the same client set during the pass | `tests/lampway_tools` full: 262 passed, 4 failed (the 4 were `test_api_meshpaint.py`'s hard-coded Dev binary, fixed) then 9/9; the sandbox/executor set + `tests/lampway`: 295 passed, 7 skipped | |
| Mutation checks | sandbox containment removed → 14 failed; lane guard location restore removed → 2 in-app failed; guard never fails the worker → 1 failed; all restored and re-verified | |

Live runs (the real Prod binary under Xvfb + xfwm4 in `lampway-build`, the host server on 18790, OpenRouter: Sonnet 5.5 main, deepseek-v4.1-flash workers, gemini-3.1-flash-image images; `scratch/harden/x11/`):

| Run | What happened | Cost |
|---|---|---|
| Image generation through the real client (`mixie.imagegen_generate`) | POST job → OpenRouter → file served → client downloaded and packed `lw_live_helmet` 1408×768; queue job SUCCESS (`reports/harden-shots/live_imagegen_helmet_client.png`) | $0.0672 |
| Mesh-paint, four views live, on a copy of the real chest (`uv1_nobowl.fbx`, V3 Chest1 plates, chest1_4k reliefs) | clay ×4 (6 s), image ×4 (46 s), picks by IoU 0.994/0.994/0.994/0.990, plates, projection job (`relief_project`, `material_masks` rc 0), loaded `chest_9c052d49_mp_live_meshpaint_textured` (35,378 polys) with the albedo material; albedo toggle off/on | $0.2737 |
| Rebuild loop live on the real piece (`rebuild-2`) | qa_setup, candidates (75 open loops, 16 floating shells, 91 candidates), tag layers, the owner's recorded Red/Green/Yellow strokes replayed and read (1 Delete, 4 Mislabel, 3 Hole strokes → faces per stroke), rebuild at 2048: patch_holes, uv_patches, mesh_to_npz, maps, relief_project, material_masks all rc 0, `chest_9c052d49_mp_live_textured` loaded, `chest_r7` hidden | $0 |
| Plan Mode + question through the real client | "Add a small bronze UV sphere…" with the toggle on → the plan + `ask_user` (bubble `input_type: choice`, session AWAITING_INPUT) → "Approve" → `LW_PLAN_SPHERE` at (0, 0, 2.5), r 0.1, material `LW_Bronze` | $0.1984 |
| Swarm, two runs | run 1: the worker ignored the deliberate violation (nothing to catch; both objects attributed); run 2 with the move as an explicit script: **guard caught `renamed` + `moved` on `alpha_cube`, put it back, reported under `violations`**; `alpha_cube_moved` does not exist; `gamma_cube`/`delta_cone` attributed | $0.50 (orchestrator) + $0.009 (workers) |
| MatGen through the paint operator | "worn copper with green patina, fine brushed grain" → script checked → registered, saved, `done:` status, "Just Generated" → node group `LW_WornCopperWithGreen_4fda`: Principled BSDF, Noise, Bump, Mapping, Mix, ColorRamp; inputs Copper Color, Patina Color, Scale, Grain Scale, Wear, Roughness, Grain Strength | $0.0384 |
| Tripo Studio, read-only | `tripo_image` home view against the real tool browser: browser up, credits 9290, selected "Quad 27,753 faces"; nothing clicked | $0 |
| **Total this pass** | | **$1.0832** (ledger `scratch/harden/x11/state/openrouter_spend.jsonl`; previous pass $0.8364; cap $15) |

No Tripo credit was spent, no Generate was clicked. Free image quota: 0 images (OpenRouter was used instead). The owner's live Blender and port 9876 were never touched (bridge 19880, server 18790, display :99 in the box).

## Launch command

```
cd <workspace>/wt-harden
LAMPWAY_SERVER_PYTHON=<python with `pip install -r server/requirements-lock.txt && pip install -e server/`> \
scripts/lampway/lampway --env Prod --copy --provider openrouter \
  --openrouter-key-file ~/.hermes/.env --budget 3 --image-backend openrouter \
  /path/to/scene.blend
```

`--image-backend` is also kept as the setting `image_backend` (`lampway_status` shows it), so an app started any other way uses it. The Prod binary in `wt-harden/build/Prod/bin` is the `lp/tools` build with the Python half synced; the C++ is unchanged on this branch except that the splash datafile needs a rebuild to show its new label. Inside the `lampway-build` box use a box venv for `LAMPWAY_SERVER_PYTHON` (a host venv's `python` resolves to the box's interpreter there — that is what the first mesh-paint attempt tripped on).

## What is left

- **Sandbox residual** (Security #1): RNA properties that name a path and are not in the guarded-method list.
- **Pill drag on a real desktop**: the client emits the right EWMH request (proven); the WM side needs one check on KWin/Mutter.
- **Splash**: rebuilt art is in the tree; the binary shows it after a rebuild.
- **ChatGPT plan consent**: the owner's click; the live test skips until then.
- **Tripo dry runs against the real browser**: the image/mesh dry run reloads the Studio tab and uploads references into it; I ran only the read-only state call. The Texture/PBR dry run (`state`, `texture` without `--go`) is safe to run next.
- **Mixar features not rebuilt**: image-to-3D / multi-view / retopology / UV unwrap / auto-rig / segmentation / splats / video / AI Render / Texture Gen / semantic asset search / dictation / handwriting fallback / MCP eligibility. The job queue is the seam they plug into; the local candidates and their VRAM needs are in Research (Hunyuan3D-2 shape 6 GB, Omni 10 GB, TripoSG ≥ 8 GB fit this 16 GB box; TRELLIS.2 and Hunyuan3D-2.1 texture do not).
- **MatGen auto-apply** (`add_to_layer_stack` in the agent tool): the material lands in the library; "Add to Layer" applies it; not auto-applied.
- **Retry failed tasks / review cards**, Auto mode's semantics.
- **History rewrite**: the owner's paths stay in earlier commits of `lp/*` (pushed branches are not rewritten).
- Two commit messages on this branch overstate a count by one (`d9ca8342` says 13 passed, the file has 12 tests, all passing; `e3590586`'s "server suite green" was corrected by `1a8691e2`).

## Closing receipts

- Client suites, final run (`scratch/harden/client_final.log`): **582 passed, 1 skipped in 223.77 s, rc=0** (tests/lampway_tools, tests/lampway, the sandbox/executor files, test_ghost_no_x11_stub_parity, test_agent_bubble_linux_controls, test_byok_api_key; the name filter also pulled in the three test_toast_* files, which passed).
- Server suite, final run: 281 passed, 3 skipped.
- Pushed: `lp/harden` → origin (github.com/Keigyoku/lampway), remote head 2dce9fcb311e = local 2dce9fcb311e. No force push; main/main-fork untouched.
- The test session (boxed app, host server, Xvfb) was stopped; nothing listens on 18790/19880 any more.
