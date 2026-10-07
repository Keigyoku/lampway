# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Codex CLI (`codex`): the user's own Codex, on its own login (Sign in with ChatGPT or the user's key), in a Lampway pane.

New session: `codex --no-alt-screen`; resume: `codex resume <id> --no-alt-screen`. Effort: `-c model_reasoning_effort="<e>"`.
Bypass (the user's tick only): `--dangerously-bypass-approvals-and-sandbox`. Lampway's tools: `-c mcp_servers.lampway...`
overrides on the pane's own command line [UNVERIFIED], so the user's config.toml is never changed.
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
    task_flag = ()                            # `codex "<prompt>"`: the TUI starts with it [UNVERIFIED by fixture]
    direct_ok = True                          # a streamable-HTTP entry: url, bearer_token_env_var, http_headers [UNVERIFIED by fixture]

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
                          pane.scene_session_id or direct_binding(pane), False,
                          "[UNVERIFIED] -c overrides of mcp_servers.lampway on the pane's own command line; the file is the same entry, kept for the record")

    def observe(self, record):
        home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
        return Observer("rollout", home, True, "Codex's own rollout files under its home (observers/native.py codex_find_session)")
