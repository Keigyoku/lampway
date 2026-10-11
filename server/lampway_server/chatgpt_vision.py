# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Human-requested fixed synthetic vision check; no arbitrary inference forwarding."""
import base64
import asyncio
import os
import fcntl
import hashlib
import json
import math
import re
import secrets
import struct
import time
import zlib
from pathlib import Path

import httpx

from .connections import files as CF

ROUTE = "https://api.openai.com/v1/responses"
VERSION = 1
DISCLOSURE = ("Check image support using your ChatGPT plan. This sends one small synthetic image and a fixed question to "
              "OpenAI on the model shown below, using your plan allowance. No scene, file or chat content is sent. "
              "The result stays on this machine. This does not enable image generation. Click Run vision check to consent.")


def _path(auth, model):
    name = hashlib.sha256(json.dumps([ROUTE, model], separators=(",", ":")).encode()).hexdigest()
    return Path(auth.dir) / "chatgpt_vision" / (name + ".json")


def _read(auth, model):
    try:
        value = json.loads(_path(auth, model).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def admitted(auth, model, route=ROUTE):
    """Read-only and false for missing, invalidated, malformed or different account/model/route evidence."""
    scope_fn = getattr(auth, "vision_account_scope", None)
    scope = scope_fn() if callable(scope_fn) else None
    if not scope:
        return False
    r = _read(auth, model)
    stamps = [r.get(key) for key in ("started_at", "finished_at", "verified_at")]
    evidence = (r.get("completed") is True and isinstance(r.get("attempt"), str)
                and re.fullmatch(r"[0-9a-f]{32}", r["attempt"]) is not None
                and isinstance(r.get("image_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", r["image_sha256"]) is not None
                and all(type(t) in (int, float) and math.isfinite(t) for t in stamps)
                and 0 <= stamps[0] <= stamps[1] == stamps[2])
    return bool(evidence and scope and type(r.get("version")) is int and r.get("version") == VERSION and r.get("status") == "verified"
                and r.get("account_scope") == scope and r.get("model") == model and r.get("route") == route == ROUTE)


def invalidate(auth, model, route=ROUTE, *, scope=None):
    """An image request failure withdraws only its own matching qualification, preserving other scopes."""
    if scope is None:
        return
    changed = False
    with CF.locked(Path(auth.dir) / ".chatgpt_vision.lock"):
        receipt = _read(auth, model)
        if receipt.get("status") == "verified" and receipt.get("account_scope") == scope and receipt.get("model") == model and receipt.get("route") == route:
            receipt.update(status="failed", invalidated_at=time.time())
            CF.atomic_write_json(_path(auth, model), receipt)
            changed = True
    if changed:
        from .capabilities import notify_changed
        notify_changed()  # receipt is durable and its file lock has been released



def _challenge():
    colors = {"RED": (255, 0, 0), "GREEN": (0, 255, 0), "BLUE": (0, 0, 255)}
    chosen = [secrets.choice(tuple(colors)) for _ in range(8)]
    row = b"\0" + b"".join(bytes(colors[color]) * 16 for color in chosen)
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", 128, 16, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(row * 16)) + chunk(b"IEND", b"")
    return png, " ".join(chosen)


async def probe(auth, model, *, consent=False, acknowledge_unknown=False, transport=None):
    if consent is not True:
        raise ValueError("Explicit consent is required for the vision check")
    CF.ensure_dir(Path(auth.dir))
    fd = os.open(Path(auth.dir) / ".chatgpt_vision.active", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("A vision check is already running") from None
        async with asyncio.timeout(60):
            return await _probe(auth, model, consent=consent, acknowledge_unknown=acknowledge_unknown, transport=transport)
    finally:
        os.close(fd)


async def _probe(auth, model, *, consent=False, acknowledge_unknown=False, transport=None):
    """Only the guarded browser route calls this; body/image/route are fixed, never caller content.

    Pending is durable before outbound bytes. A transport error leaves unknown and cannot be resubmitted without a second
    explicit acknowledgement. Known rejection or incorrect/completed response fails closed; there is no automatic retry.
    """
    if consent is not True:
        raise ValueError("Explicit consent is required for the vision check")
    if not isinstance(model, str) or not model or len(model) > 128 or any(ord(c) < 33 for c in model):
        raise ValueError("Choose a valid ChatGPT model first")
    scope = auth.vision_account_scope()
    if not scope:
        raise ValueError("Sign in and enable ChatGPT plan usage before checking vision")
    from . import egress
    try:
        egress.preflight("chatgpt_plan")
    except Exception:
        invalidate(auth, model, scope=scope)
        raise
    attempt = secrets.token_hex(16)
    png, expected = _challenge()
    receipt = {"version": VERSION, "account_scope": scope, "model": model, "route": ROUTE,
               "attempt": attempt, "status": "pending", "started_at": time.time(), "image_sha256": hashlib.sha256(png).hexdigest()}
    with CF.locked(Path(auth.dir) / ".chatgpt_vision.lock"):
        old = _read(auth, model)
        if old.get("status") in {"pending", "unknown"} and not acknowledge_unknown:
            raise ValueError("Previous vision check may have used plan allowance; acknowledge it before checking again")
        CF.atomic_write_json(_path(auth, model), receipt)
    body = {"model": model, "instructions": "Answer the fixed image question exactly.", "store": False, "stream": True,
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "Name the eight panel colors from left to right, choosing RED, GREEN or BLUE. Reply with only eight uppercase color names separated by single spaces."},
                {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode(), "detail": "low"}]}]}
    status, text, completed = "unknown", "", False
    try:
        token = await auth.access_token_for_scope(scope)
        async with httpx.AsyncClient(transport=transport, timeout=60) as client:
            async with client.stream("POST", ROUTE, json=body,
                                     headers={"Authorization": "Bearer " + token, "Accept": "text/event-stream"}) as response:
                if response.status_code >= 400:
                    status = "failed"  # Do not persist or display provider bodies, tokens, identities or signed URLs.
                else:
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        try:
                            event = json.loads(line[5:])
                        except ValueError:
                            continue
                        if event.get("type") == "response.output_text.delta":
                            text = (text + str(event.get("delta") or ""))[:64]
                        elif event.get("type") in {"response.failed", "response.incomplete"}:
                            status = "failed"
                            break
                        elif event.get("type") == "response.completed":
                            completed = True
                            status = "verified" if text.strip() == expected else "failed"
                            break
    except BaseException:
        status = "unknown"
        raise
    finally:
        if auth.vision_account_scope() != scope:
            status = "failed"
        receipt.update(status=status, completed=completed, finished_at=time.time())
        if status == "verified":
            receipt["verified_at"] = receipt["finished_at"]
        with CF.locked(Path(auth.dir) / ".chatgpt_vision.lock"):
            if _read(auth, model).get("attempt") == attempt:
                CF.atomic_write_json(_path(auth, model), receipt)
    return {"status": status, "model": model, "images_enabled": admitted(auth, model)}
