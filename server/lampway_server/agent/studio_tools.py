"""The agent's Studio tools: PLAN and READ only. A plan reads the price back from Studio and puts an approval in front of the captain
in the Client; it clicks nothing and spends nothing. There is deliberately no tool that confirms: the captain's click in the Client
(a REST route an agent holds no token for) is the only approval."""

import json

from ..studios.actions import ACTIONS, ActionError
from ..studios.approvals import ApprovalError
from .providers.base import ToolSpec

NAMES = {"studio_plan", "studio_job", "studio_actions"}


def specs() -> list:
    return [
        ToolSpec("studio_actions", "List the online Studio actions (Tripo today; Meshy and Hi3D when their drivers exist): what each does, "
                 "whether it needs the captain's approval and the price it must read back.",
                 {"type": "object", "properties": {}, "additionalProperties": False}),
        ToolSpec("studio_plan", "Ask a Studio to do something. Free steps (state, clone, retry, pick, save, fetch...) run at once as a server "
                 "job. An action that spends credits (tripo.mesh, tripo.texture, tripo.pbr, tripo.image, tripo.uv.unwrap) is only PLANNED: "
                 "the driver sets every setting and reads the price back, nothing is clicked, and the captain gets a confirm card in the "
                 "Client with that price. You cannot confirm it; tell the user it is waiting and carry on. Laws enforced for you: 4 variants "
                 "at maximum polycount, a saved copy only, texturing last, paired pieces (paired=true) send front+back only, a hung job is "
                 "never re-clicked. Paths are inside the project root.",
                 {"type": "object", "properties": {"action": {"type": "string"}, "args": {"type": "object"}},
                  "required": ["action"], "additionalProperties": False}),
        ToolSpec("studio_job", "Read one Studio job (state, what the driver reported, the files it made) or, with no job_id, all jobs and "
                 "pending approvals. Poll this after the captain has confirmed.",
                 {"type": "object", "properties": {"job_id": {"type": "string"}}, "additionalProperties": False}),
    ]


async def call(service, name: str, arguments: dict) -> tuple:
    """(text for the model, is_error)."""
    arguments = arguments if isinstance(arguments, dict) else {}
    try:
        if name == "studio_actions":
            return json.dumps([{"id": a.id, "studio": a.studio, "label": a.label, "needs_approval": a.needs_approval,
                                "expected_price": a.expected_price} for a in ACTIONS.values()]), False
        if name == "studio_plan":
            out = await service.plan(str(arguments.get("action") or ""), arguments.get("args") or {}, by="agent")
            return json.dumps(out, default=str), out.get("state") == "refused"
        if name == "studio_job":
            jid = arguments.get("job_id")
            if jid:
                job = service.job(str(jid))
                return (json.dumps(job, default=str), False) if job else (f"no job {jid!r}", True)
            return json.dumps({"jobs": service.jobs(), "approvals": service.approvals()}, default=str), False
    except (ActionError, ApprovalError) as exc:
        return str(exc), True
    return f"unknown studio tool {name!r}", True
