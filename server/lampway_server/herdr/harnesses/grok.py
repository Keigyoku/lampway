# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Grok (Grok Build, `grok`): the user's own Grok CLI, in a Lampway pane.

New session uses --session-id; resume uses --resume. Only the user's bypass tick adds --always-approve.
MAIN uses an explicitly installed native symbolic stdio connector and a pane-owned binding file. The user's own agent,
HOME, model settings, permissions and other MCP servers remain native. Workers are refused: exclusive discovery preserving
all native policy/configuration is unproved. Observation is the screen. Checked with installed Grok 1.0.46 (see FACTS).
"""
import json
from pathlib import Path
import sys

from .base import Adapter, Observer, ToolWiring, bearer_headers, direct_binding
from ...pane_mcp import CONFIG_ENV, ROOT_ENV


class Grok(Adapter):
    id = "grok"
    label = "Grok"
    binary = "grok"
    herdr_kind = "grok"
    install_hint = "install Grok Build's CLI (grok) with xAI's own installer (its Grok CLI page)"
    status_argv = None                         # grok has `login` and `logout`, no status command
    picks_session_id = True
    BYPASS = ("--always-approve",)
    task_flag = ()                             # `grok [PROMPT]`: the interactive session starts with it
    interrupt_keys = ("ctrl+c",)
    takes_image_paths = True
    always_pane_config = True
    tools_reachable = True
    direct_ok = True
    worker_ok = False
    worker_note = ("Grok workers need an exclusive MCP route preserving native configuration and policies. "
                   "That route is unproved; choose another supported worker harness.")
    tools_note = ("Install lampway_pane once with your own Grok MCP command using lampway-pane-mcp. Lampway supplies only "
                  "a pane-owned binding file; your native agent, HOME, providers, permissions and other configured MCP "
                  "servers remain unchanged. Grok workers are unavailable until exclusive MCP discovery preserving "
                  "native policies is proved. Account-backed native tool execution remains unverified.")
    FACTS = {
        "version": "1.0.46 installed with xAI's own install script into a throwaway HOME; `grok --version` -> "
                   "'grok 1.0.46 (2765805b9442)'",
        "argv": "`grok --help` (1.0.46): `[PROMPT]`, `-s, --session-id <SESSION_ID>` (a new conversation's UUID), `-r, --resume "
                "[<SESSION_ID_OR_TITLE>]`, `--always-approve`, `--agent <path>`",
        "status": "no status command (`login`, `logout` only)",
        "mcp": "`grok mcp add --help` and docs/user-guide/07-mcp-servers.md (installed with 1.0.46): user and project config.toml, "
               ".mcp.json and compat sources; GROK_CONFIG_PATH and GROK_CONFIG naming a pane file left `grok mcp list` empty (checked)",
        "primary_agent": "network-denied synthetic first turn on 1.0.46 activated --agent <absolute.md> when mcpServers was a YAML "
                         "sequence of singleton mappings; the earlier mapping-shaped fixture was invalid. The custom body and "
                         "inline stdio server were observed without an account or provider call",
        "mcp_scope": "the same offline fixture retained the inherited desktop server despite enabled: false; a complete same-name "
                     "inline entry replaced it, but an unrelated inherited sentinel still initialized and listed tools. "
                     "mcpInheritance: none did not exclude primary-agent disk sources. Inline env placeholders arrived literally; "
                     "omitting the inline env mapping preserved the inherited process binding. This does not prove HTTP headers "
                     "or an exclusive worker route (scratch receipt grok-primary-route-supported-receipt.json)",
        "symbolic_connector": "Grok 1.0.46's supported `grok mcp add lampway_pane -- <absolute lampway-pane-mcp>` installs "
                              "a dedicated stdio connector. Lampway never runs that command against a user's configuration: "
                              "the user installs it explicitly. MAIN supplies only a pane-owned version-1 file and connector "
                              "config/root environment variables; no --agent override or HOME/provider/model/policy change. "
                              "Offline native add using the interpreter and helper path succeeded. Native ACP _x.ai/mcp/call "
                              "returned two synthetic scene bindings through live rebind; native TUI first-turn discovery "
                              "preserved the original custom persona. Warmed native config/auth/agent hashes stayed equal. "
                              "Account-backed native TUI tool execution remains unverified.",
        "native_bootstrap": "An identical no-connector native ACP baseline also deleted synthetic home managed policy cache "
                            "and inserted marketplace.default_skills_installs_purged. Ordinary TUI baseline deleted synthetic "
                            "requirements and managed caches. Native bootstrap owns that behavior; Lampway never reads, "
                            "copies or writes native configuration/policies. File immutability is not promised.",
        "primary_empty_body": "Installed 1.0.46 offline baseline saved the configured custom persona; adding an empty-body "
                              "--agent file replaced it with the default prompt. Therefore MAIN uses no --agent overlay.",
        "worker_policy": "Native requirements.toml allow_managed_mcp_servers_only and allowed_mcp_servers restricted synthetic "
                         "discovery, but relocating GROK_HOME changes native configuration. A preserving-home extra policy "
                         "namespace could not be tested here: bwrap returned 'setting up uid map: Read-only file system'. "
                         "herdr 0.9.3 also fixes the canonical executable for each kind and has no executable override; a "
                         "namespace wrapper additionally needs a reviewed native launch seam. No workaround or shared "
                         "native policy change is used; workers are explicitly refused.",
        "herdr": "herdr 0.9.3 knows the kind `grok` (src/detect/mod.rs interactive_agent_executable)",
        "interrupt": "Ctrl+C: docs/user-guide/03-keyboard-shortcuts.md (1.0.46) 'Esc ... never cancels a running turn (Ctrl+C does)'; "
                     "herdr 0.9.3's grok.toml still names an older 'Esc:cancel' footer",
        "images": "an image dragged into the prompt (a pasted path) becomes an image chip (docs/user-guide/03-keyboard-shortcuts.md, "
                  "1.0.46). [UNVERIFIED by a turn: needs an account]",
        "session_file": "~/.grok/sessions/<url-encoded cwd>/<session id>/updates.jsonl, an ACP session-update stream (docs/user-guide/"
                        "17-sessions.md, 1.0.46); not mirrored yet: the island shows the screen",
    }

    def _main_only(self, pane):
        if not pane.desktop:
            if not self.worker_ok:
                raise ValueError(self.worker_note)
            binding = direct_binding(pane) or ""
            if (not pane.mcp_config_path or len(pane.direct) != 1 or pane.direct[0].name != "lampway"
                    or pane.launcher or not binding.startswith("swarm:")
                    or (pane.scene_session_id and pane.scene_session_id != binding)):
                raise ValueError("Grok worker requires one owned direct-only swarm MCP binding")

    def worker_compatibility_note(self):
        from ...native_worker_readiness import grok_worker_note
        return grok_worker_note(self.locate())

    def launch(self, pane, task=None):
        if pane.desktop:
            return super().launch(pane, task)
        self._main_only(pane)
        if not isinstance(task, str) or not task or "\0" in task:
            raise ValueError("Grok worker requires a nonempty literal task")
        if pane.bypass:
            raise ValueError("Grok worker boundary does not support an approval bypass")
        return [self.binary, *self.lampway_tools(pane).argv, "--task=" + task]

    def resume(self, native_id, pane):
        if not pane.desktop:
            raise ValueError("Grok worker boundary supports new worker tasks only")
        return super().resume(native_id, pane)

    def _args(self, pane, resume_id):
        self._main_only(pane)
        if resume_id:
            return ["--resume", resume_id, *self._bypass(pane)]
        return (["--session-id", pane.session_id] if pane.session_id else []) + self._bypass(pane)

    def lampway_tools(self, pane):
        self._main_only(pane)
        path = pane.mcp_config_path
        binding = pane.scene_session_id or direct_binding(pane) or ""
        desktop = ({"command": pane.launcher[0], "args": list(pane.launcher[1:]),
                    "env": {"LAMPWAY_BOUND_SESSION": binding}}
                   if binding and pane.desktop and pane.launcher else None)
        direct = [{"url": entry.url, "headers": bearer_headers(entry)} for entry in pane.direct] if binding else []
        body = json.dumps({"version": 1, "binding": binding, "desktop": desktop, "direct": direct}, indent=2)
        env = {CONFIG_ENV: path, ROOT_ENV: str(Path(path).parent.parent.parent)} if path else {}
        files = {path: body} if path else {}
        argv = ()
        if not pane.desktop:
            from ...native_worker_readiness import grok_worker_description
            metadata = Path(path).with_name("grok-worker.json")
            description = grok_worker_description(self.locate(), cwd=pane.cwd)
            description.update(version=1, root=env[ROOT_ENV], cwd=pane.cwd,
                               inner_socket=str(metadata.with_name("grok-inner.sock")),
                               outer_socket=str(metadata.with_name("grok-outer.sock")))
            files[str(metadata)] = json.dumps(description, indent=2)
            argv = ("--leader-socket", description["outer_socket"], "wrap", "--", sys.executable,
                    "-m", "lampway_server.grok_worker", "--config", str(metadata))
        return ToolWiring("symbolic_stdio", argv, env, files, tuple(pane.launcher), binding or None, False, self.tools_note)

    def observe(self, record):
        return Observer("screen", None, True, "the pane's screen (Grok's updates.jsonl is an ACP stream Lampway does not mirror yet)")
