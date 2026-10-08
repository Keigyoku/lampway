# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Q2 visibility maintenance through pinned Hermes's public SessionDB, never a conversation store.

Run by path with the engine's interpreter across recorded Lampway-owned homes. Native archive selection is an ended-tip snapshot:
a concurrent native resume can change visibility after selection; archiving never ends a process or deletes history.
"""
import contextlib
import json
import sys
from pathlib import Path

RETENTION_DAYS = 30
VISIBLE_ENDED_LIMIT = 200


def maintain(db):
    return maintain_many([db])


def maintain_many(dbs):
    """Retain the newest 200 visible ended tips globally; aggregate only transient native metadata."""
    aged = sum(db.archive_sessions(older_than_days=RETENTION_DAYS, include_pinned=True) for db in dbs)
    visible = []
    for index, db in enumerate(dbs):
        rows = db.list_prune_candidates(archived=False, lineage_tips_only=True, include_pinned=True)
        visible.extend((row, index, db) for row in rows if not (db.get_session(row["id"]) or {}).get("hidden"))
    visible.sort(key=lambda entry: (float(entry[0].get("last_active") or 0),
                                   float(entry[0].get("started_at") or 0), entry[1], entry[0]["id"]))
    overflow = 0
    for row, index, db in visible[:max(0, len(visible) - VISIBLE_ENDED_LIMIT)]:
        # Avoid hiding a row resumed since the native candidate snapshot when we can see the change.
        current = db.get_session(row["id"]) or {}
        if current.get("ended_at") is not None and not current.get("archived"):
            overflow += int(db.set_session_archived(row["id"], True))
    return {"aged": aged, "overflow": overflow}


def main():
    homes = json.load(sys.stdin)
    if not isinstance(homes, list) or any(not isinstance(h, str) or not Path(h).is_absolute() for h in homes):
        raise ValueError("native visibility maintenance needs validated absolute owned homes")
    from hermes_state import SessionDB
    with contextlib.ExitStack() as stack:
        dbs = []
        for home in homes:
            path = Path(home) / "state.db"
            if path.is_file():
                db = SessionDB(path)
                stack.callback(db.close)
                dbs.append(db)
        print(json.dumps(maintain_many(dbs)))


if __name__ == "__main__":
    main()
