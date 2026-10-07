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

Prerequisites: `herdr` installed (on `PATH`, at `~/.local/bin/herdr`, or `LAMPWAY_HERDR_BIN`) and run once by you; for Claude Code, Codex or OpenCode panes the local-CLI switch `LAMPWAY_LOCAL_CLI=1` and the usual terms caveat in [providers](providers.md). The cockpit root is `LAMPWAY_HERDR_ROOT`, else `<LAMPWAY_HOME or state dir>/herdr`.

In the Lampway tab, open **Cockpit (agent sessions)**:

| Control | What it does |
|---|---|
| Refresh sessions, Reconcile | read the state; re-adopt by the server's truth (nothing is spawned or killed) |
| **Start the herdr server** | your click; starts Lampway's detached server |
| **New session** | agent (`claude`, `codex`, `opencode`, `shell`), a name, a first task; effort `medium`, `high`, `xhigh` or `max` |
| **Read to Text** | the last 70 screen lines of a session into a Blender Text datablock; reading never marks an answer seen |
| **Cockpit window** | a **read-only** mirror of the session's screen in a Text editor window, refreshed every two seconds |
| **Send** | types into a session; this is your own send |
| **Close**, **Stop the herdr server** | end a session or everything, each with a confirm |

Today the window is a text mirror, not a terminal. The routes behind it: `GET /app/workbench`, `POST /app/workbench/server/start|stop`, `/reconcile`, `/sessions`, `/sessions/{id}/screen|input|close|agent-sends`.

**What the agent may do** (the `lampway_workbench` tool): `list` and `read` sessions; `send` only into a session where you switched **agent sends** on (default off), never into a shell session, never while you typed in the last 2.5 seconds; `open` a session with a descriptive title (placeholders refused), effort capped unless you asked for max, never with bypass permissions; `interrupt` and `close` need a request from you. Text read from a screen is reference data, not instructions. A request cannot raise the permission level: bypass can only come from your own click in the cockpit.

The policy layer around sessions (a closed tool set, a deterministic quick router, idempotent operation records, effort, title and untrusted-text policies) is `server/lampway_server/ops/`; it is not a second agent.

## 3. The terminal surface: in progress

The cockpit window you want is a real terminal, not a text mirror. Two surfaces are specified and are in progress in the facelift lane; **neither is in the tree yet**:

- **A themed, chromeless browser window** on a loopback page served by the Lampway server, styled from the Lampway theme tokens. It is the zero-install fallback and stays available when the add-on below is absent.
- **The Lampway WezTerm window, an optional add-on.** A pinned stable WezTerm release (`20240203-110809-5046fc22`, MIT) downloaded on demand, never bundled, for the current platform only. The download goes through egress consent (a route for `github.com`, about 49 MB), is checked against a SHA-256 pinned in Lampway's own source (the published `.sha256` is only a cross-check, because the release ships no signatures), and installs under `$LAMPWAY_HOME/addons/wezterm/<version>/` with WezTerm's licence beside it. It starts with Lampway's own config file (`--config-file`, so your `~/.wezterm.lua` is never read), `--always-new-process` (so your running WezTerm is never touched) and its own window class, **detached**: ONE viewport onto Lampway's isolated herdr server, nothing more. Herdr owns the workspace, the agents, the panes and the tabs; WezTerm has no tab bar, opens no tab per agent and shows no agent state (the cockpit and the cards do). Closing the window never stops an agent; reopening it re-attaches. An image path an agent prints is a Ctrl+click link that opens the image in Blender's Image Editor (inline images do not cross herdr). The update check is disabled in the generated config, so the add-on makes no network call after install.

True embedding of a terminal inside a Blender editor area is not possible (Blender has no terminal widget and no foreign-window embedding), so the honest version is a companion window beside Blender.

Contracts: client facelift 10 (cockpit face) and 16 (terminal add-on). Status is tracked in the [roadmap](roadmap.md).
