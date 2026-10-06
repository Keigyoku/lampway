"""The orphan tools that run on the SERVER (STATUS.md ORPHANS), never in Blender: one module so ``tools.py`` and ``turns.py`` each carry one line for all of
them. ``call(hub, name, arguments)`` returns (text, is_error) like every other server tool family."""

import asyncio
import json

from .providers.base import ToolSpec

NAMES: set = set()


def _obj(props, req=()):
    return {"type": "object", "properties": props, "required": list(req), "additionalProperties": False}


def specs() -> list:
    return [
        ToolSpec("lampway_slot_register", "The slot register: a typed, dated, append-only record of every model or Studio slot (tripo.mesh, meshy.remesh, rodin.partial_edit, "
                 "arbor ...): its evidence class (paper | repo | demo_shell | caption_demo | official_docs | local_measured), whether a driver exists, the eligibility the "
                 "user stated, the last price read back and when. action list (family, runnable_only) answers what can actually run now: runnable = a driver in the "
                 "Studio catalog (or a server route), evidence not a research class, not expired; rows whose read-back (else record date) is over 30 days old are "
                 "stale [UNVERIFIED policy]. show (slot) gives its history; record (slot, row {evidence, driver_exists, eligibility, price_read_back, read_back_at, "
                 "source}) appends a row (you record as the agent; eligibility is only the user's; a price needs its read-back date); expire (slot) marks the "
                 "read-back gone. Refused: driver_exists for a slot with no catalog action, a research evidence class with a driver. Nothing is run or spent.",
                 _obj({"action": {"type": "string", "description": "list | show | record | expire"}, "slot": {"type": "string"},
                       "row": {"type": "object", "description": "record: {evidence, driver_exists, eligibility, price_read_back, read_back_at, source}"},
                       "family": {"type": "string"}, "runnable_only": {"type": "boolean"}}, ["action"])),
        ToolSpec("lampway_studio_cross_pass", "Use one Studio's tool on another Studio's mesh, recorded as lineage in the ONE seed catalogue. verb plan: the mesh "
                 "(a saved copy, never the original) goes to a MESH-TAKING action of to_studio (meshy.remesh | meshy.uv_unwrap | meshy.retexture | hyper3d.texture_only | "
                 "hyper3d.bang | hi3d.texture_only | hi3d.split | tripo.rest.texture | tripo.rest.decimate) through that Studio's own plan: its price is read back and "
                 "only the user confirms it in the Studios panel; needs parent_id (the source's catalogue id). A Tripo Studio browser action has no upload verb: "
                 "refused, never assumed. verb record: after the confirmed job, its result file becomes a child version (parent_id, studio, action, piece; root=true "
                 "only for a first source); a result identical to its parent is flagged no_op_pass. verb lineage (id): the chain of versions A -> B -> A. The "
                 "proportion score of a result is the proportion tools' (then seed_catalog ingest_scores).",
                 _obj({"verb": {"type": "string", "description": "plan | record | lineage"}, "mesh": {"type": "string"}, "from_studio": {"type": "string"},
                       "to_studio": {"type": "string"}, "action": {"type": "string"}, "args": {"type": "object"}, "parent_id": {"type": "string"},
                       "file": {"type": "string"}, "studio": {"type": "string"}, "piece": {"type": "string"}, "root": {"type": "boolean"}, "id": {"type": "string"}},
                      ["verb"])),
    ]


NAMES.update(t.name for t in specs())


async def call(hub, name: str, arguments: dict) -> tuple:
    a = arguments if isinstance(arguments, dict) else {}
    if name == "lampway_slot_register":
        from .. import slots as SL
        reg = SL.SlotRegister(SL.default_path())
        act = a.get("action")
        try:
            if act == "list":
                return json.dumps({"rows": reg.list(str(a.get("family") or ""), bool(a.get("runnable_only")))}), False
            if act == "show":
                return json.dumps(reg.show(str(a.get("slot") or ""))), False
            if act == "record":
                row = dict(a.get("row") or {}, by="agent")
                return json.dumps({"row": await asyncio.to_thread(reg.record, str(a.get("slot") or ""), row)}), False
            if act == "expire":
                return json.dumps({"row": reg.expire(str(a.get("slot") or ""), by="agent")}), False
            return "action is list | show | record | expire", True
        except SL.SlotError as exc:
            return str(exc), True
    if name == "lampway_studio_cross_pass":
        from .. import crosspass as XP
        from ..seeds import Catalog
        from . import server_tools as SVT
        verb = a.get("verb")
        try:
            cp = XP.CrossPass(Catalog(), getattr(hub, "studio", None))
            if verb == "plan":
                if cp.studio is None:
                    return "the Studio service is not available on this server", True
                return json.dumps(await cp.plan(str(a.get("mesh") or ""), str(a.get("from_studio") or ""), str(a.get("to_studio") or ""), str(a.get("action") or ""),
                                                a.get("args") or {}, str(a.get("parent_id") or ""), "agent"), default=str), False
            if verb == "record":
                row = await asyncio.to_thread(cp.record, str(a.get("parent_id") or ""), str(a.get("piece") or ""), SVT.jail(str(a.get("file") or "")),
                                              str(a.get("studio") or ""), str(a.get("action") or ""), bool(a.get("root")))
                return json.dumps({"row": row}), False
            if verb == "lineage":
                return json.dumps({"chain": XP.lineage(cp.cat, str(a.get("id") or ""))}), False
            return "verb is plan | record | lineage", True
        except (XP.CrossPassError, SVT.BadToolCall, ValueError) as exc:
            return str(exc), True
    return f"unknown orphan server tool {name!r}", True
