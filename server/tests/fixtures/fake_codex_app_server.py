"""A fake `codex app-server` speaking the JSON lines the provider uses. SCENARIO (env) picks the behaviour; every message received is appended to LOG (env)."""
import json
import os
import sys
import time

SCENARIO = os.environ.get("SCENARIO", "two_tools")
LOG = os.environ.get("LOG", "/dev/null")


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def log(obj):
    with open(LOG, "a") as fh:
        fh.write(json.dumps(obj) + "\n")


def read():
    line = sys.stdin.readline()
    return json.loads(line) if line.strip() else (None if line == "" else read())


log({"env_keys": sorted(os.environ), "cwd": os.getcwd(), "argv": sys.argv[1:]})
pending_results = {}
while True:
    msg = read()
    if msg is None:
        break
    log(msg)
    m, i = msg.get("method"), msg.get("id")
    if m == "initialize":
        send({"id": i, "result": {"userAgent": "fake-codex"}})
    elif m == "thread/start":
        send({"id": i, "result": {"thread": {"id": "th1"}}})
    elif m == "turn/interrupt":
        send({"id": i, "result": {}})
    elif m == "turn/start":
        send({"id": i, "result": {"turn": {"id": "tu1"}}})
        if SCENARIO == "never":
            continue
        if SCENARIO == "exit_mid_turn":
            os._exit(3)
        if SCENARIO == "unknown_request":
            send({"id": 900, "method": "foo/bar", "params": {}})
            time.sleep(0.2)
        calls = {"two_tools": [("call-a", "scene_summary", {}), ("call-b", "lampway_status", {})], "one_tool": [("call-a", "scene_summary", {})], "dup_call": [("call-a", "scene_summary", {}), ("call-a", "scene_summary", {})]}.get(SCENARIO, [])
        for k, (cid, tool, args) in enumerate(calls):
            send({"id": 100 + k, "method": "item/tool/call", "params": {"tool": tool, "arguments": args, "callId": cid, "threadId": "th1", "turnId": "tu1"}})
        want = len({c[0] for c in calls})
        got = 0
        while got < want:
            r = read()
            if r is None:
                sys.exit(0)
            log(r)
            if "result" in r and r.get("id", 0) >= 100:
                got += 1
        send({"method": "item/agentMessage/delta", "params": {"threadId": "th1", "turnId": "tu1", "delta": "OK"}})
        send({"method": "turn/completed", "params": {"threadId": "th1", "turn": {"id": "tu1", "status": "completed"}}})
    elif m == "stray/tool":
        send({"id": 500, "method": "item/tool/call", "params": {"tool": "x", "arguments": {}, "callId": "late", "threadId": "th1", "turnId": "tu0"}})
