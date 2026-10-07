<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Getting started

This page takes you from a clone to a first conversation with the agent. Linux is the only platform that has been built and run; macOS and Windows scripts are inherited from upstream and untested here. There are no binaries yet.

## 1. What you need

- Ubuntu 24.04 (a container or VM is fine) with GCC 14. Blender 5.2 refuses older compilers and Ubuntu 24.04 ships GCC 13 by default, so the build script installs the versioned `gcc-14` pair.
- About 13 GB of disk per build environment (`Dev` or `Prod`) and 100 GB free as a safety floor (`LAMPWAY_MIN_FREE_GB`, default 100).
- Python 3.12 or newer for the server (`server/pyproject.toml` says 3.11 or newer; 3.12 and 3.14 have run the suite). The Asset Vault library needs 3.14 today ([asset vault](asset-vault.md)).
- Optional, per feature: an OpenRouter key, a ChatGPT plan, an Anthropic key, a local OpenAI-compatible server, the `boat` CLI for the compute wrapper.
- For agent panes (the cockpit, both agent modes): Lampway's pinned herdr (`third_party/herdr`, tag `v0.9.3`). Build it with `scripts/lampway/herdr_env.py`, which needs Rust through rustup and Zig 0.16.0; `--check-deps` names what is missing. See [providers](providers.md).
- For Lampway's own agent (Mode 1): the pinned Hermes engine (`third_party/hermes-agent`, tag `v2026.9.24`), built with `scripts/lampway/engine_env.py` (`--check-deps` names what is missing; the build also prebuilds Hermes's TUI with npm), and Node.js 22 or 24 at run time (on PATH, or `LAMPWAY_NODE`). Lampway never downloads either at run time. Without them Lampway's agent refuses every message, saying which is missing; your own agent (Mode 2) still works.

## 2. Get the source

```bash
git clone https://github.com/Keigyoku/lampway.git
cd lampway
```

`upstream/` is a git submodule of Blender at the pinned `v5.2.0` tag. You do not need `--recursive`: the build script fetches the submodule shallow at the committed pin, then pulls its LFS payload and the precompiled libraries (git-lfs is needed in the build environment).

## 3. Build the app

Run these inside the Ubuntu 24.04 environment. The maintainer uses a distrobox named `lampway-build`; any Ubuntu 24.04 works.

```bash
scripts/lampway/build_linux.sh --check-deps    # names anything missing (exit 2) and prints the apt line
scripts/lampway/build_linux.sh --plan          # prints what a run would use; touches nothing
MIXAR_ENV=Prod scripts/lampway/build_linux.sh  # the build variables keep their upstream names for now
```

Measured: a clean build is 41 minutes on 5 of 16 cores; an unchanged re-run is about a minute. The result is `build/Prod/bin/mixar`. Use `Dev` while developing and `Prod` for the real thing (only a `Prod` build shows whether the upstream native login gate is really gone). A build with `MIXAR_CUDA=0` (the default here) renders Cycles on the CPU only. The full table of steps, timings and disk use is in [`BUILD-LAMPWAY.md`](../BUILD-LAMPWAY.md).

If `distrobox enter` answers `unable to find user` right after another session ended, use the numeric form: `podman exec --user 1000:1000 -w "$PWD" lampway-build ./scripts/lampway/build_linux.sh`.

## 4. Install the server

```bash
python3 -m venv server/.venv
server/.venv/bin/pip install -r server/requirements-lock.txt   # the exact versions the suite was verified with
server/.venv/bin/pip install -e server/
```

The launcher uses `server/.venv/bin/python` when it exists; otherwise set `LAMPWAY_SERVER_PYTHON`.

## 5. Launch

```bash
scripts/lampway/lampway --env Prod --copy --provider mock path/to/scene.blend
```

The one command:

1. starts the server on `127.0.0.1:8787` (or uses a Lampway server that already answers there),
2. starts the app against it, with the tools and the live bridge on,
3. opens a **copy** of your file under `<home>/copies/` (`--copy`; without it your file is opened directly),
4. stops the server it started when the app exits.

Useful flags: `--plan` (print every resolved setting, start nothing), `--no-server`, `--port`, `--bridge-port 0` (live bridge off), `--system-keyring`, `--install-desktop` (an app-menu entry). Refusals go to stdout and exit 1; an unknown flag exits 2.

The profile lives under `$LAMPWAY_HOME` (default `~/.local/share/lampway`): `config/`, `data/`, `projects/` (the project root the tools are jailed to), `server-state/` (secrets, prefs, ledgers), `copies/`, `bridge/`, `keyring.json` (a file keyring, 0600), `server.log` and `server.pid`. Your stock Blender profile is not touched.

Login is automatic: the client opens the server's loopback sign-in page in your browser and the server approves it at once. Set `LAMPWAY_USER_PASSWORD` to make that page ask for a password.

## 6. First conversation

Lampway's agent (Mode 1) is the pinned Hermes runtime in a pane of Lampway's herdr server; the island in the app is a second window onto that same conversation. Before the first message: build the engine and herdr (section 1), have Node.js, and start the herdr server from the cockpit (**Lampway > Agents**). Your first message in a scene tab opens that tab's agent pane; later messages go to the same conversation, which survives a restart of the app or the server.

If something is missing, the message is not sent and the island says what to do: `scripts/lampway/engine_env.py` for the engine, `scripts/lampway/herdr_env.py` (or `LAMPWAY_HERDR_BIN`) for herdr, Node.js 22 or 24 (or `LAMPWAY_NODE`) for the pane's TUI, or starting the herdr server. You can also switch the tab to **Your agent** and work with your own agent CLI in its pane instead. There is no built-in fallback agent.

The agent thinks with the provider you chose, through the server's loopback gateway. `--provider mock` has no model behind it: it was written for Lampway's removed built-in loop and does not drive Hermes's tools, so use it only to check that the pane starts. To work with the scene, start with a real provider (next section).

## 7. Choose a provider, then open its route

```bash
# OpenRouter, with a hard session ceiling (default $3)
scripts/lampway/lampway --env Prod --copy --provider openrouter \
  --openrouter-key-file ~/.config/lampway/openrouter.env --budget 3 --image-backend openrouter scene.blend
```

The server starts with **every outbound route off**. The first call to OpenRouter, ChatGPT, Anthropic or any studio is refused with `<route> is off: switch it on in Privacy`, and nothing is sent. Open the **Lampway** tab in the 3D viewport sidebar, expand **Privacy (what leaves this machine)**, read each route's retention and training policy, and press **Switch on** for the ones you use. The badge at the top of the panel reads `DATA LEAVING: <route>` while a call is in flight. Loopback traffic (the mock provider, a local Ollama) is never gated. More in [privacy](privacy.md).

Model, swarm and image settings are in the **Providers** button of the Studios panel; they are saved with 0600 permissions and applied to new turns without a restart. Details, defaults and the studios are in [providers](providers.md); money is in [spend](spend.md).

## 8. Connect another AI app (optional)

Profile menu, **Connect AI Apps (MCP)**, enable MCP, pick your app and click **Add**. See [`docs/lampway/connect-ai-apps.md`](lampway/connect-ai-apps.md). The **Connections (MCP servers)** panel in the Lampway tab shows which MCP servers each of your agent apps has and checks one on your click.

## 9. Optional pieces and their settings

| Setting | Environment variable | What it is for |
|---|---|---|
| project root | `LAMPWAY_PROJECT_ROOT` | where pieces live; every tool path must stay inside it (the launcher sets `<home>/projects`) |
| science python | `LAMPWAY_PYTHON_SCIENCE` | a Python with numpy, scipy, Pillow, OpenCV: texture and part-transfer tools, robust weight transfer |
| browser python | `LAMPWAY_PYTHON_BROWSER` | a Python with patchright: the Tripo Studio browser drivers (run by the server, never the app) |
| Studio shelf | `LAMPWAY_STUDIO_SHELF` | a folder of AXI studio drivers that supersedes the bundled ports (`tripo_uv` and paired `--views` need it) |
| tool browser | `LAMPWAY_STUDIO_CDP` | the debugging address of the browser holding your studio login (default `http://127.0.0.1:9333`) |
| studio guard | `LAMPWAY_STUDIO_ARMED=1` | set by the confirmed run for that process only; never set it yourself globally |
| AutoRemesher | `LAMPWAY_AUTOREMESHER_BIN` | the executable built by `native/quadremesh/build.sh`; the app never downloads one |
| your own agents | `LAMPWAY_LOCAL_CLI=1` | lets the cockpit start your own Claude Code, Codex or OpenCode in its panes (see [cockpit](cockpit.md)) |
| herdr | `LAMPWAY_HERDR_BIN`, `LAMPWAY_HERDR_BUILDS`, `LAMPWAY_HERDR_ROOT` | the cockpit's own herdr server (see [cockpit](cockpit.md)): the pinned build under `LAMPWAY_HERDR_BUILDS` (default `build/herdr`) is used ahead of one on PATH; `LAMPWAY_HERDR_BIN` overrides both |
| server bind | `LAMPWAY_HOST`, `LAMPWAY_PORT` | default `127.0.0.1:8787`; a Host guard answers 421 to any other Host |
| state dir | `LAMPWAY_STATE_DIR` | secrets, prefs, egress prefs and log, spend log (the launcher sets `<home>/server-state`) |

Tool settings can also be saved in `<home>/settings.json`; the environment wins over the file, the file over the default.

## 10. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `no build at .../build/Prod/bin/mixar` | build first, or pass `--env Dev` |
| `port 8787 is in use by something that is not a Lampway server` | pick another port with `--port` |
| the server exits at start-up | read `<home>/server.log` |
| `<route> is off: switch it on in Privacy` | expected; open the route in the Privacy panel |
| the agent says Lampway's Hermes engine is not running (`engine_not_built`) | build it: `scripts/lampway/engine_env.py`, then restart Lampway; or switch the tab to Your agent |
| the agent says Node.js was not found (`node_missing`) | install Node.js 22 or 24, or point `LAMPWAY_NODE` at it |
| the agent says no herdr was found, or the herdr server is not running | build herdr with `scripts/lampway/herdr_env.py` (or set `LAMPWAY_HERDR_BIN`), then start its server from Lampway > Agents |
| `no OpenRouter key` | set `OPENROUTER_API_KEY` or pass `--openrouter-key-file` |
| a refusal naming the local-CLI switch | your own agents in the cockpit's panes need `LAMPWAY_LOCAL_CLI=1` (see [cockpit](cockpit.md)) |
| `claude_cli is retired` (or `codex_cli`, `codex_app_server`) | those providers are gone: pick an API key, an endpoint you run or Sign in with ChatGPT, and run the CLI as your own agent in the cockpit (see [providers](providers.md)) |
| startup logs `Failed to import ... procedural_materials` lines from the paint package | upstream withheld that package; Lampway ships a small replacement (see [`BUILD-LAMPWAY.md`](../BUILD-LAMPWAY.md) section 4) |

## Next

[Providers](providers.md) | [Privacy](privacy.md) | [Spend](spend.md) | [Tools](tools.md) | [Roadmap](roadmap.md)
