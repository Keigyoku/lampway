"""The agent's file tools (agent_files): the project's instruction files and skills, and the notes agents keep. All writes stay inside the project root (scaffold, generate, sync, notes, pack output); nothing
here spends, uploads or reads a credential file."""
import asyncio
import json
import os
from pathlib import Path

from ..agent_files import generate as GEN
from ..agent_files import mirror as MIR
from ..agent_files import notes as NOTES
from ..agent_files import pack as PACK
from ..agent_files import roots as ROOTS
from ..agent_files import scaffold as SCAF
from .providers.base import ToolSpec

NAMES = {"lampway_agent_files", "lampway_skills_list", "lampway_skill_read", "lampway_note_write"}
ACTIONS = ["status", "scaffold", "generate", "sync", "check", "pack_build", "pack_verify"]


def specs() -> list:
    obj = lambda props, req=(): {"type": "object", "additionalProperties": False, "required": list(req), "properties": props}  # noqa: E731
    return [
        ToolSpec("lampway_agent_files", "The project's instruction files and skills. status: what exists (ok | missing | stale | differs | differs-user-owned). scaffold: create AGENTS.md, CLAUDE.md, context/preferences.md and the note "
                 "folders, NEVER overwriting. generate: write the skills from the live tool registry (a file whose generated marker the user removed is the user's and is left alone). sync: copy .agents/skills to "
                 ".claude/skills byte for byte (never deletes). check: is anything stale or different. pack_build / pack_verify: a skill pack zip (`out` under the project) that proves itself when unpacked.",
                 obj({"action": {"type": "string", "enum": ACTIONS}, "overwrite": {"type": "boolean"}, "out": {"type": "string", "description": "pack_build / pack_verify: a zip path inside the project"}}, ["action"])),
        ToolSpec("lampway_skills_list", "List the skills available to this project (name and a 260-character description) from .agents/skills, .claude/skills and the user's skill folders.", obj({"query": {"type": "string"}})),
        ToolSpec("lampway_skill_read", "Read a skill or a project note (a skill name, or a path inside a skill root or knowledge/ processes/ context/ projects/). Pages of 24000 characters with next_offset. Refused: credential-looking "
                 "names, dot-folders, other extensions, files over 2 MB, anything that leaves the roots.", obj({"path": {"type": "string"}, "offset": {"type": "integer"}}, ["path"])),
        ToolSpec("lampway_note_write", "Write a note under knowledge/, processes/, context/ or projects/. Pass the `revision` (sha256) of the bytes you read, or none for a new file: a stale revision is refused and your draft kept; the "
                 "previous bytes are backed up. At most 2 MB.", obj({"path": {"type": "string"}, "text": {"type": "string"}, "revision": {"type": "string"}}, ["path", "text"])),
    ]


def _state_dir() -> Path:
    from ..config import _default_state_dir
    return Path(os.environ.get("LAMPWAY_STATE_DIR") or _default_state_dir())


def _in_root(root: Path, p: str) -> Path:
    full = Path(p) if os.path.isabs(p) else root / p
    rr, rf = os.path.realpath(root), os.path.realpath(full)
    if rf != rr and not rf.startswith(rr + os.sep):
        raise ValueError(f"{p} is outside the project root")
    return full


def _run(root: Path, name: str, a: dict):
    if name == "lampway_skills_list":
        return {"skills": ROOTS.list_skills(root, a.get("query"))}
    if name == "lampway_skill_read":
        return ROOTS.read_skill(root, str(a.get("path") or ""), int(a.get("offset") or 0))
    if name == "lampway_note_write":
        return NOTES.write(root, str(a.get("path") or ""), str(a.get("text") or ""), a.get("revision"), _state_dir())
    act = a.get("action")
    if act == "status":
        return {"files": SCAF.status(root)}
    if act == "scaffold":
        return SCAF.scaffold(root, bool(a.get("overwrite")))
    if act == "generate":
        return GEN.generate(root, overwrite=bool(a.get("overwrite")))
    if act == "sync":
        return MIR.sync(root)
    if act == "check":
        return GEN.check(root)
    if act == "pack_build":
        return PACK.build(root, _in_root(root, str(a.get("out") or "skills-pack.zip")))
    if act == "pack_verify":
        return PACK.verify(_in_root(root, str(a.get("out") or "skills-pack.zip")))
    raise ValueError(f"action is one of {ACTIONS}")


async def call(root, name: str, arguments: dict) -> tuple:
    try:
        return json.dumps(await asyncio.to_thread(_run, Path(root), name, arguments or {})), False
    except (ROOTS.ReadRefused, NOTES.NoteRefused, SCAF.ScaffoldError, PACK.PackError, GEN.LawError, ValueError, OSError) as exc:
        return str(exc), True
