# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The hub's write half (CONNECTIONS.md section 5): set the source, paste, rotate, test, forget, move into the keyring, sign in and out,
scan, and the poller. Every action that writes, tests or signs in is the user's (``by="user"``); the poller tests only connections whose
route is on and that were used in the last day (C2); a test with the route off sends nothing (C1)."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from .. import egress as EG
from . import checks as CK
from . import files as CF
from . import registry as R
from . import sources as S
from .errors import NotConnected, Refused
from .store import StoreError, StoreLocked

POLL_EVERY_S = 30 * 60
USED_WITHIN_S = 24 * 3600
MAX_SECRET_BYTES = 8 * 1024


def _spec(cid):
    try:
        return R.get(cid)
    except R.UnknownConnection as exc:
        raise Refused(str(exc), 404) from None


def _route_label(route):
    r = EG.ROUTES.get(route)
    return r.label if r else route


def _check_host(spec, base) -> str:
    if spec.check.kind == "cli":
        r = EG.ROUTES.get(spec.route)
        return r.hosts[0] if r and r.hosts else spec.route
    return urlsplit(spec.check.url.replace("{base}", base)).hostname or spec.route


class Actions:
    def _validate_fields(self, spec, fields) -> dict:
        bad = Refused(f"this does not look like a {spec.label} key: nothing was saved")
        if not spec.fields or not isinstance(fields, dict) or set(fields) != set(spec.fields):
            raise bad
        clean = {}
        for f in spec.fields:
            v = fields[f]
            if not isinstance(v, str) or not v.strip() or len(v.encode("utf-8")) > MAX_SECRET_BYTES or "\n" in v.strip() or "\r" in v:
                raise bad
            v = v.strip()
            if f == "key" and spec.shape and not v.startswith(spec.shape):
                raise bad
            clean[f] = v
        return clean

    # ---------------------------------------------------------------------------------------------------- sources
    def set_source(self, cid, mode, ref=None, by="user") -> dict:
        self._gate(by)
        spec = _spec(cid)
        if mode not in S.MODES:
            raise Refused(f"no source mode {mode!r}: the modes are {', '.join(S.MODES)}")
        pointer = None
        if mode == "pointer" and ref is not None:
            if not spec.fields:
                raise Refused(f"{spec.label} has no key to point at")
            if ref.get("env"):
                name = str(ref["env"])
                if not (self.env.get(name) or "").strip():
                    raise Refused(f"the environment of the Lampway server has no {name}: set it before starting Lampway, or paste the key instead")
                pointer = {"env": name}
            elif ref.get("path"):
                path = Path(str(ref["path"])).expanduser()
                try:
                    S.read_key_file(path, spec.env.get(spec.fields[0], ()), spec.scheme, ref.get("field"))
                except S.SourceError as exc:
                    raise Refused(str(exc)) from None
                pointer = {"path": str(path), **({"field": str(ref["field"])} if ref.get("field") else {})}
            else:
                raise Refused("a pointer names an environment variable ({env: NAME}) or a file ({path: PATH})")
        now = self.clock()

        def fn(rec):
            rec["active"] = mode
            if pointer is not None:
                rec["pointer"] = pointer
            rec["source_changed_at"] = now
        self._update(cid, fn)
        self._log(cid, "source", by, True, mode)
        return self._view_of(spec, self._rec(cid))

    def put_secret(self, cid, fields, by="user") -> dict:
        self._gate(by)
        spec = _spec(cid)
        clean = self._validate_fields(spec, fields)
        store = self.store()
        try:
            store.put(cid, clean)
        except StoreLocked as exc:
            self._log(cid, "secret", by, False, "keyring locked")
            raise Refused(str(exc), 423) from None
        except StoreError as exc:
            self._log(cid, "secret", by, False, "store refused")
            raise Refused(str(exc), 500) from None
        fp = S.fingerprint(clean, True)
        now = self.clock()

        def fn(rec):
            rec["manual"] = {"store": store.kind, "fields": list(spec.fields), "fingerprint": fp, "saved_at": now}
            rec["source_changed_at"] = now
        self._update(cid, fn)
        self._log(cid, "secret", by, True)
        return self._view_of(spec, self._rec(cid))

    def rotate(self, cid, fields, by="user") -> dict:
        """The new key replaces the old one only after its check passes; until then the old one stays."""
        self._gate(by)
        spec = _spec(cid)
        clean = self._validate_fields(spec, fields)
        self._require_testable(spec)
        state, ev, _ = self._check_values(spec, S.Credential(spec, "manual", clean))
        if state != "connected":
            self._log(cid, "rotate", by, False, state)
            raise Refused(f"the new {spec.label} key did not pass its check ({state}): the old one is kept")
        return self.put_secret(cid, clean, by)

    def forget(self, cid, mode, by="user") -> dict:
        self._gate(by)
        spec = _spec(cid)
        if mode == "host":
            cli = spec.binary[0].rsplit("/", 1)[-1] if spec.binary else spec.label
            raise Refused(f"this login belongs to {cli}: sign out there (`{spec.logout_hint or cli + ' logout'}`)")
        if mode == "env":
            raise Refused(f"the environment of the Lampway server sets this key: unset it before starting Lampway")
        if mode == "signin":
            return self.signout(cid, by)
        rec = self._rec(cid)
        if mode == "manual" and rec.get("manual"):
            try:
                self.store().delete(cid, tuple(rec["manual"].get("fields") or spec.fields))
            except StoreLocked as exc:
                raise Refused(str(exc), 423) from None
        now = self.clock()

        def fn(r):
            r.pop(mode, None)
            if r.get("active") == mode:
                r["active"] = "auto"
            r["source_changed_at"] = now
        self._update(cid, fn)
        self._log(cid, "forget", by, True, mode)
        return self._view_of(spec, self._rec(cid))

    def move_to_keyring(self, cid, by="user") -> dict:
        """Copies an environment or pointer key into the store, reads it back, and makes it the active source. The original stays."""
        self._gate(by)
        spec = _spec(cid)
        src, _ = self._active(spec, self._sources(spec), self._rec(cid))
        if src is None or src.mode not in ("env", "pointer"):
            raise Refused("only a key from the environment or a file can be moved into the keyring")
        try:
            values = src.values()
        except S.SourceError as exc:
            raise Refused(str(exc)) from None
        view = self.put_secret(cid, values, by)
        store = self.store()
        if any(store.get(cid, f) != values[f] for f in spec.fields):
            store.delete(cid, spec.fields)
            self._update(cid, lambda r: r.pop("manual", None))
            raise Refused("the keyring did not return the key that was written: nothing was moved")
        self._update(cid, lambda r: r.__setitem__("active", "manual"))
        self._log(cid, "move-to-keyring", by, True)
        return self._view_of(spec, self._rec(cid)) if view else view

    # ---------------------------------------------------------------------------------------------------- sign-in
    def signin(self, cid, by="user") -> dict:
        self._gate(by)
        spec = _spec(cid)
        adapter = self.oauth.get(cid)
        if not spec.signin or adapter is None:
            raise Refused(f"{spec.label} has no sign-in in Lampway")
        attempt = adapter.start_login()
        self._log(cid, "signin", by, True)
        return {"url": attempt.url}

    def signout(self, cid, by="user") -> dict:
        self._gate(by)
        spec = _spec(cid)
        adapter = self.oauth.get(cid)
        if adapter is None:
            raise Refused(f"{spec.label} has no sign-in in Lampway")
        adapter.sign_out()
        self._update(cid, lambda r: r.__setitem__("source_changed_at", self.clock()))
        self._log(cid, "signout", by, True)
        return self._view_of(spec, self._rec(cid))

    def scan(self, by="user") -> dict:
        """Local detection only, no network: which connections' detected sources changed since the last scan (one write)."""
        now = self.clock()
        sigs = {spec.id: [[s.mode, s.present, bool(s.error)] for s in self._sources(spec)] for spec in R.SPECS.values()}
        changed = []
        with self._lock, CF.locked(self.state_dir / "connections" / "record.lock"):
            data = self._read()
            for cid, sig in sigs.items():
                rec = data["connections"].setdefault(cid, {})
                if rec.get("scan") != sig:
                    changed.append(cid)
                    rec["scan"] = sig
            data["scanned_at"] = now
            CF.atomic_write_json(self.record_path, data)
        return {"scanned_at": now, "changed": changed}

    # ---------------------------------------------------------------------------------------------------- checks
    def _require_testable(self, spec) -> None:
        kind = spec.check.kind
        if kind == "none" or (kind == "local" and spec.kind != "browser_session"):
            raise Refused(f"{spec.label} has no check that costs nothing: its status is read on this machine only")
        if kind in ("http", "mcp", "cli") and not self.route_on(spec.route):
            raise Refused(f"testing sends your key to {_check_host(spec, self.endpoint())}: switch {_route_label(spec.route)} on in Privacy first", 409)

    def _check_values(self, spec, cred) -> tuple:
        kind = spec.check.kind
        if kind == "http":
            return CK.run_http(spec, cred, self.transport, self.endpoint())
        if kind == "mcp":
            factory = self.mcp_clients.get(spec.id)
            if factory is None:
                return "error", {"reason": "no MCP client for this connection"}, 0
            return CK.run_mcp(spec, factory())
        if kind == "cli":
            binary = S._which(spec.binary[0], self.which, self.home) if spec.binary else None
            if not binary:
                return "error", {"reason": f"{Path(spec.binary[0]).name} is not installed"}, 0
            with EG.guard(spec.route, kind="request"):
                return CK.run_cli(spec, binary, self.env_for([]), **({"runner": self.cli_runner} if self.cli_runner else {}))
        if kind == "local" and spec.kind == "browser_session":
            return CK.run_local_cdp(spec, self.transport)
        return "error", {"reason": "no check"}, 0

    def _run_check(self, cid, by) -> dict:
        spec = _spec(cid)
        self._require_testable(spec)
        if cid in self._inflight:
            raise Refused(f"{spec.label} is being checked already", 409)
        self._inflight.add(cid)
        try:
            cred = self.credential(cid)
            sig = self._sig(spec)
            state, ev, _ = self._check_values(spec, cred)
        except NotConnected:
            raise
        finally:
            self._inflight.discard(cid)
        now = self.clock()
        kind = "local" if spec.check.kind == "local" else "remote"
        self._update(cid, lambda r: self._push(r, {"state": state, "checked_at": now, "check_id": spec.check.kind, "by": by, "kind": kind,
                                                   "evidence": ev, "sig": sig}))
        self._log(cid, "test", by, state == "connected", state)
        return self._view_of(spec, self._rec(cid))

    def test(self, cid, by="user") -> dict:
        self._gate(by)
        return self._run_check(cid, by)

    def poll(self) -> list:
        """C2: every 30 min, only connections whose route is on and that were used in the last day; reads only; never two at once."""
        now = self.clock()
        done = []
        data = self._read()["connections"]
        for spec in R.SPECS.values():
            if spec.check.kind not in ("http", "mcp", "cli") or not spec.route or not self.route_on(spec.route):
                continue
            rec = data.get(spec.id, {})
            if now - (rec.get("last_used") or 0) > USED_WITHIN_S:
                continue
            last = max((c.get("checked_at", 0) for c in rec.get("checks") or [] if c.get("kind") == "remote"), default=0)
            if now - last < POLL_EVERY_S:
                continue
            try:
                self._run_check(spec.id, "poll")
                done.append(spec.id)
            except Refused:
                continue
        return done
