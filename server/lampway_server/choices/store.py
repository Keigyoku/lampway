# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The choices store (choices_store.md 5 and 6.5): the user's choices per scope, the acknowledgements (CH1), the proposals and the write log.

Files, all under the server state directory the agent sandbox denies: ``choices.json`` (global), ``choices/projects/<sha16>.json``,
``choices/proposals.jsonl``, ``choices/log.jsonl``. Every write is atomic under one fcntl lock; a file that does not parse is set aside
and reported, never overwritten by an empty one. A value that looks like a secret is refused: Connections holds credentials, never this.
Only the user writes; an agent proposes."""

import copy
import hashlib
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from . import registry as REG

SCHEMA = "lampway.choices/1"
MAX_CHAIN = 8
MAX_OPEN_PER_ORIGIN = 5
AGENT_WRITE = "only your click in Choices can change a choice: an agent may propose one"
OWN_PROVIDER = "an agent must not change its own provider"


class Refused(Exception):
    def __init__(self, text: str, status: int = 400):
        super().__init__(text)
        self.status = status


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(o, (list, tuple)):
        for v in o:
            yield from _strings(v)


def _no_secret(*values) -> None:
    from ..ledger import find_secret
    for v in values:
        for s in _strings(v):
            if find_secret(s):
                raise Refused("a choice never holds a credential: Connections does")


def project_key(project: str) -> str:
    return hashlib.sha256(os.path.realpath(project).encode()).hexdigest()[:16]


def _version(doc: dict) -> str:
    body = {k: v for k, v in doc.items() if k not in ("version", "error")}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:8]


def validate(pid: str, entry: dict) -> dict:
    purpose = REG.get(pid)
    if not isinstance(entry, dict) or not entry.get("preferred"):
        raise Refused(f"a choice for {pid} names a preferred option")
    preferred, fallbacks = str(entry["preferred"]), [str(f) for f in entry.get("fallbacks") or []]
    for oid in [preferred] + fallbacks:
        if not REG.offers(purpose, oid):
            raise Refused(f"{oid} is not an option for {pid}: its options are {', '.join(REG.listed(purpose))}")
    if len(set([preferred] + fallbacks)) != 1 + len(fallbacks):
        raise Refused("a fallback cannot repeat the preferred option or another fallback")
    if 1 + len(fallbacks) > MAX_CHAIN:
        raise Refused(f"a chain holds at most {MAX_CHAIN} options")
    policy = entry.get("override_policy")
    if policy is not None and policy not in REG.POLICIES:
        raise Refused(f"override_policy is one of {', '.join(REG.POLICIES)}")
    if pid in ("agent.main", "agent.worker") and policy not in (None, "none"):
        raise Refused(OWN_PROVIDER)
    params = entry.get("params") or {}
    if not isinstance(params, dict):
        raise Refused("params is an object")
    _no_secret(params)
    out = {"preferred": preferred, "fallbacks": fallbacks, "params": copy.deepcopy(params)}
    if policy:
        out["override_policy"] = policy
    return out


class MemoryStore:
    """The store's interface, held in memory (tests, and the "what if" preview)."""

    def __init__(self):
        self._lock = threading.RLock()
        self._global = {"schema": SCHEMA, "purposes": {}, "acknowledgements": {}}
        self._projects: dict = {}
        self._proposals: list = []
        self._log: list = []

    # ------------------------------------------------------------------------------------------------- persistence hooks
    def _load_global(self) -> dict:
        return copy.deepcopy(self._global)

    def _save_global(self, doc: dict) -> None:
        self._global = copy.deepcopy(doc)

    def _load_project(self, key: str) -> dict:
        return copy.deepcopy(self._projects.get(key) or {"schema": SCHEMA, "purposes": {}})

    def _save_project(self, key: str, doc: dict) -> None:
        self._projects[key] = copy.deepcopy(doc)

    def _load_proposals(self) -> list:
        return copy.deepcopy(self._proposals)

    def _save_proposals(self, rows: list) -> None:
        self._proposals = copy.deepcopy(rows)

    def _append_log(self, row: dict) -> None:
        self._log.append(row)

    def _locked(self):
        return self._lock

    # ------------------------------------------------------------------------------------------------- reads
    def global_doc(self) -> dict:
        doc = self._load_global()
        doc.setdefault("purposes", {})
        doc.setdefault("acknowledgements", {})
        doc["version"] = _version(doc)
        return doc

    def project_doc(self, project: Optional[str]) -> dict:
        if not project:
            return {"schema": SCHEMA, "purposes": {}}
        return self._load_project(project_key(project))

    def proposals(self, state: Optional[str] = None, origin: Optional[str] = None) -> list:
        return [p for p in self._load_proposals() if (state is None or p["state"] == state) and (origin is None or p["origin"] == origin)]

    # ------------------------------------------------------------------------------------------------- writes (the user's)
    @staticmethod
    def _gate(by: str) -> None:
        if by != "user":
            raise Refused(AGENT_WRITE, 403)

    def set(self, pid: str, scope: str, project: Optional[str], entry: dict, by: str) -> dict:
        self._gate(by)
        clean = validate(pid, entry)
        clean.update(set_at=_now_iso(), set_by=by)
        with self._locked():
            if scope == "project":
                if not project:
                    raise Refused("a project choice names its project")
                key = project_key(project)
                doc = self._load_project(key)
                doc.setdefault("purposes", {})[pid] = clean
                doc["root"] = os.path.realpath(project)
                before = _version(self._load_project(key))
                self._save_project(key, doc)
                after = _version(doc)
            elif scope == "global":
                doc = self._load_global()
                before = _version(doc)
                doc.setdefault("purposes", {})[pid] = clean
                self._save_global(doc)
                after = _version(doc)
            else:
                raise Refused("scope is global or project")
            self._append_log({"t": time.time(), "purpose": pid, "scope": scope, "by": by, "before_sha8": before, "after_sha8": after})
        return clean

    def clear(self, pid: str, project: Optional[str], by: str) -> None:
        self._gate(by)
        REG.get(pid)
        with self._locked():
            if project:
                key = project_key(project)
                doc = self._load_project(key)
                doc.setdefault("purposes", {}).pop(pid, None)
                self._save_project(key, doc)
            else:
                doc = self._load_global()
                doc.setdefault("purposes", {}).pop(pid, None)
                self._save_global(doc)
            self._append_log({"t": time.time(), "purpose": pid, "scope": "project" if project else "global", "by": by, "action": "clear"})

    def acknowledge(self, option: str, private: bool, by: str, at: Optional[str] = None) -> Optional[str]:
        """CH1: the user lets private content go to one option whose terms are unread or that retains; dated and revocable."""
        self._gate(by)
        if not any(option in p.options for p in REG.PURPOSES.values()):
            raise Refused(f"no option {option}")
        with self._locked():
            doc = self._load_global()
            acks = doc.setdefault("acknowledgements", {})
            if private:
                acks[option] = {"private": True, "at": at or _now_iso()}
            else:
                acks.pop(option, None)
            self._save_global(doc)
            self._append_log({"t": time.time(), "option": option, "by": by, "action": "acknowledge" if private else "revoke"})
            return acks.get(option, {}).get("at")

    # ------------------------------------------------------------------------------------------------- quality records (CHOICES.md 8.4)
    def _load_quality(self) -> list:
        return list(getattr(self, "_quality", []))

    def _append_quality(self, rows: list) -> None:
        self._quality = self._load_quality() + list(rows)

    def add_quality(self, records: list, by: str) -> int:
        """Append measured records ``{purpose, option, metric, value, n, source, measured_at}``; evidence for the user, never a reordering."""
        self._gate(by)
        clean = []
        for r in records:
            purpose = REG.get(str(r.get("purpose")))
            if not REG.offers(purpose, str(r.get("option"))):
                raise Refused(f"{r.get('option')} is not an option for {purpose.id}")
            value = r.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise Refused("a quality value is a number")
            row = {"purpose": purpose.id, "option": str(r["option"]), "metric": str(r.get("metric") or "")[:40], "value": float(value),
                   "n": int(r.get("n") or 1), "source": str(r.get("source") or "")[:120], "measured_at": str(r.get("measured_at") or "")[:32], "by": by}
            _no_secret(row)
            clean.append(row)
        with self._locked():
            self._append_quality(clean)
        return len(clean)

    def quality(self, purpose: Optional[str] = None, option: Optional[str] = None) -> list:
        return [q for q in self._load_quality() if (purpose is None or q["purpose"] == purpose) and (option is None or q["option"] == option)]

    # ------------------------------------------------------------------------------------------------- proposals (an agent's)
    def propose(self, origin: str, pid: str, change: dict, reason: str, evidence) -> str:
        REG.get(pid)
        if not reason or not str(reason).strip():
            raise Refused("a proposal says why (reason)")
        _no_secret(change, reason, evidence)
        validate(pid, {"preferred": change.get("preferred") or (REG.get(pid).default[:1] or REG.get(pid).options[:1])[0],
                       "fallbacks": change.get("fallbacks") or [], "params": change.get("params") or {}})
        with self._locked():
            rows = self._load_proposals()
            if sum(1 for r in rows if r["origin"] == origin and r["state"] == "open") >= MAX_OPEN_PER_ORIGIN:
                raise Refused(f"{MAX_OPEN_PER_ORIGIN} proposals are waiting for the user already")
            pid_ = uuid.uuid4().hex[:12]
            rows.append({"id": pid_, "at": _now_iso(), "origin": origin, "purpose": pid, "change": change, "reason": str(reason)[:400],
                         "evidence": list(evidence or [])[:10], "state": "open", "decided_at": None, "decided_by": None})
            self._save_proposals(rows)
        return pid_

    def decide(self, proposal_id: str, accept: bool, by: str, scope: str = "global", project: Optional[str] = None) -> dict:
        self._gate(by)
        with self._locked():
            rows = self._load_proposals()
            row = next((r for r in rows if r["id"] == proposal_id), None)
            if row is None or row["state"] != "open":
                raise Refused(f"no open proposal {proposal_id}", 404)
            if accept:
                cur = ((self.project_doc(project) if scope == "project" else self.global_doc())["purposes"].get(row["purpose"]) or {})
                entry = {**{k: v for k, v in cur.items() if k in ("preferred", "fallbacks", "params", "override_policy")}, **row["change"]}
                self.set(row["purpose"], scope, project, entry, by)
            row.update(state="accepted" if accept else "declined", decided_at=_now_iso(), decided_by=by)
            self._save_proposals(rows)
            return row


class FileStore(MemoryStore):
    """The JSON files of choices_store.md section 5, atomic and locked."""

    def __init__(self, state_dir):
        super().__init__()
        self.state_dir = Path(state_dir)
        self.dir = self.state_dir / "choices"
        self._error = ""

    @property
    def global_path(self) -> Path:
        return self.state_dir / "choices.json"

    def _locked(self):
        """The thread lock and the cross-process fcntl lock, re-entrant (a decision that sets a choice takes it once)."""
        from ..connections import files as CF
        store = self

        class _Both:
            def __enter__(s):
                store._lock.acquire()
                store._depth = getattr(store, "_depth", 0) + 1
                s._f = CF.locked(store.dir / ".lock") if store._depth == 1 else None
                if s._f is not None:
                    s._f.__enter__()

            def __exit__(s, *exc):
                try:
                    if s._f is not None:
                        s._f.__exit__(*exc)
                finally:
                    store._depth -= 1
                    store._lock.release()
        return _Both()

    def _read(self, path: Path, default: dict) -> dict:
        from ..connections import files as CF
        try:
            data = CF.read_json(path)
        except CF.Unreadable as exc:
            self._error = str(exc)
            return dict(default)
        return data or dict(default)

    def _load_global(self) -> dict:
        doc = self._read(self.global_path, {"schema": SCHEMA, "purposes": {}, "acknowledgements": {}})
        if self._error:
            doc["error"] = self._error
        return doc

    def _save_global(self, doc: dict) -> None:
        from ..connections import files as CF
        CF.atomic_write_json(self.global_path, {k: v for k, v in doc.items() if k not in ("version", "error")})

    def _load_project(self, key: str) -> dict:
        return self._read(self.dir / "projects" / f"{key}.json", {"schema": SCHEMA, "purposes": {}})

    def _save_project(self, key: str, doc: dict) -> None:
        from ..connections import files as CF
        CF.atomic_write_json(self.dir / "projects" / f"{key}.json", doc)

    def _load_proposals(self) -> list:
        try:
            return [json.loads(line) for line in (self.dir / "proposals.jsonl").read_text().splitlines() if line.strip()]
        except (OSError, ValueError):
            return []

    def _save_proposals(self, rows: list) -> None:
        from ..connections import files as CF
        CF.atomic_write_bytes(self.dir / "proposals.jsonl", "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows).encode())

    def _load_quality(self) -> list:
        try:
            return [json.loads(line) for line in (self.dir / "quality.jsonl").read_text().splitlines() if line.strip()]
        except (OSError, ValueError):
            return []

    def _append_quality(self, rows: list) -> None:
        from ..connections import files as CF
        CF.ensure_dir(self.dir)
        fd = os.open(self.dir / "quality.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as fh:
            for r in rows:
                fh.write(json.dumps(r, sort_keys=True) + "\n")

    def _append_log(self, row: dict) -> None:
        from ..connections import files as CF
        CF.ensure_dir(self.dir)
        fd = os.open(self.dir / "log.jsonl", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
