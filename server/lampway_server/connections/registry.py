# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The registry: specs/connections/CATALOGUE.md tables A, B and C as data, one ``Spec`` per row. It is the one place a service is described;
the hub, the routes, the agent tool, the poller and "where it is used" read it, and a service that is not here cannot be stored.

``uses`` is not written here: a consumer registers what it needs at import (``register_use``), so "where it is used" follows the code."""

from dataclasses import dataclass, field
from typing import Callable, Optional, Union

GROUPS = ("Agents", "Studios", "Video and images", "Compute", "Your tools", "System")
KINDS = ("api_key", "key_pair", "oauth", "host_login", "browser_session", "endpoint", "derived", "reference", "local_account", "none")


@dataclass(frozen=True)
class Check:
    """One free status check (CATALOGUE.md table C). ``kind``: http (one documented read through the egress hook), mcp (initialize +
    tools/list + an optional named free tool), cli (a status subcommand), local (presence, mode, expiry, loopback only), none."""
    kind: str
    method: str = "GET"
    url: str = ""
    reads: tuple = ()                     # every (method, url) the check may send: test 15 holds it to these
    tool: str = ""                        # mcp: the named free tool
    argv: tuple = ()                      # cli
    show: tuple = ()                      # the evidence fields the hub keeps (all others are dropped before storing)


@dataclass(frozen=True)
class Spec:
    id: str
    label: str
    group: str
    kind: str
    route: Optional[str]                  # egress.ROUTES id, or None (loopback / no network)
    fields: tuple = ()                    # the secret fields Lampway can hold, in order
    env: dict = field(default_factory=dict)        # field -> env var names holding the value (first set wins)
    file_env: dict = field(default_factory=dict)   # field -> env var names naming a file that holds it
    shape: str = ""                       # a prefix the "key" field must start with ("" = any)
    scheme: str = "bearer"                # bearer | x-api-key | key | modal | basic
    binary: tuple = ()                    # host CLIs: names on PATH or absolute paths ("~" expanded)
    paths: tuple = ()                     # host files whose existence and mode are shown (never opened)
    host_hint: str = ""                   # how the user signs in on the host ("codex login")
    logout_hint: str = ""                 # how to sign out of a host login ("codex logout")
    check: Check = Check("none")
    signin: bool = False
    derived_from: Optional[str] = None
    unused: bool = False                  # C10: kept, marked "no Lampway use yet"
    future: bool = False
    note: str = ""

    def child_env_names(self) -> dict:
        """field -> the ONE variable name a child process receives it under (the first name the code reads today)."""
        return {f: self.env[f][0] for f in self.fields if self.env.get(f)}


_OR_KEY = Check("http", "GET", "https://openrouter.ai/api/v1/key", (("GET", "https://openrouter.ai/api/v1/key"),),
                show=("label", "limit", "limit_remaining", "limit_reset", "usage", "is_free_tier"))
_FAL_PRICE = "https://api.fal.ai/v1/models/pricing?endpoint_id=fal-ai/flux/dev"


def _studio(sid, label, shape_name, route=None):
    """A Studio REST row from its request shape (studios/rest/shapes.py): the key variables and the balance read are the driver's own."""
    from ..studios.rest import shapes as SH
    shape = SH.STUDIOS[shape_name]
    if shape_name == "hi3d":
        fields = ("client_id", "client_secret")
        env = {"client_id": (shape.key_vars[0],), "client_secret": (shape.key_vars[1],)}
    else:
        fields, env = ("key",), {"key": tuple(shape.key_vars)}
    url = shape.base + shape.balance[1]
    reads = ((shape.balance[0], url),)
    if shape_name == "hi3d":
        reads = (("POST", shape.base + "/open-api/v1/auth/token"),) + reads          # the token exchange is how a Hi3D pair is read
    return Spec(sid, label, "Studios", "key_pair" if len(fields) > 1 else "api_key", route or sid, fields, env,
                {f: tuple(n + "_FILE" for n in env[f]) for f in fields}, scheme="basic" if shape_name == "hi3d" else "bearer",
                check=Check("http", shape.balance[0], url, reads, show=("balance",)))


SPECS = {s.id: s for s in (
    # ---------------------------------------------------------------------------------------------------------------------- Agents
    Spec("openrouter", "OpenRouter", "Agents", "api_key", "openrouter", ("key",), {"key": ("OPENROUTER_API_KEY",)},
         {"key": ("LAMPWAY_OPENROUTER_KEY_FILE",)}, shape="sk-or-", check=_OR_KEY),
    Spec("chatgpt_plan", "ChatGPT plan", "Agents", "oauth", "chatgpt_plan", signin=True, check=Check("local"),
         note="manage usage at chatgpt.com/settings/usage"),
    Spec("anthropic", "Anthropic API", "Agents", "api_key", "claude_plan", ("key",), {"key": ("ANTHROPIC_API_KEY",)}, shape="sk-ant-",
         scheme="x-api-key", check=Check("http", "GET", "https://api.anthropic.com/v1/models", (("GET", "https://api.anthropic.com/v1/models"),))),
    Spec("custom_llm", "OpenAI-compatible endpoint", "Agents", "endpoint", "custom_llm", ("key",), {"key": ("OPENAI_API_KEY",)},
         check=Check("http", "GET", "{base}/models", (("GET", "{base}/models"),))),
    Spec("claude_cli", "Claude Code CLI", "Agents", "host_login", "claude_plan", binary=("claude",), paths=("~/.claude/.credentials.json",),
         host_hint="claude auth login", logout_hint="claude auth logout"),
    Spec("codex_cli", "Codex CLI", "Agents", "host_login", "chatgpt_plan", binary=("codex",), paths=("~/.codex/auth.json",),
         host_hint="codex login", logout_hint="codex logout"),
    Spec("opencode_cli", "OpenCode CLI", "Agents", "host_login", None, binary=("opencode",), paths=("~/.local/share/opencode/auth.json",),
         host_hint="opencode auth login", logout_hint="opencode auth logout"),
    # --------------------------------------------------------------------------------------------------------------------- Studios
    _studio("studio:hyper3d", "Hyper3D (Rodin REST)", "hyper3d"),
    Spec("mcp:hyper3d", "Hyper3D (Rodin MCP)", "Studios", "oauth", "studio:hyper3d", signin=True,
         check=Check("mcp", "POST", "https://api.hyper3d.com/api/mcp", (("POST", "https://api.hyper3d.com/api/mcp"),)),
         note="the MCP has no balance tool: liveness only"),
    _studio("studio:meshy", "Meshy", "meshy"),
    _studio("studio:hi3d", "Hi3D", "hi3d"),
    _studio("studio:tripo_api", "Tripo API", "tripo", route="studio:tripo"),
    Spec("studio:tripo", "Tripo Studio (tool browser)", "Studios", "browser_session", "studio:tripo",
         paths=("~/.local/share/lampway/tool-browser/profile",), host_hint="Open the tool browser and sign in to Tripo there",
         check=Check("local", "GET", "http://127.0.0.1:9333/json/version")),
    Spec("mcp:3daistudio", "3D AI Studio", "Studios", "oauth", None, future=True),
    Spec("hunyuan", "Tencent Hunyuan 3D", "Studios", "key_pair", None, future=True),
    # ----------------------------------------------------------------------------------------------------------- Video and images
    Spec("higgsfield", "Higgsfield", "Video and images", "oauth", "higgsfield", signin=True, paths=("~/.config/higgsfield/credentials.json",),
         check=Check("mcp", "POST", "https://mcp.higgsfield.ai/mcp", (("POST", "https://mcp.higgsfield.ai/mcp"),), tool="balance",
                     show=("plan", "credits"))),
    Spec("heygen", "HeyGen video", "Video and images", "derived", "heygen", derived_from="openrouter"),
    Spec("fal", "fal", "Video and images", "api_key", "fal", ("key",), {"key": ("FAL_KEY", "FALAI_KEY")}, {"key": ("FAL_KEY_FILE",)}, scheme="key",
         check=Check("http", "GET", _FAL_PRICE, (("GET", _FAL_PRICE),))),
    # ------------------------------------------------------------------------------------------------------------------- Compute
    Spec("compute:modal", "Modal", "Compute", "key_pair", "compute:modal", ("token_id", "token_secret"),
         {"token_id": ("MODAL_TOKEN_ID",), "token_secret": ("MODAL_TOKEN_SECRET",)}, scheme="modal", binary=("modal",)),
    Spec("compute:runpod", "RunPod", "Compute", "api_key", "compute:runpod", ("key",), {"key": ("RUNPOD_API_KEY",)}, binary=("runpodctl",)),
    Spec("compute:boat", "Boat", "Compute", "host_login", "compute:boat", binary=("~/.ascii/bin/boat",), paths=("~/.config/ascii/boat/config.json",),
         host_hint="boat login", logout_hint="boat logout",
         check=Check("cli", argv=("status", "--json"), show=("plan", "health"))),
    # ---------------------------------------------------------------------------------------------------------------- Your tools
    Spec("github", "GitHub (gh)", "Your tools", "host_login", None, binary=("gh",), paths=("~/.config/gh/hosts.yml",),
         host_hint="gh auth login", logout_hint="gh auth logout", unused=True),
    Spec("huggingface", "Hugging Face", "Your tools", "api_key", "model_download", ("key",), {"key": ("HF_TOKEN",)},
         paths=("~/.cache/huggingface/token",), unused=True,
         check=Check("http", "GET", "https://huggingface.co/api/whoami-v2", (("GET", "https://huggingface.co/api/whoami-v2"),))),
    Spec("mcp_clients", "Your agents' MCP servers", "Your tools", "reference", "mcp_probe", note="see the MCP inventory; Lampway never uses their credentials"),
    # -------------------------------------------------------------------------------------------------------------------- System
    Spec("lampway_server", "Lampway server account", "System", "local_account", None, check=Check("local")),
    Spec("byok_legacy", "BYOK store (legacy)", "System", "reference", None, note="stored by the BYOK form; no provider reads it"),
    Spec("download:wezterm", "WezTerm download", "System", "none", None, note="needs no credential: only its route matters"),
    Spec("download:local_models", "Local model downloads", "System", "none", None, note="needs no credential; runs in the client, outside the egress hook"),
)}


class UnknownConnection(KeyError):
    def __str__(self):
        return self.args[0]


def get(cid: str) -> Spec:
    spec = SPECS.get(cid)
    if spec is None:
        raise UnknownConnection(f"no connection {cid}: the connections are {', '.join(sorted(SPECS))}")
    return spec


# --------------------------------------------------------------------------------------------------------------------- uses
Resolver = Union[str, Callable[[], Optional[str]]]
_USES: dict = {}


def register_use(use_id: str, connection: Resolver, label: str = "") -> None:
    """A consumer declares what it needs: ``connection`` is an id, or a callable that answers the id for the current setting."""
    if isinstance(connection, str):
        get(connection)
    _USES[use_id] = (connection, label or use_id)


CONSUMERS = ("lampway_server.imagegen", "lampway_server.studios.actions")     # the modules that register their uses at import


def _load() -> None:
    import importlib
    for m in CONSUMERS:
        importlib.import_module(m)


def connection_for(use_id: str) -> Optional[str]:
    _load()
    entry = _USES.get(use_id)
    if entry is None:
        return None
    conn = entry[0]
    return conn() if callable(conn) else conn


def uses_of(cid: str) -> list:
    _load()
    out = []
    for use_id, (conn, label) in sorted(_USES.items()):
        try:
            now = conn() if callable(conn) else conn
        except Exception:  # noqa: BLE001 - a resolver that fails names nothing
            now = None
        if now == cid:
            out.append({"id": use_id, "label": label})
    return out


def known_uses() -> list:
    _load()
    return sorted(_USES)
