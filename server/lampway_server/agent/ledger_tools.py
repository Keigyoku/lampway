"""The agent's experiment-ledger tools. The agent records as ``agent`` always (it can never claim to be the user), so it can reject a spend result but never
choose one."""

import asyncio
import json

from ..ledger import Ledger, LedgerError
from .providers.base import ToolSpec

NAMES = {"lampway_ledger_record", "lampway_ledger_list", "lampway_ledger_compare", "lampway_ledger_receipt"}
JOB_NAMES = {"lampway_job_services"}


def specs() -> list:
    obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req), "additionalProperties": False}  # noqa: E731
    return [
        ToolSpec("lampway_ledger_record", "Append one run to the experiment ledger (never edited: correct with `supersedes`). piece, stage (image|mesh|uv|texture|pbr|video|motion|"
                 "rig|fit|export|decision|other), studio, settings read back, seed or 'not_exposed', hashes, cost {subscription, generation_credits + price_source, "
                 "developer_api_usd, work_s}, verdict, reason. You record as the agent: you may reject a spend result, only the user chooses one.",
                 obj({"run": {"type": "object"}}, ["run"])),
        ToolSpec("lampway_ledger_list", "The ledger's experiment rows for a piece and/or stage (superseded rows hidden).", obj({"piece": {"type": "string"}, "stage": {"type": "string"}})),
        ToolSpec("lampway_ledger_compare", "Two or more runs side by side: the settings that differ, the seeds, whether the outputs changed, cost and verdicts.",
                 obj({"ids": {"type": "array", "items": {"type": "string"}}}, ["ids"])),
        ToolSpec("lampway_job_services", "Read-only: which of the Client's generation job types (image_gen, retopology, tripo_rig, video_gen ...) this server backs, with "
                 "whether each spends (a spend service waits for the user's confirm in the Studios panel), its backend, models and queue length, and which job types are "
                 "unbacked. Plan only what is listed.", obj({})),
        ToolSpec("lampway_ledger_receipt", "What a piece cost: generation credits, developer-API dollars, work seconds and the subscription notes, summed separately.",
                 obj({"piece": {"type": "string"}}, ["piece"])),
    ]


def job_services(jobs) -> str:
    return json.dumps(jobs.service_report() if jobs is not None else {"services": [], "unbacked": []})


async def call(svc, name: str, arguments: dict) -> tuple:
    a = arguments if isinstance(arguments, dict) else {}
    ledger = Ledger(svc.runlog.path)
    try:
        if name == "lampway_ledger_record":
            run = dict(a.get("run") or {}, by="agent")
            return json.dumps(await asyncio.to_thread(ledger.record, run)), False
        if name == "lampway_ledger_list":
            return json.dumps({"rows": ledger.list(a.get("piece"), a.get("stage"))}), False
        if name == "lampway_ledger_compare":
            return json.dumps(ledger.compare([str(i) for i in a.get("ids") or []])), False
        if name == "lampway_ledger_receipt":
            return json.dumps(ledger.receipt(str(a.get("piece") or ""))), False
    except LedgerError as exc:
        return str(exc), True
    return f"unknown ledger tool {name!r}", True
