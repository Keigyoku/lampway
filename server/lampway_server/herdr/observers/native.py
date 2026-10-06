"""Native transcript records -> activity events, and the incremental reader that tails a transcript from a byte offset captured BEFORE launch (history is never replayed). Pure standard library."""
import codecs
import json
import os
from pathlib import Path

PREVIEW_CHARS = 350


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(i.get("text", "") for i in (content or []) if isinstance(i, dict) and i.get("type") == "text")


def completed_turn(record: dict, agent: str):
    if agent == "codex" and record.get("type") == "event_msg" and (record.get("payload") or {}).get("type") == "task_complete":
        p = record["payload"]
        return {"kind": "turn-completed", "id": p.get("turn_id"), "text": "The agent finished its turn.", "preview": str(p.get("last_agent_message") or "")[-PREVIEW_CHARS:]}
    if agent == "claude" and not record.get("isSidechain"):
        msg = record.get("message") or {}
        if record.get("type") == "assistant" and msg.get("stop_reason") == "end_turn" and any(i.get("type") == "text" for i in (msg.get("content") or []) if isinstance(i, dict)):
            return {"kind": "turn-completed", "id": msg.get("id"), "text": "The agent finished its turn.", "preview": _text(msg.get("content"))[-PREVIEW_CHARS:]}
        if record.get("type") == "system" and record.get("subtype") == "api_error":
            return {"kind": "attention", "text": "The agent reported an API error."}
    return None


def native_activity(record: dict, agent: str):
    done = completed_turn(record, agent)
    if done:
        return done
    if agent == "codex" and record.get("type") == "event_msg":
        t = (record.get("payload") or {}).get("type")
        if t == "task_started":
            return {"kind": "turn-started"}
        if t == "turn_aborted":
            return {"kind": "turn-interrupted"}
    if agent == "claude" and not record.get("isSidechain"):
        if record.get("type") == "user" and not record.get("isMeta"):
            content = (record.get("message") or {}).get("content")
            interrupted = lambda v: isinstance(v, str) and v.startswith("[Request interrupted by user")  # noqa: E731
            if interrupted(content) or (isinstance(content, list) and any(i.get("type") == "text" and interrupted(i.get("text")) for i in content if isinstance(i, dict))):
                return {"kind": "turn-interrupted"}
            if content:                                                      # tool results also confirm ongoing work; file snapshots and metadata do not
                return {"kind": "turn-started"}
        if record.get("type") == "assistant" and (record.get("message") or {}).get("stop_reason") != "end_turn":
            return {"kind": "turn-started"}
    return None


class Tailer:
    """Reads only records appended after ``from_offset``; a record cut mid-character or mid-line waits for the rest."""

    def __init__(self, path: str, agent: str, from_offset: int = 0):
        self.path, self.agent, self.offset = path, agent, int(from_offset)
        self._partial = ""
        self._decoder = codecs.getincrementaldecoder("utf-8")()

    def poll(self) -> list:
        try:
            size = os.stat(self.path).st_size
        except OSError:
            return []
        if size <= self.offset:
            return []
        with open(self.path, "rb") as fh:
            fh.seek(self.offset)
            chunk = fh.read(size - self.offset)
        self.offset += len(chunk)
        text = self._partial + self._decoder.decode(chunk)
        lines = text.split("\n")
        self._partial = lines.pop()
        out = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                ev = native_activity(json.loads(line), self.agent)
            except ValueError:
                continue
            if ev:
                out.append(ev)
        return out


def claude_transcript(cwd: str, native_id: str, config_dir=None) -> str:
    """~/.claude/projects/<cwd with every non-alphanumeric as '-'>/<native id>.jsonl (CLAUDE_CONFIG_DIR honoured)."""
    base = Path(config_dir or os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    folder = "".join(c if c.isalnum() else "-" for c in cwd)
    return str(base / "projects" / folder / f"{native_id}.jsonl")


def codex_find_session(codex_home: str, originator: str, cwd: str):
    """The Codex rollout whose first record is a session_meta with OUR originator marker, source 'cli' and this folder: exactly one match, or none (never another recent chat in the folder)."""
    matches = []
    for f in Path(codex_home, "sessions").rglob("*.jsonl"):
        try:
            first = json.loads(f.open().readline())
        except (OSError, ValueError):
            continue
        p = first.get("payload") or {}
        if first.get("type") == "session_meta" and p.get("originator") == originator and p.get("source") == "cli" and p.get("cwd") == cwd:
            matches.append({"id": p.get("id") or f.name, "path": str(f)})
    return matches[0] if len(matches) == 1 else None
