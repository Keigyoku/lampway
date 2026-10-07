# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pi (`pi`, the Pi coding agent, @earendil-works/pi-coding-agent): the user's own Pi, in a Lampway pane.

Pi 1.x has MCP built in (`docs/mcp.md` in the installed package), but reads servers only from the user's `~/.pi/agent/mcp.json` and
the project's trust-gated `.pi/mcp.json`, neither of which is Lampway's to write. So a bound pane reaches Lampway through
Lampway's own Pi extension (``lampway_pi_extension.js`` beside this module), a wrapper only: Pi loads it with `-e <path>`, it reads
this pane's own 0600 config (named by ``LAMPWAY_PI_MCP``) and hands its entries to Pi's own MCP client with
`pi.registerMcpServer` for this session only. Pi then connects to Lampway's launcher (pinned to the tab by LAMPWAY_BOUND_SESSION)
and to the swarm entry (the pane's bearer in the same file), as a Claude Code pane does.

New session: `--session-id <id>` chosen by Lampway (recorded as the native id); resume: `--session <id>`. No bypass flag: Pi asks
no permission. Observation: its own session file (observers/mirror.py PiMirror). Verified on an installed Pi 1.0.4 (see FACTS).
"""
import json
import os
from pathlib import Path

from .base import Adapter, Observer, SERVER_NAME, ToolWiring, bearer_headers, direct_binding, mcp_entry

#: Lampway's Pi extension, by path (shipped as package data beside this module).
EXTENSION = Path(__file__).resolve().with_name("lampway_pi_extension.js")
#: The variable the extension reads this pane's own MCP config from.
MCP_ENV = "LAMPWAY_PI_MCP"


def sessions_dir() -> str:
    """Pi's session store: PI_CODING_AGENT_SESSION_DIR, else <PI_CODING_AGENT_DIR or ~/.pi/agent>/sessions (Pi's
    docs/environment-variables.md). A `sessionDir` setting in the user's own Pi settings is not read (Lampway never reads them):
    with one, the pane's file is not found and the island shows its screen."""
    explicit = os.environ.get("PI_CODING_AGENT_SESSION_DIR")
    if explicit:
        return explicit
    return str(Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi" / "agent") / "sessions")


class Pi(Adapter):
    id = "pi"
    label = "Pi"
    binary = "pi"
    herdr_kind = "pi"
    install_hint = "install Pi (pi): npm install -g @earendil-works/pi-coding-agent"
    status_argv = None                         # `pi auth check` needs a --provider or --model: no account-wide status command
    picks_session_id = True
    task_flag = ()                             # `pi [messages...]`: the first prompt
    direct_ok = True                           # an http entry {url, headers} through the extension
    interrupt_keys = ("esc",)
    takes_image_paths = True
    FACTS = {
        "version": "1.0.4 installed with npm (@earendil-works/pi-coding-agent; the older @mariozechner/pi-coding-agent is deprecated "
                   "in its favour) into a scratch prefix; `pi --version` -> '1.0.4'",
        "argv": "`pi --help` (1.0.4): `[messages...]`, `--session <path|id>`, `--session-id <id>` (exact id, created if missing), "
                "`-e, --extension <path>`; no permission flag (Pi has no permission prompt)",
        "status": "`pi auth check` requires --provider or --model (`pi auth --help`, 1.0.4): no status command is run",
        "mcp": "Pi 1.0.4 has MCP built in (docs/mcp.md): ~/.pi/agent/mcp.json and the trust-gated .pi/mcp.json only; extensions add "
               "servers with pi.registerMcpServer (docs/extensions.md)",
        "extension": "`pi --mode rpc -e lampway_pi_extension.js` with LAMPWAY_PI_MCP naming a pane config (throwaway HOME, no provider, "
                     "PI_OFFLINE=1) answered `/mcp` with 'lampway: connected, 1 tools (direct)', and the stand-in server saw "
                     "LAMPWAY_BOUND_SESSION",
        "session_file": "`get_state` over RPC (1.0.4) names the file: <sessions dir>/--<cwd without its leading '/', '/' -> '-'>--/"
                        "<ISO time, ':' and '.' -> '-'>_<session id>.jsonl; its records are docs/session-format.md's",
        "herdr": "herdr 0.9.3 starts it itself: `agent start <name> --kind pi --pane <p> -- <args>` ran Pi 1.0.4 to 'idle' (live)",
        "interrupt": "Esc: `app.interrupt` = escape (docs/keybindings.md, 1.0.4)",
        "images": "Pi's `read` tool reads supported images (docs/cli.md, 1.0.4): the image's path in the prompt",
    }

    def _args(self, pane, resume_id):
        if resume_id:
            return ["--session", resume_id]
        return ["--session-id", pane.session_id] if pane.session_id else []

    def lampway_tools(self, pane):
        path = pane.mcp_config_path
        servers = {SERVER_NAME: mcp_entry(pane)} if pane.desktop else {}
        for d in pane.direct:                  # spec S3: the bearer in this 0600 file only
            servers[d.name] = {"url": d.url, "headers": bearer_headers(d)}
        body = json.dumps({"mcpServers": servers}, indent=2)
        return ToolWiring("extension", ("-e", str(EXTENSION)) if path else (), {MCP_ENV: path} if path else {}, {path: body} if path else {},
                          tuple(pane.launcher), pane.scene_session_id or direct_binding(pane), True,
                          "Lampway's Pi extension (-e) hands this pane's own MCP entries to Pi's MCP client for this session only "
                          "(checked on Pi 1.0.4); the user's ~/.pi/agent/mcp.json and the project's .pi/mcp.json are left alone")

    def observe(self, record):
        if not record.get("native_id"):
            return Observer("screen", None, True, "no session id recorded: the pane's screen")
        return Observer("pi_session", sessions_dir(), True, "Pi's own session file (observers/native.py pi_find_session)")
