# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The hub's read half: the status of every connection (CONNECTIONS.md section 3), computed by the server from the record, the host and
the last checks, never by the client. A view carries no secret, no pointer's contents and no environment value: a variable NAME, a PATH,
a store kind and a fingerprint at most."""

from . import registry as R
from . import sources as S
from .errors import Refused

STATES = ("connected", "signed_out", "expired", "missing", "error", "not_checked")


def _spec_or_refuse(cid):
    try:
        return R.get(cid)
    except R.UnknownConnection as exc:
        raise Refused(str(exc), 404) from None


class Views:
    def view(self, ids=None) -> list:
        specs = [_spec_or_refuse(i) for i in ids] if ids else list(R.SPECS.values())
        data = self._read()["connections"]
        return [self._view_of(s, data.get(s.id, {})) for s in specs]

    def one(self, cid: str) -> dict:
        spec = _spec_or_refuse(cid)
        rec = self._rec(cid)
        v = self._view_of(spec, rec)
        v["sources"] = [s.public() for s in self._sources(spec, rec)]
        v["host_files"] = S.host_paths(spec, self.home)
        v["uses"] = R.uses_of(cid)
        v["history"] = [{k: c.get(k) for k in ("state", "checked_at", "check_id", "by", "kind")} for c in (rec.get("checks") or [])[-10:]]
        return v

    # ------------------------------------------------------------------------------------------------------------------
    def _last_check(self, spec, rec, sig):
        for c in reversed(rec.get("checks") or []):
            if c.get("sig") == sig:
                return c
        return None

    def _state_of(self, spec, rec, sources, src) -> dict:
        """{state, check, next_step, check_kind, extra} for one connection."""
        label = spec.label
        if spec.future:
            return {"state": "missing", "next_step": f"{label} is not available in Lampway yet", "check_kind": "none"}
        if spec.kind == "none":
            return {"state": "connected", "next_step": spec.note, "check_kind": "none"}
        if spec.kind == "local_account":
            return {"state": "connected", "next_step": "this server is running", "check_kind": "local"}
        if spec.id == "mcp_clients":
            return {"state": "not_checked", "next_step": spec.note, "check_kind": "none"}
        if spec.id == "byok_legacy":
            return ({"state": "not_checked", "next_step": spec.note, "check_kind": "none"} if self.byok_present()
                    else {"state": "missing", "next_step": "nothing is stored here", "check_kind": "none"})
        if src is None:
            signin = next((s for s in sources if s.mode == "signin"), None)
            if signin is not None and signin.extra.get("set_up"):
                named = getattr(self.oauth.get(spec.id), "connection_state", lambda: {})() or {}
                return {"state": "signed_out", "next_step": named.get("next_step") or f"{label} is signed out: sign in again in Connections",
                        "check_kind": "local"}
            return {"state": "missing", "next_step": f"{label} is not connected: connect it in Connections", "check_kind": "none"}
        if src.error:
            return {"state": "error", "next_step": src.error, "check_kind": "local"}
        if not src.present:
            return {"state": "missing", "next_step": f"{label} is not connected: connect it in Connections", "check_kind": "none"}
        sig = src.sig
        last = self._last_check(spec, rec, sig)
        if src.mode == "signin":
            st = self.oauth[spec.id].status()
            out = {"state": "connected", "next_step": "", "check_kind": "local", "expires_at": st.get("expires_at"), "scopes": st.get("scopes") or []}
            if st.get("plan_usage_enabled") is False:
                out.update(state="error", next_step=f"{label}: plan usage is not enabled for this sign-in: sign in again and allow it")
            if hasattr(self.oauth[spec.id], "connection_state"):
                extra = self.oauth[spec.id].connection_state()
                if extra:
                    out.update(extra)
            if last and last.get("kind") in ("remote", "use") and last.get("checked_at", 0) >= (rec.get("source_changed_at") or 0):
                out["check"] = last
                if last["state"] != "connected":
                    out.update(state=last["state"], next_step=(last.get("evidence") or {}).get("reason") or out["next_step"])
            return out
        if last is not None:
            ev = last.get("evidence") or {}
            nxt = {"connected": "", "expired": f"{label} refused the key: paste a new one in Connections",
                   "signed_out": f"{label} is signed out: sign in again", "error": ev.get("reason") or "the check failed"}.get(last["state"], "")
            return {"state": last["state"], "next_step": nxt, "check": last, "check_kind": "remote" if last.get("kind") != "local" else "local"}
        if src.mode == "host":
            text = ("installed; status not read" if spec.binary else "the tool browser's profile exists: press Test to see whether it is open")
            return {"state": "not_checked", "next_step": text, "check_kind": "none"}
        if spec.check.kind in ("none", "local"):
            return {"state": "not_checked", "next_step": f"{label} has no check that costs nothing: its status is read on this machine only", "check_kind": "none"}
        return {"state": "not_checked", "next_step": "press Test to check it", "check_kind": "none"}

    def _view_of(self, spec, rec) -> dict:
        if spec.derived_from:
            parent = self._view_of(R.get(spec.derived_from), self._rec(spec.derived_from))
            on = self.route_on(spec.route)
            parent.update(id=spec.id, label=spec.label, group=spec.group, kind="derived", route={"id": spec.route, "on": on},
                          derived_from=spec.derived_from, fingerprint=None, active_source={"mode": "derived", "label": f"from {parent['label']}"})
            parent["qualifiers"] = [q for q in parent["qualifiers"] if q != "route_off"] + (["route_off"] if parent["state"] == "connected" and not on else [])
            return parent
        sources = self._sources(spec, rec)
        src, conflict = self._active(spec, sources, rec)
        st = self._state_of(spec, rec, sources, src)
        now = self.clock()
        check = st.get("check")
        on = self.route_on(spec.route)
        qualifiers = []
        if st["state"] == "connected":
            exp = st.get("expires_at")
            if exp and exp - now < 24 * 3600 and st.get("refreshable") is False:
                qualifiers.append("warning")
            ev = (check or {}).get("evidence") or {}
            if ev.get("tier") == "free":
                qualifiers.append("warning")
            if spec.route and not on:
                qualifiers.append("route_off")
        ev = (check or {}).get("evidence") or {}
        fp = (rec.get("manual") or {}).get("fingerprint") if src is not None and src.mode == "manual" else None      # never from a value Lampway does not hold
        next_step = st["next_step"]
        if st["state"] == "connected" and spec.route and not on:
            next_step = f"{spec.label} is connected but its route is off: switch it on in Privacy"
        return {"id": spec.id, "label": spec.label, "group": spec.group, "kind": spec.kind, "state": st["state"],
                "qualifiers": sorted(set(qualifiers)), "route": {"id": spec.route, "on": on} if spec.route else None,
                "active_source": {"mode": src.mode, "label": src.label} if src is not None else None,
                "identity": {"masked": ev.get("masked"), "plan": ev.get("plan"), "tier": ev.get("tier"),
                             "balance": dict(ev["balance"], as_of=check.get("checked_at")) if ev.get("balance") else None},
                "scopes": st.get("scopes") or [], "expires_at": st.get("expires_at"),
                "checked_at": check.get("checked_at") if check else None,
                "check_age_s": int(now - check["checked_at"]) if check and check.get("checked_at") else None,
                "check_kind": st.get("check_kind", "none"), "fingerprint": fp, "conflict": conflict, "next_step": next_step,
                "unused": spec.unused, "note": spec.note}
