# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native transcript invalidation and atomic, read-only display snapshots.

No transcript is stored here. The registered native history projection remains
the authority, including durable row IDs, ancestor lineage and media handling.
"""
import functools
import contextlib

METHOD = "lampway.history_snapshot"
MODULES = frozenset({"tui_gateway.server"})


def revision(session):
    value = session.get("history_version", 0)
    return value if type(value) is int and value >= 0 else 0


def install_module(module):
    if module.__name__ != "tui_gateway.server" or not hasattr(module, "_emit"):
        return
    if not getattr(module._emit, "_lampway_history_guarded", False):
        original = module._emit
        @functools.wraps(original)
        def emit(event, sid, payload=None):
            if event == "session.info" and isinstance(payload, dict):
                session = module._sessions.get(sid)
                if session is not None:
                    marker = {"protocol": 1, "revision": revision(session)}
                    incoming = payload.get("lampway_history")
                    if isinstance(incoming, dict) and incoming.get("reason") == "undo":
                        marker["reason"] = "undo"
                    payload = {**payload, "lampway_history": marker}
            return original(event, sid, payload)
        emit._lampway_history_guarded = True
        module._emit = emit
    history = module._methods.get("session.history")
    if history is not None and METHOD not in module._methods:
        from pydantic import BaseModel, ConfigDict, create_model
        contract = module._contracts.METHODS["session.history"]
        class SnapshotBase(BaseModel):
            model_config = ConfigDict(extra="forbid")
        result_type = create_model("LampwayHistorySnapshot", __base__=SnapshotBase,
            protocol=(int, ...), session_id=(str, ...), revision=(int, ...), history=(contract.result, ...))
        module._contracts.METHODS[METHOD] = type(contract)(name=METHOD, params=contract.params,
            result=result_type, doc="Read-only native display projection with its locked native revision.")
        def snapshot(rid, params):
            if not isinstance(params, dict) or type(params.get("session_id")) is not str or not params["session_id"]:
                return module._err(rid, 4000, "invalid native session id")
            try:
                contract.params.model_validate(params)
            except ValueError:
                return module._err(rid, 4000, "invalid history snapshot parameters")
            session, error = module._sess_nowait(params, rid)
            if error:
                return error
            sid = params.get("session_id")
            with session["history_lock"]:
                # A removed/replaced runtime must never revive its old rows.
                current, error = module._sess_nowait(params, rid)
                if error:
                    return error
                if current is not session:
                    return module._err(rid, 4001, "session changed")
                if session.get("running"):
                    return module._err(rid, 4009, "history snapshot requires an idle session")
                # Native display history includes archived compacted rows; the
                # public history RPC instead projects the active model context.
                fallback = list(session.get("display_history_prefix") or []) + list(session.get("history") or [])
                with module._session_db(session) as db:
                    visible = module._live_visible_history(session, db, fallback)
                messages = module._history_to_messages(visible, profile_home=session.get("profile_home"))
                response = module._ok(rid, {"count": len(visible), "messages": messages})
                if module._sessions.get(sid) is not session:
                    return module._err(rid, 4001, "session changed")
                return module._ok(rid, {"protocol": 1, "session_id": sid,
                    "revision": revision(session), "history": response["result"]})
        module.register_method(METHOD, snapshot)
    undo = module._methods.get("session.undo")
    if undo is not None and not getattr(undo, "_lampway_history_guarded", False):
        @functools.wraps(undo)
        def changed(rid, params):
            response = undo(rid, params)
            if response.get("result", {}).get("removed", 0) > 0:
                sid = params.get("session_id")
                session = module._sessions.get(sid)
                if session is not None:
                    # Notification failure cannot turn a completed undo into a
                    # failed command that a client might repeat.
                    with contextlib.suppress(Exception):
                        info = module._fallback_session_info(session)
                        module._emit("session.info", sid, {**info, "lampway_history": {"reason": "undo"}})
            return response
        changed._lampway_history_guarded = True
        module._methods["session.undo"] = changed
