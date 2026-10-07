# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mode 1 swarm workers (docs/reports/agent-modes-spec.md S2): each worker thinks as its own Hermes engine session.

* Its home is ``<state>/agent/hermes/<parent session>/workers/<swarm>-<worker>``: the worker's conversation stays in Hermes beside
  its parent's (Hermes owns durability, captain 2026-10-07).
* Its model is the gateway, answered on the ``agent.worker`` choice (``EngineRuntime.provider_for``), never the main provider.
* Its tools are its job's ``worker_tools()`` on its own MCP endpoint, every call through ``WorkerJob.call_tool`` (its own headless
  Lampway); its config is the parent's capability choices minus what would let it act outside its task (``worker=True``).
* It is never asked a question and asks none; its last words are its summary. Hermes's own ``delegate_task`` stays off.
"""

from pathlib import Path

from ..agent.swarm_brains import WorkerJob


class EngineBrain:
    kind = "engine"

    def __init__(self, runtime, provider_factory=None):
        self.runtime = runtime
        self.provider_factory = provider_factory

    @staticmethod
    def key(job: WorkerJob) -> str:
        return f"{job.meta.get('session_id', '')}:worker:{job.meta.get('swarm_id', '')}:{job.worker.id}"

    def home(self, job: WorkerJob) -> Path:
        return (self.runtime.state_dir / "agent" / "hermes" / str(job.meta.get("session_id", "")) / "workers"
                / f"{job.meta.get('swarm_id', '')}-{job.worker.id}")

    async def run(self, job: WorkerJob) -> str:
        provider = self.provider_factory(job.worker.id) if self.provider_factory is not None else None
        job.worker.choice = getattr(provider, "choice", None)
        prompt = f"{job.system}\n\nYour task:\n{job.worker.prompt}"
        summary = await self.runtime.run_worker(self.key(job), self.home(job), prompt, tools=job.tools, tool_router=job.call_tool,
                                                provider=provider, on_progress=job.progress)
        if not summary and job.worker.tool_calls == 0:            # nothing said, nothing done: not a finished task
            raise RuntimeError("the worker's engine returned an empty response")
        return summary or "(no summary)"

    async def stop(self, job: WorkerJob) -> None:
        await self.runtime.stop(self.key(job))
