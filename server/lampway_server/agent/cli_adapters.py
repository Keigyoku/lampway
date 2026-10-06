"""Local CLI adapters: a provider and an image backend that call the OFFICIAL `codex` and `claude` binaries the owner is
already logged into on this machine. For the owner's personal use.

No token is read, copied or stored by this code: it never opens ``~/.codex/auth.json``, ``~/.claude/.credentials.json`` or any
keychain; it only starts the binaries (which use their own login) and reads what they print or write for us. OFF by default:
enable with ``LAMPWAY_LOCAL_CLI=1`` or ``{"enabled": true}`` in ``<state>/local_cli.json``.

TERMS CAVEAT (read before enabling, and before shipping this as a feature for anyone else):

* Codex / ChatGPT: for personal local use this is the user running OpenAI's own client. Offering it to other people is a grey
  area under OpenAI's terms (the supported way to use a ChatGPT plan in a third-party app is Sign in with ChatGPT: the
  chatgpt_plan provider).
* Claude: Anthropic's legal page (code.claude.com/docs/en/legal-and-compliance) says: "Anthropic does not permit third-party
  developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, or Max plan
  credentials on behalf of their users." and "developers may not collect, store, or intermediate Claude.ai credentials or
  session tokens". Running the unmodified `claude` binary yourself, for yourself, is the user using Claude Code; building it
  into a product that routes other people's requests through their plans is exactly what that clause forbids. The anthropic
  provider (API key) is the compliant way to ship Claude.
"""

import asyncio
import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from .providers.base import Message, ModelRequest, ProviderEvent, Text, ToolCall

TERMS_NOTE = (
    "Local CLI adapters call the official `codex` / `claude` binaries you are logged into, for your personal use. "
    "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route "
    "requests through Free, Pro, or Max plan credentials on behalf of their users (code.claude.com/docs/en/legal-and-compliance); "
    "shipping this for others is not compliant. OpenAI: personal local use only; offering it to others is a grey area (use the "
    "chatgpt_plan provider)."
)


class CLIError(RuntimeError):
    pass


def enabled(state_dir) -> bool:
    """Off unless exactly LAMPWAY_LOCAL_CLI=1 or <state>/local_cli.json says {"enabled": true}."""
    env = os.environ.get("LAMPWAY_LOCAL_CLI")
    if env is not None:
        return env == "1"
    try:
        return json.loads((Path(state_dir) / "local_cli.json").read_text(encoding="utf-8")).get("enabled") is True
    except (OSError, ValueError):
        return False


def require_enabled(state_dir) -> None:
    if not enabled(state_dir):
        raise ValueError("the local CLI adapters are off. For your own personal use on this machine only, set LAMPWAY_LOCAL_CLI=1 "
                         "(or write {\"enabled\": true} to " + str(Path(state_dir) / "local_cli.json") + "). " + TERMS_NOTE)


# ------------------------------------------------------------------ the prompt and its answer
def build_prompt(request: ModelRequest) -> str:
    parts = [request.system.strip(), ""]
    if request.tools:
        parts += ["You can call these tools. To call one, finish your reply with exactly one line:",
                  'TOOL_CALL {"name": "<tool>", "arguments": {...}}', "and nothing after it. Otherwise answer normally.", "Tools:"]
        for t in request.tools:
            parts.append(f"- {t.name}: {t.description} parameters: {json.dumps(t.parameters, separators=(',', ':'))}")
        parts.append("")
    parts.append("Conversation:")
    names = {}
    for m in request.messages:
        if m.role == "assistant":
            if m.text():
                parts.append(f"ASSISTANT: {m.text()}")
            for p in m.content:
                if p.get("type") == "tool_call":
                    names[p["id"]] = p["name"]
                    parts.append(f"ASSISTANT TOOL_CALL {json.dumps({'name': p['name'], 'arguments': p.get('arguments') or {}})}")
        else:
            for p in m.content:
                if p.get("type") == "tool_result":
                    parts.append(f"TOOL_RESULT ({names.get(p['tool_call_id'], '?')}): {p.get('content', '')}")
                elif p.get("type") == "text":
                    parts.append(f"USER: {p['text']}")
    parts.append("ASSISTANT:")
    return "\n".join(parts)


def parse_answer(text: str, tools) -> list:
    """Text and at most one tool call: a last line `TOOL_CALL {...}` naming a tool we offered."""
    known = {t.name for t in tools}
    lines = text.rstrip().splitlines()
    events: list = []
    if lines and lines[-1].strip().startswith("TOOL_CALL"):
        raw = lines[-1].strip()[len("TOOL_CALL"):].strip()
        body = "\n".join(lines[:-1]).strip()
        try:
            call = json.loads(raw)
            name, args = call["name"], call.get("arguments") or {}
            if not isinstance(args, dict):
                raise ValueError("arguments must be an object")
        except (ValueError, KeyError, TypeError):
            return [Text(text)]
        if body:
            events.append(Text(body + "\n" if False else body))
        if name not in known:
            events.append(Text(f"\n(unknown tool {name!r} requested; ignored)"))
            return events
        events.append(ToolCall(id=f"cli_{uuid.uuid4().hex[:12]}", name=name, arguments=args))
        return events
    return [Text(text.strip())] if text.strip() else []


# ------------------------------------------------------------------ running a binary
CLI_ROUTES = {"claude": "claude_plan", "codex": "chatgpt_plan"}


async def _run(cmd: list, prompt: str, timeout: float, env=None, cwd=None):
    from .. import egress as EG
    with EG.guard(CLI_ROUTES.get(Path(cmd[0]).name, "custom_llm"), kind="text", nbytes=len(prompt)):                 # the CLI talks to its own provider: gated and logged where Lampway launches it
        return await _run_gated(cmd, prompt, timeout, env, cwd)


async def _run_gated(cmd: list, prompt: str, timeout: float, env=None, cwd=None):
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE, env=env, cwd=cwd)
    except FileNotFoundError as exc:
        raise CLIError(f"{cmd[0]} not found: install it and log in once yourself") from exc
    try:
        out, err = await asyncio.wait_for(proc.communicate(prompt.encode("utf-8")), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise CLIError(f"{Path(cmd[0]).name} timed out after {timeout:.0f} s and was killed")
    if proc.returncode != 0:
        tail = (err or out).decode("utf-8", "replace").strip()[-400:]
        raise CLIError(f"{Path(cmd[0]).name} exited {proc.returncode}: {tail}")
    return out.decode("utf-8", "replace")


class CodexCLIProvider:
    name = "codex_cli"

    def __init__(self, binary: str = "codex", model: str = "", timeout: float = 900.0):
        self.binary, self.model, self.timeout = binary, model, timeout

    async def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        with tempfile.TemporaryDirectory(prefix="lampway-codex-") as tmp:
            outfile = Path(tmp) / "last.txt"
            cmd = [self.binary, "exec", "--skip-git-repo-check", "--ephemeral", "-s", "read-only", "--color", "never",
                   "-C", tmp, "-o", str(outfile)] + (["-m", self.model] if self.model else []) + ["-"]
            await _run(cmd, build_prompt(request), self.timeout)
            answer = outfile.read_text(encoding="utf-8") if outfile.exists() else ""
        for event in parse_answer(answer, request.tools):
            yield event


class ClaudeCLIProvider:
    name = "claude_cli"

    def __init__(self, binary: str = "claude", model: str = "", timeout: float = 900.0, workdir=None):
        self.binary, self.model, self.timeout = binary, model, timeout
        # an empty directory of its own: no CLAUDE.md / .claude of wherever the server runs is picked up
        self.cwd = Path(workdir or Path(tempfile.gettempdir()) / "lampway") / "claude_cli_cwd"

    async def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        # --tools "" : a plain model, not Claude Code's agent; no --bare (that would skip the subscription login).
        # --setting-sources "" + --strict-mcp-config: none of the owner's settings, hooks or MCP servers load into a worker
        # (measured 2026-10-05: claude 2.1.288 answers headless on the owner's own login with these, model claude-sonnet-5-5).
        cmd = [self.binary, "-p", "--output-format", "text", "--no-session-persistence", "--tools", "",
               "--setting-sources", "", "--strict-mcp-config"] + (["--model", self.model] if self.model else [])
        self.cwd.mkdir(parents=True, exist_ok=True)
        answer = await _run(cmd, build_prompt(request), self.timeout, cwd=str(self.cwd))
        for event in parse_answer(answer, request.tools):
            yield event


# ------------------------------------------------------------------ image generation through codex ($imagegen)
def codex_image(binary: str, prompt: str, refs, out_dir, name: str, timeout: float = 900.0) -> dict:
    """One image through `codex exec '$imagegen'` on the owner's ChatGPT login (measured: works with -i references). The
    returned bytes are copied untouched into ``<out_dir>/<name>.png`` with a manifest of what was asked and what came back."""
    import subprocess
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    gen_dir = home / "generated_images"
    refs = [Path(r) for r in refs]
    full = (f"$imagegen Generate exactly ONE image and nothing else. {prompt} Do not post-process, resize or crop it. "
            "When done, print the absolute path of the generated file on the last line.")
    cmd = [binary, "exec", "--skip-git-repo-check", "-C", str(out)] + [x for r in refs for x in ("-i", str(r))] + ["--", full]
    start = time.time() - 1
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise CLIError(f"{binary} not found: install codex and log in once yourself") from exc
    except subprocess.TimeoutExpired as exc:
        raise CLIError(f"codex timed out after {timeout:.0f} s") from exc
    log = out / f"{name}.codex.log"
    log.write_text((p.stdout or "") + (p.stderr or ""), encoding="utf-8")
    fresh = [f for f in gen_dir.rglob("*.png") if f.stat().st_mtime >= start] if gen_dir.exists() else []
    if not fresh:
        raise CLIError(f"codex produced no image (rc {p.returncode}); see {log}")
    gen = max(fresh, key=lambda f: f.stat().st_mtime)
    dest = out / f"{name}.png"
    shutil.copyfile(gen, dest)
    data = dest.read_bytes()
    sha = lambda b: hashlib.sha256(b).hexdigest()
    manifest = {"role": "generated image candidate", "provider": "OpenAI", "method": "codex exec built-in image_gen ($imagegen)",
                "model_version": None, "seed": None, "cost": None, "file": dest.name, "raw_sha256": sha(data), "bytes": len(data),
                "codex_generated_path": str(gen), "prompt": prompt, "references": {r.name: sha(r.read_bytes()) for r in refs}}
    (out / f"{name}.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return {"file": str(dest), "manifest": str(out / f"{name}.json"), "sha256": manifest["raw_sha256"]}
