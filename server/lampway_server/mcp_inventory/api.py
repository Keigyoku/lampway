"""The inventory and the live check. Precedence is each app's own: Claude local > project > global (no deep merge); Codex project over user, deep-merged. readiness precedence disabled > managed > missing-env >
missing-command > approval > configured. Endpoints are reduced to their origin: no URL path, query, userinfo, header value, env value or command argument is ever returned. The probe result is bound to a
fingerprint of everything that would change what it connects to and goes stale after five minutes. Managed-policy locations are [UNVERIFIED] on Linux and are not assumed: nothing is ever reported `managed`
until they are measured on a real box."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Optional

from . import probe as PR
from . import sources as SRC

STALE_S = 300.0
LEGACY = "mixar"
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_CACHE: dict = {}
_SLOTS = threading.BoundedSemaphore(2)
SCOPE_ORDER = {"local": 0, "project": 1, "plugin": 2, "global": 3}


class InventoryError(ValueError):
    pass


def _dotenv(project: Path) -> dict:
    out = {}
    try:
        for line in (project / ".env").read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip("'\"")
    except OSError:
        pass
    return out


def _expand(value, lookup, missing: set):
    if not isinstance(value, str):
        return value

    def sub(m):
        v = lookup(m.group(1))
        if v in (None, ""):
            v = m.group(2) if m.group(2) is not None else ""
        if v == "":
            missing.add(m.group(1))
        return v
    return _VAR.sub(sub, value)


def _deep(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _deep(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def _origin(url: str) -> Optional[str]:
    p = urllib.parse.urlsplit(url)
    if not p.scheme or not p.hostname:
        return None
    return f"{p.scheme}://{p.hostname}" + (f":{p.port}" if p.port else "")


def _spec(raw: dict, lookup, project: Path, env_path: str):
    """(internal spec with real values, public facts). The internal spec never leaves this module."""
    missing: set = set()
    cmd = raw.get("command")
    args = list(raw.get("args") or [])
    if isinstance(cmd, list):                                                 # OpenCode: command is the whole argv
        cmd, args = (cmd[0] if cmd else None), list(cmd[1:])
    url = raw.get("url")
    kind = str(raw.get("type") or "").lower()
    transport = "stdio" if cmd and not url else ("sse" if kind == "sse" else "http") if url else "stdio"
    env = {k: _expand(v, lookup, missing) for k, v in (raw.get("env") or raw.get("environment") or {}).items()}
    headers = raw.get("headers") or raw.get("http_headers") or {}
    expanded_headers = {k: _expand(v, lookup, missing) for k, v in headers.items()}
    bearer = raw.get("bearer_token_env_var")
    if bearer and not lookup(bearer):
        missing.add(bearer)
    for name in raw.get("env_vars") or []:
        if not lookup(name):
            missing.add(name)
    cmd = _expand(cmd, lookup, missing) if cmd else None
    args = [_expand(a, lookup, missing) for a in args]
    url = _expand(url, lookup, missing) if url else None
    exe_ok = True
    if transport == "stdio":
        exe_ok = bool(cmd) and (Path(cmd).is_file() and os.access(cmd, os.X_OK) if os.path.isabs(cmd) else shutil.which(cmd, path=env_path) is not None)
    return ({"transport": transport, "argv": ([cmd] + args) if cmd else [], "url": url, "env": env, "cwd": str(project), "headers": expanded_headers, "flags": sorted(k for k in raw if k not in ("command", "args", "env", "url", "headers", "type"))},
            {"transport": transport, "endpoint": _origin(url) if url else None, "executable": os.path.basename(cmd) if cmd else None, "missing_env": sorted(missing),
             "credential_names": sorted(set(headers) | ({bearer} if bearer else set())), "exe_ok": exe_ok, "disabled": raw.get("enabled") is False or raw.get("disabled") is True,
             "launcher": cmd or (_origin(url) if url else None)})


def inventory(project, home, env=None, client="all", scope="all", eligibility: Optional[Callable] = None, tools_offered: Optional[Callable] = None, clock=time.time) -> dict:
    project, home, env = Path(project), Path(home), dict(env if env is not None else os.environ)
    problems: list = []
    entries = SRC.read_all(project, home, env, problems)
    settings = SRC.claude_settings(project, home, env, problems)
    dotenv = _dotenv(project)
    lookup = lambda k: dotenv.get(k) or env.get(k)                           # noqa: E731  (.env first, then the process environment)
    path = env.get("PATH", "")
    groups: dict = {}
    for e in entries:
        groups.setdefault((e["client"], e["name"], e.get("plugin")), []).append(e)
    servers = []
    for (cl, name, plugin), group in groups.items():
        if cl == "codex":                                                     # project over user, deep-merged
            group = sorted(group, key=lambda g: 0 if g["scope"] == "project" else 1)
            merged = {}
            for g in reversed(group):
                merged = _deep(merged, g["raw"])
            raw = merged
        else:
            group = sorted(group, key=lambda g: SCOPE_ORDER.get(g["scope"], 9))
            raw = group[0]["raw"]
        eff = group[0]
        spec, facts = _spec(raw, lookup, project, path)
        enabled, approved = not facts["disabled"], True
        if cl == "claude" and eff["scope"] == "project":
            if name in settings["disabledMcpjsonServers"]:
                enabled = False
            approved = settings["enableAllProjectMcpServers"] or name in settings["enabledMcpjsonServers"]
        if cl == "claude" and eff["scope"] == "plugin":
            enabled = enabled and bool(settings["enabledPlugins"].get(plugin))
        readiness = ("disabled" if not enabled else "missing-env" if facts["missing_env"] else "missing-command" if not facts["exe_ok"] else "approval" if not approved else "configured")
        sid = f"{cl}:{plugin + ':' if plugin else ''}{name}"
        fp = hashlib.sha256(json.dumps({"spec": spec, "approved": approved, "enabled": enabled}, sort_keys=True, default=str).encode()).hexdigest()
        conn = None
        c = _CACHE.get((str(project), sid))
        if c and c["fp"] == fp:
            conn = {"status": c["status"], "tool_count": c["tool_count"], "more_tools": c["more_tools"], "checked_at": c["at"], "stale": clock() - c["at"] > STALE_S}
        servers.append({"id": sid, "name": name, "client": cl, "scope": eff["scope"], "enabled": enabled, "readiness": readiness, "transport": facts["transport"], "endpoint": facts["endpoint"],
                        "executable": facts["executable"], "plugin": plugin, "sources": [{"scope": g["scope"], "path": g["path"], "effective": i == 0} for i, g in enumerate(group)],
                        "missing_env": facts["missing_env"], "credential_names": facts["credential_names"], "can_check": readiness == "configured", "connection": conn,
                        "_spec": spec, "_fp": fp, "_launcher": facts["launcher"], "_exe_ok": facts["exe_ok"]})
    servers.sort(key=lambda s: (s["client"], s["name"]))
    notes = []
    row = {"launcher": None, "launcher_ok": False, "opted_in": False, "eligible": False, "eligibility_detail": "", "tools_offered": 0, "notes": notes}
    lamp = next((s for s in servers if s["name"] == "lampway"), None)
    if lamp:
        row.update(launcher=lamp["_launcher"], launcher_ok=lamp["_exe_ok"], opted_in=lamp["enabled"])
    if any(s["name"] == LEGACY for s in servers):
        notes.append("an entry left from the upstream app points at the old name: replace with lampway (click Add)")
    if eligibility:
        ok, detail = eligibility()
        row.update(eligible=bool(ok), eligibility_detail=str(detail))
    if tools_offered:
        row["tools_offered"] = int(tools_offered())
    keep = [s for s in servers if client in ("all", s["client"]) and scope in ("all", s["scope"])]
    public = [{k: v for k, v in s.items() if not k.startswith("_")} for s in keep]
    inventory._last = {s["id"]: s for s in servers}                          # for check(): the same scan, with the internal specs
    return {"scanned_at": clock(), "project": str(project), "servers": public, "problems": problems, "lampway": row}


def check(project, home, sid: str, env=None, clock=time.time, transport=None) -> dict:
    inv = inventory(project, home, env=env, clock=clock)
    srv = inventory._last.get(sid)
    if srv is None:
        raise InventoryError("MCP configuration was not found: refresh the list")
    if not srv["can_check"]:
        raise InventoryError(f"{sid} cannot be checked: it is {srv['readiness']} (disabled, managed by its host, awaiting approval, or needing configuration): fix that first")
    if not _SLOTS.acquire(blocking=False):
        raise InventoryError("Two connection checks are running: wait for one to finish")
    try:
        res = PR.probe(srv["_spec"], transport) if transport else PR.probe(srv["_spec"])
    finally:
        _SLOTS.release()
    at = clock()
    _CACHE[(str(project), sid)] = {"fp": srv["_fp"], "status": res["status"], "tool_count": res["tool_count"], "more_tools": res["more_tools"], "at": at}
    return {"id": sid, "connection": {"status": res["status"], "tool_count": res["tool_count"], "more_tools": res["more_tools"], "checked_at": at, "stale": False}}
