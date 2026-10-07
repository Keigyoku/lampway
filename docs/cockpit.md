<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Cockpit: your real agent CLIs, in Lampway's own isolated herdr

The cockpit lets you run your own Claude Code, Codex or OpenCode sessions from inside Lampway, persistently, without touching any other terminal setup on your machine. The sessions are panes of a **herdr server that Lampway runs itself**, on its own socket and its own config, separate from any herdr you use elsewhere.

Code: `server/lampway_server/herdr/` (launcher, session host, activity observers), routes `/app/workbench/*`, the agent tool `lampway_workbench`, and the **Cockpit (agent sessions)** panel in the Lampway tab.

## 1. The two guarantees

**Isolation.** Lampway never addresses any other herdr server. Every herdr invocation goes through one launcher function that sets `HOME`, `XDG_CONFIG_HOME`, `HERDR_SOCKET_PATH`, `HERDR_CLIENT_SOCKET_PATH` and `HERDR_CONFIG_PATH` under a Lampway root, scrubs every inherited `HERDR_*` variable, and refuses to run otherwise. The only process-spawning code in the package is that launcher. The agents inside the panes still see your real login environment (`HOME`, `CLAUDE_CONFIG_DIR`, `CODEX_HOME` and the XDG directories are passed through to the panes), so your own CLIs are logged in as you.

**Controlled decoupling.** The maintainer's rule, in his words: "Lampway crashing and having to restart doesn't touch the agents. Lampway comes back, reconciles, and you're back in business." In the code:

- The herdr server and its agent panes **survive** Blender crashing, being killed or closed, an add-on unregister, and the Lampway server restarting or crashing. The server is launched detached (a transient `systemd --user` unit when available, otherwise its own session), never as a child that dies with Blender.
- Nothing stops a pane or the server implicitly. Only an explicit action of yours stops them (**Stop the herdr server** asks you to confirm that every session in it ends, and **Close** on a session asks too), or an agent finishing on its own.
- On every start the server runs **one idempotent reconcile pass** that also covers paid jobs ([spend](spend.md)). The live herdr server is the truth and the session registry is the map:
  - a live pane with a record is **re-adopted**;
  - a live pane with no record is shown as *unadopted* and is **never killed and never typed into**;
  - a record with no pane (or the agent process gone) is marked *ended*, keeps its transcript for resume, and is **never respawned without your click**;
  - if the herdr server is not running, reconcile reports it and offers start and resume as your actions; it never relaunches agents by itself;
  - a second reconcile changes nothing and never double-spawns.

Survival was exercised against the real herdr binary: SIGKILL of the agent process and of the Lampway server left panes and records intact and the next reconcile re-adopted them. (An earlier test asserted one end reason; herdr closes a dead command's pane on its own clock, so "gone from the server" and "no longer running" are both accepted.)

## 2. Using it

Prerequisites: `herdr` installed (on `PATH`, at `~/.local/bin/herdr`, or `LAMPWAY_HERDR_BIN`) and run once by you; for a pane running your own agent the switch `LAMPWAY_LOCAL_CLI=1` and that harness's egress route (`byoa:claude`, `byoa:codex`, `byoa:hermes`, `byoa:opencode`, `byoa:pi`, `byoa:grok` or `byoa:cursor`) switched on in Privacy ([privacy](privacy.md)). Each pane runs the vendor's own binary as you, on its own login; Lampway never reads that login and never sends a model request through it. herdr and its panes start without your API keys; a key reaches a pane only when you tick "bill this pane to my API key" for it.

The harnesses come through one adapter each (`server/lampway_server/herdr/harnesses/`, agent-modes spec B1). Claude Code, Codex CLI and OpenCode start exactly as before; Hermes Agent (your own, never Lampway's engine), Pi, Grok and Cursor's `cursor-agent` are wired from their vendors' documentation and not yet from an installed copy, so their flags are marked `[UNVERIFIED]` in the code. The cockpit root is `LAMPWAY_HERDR_ROOT`, else `<LAMPWAY_HOME or state dir>/herdr`.

In the Lampway tab, open **Cockpit (agent sessions)**:

| Control | What it does |
|---|---|
| Refresh sessions, Reconcile | read the state; re-adopt by the server's truth (nothing is spawned or killed) |
| **Start the herdr server** | your click; starts Lampway's detached server |
| **New session** | agent (`claude`, `codex`, `opencode`, `shell`), a name, a first task; effort `medium`, `high`, `xhigh` or `max` (the server also accepts `hermes`, `pi`, `grok` and `cursor`) |
| **Read to Text** | the last 70 screen lines of a session into a Blender Text datablock; reading never marks an answer seen |
| **Cockpit window** | a **read-only** mirror of the session's screen in a Text editor window, refreshed every two seconds |
| **Send** | types into a session; this is your own send |
| **Close**, **Stop the herdr server** | end a session or everything, each with a confirm |

Today the window is a text mirror, not a terminal. The routes behind it: `GET /app/workbench`, `POST /app/workbench/server/start|stop`, `/reconcile`, `/sessions`, `/sessions/{id}/screen|input|close|agent-sends`.

**A pane bound to a scene tab.** A harness pane can be bound to the scene tab it was started from (`scene_session_id` on create, or `POST /app/workbench/sessions/{id}/binding`, from your Client only). The pane then gets its own MCP config under the cockpit root (`panes/<id>/`), pointing at Lampway's MCP launcher with `LAMPWAY_BOUND_SESSION` set to that tab, so its tool calls land in that tab; your own user-scope MCP entries are left alone. Claude Code is pointed at the file with `--mcp-config`, Codex with `-c mcp_servers.lampway...` overrides and OpenCode with `OPENCODE_CONFIG`; for the other harnesses the file is written but no flag is known yet. Unbinding (closing the tab) only changes that file and the record: the pane runs on, listed unbound, and a running harness picks up a new binding when it next starts its Lampway server.

**Who is typing** is decided by the server from the caller, never from a field in the request: a request that declares an agent origin, a cross-origin request or an agent's token is an agent send.

**What the agent may do** (the `lampway_workbench` tool): `list` and `read` sessions; `send` only into a session where you switched **agent sends** on (default off), never into a shell session, never while you typed in the last 2.5 seconds; `open` a session with a descriptive title (placeholders refused), effort capped unless you asked for max, never with bypass permissions; `interrupt` and `close` need a request from you. Text read from a screen is reference data, not instructions. A request cannot raise the permission level: bypass can only come from your own click in the cockpit.

The policy layer around sessions (a closed tool set, a deterministic quick router, idempotent operation records, effort, title and untrusted-text policies) is `server/lampway_server/ops/`; it is not a second agent.

## 3. The terminal surface: in progress

The cockpit window you want is a real terminal, not a text mirror. Two surfaces are specified and are in progress in the facelift lane; **neither is in the tree yet**:

- **A themed, chromeless browser window** on a loopback page served by the Lampway server, styled from the Lampway theme tokens. It is the zero-install fallback and stays available when the add-on below is absent.
- **The Lampway WezTerm window, an optional add-on.** A pinned stable WezTerm release (`20240203-110809-5046fc22`, MIT) downloaded on demand, never bundled, for the current platform only. The download goes through egress consent (a route for `github.com`, about 49 MB), is checked against a SHA-256 pinned in Lampway's own source (the published `.sha256` is only a cross-check, because the release ships no signatures), and installs under `$LAMPWAY_HOME/addons/wezterm/<version>/` with WezTerm's licence beside it. It starts with Lampway's own config file (`--config-file`, so your `~/.wezterm.lua` is never read), `--always-new-process` (so your running WezTerm is never touched) and its own window class, **detached**, one tab per agent attached to Lampway's isolated herdr server, with the agent state and egress state drawn on the tab titles. Closing the window never stops an agent; reopening it re-attaches. Lampway never sends text to a pane it did not create. The update check is disabled in the generated config, so the add-on makes no network call after install.

True embedding of a terminal inside a Blender editor area is not possible (Blender has no terminal widget and no foreign-window embedding), so the honest version is a companion window beside Blender.

Contracts: client facelift 10 (cockpit face) and 16 (terminal add-on). Status is tracked in the [roadmap](roadmap.md).
