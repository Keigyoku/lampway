"""The agent hub: chat sessions, turns, and the event stream the client renders.

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
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .prompt import PLAN_MODE_PROMPT, SYSTEM_PROMPT
from .providers.base import Message, ModelRequest, Stop, Text, ToolCall
from . import server_tools, studio_tools, video_tools, prompt_tools, image_tools, ledger_tools, seed_tools, engine_tools, workbench_tools, compute_tools, vault_tools, cards_tools, files_tools, connections_tools, choices_tools, orphan_server_tools, marks_context, questions as Q
from . import plan_tools
from .swarm import SWARM_SPECS, SwarmContext, SwarmManager, is_swarm_tool
from .tools import ASK_USER, TOOLS, UnknownTool, format_tool_result, script_for

log = logging.getLogger("lampway.agent")

MAX_ROUNDS = 64
MODEL_RESULT_CLIP = 20_000          # characters of one tool result the model is shown
HISTORY_BUDGET = 200_000            # characters of tool results kept in the context; the oldest are replaced by a note
_STOP_HINTS = {
    "length": "the model hit its output or context limit",
    "max_tokens": "the model hit its output limit",
    "content_filter": "the provider's content filter stopped it",
}

METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


@dataclass
class Turn:
    session_id: str
    turn_id: str
    run_id: str
    events: list[dict] = field(default_factory=list)  # payloads by seq
    status: str = "running"  # running | ended | abandoned
    task: Optional[asyncio.Task] = None
    plan_mode: bool = False
    asked: bool = False       # ended on an ask_user question: the run stays in progress until the answer

    @property
    def last_seq(self) -> int:
        return len(self.events) - 1


@dataclass
class Session:
    session_id: str
    messages: list[Message] = field(default_factory=list)
    turns: dict[str, Turn] = field(default_factory=dict)
    last_turn_id: Optional[str] = None
    current: Optional[Turn] = None
    pending_question: Optional[dict] = None   # {interrupt_id, call_id, question} while an ask_user waits for its answer
    bookmarks: dict = field(default_factory=dict)   # checkpoint request_id -> len(messages) at the mark


@dataclass
class Command:
    command_id: str
    session_id: str
    state: str = "pending"  # pending | complete
    result: Optional[dict] = None


class AgentHub:
    def __init__(self, provider, *, script_timeout_s: float = 600.0, system_prompt: str = SYSTEM_PROMPT,
                 swarm_provider_factory=None, studio=None, video=None, prompts=None, jobs=None, cockpit=None, assets=None):
        self.provider = provider
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
            self.ops = AgentOps(cockpit, cockpit.root / "ops", cwd=_os.environ.get("LAMPWAY_PROJECT_ROOT") or ".")
        self.script_timeout_s = script_timeout_s
        self.system_prompt = system_prompt
        self.sessions: dict[str, Session] = {}
        self.commands: dict[str, Command] = {}
        # The swarm's workers think with their own (cheaper) provider; with none configured they share the main one.
        self.swarm = SwarmManager(swarm_provider_factory or (lambda label: self.provider), self._blender_script,
                                  script_timeout_s=script_timeout_s)
        self.swarm.library = assets

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
        }.get(method)
        if handler is None:
            await socket.send_error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")
            return
        try:
            result = await handler(socket, params)
        except InvalidParams as exc:
            await socket.send_error(request_id, INVALID_PARAMS, str(exc))
            return
        await socket.reply(request_id, result)

    def socket_closed(self, socket):
        self.swarm.socket_closed(socket)
        for session in self.sessions.values():
            turn = session.current
            if turn is not None and turn.task is not None and getattr(turn, "socket", None) is socket:
                turn.task.cancel()

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
        return self._admit(socket, command_id, session_id, message, plan_mode=bool(payload.get("plan_required")),
                           marks_text=marks_context.describe(payload.get("mark_context")))

    async def _input(self, socket, params):
        command_id, payload = _command_parts(params)
        session_id = str(payload.get("session_id") or "")
        text = payload.get("text")
        if not session_id or not isinstance(text, str):
            raise InvalidParams("payload.session_id and payload.text are required")
        answers = payload.get("answers")
        session = self._session(session_id)
        pending = session.pending_question
        interrupt_id = str(payload.get("interrupt_id") or "")
        if pending is not None and (not interrupt_id or interrupt_id == pending["interrupt_id"]):
            # The answer to an ask_user question: it is the tool's result, and the model goes on from there.
            action = payload.get("action")
            reply = None
            if pending.get("batch") and action == Q.CANCEL:
                answer, reply = "The user cancelled these questions; do not go on with what they were for.", "Cancelled: the questions were not answered."
            elif pending.get("batch"):
                answer, refused = Q.batch_answer(pending["batch"], answers)
                if refused:
                    return {"state": "complete", "result": {"ok": False, "message": refused}}
            else:
                answer = Q.single_answer(text, answers, action)
            session.messages.append(Message("user", [{"type": "tool_result", "tool_call_id": pending["call_id"],
                                                      "content": answer, "is_error": False}]))
            session.pending_question = None
            return self._admit(socket, command_id, session_id, None, plan_mode=pending.get("plan_mode", False), reply=reply)
        if answers:
            text = f"{text}\n{answers}" if text else str(answers)
        return self._admit(socket, command_id, session_id, text)

    def _admit(self, socket, command_id, session_id, user_text, plan_mode=False, marks_text="", reply=None):
        session = self._session(session_id)
        command = self.commands[command_id] = Command(command_id, session_id)
        turn = Turn(session_id, command_id, str(uuid.uuid4()), plan_mode=plan_mode)
        turn.socket = socket  # type: ignore[attr-defined]
        session.turns[command_id] = turn
        session.last_turn_id = command_id
        previous = session.current
        session.current = turn
        turn.task = socket.spawn(self._run_turn(socket, session, turn, command, user_text, previous, marks_text, reply))
        return {"state": "pending"}

    async def _cancel(self, socket, params):
        command_id, payload = _command_parts(params)
        session = self.sessions.get(str(payload.get("session_id") or ""))
        cancelled = False
        if session is not None and session.current is not None and session.current.task is not None:
            log.debug("cancelling turn %s", session.current.turn_id)
            cancelled = session.current.task.cancel()
            self.swarm.cancel_session(session.session_id)
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
        after = after if isinstance(after, int) else -1
        for seq in range(after + 1, len(turn.events)):
            await socket.notify("agent.turn.event", {
                "session_id": turn.session_id, "turn_id": turn.turn_id, "seq": seq, "event": turn.events[seq],
            })
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
        """Bookmark the conversation where it stands (turn_checkpoints.py: sent after a scene snapshot is written)."""
        _command_id, payload = _command_parts(params)
        session = self.sessions.get(str(payload.get("session_id") or ""))
        request_id = str(payload.get("request_id") or "")
        if session is None or not request_id:
            return {"ok": True, "has_conversation": False}
        session.bookmarks[request_id] = len(session.messages)
        return {"ok": True, "has_conversation": True}

    async def _checkpoint_rewind(self, socket, params):
        """Forget every turn after the bookmark the restored scene was taken at. ``has_conversation: false`` tells the
        client there is nothing to rewind to and to start a new session (checkpoint_backend.py)."""
        _command_id, payload = _command_parts(params)
        session = self.sessions.get(str(payload.get("session_id") or ""))
        request_id = str(payload.get("request_id") or "")
        if session is None or request_id not in session.bookmarks:
            return {"ok": True, "has_conversation": False}
        if session.current is not None and session.current.task is not None:
            session.current.task.cancel()
        keep = session.bookmarks[request_id]
        del session.messages[keep:]
        session.bookmarks = {rid: n for rid, n in session.bookmarks.items() if n <= keep}
        session.pending_question = None
        return {"ok": True, "has_conversation": True}

    # ------------------------------------------------------------ the turn
    async def _run_turn(self, socket, session: Session, turn: Turn, command: Command, user_text: str,
                        previous: Optional[Turn], marks_text: str = "", reply: Optional[str] = None):
        if previous is not None and previous.task is not None and not previous.task.done():
            previous.task.cancel()
            try:
                await previous.task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        stream = TurnStream(socket, turn)
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
            await stream.emit({"bubble_id": bubble_id,
                               "loader": {"visible": True, "texts": ["Thinking..."], "rotate_ms": 2000}})
            if user_text is not None:                      # None: resuming after an ask_user answer
                message = Message.user_text(user_text)
                if marks_text:                             # the Scribble marks ride WITH the words, so a follow-up turn still has them in history
                    message.content.append({"type": "text", "text": "\n\n" + marks_text})
                session.messages.append(message)
            if reply is not None:                          # answered here (a cancelled batch): the model is not called again
                await stream.emit({"bubble_id": bubble_id, "content": {"set": reply}})
                return
            if user_text is not None and user_text.strip().lower() == Q.CONTINUE_MESSAGE and self.swarm.failed_tasks(session.session_id):
                await self._retry_failed(socket, session, turn, stream, bubble_id, steps)
            await self._agent_loop(socket, session, turn, stream, bubble_id, steps)
            if not turn.asked and self.swarm.failed_tasks(session.session_id, collected_in=turn.turn_id):
                await stream.emit({"bubble_id": bubble_id, "actions": [{"label": Q.RETRY_LABEL, "value": Q.RETRY_ACTION, "style": "primary"}]})
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001 - the turn must end for the client
            log.exception("turn %s failed", turn.turn_id)
            await stream.emit_quietly({"type": "error", "message": f"The agent failed: {exc}"})
        finally:
            await self._finish(socket, session, turn, stream, bubble_id, steps, status)

    async def _finish(self, socket, session, turn, stream, bubble_id, steps, status):
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

    async def _agent_loop(self, socket, session, turn, stream, bubble_id, steps):
        system = self.system_prompt + (PLAN_MODE_PROMPT if turn.plan_mode else "")
        for _round in range(MAX_ROUNDS):
            request = ModelRequest(system, trim_history(session.messages), list(TOOLS) + SWARM_SPECS, session_id=session.session_id)
            text_parts: list[str] = []
            calls: list[ToolCall] = []
            stop = ""
            async for event in self.provider.stream(request):
                if isinstance(event, Text):
                    text_parts.append(event.text)
                    await stream.emit({"bubble_id": bubble_id, "ephemeral": {"append": event.text}})
                elif isinstance(event, ToolCall):
                    calls.append(event)
                elif isinstance(event, Stop):
                    stop = event.reason
            text = "".join(text_parts)
            assistant = Message("assistant", ([{"type": "text", "text": text}] if text else []) + [
                {"type": "tool_call", "id": c.id, "name": c.name, "arguments": c.arguments} for c in calls])
            session.messages.append(assistant)
            if not calls:
                if not text.strip():
                    n = len(steps)
                    log.warning("turn %s ended on an empty reply after %d tool calls (stop reason %r)", turn.turn_id, n, stop)
                    text = empty_reply_note(stop, n)
                elif stop in ("length", "max_tokens"):
                    text += "\n\n(The reply was cut off at the model's output limit.)"
                await stream.emit({"bubble_id": bubble_id, "content": {"set": text}})
                return
            question = next((c for c in calls if c.name == ASK_USER and Q.batch_error(c.arguments if isinstance(c.arguments, dict) else {}) is None), None)
            if question is not None:
                await self._ask(session, turn, stream, bubble_id, text, question)
                return
            results = []
            for call in calls:
                steps.append({"id": call.id, "kind": "tool", "label": call.name, "target": "",
                              "detail": _detail(call), "status": "running"})
                await stream.emit({"bubble_id": bubble_id, "steps": {"items": list(steps)}})
                content, is_error = await self._run_tool(socket, session, turn, call, stream, bubble_id, steps)
                steps[-1]["status"] = "failed" if is_error else "done"
                await stream.emit({"bubble_id": bubble_id, "steps": {"items": list(steps)}})
                results.append({"type": "tool_result", "tool_call_id": call.id, "content": clip_result(content),
                                "is_error": is_error})
            session.messages.append(Message("user", results))
        log.warning("turn %s hit the %d-round tool cap", turn.turn_id, MAX_ROUNDS)
        await stream.emit({"bubble_id": bubble_id, "content": {"set": (
            f"I stopped after {MAX_ROUNDS} rounds of tool calls without finishing. Tell me to continue, or give me a narrower task.")}})

    async def _ask(self, session, turn, stream, bubble_id, text, call: ToolCall):
        """End the turn on the model's question: a bubble the client renders as a choice (or a text prompt), whose answer
        comes back as agent.input with the interrupt id and resumes the model with the answer as the tool's result."""
        args = call.arguments if isinstance(call.arguments, dict) else {}
        if args.get("questions"):
            await self._ask_batch(session, turn, stream, bubble_id, text, call, Q.clean_batch(args["questions"]))
            return
        question = str(args.get("question") or "").strip() or "Which do you want?"
        options = [str(o).strip() for o in (args.get("options") or []) if str(o).strip()][:6]
        interrupt_id = f"q_{uuid.uuid4().hex[:12]}"
        session.pending_question = {"interrupt_id": interrupt_id, "call_id": call.id, "question": question,
                                    "plan_mode": turn.plan_mode}
        turn.asked = True
        body = f"{text.strip()}\n\n{question}" if text.strip() else question
        event = {"bubble_id": bubble_id, "content": {"set": body}, "interrupt_id": interrupt_id,
                 "input_type": "choice" if options else "text"}
        if options:
            event["actions"] = [{"label": o, "value": o, "style": "primary" if i == 0 else "default"} for i, o in enumerate(options)]
        await stream.emit(event)

    async def _ask_batch(self, session, turn, stream, bubble_id, text, call: ToolCall, batch: list):
        """ONE input_required event for the whole batch (its ``questions`` slot): the client's wizard draws the first card from content +
        actions and the rest locally, then answers once with the complete map (batched_choice.py)."""
        interrupt_id = f"q_{uuid.uuid4().hex[:12]}"
        session.pending_question = {"interrupt_id": interrupt_id, "call_id": call.id, "question": batch[0]["question"], "batch": batch,
                                    "plan_mode": turn.plan_mode}
        turn.asked = True
        first = batch[0]
        body = f"{text.strip()}\n\n{first['question']}" if text.strip() else first["question"]
        actions = [{"label": o, "value": o, "style": "default"} for o in first["options"]]
        actions.append({"label": "Cancel", "value": Q.CANCEL, "style": "danger"})
        await stream.emit({"bubble_id": bubble_id, "content": {"set": body}, "interrupt_id": interrupt_id, "input_type": "choice",
                           "questions": batch, "actions": actions})

    async def _retry_failed(self, socket, session, turn, stream, bubble_id, steps):
        """Retry failed tasks: a new swarm of exactly the failed tasks, collected, written into the conversation as the tool calls they are,
        so the model then reports on them. Nothing that finished runs again."""
        tasks = self.swarm.failed_tasks(session.session_id)
        self.swarm.mark_retried(session.session_id)
        start = ToolCall(id=f"retry_{uuid.uuid4().hex[:8]}", name="swarm_start", arguments={"tasks": tasks})
        for call in (start, None):
            if call is None:
                started = json.loads(content) if not is_error else {}
                if not started.get("swarm_id"):
                    return
                call = ToolCall(id=f"retry_{uuid.uuid4().hex[:8]}", name="swarm_collect", arguments={"swarm_id": started["swarm_id"]})
            session.messages.append(Message("assistant", [{"type": "tool_call", "id": call.id, "name": call.name, "arguments": call.arguments}]))
            steps.append({"id": call.id, "kind": "tool", "label": call.name, "target": "", "detail": "retry failed tasks", "status": "running"})
            await stream.emit({"bubble_id": bubble_id, "steps": {"items": list(steps)}})
            content, is_error = await self._run_swarm_tool(socket, session, turn, call, stream, bubble_id, steps)
            steps[-1]["status"] = "failed" if is_error else "done"
            await stream.emit({"bubble_id": bubble_id, "steps": {"items": list(steps)}})
            session.messages.append(Message("user", [{"type": "tool_result", "tool_call_id": call.id, "content": clip_result(content),
                                                      "is_error": is_error}]))

    async def _run_tool(self, socket, session, turn, call: ToolCall, stream=None, bubble_id=None,
                        steps=None) -> tuple[str, bool]:
        if call.name == ASK_USER:                                  # only a refused ask_user reaches here: the valid one ends the turn
            return Q.batch_error(call.arguments if isinstance(call.arguments, dict) else {}) or "ask_user could not be shown", True
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
            last_user = next((m.text() for m in reversed(session.messages) if m.role == "user" and m.text()), "")
            return await workbench_tools.call(self.cockpit, call.name, call.arguments, self.ops, call.id, last_user, turn.turn_id)
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

    async def _blender_script(self, socket, *, session_id, chat_session_id, turn_id, call_id, tool_name, script):
        """One blender.execute_script round trip. ``session_id`` routes it (a worker's lane scene, or the chat's own scene);
        ``chat_session_id`` is the agent context the client checks is active."""
        return await socket.request("blender.execute_script", {
            "script": script, "tool_name": tool_name, "session_id": session_id,
            "agent_ctx": {"chat_session_id": chat_session_id, "turn_id": turn_id, "call_id": call_id},
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

        ctx = SwarmContext(socket=socket, session_id=session.session_id, turn_id=turn.turn_id, call_id=call.id,
                           run_id=turn.run_id, progress=progress, emit_todo=emit_todo if stream is not None else None)
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
        await self.socket.notify("agent.turn.event", {
            "session_id": self.turn.session_id, "turn_id": self.turn.turn_id, "seq": seq, "event": payload,
        })

    async def emit_quietly(self, payload: dict):
        try:
            await self.emit(payload)
        except Exception:  # noqa: BLE001
            log.debug("could not deliver event after the socket closed")


class InvalidParams(ValueError):
    pass


def clip_result(text: str, limit: int = MODEL_RESULT_CLIP) -> str:
    """A tool result as the model sees it: bounded. The live silent turn was 0.5-1.6 MB candidate files read eight times."""
    if len(text) <= limit:
        return text
    return (text[:limit] + f"\n...[clipped: the first {limit} of {len(text)} characters. Ask for less: a summary, specific ids, "
            "a smaller slice - never the whole file.]")


def trim_history(messages: list, budget: int = HISTORY_BUDGET) -> list:
    """The messages the model is sent: when the tool results in the history outgrow ``budget`` characters, the OLDEST results are
    replaced by a one-line note (the conversation and the recent results stay). The session's own list is never changed."""
    total = sum(len(str(p.get("content", ""))) for m in messages for p in m.content if p.get("type") == "tool_result")
    if total <= budget:
        return list(messages)
    out = []
    for m in messages:
        parts = []
        for p in m.content:
            if p.get("type") == "tool_result" and total > budget:
                size = len(str(p.get("content", "")))
                total -= size
                p = {**p, "content": f"[an older tool result of {size} characters was left out to keep the context small]"}
            parts.append(p)
        out.append(Message(m.role, parts))
    return out


def empty_reply_note(stop: str, tool_calls: int) -> str:
    why = _STOP_HINTS.get(stop or "", "")
    tail = f" ({why}; stop reason: {stop})" if why else (f" (stop reason: {stop})" if stop else " (the provider reported no abnormal stop)")
    n = f" after {tool_calls} tool call{'s' if tool_calls != 1 else ''}" if tool_calls else ""
    return (f"The model returned an empty reply{n}{tail}. Nothing more was done. "
            "This usually means a limit was reached: ask again with less to read, or in smaller steps.")


def _command_parts(params: dict):
    command_id = params.get("command_id")
    payload = params.get("payload")
    if not isinstance(command_id, str) or not command_id or not isinstance(payload, dict):
        raise InvalidParams("command_id and payload are required")
    return command_id, payload


def _detail(call: ToolCall) -> str:
    script = call.arguments.get("script") if isinstance(call.arguments, dict) else None
    if isinstance(script, str) and script.strip():
        return script.strip().splitlines()[0][:120]
    return ""
