"""The fallback: any folder is a project of confidence 0.01, so a path is never 'unknown'."""
from pathlib import Path

from .contracts import match

ID, LABEL = "generic", "Generic folder"


def detect(start, ctx):
    p = Path(start)
    return [match(ID, p, 0.01, "Fallback for any local folder", p.name)]


def capabilities(m, ctx):
    return {"files": [{"path": "."}], "commands": [], "artifacts": [], "context": []}
