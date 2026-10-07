# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""OpenCode (`opencode`): the user's own OpenCode, on its own login, in a Lampway pane.

Resume: `--session <id>`. Bypass (the user's tick only): `--auto`. Lampway's tools: this pane's own config file named by
`OPENCODE_CONFIG` (the project's opencode.json, which every pane in the project would share and which is the user's own file, is
left alone). Verified on an installed OpenCode 1.18.35 (see FACTS).
"""
import json
import re

from .base import BOUND_ENV, SERVER_NAME, Adapter, LoginState, Observer, ToolWiring, bearer_headers, direct_binding

#: OpenCode stops listing a server's tools after 5 s by default; the launcher may first have to start Lampway (the Client's setup).
TOOLS_TIMEOUT_MS = 60_000
_CREDENTIALS = re.compile(r"(\d+)\s+credentials?\b")


class OpenCode(Adapter):
    id = "opencode"
    label = "OpenCode"
    binary = "opencode"
    config_name = "opencode.json"
    herdr_kind = "opencode"
    install_hint = "install OpenCode (opencode): npm install -g opencode-ai"
    status_argv = ("auth", "list")
    BYPASS = ("--auto",)
    task_flag = ("--prompt",)
    direct_ok = True                                                                   # a "remote" entry: url, headers
    interrupt_keys = ("esc", "esc")
    takes_image_paths = True
    FACTS = {
        "version": "1.18.35 installed with npm (opencode-ai) into a scratch prefix; `opencode --version` -> '1.18.35'",
        "argv": "`opencode --help` (1.18.35): `-s, --session <id>`, `--prompt <text>`, `--auto` (auto-approve permissions)",
        "status": "`opencode auth list` in a signed-out HOME prints '0 credentials' and exits 0 (1.18.35): the count is the signal",
        "mcp_config": "with OPENCODE_CONFIG naming this pane's file, `opencode mcp list` (1.18.35, no login) connected the `local` entry "
                      "(a stand-in server saw LAMPWAY_BOUND_SESSION) and parsed the `remote` entry with its headers",
        "interrupt": "Esc twice: the 1.18.35 binary's default keybind is session_interrupt 'escape', and its first press only arms "
                     "it ('esc again to interrupt', also in herdr 0.9.3's opencode.toml manifest)",
        "images": "OpenCode attaches a pasted image path. [UNVERIFIED on the installed copy: a turn needs an account]",
        "session_file": "sessions are in OpenCode's own database under its data dir (`opencode debug paths`): the island shows the screen",
    }

    def _args(self, pane, resume_id):
        return (["--session", resume_id] if resume_id else []) + self._bypass(pane)

    def read_status(self, code, out):
        m = _CREDENTIALS.search(out or "")
        if code == 0 and m:
            n = int(m.group(1))
            return LoginState("signed_in" if n else "signed_out", f"OpenCode: {n} credential{'s' if n != 1 else ''}")
        return super().read_status(code, out)

    def lampway_tools(self, pane):
        cmd = list(pane.launcher) or ["lampway-mcp"]
        servers = {SERVER_NAME: {"type": "local", "command": cmd, "enabled": True, "timeout": TOOLS_TIMEOUT_MS,
                                 "environment": {BOUND_ENV: pane.scene_session_id or ""}}} if pane.desktop else {}
        for d in pane.direct:                                                          # spec S3: the bearer in this 0600 file only
            servers[d.name] = {"type": "remote", "url": d.url, "enabled": True, "timeout": TOOLS_TIMEOUT_MS, "headers": bearer_headers(d)}
        body = json.dumps({"$schema": "https://opencode.ai/config.json", "mcp": servers}, indent=2)
        path = pane.mcp_config_path
        return ToolWiring("mcp_config_file", (), {"OPENCODE_CONFIG": path} if path else {}, {path: body} if path else {}, tuple(pane.launcher),
                          pane.scene_session_id or direct_binding(pane), True,
                          "OPENCODE_CONFIG names this pane's own config file (checked with `opencode mcp list`, 1.18.35); the project's "
                          "opencode.json is left alone")

    def observe(self, record):
        return Observer("screen", None, True, "OpenCode keeps its sessions in its own database, not a file Lampway reads: the pane's screen")
