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
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .prompt import SYSTEM_PROMPT
from .providers.base import Message, ModelRequest, Text, ToolCall
from .tools import TOOLS, UnknownTool, format_tool_result, script_for

log = logging.getLogger("lampway.agent")

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


@dataclass
class Command:
    command_id: str
    session_id: str
    state: str = "pending"  # pending | complete
    result: Optional[dict] = None


class AgentHub:
    def __init__(self, provider, *, script_timeout_s: float = 600.0, system_prompt: str = SYSTEM_PROMPT):
        self.provider = provider
        self.script_timeout_s = script_timeout_s
        self.system_prompt = system_prompt
        self.sessions: dict[str, Session] = {}
        self.commands: dict[str, Command] = {}

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
        return self._admit(socket, command_id, session_id, message)

    async def _input(self, socket, params):
        command_id, payload = _command_parts(params)
        session_id = str(payload.get("session_id") or "")
        text = payload.get("text")
        if not session_id or not isinstance(text, str):
            raise InvalidParams("payload.session_id and payload.text are required")
        answers = payload.get("answers")
        if answers:
            text = f"{text}\n{answers}" if text else str(answers)
        return self._admit(socket, command_id, session_id, text)

    def _admit(self, socket, command_id, session_id, user_text):
        session = self._session(session_id)
        command = self.commands[command_id] = Command(command_id, session_id)
        turn = Turn(session_id, command_id, str(uuid.uuid4()))
        turn.socket = socket  # type: ignore[attr-defined]
        session.turns[command_id] = turn
        session.last_turn_id = command_id
        previous = session.current
        session.current = turn
        turn.task = socket.spawn(self._run_turn(socket, session, turn, command, user_text, previous))
        return {"state": "pending"}

    async def _cancel(self, socket, params):
        command_id, payload = _command_parts(params)
        session = self.sessions.get(str(payload.get("session_id") or ""))
        cancelled = False
        if session is not None and session.current is not None and session.current.task is not None:
            log.debug("cancelling turn %s", session.current.turn_id)
            cancelled = session.current.task.cancel()
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
        return {"ok": True, "has_conversation": True}

    async def _checkpoint_rewind(self, socket, params):
        return {"ok": False, "has_conversation": True}

    # ------------------------------------------------------------ the turn
    async def _run_turn(self, socket, session: Session, turn: Turn, command: Command, user_text: str,
                        previous: Optional[Turn]):
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
            session.messages.append(Message.user_text(user_text))
            await self._agent_loop(socket, session, turn, stream, bubble_id, steps)
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
            await stream.emit_quietly({"type": "turn_end", "status": status, "run_id": turn.run_id})
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
        for _round in range(64):
            request = ModelRequest(self.system_prompt, list(session.messages), list(TOOLS))
            text_parts: list[str] = []
            calls: list[ToolCall] = []
            async for event in self.provider.stream(request):
                if isinstance(event, Text):
                    text_parts.append(event.text)
                    await stream.emit({"bubble_id": bubble_id, "ephemeral": {"append": event.text}})
                elif isinstance(event, ToolCall):
                    calls.append(event)
            text = "".join(text_parts)
            assistant = Message("assistant", ([{"type": "text", "text": text}] if text else []) + [
                {"type": "tool_call", "id": c.id, "name": c.name, "arguments": c.arguments} for c in calls])
            session.messages.append(assistant)
            if not calls:
                if text:
                    await stream.emit({"bubble_id": bubble_id, "content": {"set": text}})
                return
            results = []
            for call in calls:
                steps.append({"id": call.id, "kind": "tool", "label": call.name, "target": "",
                              "detail": _detail(call), "status": "running"})
                await stream.emit({"bubble_id": bubble_id, "steps": {"items": list(steps)}})
                content, is_error = await self._run_tool(socket, session, turn, call)
                steps[-1]["status"] = "failed" if is_error else "done"
                await stream.emit({"bubble_id": bubble_id, "steps": {"items": list(steps)}})
                results.append({"type": "tool_result", "tool_call_id": call.id, "content": content,
                                "is_error": is_error})
            session.messages.append(Message("user", results))
        await stream.emit({"bubble_id": bubble_id, "content": {"set": "I stopped after too many tool calls."}})

    async def _run_tool(self, socket, session, turn, call: ToolCall) -> tuple[str, bool]:
        try:
            script = script_for(call.name, call.arguments)
        except UnknownTool as exc:
            return str(exc), True
        try:
            result = await socket.request("blender.execute_script", {
                "script": script, "tool_name": call.name, "session_id": session.session_id,
                "agent_ctx": {"chat_session_id": session.session_id, "turn_id": turn.turn_id,
                              "call_id": call.id},
            }, timeout=self.script_timeout_s)
        except asyncio.TimeoutError:
            return f"Blender did not answer within {self.script_timeout_s:.0f}s", True
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported to the model
            return f"Blender could not run the script: {exc}", True
        return format_tool_result(result)


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
