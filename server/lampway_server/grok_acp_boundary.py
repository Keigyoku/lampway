# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway's ACP boundary in front of a Grok worker's native agent (issue #11 P4-17, captain's ruling 2026-10-12).

Native Grok 1.0.50 applies an MCP server update by name before its policy filters it: a same-name HTTP/SSE entry replaces the
canonical STDIO ``lampway_pane`` in the session, the policy then refuses the hostile URL, and the canonical server is left
disabled (tests/qa/grok_worker_validation.py:700, reproduced natively; the owned policy files cannot pin a definition). This
boundary sits between the ACP client and ``grok agent --no-leader stdio``, newline-delimited JSON-RPC both ways, and refuses
before native Grok sees it any client request whose MCP server list names the canonical server (Grok's own name comparison:
case-insensitive, spaces as ``_``, a ``grok_com_`` prefix stripped) with another transport or another argv. Such a request is
answered with a JSON-RPC error and never forwarded, so the canonical server stays enabled. Everything else passes unchanged:
other names (the owned policy files decide those), the canonical argv itself (an environment-only update stays native).

Scope: an ACP-stdio client. Today's production worker pane runs the native TUI over its own leader socket, which this relay
does not sit on.

REMOVAL (when native Grok retains the canonical server itself): the CI watch in .github/workflows/byoa-worker-validation.yml
(tests/qa/grok_native_retention_watch.py) fails loudly the first time the ORIGINAL check at grok_worker_validation.py:700
passes against the pinned artifact. Then delete this module, ``grok_worker.acp_boundary_argv``,
tests/qa/grok_worker_boundary_validation.py, server/tests/test_grok_acp_boundary.py and the watch wrapper; run the two
original validator steps directly again. The original native check is then the gate for P4-17.
"""
import argparse
import json
import signal
import subprocess
import sys
import threading

CANONICAL_NAME = "lampway_pane"
REFUSED = -32010                                   # application error code for a boundary refusal (JSON-RPC server range)
SERVER_LISTS = {"_x.ai/session/update_mcp_servers", "session/new", "session/load", "session/resume"}


def _native_name(name) -> str:
    """Grok's comparison of an MCP server name (its embedded user guide: case-insensitive after spaces become ``_``, a
    ``grok_com_`` prefix on the runtime name stripped)."""
    text = str(name or "").strip().lower().replace(" ", "_")
    return text[len("grok_com_"):] if text.startswith("grok_com_") else text


def screen(message, command: str, args=()) -> str:
    """Why ``message`` (one parsed client->agent frame) must not reach native Grok, or "" when it may."""
    if not isinstance(message, dict) or message.get("method") not in SERVER_LISTS:
        return ""
    params = message.get("params")
    servers = params.get("mcpServers") if isinstance(params, dict) else None
    if not isinstance(servers, list):
        return ""
    for entry in servers:
        if not isinstance(entry, dict) or _native_name(entry.get("name")) != CANONICAL_NAME:
            continue
        transport = str(entry.get("type") or "stdio").lower()
        if transport != "stdio" or "url" in entry:
            return (f"Lampway refused this MCP update: it names the canonical {CANONICAL_NAME} with transport {transport!r}; "
                    f"the canonical server is Lampway's STDIO connector and stays enabled")
        if entry.get("command") != command or list(entry.get("args") or []) != list(args):
            return (f"Lampway refused this MCP update: it names the canonical {CANONICAL_NAME} with another argv; "
                    f"the canonical server keeps its own and stays enabled")
    return ""


def refusal(message, reason: str) -> dict:
    return {"jsonrpc": "2.0", "id": message.get("id"), "error": {"code": REFUSED, "message": reason,
                                                                  "data": {"refused_by": "lampway_acp_boundary"}}}


def relay(agent_argv, command: str, args=(), *, stdin=None, stdout=None) -> int:
    """Run the native agent and carry ACP lines both ways, screening the client's; returns the agent's exit status."""
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    child = subprocess.Popen(list(agent_argv), stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    lock = threading.Lock()

    def emit(raw: bytes) -> None:
        with lock:
            stdout.write(raw)
            stdout.flush()

    def from_agent() -> None:
        for raw in iter(child.stdout.readline, b""):
            emit(raw)

    reader = threading.Thread(target=from_agent, name="acp-boundary-agent", daemon=True)
    reader.start()
    forward = signal.signal(signal.SIGTERM, lambda *_: child.terminate())
    try:
        for raw in iter(stdin.readline, b""):
            try:
                message = json.loads(raw)
            except ValueError:
                message = None
            reason = screen(message, command, args)
            if reason:
                if message.get("id") is not None:                     # a notification gets no answer; it is still dropped
                    emit((json.dumps(refusal(message, reason)) + "\n").encode())
                continue
            try:
                child.stdin.write(raw)
                child.stdin.flush()
            except BrokenPipeError:
                break
    finally:
        try:
            child.stdin.close()
        except OSError:
            pass
        status = child.wait()
        reader.join()
        signal.signal(signal.SIGTERM, forward)
    return status


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--canonical-command", required=True, help="the canonical lampway_pane connector's executable")
    parser.add_argument("--canonical-arg", action="append", default=[], help="one argument of the canonical connector")
    parser.add_argument("agent", nargs=argparse.REMAINDER, help="-- then the native agent's argv")
    options = parser.parse_args(argv)
    agent = options.agent[1:] if options.agent[:1] == ["--"] else options.agent
    if not agent:
        parser.error("the native agent's argv is required after --")
    return relay(agent, options.canonical_command, options.canonical_arg)


if __name__ == "__main__":
    raise SystemExit(main())
