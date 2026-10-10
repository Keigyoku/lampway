# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine's Hermes config, from the user's capability choices (docs/reports/agent-modes-spec.md E1.3, E1.10, E2, A1).

Captain, 2026-10-06: "Nothing is removed; everything is chosen." Each Mode 1 pane (``hermes serve`` plus Hermes's own TUI, spec A1)
runs with ``HERMES_HOME=<state_dir>/agent/hermes/<unit>`` (a worker's under ``<unit>/workers/``); before it starts, Lampway writes
that home's ``config.yaml`` here:

* **The model is Lampway's gateway only** (E1.3, E1.4, E1.10): ``model.provider: custom`` with the gateway's loopback ``base_url``,
  the per-process token as ``api_key`` and the model id as ``default``; no other provider, no fallback chain, no ``auth.json``,
  and Hermes's adoption of other apps' logins (Codex CLI, Claude Code) switched off.
* **The serve platform's toolsets are exactly the Hermes toolsets of the capabilities in force** (``platform_toolsets.cli``: the
  key ``hermes serve`` and its TUI read, tui_gateway/server.py:1939 at the pin), plus ``clarify`` for a main agent (its questions
  are the island's, spec A2; a worker never asks, S2). Every other known Hermes toolset, and the client-surface toolsets serve
  folds in for a GUI, are named in ``agent.disabled_toolsets`` as well; memory, skill writing and the curator follow their
  capabilities. Lampway's own tools are the ONE config-declared MCP server, ``lampway`` (the unit's ``/engine/mcp/<unit>``, or a
  worker's pane endpoint, with its bearer), which no choice hides.
* **Every outbound check Hermes lets config switch off is off** (update checks, telemetry, the remote model catalog, the Nous guest
  bootstrap, lazy installs, language-server installs, the Nous tool gateway's connectors); models.dev, which has no off switch, is
  pointed at the gateway; approvals are the user's (``manual``), never a guardian model's. What config cannot switch off, the
  engine's egress proxy (E1.5) still refuses (measured 2026-10-07 on the pinned serve: zero external requests).
* **Context is Hermes's** (captain, Q3): compression, the context engine and tool search stay at Hermes's defaults unless the
  caller passes ``context``, which is written through (but can never reach the model route or a choice).

``check_advertised`` is E1.3's start-up check: given the tool list the model is sent (the gateway sees it in the first request),
it names every tool the choices do not allow, every deferred tool it cannot see, and every chosen tool Hermes did not offer.

The Hermes config keys and tool names are those of the pinned release (``PINNED_TAG``); the citations are ``file:line`` in its
source tree. A pin bump re-reads them; the live tests in ``tests/test_engine_hermes_config.py`` run the built engine against them.
"""

import threading
from functools import wraps

CONFIG_WRITER_LOCK = threading.RLock()

def serialized_config(fn):
    @wraps(fn)
    def guarded(*args, **kwargs):
        with CONFIG_WRITER_LOCK:
            return fn(*args, **kwargs)
    return guarded

import ipaddress
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional
from urllib.parse import urlsplit

from .. import capabilities as CAP

PINNED_TAG = "v2026.9.24"

#: Capability -> the Hermes toolsets it turns on (toolsets.py ``TOOLSETS`` at the pin, lines 77-256; the configurable ones are
#: hermes_cli/tools_config.py:53-82 ``CONFIGURABLE_TOOLSETS``). ``skills.write`` shares the ``skills`` toolset with ``skills.use``:
#: Hermes registers ``skill_manage`` in ``skills`` (tools/skill_manager_tool.py:927) and has no toolset with only the read tools,
#: so the config stages every skill write with native ``skills.write_approval``. Q8 keeps that review when writes are ON;
#: applying a pending write from the island additionally requires skills.write for the pane's bound project.
HERMES_TOOLSETS = {
    "files.project": ("file",),
    "terminal": ("terminal",),
    "code.execute": ("code_execution",),
    "web.search": ("web",),
    "web.browse": ("browser",),
    "vision": ("vision",),
    "memory": ("memory",),
    "history.search": ("session_search",),
    "skills.use": ("skills",),
    "skills.write": ("skills",),
    "subagents": ("delegation",),
    "schedule": ("cronjob",),
    "computer.use": ("computer_use",),
}

#: Catalogue rows with a ``hermes`` field that an ACP child's config cannot turn on, with why. They stay off in the child.
NOT_EXPRESSIBLE = {
    "messaging.*": "Hermes's messaging gateway is a separate process (`hermes gateway`), not a toolset of the ACP platform",
    "mcp.*": "MCP servers the user added arrive through Connections; the child's config declares none",
}

#: Hermes toolset -> its tool names at the pin (toolsets.py:12-41 ``_HERMES_CORE_TOOLS`` and :77-256 ``TOOLSETS``).
TOOLSET_TOOLS = {
    "file": ("read_file", "write_file", "patch", "search_files"),
    "terminal": ("terminal", "process_manage"),
    "code_execution": ("execute_code",),
    "web": ("web_search", "web_extract"),
    "browser": ("browser_navigate", "browser_snapshot", "browser_click", "browser_type", "browser_scroll", "browser_back",
                "browser_press", "browser_get_images", "browser_vision", "browser_console", "browser_cdp", "browser_dialog",
                "browser_vault_list", "browser_vault_unlock", "browser_vault_fill", "browser_vault_save_login",
                "browser_vault_enter_code", "browser_exec"),
    "vision": ("vision_analyze",),
    "memory": ("memory",),
    "session_search": ("session_search",),
    "skills": ("skills_list", "skill_view", "skill_manage"),
    "delegation": ("delegate_task",),
    "cronjob": ("cronjob_manage",),
    "computer_use": ("computer_use",),
}

#: Every toolset Hermes's configurator knows at the pin (tools_config.py:53-82, less ``stt``, which is a setting with no tools,
#: tools_config.py:99-100). Those not chosen go into ``agent.disabled_toolsets``, which Hermes subtracts last at tool
#: granularity (tools_config.py:622-629, model_tools.py:334-339), whatever a composite or a recovery step re-adds.
KNOWN_TOOLSETS = ("web", "browser", "terminal", "file", "code_execution", "vision", "video", "image_gen", "video_gen", "x_search",
                  "tts", "skills", "todo", "kanban", "memory", "context_engine", "session_search", "connections", "clarify",
                  "delegation", "cronjob", "homeassistant", "spotify", "discord", "discord_admin", "yuanbao", "computer_use")

#: The platform ``hermes serve`` resolves a session's toolsets on (tui_gateway/server.py:1939 ``_get_platform_tools(cfg, "cli")``).
PLATFORM = "cli"
#: The client-surface toolsets serve folds into a session whatever its config (tui_gateway/server.py:1842-1858, toolsets.py:74
#: ``CLIENT_SURFACE_TOOLSETS``): GUI-only, never Lampway's pane.
SURFACE_TOOLSETS = ("project", "desktop_ui")
#: The main agent's question tool (toolsets.py:159): its call reaches every attached client as a ``clarify`` server request, the
#: island's question (spec A2). Allowed for a main agent, never chosen, so its absence is no mismatch; a worker never asks (S2).
ASK_TOOLSET = "clarify"
ASK_TOOLS = ("clarify",)

#: Hermes's largest timeout before it clamps: agent/deadline.py:38 ``MAX_SAFE_TIMEOUT_S`` (one year), applied by
#: ``clamp_timeout`` at :111 to every ``timeouts.*`` value (``resolve_timeout``, :138-163). Lampway's MCP tools run Blender
#: scripts for up to 600 s and a swarm's collect waits for its workers, so the call timeout is that bound.
MCP_TOOL_CALL_TIMEOUT_S = 31_536_000

#: The tool_search bridge (tools/tool_search_catalog.py:18-21). Its tools reach only deferred tools, which its description lists.
BRIDGE_TOOLS = frozenset({"tool_search", "tool_describe", "tool_call"})

#: Roots ``context`` may write (captain, Q3: context is Hermes's), as paths into the config.
CONTEXT_PATHS = (("compression",), ("context",), ("prompt_caching",), ("tool_output",), ("context_file_max_chars",),
                 ("file_read_max_chars",), ("tools", "tool_search"), ("model", "context_length"))


class Refused(ValueError):
    pass


@dataclass(frozen=True)
class Mismatch:
    """One difference between the advertised tools and the choices. ``unexpected``: a tool the choices do not allow;
    ``unverifiable``: deferred tools the check cannot see; both refuse. ``missing``: a chosen tool Hermes did not offer (a
    tool whose own check failed, e.g. no search provider), reported but not refused."""
    kind: str
    tool: str
    why: str

    @property
    def blocking(self) -> bool:
        return self.kind != "missing"


# ---------------------------------------------------------------------------------------------------- the choices
def _in_force(capabilities, project, routes_on) -> set:
    return {c.id for c in CAP.CATALOGUE if "*" not in c.id and capabilities.effective(c.id, project, routes_on)[0]}


def _toolsets(in_force: set) -> list:
    return sorted({ts for cid in in_force for ts in HERMES_TOOLSETS.get(cid, ())})


def expected_tools(capabilities, project, routes_on: Optional[Callable] = None) -> frozenset:
    """The Hermes tool names the choices allow (Lampway's MCP tools aside)."""
    return frozenset(t for ts in _toolsets(_in_force(capabilities, project, routes_on)) for t in TOOLSET_TOOLS[ts])


def _loopback_url(url, what: str) -> str:
    parts = urlsplit(str(url or ""))
    host = parts.hostname or ""
    try:
        loop = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loop = False
    if parts.scheme not in ("http", "https") or not loop:
        raise Refused(f"refused: the engine's {what} must be on loopback (http://127.0.0.1:<port>/...), not {url!r}")
    return str(url)


def _merge_context(cfg: dict, context: Optional[dict]) -> None:
    if context is not None and not isinstance(context, dict):
        raise Refused("refused: context must be a mapping")
    from .context_settings import validate
    fields = {}
    for root, nested, field in (("compression", "threshold", "compression_threshold"),
                                ("compression", "protect_last_n", "protected_recent_turns"),
                                ("context", "engine", "context_engine")):
        if root in (context or {}):
            branch = context[root]
            if not isinstance(branch, dict):
                raise Refused(f"refused: context {root} must be a mapping")
            if nested in branch:
                fields[field] = branch[nested]
    validate(fields)
    for key, value in (context or {}).items():
        if key == "auxiliary":
            if not isinstance(value, dict) or set(value) != {"compression"}:
                raise Refused("refused: context auxiliary may edit only compression.model")
            compression = value["compression"]
            if not isinstance(compression, dict) or set(compression) != {"model"}:
                raise Refused("refused: context auxiliary may edit only compression.model")
            validate({"summarizing_model": compression["model"]}, allow_wire_alias=True)
            cfg.setdefault("auxiliary", {}).setdefault("compression", {})["model"] = compression["model"]
            continue
        branch = value if isinstance(value, dict) else None
        paths = [p for p in CONTEXT_PATHS if p[0] == key]
        if not paths:
            raise Refused(f"refused: context may set only Hermes's context settings ({_context_names()}), not {key!r}")
        if (key,) in paths:
            cfg[key] = _deep_merge(cfg.get(key), value)
            continue
        for sub, sub_value in (branch or {}).items():
            if (key, sub) not in paths:
                raise Refused(f"refused: context may set only Hermes's context settings ({_context_names()}), not {key}.{sub}")
            cfg.setdefault(key, {})[sub] = _deep_merge(cfg[key].get(sub), sub_value)
        if branch is None:
            raise Refused(f"refused: context {key!r} must be a mapping of {_context_names()}")


def _context_names() -> str:
    return ", ".join(".".join(p) for p in CONTEXT_PATHS)


def _deep_merge(base, override):
    if isinstance(base, dict) and isinstance(override, dict):
        out = dict(base)
        for k, v in override.items():
            out[k] = _deep_merge(out.get(k), v)
        return out
    return json.loads(json.dumps(override))   # a copy, and only what YAML can say


def render(capabilities, project, gateway_base_url, gateway_token, model_id, *, context: Optional[dict] = None,
           routes_on: Optional[Callable] = None, models_dev_url: Optional[str] = None,
           supports_vision: Optional[bool] = None, mcp_url: Optional[str] = None, mcp_headers: Optional[dict] = None,
           asks_user: bool = True, instructions: Optional[str] = None) -> dict:
    """The Mode 1 pane's ``config.yaml`` as a dict. ``capabilities`` is the board (``capabilities.Store``), ``project`` the
    project whose choices apply, ``routes_on`` the egress routes' state (default: the active egress manager). ``mcp_url`` and
    ``mcp_headers`` are Lampway's one MCP server for this pane (the unit's endpoint, or a worker's pane endpoint, with its bearer);
    ``asks_user`` is False for a swarm worker, which never asks (spec S2). ``instructions`` is Lampway's guidance on its tools
    (``agent/prompt.py``), written as Hermes's own ``agent.system_prompt``."""
    base_url = _loopback_url(gateway_base_url, "model gateway")
    if not gateway_token or not str(gateway_token).strip():
        raise Refused("refused: the engine needs its per-process gateway token")
    if not model_id or not str(model_id).strip():
        raise Refused("refused: the engine needs a model id")
    md_url = _loopback_url(models_dev_url, "models.dev mirror") if models_dev_url else base_url.rstrip("/") + "/models-dev.json"
    lampway_mcp = _loopback_url(mcp_url, "Lampway MCP endpoint") if mcp_url else None

    in_force = _in_force(capabilities, project, routes_on)
    toolsets = _toolsets(in_force) + ([ASK_TOOLSET] if asks_user else [])
    memory = "memory" in in_force
    skills_write = "skills.write" in in_force
    background = "background" in in_force

    cfg = {
        # hermes_cli/config_defaults.py:22-24; acp_adapter/session.py:472-510 reads model.default and model.provider and resolves
        # the custom endpoint from model.base_url / model.api_key (hermes_cli/runtime_provider.py).
        "model": {"provider": "custom", "base_url": base_url, "api_key": str(gateway_token), "default": str(model_id),
                  # agent/image_routing.py:133: Hermes sends attached images only to a model it knows sees them (R3); unknown -> unset
                  **({"supports_vision": bool(supports_vision)} if supports_vision is not None else {})},
        "providers": {},              # config_defaults.py:23: no named providers
        "fallback_providers": [],     # config_defaults.py:24: no fallback chain past the gateway
        # config_defaults.py:1718-1726: never borrow the Codex CLI or Claude Code logins (E1.10, B0).
        "auth": {"adopt_external_logins": False},
        # Q2: native ended history remains resumable. Hermes's default prune deletes it, and its automatic archive
        # can hide unended sessions. Lampway uses native ended-tip snapshot archive helpers for Q2 visibility.
        "sessions": {"auto_prune": False, "auto_archive": False},
        # tools_config.py:576-633 ``_get_platform_tools``: an explicit list of configurable keys is the whole set
        # (``_explicit_toolsets``, :506-521); serve reads the ``cli`` platform (tui_gateway/server.py:1939) with the
        # config-declared MCP servers included, so no ``no_mcp`` (:685-686): Lampway's own server is declared below.
        "platform_toolsets": {PLATFORM: toolsets},
        # tools_config.py:622-629 and model_tools.py:334-339: subtracted last, at tool granularity; the client-surface toolsets
        # serve folds in (tui_gateway/server.py:1842-1858) are subtracted the same way.
        "agent": {"disabled_toolsets": sorted((set(KNOWN_TOOLSETS) | set(SURFACE_TOOLSETS)) - set(toolsets))},
        # config_defaults.py:1289-1305, read by agent/agent_init.py:1259-1296: the built-in store and the user profile follow
        # ``memory``; no external memory provider.
        "memory": {"memory_enabled": memory, "user_profile_enabled": memory, "provider": ""},
        # Q8: even with skills.write ON, keep native staging and explicit human review in the pane or island.
        "skills": {"write_approval": True},
        # config_defaults.py:1475-1476: the curator rewrites agent-created skills in the background.
        "curator": {"enabled": skills_write and background},
        # Native background forks require their separate default-off Agent preference, even when memory/skill writes are on.
        "auxiliary": {"background_review": {"enabled": (memory or skills_write) and background}},
        # Read by Lampway's native-entry bootstrap, not a new Hermes toolset or model route.
        "lampway_features": {key: key in in_force for key in ("subagents", "schedule", "background")},
        # tools/mcp_tool_common.py:43-55 ``_resolve_tool_timeout`` reads ``timeouts.mcp.tool_call``; ACP-passed servers carry no
        # per-server timeout (acp_adapter/server.py:170-173).
        "timeouts": {"mcp": {"tool_call": MCP_TOOL_CALL_TIMEOUT_S}},
        # config_defaults.py:1996-1998: the Nous tool gateway's remote connectors.
        "tools": {"connectors": {"enabled": False}},
        # config_defaults.py:2314-2316: passive version and banner checks.
        "updates": {"check": False},
        # config_defaults.py:2297-2307: shared metrics, collection and sending (already off by default; pinned off).
        "telemetry": {"shared_metrics": {"enabled": False, "send": False}},
        # config_defaults.py:2008-2010 and hermes_cli/model_catalog.py:206-210: the remote model-catalog manifest.
        "model_catalog": {"enabled": False},
        # config_defaults.py:2036-2038 and agent/models_dev.py:254-258: models.dev has no off switch, only a mirror URL.
        "models_dev": {"url": md_url},
        # config_defaults.py:1765-1767 and tools/lazy_deps.py:325-337: lazy installs from PyPI.
        "security": {"allow_lazy_installs": False},
        # config_defaults.py:2373-2375: language-server installs through npm, go or pip.
        "lsp": {"install_strategy": "manual"},
        # config_defaults.py:2625: the Nous free-tier guest bootstrap (measured: serve installs boto3 and edge-tts for it).
        "nous": {"guest": False},
        # config_defaults.py:1642-1657: the default ``smart`` asks a guardian model; ``manual`` asks the user, in the pane and
        # the island (spec A2: an ``approval`` server request to every client, first answer wins).
        "approvals": {"mode": "manual"},
    }
    terminal = {"cwd": str(project)} if project else {}               # config_defaults.py:284: the agent's working directory (A1)
    if "terminal" in in_force:
        # config_defaults.py:277-278: the terminal backend is the capability's option (E2).
        chosen = (capabilities.setting("terminal", project).get("options") or {}).get("backend", "local")
        if chosen not in CAP.get("terminal").options:
            raise Refused(f"refused: the terminal backend is one of {', '.join(CAP.get('terminal').options)}, not {chosen!r}")
        terminal["backend"] = chosen
    if terminal:
        cfg["terminal"] = terminal
    if instructions and str(instructions).strip():
        # hermes_cli/personality.py:118-124 ``resolve_ephemeral_system_prompt``: ``agent.system_prompt`` (no personality is set),
        # read when serve builds a session (tui_gateway/server.py:2384) and appended to the system message of every model call
        # after Hermes's own prompt (agent/chat_completion_helpers.py:2175-2177). Lampway's guidance on its tools rides there:
        # no file in the user's project, Hermes's identity kept (measured 2026-10-07).
        cfg["agent"]["system_prompt"] = str(instructions)
    if lampway_mcp:
        # Lampway's tools (spec A3): the one MCP server this pane declares, reached on loopback with its own bearer. Hermes names
        # its tools mcp__lampway__<tool> and may defer them behind tool_search (measured 2026-10-07).
        cfg["mcp_servers"] = {"lampway": {"url": lampway_mcp, "headers": {str(k): str(v) for k, v in (mcp_headers or {}).items()}}}
    _merge_context(cfg, context)
    return cfg


# ---------------------------------------------------------------------------------------------------- YAML, by hand
_BARE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")
_YAML_WORDS = {"y", "n", "yes", "no", "true", "false", "on", "off", "null"}


def _scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return ".nan"
        if math.isinf(value):
            return ".inf" if value > 0 else "-.inf"
        text = repr(value)
        mant, _, exp = text.partition("e")
        if "." not in mant:
            mant += ".0"
        return mant + ("e" + (exp if exp[:1] in "+-" else "+" + exp) if exp else "")
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise Refused(f"refused: {type(value).__name__} cannot be written to the engine's config")


def _key(key) -> str:
    key = str(key)
    return key if _BARE_KEY.fullmatch(key) and key.lower() not in _YAML_WORDS else json.dumps(key, ensure_ascii=False)


def _flow(value) -> str:
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(str(k), ensure_ascii=False)}: {_flow(v)}" for k, v in value.items()) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_flow(v) for v in value) + "]"
    return _scalar(value)


def _lines(node, indent: int) -> Iterable[str]:
    pad = " " * indent
    for k, v in node.items():
        if isinstance(v, dict) and v:
            yield f"{pad}{_key(k)}:"
            yield from _lines(v, indent + 2)
        elif isinstance(v, (list, tuple)) and v:
            yield f"{pad}{_key(k)}:"
            for item in v:
                yield f"{pad}  - {_flow(item)}"
        else:
            yield f"{pad}{_key(k)}: {_flow(v)}"


def to_yaml(config: dict) -> str:
    """Deterministic block YAML (strings double-quoted as JSON, which YAML reads), so the server needs no YAML library."""
    return "# Written by Lampway from your Capabilities; edits here are replaced at the next start.\n" + "\n".join(_lines(config, 0)) + "\n"


_SPECIAL = {".nan": math.nan, ".inf": math.inf, "-.inf": -math.inf}


def _unflow(text: str):
    text = text.strip()
    if text in _SPECIAL:
        return _SPECIAL[text]
    return json.loads(text)


def from_yaml(text: str) -> dict:
    """The dict ``to_yaml`` wrote: Lampway reads back only its own file (block mappings two spaces deep, ``- `` items, every value
    in JSON's flow form), so no YAML library is needed; anything else is refused."""
    root: dict = {}
    stack = [(-1, root)]                                   # (indent, the mapping or list a deeper line goes into)
    pending = None                                         # (indent, parent, key): a ``key:`` whose value is the next, deeper block
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if pending is not None:
            p_indent, parent, key = pending
            pending = None
            if indent <= p_indent:
                raise Refused(f"refused: not Lampway's config (an empty block under {key!r})")
            parent[key] = [] if line.startswith("- ") else {}
            stack.append((p_indent, parent[key]))
        while stack and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]
        if line.startswith("- "):
            if not isinstance(container, list):
                raise Refused("refused: not Lampway's config (a list item outside a list)")
            container.append(_unflow(line[2:]))
            continue
        if not isinstance(container, dict):
            raise Refused("refused: not Lampway's config (a key inside a list)")
        if line.startswith('"'):
            end = json.JSONDecoder().raw_decode(line)[1]
            key, rest = json.loads(line[:end]), line[end:]
        else:
            key, sep, rest = line.partition(":")
            rest = sep + rest
        if not rest.startswith(":"):
            raise Refused(f"refused: not Lampway's config ({line[:40]!r})")
        value = rest[1:].strip()
        if value:
            container[key] = _unflow(value)
        else:
            pending = (indent, container, key)
    if pending is not None:
        raise Refused("refused: not Lampway's config (it ends inside a block)")
    return root


def read(home_dir) -> dict:
    """A pane's ``config.yaml``, as the dict it was rendered from (``from_yaml``)."""
    return from_yaml((Path(home_dir) / "config.yaml").read_text(encoding="utf-8"))


#: The home's dotenv file: ``hermes serve`` loads it at start, over what it inherited (hermes_cli/env_loader.py ``load_hermes_dotenv``,
#: override) and again on ``reload.env`` (hermes_cli/config.py ``reload_env``). Lampway writes only the toolset pin there.
ENV_FILE = ".env"
TOOLSETS_ENV = "HERMES_TUI_TOOLSETS"


def env_text(config: dict) -> str:
    """The pane's ``.env``: the toolset pin (``serve_toolsets``) and nothing else, no secret."""
    return f"{TOOLSETS_ENV}={','.join(serve_toolsets(config))}\n"


# ---------------------------------------------------------------------------------------------------- write
def _users_hermes_home() -> Path:
    return Path.home().expanduser().resolve() / ".hermes"


def serve_toolsets(config: dict) -> list:
    """The serve session's whole toolset list, for ``HERMES_TUI_TOOLSETS``: the chosen platform toolsets and Lampway's MCP server.
    Measured on the pinned serve (2026-10-07): it folds the client-surface toolset ``project`` (``desktop_project``) into every TUI
    session after ``agent.disabled_toolsets`` is applied, which the start-up check then refuses; an operator pin replaces that
    fold-in (tui_gateway/server.py:1906-1930 ``_load_enabled_toolsets``). The MCP server is named so its tools stay in."""
    return list(config["platform_toolsets"][PLATFORM]) + sorted(config.get("mcp_servers") or {})


@serialized_config
def write(home_dir, capabilities, project, gateway_base_url, gateway_token, model_id, *, rendered: Optional[dict] = None, **kw) -> Path:
    """Write ``<home_dir>/config.yaml`` (0600) in a 0700 home and return its path. Never the user's own Hermes (E1.10).
    ``rendered``, when given, receives the config as a dict (``serve_toolsets`` reads it)."""
    home = Path(home_dir).expanduser().resolve()
    theirs = _users_hermes_home()
    if home == theirs or theirs in home.parents:
        raise Refused(f"refused: {home} is the user's own Hermes home; Lampway's engine never reads or writes it (E1.10)")
    config = render(capabilities, project, gateway_base_url, gateway_token, model_id, **kw)
    if rendered is not None:
        rendered.update(config)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    home.chmod(0o700)
    path = _write_private(home, "config.yaml", to_yaml(config))
    _write_private(home, ENV_FILE, env_text(config))         # the toolset pin serve reloads live (spec E2)
    return path


def _write_private(home: Path, name: str, text: str) -> Path:
    path, tmp = home / name, home / f".{name.lstrip('.')}.lampway-tmp"
    try:
        tmp.unlink()
    except FileNotFoundError:
        pass
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise
    path.chmod(0o600)
    return path


# ---------------------------------------------------------------------------------------------------- the start-up check
_CATALOG_HEADER = "Deferred tool catalog"
_COUNT = re.compile(r"^Search (\d+) additional tools")
_GROUP = re.compile(r"^(\S+) tools \((\d+)\):$")
_SUMMARY = re.compile(r"^(\S+) \((\d+) tools — names not listed")
_UNAVAILABLE = re.compile(r"^\S+ \((?:\d+ )?tools unavailable")
_NAME = re.compile(r"[A-Za-z0-9_.-]+")


def _name(tool) -> str:
    if isinstance(tool, str):
        return tool
    fn = (tool or {}).get("function") if isinstance(tool, dict) else None
    return str((fn or tool or {}).get("name") or "") if isinstance(fn or tool, dict) else ""


def _parse_bridge(tools) -> tuple:
    """(readable, deferred count, names, {summarised group: count}) from the tool_search description, in the format of
    tools/tool_search.py:231-271 and tools/tool_search_catalog.py:261-318 at the pin."""
    desc = next((str(((t.get("function") or t) if isinstance(t, dict) else {}).get("description") or "")
                 for t in tools if _name(t) == "tool_search" and isinstance(t, dict)), None)
    if desc is None or _CATALOG_HEADER not in desc:
        return False, None, frozenset(), {}
    count = _COUNT.match(desc)
    names, groups, in_group = set(), {}, False
    for line in desc[desc.index(_CATALOG_HEADER):].splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        if _GROUP.match(line):
            in_group = True
        elif (m := _SUMMARY.match(line)):
            groups[m.group(1)] = int(m.group(2))
            in_group = False
        elif _UNAVAILABLE.match(line):
            in_group = False
        elif in_group and line.startswith("- "):
            names.add(line[2:].split(":", 1)[0].strip())
        elif in_group and all(_NAME.fullmatch(n.strip()) for n in line.split(",")):
            names.update(n.strip() for n in line.split(","))
        else:
            return False, None, frozenset(), {}
    return True, int(count.group(1)) if count else None, frozenset(names), groups


def deferred_listing(tools) -> tuple:
    """(deferred tool names, summarised groups) that Hermes's tool_search bridge lists in the tools the model is sent."""
    _, _, names, groups = _parse_bridge(list(tools))
    return names, frozenset(groups)


def check_advertised(tools, capabilities, project, *, mcp_servers=("lampway",), routes_on: Optional[Callable] = None,
                     asks_user: bool = True) -> list:
    """E1.3's start-up check. ``tools`` is the tool list the model is sent (OpenAI tool dicts, or bare names when no bridge is
    involved). Returns the mismatches; ``refuses(...)`` says whether the session must be refused. ``asks_user``: a main agent's
    ``clarify`` is allowed (never chosen, so never missing); a worker's is refused (spec S2)."""
    tools = list(tools)
    allowed = frozenset(expected_tools(capabilities, project, routes_on))
    asking = frozenset(ASK_TOOLS) if asks_user else frozenset()
    prefixes = tuple(f"mcp__{s}__" for s in mcp_servers)
    visible = [_name(t) for t in tools]
    out = []

    def judge(name: str, where: str) -> None:
        if name in allowed or name in asking or name.startswith(prefixes):
            return
        out.append(Mismatch("unexpected", name, f"{name} ({where}) is not allowed by the capabilities in force"))

    for name in visible:
        if name not in BRIDGE_TOOLS:
            judge(name, "offered")
    deferred = frozenset()
    if BRIDGE_TOOLS & set(visible):
        readable, count, deferred, groups = _parse_bridge(tools)
        listed = len(deferred) + sum(groups.values())
        if not readable or count is None or count != listed:
            out.append(Mismatch("unverifiable", "tool_search", "the tool_search bridge defers tools the check cannot list "
                                f"(listed {listed}, says {count})"))
        for name in sorted(deferred):
            judge(name, "deferred")
        for label in sorted(groups):
            if label not in mcp_servers:
                out.append(Mismatch("unverifiable", label, f"the deferred group {label!r} is summarised without its tool names"))
    for name in sorted(allowed - set(visible) - deferred):
        out.append(Mismatch("missing", name, f"{name} is chosen but Hermes did not offer it"))
    order = {"unexpected": 0, "unverifiable": 1, "missing": 2}
    return sorted(out, key=lambda m: (order[m.kind], m.tool))


def refuses(mismatches) -> bool:
    return any(m.blocking for m in mismatches)
