# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Claude Code (`claude`): the user's own Claude Code, on its own login, in a pane on Lampway's herdr server.

New session: `--session-id <uuid>` chosen by Lampway (recorded as the native id); resume: `--resume <id>`. Effort: `--effort`.
Bypass (the user's tick only): `--dangerously-skip-permissions`. Lampway's tools: a per-pane `--mcp-config <file>`. Verified on an
installed Claude Code 2.1.293 (see FACTS).
"""
import json
import os

from ..observers.native import claude_transcript
from .base import Adapter, LoginState, Observer, SERVER_NAME, ToolWiring, _first_line, bearer_headers, direct_binding, mcp_entry


class Claude(Adapter):
    id = "claude"
    label = "Claude Code"
    binary = "claude"
    herdr_kind = "claude"
    install_hint = "install Claude Code (claude) from Anthropic: npm install -g @anthropic-ai/claude-code"
    status_argv = ("auth", "status")
    api_key_connections = ("anthropic",)
    picks_session_id = True
    BYPASS = ("--dangerously-skip-permissions",)
    task_flag = ()                            # `claude [prompt]`: the interactive session starts with it
    direct_ok = True                          # an mcpServers entry {"type": "http", "url", "headers"} (Claude Code's documented shape)
    worker_ok = True                          # --strict-mcp-config: offline global/project/plugin exclusion proved on 2.1.293
    interrupt_keys = ("esc",)
    takes_image_paths = True
    FACTS = {
        "version": "2.1.293 installed with npm (@anthropic-ai/claude-code) into a scratch prefix; `claude --version` -> '2.1.293 (Claude Code)'",
        "argv": "`claude --help` (2.1.293): `[prompt]`, `--session-id <uuid>`, `-r, --resume [value]`, `--effort <level>` (low, medium, "
                "high, xhigh, max), `--dangerously-skip-permissions`, `--mcp-config <configs...>` (variadic: the task goes before it)",
        "status": "`claude auth status` prints JSON with `loggedIn` (2.1.293); read from that field, the exit status as a fallback",
        "session_file": "`claude auth status` names `projectsDirectory` = <config dir>/projects; the transcript is <projects>/<cwd, "
                        "every non-alphanumeric as '-'>/<session id>.jsonl (observers/native.py claude_transcript)",
        "turn_end": "every main-chain assistant record carries its message's stop_reason ('tool_use' on each block of a tool-using "
                    "message, 'end_turn' on each block of the last one), never null: record shapes counted in a Claude Code 2.1.292 "
                    "transcript on this machine (no content read); the mirror ends a turn on 'end_turn' with a text block",
        "interrupt": "Esc: herdr 0.9.3's pinned detection manifest (src/detect/manifests/claude.toml) reads a running turn by "
                     "'esc to interrupt' on Claude Code's own screen. [UNVERIFIED on the installed copy: a turn needs an account]",
        "images": "a pasted image path is attached (Claude Code's documented 'give Claude an image path'). [UNVERIFIED on the "
                  "installed copy: a turn needs an account]",
        "mcp_entry": "the stdio entry {command, args, env} and the http entry {type: http, url, headers} are Claude Code's documented "
                     "mcpServers shape. Stdio initialize/tools/list verified with synthetic offline sentinels on 2.1.293. "
                     "[UNVERIFIED: account-backed HTTP tool execution]",
        "worker_mcp": "Claude Code 2.1.293 offline synthetic startup: global, project and plugin stdio sentinels initialized and "
                      "listed tools with --mcp-config; adding --strict-mcp-config initialized/listed only the supplied worker. "
                      "Native tools and the plugin stayed loaded; synthetic persona/auth files and user MCP entries were preserved. "
                      "AF_INET/AF_INET6 sockets were denied by seccomp; no account/model acceptance was tested",
    }

    def _require_worker_config(self, pane):
        if not pane.desktop and (not pane.mcp_config_path or len(pane.direct) != 1 or pane.direct[0].name != SERVER_NAME):
            raise ValueError("Claude worker requires its owned MCP config with exactly one lampway server")

    def _args(self, pane, resume_id):
        self._require_worker_config(pane)
        a = ["--resume", resume_id] if resume_id else (["--session-id", pane.session_id] if pane.session_id else [])
        a += self._bypass(pane)
        if pane.effort:
            a += ["--effort", pane.effort]
        return a

    def read_status(self, code, out):
        try:
            data = json.loads(out)
        except ValueError:
            return super().read_status(code, out)
        if isinstance(data, dict) and isinstance(data.get("loggedIn"), bool):
            how = str(data.get("authMethod") or "")
            return LoginState("signed_in" if data["loggedIn"] else "signed_out", f"Claude Code: {'signed in' if data['loggedIn'] else 'not signed in'}"
                              + (f" ({how})" if how and data["loggedIn"] else ""))
        return LoginState("signed_in" if code == 0 else "signed_out", _first_line(out))

    def lampway_tools(self, pane):
        self._require_worker_config(pane)
        path = pane.mcp_config_path
        servers = {SERVER_NAME: mcp_entry(pane)} if pane.desktop else {}
        for d in pane.direct:                 # spec S3: Lampway's own endpoint, the bearer in this 0600 file only
            servers[d.name] = {"type": "http", "url": d.url, "headers": bearer_headers(d)}
        body = json.dumps({"mcpServers": servers}, indent=2)
        argv = (("--strict-mcp-config",) if not pane.desktop else ()) + ("--mcp-config", path) if path else ()
        return ToolWiring("mcp_config_file", argv, {}, {path: body} if path else {}, tuple(pane.launcher),
                          pane.scene_session_id or direct_binding(pane), True,
                          "--strict-mcp-config confines this worker to its supplied MCP config (Claude Code 2.1.293 offline sentinel "
                          "connections); native tools, persona and login remain native" if not pane.desktop else
                          "--mcp-config <file> adds this pane's own server entry (Claude Code 2.1.293's --help); the user's own user-scope "
                          "entries are left alone")

    def observe(self, record):
        if not record.get("native_id"):
            return Observer("screen", None, True, "no session id recorded: the pane's screen")
        return Observer("session_file", claude_transcript(record.get("cwd") or "", record["native_id"], os.environ.get("CLAUDE_CONFIG_DIR")), True,
                        "Claude Code's own transcript (observers/native.py)")
