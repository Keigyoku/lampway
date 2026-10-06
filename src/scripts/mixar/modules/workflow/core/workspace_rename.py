# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The captain's rename (2026-10-06): the agent-first workspace Mixar called "Zen Mode" is Lamplight. A file saved
before the rename still has the old name; on load it is renamed in place, so its layout and contents come with it.
Never when the file already has a Lamplight workspace (that one wins; the old one is left as the user's own tab)."""

from ..constants import BASIC_WORKSPACE_NAME, LEGACY_BASIC_WORKSPACE_NAMES


def rename_legacy(workspaces) -> list:
    """Rename a legacy-named workspace in ``workspaces`` (``bpy.data.workspaces``); return the old names renamed."""
    renamed = []
    for old in LEGACY_BASIC_WORKSPACE_NAMES:
        ws = workspaces.get(old)
        if ws is not None and workspaces.get(BASIC_WORKSPACE_NAME) is None:
            ws.name = BASIC_WORKSPACE_NAME
            renamed.append(old)
    return renamed
