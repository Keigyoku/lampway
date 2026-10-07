# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Codex CLI (`codex`): the user's own Codex, on its own login (Sign in with ChatGPT or the user's key), in a Lampway pane.

New session: `codex --no-alt-screen`; resume: `codex resume <id> --no-alt-screen`. Effort: `-c model_reasoning_effort="<e>"`.
Bypass (the user's tick only): `--dangerously-bypass-approvals-and-sandbox`. Lampway's tools: `-c mcp_servers.lampway...`
overrides on the pane's own command line, so the user's config.toml is never changed. Verified on an installed Codex CLI 0.161.0
(see FACTS).
"""
import json
import os
from pathlib import Path

from .base import BOUND_ENV, SERVER_NAME, Adapter, Observer, ToolWiring, direct_binding

#: Codex cuts a tool call off after its default timeout; a scene call may run 570 s (the Client's setup uses the same value).
TOOL_TIMEOUT_S = 610


class Codex(Adapter):
    id = "codex"
    label = "Codex CLI"
    binary = "codex"
    config_name = "mcp.toml"
    herdr_kind = "codex"
    install_hint = "install the Codex CLI (codex) from OpenAI: npm install -g @openai/codex"
    status_argv = ("login", "status")
    BYPASS = ("--dangerously-bypass-approvals-and-sandbox",)
    task_flag = ()                            # `codex [PROMPT]`: the TUI starts with it
    direct_ok = True                          # a streamable-HTTP entry: url, bearer_token_env_var, http_headers
    interrupt_keys = ("esc",)
    takes_image_paths = True
    FACTS = {
        "version": "0.161.0 installed with npm (@openai/codex) into a scratch prefix; `codex --version` -> 'codex-cli 0.161.0'",
        "argv": "`codex --help` / `codex resume --help` (0.161.0): `[PROMPT]`, `resume [SESSION_ID] [PROMPT]`, `-c key=value` (TOML), "
                "`--no-alt-screen`, `--dangerously-bypass-approvals-and-sandbox`",
        "status": "`codex login status` in a signed-out HOME prints 'Not logged in' and exits 1 (0.161.0): the exit status is the signal",
        "mcp_overrides": "`codex <these -c overrides> mcp list --json` (0.161.0, no login) lists `lampway` as a stdio server with this "
                         "pane's command, args and LAMPWAY_BOUND_SESSION, tool_timeout_sec 610, and the swarm entry as streamable "
                         "HTTP with its bearer variable and headers (tests/test_byoa_harnesses.py pins the argv)",
        "session_file": "rollouts under $CODEX_HOME/sessions (default ~/.codex), matched by session_meta (observers/native.py); still "
                        "the default store in 0.161.0: `codex features list` shows background_paginated_rollout_migration 'under "
                        "development, false' and `codex migrate-rollouts` calls rollouts the legacy sessions it would move. When that "
                        "migration ships, the rollout match finds nothing and the island shows no observed turns. [UNVERIFIED: a "
                        "rollout written by 0.161.0, since a turn needs an account]",
        "interrupt": "Esc: herdr 0.9.3's pinned detection manifest (codex.toml) reads a running turn by Codex's '<key> to interrupt' "
                     "hint, Esc by default. [UNVERIFIED on the installed copy: a turn needs an account]",
        "images": "a pasted image path is attached by the TUI; `-i/--image` exists only for the first prompt. [UNVERIFIED on the "
                  "installed copy: a turn needs an account]",
    }

    def _args(self, pane, resume_id):
        a = ["resume", resume_id] if resume_id else []
        a += ["--no-alt-screen"]
        a += self._bypass(pane)
        if pane.effort:
            a += ["-c", f'model_reasoning_effort="{pane.effort}"']
        return a

    def lampway_tools(self, pane):
        cmd = list(pane.launcher) or ["lampway-mcp"]
        argv, record, env = [], "", {}
        if pane.desktop:
            key = f"mcp_servers.{SERVER_NAME}"
            argv += ["-c", f"{key}.command={json.dumps(cmd[0])}", "-c", f"{key}.args={json.dumps(cmd[1:])}",
                     "-c", f"{key}.env.{BOUND_ENV}={json.dumps(pane.scene_session_id or '')}", "-c", f"{key}.tool_timeout_sec={TOOL_TIMEOUT_S}"]
            record += (f"[{key}]\ncommand = {json.dumps(cmd[0])}\nargs = {json.dumps(cmd[1:])}\ntool_timeout_sec = {TOOL_TIMEOUT_S}\n\n"
                       f"[{key}.env]\n{BOUND_ENV} = {json.dumps(pane.scene_session_id or '')}\n")
        for d in pane.direct:                 # spec S3: the bearer only in the pane's environment, never on its command line or in a file
            key = f"mcp_servers.{d.name}"
            headers = "{" + ", ".join(f"{json.dumps(k)} = {json.dumps(v)}" for k, v in d.headers.items()) + "}"
            argv += ["-c", f"{key}.url={json.dumps(d.url)}", "-c", f"{key}.bearer_token_env_var={json.dumps(d.token_env)}",
                     *(["-c", f"{key}.http_headers={headers}"] if d.headers else []), "-c", f"{key}.tool_timeout_sec={TOOL_TIMEOUT_S}"]
            record += (f"\n[{key}]\nurl = {json.dumps(d.url)}\nbearer_token_env_var = {json.dumps(d.token_env)}\n"
                       + (f"http_headers = {headers}\n" if d.headers else "") + f"tool_timeout_sec = {TOOL_TIMEOUT_S}\n")
            env[d.token_env] = d.token
        path = pane.mcp_config_path
        return ToolWiring("mcp_override", tuple(argv), env, {path: record.lstrip("\n")} if path else {}, tuple(pane.launcher),
                          pane.scene_session_id or direct_binding(pane), True,
                          "-c overrides of mcp_servers.lampway on the pane's own command line (checked with `codex mcp list --json`, 0.161.0); the "
                          "file is the same entry, kept for the record")

    def observe(self, record):
        home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
        return Observer("rollout", home, True, "Codex's own rollout files under its home (observers/native.py codex_find_session)")
