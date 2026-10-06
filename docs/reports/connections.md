<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Lane `lp/connections`: report

Worktree `<workspace>/wt-connections`, branch `lp/connections`, from `lp/wave5` at `00d907d4`. Specs:
`specs/connections/` (C1-C10 as recommended, C4 changed by the captain to "Hyper3D MCP sign-in now") and `specs/choices/`
(CH1-CH8 as recommended). Server suite run in the shared tools venv (Python 3.14.7), every run with its own basetemp under
the lane's scratch directory, deleted after. Commits are the noreply identity, no trailers.

## Per item

| # | item | state | commits |
|---|---|---|---|
| 1 | `connections_store` (hub, store, redaction, atomic writes, locks, scanner, checks, poller) | done | `71991f7a`, `eeb6b315`, `46ea1734` |
| 1+ | Hyper3D MCP (captain's C4 change): one generic MCP OAuth + client, the `mcp:hyper3d` row, seven Studio actions | done | `2d1d5bda`, `4cd2687d` |
| 2 | F4: scrubbed child environments | done | `b6e466aa` |
| 3 | F6: receipt `error_text` redaction | done (in the first commit) | `71991f7a` |
| 4 | F7 + C8: owner-only OpenRouter and fal key files | done | `1016aeb5` |
| 5 | F8: bearer on the old status routes, answers narrowed | done | `f16dd8aa` |
| 6 | `connections_status_tool` (`lampway_connections`) | done | `c0b18a23` |
| 7 | `connections_migration` (BYOK F3/C5, compute, keyring move C7, real-use reporting) | done | `3ea97a10`, `233233d8`, `64c72c09`, `7289b1b6` |
| 8 | Choices server side | in progress (see the Choices section) | |

## What was built

**`server/lampway_server/connections/`** (11 modules, each under 300 lines):
- `registry.py`: CATALOGUE.md tables A-C as data, 28 rows. Studio REST rows are derived from `studios/rest/shapes.py` (the
  key variables and the balance read are the driver's own). `uses` are registered by consumers at import (`register_use`;
  today: the image backends and every Studio action).
- `store.py`: `KeyringStore` (service `lampway`, user `<id>:<field>`), `FileStore` (0600 JSON in a 0700 directory,
  `LAMPWAY_SECRETS_DIR`, default `$XDG_STATE_HOME/lampway-secrets`), `MemoryStore`. The choice is a write-read-delete probe;
  a locked keyring stays the keyring and refuses with "your keyring is locked: unlock it and try again (nothing was saved)".
- `files.py`: atomic write (temp, fsync, replace, directory fsync), read that sets an unparseable file aside, `fcntl` lock.
- `sources.py`: env, env-named key file, the user's pointer (a variable NAME or a PATH, never a value), manual, sign-in,
  host. `Credential` has no repr/str/pickle/JSON and no attribute holding a value; `secret_of` is the one internal door and
  every value it hands out is registered with the log redactor first.
- `views.py`, `actions.py`, `hub.py`: the six states, the qualifiers, C1 (a Test with the route off sends nothing and says
  which host and route), C2 (the poller: 30 min, route on, used in the last day, reads only, single-flight, never at start;
  wired into the server's existing 60 s tick), C3 (an environment source wins; the conflict is shown on the row), C8.
- `checks.py`: the free checks of table C (http through the egress hook, MCP `initialize` + `tools/list` + a named free
  tool, the Boat CLI status command with a scrubbed environment, the tool browser's loopback CDP read).
- `routes.py`: `/app/connections*` behind the bearer; writes refuse a declared agent origin and a cross-origin request.
- `logredact.register_secret`: an exact-value set applied to every log record (tracebacks included) and to receipt texts.

**Hyper3D MCP** (`mcp_oauth.py`, `mcp_client.py`, `studios/mcp_driver.py`): Higgsfield and Hyper3D are two configurations
of one MCP OAuth module (RFC 9728 from the documented URL or from the server's own 401, RFC 8414, RFC 7591 as "Lampway",
S256 PKCE on the loopback port) and one MCP client. Hyper3D's session lives in the Connections store; Claude Code's Hyper3D
token is never read (a test plants it and records every `open`). The seven tools are Studio actions `hyper3d.mcp.*`;
`generate` and `generate_bang` are planned with no tool called, need `accept_up_to_credits` (no published price), wait for
the user's click, have their receipt pending before the driver runs, are called once and reported HUNG on a timeout.

**Migration**: OpenRouter, fal, Anthropic, the OpenAI-compatible endpoint and the compute endpoints resolve their keys
through Connections (same exception types and messages); Studio drivers get their key through `env_for` under the name
they read; BYOK writes into Connections and an older plain key moves on start, verified before it leaves the JSON (F3);
the launcher moves `$LAMPWAY_HOME/keyring.json` to `$XDG_STATE_HOME/lampway/keyring.json` once and exports
`LAMPWAY_SECRETS_DIR` (C7); a real 401/403 from OpenRouter or the OpenAI-compatible endpoint turns the row `expired`.

## RED evidence (measured; each in its commit body)

- store 8, hub 25, routes 8 (404), redaction 2: against `NotImplementedError` stubs or missing routes.
- F5: 6 failed, among them `resolve_jwt_secret` returning `''` for an empty file (the server would have signed with an
  empty HS256 key).
- F9: two spawned processes against a rotating, reuse-refusing token endpoint: one got `at-1`, the other
  `refresh_token_reused` - a signed-out user. After: both `at-1`, exactly one refresh request.
- MCP OAuth 8; Hyper3D: the action set was empty, the other driver tests first timed out on a nested `flock` (a real
  defect, the wrong reason for RED) and were then mutation-checked (6 mutants, each killed).
- F4 5, F7 2, F8 4, status tool 7, migration 4 (+3 compute, +1 real use), keyring move 3.
- Tests written after the code were mutation-checked (scan reading a planted file, a check sending a POST, an MCP check
  calling a second tool, the CLI check given the unscrubbed environment, PUT echoing its body, receipts without redaction).

## Test totals

- Server suite at `7289b1b6`: **1184 passed, 6 skipped** (729 s).
- Client suite (root `pytest`, `LAMPWAY_BIN` = the lane's binary, `--continue-on-collection-errors`): 7908 passed,
  123 failed, 75 skipped, 20 errors. The same 143 failing ids run at `00d907d4`: 139 fail there too (inherited; the
  integrator's triage counts them, `tests/mcp/*` need `mcp`/`jsonschema` the venv lacks). The other 4
  (`space_mixie_chat/tests/test_turn_resume.py`) pass when run alone in this tree: an order dependence in the full run, in a
  module this lane does not touch.

## Findings and things to know

- **Fixed in passing:** before the conftest isolation, a consumer running outside `create_app` (an OpenRouter provider in a
  provider test) recorded its use in the real `~/.local/state/lampway-server/connections.json`. This lane's runs created that
  directory (CATALOGUE.md measured it absent); it held two fake-key rows (no value) and was removed. Every test now gets an
  active hub in its own tmp.
- **Spec values I followed but question:** `CONNECTIONS.md` says a pointer's lock is `<secrets>/<id>.lock`; the OAuth adapters
  lock beside their own file (they do not know the secrets directory). Same effect: every process that refreshes shares it.
- **Behaviour changes, all decided:** a group- or world-readable key file is refused (C8); with both `FAL_KEY` and
  `FAL_KEY_FILE` set the variable wins (C3; the old code read the file first); a key preview shows only when 16 characters
  stay hidden (spec 8.3); `/app/chatgpt/status` and `/app/higgsfield/status` need the bearer (F8).
- **Not done here:** the integrator's F1/F2 hotfix (`56ebbd94`, sandbox deny list and the bearer-module probes 14a-c) is not
  on `origin/lp/wave5` yet, so this branch does not build on it; test 14 is the integrator's. The cockpit panes (the user's own
  CLIs in herdr) still inherit the server environment: F4 named three sites and those are done.
- **Graph:** `codebase-memory-mcp` could not index this worktree ("a pre-coordination or unverified CBM generation is
  active", twice); the only indexed Lampway trees were older ancestors. Files were read directly.

## Merge notes

- New files only under `server/lampway_server/connections/`, `choices/`, `mcp_oauth.py`, `mcp_client.py`,
  `studios/mcp_driver.py`, `agent/connections_tools.py`, tests `server/tests/test_connections_*`, `test_mcp_oauth.py`,
  `test_hyper3d_mcp.py`, `fake_mcp_oauth.py`, `fixtures/hyper3d_tools_list.json`.
- Hot files touched: `app.py` (the hub, the Hyper3D callback, the poller in the tick, the BYOK move), `agent/providers/
  __init__.py`, `studios/service.py` (`_env`), `studios/actions.py` (MCP actions, uses), `agent/tools.py`, `agent/turns.py`,
  `mcp.py`, `imagegen.py` (uses), `scripts/lampway/lampway`, the client's `lampway_tools/keyring_file.py`.
- `server/pyproject.toml` declares `keyring` and `secretstorage` (C6); `requirements-lock.txt` is not regenerated here (it
  records a build-box venv).
- `docs/tools.md` (generated by `docs/gen_tools.py` on the integration branch) gains `lampway_connections`; regenerate it.
