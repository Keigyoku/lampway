"""Where each agent app keeps its MCP servers, read the way that app reads them. Nothing is written. A file above 8 MB or unparseable becomes a `problem` with FIXED text: a config file is never quoted,
because it may hold a secret. Files whose names look like credential stores are never opened."""
from __future__ import annotations

import json
import tomllib
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
_CRED = ("credentials", "auth.json", "tokens", "token.json", ".netrc")


def _read(path: Path, kind: str, problems: list):
    if any(w in path.name.lower() for w in _CRED):
        return None
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > MAX_BYTES:
            problems.append({"path": str(path), "message": "this configuration file is larger than 8 MB and was not read"})
            return None
        data = path.read_bytes()
        return tomllib.loads(data.decode("utf-8")) if kind == "toml" else json.loads(data.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        problems.append({"path": str(path), "message": "this configuration file could not be read as valid " + ("TOML" if kind == "toml" else "JSON") + "; it was skipped"})
        return None


def claude_home(home: Path, env: dict) -> Path:
    return Path(env["CLAUDE_CONFIG_DIR"]) if env.get("CLAUDE_CONFIG_DIR") else home / ".claude"


def codex_home(home: Path, env: dict) -> Path:
    return Path(env["CODEX_HOME"]) if env.get("CODEX_HOME") else home / ".codex"


def claude_settings(project: Path, home: Path, env: dict, problems: list) -> dict:
    """The approval keys across Claude's settings files (user, project, project-local): lists are unioned, the booleans OR-ed."""
    out = {"enableAllProjectMcpServers": False, "enabledMcpjsonServers": set(), "disabledMcpjsonServers": set(), "enabledPlugins": {}}
    for p in (claude_home(home, env) / "settings.json", project / ".claude" / "settings.json", project / ".claude" / "settings.local.json"):
        d = _read(p, "json", problems)
        if not isinstance(d, dict):
            continue
        out["enableAllProjectMcpServers"] |= bool(d.get("enableAllProjectMcpServers"))
        out["enabledMcpjsonServers"] |= set(d.get("enabledMcpjsonServers") or [])
        out["disabledMcpjsonServers"] |= set(d.get("disabledMcpjsonServers") or [])
        out["enabledPlugins"].update(d.get("enabledPlugins") or {})
    return out


def read_all(project: Path, home: Path, env: dict, problems: list) -> list:
    """Raw entries: {client, name, scope, path, raw, plugin}. Priority order is applied by the merge, not here."""
    out = []

    def add(client, scope, path, servers, plugin=None):
        for name, raw in (servers or {}).items():
            if isinstance(raw, dict):
                out.append({"client": client, "name": name, "scope": scope, "path": str(path), "raw": raw, "plugin": plugin})

    # --- Claude Code: global, local (per project), project, plugins
    cj = Path(env["CLAUDE_CONFIG_DIR"]) / ".claude.json" if env.get("CLAUDE_CONFIG_DIR") else home / ".claude.json"
    d = _read(cj, "json", problems)
    if isinstance(d, dict):
        add("claude", "global", cj, d.get("mcpServers"))
        add("claude", "local", cj, ((d.get("projects") or {}).get(str(project)) or {}).get("mcpServers"))              # only THIS project's entry: another project's servers are never read out
    pj = project / ".mcp.json"
    d = _read(pj, "json", problems)
    if isinstance(d, dict):
        add("claude", "project", pj, d.get("mcpServers"))
    inst = _read(claude_home(home, env) / "plugins" / "installed_plugins.json", "json", problems)
    for pid, entries in ((inst or {}).get("plugins") or {}).items() if isinstance(inst, dict) else []:
        for e in entries if isinstance(entries, list) else []:
            root = Path(str(e.get("installPath") or ""))
            m = _read(root / ".mcp.json", "json", problems)
            if isinstance(m, dict):
                add("claude", "plugin", root / ".mcp.json", m.get("mcpServers") or m, plugin=pid)
    # --- Codex: user and project config.toml (deep-merged by the merge), plugins are declared in config
    for scope, p in (("global", codex_home(home, env) / "config.toml"), ("project", project / ".codex" / "config.toml")):
        d = _read(p, "toml", problems)
        if isinstance(d, dict):
            add("codex", scope, p, d.get("mcp_servers"))
    # --- OpenCode [UNVERIFIED key layout: the `mcp` key of opencode.json], Cursor, Kimi, Claude Desktop, VS Code
    for scope, p in (("global", home / ".config" / "opencode" / "opencode.json"), ("project", project / "opencode.json")):
        d = _read(p, "json", problems)
        if isinstance(d, dict):
            add("opencode", scope, p, d.get("mcp"))
    for scope, p in (("global", home / ".cursor" / "mcp.json"), ("project", project / ".cursor" / "mcp.json")):
        d = _read(p, "json", problems)
        if isinstance(d, dict):
            add("cursor", scope, p, d.get("mcpServers"))
    d = _read(home / ".kimi" / "mcp.json", "json", problems)
    if isinstance(d, dict):
        add("kimi", "global", home / ".kimi" / "mcp.json", d.get("mcpServers"))
    cd = home / ".config" / "Claude" / "claude_desktop_config.json"
    d = _read(cd, "json", problems)
    if isinstance(d, dict):
        add("claude_desktop", "global", cd, d.get("mcpServers"))
    vs = project / ".vscode" / "mcp.json"
    d = _read(vs, "json", problems)
    if isinstance(d, dict):
        add("vscode", "project", vs, d.get("servers"))
    return out
