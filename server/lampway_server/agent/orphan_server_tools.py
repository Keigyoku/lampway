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
        ToolSpec("lampway_vision_judge", "Judge frames or one native video with a vision model through OpenRouter, answered as a STRICT JSON verdict: PASS | FAIL | "
                 "INCONCLUSIVE with timestamped findings, per-criterion verdicts and limitations. purpose judge (generic) | locomotion | air | combat | moment "
                 "selects the criteria prompt; reference adds a second stream labelled reference. Anything but the strict JSON is INCONCLUSIVE (status failed), "
                 "never PASS; INCONCLUSIVE is never upgraded (the verdict is the worse of the model's and every criterion's). Private content (the default) "
                 "goes only to a model on OpenRouter's live ZDR list with data_collection=deny, never a ':free' model; none eligible = nothing sent. dry_run "
                 "(default true) returns the plan: the prompt, media, estimated bytes; dry_run=false sends, charged to the session spend ceiling, and writes a "
                 "receipt under <root>/vision/receipts (the same media and purpose are answered from it with no call). A judge's claims are advisory: they "
                 "count only where a measured gate agrees. Refused: a folder mixing frames and video, over 64 frames, over the 19,000,000-byte request cap.",
                 _obj({"media": {"type": "string", "description": "a frames folder or one image or video under the project root"},
                       "purpose": {"type": "string", "description": "judge | locomotion | air | combat | moment"},
                       "reference": {"type": "string", "description": "an optional reference stream of the same modality"},
                       "prompt": {"type": "string", "description": "extra context appended to the purpose prompt"},
                       "content_class": {"type": "string", "description": "private (default) | public"},
                       "model": {"type": "string", "description": "pin one eligible model (else the first eligible by preference)"},
                       "bounds": {"type": "array", "items": {"type": "number"}, "description": "the source seconds this media covers (recorded)"},
                       "dry_run": {"type": "boolean"}}, ["media", "purpose"])),
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
    if name == "lampway_vision_judge":
        from .. import vision_judge as VJ
        from . import server_tools as SVT
        root = SVT.project_root()
        try:
            media = SVT.jail(str(a.get("media") or ""))
            ref = SVT.jail(str(a["reference"])) if a.get("reference") else None
            cc = str(a.get("content_class") or "private")
            if cc not in ("private", "public"):
                return "content_class is private | public", True
            if a.get("dry_run", True) is not False:
                p = VJ.VisionJudge("", receipts=None).plan(media, str(a.get("purpose") or ""), str(a.get("prompt") or ""), ref)
                return json.dumps({"dry_run": True, "purpose": p["purpose"], "modality": p["modality"], "media": len(p["media"]), "reference": len(p["reference"]),
                                   "estimated_request_bytes": p["estimated_request_bytes"], "prompt": p["text"], "content_class": cc,
                                   "help": ["dry_run=false sends it (charged to the session spend ceiling)"]}), False
            from .. import provider_prefs
            from .providers import spend_ledger
            from .providers.openrouter import KeyMissing, resolve_api_key
            try:
                key = resolve_api_key()
            except KeyMissing as exc:
                return str(exc), True
            j = VJ.VisionJudge(key, receipts=root / "vision" / "receipts", ledger=spend_ledger(provider_prefs.effective()))
            r = await asyncio.to_thread(j.judge, media, str(a.get("purpose") or ""), str(a.get("prompt") or ""), ref, cc, a.get("model") or None, a.get("bounds"))
            keep = ("status", "verdict", "model_verdict", "downgraded_by", "findings", "limitations", "schema_errors", "model", "cost_usd", "receipt", "noop", "refused")
            return json.dumps({k: r[k] for k in keep if k in r}, default=str), r.get("status") == "refused"
        except (SVT.BadToolCall, ValueError, OSError) as exc:
            return str(exc), True
    return f"unknown orphan server tool {name!r}", True
