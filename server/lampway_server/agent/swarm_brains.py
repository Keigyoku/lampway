# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""What thinks inside a swarm worker (docs/reports/agent-modes-spec.md S1, as superseded by A).

The swarm's substrate (spawn, bind, reset, seed, stage, collect, commit, revoke, shutdown; ``agent/swarm.py``) is one implementation
for both modes. A **brain** only thinks: it gets a ``WorkerJob`` and returns the worker's one-sentence summary, or raises to fail the
task. Its only door to a scene is ``job.call_tool``, which runs on THIS worker's headless Lampway, so no brain can reach the user's
scene or another worker's.

There is one brain (captain, 2026-10-07: every agent is a process in a pane on Lampway's herdr server; no agent runs without a
pane): ``herdr/swarm_brain.py`` ``PaneBrain``. The unit's mode picks the adapter its pane starts through
(``herdr.harnesses.worker_adapter``), not the brain. Lampway's own worker loop and the engine's hidden Hermes children are gone (A5).
"""

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol


@dataclass
class WorkerJob:
    worker: object                                            # swarm.Worker: id, name, prompt, objects, status, created, calls
    system: str                                               # worker_system_prompt(worker)
    tools: list                                               # worker_tools(): never the swarm, the studios, ask_user or panes
    call_tool: Callable[[str, dict], Awaitable[tuple]]       # (name, arguments) -> (text, is_error) on this worker's Lampway
    progress: Callable[[str], None] = lambda text: None
    meta: dict = field(default_factory=dict)                  # the swarm id, the parent session (the unit) and turn


class WorkerBrain(Protocol):
    kind: str

    async def run(self, job: WorkerJob) -> str: ...

    async def stop(self, job: WorkerJob) -> None: ...
