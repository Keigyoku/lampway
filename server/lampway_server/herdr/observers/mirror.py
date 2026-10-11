# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The island view of a harness's own session file (docs/reports/agent-modes-spec.md B4): native records in, the operations of
Mode 1's turn stream out, so the island renders a BYOA session with the bubbles and steps it already draws.

Pure and read-only: a mirror is fed one record at a time (``feed(record, at)``, ``at`` being the record's byte offset in the
file) and returns operations; it never opens a file, and the hub (agent/byoa.py) numbers and sends what it returns.

Operations, each ``(kind, turn_id, data)``:
- ``("start", tid, {"user_text": str})``: a turn begins (the user's prompt, or "" when the observation began mid-turn);
- ``("event", tid, payload)``: one ``agent.turn.event`` payload (``run_status``, a ``content.set`` slot, a ``steps`` slot);
- ``("end", tid, {"status": "completed" | "cancelled" | "failed"})``: the turn is over.

A turn id is ``byoa-<key>-<offset of the record that opened it>``: the same file gives the same ids, and two panes never share one.
The record shapes are the harnesses' own (observers/native.py reads the same ones). [UNVERIFIED] against an installed version:
the fixtures in server/tests/byoa_fixtures.py are hand-built until each adapter records its own (spec B1).
"""
import json
from typing import Optional

#: The prefix a harness puts before the tools of Lampway's MCP server (Claude Code: mcp__<server>__<tool>; Codex: <server>__<tool>).
TOOL_PREFIXES = ("mcp__lampway__", "lampway__")
DETAIL_CHARS = 120
API_ERROR = "The agent reported an API error."


def _label(name: str) -> str:
    for prefix in TOOL_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):]
    return name


def _detail(arguments) -> str:
    """One line that says what a call is about: the command, else the first short string argument."""
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return arguments.strip().splitlines()[0][:DETAIL_CHARS] if arguments.strip() else ""
    if not isinstance(arguments, dict):
        return ""
    cmd = arguments.get("command")
    if isinstance(cmd, list):
        cmd = " ".join(str(c) for c in cmd)
    if isinstance(cmd, str) and cmd.strip():
        return cmd.strip().splitlines()[0][:DETAIL_CHARS]
    for value in arguments.values():
        if isinstance(value, str) and value.strip():
            return value.strip().splitlines()[0][:DETAIL_CHARS]
    return ""


class _Mirror:
    harness = ""

    def __init__(self, key: str):
        self.key = key
        self.turn: Optional[str] = None
        self._texts: list = []
        self._steps: list = []

    # ------------------------------------------------------------------------------------------------- turn bookkeeping
    def _start(self, at: int, user_text: str) -> list:
        ops = self._close("completed")
        self.turn = f"byoa-{self.key}-{at}"
        self._texts, self._steps = [], []
        return ops + [("start", self.turn, {"user_text": user_text}),
                      ("event", self.turn, {"type": "run_status", "run_id": self.turn, "status": "in_progress"})]

    def _ensure(self, at: int) -> list:
        return [] if self.turn else self._start(at, "")

    def _text(self, text: str) -> list:
        if not text or not text.strip():
            return []
        self._texts.append(text.strip())
        return [("event", self.turn, {"bubble_id": f"{self.turn}:agent", "content": {"set": "\n\n".join(self._texts)}})]

    def _steps_event(self) -> list:
        return [("event", self.turn, {"bubble_id": f"{self.turn}:agent", "steps": {"items": [dict(s) for s in self._steps]}})]

    def _step_start(self, call_id: str, name: str, arguments) -> list:
        self._steps.append({"id": str(call_id or len(self._steps)), "kind": "tool", "label": _label(str(name or "tool")), "target": "",
                            "detail": _detail(arguments), "status": "running"})
        return self._steps_event()

    def _step_end(self, call_id: str, failed: bool) -> list:
        step = next((s for s in self._steps if s["id"] == str(call_id) and s["status"] == "running"), None)
        if step is None:
            return []
        step["status"] = "failed" if failed else "done"
        return self._steps_event()

    def _close(self, status: str) -> list:
        if not self.turn:
            return []
        ops = []
        if any(s["status"] == "running" for s in self._steps):
            for s in self._steps:
                if s["status"] == "running":
                    s["status"] = "done" if status == "completed" else "failed"
            ops += self._steps_event()
        ops.append(("end", self.turn, {"status": status}))
        self.turn = None
        return ops

    def feed(self, record: dict, at: int) -> list:      # pragma: no cover - each harness has its own
        raise NotImplementedError


class ClaudeMirror(_Mirror):
    """Claude Code's transcript: ``user`` records (a prompt, or tool results), ``assistant`` records (text, thinking, tool_use,
    one content block each), ``system`` records; subagents' records carry ``isSidechain`` and stay out of the island."""
    harness = "claude"

    @staticmethod
    def _interrupted(text) -> bool:
        return isinstance(text, str) and text.startswith("[Request interrupted by user")

    def feed(self, record: dict, at: int) -> list:
        if not isinstance(record, dict) or record.get("isSidechain"):
            return []
        kind = record.get("type")
        msg = record.get("message") if isinstance(record.get("message"), dict) else {}
        if kind == "user" and not record.get("isMeta"):
            content = msg.get("content")
            if isinstance(content, str):
                if self._interrupted(content):
                    return self._close("cancelled")
                if not content.strip() or content.lstrip().startswith(("<command-", "<local-command")):
                    return []
                return self._start(at, content.strip())
            items = [i for i in (content or []) if isinstance(i, dict)]
            ops = []
            for item in items:
                if item.get("type") == "tool_result" and self.turn:
                    ops += self._step_end(item.get("tool_use_id"), bool(item.get("is_error")))
            texts = [i.get("text", "") for i in items if i.get("type") == "text"]
            if any(self._interrupted(t) for t in texts):
                return ops + self._close("cancelled")
            prompt = "\n".join(t for t in texts if t.strip()).strip()
            if prompt and not any(i.get("type") == "tool_result" for i in items):
                ops += self._start(at, prompt)
            return ops
        if kind == "assistant":
            ops = self._ensure(at)
            for item in msg.get("content") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    ops += self._text(item.get("text", ""))
                elif item.get("type") == "tool_use":
                    ops += self._step_start(item.get("id"), item.get("name"), item.get("input"))
            has_text = any(isinstance(i, dict) and i.get("type") == "text" for i in msg.get("content") or [])
            if msg.get("stop_reason") == "end_turn" and has_text:
                ops += self._close("completed")
            return ops
        if kind == "system" and record.get("subtype") == "api_error":
            return self._ensure(at) + self._text(API_ERROR)
        return []


class CodexMirror(_Mirror):
    """Codex rollouts include raw response messages, legacy events and optional completed TurnItems.
    Message ids and matching cross-format echoes keep one island entry; task completion, not final phase, ends the turn."""
    harness = "codex"

    def __init__(self, key):
        super().__init__(key)
        self._message_ids = set()
        self._message_counts = {}
        self._user_text = ""
        self._task_id = None
        self._finished_tasks = set()
        self._output_calls = {}

    def _start(self, at, user_text):
        ops = super()._start(at, user_text)
        self._message_counts = {}
        self._user_text = user_text
        return ops

    def _message(self, role, text, source, at, item_id=None):
        if not isinstance(text, str) or not text.strip():
            return []
        text = text.strip()
        identity = (role, item_id) if item_id else None
        if identity and identity in self._message_ids:
            return []
        if role == "user" and text.startswith(("<environment_context>", "<instructions>", "<developer_instructions>")):
            return []
        counts = self._message_counts.get((role, text), {})
        next_count = counts.get(source, 0) + 1
        echo = next_count <= max((n for s, n in counts.items() if s != source), default=0)
        if echo:
            counts[source] = next_count
            if identity:
                self._message_ids.add(identity)
            return []
        ops = self._start(at, text) if role == "user" else self._ensure(at)
        counts = self._message_counts.setdefault((role, text), {})
        counts[source] = counts.get(source, 0) + 1
        if identity:
            self._message_ids.add(identity)
        return ops if role == "user" else ops + self._text(text)

    def _step_start(self, call_id, name, arguments):
        if call_id and any(s["id"] == str(call_id) for s in self._steps):
            return []
        return super()._step_start(call_id, name, arguments)

    @staticmethod
    def _content(items, kinds):
        return "\n".join(i["text"] for i in (items or []) if isinstance(i, dict)
                         and i.get("type") in kinds and isinstance(i.get("text"), str))

    def _item(self, item, source, at):
        t = item.get("type")
        if t in ("AgentMessage", "UserMessage"):
            role = "assistant" if t == "AgentMessage" else "user"
            kinds = ("Text",) if role == "assistant" else ("text",)
            return self._message(role, self._content(item.get("content"), kinds), source, at, item.get("id"))
        if t in ("CommandExecution", "McpToolCall"):
            ops = self._ensure(at)
            name = "shell" if t == "CommandExecution" else f"{item.get('server', '')}__{item.get('tool', 'tool')}"
            args = {"command": item.get("command")} if t == "CommandExecution" else item.get("arguments")
            ops += self._step_start(item.get("id"), name, args)
            status = item.get("status")
            if status in ("completed", "failed", "declined"):
                failed = status != "completed" or self._failed(item.get("result")) or self._failed(item)
                ops += self._step_end(item.get("id"), failed)
            return ops
        if t == "FunctionCallOutput":
            # A TurnItem's id need not be the raw call_id: never invent a second call from an output.
            call_id = self._output_calls.get(item.get("id"), item.get("id"))
            return self._step_end(call_id, self._failed(item.get("output"))) if self.turn else []
        return []

    @staticmethod
    def _failed(output) -> bool:
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except ValueError:
                return False
        if not isinstance(output, dict):
            return False
        meta = output.get("metadata") if isinstance(output.get("metadata"), dict) else {}
        code = meta.get("exit_code", output.get("exit_code"))
        return bool(output.get("isError") or output.get("is_error")) or (isinstance(code, int) and code != 0)

    def feed(self, record: dict, at: int) -> list:
        if not isinstance(record, dict):
            return []
        p = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        t = p.get("type")
        if record.get("type") == "event_msg":
            native_turn = p.get("turn_id")
            if native_turn and native_turn in self._finished_tasks:
                return []
            if t != "task_started" and native_turn and self._task_id and native_turn != self._task_id:
                return []
            if t == "task_started":
                ops = []
                if self._task_id and self._task_id != native_turn:
                    # Replacement retires the old task even if its terminal record arrives later.
                    self._finished_tasks.add(self._task_id)
                    ops = self._close("completed")
                if not self.turn:
                    self._message_counts = {}
                self._task_id = native_turn
                return ops
            if t == "user_message":
                return self._message("user", p.get("message"), "legacy", at)
            if t == "agent_message":
                return self._message("assistant", p.get("message"), "legacy", at)
            if t in ("item_started", "item_completed") and isinstance(p.get("item"), dict):
                return self._item(p["item"], "item", at)
            if t == "task_complete":
                last = p.get("last_agent_message")
                ops = []
                if isinstance(last, str) and last.strip() and (not self._texts or self._texts[-1] != last.strip()):
                    ops = self._ensure(at) + self._text(last)
                if native_turn:
                    self._finished_tasks.add(native_turn)
                self._task_id = None
                return ops + self._close("completed")
            if t == "turn_aborted":
                if native_turn:
                    self._finished_tasks.add(native_turn)
                self._task_id = None
                return self._close("cancelled")
            return []
        if record.get("type") == "response_item":
            meta = p.get("internal_chat_message_metadata_passthrough")
            if isinstance(meta, dict):
                native_turn = meta.get("turn_id")
                if native_turn in self._finished_tasks:
                    return []
                if native_turn and self._task_id and native_turn != self._task_id:
                    return []
            if t == "message" and p.get("role") in ("user", "assistant") and p.get("phase") != "analysis":
                role = p["role"]
                kinds = ("input_text",) if role == "user" else ("output_text",)
                return self._message(role, self._content(p.get("content"), kinds), "response", at, p.get("id"))
            if t in ("function_call", "custom_tool_call"):
                return self._ensure(at) + self._step_start(p.get("call_id"), p.get("name"), p.get("arguments", p.get("input")))
            if t in ("function_call_output", "custom_tool_call_output") and self.turn:
                if p.get("id"):
                    self._output_calls[p["id"]] = p.get("call_id")
                return self._step_end(p.get("call_id"), self._failed(p.get("output")))
        return []


class PiMirror(_Mirror):
    """Pi's session file (Pi 1.0.4 docs/session-format.md and docs/message-types.md): ``message`` records carry a ``user`` message
    (the prompt: text, or text and image blocks), an ``assistant`` message (``text``, ``thinking`` and ``toolCall`` blocks, and a
    ``stopReason``: ``toolUse`` goes on, ``stop`` and ``length`` end the turn, ``aborted`` is the user's interrupt, ``error`` carries
    ``errorMessage``) and a ``toolResult`` (``toolCallId``, ``isError``). The header, system messages, model and thinking changes,
    usage and compaction records are not part of the conversation shown. [UNVERIFIED by a recorded turn: a turn needs a provider;
    the shapes are the installed package's own documentation.]"""
    harness = "pi"

    def feed(self, record: dict, at: int) -> list:
        if not isinstance(record, dict) or record.get("type") != "message" or not isinstance(record.get("message"), dict):
            return []
        msg = record["message"]
        role = msg.get("role")
        if role == "user":
            content = msg.get("content")
            if isinstance(content, str):
                text = content
            else:
                text = "\n".join(i.get("text", "") for i in (content or []) if isinstance(i, dict) and i.get("type") == "text")
            text = text.strip()
            return self._start(at, text) if text else []
        if role == "assistant":
            ops = self._ensure(at)
            for item in msg.get("content") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    ops += self._text(item.get("text", ""))
                elif item.get("type") == "toolCall":
                    ops += self._step_start(item.get("id"), item.get("name"), item.get("arguments"))
            stop = msg.get("stopReason")
            if stop == "error":
                ops += self._text(str(msg.get("errorMessage") or API_ERROR))
                ops += self._close("failed")
            elif stop == "aborted":
                ops += self._close("cancelled")
            elif stop in ("stop", "length"):
                ops += self._close("completed")
            return ops
        if role == "toolResult" and self.turn:
            return self._step_end(msg.get("toolCallId"), bool(msg.get("isError")))
        return []


MIRRORS = {"claude": ClaudeMirror, "codex": CodexMirror, "pi": PiMirror}


def for_harness(harness, key: str):
    """The mirror for a harness whose own session file Lampway reads, else None (the island shows the pane's screen)."""
    cls = MIRRORS.get(harness)
    return cls(key) if cls else None
