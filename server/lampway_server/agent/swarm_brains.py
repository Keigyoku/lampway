# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What thinks inside a swarm worker (docs/reports/agent-modes-spec.md S1).

The swarm's substrate (spawn, bind, reset, seed, stage, collect, commit, revoke, shutdown; ``agent/swarm.py``) is one implementation
for both modes. A **brain** only thinks: it gets a ``WorkerJob`` and returns the worker's one-sentence summary, or raises to fail the
task. Its only door to a scene is ``job.call_tool``, which runs on THIS worker's headless Lampway, so no brain can reach the user's
scene or another worker's.

* ``BuiltinBrain``: Lampway's own loop on the ``agent.worker`` provider (what every swarm used before the Mode system).
* ``engine`` (Mode 1, S2) and ``pane`` (Mode 2, S3) brains live in ``engine/`` and ``herdr/``.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from .providers.base import Message, ModelRequest, Text, ToolCall

MAX_WORKER_ROUNDS = 24
MODEL_ROUND_TIMEOUT_S = 300.0      # one model call (a headless CLI process can wedge); the worker fails, the others go on


@dataclass
class WorkerJob:
    worker: object                                            # swarm.Worker: id, name, prompt, objects, status, created, calls
    system: str                                               # worker_system_prompt(worker)
    tools: list                                               # worker_tools(): never the swarm, the studios, ask_user or panes
    call_tool: Callable[[str, dict], Awaitable[tuple]]       # (name, arguments) -> (text, is_error) on this worker's Lampway
    progress: Callable[[str], None] = lambda text: None
    meta: dict = field(default_factory=dict)                  # the swarm id, the parent session and turn: for brains that need them


class WorkerBrain(Protocol):
    kind: str

    async def run(self, job: WorkerJob) -> str: ...

    async def stop(self, job: WorkerJob) -> None: ...


class BuiltinBrain:
    """Lampway's own model loop: up to ``MAX_WORKER_ROUNDS`` rounds on the worker's provider, every tool call through the job."""
    kind = "builtin"

    def __init__(self, provider_factory: Callable[[str], object], *, round_timeout_s: float = MODEL_ROUND_TIMEOUT_S):
        self.provider_factory = provider_factory
        self.round_timeout_s = round_timeout_s

    async def run(self, job: WorkerJob) -> str:
        worker = job.worker
        provider = self.provider_factory(worker.id)
        worker.choice = getattr(provider, "choice", None)
        messages = [Message.user_text(worker.prompt)]
        for _round in range(MAX_WORKER_ROUNDS):
            text, calls = await self.model_round(provider, ModelRequest(job.system, list(messages), job.tools), self.round_timeout_s)
            messages.append(Message("assistant", ([{"type": "text", "text": text}] if text else []) + [
                {"type": "tool_call", "id": c.id, "name": c.name, "arguments": c.arguments} for c in calls]))
            if not calls:
                if not text.strip() and worker.tool_calls == 0:      # nothing said, nothing done: not a finished task
                    raise RuntimeError("the model returned an empty response")
                return text.strip() or "(no summary)"
            results = []
            for call in calls:
                content, is_error = await job.call_tool(call.name, call.arguments)
                results.append({"type": "tool_result", "tool_call_id": call.id, "content": content, "is_error": is_error})
            messages.append(Message("user", results))
        raise RuntimeError("stopped after too many tool calls")

    async def stop(self, job: WorkerJob) -> None:
        return None                       # the worker's task is cancelled by the swarm; the loop has nothing of its own to stop

    @staticmethod
    async def model_round(provider, request, timeout_s: float = MODEL_ROUND_TIMEOUT_S) -> tuple:
        async def one():
            text_parts, calls = [], []
            async for event in provider.stream(request):
                if isinstance(event, Text):
                    text_parts.append(event.text)
                elif isinstance(event, ToolCall):
                    calls.append(event)
            return "".join(text_parts), calls
        try:
            return await asyncio.wait_for(one(), timeout_s)
        except asyncio.TimeoutError:
            raise RuntimeError(f"the model did not answer within {timeout_s:.0f}s") from None
