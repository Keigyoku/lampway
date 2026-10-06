# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Connections hub (connections_store.md): one record of which source each connection uses, its checks and its last use; the
status of every connection computed from that record and what is on the host; the user's actions; and the consumer interface
(``require``, ``env_for``, ``report_use``).

The record (``<state>/connections.json``) never holds a secret: a pointer is a NAME or a PATH, a manual key lives in the store and the
record names the store and the key's fingerprint. Every write is the user's (``by="user"``); a declared agent is refused. Having a
credential never opens a route: the hub reads the egress switch and never writes it."""

import os
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from .. import egress as EG
from . import checks as CK
from . import files as CF
from . import registry as R
from . import sources as S
from .sources import Credential, secret_of  # noqa: F401  (the consumer interface re-exports them)
from .store import StoreError, choose_store
from .errors import AGENT_WRITE, NotConnected, Refused
from .views import Views
from .actions import Actions

REMOTE_FRESH_S = 30 * 60
LOCAL_FRESH_S = 60
POLL_EVERY_S = 30 * 60
USED_WITHIN_S = 24 * 3600
EXPIRY_WARNING_S = 24 * 3600
MAX_SECRET_BYTES = 8 * 1024
HISTORY = 10


def _spec(cid: str) -> R.Spec:
    try:
        return R.get(cid)
    except R.UnknownConnection as exc:
        raise Refused(str(exc), 404) from None


def default_secrets_dir(env=None) -> Path:
    env = os.environ if env is None else env
    base = env.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(env.get("LAMPWAY_SECRETS_DIR") or Path(base) / "lampway-secrets")


class Hub(Views, Actions):
    def __init__(self, state_dir, secrets_dir=None, env=None, store=None, keyring_backend=None, oauth=None, route_on=None, transport=None,
                 which: Callable = shutil.which, home=None, clock: Callable = time.time, endpoint: Callable = None, mcp_clients=None,
                 cli_runner=None, byok_present: Callable = None):
        self.state_dir = Path(state_dir)
        self._env = env
        self.secrets_dir = Path(secrets_dir) if secrets_dir else default_secrets_dir(self.env)
        self._store, self._store_reason, self._keyring_backend = store, ("given" if store is not None else None), keyring_backend
        self.oauth = dict(oauth or {})
        self._route_on = route_on
        self.transport, self.which, self.home, self.clock = transport, which, Path(home or Path.home()), clock
        self.endpoint = endpoint or (lambda: self.env.get("OPENAI_BASE_URL") or "http://127.0.0.1:11434/v1")
        self.mcp_clients = dict(mcp_clients or {})
        self.cli_runner = cli_runner
        self.byok_present = byok_present or (lambda: False)
        self._lock = threading.RLock()
        self._inflight: set = set()

    # ---------------------------------------------------------------------------------------------------- plumbing
    @property
    def env(self):
        return os.environ if self._env is None else self._env

    @property
    def record_path(self) -> Path:
        return self.state_dir / "connections.json"

    @property
    def log_path(self) -> Path:
        return self.state_dir / "connections" / "log.jsonl"

    def store(self):
        if self._store is None:
            self._store, self._store_reason = choose_store(self.secrets_dir, self._keyring_backend)
        return self._store

    def store_info(self) -> dict:
        s = self.store()
        return {"kind": s.kind, "reason": self._store_reason}

    def route_on(self, route: Optional[str]) -> bool:
        if route is None:
            return True
        if self._route_on is not None:
            return bool(self._route_on(route))
        return EG.ACTIVE.enabled(route) if EG.ACTIVE is not None else False

    def _read(self) -> dict:
        try:
            data = CF.read_json(self.record_path)
        except CF.Unreadable as exc:
            self._log("*", "record", "system", False, str(exc))
            data = {}
        data.setdefault("connections", {})
        return data

    def _update(self, cid: str, fn) -> dict:
        with self._lock, CF.locked(self.state_dir / "connections" / "record.lock"):
            data = self._read()
            rec = data["connections"].setdefault(cid, {})
            fn(rec)
            CF.atomic_write_json(self.record_path, data)
            return rec

    def _rec(self, cid: str) -> dict:
        return self._read()["connections"].get(cid, {})

    def _log(self, cid, action, by, ok, reason="") -> None:
        import json
        CF.ensure_dir(self.log_path.parent)
        row = {"t": self.clock(), "id": cid, "action": action, "by": by, "ok": bool(ok), "reason": reason[:200]}
        fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")

    def _gate(self, by: str) -> None:
        if by != "user":
            raise Refused(AGENT_WRITE, 403)

    # ---------------------------------------------------------------------------------------------------- resolution
    def _sources(self, spec, rec=None) -> list:
        rec = self._rec(spec.id) if rec is None else rec
        store = self._store_for_read(rec)
        return S.detect(spec, rec, self.env, store, self.oauth.get(spec.id), self.which, self.home)

    def _store_for_read(self, rec):
        if not rec.get("manual"):
            return None
        if self._store is None and rec["manual"].get("store") == "file":
            from .store import FileStore
            return FileStore(self.secrets_dir)
        return self.store()

    def _active(self, spec, sources, rec) -> tuple:
        """(the source in use, the conflict text). C3: a source set in the environment wins over the chosen one; the conflict is shown."""
        chosen = rec.get("active", "auto")
        env_src = next((s for s in sources if s.from_env and s.present), None)
        held = [s for s in sources if s.mode in ("manual", "pointer") and not s.from_env and s.present]
        if env_src is not None:
            conflict = None
            if chosen not in ("auto", env_src.mode) or held:
                other = held[0].label if held else f"the {chosen} source you chose"
                conflict = f"the environment sets {env_src.detail}, which wins over {other}: unset it before starting Lampway to use the one saved here"
            return env_src, conflict
        if chosen != "auto":
            return next((s for s in sources if s.mode == chosen), None), None
        for mode in S.AUTO_ORDER:
            s = next((s for s in sources if s.mode == mode and s.present), None)
            if s is not None:
                return s, None
        return None, None

    def credential(self, cid: str) -> Credential:
        """The credential in use, route or no route (the egress hook refuses a send when the route is off)."""
        spec = _spec(cid)
        if spec.derived_from:
            return self.credential(spec.derived_from)
        sources = self._sources(spec)
        src, _ = self._active(spec, sources, self._rec(cid))
        if src is None or not src.present:
            raise NotConnected(f"{spec.label} is not connected: connect it in Connections", cid)
        if src.mode == "signin":
            return Credential(spec, "signin", oauth=self.oauth[cid])
        if src.mode == "host":
            return Credential(spec, "host")
        try:
            values = src.values()
        except (S.SourceError, StoreError) as exc:
            raise NotConnected(f"{spec.label} is not connected: {exc}", cid) from None
        if spec.fields and not all(values.get(f) for f in spec.fields if spec.kind != "endpoint"):
            raise NotConnected(f"{spec.label} is not connected: connect it in Connections", cid)
        return Credential(spec, src.mode, values)

    def require(self, cid: str) -> Credential:
        spec = _spec(cid)
        cred = self.credential(cid)
        if not self.route_on(spec.route):
            raise NotConnected(f"{spec.label} is connected but its route is off: switch it on in Privacy", cid)
        return cred

    def env_for(self, ids=()) -> dict:
        """A child's environment: ours scrubbed of every secret-shaped variable and every registry name, plus exactly these connections."""
        drop = {n for s in R.SPECS.values() for names in list(s.env.values()) + list(s.file_env.values()) for n in names}
        from ..agent.providers.codex_app_server import DROP_EXACT
        out = {}
        for k, v in self.env.items():
            up = k.upper()
            if k in drop or k in DROP_EXACT or any(t in up for t in ("API_KEY", "SECRET", "TOKEN", "PASSWORD")) or up.endswith("_KEY"):
                continue
            out[k] = v
        for cid in ids:
            try:
                out.update(self.credential(cid).env())
            except Refused:
                pass
        return out

    def report_use(self, cid: str, ok: bool, status: Optional[int] = None) -> None:
        spec = _spec(cid)
        now = self.clock()

        def fn(rec):
            rec["last_used"] = now
            if ok:
                self._push(rec, {"state": "connected", "checked_at": now, "check_id": "use", "by": "use", "kind": "use", "evidence": {}, "sig": self._sig(spec)})
            elif status in (401, 403):
                self._push(rec, {"state": "expired", "checked_at": now, "check_id": "use", "by": "use", "kind": "use",
                                 "evidence": {"reason": f"a real call answered HTTP {status}"}, "sig": self._sig(spec)})
        self._update(cid, fn)

    @staticmethod
    def _push(rec, check) -> None:
        rec["checks"] = (rec.get("checks") or [])[-(HISTORY - 1):] + [check]

    def _sig(self, spec) -> Optional[str]:
        src, _ = self._active(spec, self._sources(spec), self._rec(spec.id))
        return src.sig if src is not None else None
