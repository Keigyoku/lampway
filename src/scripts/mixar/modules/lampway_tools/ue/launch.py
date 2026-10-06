# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The launcher's UE Look state: ``<lampway home>/ue_look/launch.state``, present only while UE Look is enabled with a cube that
validated. scripts/lampway/lampway reads it (plain ``key=value`` lines, never sourced) and exports OCIO to ``config`` only when
the file exists, the config exists and the cube's sha256 still equals ``cube_sha256``; otherwise OCIO is left untouched."""

from pathlib import Path

from .. import settings as S


def state_path() -> Path:
    return S.lampway_home() / "ue_look" / "launch.state"


def enable(config_path, cube_path, cube_sha256, view_name):
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".partial")
    tmp.write_text(f"config={config_path}\ncube={cube_path}\ncube_sha256={cube_sha256}\nview={view_name}\n", encoding="utf-8")
    tmp.replace(p)
    return str(p)


def disable() -> bool:
    p = state_path()
    if p.exists():
        p.unlink()
        return True
    return False
