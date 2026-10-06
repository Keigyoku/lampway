# Integration log (branch lp/wave5)

Role: the implementer became the integrator; lanes lp/vault-ops, lp/vault-ui, lp/facelift and lp/docs merge `origin/lp/wave5` themselves; this log records each merge into lp/wave5.

## Integration glue

### F8: OpenRouter follows the cloud D1 click rule (found by the coordinator's site truth-check)
- Was: `DEFAULT_SPEND_POLICY["openrouter"] == {"click": "off"}`: no per-call click; only the $3 session ceiling and the per-request token cap gated spend.
- Now: `{"click": "above", "above": 0.25}` (configurable in provider prefs; `off` still works). The session ceiling is unchanged.
- Consequence found while doing it: the job queue asked the policy about an UNKNOWN price for every image job, which under any "above" rule means a click for every image. The queue now passes an estimate (`IMAGE_USD_ESTIMATE = 0.07` per image, from the spike's measured ~$0.067, times `number_of_images`); only the click decision uses it, never a charge. One to three images run untouched; four or more wait for the click.
- RED first: `test_openrouter_defaults_to_the_d1_rule_a_click_above_25_cents` failed on the old default; the three existing job-queue tests then hung on the unknown-price click, which is what drove the estimate; `test_image_jobs_follow_the_d1_click_rule_by_estimated_price` pins both sides (mutant: dropping the per-image multiplier fails it).

### Video ingest bypassed egress consent; the coverage audit is now structural (site truth-check, fix request 1)
- The bug: `videoingest.ingest` ran yt-dlp (metadata and download) with no egress check, while `egress.py` says every outbound call is checked.
- Why the promised coverage test did not catch it: `test_no_server_module_opens_a_network_door_around_the_hook` scanned only for in-process network imports (urllib, sockets, requests...). Process launches were covered by convention ("each calls `guard` where it launches") and nothing checked the convention.
- Closed by construction: `tests/test_egress_launch_audit.py` parses the server package (AST) and fails on ANY process launch (subprocess.*, asyncio.create_subprocess_*, os.system/popen/exec*/spawn*) that is not lexically inside `with ...guard(route)` and not declared in `egress.LAUNCHES` with a kind and a reason (`local`, `callers_guard` checked through every call site, `wrapped` checked through its wrapper and attribute uses, `driver` for studio driver scripts). Stale declarations fail too; a planted unguarded yt-dlp launch in a temp module is reported (the instrument is not blind).
- RED: the audit's first run listed 21 undeclared launches. Four were real bypasses and are now gated:
  1. `videoingest.ingest` → new route `video_link` (off until opted in; refused before yt-dlp starts; the log row is written before the first downloader call: `test_with_the_route_on_the_log_row_is_written_before_the_downloader_starts`).
  2. `agent/cli_adapters.codex_image` (codex `$imagegen` sends the prompt and reference images to the ChatGPT plan) → `guard(chatgpt_plan, kind=image)`.
  3. `agent/server_tools._exec` (the studio_tripo_* driver tools drive the owner's Tripo tab) → `guard(studio:tripo)`; the seed catalog (a local SQLite read) moved to `_exec_local`.
  4. Boat: only provision/upload/run were gated by the runner; status, fetch, meter, list and teardown ran the Boat CLI ungated. The guard now sits in `BoatCliBackend._cli` (every CLI call), carrying the backend's constraints (snapshots off, no env); the runner only declares the job's assets (`egress_via = "self"`). `guard()` now inherits what an enclosing `context` declared.
  The other 17 are local (ffmpeg/ffprobe, herdr, systemctl, a local blender render, codex schema generation), each declared with its reason. Declared judgement calls: the user's own stdio MCP servers (`mcp_inventory/probe._stdio`) and the long-lived codex app-server start (turns are gated in `stream()`).
- Mutants: removing each of the four new guards fails the audit.

### One state directory for the server and the compute CLI (site truth-check, fix request 2)
- Was: the server defaulted to `<XDG_STATE_HOME>/lampway-server`, `compute/cli.py` to `<XDG_STATE_HOME>/lampway`, so a route switched on in one was off in the other. `imagegen`, `files_tools` and `compute_tools` each re-derived it.
- Now: `config.state_dir()` is the one function (LAMPWAY_STATE_DIR, else `<XDG_STATE_HOME>/lampway-server`), used by `Settings.from_env`, the compute CLI, the compute agent tool, `files_tools` and `imagegen`.
- RED: `test_a_route_switched_on_through_the_server_is_on_for_the_compute_cli` (no explicit state dir anywhere; switch compute:boat on through `/app/egress/route`, then build the CLI as `compute` does: the route is on) failed before the fix.

### The four tests/lampway failures at the integration tip (docs audit, item 2)
- Why my batches did not show them: my per-wave client runs were `tests/lampway_tools` only, so the brand, links and gate checks under `tests/lampway` never ran. The batch script (`scratch/run_suites.sh`) now runs the whole root suite (`pytest` at the repository root with every pytest.ini testpath, the real binary for the tool tests) and the full server suite, in parallel.
- Fixed: the provider API hosts (fal's queue, its site, model API and storage; the Meshy, Hyper3D, Hi3D and Tripo REST APIs) are on the hosts allow-list with reasons; "no Mixar Paint material" now reads "no layer-paint material"; the MCP inventory note about a legacy entry no longer names the upstream brand; the PII allow-list entry `/home/x` says why.

### Python floor and dependencies (docs audit, item 3)
- `uuid.uuid7` (3.14 only) is replaced by `library/ids.py` (RFC 9562 version 7, local); `requires-python >= 3.11` stays.
- numpy is declared (`numpy>=1.26`) and pinned in the lock to 2.4.6: the obvious pin, 2.5.3 (the dev venv's), does not install on 3.11 (pip, measured in a 3.11 venv).
- `tests/test_python_floor.py`: every server module compiles under a real `python3.11` when one is on the machine (one is: uv's 3.11.15), and a named list of post-3.11 stdlib APIs is denied (the list cannot see an API it does not name; the compile check covers syntax, PEP 701 f-strings included).
- Evidence beyond the test: the full server suite run under a Python 3.11.15 venv built from the lock (results under "Merges").

### Receipt resolution routes (docs audit, item 4): the contract for lane facelift (spend surfaces, contract 13)
- `GET /app/receipts?state=submission_unknown` -> `{"receipts": [<export-safe receipt> + "actions": ["acknowledge", "link"]]}`.
- `POST /app/receipts/{key}/acknowledge` `{}` -> 200 `{"receipt"}` (state `abandoned`, "acknowledged by the user: it did not run").
- `POST /app/receipts/{key}/link` `{"provider_job_id": "..."}` -> 200 (state `submitted`; the queue's recovery resumes it by that id); 422 without an id.
- 401 without the user's bearer; 404 unknown key; 409 if the receipt is not `submission_unknown`; 403 if the body says `"by": "agent"` or the header `X-Lampway-Origin: agent` is present. No agent or MCP tool resolves a receipt (pinned by a test).
- After either action the job queue re-reads the receipts, so the Client's queue shows the new state at once.

### Temp files leaking into the shared /tmp (coordinator fix request)
- Cause: the real-binary tool tests made Lampway homes with `tempfile.mkdtemp(prefix="lw_home_")` in the pytest process and handed them to the binary; scripts run INSIDE the binary made `lw_bake_`, `lw_pbr_`, `lw_w_` and `lw_probe_` dirs with the binary's own TMPDIR (the shared /tmp unless the caller set one). Nothing removed them; my own batches left 24 GB in `scratch/tmp-w4`. Three production leaks too: the codex app-server provider's workdir and schema dir, and the procedural-library probe's scratch folder (one dir per probe render).
- Fixed by construction: `blender_run.run_script` points the binary's TMPDIR into the run's own temp dir (removed after the run) and resolves `@RUN_TMP@` in env values (`LAMPWAY_HOME="@RUN_TMP@/home"`); the in-process helpers use `tmp_path`; the three production sites use self-removing `TemporaryDirectory`.
- Guards: `tests/lampway/test_tmp_hygiene.py` (AST over the tests and the Lampway Python: `mkdtemp`/`mkstemp`/`NamedTemporaryFile(delete=False)` must say `dir=`; a planted leak is seen) and `tests/lampway_tools/test_tmp_hygiene_live.py` (in the real binary: a dir a script makes is not in the shared temp dir and is gone after the run; removing the TMPDIR redirect fails it).
- Not built: a before/after snapshot of every user-owned /tmp entry: other agents write /tmp at the same time, so a new entry cannot be attributed to this run.

### Python 3.11 under the full server suite
- Run: the server suite in a 3.11.15 venv built from the lock (at 341d8a5e): 1081 passed, 3 failed: `ast.TypeAlias` in the floor test itself (3.12+; fixed), `test_herdr_cockpit`'s end-reason test (ProcessLookupError: a kill race; passed on re-run under 3.11), and `test_ledger`'s concurrent appends, which deadlocked: it forks processes while its threads hold the ledger lock, and 3.11 forks by default (3.14 uses forkserver). The test now uses the spawn context; under 3.11: 21 passed (ledger, cockpit, floor). The hung forked children also kept the 3.11 pytest from exiting; killed by pid.

## Merges
(none yet: this section is appended per merge with lane, range, conflicts, suite and gate results)

## Requests to lanes
(none yet)

## Lane overlap and duplication seen
- The asset_mcp tool family (`lampway_vault_*`) was drafted by the previous implementer but not committed: a test draft is at `scratch/test_library_vault_tools.draft.py` for lane lp/vault-ui (asset_mcp is its contract). Its design: server-run tools (`agent/vault_tools.py`), a `Vault` facade (lib + ingest + embed + spool + project root), origin `agent|mcp`, rater `agent:<id>`, no SQL tool and no import tool, `scan` restricted to the project root or a user-registered source.
