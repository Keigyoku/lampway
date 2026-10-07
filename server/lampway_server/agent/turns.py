"""The agent hub: the client protocol's front end for Mode 1 (docs/reports/agent-modes-spec.md A2, A5).

Mode 1 runs only on Hermes, in the unit's herdr pane: ``self.engine`` (``engine/front.HermesFront``) drives every turn, and the
agent's conversation, rounds, history, compression and retries are Hermes's (A0). Lampway's own provider loop is gone (A5). With no
engine on this server a Mode 1 ``agent.chat`` or ``agent.input`` is refused before any turn starts (``engine_refusal``, with what
``engine/wiring.py`` found), and nothing answers in the engine's place. What stays here is the protocol the client renders, the
journal ``agent.attach`` replays, the tool door ``_run_tool`` the engine's MCP endpoint calls (A3), and the swarm substrate.

The client's contract (turn_events.py, queue_processor.py, slot_processor.py):
  * agent.chat is acknowledged with an admission receipt {state: "pending"};
  * agent.turn.started carries turn_id == command_id, and must precede
    agent.command.result (which pops the command from the client's registry);
  * agent.turn.event seq starts at 0 per turn and is contiguous; a gap makes the
    client call agent.attach with its last rendered seq;
  * the first payload is {type: run_status, status: in_progress}; everything
    with a bubble_id is a slot update; the last payload is {type: turn_end};
  * agent.turn.ended carries last_seq; the client re-attaches if it missed any;
  * blender.execute_script must arrive after turn.started with
    session_id / agent_ctx.chat_session_id equal to the chat session.
"""

import asyncio
import copy
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .providers.base import ToolCall
from . import server_tools, studio_tools, video_tools, prompt_tools, image_tools, ledger_tools, seed_tools, engine_tools, workbench_tools, compute_tools, vault_tools, cards_tools, files_tools, connections_tools, choices_tools, capabilities_tools, orphan_server_tools, marks_context, questions as Q
from .. import capabilities as CAP
from . import plan_tools
from .swarm import SwarmContext, SwarmManager, is_swarm_tool
from .tools import UnknownTool, format_tool_result, script_for

log = logging.getLogger("lampway.agent")

MODEL_RESULT_CLIP = 20_000          # characters of one tool result the agent is shown (the engine's MCP endpoint clips with it)
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
#: The other mode, named in every refusal of a Mode 1 chat that cannot run here: the user can still work with their own agent.
YOUR_AGENT_HELP = ("Or switch this scene tab to Your agent in the island's agent menu (the mode switch above the model list) and "
                   "work with your own agent in its pane")
#: Why Mode 1 cannot run on this server when nothing better is known: (code, why, the exact fix).
NO_ENGINE = ("engine_not_built", "no finished engine build was found",
             "Build Lampway's pinned Hermes engine: scripts/lampway/engine_env.py (then restart Lampway)")


@dataclass
class Turn:
    session_id: str
    turn_id: str
    run_id: str
    events: list[dict] = field(default_factory=list)  # payloads by seq
    status: str = "running"  # running | ended | abandoned
    task: Optional[asyncio.Task] = None
    asked: bool = False       # stopped on a question from the pane's Hermes: the run stays in progress until the answer
    context: dict = field(default_factory=dict)   # what the client sent beside the message (R3): images, rules, folders, notes
    stream: object = None     # the turn's TurnStream: re-attached to a new socket by agent.attach (A2)
    detached: bool = False    # the client's socket closed while the pane's turn ran: it journals on and waits for agent.attach

    @property
    def last_seq(self) -> int:
        return len(self.events) - 1


@dataclass
class Session:
    session_id: str
    turns: dict[str, Turn] = field(default_factory=dict)
    last_turn_id: Optional[str] = None
    current: Optional[Turn] = None
    pending_question: Optional[dict] = None   # {interrupt_id, call_id, question, engine} while the pane's Hermes waits on the island
    last_user: str = ""                       # the user's latest words in this tab (the island's, or typed in the pane)
    plan_notice_shown: bool = False           # the ChatGPT-plan disclosure was shown in this session's transcript (R0a)


@dataclass
class Command:
    command_id: str
    session_id: str
    state: str = "pending"  # pending | complete
    result: Optional[dict] = None


class AgentHub:
    def __init__(self, provider, *, script_timeout_s: float = 600.0, swarm_provider_factory=None, studio=None, video=None,
                 prompts=None, jobs=None, cockpit=None, assets=None, switch_dir=None):
        self.provider = provider        # the current main provider: the model gateway's door for every Mode 1 pane (E1.4)
        self.engine = None              # engine/front.HermesFront: Mode 1 is the unit's Hermes pane (spec A1, A2); None = no Mode 1 here
        self.engine_problem = NO_ENGINE  # (code, why, fix) while self.engine is None: engine/wiring.py says what it found
        self.client_sockets: dict = {}  # scene session id -> the user's Client socket that last spoke for it (spec A3: where tools go)
        self.assets = assets
        self.studio = studio
        self.video = video
        self.prompts = prompts
        self.jobs = jobs
        self.cockpit = cockpit
        self.ops = None
        if cockpit is not None:
            from ..ops.registry import AgentOps
            import os as _os
            self.ops = AgentOps(cockpit, cockpit.root / "ops", cwd=_os.environ.get("LAMPWAY_PROJECT_ROOT") or ".", switch_dir=switch_dir)
        self.script_timeout_s = script_timeout_s
        self.sessions: dict[str, Session] = {}
        self.commands: dict[str, Command] = {}
        from .byoa import ByoaView
        self.byoa = ByoaView(self)      # spec M0 and B4: a tab in Your agent mode, and its pane shown in the island
        # The agent.worker choice's provider (Choices), kept for the model gateway's Mode 1 workers (spec A1, S2 as superseded by A):
        # no worker thinks inside this server; every one is a pane (spec S1, A5).
        self.swarm_provider_factory = swarm_provider_factory or (lambda label: self.provider)
        self.swarm = SwarmManager(self._blender_script, script_timeout_s=script_timeout_s)
        self.swarm.library = assets
        self.swarm.cockpit = cockpit

    # ------------------------------------------------------------ dispatch
    async def handle(self, socket, method: str, request_id, params: dict):
        handler = {
            "agent.chat": self._chat,
            "agent.input": self._input,
            "agent.cancel": self._cancel,
            "agent.status": self._status,
            "agent.attach": self._attach,
            "agent.request_status": self._request_status,
            "agent.parked_turn": self._parked_turn,
            "agent.feedback": self._feedback,
            "agent.checkpoint.mark": self._checkpoint_mark,
            "agent.checkpoint.rewind": self._checkpoint_rewind,
            "agent.byoa.observe": self.byoa.observe,
            "agent.byoa.send": self.byoa.send,
        }.get(method)
        if handler is None:
            await socket.send_error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")
            return
        self._note_socket(socket, params)
        try:
            result = await handler(socket, params)
        except InvalidParams as exc:
            await socket.send_error(request_id, INVALID_PARAMS, str(exc))
            return
        await socket.reply(request_id, result)

    def _note_socket(self, socket, params: dict) -> None:
        """The scene tabs this Client socket speaks for (spec A3): a tool call from a unit's Hermes, whoever started its turn, goes
        to the socket that last spoke for that tab. A headless worker's socket (it says its role) is never a tab's."""
        if getattr(socket, "role", ""):
            return
        payload = params.get("payload") if isinstance(params.get("payload"), dict) else params
        ids = [payload.get("session_id"), params.get("session_id")] + list(params.get("session_ids") or [])[:32]
        for sid in ids:
            if isinstance(sid, str) and sid:
                self.client_sockets[sid] = socket

    def socket_for(self, session_id: str):
        """The scene tab's current Client socket, or None when no Lampway window speaks for it."""
        return self.client_sockets.get(session_id)

    def socket_closed(self, socket) -> set:
        """The client's socket closed. Returns the turn tasks that outlive it (the socket cancels the rest)."""
        for sid in [s for s, sock in self.client_sockets.items() if sock is socket]:
            del self.client_sockets[sid]
        self.swarm.socket_closed(socket)
        survivors = set()
        for session in self.sessions.values():
            turn = session.current
            if turn is not None and turn.task is not None and getattr(turn, "socket", None) is socket:
                if self.engine is not None and self.engine.is_running(session.session_id):
                    # Spec A2: the island is only a client of the pane's Hermes, whose turn goes on; it journals on here and the
                    # client re-attaches with agent.attach. A Blender call in flight fails (the socket is gone) and the agent is told.
                    turn.detached = True
                    survivors.add(turn.task)
                    continue
                turn.task.cancel()
        return survivors

    def engine_refusal(self) -> dict:
        """Mode 1 cannot run on this server (no engine build, or it could not start): the refusal, before any turn starts. Nothing
        else answers in the engine's place (spec A5)."""
        code, why, fix = self.engine_problem or NO_ENGINE
        return {"state": "complete", "result": {
            "ok": False, "code": code, "status_code": 409,
            "message": f"Lampway Agent runs on Lampway's pinned Hermes engine, and this server is not running it ({why}), so this "
                       "message was not sent.",
            "help": [fix, YOUR_AGENT_HELP]}}

    # ------------------------------------------------------------ commands
    def _session(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            session = self.sessions[session_id] = Session(session_id)
        return session

    async def _chat(self, socket, params):
        command_id, payload = _command_parts(params)
        session_id = str(payload.get("session_id") or "")
        message = payload.get("message")
        if not session_id or not isinstance(message, str):
            raise InvalidParams("payload.session_id and payload.message are required")
        if (refused := self.byoa.refusal(session_id, payload)) is not None:     # spec M0: the tab is in Your agent mode
            return refused
        if self.engine is None:
            return self.engine_refusal()
        if self.engine.has_question(session_id) and message.strip():
            # A new message while the pane's Hermes waits on the island's question: the message is the answer (a permission card
            # takes it as deny unless it names a choice), and the turn goes on in this command's turn (spec A2).
            self._session(session_id).pending_question = None
            self.engine.answer(session_id, message)
            return self._admit(socket, command_id, session_id, None)
        marks = marks_context.describe(payload.get("mark_context"))          # the Scribble marks ride WITH the words
        return await self._message(socket, command_id, session_id, message + ("\n\n" + marks if marks else ""),
                                   {k: payload[k] for k in ("content", "rules", "folder_context", "project_context",
                                                            "attachment_names", "imported_object_names", "plan_required",
                                                            "auto_mode", "user_preferences") if k in payload})

    async def _message(self, socket, command_id, session_id, text: str, context: Optional[dict] = None):
        """The user's words for the unit's Hermes: they join a running turn (R4), else open a turn (A2) once the pane may be reached."""
        if self.engine.is_running(session_id) and text.strip():
            # R4: a message during the pane's turn joins it (the client's queued bubble settles on this ok); no new turn.
            await self.engine.steer(session_id, text)
            return {"state": "complete", "result": {"ok": True, "joined": True}}
        if (refused := await self.engine.precheck(socket, session_id)) is not None:
            return refused                                  # spec A1, A5: no pane for this tab, and this message may not open one
        return self._admit(socket, command_id, session_id, text, context=context)

    async def _input(self, socket, params):
        command_id, payload = _command_parts(params)
        session_id = str(payload.get("session_id") or "")
        text = payload.get("text")
        if not session_id or not isinstance(text, str):
            raise InvalidParams("payload.session_id and payload.text are required")
        if (refused := self.byoa.refusal(session_id, payload)) is not None:
            return refused
        if self.engine is None:
            return self.engine_refusal()
        answers = payload.get("answers")
        session = self._session(session_id)
        pending = session.pending_question
        interrupt_id = str(payload.get("interrupt_id") or "")
        if pending is not None and (not interrupt_id or interrupt_id == pending["interrupt_id"]):
            # The answer to the pane's question (clarify or a permission): the response to serve's request; the turn goes on.
            session.pending_question = None
            self.engine.answer(session_id, Q.single_answer(text, answers, payload.get("action")))
            return self._admit(socket, command_id, session_id, None)
        if answers:
            text = f"{text}\n{answers}" if text else str(answers)
        return await self._message(socket, command_id, session_id, text)

    def _admit(self, socket, command_id, session_id, user_text, context=None):
        session = self._session(session_id)
        if user_text is not None and session.pending_question is not None:
            # A new message instead of an answer: the waiting question is answered with that, so it never stays open.
            self._close_question(session, "The user did not answer this question; they sent a new message instead.")
        command = self.commands[command_id] = Command(command_id, session_id)
        turn = Turn(session_id, command_id, str(uuid.uuid4()), context=dict(context or {}))
        turn.socket = socket  # type: ignore[attr-defined]
        session.turns[command_id] = turn
        session.last_turn_id = command_id
        previous = session.current
        session.current = turn
        turn.task = socket.spawn(self._run_turn(socket, session, turn, command, user_text, previous))
        return {"state": "pending"}

    def _close_question(self, session, answer: str) -> None:
        session.pending_question = None
        engine = self.engine
        if engine is not None and engine.has_question(session.session_id):
            engine.answer(session.session_id, answer)

    async def _cancel(self, socket, params):
        command_id, payload = _command_parts(params)
        session_id = str(payload.get("session_id") or "")
        session = self.sessions.get(session_id)
        cancelled = False
        if session is not None and session.current is not None and session.current.task is not None:
            log.debug("cancelling turn %s", session.current.turn_id)
            cancelled = session.current.task.cancel()
            self.swarm.cancel_session(session.session_id)
        elif session is not None and session.pending_question is not None:
            self._close_question(session, "The user cancelled instead of answering this question.")
            cancelled = True
        elif self.engine is not None and self.engine.is_running(session_id):
            cancelled = await self.engine.interrupt(session_id)     # spec A2: session.interrupt
        log.debug("cancel for session %s -> %s", payload.get("session_id"), cancelled)
        return {"state": "complete", "result": {"ok": True, "cancelled": cancelled}}

    async def _status(self, socket, params):
        turns = {}
        for session_id in list(params.get("session_ids") or [])[:32]:
            session = self.sessions.get(str(session_id))
            if session is None or session.last_turn_id is None:
                continue
            turn = session.turns[session.last_turn_id]
            turns[session.session_id] = {
                "turn_id": turn.turn_id, "run_id": turn.run_id, "replay_available": True,
                "status": turn.status, "active": turn.status == "running", "last_seq": turn.last_seq,
            }
        return {"turns": turns}

    async def _attach(self, socket, params):
        session = self.sessions.get(str(params.get("session_id") or ""))
        turn = session.turns.get(str(params.get("turn_id") or "")) if session else None
        if turn is None:
            return {"status": "unavailable"}
        after = params.get("after_seq", -1)
        seq = after + 1 if isinstance(after, int) else 0
        while seq < len(turn.events):                         # the journal grows while a detached turn runs: catch up first
            await socket.notify("agent.turn.event", {
                "session_id": turn.session_id, "turn_id": turn.turn_id, "seq": seq, "event": turn.events[seq],
            })
            seq += 1
        if turn.status == "running" and turn.detached and turn.stream is not None:
            # no await between the last replayed event and the rebind: the pane's next event goes to the new socket, in order
            turn.stream.socket = socket
            turn.socket = socket  # type: ignore[attr-defined]
            turn.detached = False
            if self.engine is not None:
                self.engine.reattach(session.session_id, socket)
        if turn.status != "running":
            await socket.notify("agent.turn.ended", {
                "session_id": turn.session_id, "turn_id": turn.turn_id, "last_seq": turn.last_seq,
            })
        return {"status": "ok", "last_seq": turn.last_seq}

    async def _request_status(self, socket, params):
        command = self.commands.get(str(params.get("command_id") or ""))
        if command is None:
            return {"state": "complete", "result": {"ok": False, "message": "Unknown command"}}
        return {"state": command.state, "result": command.result}

    async def _parked_turn(self, socket, params):
        return {"has_parked": False, "auto_eligible": False, "open_count": 0}

    async def _feedback(self, socket, params):
        return {"status": "success"}

    async def _checkpoint_mark(self, socket, params):
        """The client bookmarks the conversation after a scene snapshot (turn_checkpoints.py). Mode 1's conversation is Hermes's, in
        its pane (A0): nothing is bookmarked here, and the reply says so."""
        _command_parts(params)
        return {"ok": True, "has_conversation": False}

    async def _checkpoint_rewind(self, socket, params):
        """The client restored a scene checkpoint and asks for the conversation to follow. Hermes keeps Mode 1's conversation and
        Lampway does not rewind it, so the reply refuses, saying so (checkpoint_backend.py then tells the user the agent may still
        remember the undone turns)."""
        _command_parts(params)
        return {"ok": False, "code": "rewind_unsupported",
                "message": "Lampway Agent's conversation is kept by Hermes in its pane, and Lampway does not rewind it"}

    # ------------------------------------------------------------ the turn
    async def _run_turn(self, socket, session: Session, turn: Turn, command: Command, user_text: Optional[str],
                        previous: Optional[Turn]):
        if previous is not None and previous.task is not None and not previous.task.done():
            previous.task.cancel()
            try:
                await previous.task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        stream = TurnStream(socket, turn)
        turn.stream = stream
        bubble_id = f"{turn.turn_id}:agent"
        steps: list[dict] = []
        status = "completed"
        try:
            await socket.notify("agent.turn.started", {
                "session_id": session.session_id, "turn_id": turn.turn_id, "run_id": turn.run_id,
            })
            command.state, command.result = "complete", {"ok": True}
            await socket.notify("agent.command.result", {
                "session_id": session.session_id, "command_id": turn.turn_id, "ok": True,
            })
            await stream.emit({"type": "run_status", "run_id": turn.run_id, "status": "in_progress"})
            await self._plan_notice(session, turn, stream)
            await stream.emit({"bubble_id": bubble_id,
                               "loader": {"visible": True, "texts": ["Thinking..."], "rotate_ms": 2000}})
            if user_text is not None:                      # None: going on after the island answered the pane's question
                session.last_user = user_text
            # Spec A2: the unit's Hermes pane runs the conversation; this island turn shows it.
            status = await self.engine.drive(socket, session, turn, stream, bubble_id, steps, user_text, context=turn.context) or status
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001 - the turn must end for the client
            log.exception("turn %s failed", turn.turn_id)
            await stream.emit_quietly({"type": "error", "message": f"The agent failed: {exc}"})
        finally:
            await self._finish(socket, session, turn, stream, bubble_id, steps, status)

    async def _plan_notice(self, session, turn, stream):
        """Spec R0a: the first turn of a session whose model is the user's ChatGPT plan (behind the gateway) says so once, in its own
        small bubble."""
        if session.plan_notice_shown or getattr(self.provider, "name", "") != "chatgpt_plan":
            return
        from .providers.chatgpt_plan import PLAN_NOTICE, USAGE_URL
        session.plan_notice_shown = True
        await stream.emit({"bubble_id": f"{turn.turn_id}:plan", "content": {"set": (
            f"{PLAN_NOTICE}: Lampway's agent sends this conversation to OpenAI with your ChatGPT sign-in, and it counts toward "
            f"your plan's usage ({USAGE_URL}).")}})

    async def _finish(self, socket, session, turn, stream, bubble_id, steps, status):
        socket = getattr(turn.stream, "socket", None) or socket          # a re-attached turn ends on the client's new socket
        log.debug("turn %s finishing as %s", turn.turn_id, status)
        try:
            if steps:
                for step in steps:
                    if step["status"] == "running":
                        step["status"] = "failed" if status != "completed" else "done"
                await stream.emit_quietly({"bubble_id": bubble_id, "steps": {"items": list(steps)}})
            await stream.emit_quietly({"bubble_id": bubble_id, "loader": {"visible": False},
                                       "ephemeral": {"clear": True}})
            await stream.emit_quietly({"type": "turn_end", "status": "in_progress" if turn.asked and status == "completed" else status,
                                       "run_id": turn.run_id})
            turn.status = "ended"
            await socket.notify("agent.turn.ended", {
                "session_id": session.session_id, "turn_id": turn.turn_id, "last_seq": turn.last_seq,
            })
        except Exception:  # noqa: BLE001 - socket gone; the journal keeps the turn for attach
            log.debug("turn %s could not deliver its end", turn.turn_id, exc_info=True)
            turn.status = "ended"
        finally:
            if session.current is turn:
                session.current = None

    async def _run_tool(self, socket, session, turn, call: ToolCall, stream=None, bubble_id=None,
                        steps=None) -> tuple[str, bool]:
        refusal = CAP.check_tool(call.name, call.arguments, origin="agent:main")      # spec E2, checked at call time
        if refusal is not None:
            return refusal, True
        if call.name in capabilities_tools.NAMES:
            return capabilities_tools.call(call.name, call.arguments, origin="agent:main")
        if server_tools.is_local(call.name):                       # the studio drivers: on this machine, never in Blender
            return await asyncio.to_thread(server_tools.run, call.name, call.arguments)
        if call.name in prompt_tools.NAMES:
            return await prompt_tools.call(self.prompts, call.name, call.arguments)
        if call.name in ledger_tools.JOB_NAMES:
            return ledger_tools.job_services(self.jobs), False
        if call.name in seed_tools.NAMES:
            return await seed_tools.call(call.name, call.arguments)
        if call.name in ledger_tools.NAMES:
            return await ledger_tools.call(self.prompts, call.name, call.arguments)
        if call.name in workbench_tools.NAMES:
            if self.cockpit is None:
                return "the cockpit is not available on this server", True
            return await workbench_tools.call(self.cockpit, call.name, call.arguments, self.ops, call.id,
                                              getattr(session, "last_user", ""), turn.turn_id)
        if call.name in orphan_server_tools.NAMES:
            return await orphan_server_tools.call(self, call.name, call.arguments)
        if call.name in files_tools.NAMES:
            return await files_tools.call(server_tools.project_root(), call.name, call.arguments)
        if call.name in cards_tools.NAMES:
            return await cards_tools.call(None, call.name, call.arguments)
        if call.name in vault_tools.NAMES:
            return await vault_tools.call(self.assets, call.name, call.arguments, {"origin": "agent", "agent_id": "main"})
        if call.name in connections_tools.NAMES:
            return await connections_tools.call(call.name, call.arguments)
        if call.name in choices_tools.NAMES:
            return await choices_tools.call(call.name, call.arguments, origin="agent:main")
        if call.name in compute_tools.NAMES:
            return await compute_tools.call(None, server_tools.project_root(), call.name, call.arguments)
        if call.name in plan_tools.NAMES:
            return await plan_tools.call(self, server_tools.project_root(), call.name, call.arguments)
        if call.name in engine_tools.NAMES:
            return await engine_tools.call(call.name, call.arguments)
        if call.name in image_tools.NAMES:
            return await image_tools.call(self.prompts, call.name, call.arguments)
        if call.name in video_tools.NAMES:
            return await video_tools.call(self.video, call.name, call.arguments)
        if call.name in studio_tools.NAMES:
            if self.studio is None:
                return "the Studio service is not available on this server", True
            return await studio_tools.call(self.studio, call.name, call.arguments)
        if is_swarm_tool(call.name):
            return await self._run_swarm_tool(socket, session, turn, call, stream, bubble_id, steps)
        try:
            script = script_for(call.name, call.arguments)
        except UnknownTool as exc:
            return str(exc), True
        try:
            result = await self._blender_script(socket, session_id=session.session_id,
                                                chat_session_id=session.session_id, turn_id=turn.turn_id,
                                                call_id=call.id, tool_name=call.name, script=script)
        except asyncio.TimeoutError:
            return f"Blender did not answer within {self.script_timeout_s:.0f}s", True
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported to the model
            return f"Blender could not run the script: {exc}", True
        return format_tool_result(result)

    async def _blender_script(self, socket, *, session_id, chat_session_id, turn_id, call_id, tool_name, script, mcp_operation_id=None):
        """One blender.execute_script round trip. ``session_id`` routes it (a worker's lane scene, or the chat's own scene);
        ``chat_session_id`` is the agent context the client checks is active. An MCP call names the operation that leased the
        scene (``mcp_operation_id``): the client admits it only under that lease."""
        agent_ctx = {"chat_session_id": chat_session_id, "turn_id": turn_id, "call_id": call_id}
        if mcp_operation_id:
            agent_ctx["mcp_operation_id"] = mcp_operation_id
        return await socket.request("blender.execute_script", {
            "script": script, "tool_name": tool_name, "session_id": session_id, "agent_ctx": agent_ctx,
        }, timeout=self.script_timeout_s)

    async def _run_swarm_tool(self, socket, session, turn, call, stream, bubble_id, steps):
        pending: list = []

        def progress(text: str):
            if stream is None or not steps:
                return
            steps[-1]["detail"] = text[:160]
            pending.append(asyncio.ensure_future(
                stream.emit_quietly({"bubble_id": bubble_id, "steps": {"items": list(steps)}})))

        async def emit_todo(rows):
            await stream.emit_quietly({"bubble_id": bubble_id, "todo": rows})

        # The unit's mode picks the workers' adapter (spec S1 as superseded by A): a tab in Your agent mode runs them on its bound
        # pane's harness; otherwise Mode 1, Lampway's Hermes pane.
        mode = self.byoa.mode_of(session.session_id)
        pane = self.byoa.pane_for(session.session_id) if mode == "byoa" else None
        ctx = SwarmContext(socket=socket, session_id=session.session_id, turn_id=turn.turn_id, call_id=call.id,
                           run_id=turn.run_id, progress=progress, emit_todo=emit_todo if stream is not None else None,
                           mode=mode, harness=(pane or {}).get("harness"), cwd=(pane or {}).get("cwd"),
                           project_root=(pane or {}).get("project_root"))
        try:
            return await self.swarm.call(call.name, call.arguments, ctx)
        finally:
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)


class TurnStream:
    """Numbers and journals agent.turn.event payloads for one turn."""

    def __init__(self, socket, turn: Turn):
        self.socket = socket
        self.turn = turn

    async def emit(self, payload: dict):
        # The journal is what agent.attach replays: snapshot the payload, since
        # callers keep mutating the step rows they passed in.
        payload = copy.deepcopy(payload)
        seq = len(self.turn.events)
        self.turn.events.append(payload)
        try:
            await self.socket.notify("agent.turn.event", {
                "session_id": self.turn.session_id, "turn_id": self.turn.turn_id, "seq": seq, "event": payload,
            })
        except Exception:  # noqa: BLE001
            if not self.turn.detached:
                raise
            log.debug("turn %s is detached: event %d journalled for agent.attach", self.turn.turn_id, seq)

    async def emit_quietly(self, payload: dict):
        try:
            await self.emit(payload)
        except Exception:  # noqa: BLE001
            log.debug("could not deliver event after the socket closed")


class InvalidParams(ValueError):
    pass


def clip_result(text: str, limit: int = MODEL_RESULT_CLIP) -> str:
    """A tool result as the agent sees it: bounded. The live silent turn was 0.5-1.6 MB candidate files read eight times."""
    if len(text) <= limit:
        return text
    return (text[:limit] + f"\n...[clipped: the first {limit} of {len(text)} characters. Ask for less: a summary, specific ids, "
            "a smaller slice - never the whole file.]")


def _command_parts(params: dict):
    command_id = params.get("command_id")
    payload = params.get("payload")
    if not isinstance(command_id, str) or not command_id or not isinstance(payload, dict):
        raise InvalidParams("command_id and payload are required")
    return command_id, payload
