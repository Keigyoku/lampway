"""A minimal MCP client for the live check: initialize, notifications/initialized, tools/list (only when the server advertises tools), NEVER tools/call. No new dependency. Streamable HTTP over httpx
(redirects refused, no credential sent: the agent's private login is not Lampway's to reuse) and stdio over a child process whose process GROUP is terminated afterwards: only what this module started.
Only fixed strings leave: remote errors can echo authorization headers, URLs or command arguments."""
from __future__ import annotations

import json
import os
import select
import signal
import subprocess
import time

import httpx

CONNECT_S, LIST_S, TOTAL_S = 12.0, 10.0, 15.0
PROTOCOL = "2025-06-18"
SAFE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "USER", "SHELL")
_AUTH_WORDS = ("unauthorized", "forbidden", "oauth", "authenticat", "login", "bearer", "api key", "api-key", "token")


def _result(status, tools=None, more=False):
    return {"status": status, "tool_count": tools, "more_tools": more}


def _parse_http(resp: httpx.Response):
    ct = resp.headers.get("content-type", "")
    if "text/event-stream" in ct:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except ValueError:
                    continue
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def _http(url: str, transport=None) -> dict:
    deadline = time.monotonic() + TOTAL_S
    headers = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
    client = httpx.Client(transport=transport, follow_redirects=False, timeout=httpx.Timeout(LIST_S, connect=CONNECT_S))
    sid = None
    try:
        def post(body, need_reply=True):
            nonlocal sid
            h = dict(headers)
            if sid:
                h["mcp-session-id"] = sid
            r = client.post(url, json=body, headers=h)
            sid = r.headers.get("mcp-session-id", sid)
            return r

        r = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "lampway-mcp-check", "version": "1"}}})
        if 300 <= r.status_code < 400:
            return _result("unavailable")
        if r.status_code in (401, 403) or (r.status_code >= 400 and any(w in r.text.lower() for w in _AUTH_WORDS)):
            return _result("agent-auth")
        if r.status_code >= 400:
            return _result("unavailable")
        doc = _parse_http(r)
        res = (doc or {}).get("result")
        if not isinstance(res, dict):
            return _result("unavailable")
        post({"jsonrpc": "2.0", "method": "notifications/initialized"}, False)
        if "tools" not in (res.get("capabilities") or {}):
            return _result("available", None)
        if time.monotonic() > deadline:
            return _result("timeout")
        r = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        if r.status_code >= 400:
            return _result("agent-auth" if r.status_code in (401, 403) else "unavailable")
        lst = ((_parse_http(r) or {}).get("result") or {})
        tools = lst.get("tools")
        if not isinstance(tools, list):
            return _result("unavailable")
        return _result("available", len(tools), bool(lst.get("nextCursor")))
    except httpx.TimeoutException:
        return _result("timeout")
    except httpx.HTTPError:
        return _result("unavailable")
    finally:
        try:
            if sid:
                client.delete(url, headers={"mcp-session-id": sid})                  # close the session we opened
        except httpx.HTTPError:
            pass
        client.close()


def _stdio(argv, env, cwd) -> dict:
    deadline = time.monotonic() + TOTAL_S
    child_env = {k: os.environ[k] for k in SAFE_ENV if k in os.environ}
    child_env.update(env)
    try:
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=child_env, cwd=cwd or None, start_new_session=True, text=True, bufsize=1)
    except OSError:
        return _result("unavailable")
    try:
        def send(obj):
            p.stdin.write(json.dumps(obj) + "\n")
            p.stdin.flush()

        def read(rid):
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError
                ready, _w, _x = select.select([p.stdout], [], [], min(left, LIST_S))
                if not ready:
                    raise TimeoutError
                line = p.stdout.readline()
                if not line:
                    raise EOFError
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("id") == rid:
                    return msg

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "lampway-mcp-check", "version": "1"}}})
        res = read(1).get("result")
        if not isinstance(res, dict):
            return _result("unavailable")
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        if "tools" not in (res.get("capabilities") or {}):
            return _result("available", None)
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        lst = read(2).get("result") or {}
        tools = lst.get("tools")
        return _result("available", len(tools), bool(lst.get("nextCursor"))) if isinstance(tools, list) else _result("unavailable")
    except TimeoutError:
        return _result("timeout")
    except (EOFError, OSError, ValueError, BrokenPipeError):
        return _result("unavailable")
    finally:
        try:
            os.killpg(p.pid, signal.SIGTERM)                                         # the group THIS module started, never another pid
        except OSError:
            pass
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except OSError:
                pass
            p.wait()
        for f in (p.stdin, p.stdout):
            try:
                f.close()
            except OSError:
                pass


def probe(spec: dict, transport=None) -> dict:
    """spec: {transport, url | argv, env, cwd}. Returns {status, tool_count, more_tools} with only fixed status words."""
    if spec["transport"] in ("http", "sse"):
        from .. import egress as E
        with E.context(route="mcp_probe", kind="request"):
            return _http(spec["url"], transport)
    return _stdio(spec["argv"], spec.get("env") or {}, spec.get("cwd"))
