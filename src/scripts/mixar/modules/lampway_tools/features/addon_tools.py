# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""addon_project: the agent edits a Blender add-on package patch by approved patch (specs/mixar_docs/addon_project.md). The Client's AddonProjectService
(modules/addon_project: staging, checks, transactional commit, history, rollback, install) does the work; these are its agent wrappers.

A project is one the Client already links in its add-on projects registry (by id or name): anything else is refused ("works on projects inside that folder
only"). A staged patch is committed only after the user approves that proposal in the Client (the ``lampway.addon_approve`` operator, a click): the
approval is recorded here, in memory, per proposal, and an agent's own claim of approval is not one. Commit runs the service's checks and reports
whether the add-on installed; a failing check installs nothing. Rollback goes through the same service."""

from ...addon_project.errors import AddonProjectError
from ...addon_project.service import get_addon_project_service
from .. import human_gate
from . import common as C

_APPROVED: dict = {}          # proposal id -> project id: set only by the user's click (operator LAMPWAY_OT_addon_approve)


def approve(project_id: str, proposal_id: str) -> None:
    """Called by the approval operator only; refused while any script runs (human_gate), so an agent script calling it directly is refused too."""
    if human_gate.script_running():
        raise C.FeatureError("approving a patch is the user's click: a script cannot")
    _APPROVED[str(proposal_id)] = str(project_id)


def _project(service, project):
    known = []
    for pid in list(service.registry._load()):
        try:
            _root, man = service.registry.resolve(pid)
        except AddonProjectError:
            continue
        known.append(man.get("name") or pid)
        if project in (pid, man.get("name")):
            return pid
    raise C.FeatureError(f"no add-on project {project!r}: the tools work on projects inside the Client's add-on projects folder only "
                         f"(link one in the Add-on tab first); the linked projects are {sorted(known)}")


def _err(call, *a, **k):
    try:
        result = call(*a, **k)
    except AddonProjectError as exc:
        raise C.FeatureError(f"{getattr(exc, 'code', 'addon_project')}: {exc}") from None
    if isinstance(result, dict) and result.get("success") is False:
        raise C.FeatureError(str(result.get("error") or result.get("message") or result))
    return result


def addon_read(project, path):
    svc = get_addon_project_service()
    pid = _project(svc, project)
    return _err(svc.read, pid, [{"path": path}])


def addon_stage_patch(project, files, message="", expected_revision=None):
    svc = get_addon_project_service()
    pid = _project(svc, project)
    if not isinstance(files, list) or not files:
        raise C.FeatureError("files is [{path, content}] (content null deletes the file)")
    changes = [{"path": f.get("path", ""), "operation": "delete" if f.get("content") is None else "write", "content": f.get("content")} for f in files]
    rev = expected_revision or _err(svc.describe, pid)["revision"]          # the revision read (addon_read returns it); else the current one
    out = _err(svc.stage_patch, pid, {"changes": changes, "summary": str(message), "expected_revision": rev})
    return {"patch_id": out["proposal_id"], "base_revision": out.get("base_revision"), "changes": out.get("changes"),
            "next": "show the patch to the user: they approve it in the Client (Approve patch); only then addon_commit"}


def addon_commit(project, patch_id):
    svc = get_addon_project_service()
    pid = _project(svc, project)
    if _APPROVED.get(str(patch_id)) != pid:
        raise C.FeatureError("a patch is committed only after the captain approves it (ask with clarify, then his click on Approve patch in the Client); "
                             f"{patch_id} has no approval")
    try:
        res = _err(svc.commit_patch, pid, str(patch_id))
    finally:
        _APPROVED.pop(str(patch_id), None)
    try:
        checks = svc.run_checks(pid, reload_blender=True)                    # the commit stands; a failing check installs nothing and says why
    except AddonProjectError as exc:
        checks = {"success": False, "error": f"{getattr(exc, 'code', 'addon_project')}: {exc}"}
    return {"committed": res, "checks": checks, "installed": bool(checks and checks.get("success") and (checks.get("blender_reload") or {}).get("success"))}


def addon_rollback(project, to, expected_revision=None):
    svc = get_addon_project_service()
    pid = _project(svc, project)
    rev = expected_revision or _err(svc.describe, pid)["revision"]
    return _err(svc.rollback, pid, str(to), str(rev))
