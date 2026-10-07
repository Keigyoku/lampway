# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the Capabilities page shows: the last GET /app/capabilities answer. One writer on the main thread (``take`` and the page's
operators), many readers; draw() reads this and never the network. The read itself runs on a worker thread (``request``): it leaves its
answer in an inbox and only the main thread, through ``take``, moves it into ``STATE``. No bpy.

``missing`` is a server that has no Capabilities yet (an HTTP 404): the page then says so and the first-run walk skips its step."""

import os
import threading
import time

from . import capabilities_face as face

_LOCK = threading.Lock()
_INBOX = {"answer": None}
_FRESH = {"ok": False, "missing": False, "error": "", "rows": [], "proposals": [], "as_of": 0.0, "inflight": False,
          "project": "", "project_only": False,   # project_only: this page's writes go to this project alone
          "pending": "",                          # the capability whose confirm row (its plain warning) is open
          "refusal": {}, "dismissed": set()}
STATE = {}


def reset() -> None:
    """Back to a page that has read nothing (tests; a restart of the app)."""
    with _LOCK:
        _INBOX["answer"] = None
    STATE.clear()
    STATE.update({k: (type(v)() if isinstance(v, (dict, list, set)) else v) for k, v in _FRESH.items()})
    STATE["project"] = os.environ.get("LAMPWAY_PROJECT_ROOT", "")


reset()


def update(listing: dict) -> None:
    STATE.update(ok=True, missing=False, error="", rows=list(listing.get("capabilities") or []),
                 proposals=list(listing.get("proposals") or []), as_of=time.time())


def fail(message: str) -> None:
    """Keep the last good listing on screen, marked stale by ``ok`` False and the message."""
    STATE.update(ok=False, error=message, missing="HTTP 404" in message)


def merge_row(row: dict) -> None:
    """A write's answer into its row at once. A short answer (a family member's) merges; it never blanks the row's label or sentence."""
    for i, old in enumerate(STATE["rows"]):
        if old.get("id") == row.get("id"):
            STATE["rows"][i] = {**old, **row}
            return


def dismiss(pid: str) -> None:
    """Hide an agent's proposal card here. The server has no route that closes a proposal, so this is the Client's own memory."""
    STATE["dismissed"].add(pid)


def cards() -> list:
    return face.proposal_cards(STATE["proposals"], STATE["rows"], STATE["dismissed"])


def write_project():
    """The project a write carries: the page's switch is on and this file has one; otherwise None (every project)."""
    return STATE["project"] if STATE["project_only"] and STATE["project"] else None


def _spawn(fn) -> None:
    threading.Thread(target=fn, daemon=True, name="lampway-capabilities-read").start()


def request(client_factory, project="", spawn=None) -> bool:
    """Start one read off the main thread. False when one is already waiting to be taken. Never raises on the caller's thread."""
    with _LOCK:
        if STATE["inflight"]:
            return False
        STATE["inflight"] = True
    try:
        (spawn or _spawn)(lambda: _read(client_factory, project))
    except RuntimeError:   # no thread could start: nothing is in flight, the next ask may try again
        STATE["inflight"] = False
        return False
    return True


def _read(client_factory, project) -> None:
    """The worker: ask, and leave the answer or the failure in the inbox. Any failure is a stated error, so the worker never dies silent."""
    try:
        answer = ("ok", client_factory().capabilities(project or None))
    except Exception as exc:  # noqa: BLE001  (a refused connection, a bad body: the page says it, the next read tries again)
        answer = ("fail", str(exc) or exc.__class__.__name__)
    with _LOCK:
        _INBOX["answer"] = answer


def take() -> bool:
    """Main thread: apply the inbox if a read has finished. True when the page changed."""
    with _LOCK:
        answer, _INBOX["answer"] = _INBOX["answer"], None
        if answer is None:
            return False
        STATE["inflight"] = False
    (update if answer[0] == "ok" else fail)(answer[1])
    return True
