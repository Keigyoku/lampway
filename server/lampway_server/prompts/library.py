"""The template library: built-ins shipped in the repo (``builtin/*.json``), user templates (``<LAMPWAY_HOME>/prompts``) and project templates
(``<project>/prompts``). All are validated on load; an invalid file is refused with its path and the reasons and the rest still load. A template
is keyed by (id, version): a higher scope wins for the same key, ``get(id)`` is the newest version of the id, and a new version never overwrites an old
one. ``save`` writes the user scope only."""

import json
import os
from pathlib import Path
from typing import Optional

from . import schema as S

BUILTIN = Path(__file__).parent / "builtin"
SCOPES = ("builtin", "user", "project")


class LibraryError(ValueError):
    pass


def _vkey(version: str) -> tuple:
    return tuple(int(x) for x in version.split("."))


class Library:
    def __init__(self, builtin_dir=BUILTIN, user_dir=None, project_dir=None):
        self.dirs = {"builtin": builtin_dir, "user": user_dir, "project": project_dir}
        self.errors: list = []
        self._items: dict = {}
        self.reload()

    @classmethod
    def from_env(cls, builtin_dir=BUILTIN) -> "Library":
        home = os.environ.get("LAMPWAY_HOME") or str(Path.home() / ".local/share/lampway")
        project = os.environ.get("LAMPWAY_PROJECT_ROOT")
        return cls(builtin_dir, Path(home) / "prompts", Path(project) / "prompts" if project else None)

    def reload(self) -> None:
        self.errors, self._items = [], {}
        for rank, scope in enumerate(SCOPES):                      # later scopes overwrite earlier ones for the same (id, version)
            d = self.dirs[scope]
            if not d or not Path(d).is_dir():
                continue
            for path in sorted(Path(d).glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    self.errors.append({"file": str(path), "errors": [{"path": "", "reason": f"not valid JSON: {exc}"}]})
                    continue
                problems = S.validate(data)
                if problems:
                    self.errors.append({"file": str(path), "errors": problems})
                    continue
                self._items[(data["id"], data["version"])] = {**data, "scope": scope, "file": str(path)}

    # ---------------------------------------------------------------------------------- reading
    def versions(self, template_id: str) -> list:
        rows = [v for (i, _), v in self._items.items() if i == template_id]
        return sorted(rows, key=lambda t: _vkey(t["version"]), reverse=True)

    def get(self, template_id: str, version: Optional[str] = None, missing_ok: bool = False):
        rows = self.versions(template_id)
        if version:
            rows = [r for r in rows if r["version"] == version]
        if not rows:
            if missing_ok:
                return None
            have = sorted({i for i, _ in self._items})
            raise LibraryError(f"no prompt template {template_id!r}{f'@{version}' if version else ''}; the templates are: {', '.join(have)}")
        return rows[0]

    def list(self, media: Optional[str] = None) -> list:
        ids = sorted({i for i, _ in self._items})
        out = [self.get(i) for i in ids]
        return [t for t in out if media in (None, t["media"])]

    # ---------------------------------------------------------------------------------- saving
    def save(self, template: dict) -> str:
        """Write ``template`` to the USER scope. Refused when invalid (every reason with its path) or when that id@version already exists."""
        problems = S.validate(template)
        if problems:
            raise LibraryError("the template is invalid: " + "; ".join(f"{p['path'] or '(root)'}: {p['reason']}" for p in problems))
        user = self.dirs["user"]
        if not user:
            raise LibraryError("no user prompt directory is configured")
        key = (template["id"], template["version"])
        if key in self._items:
            raise LibraryError(f"{template['id']}@{template['version']} already exists ({self._items[key]['scope']}): a new wording is a new version, "
                               "never an overwrite - bump the version")
        Path(user).mkdir(parents=True, exist_ok=True)
        path = Path(user) / f"{template['id']}@{template['version']}.json"
        path.write_text(json.dumps(template, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.reload()
        return str(path)
