# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lampway's ACP boundary in front of a Grok worker's native agent (issue #11 P4-17, captain's ruling 2026-10-12).

Native Grok 1.0.50 applies an MCP server update by name before its policy filters it: a same-name HTTP/SSE entry replaces the
canonical STDIO ``lampway_pane`` in the session, the policy then refuses the hostile URL, and the canonical server is left
disabled (tests/qa/grok_worker_validation.py:700, reproduced natively; the owned policy files cannot pin a definition). This
boundary sits between the ACP client and ``grok agent --no-leader stdio``, newline-delimited JSON-RPC both ways, and refuses
before native Grok sees it any client request whose MCP server list names the canonical server (Grok's own name comparison,
from the binary's embedded user guide, "Restrict which MCP servers can run": case-insensitive after spaces become ``_``, a
``grok_com_`` prefix stripped) with another transport or another argv. Such a request is refused whole, its other entries
with it, answered with a JSON-RPC error and never forwarded, so the canonical server stays enabled. It fails closed: a server
list that is not a list, a batch holding such a request, a line it cannot parse and duplicate keys are not forwarded either.
A request that does not name the canonical server differently passes byte for byte: other names (the owned policy files
decide those), the canonical argv itself (an environment-only update stays native).

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
import os
import signal
import subprocess
import sys
import threading

CANONICAL_NAME = "lampway_pane"
REFUSED = -32010                                   # application error code for a boundary refusal (JSON-RPC server range)


def _native_name(name) -> str:
    """Grok's comparison of an MCP server name (its embedded user guide: case-insensitive after spaces become ``_``, a
    ``grok_com_`` prefix on the runtime name stripped)."""
    text = str(name or "").strip().lower().replace(" ", "_")
    return text[len("grok_com_"):] if text.startswith("grok_com_") else text


def screen(message, command: str, args=()) -> str:
    """Why ``message`` (one parsed client->agent frame) must not reach native Grok, or "" when it may. Any request carrying an
    ``mcpServers`` parameter is screened, whatever its method."""
    if isinstance(message, list):                                            # a batch: refused whole when any member is
        return next((reason for member in message if (reason := screen(member, command, args))), "")
    params = message.get("params") if isinstance(message, dict) else None
    if not isinstance(params, dict) or "mcpServers" not in params:
        return ""
    servers = params["mcpServers"]
    if not isinstance(servers, list):
        return "Lampway refused this MCP update: its server list is not a list, so it cannot be checked"
    for entry in servers:
        if not isinstance(entry, dict):
            return "Lampway refused this MCP update: a server entry is not an object, so it cannot be checked"
        if _native_name(entry.get("name")) != CANONICAL_NAME:
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


def _no_duplicates(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate keys")                                   # native's resolution is not Python's to guess
    return dict(pairs)


def parse(raw: bytes):
    """The client frame, or None when it cannot be read exactly (not UTF-8, not JSON, duplicate keys): not forwarded."""
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, ValueError):
        return None


def relay(agent_argv, command: str, args=(), *, stdin=None, stdout=None) -> int:
    """Run the native agent and carry ACP lines both ways, screening the client's; returns the agent's exit status. The relay
    ends with its agent: the client's EOF closes the agent's stdin, the agent's exit (or a SIGTERM, passed on to it) ends the
    relay and closes its stdout."""
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

    def from_client() -> None:
        try:
            for raw in iter(stdin.readline, b""):
                message = parse(raw)
                if message is None:
                    print("lampway acp boundary: an unreadable client frame was not forwarded", file=sys.stderr, flush=True)
                    continue
                reason = screen(message, command, args)
                if reason:
                    for member in (message if isinstance(message, list) else [message]):
                        if isinstance(member, dict) and member.get("id") is not None:   # a notification is dropped unanswered
                            emit((json.dumps(refusal(member, reason)) + "\n").encode())
                    continue
                child.stdin.write(raw)
                child.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            pass                                                            # the agent is gone; its exit ends the relay
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass

    reader = threading.Thread(target=from_agent, name="acp-boundary-agent", daemon=True)
    writer = threading.Thread(target=from_client, name="acp-boundary-client", daemon=True)
    main = threading.current_thread() is threading.main_thread()           # only the process's main thread owns signals
    forward = signal.signal(signal.SIGTERM, lambda *_: child.terminate()) if main else None
    try:
        reader.start()
        writer.start()
        status = child.wait()
        reader.join()
    finally:
        if main:
            signal.signal(signal.SIGTERM, forward)
        with lock:
            try:
                stdout.flush()                                              # the process ends with the relay: the client's EOF
            except (OSError, ValueError):
                pass
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


def _exit(status: int) -> None:
    """Leave without interpreter finalization: the client-side reader may still block in stdin.readline holding its buffer's
    lock, which finalization would abort on. An agent ended by a signal N exits as 128+N, the shell's convention."""
    sys.stdout.flush()
    os._exit(128 - status if status < 0 else status)


if __name__ == "__main__":
    _exit(main())
