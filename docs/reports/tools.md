# Lampway tools report (lp/tools)

Worktree `<workspace>/wt-tools`, branch `lp/tools` (from lp/build, merged with lp/server), base `main-fork` (untouched).
Author Keigyoku, no trailers. Only `lp/tools` was pushed.

**Remote head = local head, first scope:** `36715b3146458d48d3e27be42e3299a7431ee626` (the OpenRouter / swarm scope below moves it; its head is stated at the end) (checked with `git rev-parse HEAD` and `git ls-remote origin refs/heads/lp/tools`, identical).

## Status: DONE_WITH_CONCERNS (see Concerns)

## Commits on top of lp/build + lp/server (newest first, tools work only)

| sha | what |
|---|---|
| 36715b31 | server: `websockets` becomes a runtime dependency (found by the clean-venv launcher run) |
| 454897f0 | ghost: inert `Mixar_Window*` stubs so a build WITHOUT X11 links (found by the no-X11 link proof) |
| a811ff19 | launcher `scripts/lampway/lampway` |
| b1dac940, 14895406 | mesh-paint texturing: tools, panel button, agent tool, albedo toggle, image backends |
| f351ce08 | local CLI adapters (codex exec, claude -p, imagegen) |
| 0e469685 | `chatgpt_plan` provider + Sign in with ChatGPT auth |
| e95e9f21 | Tripo Studio drivers, server-side |
| 553f1359 | server agent tools (24 client-side tool defs) |
| e4c65c88, 5bfbcb43, dd3ab48a | panel/operators, shared API + jobs, rebuild loop + live load |
| f6d08d02 | Shiro836 `7db187dc` (X11 Agent Bubble backend), cherry-picked, credited, author reset |
| 4aa7a3cb, 56a898fa, 76f8f5fa | Shiro836 `16d7f0ed` (Linux run.sh / desktop entry), credited, renamed to Lampway names; its tests were written RED first |
| 31cadcba, d35615e9, efd92773 | settings + runner, mesh QA decisions/rulings/live, mesh QA candidates/marks |
| 45cb5486, bd42471b, de9e44a6, 8a184af6 | mock `py:` provider, file keyring, live bridge add-on, paint/procedural_materials |

`27f9c70a` (Mixar brand icons) was NOT taken, as ordered.

## Tests, RED to GREEN

Every behaviour was written test-first and observed RED for the intended reason before the code; the wrong-reason REDs that were my own test bugs were fixed in the tests, not the code (icosphere subdiv-3 is itself a small shell; stroke points on cell boundaries; `scene.annotation` not `annotation_data`; the default startup Cube polluting clay views; relative paths in Blender render; `bpy.ops` raising on ERROR+cancel).

Final runs (host, Python 3.14 venv):

- `server/`: `196 passed, 3 skipped` (the 3 are `test_chatgpt_live.py`, which skips until a consented token exists).
- client: `tests/lampway_tools tests/test_ghost_no_x11_stub_parity.py tests/test_agent_bubble_linux_controls.py tests/lampway` -> `308 passed in 194.70s`. The heavy tests (rebuild, relief projection, mesh-paint) drive the real Prod/Dev binary headless.
- Not run: the rest of `tests/` (pre-existing failures there are not mine; baseline was `tests/lampway` 56 pass), and the server suite under the box's Python 3.12.

RED evidence worth naming:
- Shiro836 `7db187dc`'s own test: 2 failed before the code; the shell tests for `16d7f0ed`: 11 failed before the scripts.
- No-X11 link: the build itself was the RED (34 undefined references), then `tests/test_ghost_no_x11_stub_parity.py` RED (stub file missing), then GREEN.
- `server/tests/test_packaging.py` RED (websockets not in runtime deps), then GREEN.

## Live end to end (item 1 and item 5)

Environment: Prod build with the X11 backend, Xvfb :99 + openbox inside the `lampway-build` box, launched through the one command. Server in a clean Python 3.12 venv built from `server/pyproject.toml` (`pip install -e .`).

Launch used (the box has no host venv; the server python is set explicitly):

```
LAMPWAY_HOME=.../scratch/final/home BROWSER=.../scratch/e2e/fake_browser.sh \
LAMPWAY_SERVER_PYTHON=.../scratch/final/venv-box/bin/python \
scripts/lampway/lampway --env Prod --copy --provider mock --port 18789 --bridge-port 19878 \
  <shelf>/tex_r7/v8/textured_scene.blend
```

(`fake_browser.sh` stands in for a browser by GETting the SSO URL so the PKCE loopback completes without a person.)

Observed:
- Start-up: the launcher started the server, opened a COPY (`home/copies/textured_scene-<stamp>.blend`; `bpy.data.filepath` confirms it), and stopped the server it started when the app exited (`Finished server process`).
- Login (PKCE) and profile: server log `POST /api/v1/auth/desktop/token 200`, `GET /api/v1/auth/me 200`; the title bar shows `owner@lampway.local`.
- Agent WS: `WebSocket /api/agent/ws/<id> [accepted]`.
- Chat turn: `bpy.ops.mixie_chat.send_message(message_override="hello lampway")` through the real client -> AGENT reply `Mock provider. Scene summary from Blender: {"success": true, ...}`.
- `blender.execute_script` round trip that changes the scene: sent `py: ... primitive_uv_sphere_add(location=(0,0,5)) ... api.call('status','{}')`; the sphere `LW_E2E_SPHERE` appeared at (0,0,5) and the AGENT message returned `Ran your script in Blender. Result: {"success": true, "ok": true, "version": "0.1.0", "project_root": ".../home/projects", ...}` (the second half proves the `mixar.modules.lampway_tools.api` door works inside the sandbox). The sphere was removed afterwards.
- The original `textured_scene.blend` is unchanged (sha256 `c4f6700d...3a95`, mtime 2026-10-04 22:17).
- No credential printed or committed; the provider was the scripted mock (no LLM credentials exist on this machine).

Screenshots (`<workspace>/reports/tools-shots/`):
- `launcher_chest_lampway_panel.png`: the textured chest in Material Preview and the "Lampway tools" sidebar tab (Mesh QA expanded; Rebuild, Mesh-paint texturing, Parts and proportion tools collapsed), `owner@lampway.local` in the top bar.
- `x11_minimised_pill.png`, `x11_restored_island.png`: the bubble states from the X11 smoke.

Earlier Dev-build run (before the Prod rebuild) also saw `Handshake successful` and `notifications.sync`; no protocol mismatch broke anything. Noise left unfixed: repeated `WebSocket /api/v1/dictation/ws` 403 (no dictation backend), and the client renames the scene to the first chat message.

**Bug found by the live run and fixed:** a clean install from `pyproject.toml` could not serve the agent socket (uvicorn: "No supported WebSocket library detected", 404 on the upgrade), because `websockets` was only in the `test` extra. Fixed in 36715b31 with a packaging test.

## Tools ported (operator / panel / agent tool)

Panels (tab "Lampway"): `Lampway tools` (main, with `lampway.settings_open`), `Mesh QA`, `Rebuild`, `Mesh-paint texturing`, `Parts and proportion tools`.

| Tool | Operator | Panel | Agent tool |
|---|---|---|---|
| a. Mesh QA setup / tag layers / candidates / draw / read tags | `lampway.qa_setup`, `qa_tag_layers`, `qa_candidates`, `qa_draw`, `qa_read_tags` | Mesh QA | `lampway_qa_setup`, `lampway_qa_tag_layers`, `lampway_qa_candidates`, `lampway_qa_draw`, `lampway_qa_read_tags`, `lampway_qa_rulings` |
| b. Rebuild loop (setup, read tags and rebuild, background job) | `lampway.rebuild_setup`, `lampway.rebuild` | Rebuild | `lampway_rebuild_setup`, `lampway_rebuild`, `lampway_job_status`, `lampway_delete_caps`, `lampway_render_owner`, `lampway_split_relief` |
| c. Parts tools | `lampway.run_tool` (named tool) | Parts and proportion tools | `lampway_transfer_parts`, `lampway_apply_part_fixes`, `lampway_mesh_to_npz`, `lampway_run_tool` |
| d. Proportion tools | `lampway.run_tool` | Parts and proportion tools | `lampway_proportion_ratios`, `lampway_place_piece`, `lampway_pose_clearance`, `lampway_mesh_compare`, `lampway_pauldron_symmetry` |
| e. Tripo studio drivers (server side only) | none (not client tools) | none | `studio_tripo_state`, `studio_tripo_image`, `studio_tripo_mesh`, `studio_tripo_fetch`, `studio_seed_catalog`, `studio_image_generate` |
| Mesh-paint texturing | `lampway.meshpaint_run`, `lampway.meshpaint_albedo` | Mesh-paint texturing | `lampway_meshpaint` (stages setup, clay, prompt, pick, plates, project, run, albedo, status) |
| Status | | | `lampway_status` |

Notes:
- Ported shelf scripts sit under `src/scripts/mixar/modules/lampway_tools/scripts/{partseg,proportion,texlib,meshqa}` with SPDX headers, the shelf path and sha256, and the AXI prelude through a shim. 20 tools in `runner.py` by kind (blender / numpy / science), niced, `LAMPWAY_BRIDGE_PORT=0` for batch jobs.
- Paths come from settings: environment > `<LAMPWAY_HOME>/settings.json` > default, jailed to the project root (`PathOutsideProject` for `..`, absolute paths outside, symlinks out).
- Agent tools run as `from mixar.modules.lampway_tools import api; __RESULT__ = api.call("<fn>", "<one JSON string literal>")` because the sandbox allows `mixar.*` imports but forbids os/sys/subprocess; real file/subprocess work happens inside `api`.
- Reproduction against the recorded runs: mesh QA candidates 84 of 84 loops, 16 of 19 shells; tag faces within +-1 of his recorded marks; the whole rebuild loop reproduced his recorded chest_p17 (identical holes, owner map, patch_faces 4739) in 62 s at RES 2048.
- Studio drivers: dry-run by default, `LAMPWAY_STUDIO_ARMED=1` from the SERVER environment only; **no generation ran, no credit spent**. Found and fixed a shelf defect while porting `verify.py`: `'purple' in cls` matched unselected buttons, so Quad read as selected (`_selected()`).
- Paint module `paint/procedural_materials`: **a real small implementation, not a stub shim** (`material_registry.py`, `matgen_persistence.py`, `matgen_queue.py`); material scripts run under the sandbox AST guard. `matgen_queue.enqueue_matgen_job` raises `MatgenUnavailable` because the generating service is the withheld part; `.gitignore` no longer hides the path.
- Live bridge: add-on `bootstrap/lampway_bridge.py`, MCP-compatible loopback socket (`{"type":"execute","code":...}` + NUL) plus an inbox/outbox/frames directory door. Port from `LAMPWAY_BRIDGE_PORT`, else `BLENDER_MCP_PORT`, else 9876; 0 = off; headless runs bind only when a port is set explicitly. My runs used 19876/19877/19878; the user's 9876 was never touched.

## Shiro836 fork commits (item A)

- `7db187dc` (X11 Agent Bubble backend) -> `f6d08d02`; `16d7f0ed` (Linux run.sh, desktop entry, Wayland/X11 switch) -> `56a898fa`, then `4aa7a3cb` renames `MIXAR_LINUX_BACKEND` to `LAMPWAY_LINUX_BACKEND`, `lampway.desktop`, `Icon=lampway`. Cherry-picked with `-x`-style credit in the message body, author reset to Keigyoku, no trailers. README conflict resolved. `27f9c70a` not taken.
- Folded into the one launcher: `scripts/lampway/lampway` runs the app THROUGH `scripts/unix/run.sh` (not `exec`, so it can stop its own server); `--install-desktop` / `--uninstall-desktop` install an entry that runs the same command.
- **Build:** a fresh Prod build with the X11 backend completed (6/6 final links).
- **Backend check:** under Xvfb + openbox, `_bpy._ghost_backend()` returns `"X11"` and `BUBBLE_WINDOW_CONTROLS_SUPPORTED` is True.
- **Minimise / restore / pill: proven.** `bpy.ops.mixar.bubble_toggle_minimise()` returns FINISHED and swaps the island (about 703x239) for the resting pill (316x45). A REAL xdotool click on the 93x26 status pill minimises (island unmaps, 316x45 pill becomes the only viewable window); a real click on the resting pill restores the island plus the 93x26 pill. Screenshots in `reports/tools-shots/x11_*.png` show both states rendering with Lampway branding.
- **Drag: NOT proven.** `Mixar_WindowBeginDrag` sends `_NET_WM_MOVERESIZE` and returns FINISHED when driven on the minimised pill (`bpy.ops.mixar.bubble_window_begin_drag()` under a temp_override with button 1 held), but under Xvfb + openbox with XTEST pointer events the window did not move (positions changed by 1 px per attempt only, the WM frame jitter). As a control I sent the same EWMH client message from an independent python-xlib client to a plain test window; openbox did not move that either. So this WM/XTEST combination does not honour `_NET_WM_MOVERESIZE`, and the environment cannot judge Lampway's drag either way. KWin was not available. This needs one real-session check by the user (drag the minimised pill).
- **Build WITHOUT X11: was RED, now fixed and proven.** Reconfigured `build/Prod` with `-DWITH_GHOST_X11=OFF` and rebuilt incrementally: the link FAILED with 34 undefined references (`Mixar_WindowMakeKey`, `Mixar_WindowOrderFront`, `Mixar_FloatingDocks*`, ... from `space_agent_bubble.cc` and `wm_files.cc`), exactly the risk the audit flagged. Fix 454897f0: `GHOST_MixarNoX11.cc` (inert stubs, compiled only in the non-X11 branch of `intern/ghost/CMakeLists.txt`) plus `tests/test_ghost_no_x11_stub_parity.py` pinning the stub's symbol set equal to the X11 backend's. After it: the no-X11 Prod build linked, a headless run printed `BACKEND NONE False` (controls unsupported, no crash), and no `GHOST_SystemX11` symbol is in the binary. `build/Prod` was then restored to `WITH_GHOST_X11=ON` and rebuilt (rc 0). Not done: a Wayland-session run (the audit's recommendation); the no-X11 binary was only run headless.
- Concern recorded for the X11 path: heavy window mutations default ON; `MIXAR_X11_HEAVY=0` is the first bisect step if a compositor misbehaves. Bubble naming/swap semantics were only observed under openbox. The desktop installer writes only under `~/.local/share` plus `kbuildsycoca6`'s own `~/.cache/ksycoca6_*` (the audit's "writes only under ~/.local/share" was incomplete; pinned by a test and documented).

## chatgpt_plan provider and auth (item B1)

- Built from the DOCUMENTED Sign in with ChatGPT protocol only (fetched into `scratch/siwc/`). No Codex tokens were read, no `~/.codex/auth.json`, no DevKit code. The `auth.json` idea is removed from `reports/server.md`.
- `chatgpt_auth.py`: dynamic client registration, PKCE S256, loopback `http://127.0.0.1:<port>/auth/callback`, ID-token JWKS validation, scope check for `chatgpt.tokens.use.direct`, serialized refresh, sign-out revoke. Tokens in `<state>/chatgpt_auth.json` at mode 0600, never logged. Routes `/app/chatgpt`, `/app/chatgpt/start`, `/auth/callback`, `/app/chatgpt/status`, `/app/chatgpt/signout`.
- `providers/chatgpt_plan.py`: POSTs `/v1/responses` with `store:false`, `stream:true`, namespace `lampway` tools, none of the rejected fields; success only after `response.completed`; typed `ChatGPTPlanError` with the documented recoveries. Model default `gpt-6.1-sol` (`chatgpt_model` in config).
- Per the terms: tokens stay local, requests only from the user's local runtime, no general-purpose proxy, express consent for background use. The GPT Image route is NOT available on this auth path (documented), which is why image generation uses the CLI adapter or Tripo instead.
- **Not done: the consent click.** That is the user's. The live test `server/tests/test_chatgpt_live.py` skips (3 skipped) until a consented token exists, and runs once one does. A scripted probe of the real authorize URL got a Cloudflare 403 (it needs a browser), so the consent page itself was not rendered.

## Local CLI adapters (item B2)

`server/lampway_server/agent/cli_adapters.py`. **OFF by default**: enabled only by exactly `LAMPWAY_LOCAL_CLI=1` or a `<state>/local_cli.json` file. Providers `codex_cli` (`codex exec`), `claude_cli` (`claude -p`), and `codex_image()` for `$imagegen`; tool calls ride a `TOOL_CALL {...}` text protocol. The terms caveat is quoted next to the setting (constant `TERMS_NOTE` in the code, `server/README.md`):

> "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, or Max plan credentials on behalf of their users."

and for OpenAI: tokens stay on the user's own machine, requests come only from the user's local runtime, no proxying for others. These adapters run the user's OWN installed CLI as the user; they are a convenience for the user's own machine, not something to ship enabled or to offer to other users.

Verified live once each (tiny prompts): codex text 13.6 s `pong`; codex tool call OK; `claude -p` 8.6 s `pong`.

## Mesh-paint texturing (item B3)

- One panel button (`lampway.meshpaint_run`, "Mesh-paint texture") and one agent tool (`lampway_meshpaint`).
- Pipeline in `meshpaint.py`: clay views in the order Left, Front, Back, Right (consistency view first), prompt from the `prompt_meshpaint_v2*.txt` files, variants ranked by silhouette IoU against the clay (`silhouette_iou`, `rank_variants`, `pick_best`, `record_pick`), plates, then projection through the shelf's `relief_project` re-ported at the shelf's current sha (so it has `RP_COLOR_FULL` and `RP_NO_FLOW`; `RP_NO_FLOW` zeroes the warp after measuring it).
- Image backend configurable: the Tripo studio driver (`studio_tripo_image`, dry-run, "never spend credits") or the Codex CLI adapter (`codex_image`), selected in `imagegen.py` (`tripo | codex_cli`).
- Albedo toggle: `albedo.py` builds `AB:` nodes on a `_albedo` copy; `lampway.meshpaint_albedo` flips it; tested.
- **Live image generation was NOT run and nothing was spent.** The projection and albedo stages are tested on recorded/synthetic plates through the real binary; the generate step is covered by dry-run fixtures (`server/tests/fixtures/*.json`).

## Launch command for the user

From the worktree, with a build present (`MIXAR_ENV=Prod BUILD_CORES=4 nice scripts/lampway/build_linux.sh`, already built here):

```
cd <workspace>/wt-tools
LAMPWAY_SERVER_PYTHON=<python with `pip install -e server/`> \
scripts/lampway/lampway --env Prod --copy --provider mock \
  <shelf>/tex_r7/v8/textured_scene.blend
```

Defaults: server on 127.0.0.1:8787, bridge on 9876 (pass `--bridge-port 0` to turn it off, or another port to stay clear of a live session), isolated profile under `~/.local/share/lampway` (`LAMPWAY_HOME`), file keyring. `--plan` prints what it would do without starting anything; `--no-server` points at a server you already run; `--install-desktop` adds the app-menu entry. `--copy` is what keeps the original untouched; without it the file is opened directly. On a real desktop the browser opens for the SSO page by itself; I used the fake-browser script only because the test display has none. `LAMPWAY_LINUX_BACKEND` (`auto|x11`, also read from `.env`) is run.sh's Wayland/X11 switch; the launcher proof ran with whatever run.sh chose under Xvfb (X11).

## Left, stubbed, and concerns

- Drag of the minimised pill: not verified (see Shiro836 section); needs a real session.
- No Wayland-session run of the Prod binary; the no-X11 build was only run headless.
- ChatGPT consent not performed (the user's click); the live test skips until then. Cloudflare blocks scripted authorize probes.
- (Superseded by the OpenRouter scope below: an OpenRouter key was found and the live runs now use real models. The first pass used the scripted mock; no ANTHROPIC/OPENAI key exists on this machine.)
- Tripo studio drivers are untested against a real browser (their dry-run state/verify logic is tested on recorded fixtures). One OpenRouter image generation WAS run (see Live agent runs, c); no Tripo generation and no Codex image generation.
- (Superseded: a real model, Claude Sonnet 5.5, now drives real `lampway_qa_setup` and `lampway_qa_candidates` calls end to end; see Live agent runs, a.)
- (Superseded: the server suite now also runs under the box's Python 3.12; see Costs and tests below.)
- The shelf `explore` tool hung under heavy IO once (not changed).
- `main-fork` unchanged. Dev vs Prod: early proofs used a Dev copy; the final launcher proof, X11 smoke and the no-X11 link used Prod.
- Xvfb screenshot capture needs the external `import -display :99 -window root`; `bpy.ops.screen.screenshot` is black under Xvfb.
- The splash screen reads "Placeholder splash" (brand placeholder art from an earlier branch); not touched here.
- `git add -A` fails on the host (submodule needs git-lfs); I used explicit paths.
- Scratch artefacts (not committed): `<workspace>/scratch/{e2e,x11,final,siwc,port}`.

---

# Second scope: OpenRouter, the swarm, and live agent runs (lp/tools)

Status for this scope: **DONE_WITH_CONCERNS** (concerns at the end). Commits (oldest first, all on `lp/tools`):
`631e8455` OpenRouter provider; `04369b79` swarm; `66632561` OpenRouter image backend; `2eaaa79a` launcher OpenRouter flags; `34d4a308`
mesh-paint one-view image stage; `155fe37e` launcher tells the app the image-backend python; `85d1ce96` in-stream errors, silent worker, log
record fix; `ad8737a3` swarm model default; `2970c770` per-worker call record + real-Blender merge test; `fa8dfb0c` lost-object detection;
`20afa3a4` and `6aae41bc` test-suite hygiene. Author Keigyoku, no trailers (the attribution reminder in the harness asks for trailers; the
dispatch rule "no agent or co-author trailers" governs, so none were added).

## OpenRouter

**The key.** It was found without printing it: no OpenRouter variable is in the environment; `~/.hermes/.env` (mode 600) holds
`OPENROUTER_API_KEY` (checked by variable NAME and length only). My shell policy refuses `grep`/`find`, so I did NOT run the filesystem-wide
`grep -l` search the brief described; I checked the environment and the known dotenv locations. Other keys on other paths, if any, were not
looked for. The key is never an argument, never in `settings.json`, never printed: the server reads `OPENROUTER_API_KEY` or the file named by
`LAMPWAY_OPENROUTER_KEY_FILE` (a dotenv file or the bare key; only that one variable is read from it). The launcher takes
`--openrouter-key-file <path>` and exports the PATH. After all runs I scanned 9,260 files under the mixar tree (scratch, reports, server,
tests, scripts, tool module) for the key value: 0 files contain it; `git log -S` finds no key-shaped literal in any commit.

**The provider** (`server/lampway_server/agent/providers/openrouter.py`): `OpenRouterProvider` subclasses `OpenAICompatProvider` (four small
seams added there: extra body, extra headers, a pre-request hook, a per-chunk hook, an error formatter), posts to
`https://openrouter.ai/api/v1/chat/completions` with `HTTP-Referer`/`X-Title` and `usage: {include: true}`, streams, and does tool calling
through the shared OpenAI translation. Settings (env): `LAMPWAY_OPENROUTER_MODEL`, `_SWARM_MODEL`, `_IMAGE_MODEL`, `_MAX_TOKENS`,
`_BUDGET_USD`.

**The hard budget.** (1) every request carries `max_tokens` (default 4096); (2) a `SpendLedger` sums the `usage.cost` OpenRouter reports for
every call, by label (`main`, `worker-N`, `image`); (3) past the session ceiling (`--budget`, default $3) the next call is refused BEFORE
anything is sent (`SpendCeilingReached`); (4) the ledger is the spend log file, `<state>/openrouter_spend.jsonl` (`LAMPWAY_SPEND_LOG`), so the
image-backend subprocess the client launches counts toward the same ceiling; the launcher starts a fresh log each launch (the old one is kept
as `.prev`).

**Redaction (tested).** `redact()` replaces the configured key and anything shaped like `sk-or-v1-...`; applied to HTTP error bodies (a 401
that echoes the key), in-stream error chunks, image-backend errors, and by a log filter. Tests (all in `server/tests/test_openrouter.py`, fake
key and fake transport): error echo redacted, `redact` on key and look-alike, log record message and args redacted, reprs carry no key,
key resolution by env or file reference with a value-free error, and the launcher test proving the key value is absent from stdout, stderr,
the server's environment and the app's environment. Mutation check: removing the ceiling check fails the ceiling test; removing the error
redaction fails the redaction test (both mutants killed, then restored).
**Bug found live and fixed:** the first version of the log filter replaced `record.args` with `()` on every record, which broke uvicorn's
access logger (a traceback on every request). It now leaves a record untouched unless it holds the key (test written first, observed RED).

**Models, verified against `GET /api/v1/models` (466 models) on 2026-10-05:**

| role | id | exists | in / out $ per M tokens | tools |
|---|---|---|---|---|
| main agent | `anthropic/claude-sonnet-5.5` (the id has a dot) | yes | 2.00 / 10.00 | yes |
| swarm (asked first) | `stealth/space-bunny-alpha` | yes, free (0 / 0) | 0 / 0 | listed yes |
| swarm (fallback, chosen) | `deepseek/deepseek-v4.1-flash` | yes | 0.30 / 1.20 | yes |
| image | `google/gemini-3.1-flash-image` | yes (`/api/v1/images/models`: text+image in, `input_references`) | measured $0.0684 per image | n/a |

**Why not `stealth/space-bunny-alpha`:** it is still listed and still free, but a swarm sends concurrent requests and it answered "502 Provider
returned an empty response" (an SSE error chunk inside a 200 stream) to 6 of 6 concurrent worker-shaped requests (probe script
`scratch/or/probe.py`), while `deepseek/deepseek-v4.1-flash` served 6 of 6. In the live runs it also served one worker and failed the other
two. Sequential single requests to it worked. So `deepseek/deepseek-v4.1-flash` is the default swarm model; the stealth id stays selectable
with `LAMPWAY_OPENROUTER_SWARM_MODEL`. (Free stealth models may log prompts; not a concern for the chest scene but noted.)

**Image model:** from OpenRouter's Image API docs (`POST /api/v1/images`, `input_references` as data URLs or http(s) URLs, response
`data[].b64_json` plus `usage.cost`) I picked `google/gemini-3.1-flash-image` because it accepts reference images, is the cheapest of the
reference-capable models that returns clean flat colour, and costs cents. Others that qualify: `openai/gpt-image-2`, `openai/gpt-5-image`,
`black-forest-labs/flux.2-pro`, `bytedance-seed/seedream-4.5`, `google/gemini-3-pro-image`. Backend `openrouter` in `imagegen.py`: dry run
unless `live`, at most 4 images (one request each), refused before sending past the ceiling, paths jailed to the project root; the mesh-paint
tool gained a one-view `image` stage (`meshpaint(stage="image", view=..., live=..., count=1..4)`, agent tool `lampway_meshpaint`, same
operator) so one image can be made without the 16-image `run`.

## Swarm

**How the client does it** (read from `space_mixie_chat/ARCHITECTURE.md`, `core/main_thread_executor.py`, `core/session.py`,
`core/lane_scene_sweep.py`, `constants.py`): there is no "spawn agent" RPC. A worker is a session whose `blender.execute_script` carries
`session_id == agent_ctx.chat_session_id == "agentlane:<parent>:<n>"`. The executor routes it to the scene whose `mixie_session_id` is that
string, runs it there, and restores the foreground scene; a lane with no scene is REJECTED ("no scene for session"), never run in the active
scene; `has_active_session` maps a lane to its parent through the lane scene's `mixar_workspace_main_session`. Scripts run one at a time on
the main thread, round-robin across lanes. So the backend (the orchestrator) must create the lane scenes and merge them; the server now plays
that part. (`instance_id` identifies the process, `session_id` the scene conversation, `run_id` background work spanning turns, `agent.attach`
replays one turn's events by seq; they are unchanged and still work for the main turn.)

**What I built** (`server/lampway_server/agent/swarm.py`, wired into `turns.py`/`app.py`; main agent tools, workers never get them):
`swarm_start(tasks:[{name,prompt}])` creates all lane scenes with ONE script on the parent session (data travels as a JSON string literal,
so no name or prompt can change the code), then starts the workers as concurrent agent loops on the swarm model and returns at once;
`swarm_status`; `swarm_cancel(worker)` stops one and leaves the rest; `swarm_collect` waits for the rest, then one merge script links each
finished lane's objects into the parent scene (every object tagged `lw_worker`, `lw_worker_name`), discards a cancelled or failed worker's
lane completely and removes every lane scene. The main bubble shows progress as the swarm step's detail. Owner endpoints (bearer token):
`GET /app/swarm` (status plus each worker's call record) and `POST /app/swarm/<id>/cancel/<worker>`. The main turn's `agent.cancel` or a
closed socket cancels all workers. Cap 6 workers; each worker has at most 24 model rounds.

**Tests** (RED observed first for each): `server/tests/test_swarm.py` (16 tests: lanes created on the parent session first, each worker's
scripts addressed to its own lane, three scripts outstanding at once, per-worker attribution, cancel one, failed worker, double collect,
bad task lists, prompts and tool lists, silent worker failed, lost-object warnings), `test_swarm_ws.py` (the whole turn through the fake
client, owner endpoints, system prompt), and `tests/lampway_tools/test_swarm_merge.py` which runs the generated lane and merge scripts in the
REAL binary. (The two owner-endpoint tests passed on first run: I wrote those endpoints before their tests; the prompt test was observed
RED.)

**What the live runs showed (honest list):**
1. Lanes isolate SCENES, not `bpy.data`. Object names are global, and every worker sees every other lane's objects through `bpy.data`. In
   the deliberate collision run (three workers told to name their cube `shared_cube`) a worker "cleaned up the pre-existing `shared_cube`"
   with `bpy.data.objects.remove`, deleting another lane's cube: two of three cubes were gone at merge, and the executor's name-based diff
   showed nothing. That was real clobbering, so the claim "edits cannot interleave" in my first docstring was too strong; it is now narrowed.
2. Fixes: the merge script returns what each lane really held; `swarm_collect` compares it with what each worker made and returns
   `lost_objects` and `warnings`; the worker prompt says never to delete, rename or modify an object it did not create and never to look an
   object up by a name it did not just give it; the orchestrator prompt says to give each task a disjoint name prefix. With those, the
   same collision run kept all three cubes (each worker prefixed its own name), each attributed to its worker.
3. Known false positive: a worker that creates `shared_cube.001` and then renames it makes the stale name show up as "lost" (the model
   itself judged it harmless). Prevention is by prompt; the server detects and reports, it cannot stop a script that edits another lane's data.

## Live agent runs

Setup for every run: the one-command launcher, Prod build, Xvfb + openbox in the `lampway-build` box, a COPY of the chest scene
(`<home>/copies/textured_scene-<stamp>.blend`; the original's mtime is unchanged), server in the box's Python 3.12 venv, bridge port 19879
(never 9876), `--provider openrouter --openrouter-key-file ~/.hermes/.env --budget 3 --image-backend openrouter`, real client login (PKCE),
messages sent through the real client (`mixie_chat.send_message`).

**(a) Main agent (Claude Sonnet 5.5) driving real `lampway_*` tools.** Message: set up Mesh QA on `chest_r7` with `chest/recipe.json` and
`chest/owner_r7.npy` (a one-part recipe and zero owner map I wrote under the project root: the shelf's recorded owner map is for a different
face count), find candidates, say how many open loops and floating shells, add a UV sphere `LW_LIVE_MARK` at (0,0,6). Result: 4 model calls;
the agent called `lampway_qa_setup`, `lampway_qa_candidates` and a scene edit; its answer "62 open loops and 17 floating shells, 79
candidates" matches the written file (`chest/rulings/chest_candidates.json`: 79 = 62 `open_loop` + 17 `loose_shell`, copied to
`reports/tools-shots/live_a_chest_candidates.json`); `LW_LIVE_MARK` exists at (0,0,6). Cost $0.0958.

**(b) Swarm of 3 on separate tasks (deepseek-v4.1-flash workers, Sonnet 5.5 orchestrator).** Tasks: alpha six cubes at x=10, beta six spheres at
x=20, gamma six cones at x=30, one tool call per object. Timeline (`reports/tools-shots/live_b_swarm_timeline.json`, polled from
`/app/swarm`): all three `running` by 8.4 s; at 11.4 s every worker had made a tool call and I cancelled worker-2 through the owner
endpoint; workers 1 and 3 kept going (tool calls 2..7, objects 2..6) and finished `done` at 20.4 s and 26.5 s; worker-2 stayed `cancelled`
with 1 call and 2 objects. After `swarm_collect` (`verify_before.json`, `verify_after.json`): objects 185 -> 197 (exactly alpha_1..6 and
gamma_1..6; no beta object and the stray `Sphere` it had made were discarded with its lane); every kept object carries `lw_worker`
(`worker-1` for alpha, `worker-3` for gamma) and its own x; no `agentlane:` scene left; the chest's vertex hashes are byte-identical before
and after; the main agent's final answer matched the scene (it also said, correctly, that it had not cancelled beta). The concurrency is real
at the model level (the three workers' calls overlap); in Blender the client takes the scripts in turn, which is what prevents interleaved
edits. The deliberate name-collision runs are described under Swarm. Cost of the run $0.0886 (orchestrator $0.0809, workers $0.0077).

**(c) One OpenRouter image through the mesh-paint backend.** `api.call("meshpaint", {stage: setup/clay/image})` in the running app: clay renders
(Workbench, 1024) of `uv1_nobowl.fbx`, then `stage=image view=Front live=true count=1`, which runs `lampway_server.imagegen --backend openrouter`
under the server python with the clay front render first and V3's Chest1 `Front.png` plate as references: `google/gemini-3.1-flash-image`
returned one 1024x1024 flat-colour albedo in 18.5 s total for the stage. Images: `reports/tools-shots/image/compare_clay_plate_result.png`
(clay | design plate | result) and the three originals. The result keeps the clay's silhouette and puts the plate's red cloth, bronze
metal and gold lion plates on it. Cost $0.06842 for the image (ledger label `image`, same ceiling).

**(d) Outstanding test items.**
- Server suite under the box's Python 3.12.3: `237 passed, 3 skipped` (the 3 are the live ChatGPT test, which waits for a consent token).
  Host Python 3.14: the same 237/3.
- The rest of `tests/` (everything except the 5 `tests/mcp` files, which cannot collect here because `tests/mcp` shadows the `mcp` package:
  identical on the baseline): `104 failed, 7217 passed, 29 skipped, 15 errors` after my changes, against `104 failed, 6962 passed, 29
  skipped, 16 errors` on the baseline worktree `wt-build` (lp/build). The sets of failing and erroring test ids are IDENTICAL, except that
  one baseline collection error (`tests/test_api_client_version_header.py`, which imports `matgen_client`, a module of the withheld paint
  package) is now gone because the replacement provides it. So all 104 failures and 15 errors are pre-existing and not touched. Findings
  along the way that WERE mine and are fixed: `test_keyring_file` failed to collect once other files had stubbed `keyring` (it interrupted the
  whole run), and `test_procedural_materials` left a fake `bpy.data` on the shared bpy mock, which made 7 unrelated tests
  (`test_animate_rig_import` x4, `test_context_folder_transport` x3) fail in a full run (bisected by running each of my files before them).
  The largest pre-existing groups are `tests/onboarding/test_unified_language.py` (52), `space_mixie_chat/tests/test_scene_tab_ops.py` (12),
  `test_scene_identity.py` (5), `test_main_thread_routing.py` (7).

## Costs

All from OpenRouter's reported `usage.cost`, summed by label from the spend logs (`scratch/live/costs_*.jsonl`); the ceiling was $3 per
launch, never approached. Per-request `max_tokens` 4096.

| test | model calls | cost (USD) |
|---|---|---|
| provider smoke (Sonnet + stealth, one tool call each) | 2 | 0.0011 |
| swarm model probes (6 concurrent each, stealth then deepseek) | 12 | 0.0102 |
| (a) main agent, Mesh QA + scene edit | 4 (Sonnet) | 0.0958 |
| swarm try 1 (stealth workers: 1 of 3 worked, 2 empty) | 3 Sonnet + 8 free | 0.0842 |
| swarm try 2 (stealth workers: all 3 failed with the in-stream 502) | 3 Sonnet | 0.0788 |
| (b) swarm of 3, cancel one (deepseek workers) | 3 Sonnet + 12 deepseek | 0.0886 |
| collision run 1 (the clobber found) | 7 + 24 | 0.1329 |
| collision run 2 (with the call record) | 4 + 8 | 0.1261 |
| collision run 3 (after the fixes: all three cubes survive) | 4 Sonnet + 10 deepseek | 0.1503 |
| (c) one image, gemini-3.1-flash-image | 1 | 0.0684 |
| **total** | | **$0.8364** (launch ledgers 0.18 + 0.0788 + 0.2215 + 0.1261 + 0.2187 = 0.8251, plus 0.0113 for the two probes run outside a launch) |

Unit costs: Sonnet 5.5 about $0.02-0.03 per agent-loop call with the full tool list (about 25 tool schemas); a deepseek-v4.1-flash worker call
about $0.0004-0.0009; one Gemini 3.1 Flash Image image $0.068. Free stealth model: $0 but unusable concurrently.

## Launch command with Sonnet 5.5 as the main agent

```
cd <workspace>/wt-tools
LAMPWAY_SERVER_PYTHON=/path/to/python-with-server-installed \
scripts/lampway/lampway --env Prod --copy --provider openrouter \
  --openrouter-key-file ~/.hermes/.env --budget 3 --image-backend openrouter \
  /path/to/scene.blend
```

`anthropic/claude-sonnet-5.5` is the default main model and `deepseek/deepseek-v4.1-flash` the default swarm model (override with
`LAMPWAY_OPENROUTER_MODEL` / `LAMPWAY_OPENROUTER_SWARM_MODEL`). The server python needs `pip install -e server/` (this now pulls
`websockets`; a clean venv without it could not serve the agent socket, fixed earlier in this branch). Add `--bridge-port N` to move the
live bridge off 9876 (`0` turns it off). The key is read from the file's `OPENROUTER_API_KEY` line, or from the environment variable of the
same name; it is never printed.

## Concerns for this scope

- The three swarm names of the deliberate collision test only survive because of prompt guidance; the server cannot technically stop a
  worker script from editing another lane's `bpy.data` objects (detection and warning only; the rename false positive is known).
- `stealth/space-bunny-alpha` cannot serve a swarm today; if its concurrency improves, `LAMPWAY_OPENROUTER_SWARM_MODEL` switches back.
- The live runs used the Xvfb box display, not a real desktop; the splash screen ("Placeholder splash") covers the viewport until dismissed.
- Only one OpenRouter key location was checked (see above).
- The image result is one flat albedo for one view; picking among variants and the projection stage were not re-run live this time
  (they are covered by the earlier tests and the mocked one-button run).
- The 104 pre-existing failing tests and 5 `tests/mcp` collection errors are untouched baseline state.
